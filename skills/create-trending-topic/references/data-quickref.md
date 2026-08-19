# 数据速查（tag id / list ID / 币表 / 板块矩阵 / 工具用法）— 从 SKILL.md 拆出（v2.8.2）

> ⚠️ 本文件是**数据**不是规则——数据会过时，更新这里不需要动规则文件。新 tag 实测到就补进来。

## 双栈 Twitter list ID

| 栈 | list_id | 用法 |
|----|---------|------|
| 主 | 2046422494643687464 | 首扫+刷新必跑 |
| 科技AI | 2051854001608724654 | 首扫+刷新必跑 |

## 10 币价格固定列表

`BTC, ETH, SOL, BNB, XRP, DOGE, HYPE, SUI, AVAX, LINK`

> 📦 **`verbosity="concise"` 不砍 history（2026-08-06 实测，勿再试）**：参数被接受（meta 回显 concise）但每币仍返 ~10 根小时 K 线，回包体积无收益。10 币批照默认参数跑。
> 🧱 **metrics keywords ≤5/批硬上限（v2.9.4 — 2026-07-11 实测 API 变更）**：`followin.metrics` 单次 `keywords` 超过 5 个会**静默截断到前 5**、返回 `warning: keywords truncated: N→5`，多的直接丢（07-10 同调用还 10 个全返回、零 warning，隔夜收紧）。**10 币拆 2 批（5+5）、下方板块矩阵每批 ≤5**，别一次塞 10——那是看不见的漏扫。

##### 📊 美股板块涨跌矩阵 — 8 板块代表股（§1 W3/W4 的 **6 批×5**（v2.9.8）= 本表高权重子集 +MRVL/TSLA/AMZN；GEMI/IBKR/LMT/RTX/BA/**SOFI** 仅按需补拉）

> ⚠️ **30 槽是硬约束：加一个必须换一个（v2.9.43b）**。6 批 × 5 keywords（v2.9.4 硬上限）= 30 槽已满，**只改本表不改 §1 批次组成 = 新标的根本不会被拉到**（这次 SPCX 入表同步把批6 的 SOFI 换出，否则等于白改）。换人判据：市值×活跃度×被点名频率，三项都明显更弱的降"按需"。
> 📌 **实测坑（08-13）**：批4 `[AAOI,GLW,COHR,ASML,AMAT]` 走 query 降级形态时，`ASML` 被 fanout 扩成 `ASML`+`ASML.AS` 两个 keyword，**`AMAT` 作第 6 个被截断丢弃**——批内含"有海外双重上市版"的标的（ASML/ASML.AS 型）时实际只装得下 4 个，AMAT 这类关键标的宁可单独一个 call（同 v2.9.39 日元判据）。

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
| **航天 / 国防** | `SPCX,RKLB,LMT,RTX`（BA 降为按需）|

> 🚀 **SPCX 入表（v2.9.43b — 08-13 用户定「1」，成本最低的补法）**：航天行原名单 `RKLB,LMT,RTX,BA` **没有 SPCX**，而它市值约 1.87 万亿美元、成交活跃、被 A 级账号连日点名——今早我误撤 `2592`（SPCX+9.7%）时在留档写"命中板块矩阵第 8 行"**其实不准确**，它当时只靠 ③主线头部/④A级点名 两条需现场判断的条款兜着，而现场判断恰是失手处。入表后它由 ②固定名单 直接覆盖，v2.9.37 入册与 v2.9.42 撤前搜 news 两处判据同时生效。**BA 降为按需补拉**（近月无异动、不占 5 槽上限）。
> - ~~动态兜底（"近 5 日成交/涨跌榜前列美股自动算覆盖"）~~ **本轮不做**：需额外拉榜单、为单一案例造需现场取数的规则不划算；**若再出现第二次"新晋主线漏判"再上**。

**第 9 行·亚洲存储（v2.9.38 转正——韩股双雄已连续四轮实拉，KOSPI 熔断/收盘复查/双雄验证均实战）**：`000660.KS`（SK 海力士）+ `005930.KS`（三星）@tradfi，**KST 15:30 收盘后查**（盘中数字受 v2.9.32② 中间态闸约束，不作标题结论）；ADR=`SKHY`。

