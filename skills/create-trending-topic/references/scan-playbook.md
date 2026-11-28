# 扫描详章（参考件）

> **v3.7.15 精简**：跑哪些通道、参数、兜底＝`~/.trend-scout/channels.json`（`checklist.sh channels` 查看；`checklist.sh start→mark→verify` 打勾，verify 拒未填／✅ 不带计数／❌ 不写兜底）。并发编排＝本文件「并发编排」节（v3.7.38 由 gates 沉入）；调用硬约束＝`gate.sh 调用约束`；故障分型、熔断、降级梯、半盲＝`gate.sh 通道故障`；判模式（跨天＝首扫／同日＝刷新）与时间校准＝SKILL §0 ＋ `gate.sh 开跑铁律`。本文件只留这些地方装不下的细节。v2.x 原文（TG exploit 词探针、3×10 板块批、油 `CLUSD`、不跑 signal、候选池扩窗兜底、手拍 `last-refresh.txt` 等已作废口径）在 git `0deeaa3` 版本。

## 并发编排（v3.7.38 由 gates 闸:并发编排、闸:调用约束「单 turn 齐发」沉入；通道存在性与参数以 channels.json 为准）

- **刷新**：B0 console＋B1/B2 followin（每批塞满 ≤5 槽）＋`okx.py movers`/`oi`（直连）＋A1 双栈**同一 turn 齐发**；油 `yahoo_price CL=F` 与 W-HL 不占 followin 槽。
- **首扫**：4 波 followin **每波严格塞满 5 槽**（v2.5.1——别欠装、别为 1 个 call 单开一波；spx 必 fail→SPY/QQQ/DIA 兜底预判直塞 W1（DIA 11-06 进 IDX 对账表））：W1 价格核心（＋B0＋A1＋油同波起）→ W2 事件/链上 → W3 板块前半＋econ 日历 → W4 板块后半＋国债＋涨跌榜。板块矩阵 6 批×5 受**美股时段闸**：休市/盘前＝上一收盘陈旧，跳过标注、开盘后再拉。
- **A1 双栈走 `tw-dump.py` 直连（约 8 秒，不起子进程）**，W1 波就起；list ID 与参数见 channels.json。
- **单 turn 齐发**（v2.8.9）：刷新模式**全部批次（B0 console + B1/B2 followin + okx.py movers/oi + A1 tw-dump.py）同一条消息齐发**——各批无数据依赖，分波纯浪费；墙钟=最慢一路（全轮 4-5min）。两大违规：① 单 call 单 turn 逐个调、call 间夹叙述；② 首扫 W2-W4 只等 followin 前一波返回即续发，不等其他通道（B0/A1/okx/TG 与 W1 同发）。
- **W-HL 条件触发三选一**（json guard 同步）：①美股非 regular 时段轮 ②followin `no_match`（A股/pre-IPO/韩指，quirk⑯）③需 OI/成交额判资金流向。铁律：`dex="xyz"` 不可省（xyz 标的不在主 universe，直查 `allMids` 会误判"不存在"）；**主锚仍是正股**、文案必标口径（盘后/24h）；`prevDayPx`＝滚动 24h 与当日涨跌幅**口径不同不得混写同一句**（v2.9.10 同族）；薄盘先看 OI/成交额再用价；**拿得到盘后价 ≠ 该改题**（v2.7.8 例外才改）。UNITREE 误判／`11513` 三源对齐／点差实测全文沉 LESSONS v2.9.78。
- **⚠️ 首扫完整性（08-20 复盘）**：跨天首轮不因「对话驱动/上轮刚扫过」缩水——判据：至少覆盖 W1 全通道＋event-watch 全部到期项；只有用户点名的定向轮可轻扫（黄金 4500 漏建／BitMart missed 实证沉 LESSONS）。

## Followin 调用细节（10-24 对 schema 实测）

