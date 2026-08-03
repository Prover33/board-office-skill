# 公司深度资料检索（F10 级）

> 本文件定义董办专家查询公司深度资料（F10 全部维度）的标准流程。
> 覆盖 9 大类：公司基本情况、股本结构、股东研究、财务数据、研报与评级、行情K线、现任董监高、历届董事会/高管换届、新闻公告。

---

## F10 数据源全景

| 数据源 | 可用模块 | 典型工具 |
|--------|---------|---------|
| 通达信 F10（`tdx_api_data`） | 公司概况、董监高、股本结构、股东研究、机构持股、一致预期 | `tdx_api_data` 对应 entry + fixedTag |
| 通达信（其他工具） | 行情、K 线、财务指标、研报、新闻、公告 | `tdx_quotes`, `tdx_kline`, `tdx_indicator_select`, `wenda_*` |
| 企查查 qcc | 工商底档、实控人、受益所有人、股东、对外投资 | `get_company_profile`, `get_actual_controller`, `get_shareholder_info` |
| 天眼查 tyc | 同上 + 司法风险、知识产权 | `get_company_basic_profile`, `search_companies` |
| 新浪财经（联网） | 历届董事会/高管、股本结构、股东研究、分红再融资史 | WebFetch 个股页 |
| cninfo 巨潮网 | 换届公告、年报原文、公告全文 | `search_cninfo.py` |

---

## 一、公司基本情况

### 数据源与入口

| 字段 | 首选 | 交叉 |
|------|------|------|
| 公司全称、简称、代码 | 通达信 F10 公司概况 | 企查查 |
| 上市日期、板块 | 通达信 F10 | 年报/招股书 |
| 注册地址、办公地址 | 企查查（工商底档最权威） | 年报 |
| 主营业务、行业分类 | 通达信 F10 + 年报 | — |
| 注册资本、法定代表人 | 企查查 | 通达信 |
| 员工人数 | 年报 | — |

### 调用示例

```
# 通达信 F10 公司概况
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gsgk" fixedTag="0" code="<TICKER>"

# 企查查工商底档（补充注册资本等精确数据）
get_company_profile(keyword="<COMPANY_OLD>")
```

---

## 二、股本结构

### 数据源与入口

| 字段 | 首选 | 交叉 |
|------|------|------|
| 总股本 / 流通股本 / 限售股本 | 通达信 F10 股本结构 | 新浪个股页 |
| 股本变动记录（增发/回购/送转） | 通达信 F10 + cninfo 公告 | 新浪 |
| 限售股解禁时间表 | 通达信 F10 | cninfo 公告 |

### 调用示例

```
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gbjg" code="<TICKER>" fixedTag="gbjg"
```

---

## 三、股东研究

### 数据源与入口

| 查询 | 工具 | 关键参数 |
|------|------|---------|
| 股东人数变化趋势 | `tdx_api_data` F10 股东研究 | entry=`TdxSharePCCW.tdxf10_gg_gdyj` fixedTag=`gdrs` |
| 前十大流通股东 | `tdx_api_data` F10 股东研究 | entry=`TdxSharePCCW.tdxf10_gg_gdyj` fixedTag=`ltgd` |
| 机构持股明细 | `tdx_api_data` 机构持股 | entry=`TdxSharePCCW.tdxf10_gg_gdyj_jgcgmx` reportDate=`20241231` |
| 实控人/最终受益人 | 企查查 | `get_actual_controller` + `get_beneficial_owners` |
| 股东关联方/一致行动人 | 企查查 | `get_shareholder_info` |

### 调用示例

```
# 股东人数
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gdyj" code="<TICKER>" fixedTag="gdrs" pageNo="1" pageSize="20"

# 十大流通股东
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gdyj" code="<TICKER>" fixedTag="ltgd" pageNo="1" pageSize="20"

# 机构持股明细（需报告期）
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gdyj_jgcgmx" code="<TICKER>" reportDate="20241231"

# 实控人穿透
get_actual_controller(keyword="<COMPANY_OLD>")
```

### 输出规范

- 十大股东表格（编号/股东名称/持股数/持股比例/本期增减持方向）
- 股东人数趋势判断（集中或分散，标注变化幅度）
- 机构持仓变化总结（基金/保险/社保/QFII 持仓变化）

---

## 四、财务数据

### 数据源与入口

| 需求 | 工具 |
|------|------|
| 核心财务指标（营收/利润/ROE/毛利率/负债率/EPS/BPS） | `tdx_indicator_select` |
| 三大报表（资产负债表/利润表/现金流量表） | `tdx_api_data` 对应财报 F10 entry |
| 同比/环比增长 | 自行计算，标注计算口径 |
| 同行业对比 | `tdx_screener` 筛选同行 + `tdx_indicator_select` 批量抓取 |

### 调用示例

```
# 核心财务指标
tdx_indicator_select(code="<TICKER>", indicators=["营收","净利润","ROE","毛利率","资产负债率","每股收益","每股净资产"])

# 同行业对比（以设备租赁为例）
tdx_screener(query="设备租赁行业上市公司")
tdx_indicator_select(code="<每家同行代码>", indicators=["营收","净利润","ROE"])
```

> 须标注报告期（如"2025 年报 / 2026Q1"）与截止日期。不编造、不推算未披露数据。

---

## 五、研报与评级

### 数据源与入口

| 查询 | 工具 | 关键参数 |
|------|------|---------|
| 最新研报列表 | `wenda_report_query` | code + keyword + date_range |
| 一致预期（营收/EPS） | `tdx_api_data` F10 一致预期 | entry=`TdxSharePCCW.tdxf10_gg_ybpj` fixedTag=`yzyq` |
| 机构调研纪要 | `wenda_report_query` | keyword=`调研` |

### 调用示例

