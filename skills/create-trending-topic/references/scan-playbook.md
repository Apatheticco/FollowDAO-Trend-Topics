# 扫描详章（A 入口首扫/刷新 + C 入口检索）— 从 SKILL.md 拆出（v2.8.2）

> 本文件是 SKILL.md「⚡执行卡」的判定细节附录：批次表跑什么以执行卡为唯一源，这里只放装不下的判定逻辑。

## 第 -1 步：扫描热点（A 入口）

### 🕐 第 0 步铁律：时间校准（v2.1.8 — 每次扫描第一件事）

**铁律**：任何扫描（首扫 / 刷新 / 检索）开始**前**，必须先执行：

```bash
date '+%Y-%m-%d %H:%M:%S %Z (UTC%:z) | Unix: %s'
```

**理由**：窗口判定（8h/4h/24h cutoff）、升温偏差、在审池年龄全依赖准确"现在"；系统提示的日期可能滞后。发现自述日期与 `date` 不一致 → 立刻重算所有窗口、重发简报。

> ⚠️ **bash `date` 不是唯一真值源（v2.5.4）**：compact 续接后沙箱时钟会冻结在快照时刻（实测差过 2 天）。**三角校验**：`date` ⨯ ① 系统 `currentDate` ② live MCP twitter 时间戳 ③ 价格跳变幅度（5"分钟"走不出 BTC ±3%）。**冲突以 live 数据为准**（MCP/web > bash date），按真实时间重算全窗口 + 重拉 B0。典型触发：隔几天续接同一会话。详见 LESSONS.md。

### 模式自动判断（UTC+8）

| 用户指令 | 模式 |
|---------|------|
| "跑一遍今天热点 / 隔夜更新 / 早上扫一下" | 🟢 首扫 |
| "刷新一下 / 有什么新的 / 现在有什么可以做" | 🔵 刷新 |
| 模糊（"扫一下" / "创建话题"无素材） | 06:00-10:00 默认首扫；10:00 后默认刷新 |
| 例外 | 调 `list_trending_topics(today, status=0)`，今日已发布 0 条 → 强制首扫，不论时间 |

冲突时主动询问。

### ✅ 每轮必跑（照「⚡执行卡 §1 并行批次表」打勾，禁止凭记忆跳波）

> **铁律**：跑什么 + 怎么并行 = 顶部「执行卡 §1」**单一事实源**，逐批打勾。跳过任一 call 必须在简报里写明"跳过 X，原因 Y"——这是防"经验主义简化版"的硬闸。
> 最常被漏：**三栈 list_timeline**（主 2046… / 科技AI 2051854… / 大师 2051856…）。下方「判定细节附录」只补批次表装不下的判定细节。

### ⚠️ Followin 已知 quirks（v2.3.1 实测，对齐线上 schema）