**判定**：某板块 ≥2 标的同向 >3% 涨/跌 → 板块异动信号 → 进 0b 作板块候选（如 R-Mem 存储+光通信回调）。**拆 ≤5/批 跑（v2.9.4 — keywords 硬上限 5，旧"3×10"作废，改 6 批×5 或按板块 4 个一批）**，加 `categories=["market"]`（quirk⑩）；批内补 TSLA/AMZN 即覆盖科技大票，不单跑 Wave2C。

##### 🏛️ 宏观/大宗 — 符号校正 + fallback 链

主调（quirk⑨ 已校正，均 `categories=["market"]`）：**金=`XAUT`@crypto｜美元=`DXY`｜标普=`spx`@tradfi｜日元=`USDJPY`**。
> - ⚠️ **日元改走 `yahoo_price JPY=X` 单独一个 call（v2.9.39 修正 — 08-12 实测，v2.9.38「并入美元批」当轮即失效）**：数组参被剥空后走 query 降级形态时，**keyword 数由服务端 fanout 决定**，`"美元指数 dollar index DXY 标普500 spx USDJPY 日元"` 被扩成 6 个 keyword，`USDJPY=X` 作为第 6 个**被截断丢弃**（`warning: keyword omitted after applying the maximum of 5`）。同型：腾讯+韩股批被扩成 6 词丢 `HXSCY`（该例无影响，三个目标标的都到了）。**判据：本轮非它不可的单一标的，宁可单独一个 call，别塞进多标的 query——query 形态下我控不了 keyword 数。** 实测 `JPY=X` 返回正常（159.426／159.358，52w 高 163.979）。
> - 日元线的由来：三天 10 次全靠 news 碰运气，08-12 晨"日债 5 年收益率创历史新高+BOJ 加息概率 2/3"完全漏 note 后才补进批次。国债=`DGS10/DGS2`@macro。econ 日历=传前瞻日期窗（quirk⑫）。⚠️ 绝不用裸 `gold`/`oil`（quirk⑨ 解析成金矿股/Colgate）。宏观 news query 轮换词加 **`BOJ 日债 日元`**（与 CPI/Fed 系轮着用）。

> 📅 **earnings 日历必须传 ticker，绝不拉市场级日历（quirk⑭ — 2026-08-17 实测，当轮我先误判为"通道失效"）**：
> - **市场级日历实际不可用**：`metrics(query="earnings calendar...", asset_type=tradfi, date_from/to)` 返回的是**全球**日历，按 symbol **字母序**排，**单页硬上限 50**（传 `limit=100` 返 `warning: limit_over_max`）。A 股纯数字代码（`000825.SZ`）、港台带数字前缀天然排在所有字母 ticker 之前；**美股 ticker 是纯字母（HD/WMT/ADI），要翻很多页才轮到**。实测 limit=50 时 50 条走完 `.SZ→.KL→.HK→.F→.KQ→.L→.TWO→.TW` 仍 `has_more:true`，光单日就几百条。
> - **✅ 正解 = query 里直接放 ticker**：`metrics(query="HD WMT TGT ADI NVDA next earnings date", asset_type=tradfi)` → ticker 被正确解析成 `keywords:[HD,WMT,TGT,ADI,NVDA]`，返回 **`next_earnings_estimate`（精确日期＋EPS/营收预期）＋上季 `earnings_surprise`＋`consensus_price` 目标价共识**，信息量远超日历。实测：HD 8/18（EPS 4.73）、TGT 8/19（2.26）、ADI 8/19（3.34）、WMT 8/20（0.741）、NVDA 8/26（2.08／营收 919.3 亿，上季 816 亿＝环比+12.6%，目标价共识 319.48 vs 现价 225.16＝**距共识+41.9%**）。
> - **⚠️ 我当轮的错误判断留档**：先写成「query 形态下 fanout 把语义导向中国市场」——**两处直接证伪**：返回体 `filters_applied.keywords: null`（**根本没 fanout**，机制是我编的）、`pagination.returned:10 / has_more:true`（是分页不是"只有 A 股"）。**判据升级：判定任何外部通道失效前，先把 meta 的 `filters_applied` 与 `pagination` 逐字读完**——真因每次都写在那两个字段里。本会话同型第四次（OI 通道判"疑似失效"实为 bar 档位、actions 判"无记录"实为自己改了时间戳格式、本条判"fanout 导向"实为分页＋字母序）。

