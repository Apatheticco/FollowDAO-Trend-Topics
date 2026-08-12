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

##### 📊 美股板块涨跌矩阵 — 8 板块代表股（§1 W3/W4 的 **6 批×5**（v2.9.8）= 本表高权重子集 +MRVL/TSLA/AMZN；GEMI/IBKR/LMT/RTX/BA 仅按需补拉）

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

**判定**：某板块 ≥2 标的同向 >3% 涨/跌 → 板块异动信号 → 进 0b 作板块候选（如 R-Mem 存储+光通信回调）。**拆 ≤5/批 跑（v2.9.4 — keywords 硬上限 5，旧"3×10"作废，改 6 批×5 或按板块 4 个一批）**，加 `categories=["market"]`（quirk⑩）；批内补 TSLA/AMZN 即覆盖科技大票，不单跑 Wave2C。

##### 🏛️ 宏观/大宗 — 符号校正 + fallback 链

主调（quirk⑨ 已校正，均 `categories=["market"]`）：**金=`XAUT`@crypto｜美元=`DXY`｜标普=`spx`@tradfi**。国债=`DGS10/DGS2`@macro。econ 日历=传前瞻日期窗（quirk⑫）。⚠️ 绝不用裸 `gold`/`oil`（quirk⑨ 解析成金矿股/Colgate）。

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

> 📭 **实测确认无 tag 库（勿重复探，留空即可）**：IREN、HUT8、SMCI、KOSPI、ZHIPU、Multicoin（07-21~22 create 后 matched_tags 均空且 keywords 格式已正确）。

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