1. **session 偶发掉线** — `"session not found"` / `"session initialization"` 错误。重试一次通常恢复；连续失败需重启 Claude Code
2. **🚫 `news` 端点无 `sort_by` 也无 `categories`** — 传了报 `MCP error -32602: unexpected additional properties`。`news` 只认 `query / sources / asset_type / time_range / limit / verbosity / source_lang / search_depth`。**排序/分类靠 query 措辞 + time_range，不靠参数**（旧版 skill 里所有 `news(sort_by=, categories=)` 写法已失效）
3. **🚫 `metrics` 无 `sort_by`（但有 `categories`）** — 涨跌榜/movers 用 `metrics(query="biggest gainers" / "涨幅榜" / "market movers", asset_type, categories=["market"], min_market_cap=1000000000)`。`min_market_cap=1e9` 同时滤掉 penny stock + 大部分 2x/3x leveraged ETF 噪音
4. **`news(asset_type="tradfi")` 经常返回 0（≈死调用）** — 实测几乎每轮返 0。**批次里「tradfi 头条」已砍**，统一用 `news(query="<当周关键词>", 不传 asset_type, verbosity="concise")` 兜底（这条才真出货）。query 兜底也偶发 `results=null` → 换泛化关键词（如 `"stock market earnings Fed"`）重试一次
5. **tradfi news 只返回标题** — FMP news 通道仅返回 title（~266 token / 10 条）。要正文改 `query` 走 opensearch 通道
6. **`news` 默认 verbosity=standard 带完整正文** — limit≥20 易炸 context（实战 56K 字符）。生产用 `verbosity="concise"` + `limit≤15`
7. **`news(asset_type="tradfi")` FMP 偏 WSJ/Bloomberg/Barron's** — 漏 **Reuters 独家 / X 突发 / 中文媒体爆点**。修复：刷新必跑 query 兜底 `news(query="<当周关键词>", 不传 asset_type, time_range="4h")`（实战 5/14 漏 NVIDIA H200 出口许可）
8. **TG `sources=["telegram"]` 返回 `tg_kol_feeds`** — 字段为 `tg_category / author_name / content / _source_quality / published_ts`，**无 `username`**，过滤用 `author_name`。⚠️ **v2.6.6 起 TG 仅保留 1 条 exploit 探针**（裸 feed 实测全 bot 噪音：爆仓/匿名巨鲸/喊单 shill，topic-worthy≈0）；不再跑多 cat browse。
9. **🚫 大宗裸 keyword 会乱解析成同名股票** — `gold`→Barrick 金矿股、`CL`→Colgate 牙膏；query 措辞修不了。**正解 = 现货符号**：金 `XAUT`@crypto（PAXG 同效）｜油 `CLUSD`@tradfi（name="Crude Oil"）｜美元 `DXY`（返 DXUSD）。`USO/BNO` 油 ETF 仅兜底
10. **✅ metrics 价格调用一律加 `categories=["market"]`（铁律）** — 不传会扇出 macro+fundamentals：tradfi 2 股即溢出 130K、12 股 700K，crypto 混入 macro 噪音。加了之后 tradfi 内联返回且白送 `change/dayHigh/marketCap/yearHigh`，板块矩阵/涨跌榜全内联跑（旧"存盘提取"废弃）。仅真要财报/宏观点位才用 `["fundamentals"]`/`["macro"]`
11. **🚫 `metrics` keywords 硬上限 = 10 个** — 超出**静默截断**（仅 warning，不报错不补返回），极易漏数据。>10 必拆 ≤10/批 并行（28 股 = 3×10）。`change` 是**绝对额非百分比**（% = change/previousClose）。涨榜 `biggest gainers` **不要传 min_market_cap**（gainers 端点 marketCap=null 会 source_dead）；penny/leveraged ETF 靠后过滤（name 含 2X/3X/Bull）
12. **🗓️ econ 日历必须传前瞻日期窗** — 默认 `lookback_days=7` 只向后看，**传 `date_from`=今天、`date_to`=+5d** 才返前瞻（`actual=null`+`estimate` 有值=未公布）。**仍不传 keywords**（传了每个 keyword 各回 10 条 JP/KR 噪音）；Agent 过滤 `country∈{US,CN,EU}` 且 `impact∈{High,Medium}`；关键前瞻偶缺收录，web 兜
13. **🔌 MCP 重连后「数组参数」序列化 bug** — followin 断线重连后，凡显式传数组的调用报 `["X"] has type "string"`（ToolSearch 回拉 schema 丢 array 标注；非服务端宕机、非 skill 错）。纯 query / twitter(list_id) 正常。**修复 = 重启 followin server / 重开会话**；临时绕：价格走降级梯（okx/web），TG 用纯 query news 兜底

### 价格数据铁律

简报中所有当前价格/涨跌幅，**只能引用 `followin.metrics` 返回的硬数据**。新闻标题、TG 帖子、KOL 推文里的价格描述一律视为"叙事来源"。输出分区：**📊 实时数据** vs **📰 叙事候选**。