```
# 近 90 天研报
wenda_report_query(code="<TICKER>", date_range="last_90_days", limit=20)

# 一致预期
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_ybpj" code="<TICKER>" fixedTag="yzyq"

# 机构调研
wenda_report_query(code="<TICKER>", keyword="调研", limit=20)
```

---

## 六、行情与 K 线

### 数据源与入口

| 查询 | 工具 | 关键参数 |
|------|------|---------|
| 实时价/涨幅/成交/换手 | `tdx_quotes` | codes |
| 日/周/月 K 线 | `tdx_kline` | period=`day`/`week`/`month` |
| 均线/布林等技术指标 | `tdx_indicator_select` | 指标名 |

### 调用示例

```
# 实时行情
tdx_quotes(codes=["<TICKER>"])

# 近 120 个交易日 K 线
tdx_kline(code="<TICKER>", period="day", count=120)
```

> 行情标注截止时间。A 股涨红色跌绿色（中国惯例）。

---

## 七、现任董监高

### 数据源与入口

| 工具 | 返回内容 |
|------|---------|
| `tdx_api_data` F10 董监高（fixedTag=`20`） | 姓名/职务/任职起始日期/性别/年龄 |
| `tdx_security_deep_info` → f9_ashare_board_and_management | 同上 + 简历摘要 |

### 调用示例

```
# F10 董监高
tdx_api_data entry="TdxSharePCCW.tdxf10_gg_gsgk" fixedTag="20" code="<TICKER>"

# 带简历的深度资料
tdx_security_deep_info → f9_ashare_board_and_management
```

---

## 八、历届董事会/高管/换届检索

> 专攻"历史届次"类问题——某届董事会由谁组成、各自任职起止日期、某人何时上任/离任。
> 这是董办高频需求（编年报、筹备换届、回监管问询、独董履历核查、尽调）。

### 关键认知：现任 vs 历史届次，数据源不同

- **现任董事会**：通达信 F10 董监高（fixedTag=`20`）或 `tdx_security_deep_info` → 结构化名册 + 任职日期 + 简历
- **历史届次**：通达信 F9 **不按届次存档**，必须用 **cninfo 换届选举公告 + 年度报告「董事、监事、高级管理人员情况」章节**，并以**新浪财经历届成员页**作交叉核对（按届次带每位成员的任职起始/终止日期，最干净的历史维度源）

> 切勿用二手财经端口（中财网/同花顺高管一览）的滞后快照当作董办口径，也切勿凭印象定性"第 X 届"——届次必须有换届公告/年报出处。

### 标准检索流程（四步）

1. **定届次时间窗**：确认用户问的是第几届。若只说"董事会"默认指现任→走模块三（通达信 F10）。若明确届次→走历史流程，按已知时间窗锁定检索区间。

2. **cninfo 检索换届公告 + 年报**：调用 `search_cninfo.py`，关键词组合：
   - `"<TICKER> 第X届董事会 换届选举"`
   - `"<TICKER> 董事候选人"`
   - `"<TICKER> 董事会换届"`
   - 时间窗覆盖该届次前后
   - 若"第X届"直搜命中噪声，改用"董事候选人""董事会换届"组合，并靠 `--code <TICKER>` 过滤（搜索对简称匹配过宽，会卷进同名/类似名称公司）

3. **新浪历届成员页交叉核对**：WebFetch 新浪财经个股页的「历届董事会成员」子页，提取每位成员的任职起始与终止日期。
   - **注意**：新浪个别届次"起始/终止日期"标签偶有瑕疵，但每位成员的具体起止日期可靠
   - 新浪「历届高管成员」「高管动态」页补充通达信在"历史维度"上的不足

4. **权威确权 + 输出**：以 cninfo 换届公告 + 年报「董事、监事、高级管理人员情况」章节为权威出处；新浪作交叉核对。输出带精确起止日期的名单，标注"任期末在任 / 任内离任 / 任内接任"，附可点击原文链接。新浪与 cninfo 不一致时说明采信依据。

### 数据源分工

| 要什么 | 去哪 |
|--------|------|
| 现任董监高名册（带任职日期） | 通达信 F10 董监高 / F9 深度资料 |
| 历史届次成员 + 任职起止日期 | 新浪历届董事会/高管成员页（交叉核对） + cninfo 换届公告/年报（权威确权） |
| 换届选举公告原文 | cninfo 检索 + 新浪/同花顺镜像抽正文 |
| 高管任免动态 | 新浪"高管动态"页 |

### 坑与注意

- **cninfo 静态 PDF 直链可能失效**：改用新浪/同花顺镜像全文页、或 WebFetch cninfo 详情页
- **搜索对简称匹配过宽**：必须靠 `--code <TICKER>` 或精确全称过滤
- **通达信调用顺序**：`tdx_security_deep_info` 需先 `tdx_lookup_stock` 锁定实体
- **届次定性必须有出处**：禁止拍脑袋；跨届人员易混淆，需标注所属届次

---

## 九、新闻与公告

| 查询 | 工具 | 关键参数 |
|------|------|---------|
| 公司新闻 | `wenda_news_query` | keyword=`公司简称` category=`公司资讯` |
| 最新公告 | `wenda_notice_query` | code + notice_type |
| 正式公告检索 | 走模块四 cninfo 全文检索 | `search_cninfo.py` |

> 新闻/公告仅作信息补充；正式公告案例检索走模块四。

---

## 输出规范

- 数据须标注来源与截止日期
- 财务数据标注报告期
- 行情标注截止时间
- 不同源数据冲突时并列说明采信依据
- 末尾附「💡 潜在需求与下一步」（如：要不要拉同行对比 / 要不要看机构持仓变化 / 要不要查历史分红记录）与（如有缺口）「🔧 待优化项」