> 🛢️ **油价主调换成 `tradingview yahoo_price`（quirk⑬ — 2026-08-06 三轮踩坑后实测定案）**：~~`CLUSD`@tradfi~~ **已废弃，它不是"拿不到"而是"给错值"**——该 keyword 被路由到 macro，返回 FRED `DCOILWTICO` 的**历史序列**（实测取到 84.25），而同时点真实 WTI 是 **75.92**，**差 11%**。这种错值比返空更危险（返空会被自查表标 ❌，错值会被直接写进标题）。
> - **油主调**：`tradingview yahoo_price(symbol="CL=F")` = WTI ｜ `BZ=F` = Brent（实测 75.92 / 80.16）
> - **油 fallback**：`followin.metrics(query="USO BNO oil ETF price snapshot", asset_type="tradfi")` → USO/BNO/OIL 三个 ETF/ETN 全返（实测 114.93 / 45.41 / 28.42，追踪期货非现货，标题须写"油价 ETF"或换算说明）
> - **金也可用 yahoo**：`GC=F`(期货，实测 4334.7) ｜ `GLD`(ETF，389.64)——与 XAUT/PAXG 互为交叉源

| 主调 | Fallback |
|---------|----------|
| `XAUT`(金)@crypto | `PAXG`@crypto → `yahoo_price GC=F/GLD` |
| **`yahoo_price CL=F`(油)** | `BZ=F` → followin `USO/BNO/OIL` ETF |
| `spx` | `SPY/QQQ`@tradfi |
| `DXY` | `DTWEXBGS`@macro |
> Primary 失败必跑 fallback，仍失败标"⚠️数据缺失"。**followin.metrics 整体挂 → 价格源降级梯（§1 末 okx/web）**。
>
> ⚠️ **`yahoo_price` 会偶发返「空对象」——空 ≠ 失效，必须重试一次（quirk⑬b，2026-08-06 自我纠错）**：08-05 我测 `GC=F`/`SI=F` 得到 `{"symbol":"GC=F","error":"","source":"Yahoo Finance"}`（无 error 也无 price），据此下了「yahoo_price 对大宗整环失效」的结论并写进报告；08-06 同符号重试**立刻返回 4334.7**。**判据：单次空返回=偶发，重试 1 次;连续 2 次以上空才计入故障**（对比：大师 twitter 栈是两轮、两种 action、四次全空 → 那才是真失效）。**过度概括一次偶发，代价是我漏掉了当日金价 +5.84% 这个更硬的数据锚。**

> 🌙 **盘前/盘后价 = `tradingview stock_extended_hours(symbol)`（2026-08-12 实测定案，此前一直以为拿不到）**：一次返回**三段**——`pre_market{price, change_vs_previous_close_pct}`、`regular{price, change_pct}`、`post_market{price, change_vs_regular_close_pct}` + `previous_close`。**followin `metrics` 只给 regular**（返回体 `_quote_session: "regular_inactive"` 即标志：这是已收盘的 regular 价，不含盘后信息）。
> - **判据：事件发布时点决定该用哪段价**。财报/重大公告多在**盘后**发布 → 当日 regular 收盘价**成文于事件之前**，拿它当"事件的价格反应"是错的。
> - 实测案例：LITE 财报 08-11 盘后发布，pre 812.00(−0.19%) → regular 820.59(+0.87%) → **post 840.59(+2.44%)**；我先用 regular 的 +0.87% 写进标题（"股价仅涨0.9%"），被用户指出盘后是 +2.45%。RIOT 同日反向案例：pre **+21.75%** → regular +4.33% → post +0.54%（冲高回落且盘后未修复，此时 regular 才是对的锚）。
> - **两个坑同源**：不是"该用盘后价"或"该用收盘价"，而是**必须先问事件什么时候发的**。