> **🌏 非美个股价格盲区 → 多级降级取实时价（铁律 v2.6.4 + v2.6.7 降级梯 — 2026-06-18/06-22 SK 海力士复盘）**：`followin.metrics` **对韩股/日股/欧股等非美个股无覆盖**（已实测 SK 海力士 `000660.KS`/`HXSCL`/`HYNIX`/`SKHYNIX` 全返空）。这类标的建题时**禁止拿新闻里的隔日盘中数直接进标题**（T-1 快照进标题即脱锚），**也禁止用"预期价/forecast"**（韩媒搜索常回 forecast，必弃）。
> **取价降级梯（一级挂了走下一级，别一级失败就说"取不到"）**：
> 1. `WebSearch` 韩媒/英文 dated 源（口径互洽优先；只回 forecast 则视为失败，下一级）
> 2. `tradingview yahoo_price(symbol="000660.KS")`（**偶发 SSL EOF，挂了就下一级**）
> 3. **`WebFetch https://www.google.com/finance/quote/000660:KRX`**（2026-06-22 实测**通**，回实时价+前收+涨跌额，可自算 %；stockanalysis 403 / Naver 被封 / yahoo SSL 均不可靠）
> 4. 仍取不到 → **如实告知"今日实际价未取到"，给"等收盘 dated / 叙事版不押价 / 刷新老话题"三选项**，禁止硬编。
> **教训（v2.6.7）**：06-22 我只试了 WebSearch 就下结论"取不到实时价"被用户顶回——`followin 无覆盖 ≠ 全网取不到`，降级梯必须走到底（Google Finance WebFetch 那级才通）。性质同 quirk⑨、5/14 漏 H200：盲区标的当场换源补全，不将就二手数、不提前认输。

### 🔁 价格应急扩列规则（首扫 / 刷新通用）

固定 10 币列表常漏日内主线（实战漏 ZEC +30%）。规则：扫描 news/TG/twitter 文本中 **±15% 以上且不在固定列表**的代币 → 收集 symbol 跑**第二轮 metrics 核验**；核验过的进 📊 实时数据区，没核的只能进 📰 叙事候选标 ⚠️ 单源未核。**铁律：未经第二轮核验的 ±15% 代币禁止写入实时数据区**。

### 🟢 首扫模式 — 判定细节附录

> **批次跑什么/怎么并发 = §1 唯一源。** 下方只补 §1 装不下的判定细节（TG 范式 / 板块异动判定 / 价格符号+fallback / Wave5 query）。不再重列批次表。
> 不跑 `signal`（kol_call/insider/institutional/trader_position 全砍：噪音高、与 TG/news 重复、13F 季度滞后）。

##### 📡 TG 频道扫描范式（v2.6.6 — 2026-06-20 实测降级为单条 exploit 探针）

> 🔻 **裸 feed TG 已砍（v2.6.6）**：2026-06-20 工作日+周末两批实测，空 query / category browse 的 TG 返回**几乎全是 bot 噪音**——爆仓 bot（微额 $50K）、匿名巨鲸流水（撞链上红线）、喊单/meme shill bot，topic-worthy≈0；少数实质内容（FOMC/STRC/监管）media 与三栈 list 已覆盖。**TG 唯一残余独有价值 = 安全/exploit 早警**（Axelar $4.7M、Aztec $2M 偶尔比 media 快几分钟）。故 5-cat 并行 browse 全删，只留**一条 exploit 探针**；叙事/上币/监管/鲸鱼全交给三栈 list + W2 media query（本就覆盖）。

| 模式 | TG 调用 | 说明 |
|------|---------|------|
| 🟢 首扫 / 🔵 刷新 | **1 条 exploit 探针**（见下） | 不再跑 5-cat / 2-cat browse |
| 🔴 突发安全事件 | 按标的加 `query` 定向补 | 仅当已知有 hack 在传 |

