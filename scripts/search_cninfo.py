#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巨潮网(cninfo)全文检索 —— 按关键词/公司代码搜全市场A股公告，输出结构化JSON。

接口: POST http://www.cninfo.com.cn/new/fulltextSearch/full
参数: searchkey / pageNum / pageSize / sortName=pubdate / sortType=desc
返回: announcements[]，含 announcementId/secCode/secName/announcementTitle/announcementTime/announcementType 等

说明:
  - 巨潮网原生全文检索，关键词可命中公告标题与正文。
  - 最佳用法：把"公司代码 + 行为关键词"一起放进 searchkey（如 "<TICKER> 回购"），
    接口会服务端按公司收窄，比单纯关键词堆砌精准得多。
  - 响应为 UTF-8；标题含 <em> 高亮标签，本脚本自动剥离。
  - 不返回 PDF 直链，但返回稳定的 detailUrl 原文页。

过滤参数（后置过滤，因接口本身不带这些参数，拿到结果后再筛）：
  --code  600XXX,000XXX   只保留该 secCode（可逗号分隔；一般配合 searchkey 已含代码使用，作为校验）
  --start YYYY-MM-DD       公告日期 >= 该日
  --end   YYYY-MM-DD       公告日期 <= 该日
  --type  担保            公告标题含该子串才保留（注意 announcementType 是数字代码，故按标题匹配）
  --expand / --no-expand  同义词扩展（默认开）。开启时，对命中的概念词做同义词/上下位词泛化，
                          多路并行检索后按 announcementId 去重融合。
                          例: "并购" → 同时搜 [并购, 收购, 受让, 购买资产, 股权收购]，召回率显著提升。

分页说明: 当 --start/--end/--type 任一生效时，会自动翻页抓取（最多 --maxpages 页）以覆盖非近期匹配；
          否则只取单页（快速路径）。

性能优化：
  - 多路同义词检索 + 翻页请求全部并发执行（--workers，默认8），不再串行排队。
  - 命中够了就停：当去重后满足过滤的结果达到 --target（默认20）时，取消剩余请求提前返回。
  - 单次 HTTP 请求失败自动重试（--retries，默认3），指数退避（首次等待 --retry-delay 秒）。