- **news**：没有 `categories`；`sort_by` 有（带 query：time 默认／relevance；空 query 热榜：hot 默认／time）。生产用 `verbosity="concise"`（每字段 200 字；standard 是 600）＋ `limit≤15`。
- **news TG**（`sources=["telegram"]`）：返回字段 `tg_category / author_name / content / _source_quality / published_ts`，**没有 username**，按 `author_name` 过滤去重。query 必须是具体币种/资产词（泛词返回 degraded 0 条）；**TG 通道主路与填法见 json「TG探针或兜底」**（11-07 Q14：从全源 news 抽 TG 条目）。
- **tradfi 新闻**：`news(asset_type="tradfi")` 返回的是我方看板下游（热榜＝看板），不能当新闻源，已从批次砍掉；美股新闻用 `news(query=<当周热点词>, 不传 asset_type)`，词按当周热点自拟（例：`"NVIDIA chip export China"`、`"earnings beat miss guidance"`）。
- **metrics 价格调用一律加 `categories=["market"]`**——不加会扇出 macro＋fundamentals，tradfi 几只股就溢出上下文。keywords ≤5／批的硬约束 → `gate.sh 调用约束`。
- **大宗裸词会解析成同名股票**（`gold`→Barrick、`CL`→Colgate）：金用 `XAUT`／`PAXG`@crypto，油用 `yahoo_price CL=F`（`CLUSD` 已废，返回 FRED 历史错值），美元 `DXY`。
- **美股涨跌榜**：metrics 的 movers 只覆盖美股（`query="biggest gainers"`，默认去掉 <$1 股）；**crypto 涨跌榜不走 metrics**，走 `okx.py`（见下）。
- **econ 日历**：传 `date_from=今天`、`date_to=+5d` 才有前瞻（`actual=null`＋`estimate` 有值＝未公布）；`sort_by="hot"` 把高影响的排前；不传 keywords（每个 keyword 各回一堆 JP/KR 噪音）。
- **twitter list_timeline**：只收 `list_id`／`cursor`／`limit`（≤20），没有时间窗参数——增量由 `tw-dump.py --since` 处理。
- **脚本直连**（v3.3.3）：followin 是 SSE 型 MCP，`news-fetch.py` 已封装（GET `/sse` 拿 endpoint → POST `initialize` → POST `tools/call`，结果从 SSE 流回）；`hot-scan.py` 的 L2 层用它。

## 取价

- **报告和标题里的价格/涨跌幅只能来自工具实测**：美股/港股长桥 `quote`、A 股长桥 `.SH/.SZ`、韩日等非美正股 followin metrics（`.KS/.T/.HK` 可直查）、油 yahoo `CL=F`、币 `pct.py bn`／`okx.py t`、新链 meme `dex.py t <SYM>`（先查 `contracts.json` 按地址取）。涨跌幅只用 `pct.py` 算。新闻/TG/推文里的价格只算叙事来源，报告分 📊 实测 与 📰 叙事 两区。正股优先与降级梯 → `gate.sh 通道故障`。
- **价格应急扩列**：news/TG/推特文本里出现 ±15% 以上、又不在固定 10 币表的代币 → 收集起来跑一轮实测核验；核过的进 📊 区，没核的只能进 📰 区并标 ⚠️ 单源未核。

## 链上候选

- 准入红线（地址级链上流水整体剔除，金额≠信息价值）以 `gate.sh A闸`「撤因闸的优先级」条为唯一口径（v3.5.1 已扩到单一地址/巨鲸/大户/机构的买入扫货、持仓、浮盈浮亏）。
- **项目方/基金会/国库/团队的已知钱包**处置自家或生态资产＝当事方事件，**不套红线**（Q22，11-28 用户定）：无价格腿记「缺价格腿」并 `event.sh add` 挂复查，有价格腿按 `gate.sh 归因` ①a 明确利空建题；其余地址级流水（匿名地址、巨鲸、机构托管）仍按红线判，确非项目方的备注写「非项目方:<理由>」。解锁、抛售公告等走事件日历／预告题路径，财库周报类另过 `gate.sh 时效` 内容时效。

## 推特双栈（A1）

- **取数**：`~/.trend-scout/tw-dump.py <list_id> --pages N --n N [--since <ms>]`，list ID 与 N 值以 channels.json「A1主栈／A1科技栈」为准。脚本直连 followin，配额耗尽或失败自动换 followdao-test；每条一行 `[MM/DD HH:MM] @author | 👍 🔁 💬 | 正文前130字`（北京时间、倒序），末尾原样带服务端截断警告和 `TWDUMP:` 汇总行。刷新传 `--since` 为 last-refresh 末行（毫秒）。
- **主进程粗排双轨**（脚本只 dump 不算分）：Velocity 轨 `(likes + 2×rt + 0.5×reply) / max(发帖小时数, 0.25)` 取前 7 ＋ Recency 轨按时间取前 3 ＋ **30 分钟内的新推无条件保留**，合并去重约 10 条。纯按互动排在 4h 窗里会压死新推、刷新和首扫大面积重叠。
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
| 关键词深挖 | 项目/公司/事件/人名 | `news(query=KEYWORD, time_range="1d", verbosity="concise", limit=15)` ＋ `news(query=KEYWORD, sources=["twitter"], limit=10)` ＋ `twitter(action="search", query=KEYWORD, query_type="Top")`，不传 asset_type；美股/宏观另加一路长桥 `news_search` 或金十 `search_flash` |
| 混合 | 既有标的也有主题 | 两路都跑 |

- 搜索词优先单一实体名（`Covenant AI`），少用多词 AND；突发事件并行 2–3 组不同措辞；推特搜索可加 `since:YYYY-MM-DD`、`min_faves:100`。
- 输出：📊 实测（仅符号路径）／📰 关键事件（时间倒序，带来源与核心数据）／💬 KOL 观点（多空分歧或共识）／🎯 提炼候选 1–3 条（A/B 分＋多源数）→ 进去重对照（`dedup-scoring.md` 0a）。