> ⏰ **`stock_extended_hours` 在美股完全休市时段字段会错位——`pre_market` 其实是上一交易日的盘后价（quirk⑬d，2026-08-12 实测）**：ET 00:00–04:00（= CST 12:00–16:00，即我方亚洲下午的常规扫描时段）调用时，`post_market` 返回 `null`，而 `pre_market` 装的是**上一交易日盘后最后一笔**。
> - **判据：看 `as_of_utc`——落在上一交易日且 ≈23:59 UTC（=19:59 ET，盘后窗口末端）时，这个 `pre_market` 读作盘后价，不是盘前价。** 真盘前价要等 ET 04:00 后再拉。
> - 实测三例（均 as_of `2026-08-11 23:59 UTC`）：NBIS `pre` 208.50 vs `regular` 193.23 = **+7.90%**，恰好复算出系统 `2568` 标题的「NBIS 盘后涨 8%」→ 反过来证明这个字段确实是盘后；CRCL `pre` 71.15 ≈ `regular` 71.16（盘后无成交）；MSTR `pre` 96.51 vs `regular` 96.09。
> - **误读代价**：若当成盘前价，会把上一日盘后的反应写成"今日盘前"，时点整错一天——与 ⑬c（亚洲时段过期收盘复读）同族，都是**返回值有效但语义与字段名不符**，比返空危险。

> ⚠️ **`yahoo_price` 亚洲时段会返「过期收盘复读」——识别标志：`change` 恰为 0.0 且 `price == previous_close`（quirk⑬c，2026-08-10 实测）**：当日 14:18 CST 取 `CL=F` 得 `price=78.18, change=0.0, previous_close=78.18`，而同时段 CNBC/Benzinga 实报 WTI **78.89 (+0.91%)**——返回值是上一交易日收盘的复读，不是现价。同日 09:45 取到的 78.96 则是周日夜盘真价（change≠0）。**判据：命中该标志时此值只能当"上日收盘"用，写现价必须以 news 侧报价交叉验证**；与 ⑬b 的空返回是两种坑——空返回重试可解，复读值重试无用（还是它）。


## 速查

### update_trending_topic 用法

| 需求 | 传参 |
|------|------|
| 改标题 | `title`（当前）+ `new_title` |
| 改关键词（自动重新匹配 tag） | `title` + `keywords` |
| 手动指定 tag | `title` + `tags`（如 `[{"id":10006}]`） |
| 同时手动绑 tag + 改 keywords | 传两者，**以 `tags` 为准**（不会被 keywords 自动覆盖）—— 美股/大宗等修正标准操作 |
| 改状态 | `title` + `status`（0=发布, 1=初始化, 2=审核中, 3=隐藏） |

> ⚠️ `update_trending_topic` **不能改 desc**（v2.1.1 起创建话题不写 desc，此限制不再实际影响流程）。
> ✏️ **改标题用 `new_title`（v2.9.31 — 08-10 实测）**：`title`=**定位键**（必填，按它查话题）、`new_title`=新标题。仅传 `id`+`new_title` 报「至少需要传入一个要修改的字段(new_title/status/keywords/tags)」→ 证明 `title` 不计入修改字段、**`id` 参数完全不参与定位**。连带两个结论：① 数字/排序 factfix 直接 `new_title` 原地修，**不必撤+重建**（BICO 跌幅、meme 榜排序两次实战）；② **同域同名死锁无解**——两条标题逐字相同且同 domain 时，传 `id`+`domain`+`new_title` 仍报歧义（歧义在定位阶段即阻断），只能 mark 给 dev（案例 `2520`/`2512`）。
> 🌐 **update 按 `original_title` 匹配，而 list 默认返回中文翻译版 `title`（v2.9.16 — 07-28 实测，8 条批量归集时栽坑）**：`list_trending_topics` 默认 `lang=zh-cn`，系统建的英文题会被翻译，返回体里 **`title`=译名、`original_title`=原文**；`update_trending_topic` 只认原文。**判据：list 里 `title != original_title` 时，update 必须传 `original_title`**。实测四条译名≠原文的题（`比特矿浸入技术 11%` / `上涨5.2%` / `超微半导体公司跌3.7%` / `康宁公司跌4.9%`）用 `title` 定位**全部报「未找到」**，改传 `Bitmine Immersion Technologies涨11%` / `Strategy (formerly MicroStrategy)涨5.2%` / `Advanced Micro Devices跌3.7%` / `Corning Incorporated跌4.9%` **全部成功**。译名与原文相同的题（纯英文公司名+中文涨跌词）不受影响，所以这个坑**只在中文译名题上暴露**。