依赖: 仅标准库(urllib + concurrent.futures)，无需安装第三方包。
"""
import sys, json, re, urllib.request, urllib.parse, argparse, datetime, time
from concurrent.futures import ThreadPoolExecutor, as_completed

API = 'http://www.cninfo.com.cn/new/fulltextSearch/full'
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Referer': 'https://www.cninfo.com.cn/',
}


def _strip(s):
    return re.sub(r'<[^>]+>', '', s or '')


def _norm_date(ts):
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
    dt = re.sub(r'[^0-9]', '', str(ts or ''))
    if len(dt) >= 8:
        return '%s-%s-%s' % (dt[0:4], dt[4:6], dt[6:8])
    return ''


def _tokenize(key):
    """把检索词拆成用于相关性打分的小词（去 CNINFO 布尔/引号符号）。"""
    toks = []
    for t in key.split():
        t = t.strip('"').strip()
        if not t or t.upper() in ('OR', 'NOT'):
            continue
        toks.append(t)
    return toks


# 同义词 / 概念扩展表（参考 Wind 规则五：同义词扩展、上下位词扩展、缩写还原）。
# 仅覆盖董办高频场景；命中任一概念词即展开其同义词集合，多路检索后融合去重。
SYNONYMS = {
    '并购': ['并购', '收购', '受让', '购买资产', '股权收购'],
    '收购': ['收购', '并购', '受让', '股权收购'],
    '重组': ['重组', '重大资产重组', '资产置换'],
    '担保': ['担保', '对外担保', '违规担保'],
    '处罚': ['处罚', '行政处罚', '罚款', '警示函', '监管函', '立案'],
    '分红': ['分红', '派息', '利润分配', '派现'],
    '股权激励': ['股权激励', '期权', '限制性股票', '员工持股'],
    '诉讼': ['诉讼', '仲裁', '判决', '裁定'],
    '减持': ['减持', '股份减持'],
    '增持': ['增持', '股份增持'],
    '回购': ['回购', '股份回购'],
    '关联交易': ['关联交易', '关联方'],
    '业绩': ['业绩', '业绩预告', '业绩快报'],
    '违规': ['违规', '违法', '资金占用', '违规担保'],
    '人工智能': ['人工智能', 'AI', '机器学习', '大模型'],
    '新能源': ['新能源', '锂电', '动力电池', '电动车'],
}


def expand_queries(key):
    """把检索词展开为多路候选检索式（同义词泛化）。返回含原始式在内的候选列表。"""
    toks = key.split()
    code = ''
    kws = []
    for t in toks:
        if re.fullmatch(r'\d{6}', t):
            code = t
        else:
            kws.append(t)
    base_kw = ' '.join(kws) if kws else key
    extra = []
    for t in kws:
        if t in SYNONYMS:
            extra.extend(SYNONYMS[t])
    if base_kw in SYNONYMS:
        extra.extend(SYNONYMS[base_kw])
    queries = [key]
    seen = {key}
    for e in extra:
        q = ('%s %s' % (code, e)).strip() if code else e
        if q not in seen:
            seen.add(q)
            queries.append(q)
    return queries[:8]  # 上限保护，避免 API 调用爆炸


MAX_RETRIES = 3          # 单次请求最大重试次数（可被 --retries 覆盖）
RETRY_BASE_DELAY = 3      # 首次重试等待秒数（后续指数递增）
HTTP_TIMEOUT = 20          # 单次请求超时秒数（可被 --timeout 覆盖）


def _fetch_page(key, pagesize, pagenum, timeout=HTTP_TIMEOUT):
    """抓取单页结果。失败（网络/HTTP/JSON）直接抛异常，交由调用方重试。"""
    data = urllib.parse.urlencode({
        'searchkey': key,
        'pageNum': str(pagenum),
        'pageSize': str(pagesize),
        'sortName': 'pubdate',
        'sortType': 'desc',
    }).encode()
    req = urllib.request.Request(API, data=data, headers=HEADERS)
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        # 4xx/5xx：服务端明确拒绝，重试无意义，直接抛出
        raise RuntimeError('HTTP %s 抓取失败 q=%r p=%s' % (e.code, key, pagenum))
    except urllib.error.URLError as e:
        raise RuntimeError('网络错误 q=%r p=%s: %s' % (key, pagenum, e.reason))
    try:
        j = json.loads(raw)
    except ValueError:
        j = {}
    if not isinstance(j, dict):
        j = {}
    toks = _tokenize(key)
    out = []
    for a in (j.get('announcements') or []):
        aid = a.get('announcementId')
        title = _strip(a.get('announcementTitle'))
        dt = _norm_date(a.get('announcementTime'))
        score = 0
        low = (title + ' ' + (a.get('secName') or '')).lower()
        for tk in toks:
            if tk.lower() in low:
                score += 2
        out.append({
            'announcementId': aid,
            'secCode': a.get('secCode'),
            'secName': _strip(a.get('secName')),
            'announcementTitle': title,
            'announcementTime': dt,
            'announcementType': a.get('announcementType'),
            'adjunctUrl': a.get('adjunctUrl'),
            'detailUrl': 'https://www.cninfo.com.cn/new/disclosure/detail?announcementId=%s' % aid,
            '_score': score,
        })
    return out, j.get('totalRecordNum'), j.get('totalpages')


def search(key, pagesize=10, pagenum=1, filters_active=False, maxpages=10,
            timeout=HTTP_TIMEOUT, retries=MAX_RETRIES):
    """（保留兼容）filters_active=True 时翻页聚合（最多 maxpages 页），否则单页。串行。"""
    if not filters_active:
        rows, total, pages = _safe_fetch(key, pagesize, pagenum, timeout, retries)
        return rows, total, pages
    collected = []
    total = pages = 0
    ps = max(pagesize, 20)
    for pg in range(1, maxpages + 1):
        rows, total, pages = _safe_fetch(key, ps, pg, timeout, retries)
        collected.extend(rows)
        if pg >= (pages or 1):
            break
    return collected, total, pages


def _safe_fetch(key, ps, pg, timeout=HTTP_TIMEOUT, retries=MAX_RETRIES):
    """带自动重试的安全抓取：失败时指数退避重试，最多 retries 次。

    对 HTTPError（4xx/5xx）不重试（服务端明确拒绝，重试无意义），直接返回空。
    其余网络/超时/解析异常按指数退避重试。
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return _fetch_page(key, ps, pg, timeout)
        except RuntimeError as e:
            # HTTPError 类错误，不再重试
            last_err = e
            sys.stderr.write('[fail] q=%r p=%s 不重试: %s\n' % (key, pg, e))
            return [], 0, 0
        except Exception as e:  # urllib 超时 / 连接错误 / 其它
            last_err = e
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                sys.stderr.write('[retry] q=%r p=%s 第%d/%d次，%.0fs后重试… (%s)\n'
                                % (key, pg, attempt, retries, delay, e))
                time.sleep(delay)
            else:
                sys.stderr.write('[fail] q=%r p=%s 已重试%d次均失败: %s\n' % (key, pg, retries, e))
    return [], 0, 0