**调用范式（唯一 1 路）**：
```python
followin.news(
    query="hack exploit drained bridge vulnerability stolen funds",
    sources=["telegram"],
    time_range="1d",          # 刷新用 "4h"
    limit=15,
    verbosity="standard"
)
# 命中 exploit/被盗事件 → 进 0b（金额+协议+是否仍在进行）；其余照旧噪音忽略
```

**子进程 jq 后处理（2 步精简）**：
> ⚠️ TG 返回字段为 `tg_category / author_name / content / _source_quality / published_ts`，**无 `username`**。过滤/去重一律用 `author_name`。结果路径可能是 `.results` 或 `.results.articles`，先 `.results.articles // .results` 兜底。
```bash
ROWS='(.results.articles // .results)'
# Step 1 白名单（按 author_name 保留数据 bot，砍个号 spam）
jq "[$ROWS[] | select(.author_name | test(\"PolyBeats|OnchainData|Whale_Alert|CoinbobAI\"; \"i\"))]" \
   "$FILE" > /tmp/tg-step1.json
# Step 2 同 author_name 去重（每源最新 ≤3 条）
jq '[group_by(.author_name)[] | sort_by(-.published_ts) | .[0:3]] | flatten' \
   /tmp/tg-step1.json > /tmp/tg-clean.json
# 输出：[quality] @author | time | content[0:160]
jq -r '.[] | "[\(._source_quality // "low")] @\(.author_name) | \((.published_ts/1000)|strftime("%m/%d %H:%M")) | \(.content|gsub("\n";" ")|.[0:160])"' \
   /tmp/tg-clean.json | head -25
```

**风向标用法**：TG 扫到的**具体链上事件**进 0b 双轴评分；**模糊讨论**不进。这一通道补足了 trader_position 数据死角（Followin 之前 v2.0 移除的 whale_trader_feeds 等价值）。

> 🚫 **链上候选准入红线（v2.5.7 — 2026-06-11 用户反馈：金额大 ≠ 有信息价值，这两类整体剔除）**：
> - **❌ 机构例行托管流水**（BlackRock/灰度等向 Coinbase Prime / 交易所充值，无论金额多大）—— 这是每天都有的常态托管动作，**非主动交易信号、无市场传导**，金额过亿也不进候选。
> - **❌ 匿名地址多空仓位/对赌**（"某地址 20x 多单浮盈/某 pension-usdt.eth 加空单到 $9742 万"）—— **无可识别身份、无市场影响、纯链上赌博八卦**，金额大也不进候选。
> - ✅ **保留进候选的链上事件 = 可识别身份 + 明确叙事/传导意义**：知名实体战略性财库增减持（Bitmine 增持 ETH、MSTR 加仓）、官方/项目方主动操作（解锁、抛售、官方地址异动）、有身份的标志性玩家动作（孙哥提币质押）。
> - **判定口诀**：问"这条转账/仓位**改变了谁对市场的预期**？"——答不上来（只是流水/赌博）就剔除，答得上来（战略信号/叙事）才进。金额从来不是准入理由。

**避坑**（v2.6.6 后只剩 1 条 exploit 探针，无需分批）：
- 探针命中 exploit/被盗 → 先过上方链上红线 + `tg_category/author_name` 字段（无 username）；金额+协议+是否进行中进 0b
- 上方 jq 白名单后处理对单条探针非必需，但保留以备突发安全事件加 `query` 定向扩量时复用

##### 📊 美股板块涨跌矩阵 — 8 板块代表股（§1 W3 的 3×10 = 本表高权重子集 +MRVL/TSLA/AMZN；GEMI/IBKR/LMT/RTX/BA 仅按需补拉）

风向标常漏**子板块异动**（如 5/18 存储+光通信集体崩盘只看大盘看不出）。8 大板块代表股：