> ⚠️ **标题含特殊字符会失配（v2.9.8 — 07-17 实测 10636；v2.9.28 补 `&`）**：update 按标题模糊匹配 → **用不含特殊字符的短唯一子串定位**；子串命中多条会返回 candidates 列表，据此加长子串重试。**已实测会失配的字符**：
> - **中文弯引号 `“”`**（传直引号 `"` 匹配不到）——案例 `10636`
> - **`&`（会被 HTML 转义成 `&amp;`）**——2026-08-06 实测 `10000002465`「Kratos Defense & Security Solutions, Inc.涨10%」原样传报「未找到」，改传子串 `Security Solutions, Inc.涨10%` 即成功。
> - 判据一句话：**标题里只要有 `“ ” & < >` 之类，直接改传绕开它的子串，别先试原文再补救。**

> 🔢 **定位子串必须避开数字——系统建的行情题标题数字会自己滚动更新（v2.9.39 — 2026-08-12 实测）**：系统会随行情持续改写自己题的涨跌幅，**B0 快照里读到的标题几分钟后就不是库里的标题了**。
> - 实证：B0 拉到 `2578`「存储板块逆势走强，SK Hynix Inc.涨**7.1%**」/`2579`「…Samsung Electronics涨**7.7%**」，3 分钟后用这两个全串 update **两条同时报「未找到」**；改传纯中文子串 `存储板块逆势走强` / `韩股三星电子逆势大涨` 立即成功，而返回体显示实际标题已变成「涨**6.9%**」「涨**7.5%**」——同一天更晚又变成「涨5.3%」「涨6.7%」（跟着收盘价走）。
> - **判据：定位子串只取不含数字的那段（板块名/公司中文名/动作词），数字一律不进定位串。** 与上方特殊字符条同族——都是"用眼睛看到的标题去定位"这个动作不可靠。
> - 我自建的题不受此影响（系统不改我的标题），但**处置系统行情题时必须默认标题在变**。
> - **⚠️ 板块题恰好相反：必须带数字，板块名反而定不了位（v2.9.44 — 2026-08-14 清池实测）**。系统板块题标题是**逐日复用的模板**，板块名在库里有几条到十几条同名历史题：`互联网板块集体下挫` 命中 4 条（`2573`/`2245`/`2183`/`2078`）、`航空航天与国防板块集体下挫` 命中 3 条（`2566`/`2506`/`2367`）、`DappOS` 命中 5 条、`Amazon.com Inc.涨` 命中 3 条、`美元储备增` 命中 3 条、`ARC主网定档` 2 条。**判据分两类**：① **事件题/我方题 → 避数字**（数字随行情滚动）；② **系统板块题、系统纯价格题 → 必须取 `ticker+数字` 段**（如 `TME跌12%、GOOGL跌3.8%领跌`），板块名是模板、数字才是唯一判别符。这类题已定稿不再被改写（多为 status=1/2 陈题），数字是稳定的。
> - **✅ 歧义报错可当探测器用**：命中多条时工具**安全报错并返回 candidates 全列表（含各自 status）**，绝不误伤。清池时反而靠它挖出了两类查询查不到的东西：**不在查询日期窗内的积压**（`10126` xBubble status=2，早于 08-01）、**在线的样式违规题**（`2432`「Amazon.com Inc.涨5.1%」status=0 仍挂前台，法人全名违 v2.9.43）。所以定位串**宁可先传短的**——报错的信息量大于成功。
> - **🐛 keywords 自动切词是可复现缺陷（v2.9.44 实测）**：系统给 `ETHERFI` 自动切成 `ETHER,FI`（`11388` 与 `11403` 两条独立生成的题都是这个结果），其中 **`FI` 命中 Fiserv（NYSE:FI）**，导致 news 检索 ETHFI 时返回 Fiserv 的股东诉讼稿。处置系统 crypto 题时**顺手核 keywords 有没有被切出两字母噪音段**，有则手工改（`ETHFI,AAVE`）。