def search_all(queries, pagesize, filters_active, maxpages, filt, target, workers,
               timeout=HTTP_TIMEOUT, retries=MAX_RETRIES):
    """并发多路检索 + 翻页 + 命中够了就停。

    queries      : 多路检索式（同义词扩展后）
    filt(r)->bool: 过滤器（代码/日期/类型）
    target       : 去重后达到该数量即提前停止翻页
    timeout      : 单次请求超时秒数
    retries      : 单次请求最大重试次数
    返回 (merged_dict, api_total)
    """
    merged = {}
    api_total = 0
    fail_count = 0   # 失败计数（用于网络波动检测）
    total_requests = 0

    def _merge(rows):
        for r in rows:
            if not filt(r):
                continue
            aid = r['announcementId']
            if aid not in merged or r['_score'] > merged[aid]['_score']:
                merged[aid] = r

    ps = max(pagesize, 20) if filters_active else pagesize

    # 阶段一：并发抓每一路的第 1 页（顺便拿到各路总页数）
    page_of = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_safe_fetch, q, ps, 1, timeout, retries): q for q in queries}
        total_requests += len(futs)
        for f in as_completed(futs):
            q = futs[f]
            rows, total, pages = f.result()
            api_total = max(api_total, total or 0)
            page_of[q] = pages or 1
            if not rows:  # 空结果 = 可能是失败
                fail_count += 1
            _merge(rows)

    # 无过滤：单页快速路径，直接返回
    if not filters_active:
        return merged, api_total

    # 已达标：无需翻页
    if len(merged) >= target:
        return merged, api_total

    # 阶段二：并发抓剩余页（2..min(pages,maxpages)），达标即取消余下
    tasks = []
    for q, pages in page_of.items():
        for pg in range(2, min(pages, maxpages) + 1):
            tasks.append((q, pg))
    if not tasks:
        return merged, api_total

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_safe_fetch, q, ps, pg, timeout, retries): (q, pg) for q, pg in tasks}
        total_requests += len(futs)
        for f in as_completed(futs):
            rows, _, _ = f.result()
            if not rows:
                fail_count += 1
            _merge(rows)
            if len(merged) >= target:
                for ff in futs:
                    ff.cancel()
                break

    # 网络波动检测：如果失败占比 > 30%，打印警告
    if total_requests > 0 and fail_count / total_requests > 0.3:
        sys.stderr.write('[提示] 结果可能不完整：%.0f%% 的请求失败（%d/%d），可能是网络波动。建议重试一次确认。\n'
                         % (fail_count / total_requests * 100, fail_count, total_requests))

    return merged, api_total


