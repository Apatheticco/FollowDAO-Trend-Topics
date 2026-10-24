# 扫描详章（参考件）

> **v3.7.15 精简**：跑哪些通道、参数、兜底＝`~/.trend-scout/channels.json`（`checklist.sh channels` 查看；`checklist.sh start→mark→verify` 打勾，verify 拒未填／✅ 不带计数／❌ 不写兜底）。并发＝`gate.sh 并发编排`；调用硬约束＝`gate.sh 调用约束`；故障分型、熔断、降级梯、半盲＝`gate.sh 通道故障`；判模式（跨天＝首扫／同日＝刷新）与时间校准＝SKILL §0 ＋ `gate.sh 开跑铁律`。本文件只留这些地方装不下的细节。v2.x 原文（TG exploit 词探针、3×10 板块批、油 `CLUSD`、不跑 signal、候选池扩窗兜底、手拍 `last-refresh.txt` 等已作废口径）在 git `0deeaa3` 版本。

## Followin 调用细节（10-24 对 schema 实测）

- **news**：没有 `categories`；`sort_by` 有（带 query：time 默认／relevance；空 query 热榜：hot 默认／time）。生产用 `verbosity="concise"`（每字段 200 字；standard 是 600）＋ `limit≤15`。
- **news TG**（`sources=["telegram"]`）：返回字段 `tg_category / author_name / content / _source_quality / published_ts`，**没有 username**，按 `author_name` 过滤去重。query 必须是具体币种/资产词（泛词返回 degraded 0 条，参数见 json「TG探针或兜底」）。
- **tradfi 新闻**：`news(asset_type="tradfi")` 几乎每轮返 0，已从批次砍掉；美股新闻用 `news(query=<当周热点词>, 不传 asset_type)`，词按当周热点自拟（例：`"NVIDIA chip export China"`、`"earnings beat miss guidance"`）。
- **metrics 价格调用一律加 `categories=["market"]`**——不加会扇出 macro＋fundamentals，tradfi 几只股就溢出上下文。keywords ≤5／批的硬约束 → `gate.sh 调用约束`。
- **大宗裸词会解析成同名股票**（`gold`→Barrick、`CL`→Colgate）：金用 `XAUT`／`PAXG`@crypto，油用 `yahoo_price CL=F`（`CLUSD` 已废，返回 FRED 历史错值），美元 `DXY`。
- **美股涨跌榜**：metrics 的 movers 只覆盖美股（`query="biggest gainers"`，默认去掉 <$1 股）；**crypto 涨跌榜不走 metrics**，走 `okx.py`（见下）。
- **econ 日历**：传 `date_from=今天`、`date_to=+5d` 才有前瞻（`actual=null`＋`estimate` 有值＝未公布）；`sort_by="hot"` 把高影响的排前；不传 keywords（每个 keyword 各回一堆 JP/KR 噪音）。
- **twitter list_timeline**：只收 `list_id`／`cursor`／`limit`（≤20），没有时间窗参数——增量过滤由子进程按 `createdAt` 自己做。
- **脚本直连**（v3.3.3）：followin 是 SSE 型 MCP，`news-fetch.py` 已封装（GET `/sse` 拿 endpoint → POST `initialize` → POST `tools/call`，结果从 SSE 流回）；`hot-scan.py` 的 L2 层用它。

## 取价

- **报告和标题里的价格/涨跌幅只能来自工具实测**：美股/港股长桥 `quote`、A 股长桥 `.SH/.SZ`、韩日港等非美正股 followin metrics（`.KS/.T/.HK` 可直查）、油 yahoo `CL=F`、币 `pct.py bn`／`okx.py t`、新链 meme `dex.py t <SYM>`（先查 `contracts.json` 按地址取）。涨跌幅只用 `pct.py` 算。新闻/TG/推文里的价格只算叙事来源，报告分 📊 实测 与 📰 叙事 两区。正股优先与降级梯 → `gate.sh 通道故障`。
- **价格应急扩列**：news/TG/推特文本里出现 ±15% 以上、又不在固定 10 币表的代币 → 收集起来跑一轮实测核验；核过的进 📊 区，没核的只能进 📰 区并标 ⚠️ 单源未核。

## 链上候选