| 板块 | 代表股票（3-4 个，按权重）|
|------|--------------------------|
| **AI 算力 / GPU** | `NVDA,AMD,AVGO,TSM` |
| **AI 应用 / 大科技** | `MSFT,GOOGL,META,AAPL` |
| **存储 / 内存** | `MU,SNDK,WDC,STX` |
| **光通信 / 网络** | `LITE,AAOI,GLW,COHR` |
| **半导体设备** | `ASML,AMAT,LRCX,KLAC` |
| **加密概念股** | `CRCL,COIN,MSTR,GEMI` |
| **量化交易 / Fintech** | `HOOD,SOFI,PLTR,IBKR` |
| **航天 / 国防** | `RKLB,LMT,RTX,BA` |

**判定**：某板块 ≥2 标的同向 >3% 涨/跌 → 板块异动信号 → 进 0b 作板块候选（如 R-Mem 存储+光通信回调）。拆 3×10 跑（quirk⑪），加 `categories=["market"]`（quirk⑩）；批3 补 TSLA/AMZN 即覆盖科技大票，不单跑 Wave2C。

##### 🏛️ 宏观/大宗 — 符号校正 + fallback 链

主调（quirk⑨ 已校正，均 `categories=["market"]`）：**金=`XAUT`@crypto｜油=`CLUSD`@tradfi｜美元=`DXY`｜标普=`spx`@tradfi**。国债=`DGS10/DGS2`@macro。econ 日历=传前瞻日期窗（quirk⑫）。⚠️ 绝不用裸 `gold`/`oil`（quirk⑨ 解析成金矿股/Colgate）。

| 主调失败 | Fallback |
|---------|----------|
| `XAUT`(金) | `PAXG`@crypto |
| `spx` | `SPY/QQQ`@tradfi |
| `DXY` | `DTWEXBGS`@macro |
| `CLUSD`(油) | `USO/BNO`(ETF，追踪非现货) |
> Primary 失败必跑 fallback，仍失败标"⚠️数据缺失"。**followin.metrics 整体挂 → 价格源降级梯（§1 末 okx/web）**。

##### 🔍 Wave5 二线 query（首扫 3 路 / 刷新只留鲸鱼，与 §1 W2 对齐）

鲸鱼 `news(query="鲸鱼 巨鲸 whale transfer 大额转账", 1d, limit=15)`（刷新版 query 加 `链上`、limit=10）｜上币 `news(query="binance coinbase listing delisting 上币 下架", 1d, limit=10)`｜解锁/财库 `news(query="unlock 解锁 vesting 财库 treasury", 1d, limit=10)`。**ETF 流向 query 路砍**（`spot` 总被解析成 Spotify/degraded）；ETF netflow 改由 media query `news(query="bitcoin ethereum ETF flows inflow outflow")` 覆盖（v2.6.6 起 TG 链上 bot 随裸 feed 一并砍，实测 media 已稳定覆盖 ETF 流向）。

**popularity/无 query 浏览**（`news(asset_type="crypto", time_range="1d", limit=20)` 不传 query 返 trending）：已从必跑砍掉，仅候选不足扩窗时作补充路。

执行完 → 第 0a 步。

### 🚨 强制铁律：Twitter 三栈 list 不可跳过（v2.2.4 实战教训；TG 已降级 v2.6.6）

实战教训（5/19）：漏掉 Twitter list 直接缺 5+ 强候选——megaevent 常只在 list 出现，新闻通道捞不到，故 §1 把**三栈 list 列为必跑**（详见 LESSONS.md）。**TG 已于 v2.6.6 降级**：2026-06-20 实测裸 feed TG 全 bot 噪音（出真候选的是 list，不是 TG），仅保留 1 条 exploit 探针，**不再算"不可跳过"**——三栈 list 才是必跑核心。

