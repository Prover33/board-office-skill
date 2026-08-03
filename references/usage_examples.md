# 命令示例与典型工作流

> 本文件为 SKILL.md 的补充参考，AI 在需要详细命令行示例时查阅。
> 所有脚本通过 `${SKILL_DIR}/scripts/` 定位，`${SKILL_DIR}` 为 SKILL.md 所在目录。

## 一、公告案例检索全流程

### 1.1 基础检索

```bash
# 代码 + 行为（最精准）
python "${SKILL_DIR}/scripts/search_cninfo.py" "<TICKER> 回购" --pagesize 20 --json /tmp/result.json

# 全市场某类行为 + 类型过滤 + 时间窗
python "${SKILL_DIR}/scripts/search_cninfo.py" "违规担保" \
  --start 2025-07-15 --end 2026-07-15 \
  --type 担保 --pagesize 15 --json /tmp/result.json

# 精确短语（引号）
python "${SKILL_DIR}/scripts/search_cninfo.py" '"控股权转让协议"' --pagesize 20

# 关闭同义词扩展（精准但召回少）
python "${SKILL_DIR}/scripts/search_cninfo.py" "并购" --no-expand --pagesize 20
```

### 1.2 高级用法

```bash
# 多代码过滤
python "${SKILL_DIR}/scripts/search_cninfo.py" "回购" --code <TICKER>,<示例代码> --pagesize 20

# 翻页深度（默认10页，可调）
python "${SKILL_DIR}/scripts/search_cninfo.py" "对外担保" --start 2024-01-01 --maxpages 20

# 并行度调整（默认8并发，网络差可降到4）
python "${SKILL_DIR}/scripts/search_cninfo.py" "关联交易" --workers 4
```

### 1.3 生成报告

```bash
# 生成案例分析 Word 报告（需 python-docx）
python "${SKILL_DIR}/scripts/build_docx.py" \
  /tmp/report.json \
  "公告案例分析_<主题>_<日期>.docx"
```

## 二、临时公告起草全流程

### 2.1 扫描历史同类

```bash
# 扫描某类型历史公告（需 CSV 索引文件）
python "${SKILL_DIR}/scripts/find_similar.py" "担保" \
  --csv <索引CSV路径> --limit 10

python "${SKILL_DIR}/scripts/find_similar.py" "减持" \
  --csv <索引CSV路径> --year 2025

python "${SKILL_DIR}/scripts/find_similar.py" "权益分派" \
  --csv <索引CSV路径> --limit 5 --all
```

### 2.2 生成公告 docx

```bash
# 基于母版生成公告（需母版 docx + lxml）
python "${SKILL_DIR}/scripts/new_announcement.py" \
  --base <母版docx完整路径> \
  --json announcement.json \
  --out "output/董事会决议公告.docx"
```

### 2.3 JSON 输入范例

见 `scripts/sample_announcement.json`，核心字段：
- `header`: 证券代码/简称/编号
- `title_full` / `title_name`: 公司全称 + 公告名称
- `sections`: 公告章节数组（`t`=note/h1/h2/h3/p, `v`=内容）
- `sign_org` / `sign_date`: 落款机构 + 日期

## 三、典型端到端场景

### 场景 A：做一份"对外担保"案例分析报告

1. 检索：`search_cninfo.py "对外担保" --start 2025-01-01 --type 担保`
2. AI 筛选合并为 20+ 案例，构造 JSON（参考 `references/report_template.md`）
3. 生成报告：`build_docx.py /tmp/report.json "对外担保案例分析_<日期>.docx"`
4. 归位到 `03-案例与法规/`

### 场景 B：起草一份董事会决议公告

1. 扫描历史：`find_similar.py "董事会决议" --csv <索引CSV路径> --limit 5`
2. 套母版或参考同业（巨潮网搜同类），收集议案/表决/出席信息
3. 构造 JSON（参考 `sample_announcement.json`）
4. 生成：`new_announcement.py --base <母版路径> --json input.json --out "决议公告.docx"`
5. 过自检清单，归位到 `01-公文草稿/`

### 场景 C：搜索"章程里董秘提名权怎么写"

1. cninfo 搜章程清单：`search_cninfo.py "公司章程" <TICKER>`（定位文件）
2. 取正文：搜索引擎 `"董事会秘书由董事长提名" 公司章程` 或下载 PDF→PyMuPDF 提取
3. 生成报告：对比多家，输出结论