> 🔢 **followin `metrics` 的 keywords 硬上限 5，超出部分静默丢弃（quirk⑮ — 2026-08-18 实测）**：一次传 10 个 ticker，返回体只含前 5 个，**主结果区没有任何缺失提示**，只在 `meta.warnings` 里逐个报 `keyword_count_over_max`。批量核价时若不读 warnings，会把"后 5 个标的没数据"误判成通道问题或误当成"这些标的没异动"。**判据：>5 个标的必须分批，且每批读一次 warnings 确认 `filters_applied.keywords` 与我传的一致。****同源勘误（08-18 复审）**：这不是新限制——v2.9.4（板块矩阵拆 ≤5/批）立的就是这同一个服务端上限，v2.9.39（query fanout 扩词后截断丢 keyword）是它的 query 形态；⑮ 的**增量只在失败表现**：显式多 ticker 传参时主结果区零提示、仅 warnings 报。判据三处通用：读 warnings／分批／非它不可的标的单独 call。**教训：立新 quirk 前先 grep 旧账。**

> 🚨 **`create_trending_topic` 端点会整体 500，而同期 `list`/`update` 正常（2026-08-18 实测）**：连续 5 次返回 `{"message":"An Internal Error Has Occurred.","code":500}`，含把标题和描述都缩短的极简版——**不是内容问题是端点故障**。判据：先用 `list` 探一次确认服务在线，再用短版本 create 探一次排除内容；两者都指向端点则**本轮放弃建题，把待建题写进 event-watch 下轮补**，不要反复重试刷错误。

> 🇨🇳 **followin `metrics` 不覆盖 A 股，科创板/沪深代码一律 `no_match`（quirk⑯ — 2026-08-19 实测）**：查 `688836.SS`（宇树科技）返回 `total: 0` 且 `meta.warnings` 明报 `unknown ticker / no upstream coverage`；换 `UNITREE` 关键词同样落空。对比：韩股 `000660.KS`／`005930.KS`、港股 `0700.HK` 均正常返回（memory「正股优先」那条成立的前提是**该市场在覆盖内**）。**判据：A 股标的的价格锚只能走多源媒体交叉 + 自校验**——本例发行价 150.8 元（Reuters）、开盘 1100 元＝+629.4%（BlockBeats）、现报 911 元自算 +504.1%（与 Odaily「回落至 500% 附近」吻合），三源互验后才敢写进标题。**不要因为拉不到价就跳过价格反应（v2.9.35），也不要拿单源数字直接落笔（v2.9.10）。**