**失败处置**：任一批次失败 → **重试 1 次**；主进程仍失败（尤其 followin `session initialization`）→ **走 news 降级梯：Agent 子进程代跑**（子进程独立 session 绕过主 server 抖动，v2.8.4）；子进程也失败才标"⚠️ 通道缺失"。**任一必跑通道(news/TG/三栈)缺且补不齐 → 触发半盲熔断（SKILL §0 v2.8.4）：报告标「半盲扫·结论存疑」，禁报干净干轮**。不能直接进 0b。

**覆盖自检铁律（v2.8.2 — 取代旧"候选数量铁律"）**：跑完执行卡 §1 全部批次后，进 0b 前只做**覆盖自检**：候选稀少 + 当日明显有大事 → 对照 §1 批次表逐波查是否漏跑（最常漏：三栈 list）；通道无漏 → 如实报干轮。**不设数字目标、不为凑数扩窗**（扩窗仅当确认某通道漏跑/失败需补时使用）。

### 🔵 刷新模式（日内每 2-4h，4h 窗口）

**目的**：追首扫之后的增量（含跨市场）。

> **刷新模式 — 判定细节附录。** 批次见 §1🔵。下方只补判定：TG exploit 探针、query 兜底模板、增量过滤。
> TG 刷新同首扫 = 单条 exploit 探针（`query="hack exploit drained bridge vulnerability"`, telegram, 4h）；裸 feed/多 cat browse 已于 v2.6.6 砍。见「TG 频道扫描范式」。

**美股 query 兜底关键词模板**（`news(query=..., 不传 asset_type, time_range="4h")` 抓 Reuters/X/中文爆点，每天按热点轮换）：

| 当周热点 | query |
|---------|-------|
| 中美 AI 博弈 / 芯片出口（如 H200）| `"NVIDIA AMD chip China Trump tariff Huawei"` |
| Fed 主席换届 / 通胀 | `"Powell Warsh Fed Chair CPI PPI inflation"` |
| 地缘冲突 / 油价 | `"Iran Hormuz oil OPEC Brent ceasefire"` |
| 财报周 | `"earnings beat miss EPS guidance Q1 Q2"` |
| 政策立法 | `"CLARITY GENIUS SEC stablecoin Tillis Alsobrooks"` |

> 🐛 实战教训（5/14 漏 H200 出口许可）：FMP 通道偏严肃财媒，漏 Reuters/X/中文爆点——query 兜底通道必跑。

**刷新判定要点**：
- Wave5 只留鲸鱼一路（上币 4h 返陈旧 / ETF `spot`→Spotify，砍）；不跑 trader_position + 解锁/财库（4h 增量稀疏）。
- 跨市场快照仍刷（油 `CLUSD`/美元 `DXY`/金 `XAUT`，见首扫符号校正）——油破 $100 / DXY 破 98 / 黄金回探是当日风险开关，"日内不大"的假设会漏宏观主线。
- **不跑 signal（4 cat 全砍）/ popularity（全砍，仅扩窗补充）/ econ日历 / 国债 / spx**；用户明确"看鲸鱼/看议员"才破例单跑 signal。财报周可加跑涨/跌榜。
- 候选数**不设门槛**（v2.8.2）：跑完批次即进 0b，稀少时按「覆盖自检铁律」查漏，不为凑数扩窗。
- **增量过滤铁律**：每轮结束 `echo "$(date +%s)000" >> $HOME/.trend-scout/last-refresh.txt`（**单一文件、不带日期**，v2.6.5），下次按 `createdAt > last_refresh_ts` 过滤，避免读到上轮已读内容。

### 推特 L1 排序规则（刷新模式核心）

纯 `engagement DESC` 在 4h 窗口会压制新推（3-4h 老推累积互动 vs 30min 新推零互动），刷新和首扫严重 overlap，失去追增量意义。

**双轨制**：
- 🅰️ **Velocity 轨**：`(likes + 2×rt + 0.5×reply) / max(hours_since_post, 0.25)` 降序，取 top 7
- 🅱️ **Recency 轨**：`createdAt` 降序，取 top 3
- **绝对保护**：`createdAt` 在过去 **30 分钟内**的推文，无论 velocity 多低都必须进候选池
- 合并去重，最终 10 条