- 准入红线（地址级链上流水整体剔除，金额≠信息价值）以 `gate.sh A闸`「撤因闸的优先级」条为唯一口径（v3.5.1 已扩到单一地址/巨鲸/大户/机构的买入扫货、持仓、浮盈浮亏）。
- 旧版「可识别身份＋叙事」白名单（知名实体财库增减持、官方地址异动、有身份玩家动作）10-24 用户定删除，一律按红线判；解锁、抛售公告等走事件日历／预告题路径，财库周报类另过 `gate.sh 时效` 内容时效。

## 推特双栈（A1 子进程）

- **主进程粗排双轨**（子进程只 dump 不算分）：Velocity 轨 `(likes + 2×rt + 0.5×reply) / max(发帖小时数, 0.25)` 取前 7 ＋ Recency 轨按时间取前 3 ＋ **30 分钟内的新推无条件保留**，合并去重约 10 条。纯按互动排在 4h 窗里会压死新推、刷新和首扫大面积重叠。
- **子进程 prompt 模板**（N 值、list ID、server 降级梯以 json「A1主栈／A1科技栈」为准；`model=haiku`）：

```
调用 followin.twitter(action="list_timeline", list_id="<LIST_ID>", limit=20)。
若报 session initialization / session not found：等约 10 秒重试，最多 3 次；followin 报配额耗尽或取数失败再换 followdao-test 同参重试。
时间过滤：createdAt 晚于 <LAST_REFRESH_TS> 的才留（该值取自 last-refresh.txt 末行，文件存毫秒，换成与 createdAt 相同的单位再比；首扫不滤）。
按 createdAt 倒序输出最新 <N> 条，每条一行：
[MM/DD HH:MM] @author | 👍likes 🔁rt 💬reply | text前130字
不要计算分数，不要返回 full_content / 媒体链接 / 原始 json。
```

- **增量时间戳只由脚本写**：收尾 `log-snapshot.sh refresh`，禁止手动 echo。

## crypto 异动（`okx.py` 直连，v3.3.0 起不走 okx MCP）

```
~/.trend-scout/okx.py movers --top 12 [--minvol 15000000]   # 涨跌两榜一次出，带美元成交额
~/.trend-scout/okx.py oi --top 12 [--minoi 10000000]        # OI 榜 + 与上轮快照的变化率（首次无基线打印 n/a）
~/.trend-scout/okx.py t SOPH USELESS CP                     # 单/多标的实测，不存在的 instId 不中断整批
```

- 成交额口径（`volCcy24h` 是币数，脚本已 × last 换美元）、首次无基线、OI 变化率跨度＝两次运行的实际间隔，都已在脚本里处理；读数时看打印的基线时间戳。
- okx 挂 → `tradingview top_gainers/top_losers` 兜底，但单源不下「干轮」结论（`gate.sh 通道故障` movers 条）。

## C 入口：定向检索

| 路径 | 触发 | 并行调用 |
|------|------|---------|
| 代币深挖 | 单一符号 / `$XXX` | `metrics(keywords=[SYM], categories=["market"], asset_type="crypto", time_range="7d")` ＋ `news(query=SYM, time_range="1d", limit=15, verbosity="concise")` ＋ `news(query=SYM, sources=["twitter"], time_range="1d", limit=15)` ＋ `signal(keywords=[SYM])` |
| 关键词深挖 | 项目/公司/事件/人名 | `news(query=KEYWORD, time_range="1d", verbosity="concise", limit=15)` ＋ `news(query=KEYWORD, sources=["twitter"], limit=10)` ＋ `twitter(action="search", query=KEYWORD, query_type="Top")`，不传 asset_type |
| 混合 | 既有标的也有主题 | 两路都跑 |

- 搜索词优先单一实体名（`Covenant AI`），少用多词 AND；突发事件并行 2–3 组不同措辞；推特搜索可加 `since:YYYY-MM-DD`、`min_faves:100`。
- 输出：📊 实测（仅符号路径）／📰 关键事件（时间倒序，带来源与核心数据）／💬 KOL 观点（多空分歧或共识）／🎯 提炼候选 1–3 条（A/B 分＋多源数）→ 进去重对照（`dedup-scoring.md` 0a）。