def _pass_filters(r, codes, start, end, typ):
    if codes and (r.get('secCode') not in codes):
        return False
    if start and (r.get('announcementTime') or '') < start:
        return False
    if end and (r.get('announcementTime') or '') > end:
        return False
    if typ:
        # announcementType 是数字代码(如 01010503)，故按标题/公司名匹配人类可读词
        blob = '%s %s' % (r.get('announcementTitle') or '', r.get('secName') or '')
        if typ not in blob and typ not in (r.get('announcementType') or ''):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description='巨潮网(cninfo)全文检索')
    ap.add_argument('keyword', help='关键词或"代码 关键词"（推荐），支持空格(AND)/OR/NOT/引号精确短语')
    ap.add_argument('--pagesize', type=int, default=20, help='每路检索单页条数（默认20，确保首页即≥20）')
    ap.add_argument('--pagenum', type=int, default=1)
    ap.add_argument('--json', default='', help='把结构化结果写入该JSON文件')
    ap.add_argument('--code', default='', help='按secCode过滤，逗号分隔多个，如 <TICKER>')
    ap.add_argument('--start', default='', help='公告起始日期 YYYY-MM-DD')
    ap.add_argument('--end', default='', help='公告截止日期 YYYY-MM-DD')
    ap.add_argument('--type', default='', help='公告标题含该子串才保留（如 担保/处罚/回购）')
    ap.add_argument('--maxpages', type=int, default=10, help='启用过滤时最多翻页数（默认10）')
    ap.add_argument('--no-expand', dest='expand', action='store_false', default=True,
                    help='关闭同义词扩展（默认开启）')
    ap.add_argument('--workers', type=int, default=8, help='并发请求数（默认8）')
    ap.add_argument('--target', type=int, default=20, help='去重后达到该数量即提前停止翻页（默认20）')
    ap.add_argument('--timeout', type=float, default=HTTP_TIMEOUT,
                    help='单次 HTTP 请求超时秒数（默认%d）' % HTTP_TIMEOUT)
    ap.add_argument('--retries', type=int, default=MAX_RETRIES,
                    help='单次请求失败重试次数（默认%d，指数退避）' % MAX_RETRIES)
    args = ap.parse_args()

    codes = [c.strip() for c in args.code.split(',') if c.strip()] if args.code else []
    filters_active = bool(codes or args.start or args.end or args.type)

    # 同义词扩展 → 多路候选检索式
    queries = expand_queries(args.keyword) if args.expand else [args.keyword]
    if args.expand and len(queries) > 1:
        sys.stderr.write('[expand] %s\n' % ' | '.join(queries))

    # 并发多路检索 + 翻页 + 命中够了就停
    filt = lambda r: _pass_filters(r, codes, args.start, args.end, args.type)
    merged, api_total = search_all(queries, args.pagesize, filters_active,
                                   args.maxpages, filt, args.target, args.workers,
                                   timeout=args.timeout, retries=args.retries)
    rows = list(merged.values())
    rows.sort(key=lambda r: (r['_score'], r['announcementTime']), reverse=True)

    # 案例数量下限提示（用户要求：每次检索目标 ≥20 个案例；若真实不足请如实说明，不硬凑）
    note = ''
    if len(rows) < 20:
        note = '结果仅 %d 条（低于建议下限 20），该主题可能较稀疏；如可接受请继续，否则建议：放宽 --start/--end 时间窗、去掉 --type 限制、或确认已开启 --expand 同义词扩展' % len(rows)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump({'keyword': args.keyword, 'totalRecordNum': api_total,
                       'after_filter': len(rows),
                       'expanded_queries': queries if args.expand else [args.keyword],
                       'note': note, 'results': rows}, f, ensure_ascii=False, indent=2)
        print('saved %s  (api_total=%s, after_filter=%s)' % (args.json, api_total, len(rows)))
    else:
        print('api_total=%s  after_filter=%s' % (api_total, len(rows)))
        for i, r in enumerate(rows, 1):
            print('%2d. [%s] %s(%s) %s' % (i, r['announcementTime'], r['secName'], r['secCode'], r['announcementTitle']))
            print('    %s' % r['detailUrl'])
        if note:
            print('\n[提示] %s' % note)


if __name__ == '__main__':
    main()