⚠️ **list_timeline schema 限制**：`followin.twitter` 只接受 `list_id` + `cursor`，**不接受时间窗参数**（与旧 MCP 一致）。Agent 子进程必须自己按 `createdAt > last_refresh_ts` 过滤。

#### Agent 子进程 Prompt 模板（必用 — dump-only，velocity 主进程算）

> 与 §1「子进程范式」一致：**子进程只 dump、不算 velocity**（算分吃 ~15K token/30s+）。上面的双轨制是**主进程**拿到 dump 后的粗排规则。

```
调用 followin.twitter(action="list_timeline", list_id="<LIST_ID>")。
时间过滤：createdAt > <LAST_REFRESH_TS>（unix 秒）— 早于此时间的全部丢弃（首扫不传则不滤）。
按 createdAt 倒序输出最新 <N> 条，每条只回传一行：
[MM/DD HH:MM] @author | 👍likes 🔁rt 💬reply | text前130字
不要计算任何分数。不要返回 full_content / 媒体链接 / 完整 raw json。
```

N：首扫 主15/科技12/大师8；刷新 主10/科技8。三栈 list 各跑一次。主进程拿到 dump 后按双轨制（velocity top 7 + recency top 3 + 30min 绝对保护）粗排出最终候选。

### 输出格式（v2.2 — 撤改补三件套统一）

**首扫 + 刷新通用主报告**（见第 0b 步 "输出格式" 详细模板）：

```
═══ 风向标 [首扫/刷新] 日报 — [时间戳 UTC+8] ═══

🆕 必须补充（过闸候选如实报、0=干轮，按 A+B+C+D 总分降序）
  P0 (≥8): ...
  P1 (6-7): ...
  P2 (4-5): ...

🔧 必须更新
  ID  当前标题 → 新标题   原因：升温/事件升级/数据脱锚

🚨 必须撤回
  ID  原因：反向脱锚/重复/弱主体/类型阈值/时效过期

─────────────────
🟰 重叠已建（精简，反证差异化）
📊 实时数据（fold 收起）
```

**简报不合规检测**：
- 🆕 大事日却 0 候选 → 先对照 §1 批次表自查通道漏跑；无漏则如实报干轮（禁止为凑数扩窗）
- 漏掉 🔧 或 🚨 → 必须补完整三件套
- 候选无"vs 已建 ID 差异锚点" → 不合格

### 🚨 候选池兜底（3 级）

经第 0a 去重后 **🆕 强候选 < 2 条** 时触发：

| 等级 | 操作 |
|------|------|
| 1 | 扩窗：Twitter list 24h→48，重跑 velocity+recency 双轨制取 top 15 |
| 2 | 调 `followin.twitter(action="search", query="crypto OR BTC OR ETH lang:zh OR lang:en", query_type="Top")` 兜底 |
| 3 | 等级 2 仍 <2 条 → 直接告知用户「今日候选池已饱和」，不强行凑数 |

---

## 第 -1.5 步：定向检索深挖（C 入口）

### 触发

- 单一**代币符号**："查一下 REPPO" / `$ASTEROID`
- **一句模糊描述**："以太坊基金会今天有什么动作"
- **不完整素材**："听说有大鲸鱼在做空 BTC"

### 输入分流 + 工具组