> 🟢 **Hyperliquid / Trade.xyz 公开 API — 补美股盘后价、A股与 pre-IPO 标的的兜底通道（2026-08-19 实测接入，无需认证）**：
> `curl -s -X POST https://api.hyperliquid.xyz/info -H "Content-Type: application/json" -d '{"type":"metaAndAssetCtxs","dex":"xyz"}'`
> 实测 HTTP 200、~300ms、**无 key 无鉴权**。返回 `[meta, ctxs]` 两段并列，按下标对齐；每个 ctx 有 `midPx`／`prevDayPx`／`openInterest`／`dayNtlVlm`。
>   - **`dex="xyz"` 是关键**：Trade.xyz 是建在 HL 上的 **HIP-3 builder DEX**，它的 114 个标的**不在主 universe（232 个）里**——直接查 `allMids` 或 `{"type":"meta"}` 会得到 `NOT FOUND` 而**误判为"该标的不存在"**（08-19 我就这么误判过 UNITREE）。builder DEX 列表：`{"type":"perpDexs"}`（当前 11 个：xyz/flx/vntl/hyna/km/abcd/cash/para/mkts/io）。
>   - **它填补的三个真实缺口**：① **美股盘后/隔夜价**——24h 连续交易，`stock_extended_hours` 挂掉时唯一可用（08-19 该通道连续 2 次 ConnectError）；② **followin 不覆盖的标的**——`UNITREE`(A股宇树，quirk⑯)、`CXMT`／`ZHIPU`／`MINIMAX`(未上市中国 AI)、`KR200`(韩国200指数，解决 KOSPI 拉不到只能引用媒体的问题)、`SMSN`／`HYUNDAI`／`KIOXIA`；③ **OI 与成交额**——判资金流向。
>   - **点差实测（vs 我当日实测正股收盘）**：MSTR 92.521 vs 92.52（**0.001%**）、META 545.56 vs 543.67（+0.35%）、NVDA 219.11 vs 219.74（−0.29%）、RDDT 158.51 vs 158.23（+0.18%）。**主流标的点差极小**，但差额里混着"盘后继续走"的真实变动（SNDK 1593.35 vs 收盘 1625.78＝**盘后又跌 2.0%**；AAOI −2.2%、CRWV −1.3%）——这既是它的价值也是它与收盘价的区别。
>   - **⛔ 三条使用边界**：① **主锚仍是正股**（memory「个股价格锚=正股优先」不变），HL 只在"正股拉不到／要盘后价／要 OI"时用，并在文案中标明口径；② **`prevDayPx` 是滚动 24h、不是前一交易日收盘**——自算的 24h% 与正股当日涨跌幅**口径不同**（例：SNDK HL 24h −7.35% vs 正股当日 −9.01%），两者不可混写进同一句；③ **薄盘不可信**——先看 `openInterest`／`dayNtlVlm` 再用价（`RDDT` OI 仅 91、24h 额 15 万美元；`VIX` 的 `midPx` 直接是 `None`、OI=0）。
>   - **08-19 首用即验证的一例**：`11513`「UNITREE 上线 Hyperliquid 后拉升至 100 美元」——实测 `midPx=127.89`、`prevDayPx=100.37`，**它把 24 小时前的价格当成了"拉升至"的现价**；同时 Odaily 的 133.74「短时破 140 后回落」与火星财经空头开仓 81.8／清算 172.18 全部对得上。**一个能自查的通道，能把"三个互相冲突的单源数字"直接收敛成一个可核事实。**

### 工具速查

| 工具 | 用途 |
|------|------|
| `create_trending_topic` | 创建新话题 |
| `update_trending_topic` | 修改 title/keywords/tags/status |
| `list_trending_topics` | 查看话题列表（去重对照必用） |

### 已知 tag id 速查

> 🔧 **先自查 keywords 格式再怪打标器（v2.9.11 — 07-21 实测，推翻下方"打标器不可信"的一半结论）**：**我建的题 `matched_tags` 长期为空，根因是我把 keywords 传成了数组**，被序列化成 `"[\"IREN\",\"HUT\"]"` 原样存库，打标器拿到带方括号转义引号的串**匹配不到才是正确行为**。实证：10720 由 `["BONK"]` 改传字符串 `BONK`，`auto_matched_tags` **当场命中 159920**。→ **发现 matched_tags 空，第一步查 `new_keywords` 有没有 `[`/`\"`，不是第一步骂打标器**。下方"错实体/11 位垃圾 tag"是在**系统自建题**上观察到的，那部分仍成立。

> 🚨 **系统自动打标器不可信（v2.9.5 — 2026-07-14 用户报「Circle 打 OCC、SpaceX 打 SPC」，实扫 66 条坐实）**：打标器**解析话题标题**（不是干净 keywords）去 fuzzy match，两种错法——① **错实体**：把标题里的机构/监管缩写当标的（"获 **OCC** 批准"→OCC tag 13924、SpaceX→SPC tag 11359）；② **11 位垃圾占位 tag**：匹配不到就自造（`34523806708` / `10478645335` / `10346157100` / `14127290595` / `10200232432`）。**判据：正常 tag = 5-6 位数字；≥7 位（尤其 11 位）一律是垃圾，必清**。规律：**干净单 token 的 crypto 题（ZEC/OIL）自动标对；公司名+机构缩写的 tradfi 题必吐垃圾**。→ 每轮 tag 复核见 SKILL §3/AUTO 表；治本已入 dev 单。

