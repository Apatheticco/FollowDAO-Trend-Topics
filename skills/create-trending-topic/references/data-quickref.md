# 数据速查（tag id / list ID / 币表 / 板块矩阵 / 工具用法）— 从 SKILL.md 拆出（v2.8.2）

> ⚠️ 本文件是**数据**不是规则——数据会过时，更新这里不需要动规则文件。新 tag 实测到就补进来。

## 三栈 Twitter list ID

| 栈 | list_id | 用法 |
|----|---------|------|
| 主 | 2046422494643687464 | 首扫+刷新必跑 |
| 科技AI | 2051854001608724654 | 首扫+刷新必跑 |
| 大师 | 2051856808348987697 | 仅首扫（刷新砍）|

## 10 币价格固定列表

`BTC, ETH, SOL, BNB, XRP, DOGE, HYPE, SUI, AVAX, LINK`

> 🧱 **metrics keywords ≤5/批硬上限（v2.9.4 — 2026-07-11 实测 API 变更）**：`followin.metrics` 单次 `keywords` 超过 5 个会**静默截断到前 5**、返回 `warning: keywords truncated: N→5`，多的直接丢（07-10 同调用还 10 个全返回、零 warning，隔夜收紧）。**10 币拆 2 批（5+5）、下方板块矩阵每批 ≤5**，别一次塞 10——那是看不见的漏扫。

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

**判定**：某板块 ≥2 标的同向 >3% 涨/跌 → 板块异动信号 → 进 0b 作板块候选（如 R-Mem 存储+光通信回调）。**拆 ≤5/批 跑（v2.9.4 — keywords 硬上限 5，旧"3×10"作废，改 6 批×5 或按板块 4 个一批）**，加 `categories=["market"]`（quirk⑩）；批内补 TSLA/AMZN 即覆盖科技大票，不单跑 Wave2C。

##### 🏛️ 宏观/大宗 — 符号校正 + fallback 链

主调（quirk⑨ 已校正，均 `categories=["market"]`）：**金=`XAUT`@crypto｜油=`CLUSD`@tradfi｜美元=`DXY`｜标普=`spx`@tradfi**。国债=`DGS10/DGS2`@macro。econ 日历=传前瞻日期窗（quirk⑫）。⚠️ 绝不用裸 `gold`/`oil`（quirk⑨ 解析成金矿股/Colgate）。

| 主调失败 | Fallback |
|---------|----------|
| `XAUT`(金) | `PAXG`@crypto |
| `spx` | `SPY/QQQ`@tradfi |
| `DXY` | `DTWEXBGS`@macro |
| `CLUSD`(油) | `USO/BNO`(ETF，追踪非现货) |
> Primary 失败必跑 fallback，仍失败标"⚠️数据缺失"。**followin.metrics 整体挂 → 价格源降级梯（§1 末 okx/web）**。


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

### 工具速查

| 工具 | 用途 |
|------|------|
| `create_trending_topic` | 创建新话题 |
| `update_trending_topic` | 修改 title/keywords/tags/status |
| `list_trending_topics` | 查看话题列表（去重对照必用） |

### 已知 tag id 速查

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

> 找新美股 tag：`update_trending_topic(keywords=["XXX","XXXX","XXXon"])` 加代币化后缀试一次，看返回的 `auto_matched_tags` 即得 tag id，命中即用，否则原 ticker + 手动绑。
