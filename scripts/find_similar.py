# -*- coding: utf-8 -*-
"""扫描历史同类公告。

读取用户提供的全量文件名索引 CSV，按关键词筛历史公告目录下的同类公告，
按修改日期降序返回路径。用途：announcement-drafter 技能第 2 步「扫描历史同类」，
优先取最近一份做结构参考。

索引 CSV 需含列（列名需与 --col-* 对应，默认：相对路径/文件名/扩展名/修改日期）：
    相对路径   : 文件相对路径（可含目录层级）
    文件名     : 文件名（含扩展名）
    扩展名     : 文件扩展名（不含点，如 doc/docx）
    修改日期   : 修改日期（YYYY-MM-DD 或含日期的字符串）

用法：
    python find_similar.py "担保" --csv 索引.csv --limit 10
    python find_similar.py "减持" --csv 索引.csv --year 2025
    python find_similar.py "权益分派" --csv 索引.csv --path-contains "02-公告"
"""
import argparse
import csv
import os
import sys


def log_err(msg):
    sys.stderr.write("[错误] %s\n" % msg)


def parse_args():
    ap = argparse.ArgumentParser(description="扫描公告目录历史同类公告")
    ap.add_argument("keyword", help="公告类型关键词，如 担保 / 减持 / 权益分派 / 换届")
    ap.add_argument("--csv", required=True,
                    help="文件名索引 CSV 路径（必传）")
    ap.add_argument("--limit", type=int, default=15, help="返回条数上限（默认15）")
    ap.add_argument("--year", default=None, help="限定年份，如 2025")
    ap.add_argument("--all", action="store_true",
                    help="包含非文档类（默认只返回 .doc/.docx 公告）")
    ap.add_argument("--path-contains", default="01-公文草稿",
                    help="相对路径需含此子串（公告目录标识，可改为空串取消限制）")
    ap.add_argument("--col-path", default="相对路径", help="CSV 中路径列名")
    ap.add_argument("--col-name", default="文件名", help="CSV 中文件名列名")
    ap.add_argument("--col-ext", default="扩展名", help="CSV 中扩展名列名")
    ap.add_argument("--col-date", default="修改日期", help="CSV 中日期列名")
    ap.add_argument("--encoding", default="utf-8-sig",
                    help="CSV 编码（默认 utf-8-sig，兼容带 BOM 文件）")
    return ap.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.csv):
        log_err("索引文件不存在: %s" % args.csv)
        return 1

    kw = args.keyword.lower()
    path_filter = args.path_contains.lower()
    hits = []
    try:
        with open(args.csv, encoding=args.encoding, errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                path = (row.get(args.col_path) or "")
                name = (row.get(args.col_name) or "")
                if path_filter and path_filter not in path.lower():
                    continue
                if args.year and args.year not in (row.get(args.col_date) or ""):
                    continue
                if name.lower().find(kw) >= 0:
                    ext = (row.get(args.col_ext) or "").lower()
                    if not args.all and ext not in ("doc", "docx"):
                        continue
                    hits.append((row.get(args.col_date) or "", path, name))
    except (csv.Error, OSError) as e:
        log_err("读取索引失败: %s (%s)" % (args.csv, e))
        return 1

    hits.sort(key=lambda x: x[0], reverse=True)
    shown = hits[: args.limit]
    if not shown:
        print("[无命中] 关键词='%s' 在 '%s' 下未找到匹配。可换关键词或放宽 --year。"
              % (args.keyword, args.path_contains or "全部目录"))
        return 0
    print("# 命中 %d 条，显示前 %d 条（按修改日期降序）" % (len(hits), len(shown)))
    for d, p, n in shown:
        print("%s\t%s" % (d, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