**加密原生**
| 标的 | tag id |
|------|--------|
| BTC | 10006 |
| ETH | 10007 |
| SOL（Solana） | 10012 |
| DOGE | 10015 |
| AAVE | 10052 |
| ONDO | 352019 |
| ZEC | 10058 |
| WLD | 248008 |
| FET | 10201 |
| XAUt（黄金） | 10226 |
| OIL（原油） | 520979 |
| **BONK** | **159920** |
| **HYPE** | **489344** |
| **ENA** | **399979**（08-12 实测，`11346` keywords 含 `ENA` 自动命中，同批另返 10006=BTC）|

> 📭 **实测确认无 tag 库（勿重复探，留空即可）**：IREN、HUT8、SMCI、KOSPI、ZHIPU、Multicoin（07-21~22 create 后 matched_tags 均空且 keywords 格式已正确）；**日股/韩股正股**——`6976.T` 太阳诱电（08-12 `2581` 实测空）、三星 `005930.KS`（08-12 `2580` 实测空，只能手动绑 SK 的 658686/658687）。

> 🔍 **待核 tag（映射未确定，勿当已知用）**：`667111` 与 `416160` —— 08-12 `11350` 传 `PLTR,BTC,ETH,Hyperliquid` 返回 `667111+10006+10007+416160`，10006/10007 已知是 BTC/ETH，剩两个分别对应 PLTR 与 Hyperliquid 但**无法确定谁是谁**，下次单 keyword 建题时顺手分辨再入表。

**代币化美股 / 跨市场（v2.1.2 优先用此类）**
| 标的 | tag id | 备注 |
|------|--------|------|
| **NVDAX** | 522527 | NVIDIA 代币化 |
| **CRCLX** | 522611 | Circle 代币化 |
| **AAPLon** | 546230 | Apple 代币化（Ondo 发行）|
| **SPY-X** | 522609 | S&P 500 ETF 代币化 |
| **QQQ-X** | 522709 | NASDAQ-100 ETF 代币化 |
| INTC | 548353 | Intel（无代币化版，原票 tag）|
| GOOGL | 522630 | Google（无代币化版查到）|
| TSLA | 528245 | Tesla（无代币化版查到，可试 TSLAX）|
| **MU** | 550032 | 美光（2026-06 实测确认）|
| **MRVL** | 548352 | Marvell（2026-06 实测确认）|
| **COHR** | 635980 | Coherent 光通信（2026-06 实测确认）|
| **SpaceX** | 536083 | SpaceX pre-IPO 代币化（keyword="SpaceX" 可自动命中）|
| **AVGO** | 550939 / 550614 | Broadcom 代币化（2026-06-04 实测，keyword AVGOX/AVGOon 命中）|
| **COIN** | 522512 | Coinbase 代币化（COINX，2026-06-04 实测）|
| **MSTR** | 522610 | Strategy 代币化（MSTRX，2026-06-04 实测）|
| **AMD** | 634136 / 547619 | AMD 代币化（2026-06-11 实测，keyword AMDX/AMDon 命中）|
| **ORCL** | 563897 / 549884 | Oracle 代币化（2026-06-11 实测，keyword ORCLX/ORCLon 命中；裸 ORCL 不命中）|
| **SNDK** | 627019 | 闪迪代币化（2026-06-12 实测，keyword SNDKX/SNDKon 命中；**tradfi 域同样生效**——10000001925 首验）。WDCX/STXX 无命中（疑无代币化版）|
| NASDAQ 指数 | 10646 | 大盘/纳指话题手动绑（keywords 重匹配会顶掉，需以 tags 显式传回）|
| **SK 海力士** | **658686 + 658687** | SKHYX（2026-07-11 SKHY 挂牌后入库实测，keyword 含 `SKHYX` 即自动命中双标；HANDOFF#1 已结清。韩企 tag 此前整体缺席，SK 已解除）|
| **MU 原票** | **658099** | 美光原票（与代币化 550032 并存，双标最全；create 自动匹配只给 658099，要 550032 需 keywords 带 `MUX/MUon` 或手动绑）|

> 找新美股 tag：`update_trending_topic(keywords=["XXX","XXXX","XXXon"])` 加代币化后缀试一次，看返回的 `auto_matched_tags` 即得 tag id，命中即用，否则原 ticker + 手动绑。