| 路径 | 触发 | 并行调用工具 |
|------|------|------------|
| **代币深挖** | 单一符号 / `$XXX` | `followin.metrics(keywords=[SYMBOL], asset_type="crypto", query="近 7d 走势 + 技术读")` + `followin.news(query="$SYMBOL", time_range="1d", limit=20)` + `followin.news(query="$SYMBOL", sources=["twitter"], time_range="1d", limit=15)` + `followin.signal(keywords=[SYMBOL], categories=["kol_call","trader_position"], time_range="1d")` |
| **关键词深挖** | 项目/公司/事件/人名 | `followin.news(query=KEYWORD, time_range="1d", verbosity="concise", limit=15)` + `followin.news(query=KEYWORD, sources=["twitter"], limit=10)` + `followin.twitter(action="search", query=KEYWORD, query_type="Top")` — **不传 asset_type**（query 自然分流） |
| **混合** | 既有标的也有主题 | 两路都跑 |

### 关键词搜索策略

- 优先**单一实体名**（"Covenant AI"），少用多词 AND（"Bittensor TAO Covenant" 容易零结果）
- 模糊主题用**自然语义短语**
- 突发事件并行 2-3 个不同关键词组合提高命中率
- Twitter 可加 `since:YYYY-MM-DD`、`min_faves:100` 缩窄

### 输出格式

```
🔍 检索结果（关键词 / 标的：xxx）

📊 实时数据（仅 symbol 路径）

📰 关键事件（按时间倒序）
1. [时间] 标题 — 来源 — 核心数据

💬 KOL/Twitter 观点
- 多空分歧 / 共识 / 边缘观点

🎯 提炼的话题候选（1-3 条）
1. [候选标题] — A=x B=y — 核心素材 — 多源：N 源
```

→ 提炼候选进入第 0a 去重对照。

---

## 📈 movers 异动通道（v2.8.6 详章 — 2026-07-04~07 实测）

### 标准调用（okx 为主源）

```
market_filter(instType="SWAP", sortBy="chg24hPct", sortOrder="desc", minVolUsd24h="15000000", limit=10)   # 涨榜
market_filter(instType="SWAP", sortBy="chg24hPct", sortOrder="asc",  minVolUsd24h="15000000", limit=8)    # 跌榜
market_filter_oi_change(instType="SWAP", bar="4H", sortBy="oiDeltaPct", minVolUsd24h="15000000", limit=10) # OI 异动
```

### 参数三坑（误诊事故档案）

| 坑 | 症状 | 真相 |
|----|------|------|
| sortBy 传 `priceChangePercent` | HTTP 400 "Bind Arguments Validation Failure" | 枚举是 `chg24hPct`（另有 last/volUsd24h/fundingRate/oiUsd/listTime）。07-04 我据此误诊"OKX movers 挂了、得挂几天"，改用单一 tradingview 险误报干轮——**先 ToolSearch 读 schema 再下"通道死"结论** |
| oi_change 不传 `instType` | ValidationError: Missing required parameter | `instType` 必填（SWAP/FUTURES） |
| capabilities 显示 swap/spot/account `MODULE_FILTERED` | 看着像"模块被封" | 那是**交易模块**被关（只读部署设计），`market` 模块恒 `enabled`，只读扫描不受影响 |

### 源优先级

| 优先 | 源 | 说明 |
|------|----|------|
| 1 | okx `market_filter` / `oi_change` | 主源，SWAP 宇宙全、24h 口径准 |
| 2 | tradingview `top_gainers/top_losers` | okx 挂时兜底；**单源不可信**——07-06 实测币安现货口径 +1.65% 封顶失真，同时刻 okx SWAP HMSTR +83%。单源静默 ≠ 干轮 |
| ❌ | followin.metrics movers | **advertised-but-empty**：help 宣传 query='biggest gainers'/'涨幅榜'/'最活跃'/'市场异动'，实测四种写法全 total=0 且错路由进 metrics_macro(FRED)。followin 只查**已知标的**价格（keywords 直查，这个好用），不承担全市场涨跌榜 |

### 干轮自检

movers 侧报"无异动"前必确认：本轮 okx 两榜是否真跑通（ok:true + rows 非空结构）？只有 tradingview 一源在跑 → 不下"行情异动干轮"结论，标注"movers 单源存疑"。

---
