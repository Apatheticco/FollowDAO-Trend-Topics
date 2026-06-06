---
name: create-trending-topic
description: >
  从原始素材或主动扫描热点，自动提取结构化字段，创建 Followin 热点风向标（TrendingTopic），并支持发布。
  三种触发场景：
  (A) 用户让"扫一下热点 / 找几个话题 / 批量创建今日话题" → 调 Followin MCP（metrics/news/signal/twitter）主动扫描；
  (B) 用户给一段素材（新闻/推文/描述）让创建话题 → 直接进评分；
  (C) 用户给一个标的或一句话（"查一下 REPPO" / "Aave 现在情况"）→ 多源补全资料再评分。
  全流程：采集 → 去重 → 评分 → 字段提取 + 标题优化 → 预览 → 创建 → tag 校验 → 数据核实 → 发布。
---

# 创建热点风向标

---

## ⚡ 执行卡（v2.4 — 每轮照此跑，细节见下方对应章节）

> 90% 的扫描照本卡执行即可；遇到边界/判定再翻下方详章。本卡是「跑什么 + 怎么并行」的**单一事实源**。

### 0. 开跑前（铁律）
```bash
date '+%Y-%m-%d %H:%M:%S %Z (UTC%:z) | Unix: %s'   # 必跑，算 cutoff_4h/24h
```
判模式：`"早上扫/隔夜更新"`→🟢首扫(24h) ｜ `"刷新/有什么新的"`→🔵刷新(4h) ｜ 模糊：06-10 点首扫、之后刷新 ｜ 今日 status=0 发布 0 条 → 强制首扫。

### 1. 并行批次表（同一格 = 同一 turn 内并发；followin 单批 ≤5 防掉线）

**🔵 刷新（4h）— 3 批 followin + 3 Agent + 1 console**
| 批 | server | 并发 calls |
|----|--------|-----------|
| B0 | console | `list_trending_topics(24h, 全状态, limit=80)` ← 先跑，喂 0a/0a.5/自动撤回 |
| B1 | followin | 10币 metrics（**`categories=["market"]`**）｜ 跨市场 metrics（金=`XAUT`@crypto / 油+美元=`["CLUSD","DXY"]`@tradfi，均加 `categories=["market"]`；见 quirk⑨⑩）｜ news(crypto market 4h) ｜ news(listing/解锁/SEC 4h) ｜ news(tradfi 头条 4h concise) |
| B2 | followin | TG 交易信号 ｜ TG 实盘跟踪 ｜ news(美股 query 兜底, 不传 asset_type) ｜ Wave5 鲸鱼 ｜ Wave5 上币 |
| A1 | Agent×2 | **刷新只 2 栈**：主 `2046422494643687464` + 科技AI `2051854001608724654`（大师 list 刷新砍——4h 几乎每次"无新推"，移首扫；明确"看大师"才破例）|

> 刷新 **砍掉的死调用**（v2.5 实测）：
> - **Wave5 ETF query 砍** — `spot` 总被解析成 Spotify 股 / degraded；ETF flow 改读 TG 链上 bot（PolyBeats/Database52Hz 稳定回 BTC/ETH/SOL/HYPE netflow），已含在 TG cat 里。
> - **Wave5 上币 query 刷新砍**（4h 内永远返 9 天前陈旧 HACK ETF），只首扫留。
> - 不跑 signal（4 cat 全砍）｜不跑 popularity / 国债 / spx ｜±15% 漏网币第二轮核。

**🟢 首扫（24h）— 4 波 followin 塞满 + 1 TG 波 + 3 Agent + 1 console（窗口 1d 替换 4h）**

> ⚡ **批次铁律（v2.5.1 — 2026-06-06 复盘：上次 6 波串行跑了 7min）**：每波**严格塞满 5 个 followin**（≤5 防掉线），4 波打完所有价格/news，别欠装、别为 1 个 call 单开一波。spx 必 fail → SPY/QQQ 兜底**预判着塞进 W1**，不要等失败再补一波。
>
> | 波 | 5 个并发 followin call | 备注 |
> |----|----------------------|------|
> | **W1 价格核心** | ①10币(market) ②金 XAUT(crypto/market) ③油+美元+spx `["CLUSD","DXY","spx"]`(tradfi/market) ④SPY+QQQ+VIX(tradfi/market，spx 兜底**预判直塞**) ⑤crypto market news(1d) | 同波**并行起 A1 三栈 list 子进程**（主/科技AI/大师）|
> | **W2 事件/链上 news** | ①listing/解锁/SEC/漏洞 news ②tradfi 头条(concise) ③美股 query 兜底(不传 asset_type) ④Wave5 鲸鱼 ⑤Wave5 上币 | 全 news |
> | **W3 板块+宏观** | ①板块批1[NVDA,AMD,AVGO,TSM,MSFT,GOOGL,META,AAPL,MU,SNDK] ②板块批2[WDC,STX,LITE,AAOI,GLW,COHR,ASML,AMAT,LRCX,KLAC] ③板块批3[CRCL,COIN,MSTR,HOOD,SOFI,PLTR,RKLB,MRVL,**+TSLA,AMZN**] ④econ 日历(macro，只 query) ⑤国债 DGS10/DGS2(macro) | 板块矩阵 3×10（quirk⑪）；批3 补 TSLA/AMZN 即覆盖 Wave2C，**Wave2C 已并入此处，不单跑** |
> | **W4 扫尾** | ①跌榜 top losers(market) ②earnings 日历(fundamentals，周一/财报周必跑) ③Wave5 解锁/财库 news ④（按需）关键宏观点位 CPI/UNRATE ⑤（按需）±15% 漏网币第二轮核 | 涨榜 `biggest gainers` **默认砍**（penny 垃圾 + 配 min_market_cap 必 source_dead，见 quirk⑪）；按需才补 |
> | **W-TG** | TG 5 cat（交易信号/实盘跟踪/链上数据/叙事追踪/Meme 打新），分 3+2 并行 | 独立波，与上面任一波之后接着发即可 |
>
> A1 第 3 栈 = **大师 list `2051856808348987697`**（首扫必跑；刷新砍）。3 栈子进程 44s 量级是长杆，**必须在 W1 就起**，让它和 W2-W4 并行跑完，别落关键路径末尾。

### 2. 候选处置路由（status × 年龄 → 走哪条规则）
| status | 年龄 | 处置 |
|--------|------|------|
| **0 上线** | ≤24h | 数据偏差 ≥10%→0a 升温 update title；>25%→撤(status=3)；>50% 反向→强撤 |
| **0 上线** | >24h | **不动不提**；当前行情 → 新建一条（不改老话题）；唯 >50% 反向脱锚强撤 |
| **2 审核** | ≤8h | 0a.5 预过滤 → ✅发 / 🟠改 / 🚨撤 / 🟡待核（表 3 必列）|
| **2 审核** | 8–24h | 从简报剔除、不再 push |
| **2 审核** | >24h | v2.3.0 自动撤(status=3)；命中 >10 条先列清单确认再批撤 |
| **3 hidden** | — | 不重建、不分析 |

### 3. 评分 → 三件套 → 建/核/发
- **0b.0 时效硬过滤**：published_ts 超窗（首扫>24h / 刷新>4h）→ 直接砍，不进评分。
- **四维评分** A 行情冲击(0-3)+B 讨论热(0-3)+C 稀缺(0-2)+D 紧迫(0-2)；max(A,B)≥2 才排序。P0≥8 / P1=6-7 / P2=4-5。
- **三件套主报告**：🆕表1 补充（首扫目标 12 / 刷新 8，达不到先扩窗，仍不足如实报干轮、不灌水不硬报0）｜🔧表2 更新｜🚨表3 撤回+在审池处置。
- **建**：预览确认（不可跳过，确认前不调 MCP）→ create（**不传 desc**）→ tag 校验（美股主动手动绑，查速查表）→ **4.5 数据核实**（≥5 条走批量路径：1 次 metrics + 并行多源）→ 发布 status=0。

---

## 整体管线（v2.2 — 三件套主输出）

```
[A 让扫描]    → 第 -1 步：扫描热点（首扫/刷新模式）
[C 给标的/句子] → 第 -1.5 步：定向检索深挖
                                      ↓
                第 0a 步：拉过去 24h 已建话题 → 建索引（symbol/category/keyword）
                                      ↓
                第 0a.5 步：8h 在审池预过滤
                                      ↓
                第 0b 步：四维评分 A/B/C/D（v2.2 — 加稀缺性 + 紧迫性）
                                      ↓
        ╔════════ 🎯 主报告：撤改补三件套（v2.2）═══════════╗
        ║                                                  ║
        ║   🆕 补充（最优先 — 首扫 ≥12 / 刷新 ≥8 条）        ║
        ║   🔧 更新（升温 / 事件升级 / 标题数据脱锚）         ║
        ║   🚨 撤回（脱锚 / 重复 / 弱主体 / 触类型阈值）      ║
        ║   ───────────────────────────                    ║
        ║   🟰 已建覆盖（精简列表，反证差异化）              ║
        ║   📊 实时数据（fold 收起，供查阅）                ║
        ║                                                  ║
        ╚══════════════════════════════════════════════════╝
                                      ↓
[B 给素材] ──→ 第 1 步：字段提取 + 标题优化
                                      ↓
                第 2 步：预览确认（不可跳过）
                                      ↓
                第 3 步：create_trending_topic
                                      ↓
                第 4 步：tag 命中校验
                                      ↓
                第 4.5 步：数据核实（强制）
                                      ↓
                第 5 步：发布评分 → status=0 上线
```

### 🎯 v2.2 核心理念

**风向标的本质 = 帮用户决定"今天该补什么话题"**。三件套优先级：
1. **🆕 补充（最重要）** — 当前缺什么强候选 → 用户最关心
2. **🔧 更新** — 已建话题如何随事件演进
3. **🚨 撤回** — 已建话题哪些必须下线

任何扫描的输出**必须**包含完整三件套；"🆕 补充"目标（首扫 12 / 刷新 8）达不到时**先强制扩窗重扫**，扩窗后仍不足则**如实报干轮**（见「候选池数量目标」）——不灌水、不硬报 0。

---

## 第 -1 步：扫描热点（A 入口）

### 🕐 第 0 步铁律：时间校准（v2.1.8 — 每次扫描第一件事）

**铁律**：任何扫描（首扫 / 刷新 / 检索）开始**前**，必须先执行：

```bash
date '+%Y-%m-%d %H:%M:%S %Z (UTC%:z) | Unix: %s'
```

**理由**：
- 系统 prompt 提示的"今天日期"可能滞后（实测 5/18 早上还在按 5/14 算）
- 价格 / 新闻 timestamp 解读、8h / 4h / 24h 窗口判定全部依赖准确"现在"
- 升温检查（10%/25%/50% 偏差）的"建时 vs 现在"需要正确时间锚点
- "已建话题 8h 在审池" 的 cutoff 计算依赖现在时间

**违反信号**：发现自己说"今天是 X 日"和 `date` 输出不一致 → 立刻重算所有窗口 + 重新生成简报。

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
> 最常被漏：**三栈 list_timeline**（主 2046… / 科技AI 2051854… / 大师 2051856…）。下方各 Wave 章节只补充批次表装不下的判定细节。

### ⚠️ Followin 已知 quirks（v2.3.1 实测，对齐线上 schema）

1. **session 偶发掉线** — `"session not found"` / `"session initialization"` 错误。重试一次通常恢复；连续失败需重启 Claude Code
2. **🚫 `news` 端点无 `sort_by` 也无 `categories`** — 传了报 `MCP error -32602: unexpected additional properties`。`news` 只认 `query / sources / asset_type / time_range / limit / verbosity / source_lang / search_depth`。**排序/分类靠 query 措辞 + time_range，不靠参数**（旧版 skill 里所有 `news(sort_by=, categories=)` 写法已失效）
3. **🚫 `metrics` 无 `sort_by`（但有 `categories`）** — 涨跌榜/movers 用 `metrics(query="biggest gainers" / "涨幅榜" / "market movers", asset_type, categories=["market"], min_market_cap=1000000000)`。`min_market_cap=1e9` 同时滤掉 penny stock + 大部分 2x/3x leveraged ETF 噪音
4. **`news(asset_type="tradfi")` 偶发返回 0** — Fallback：检测 `results=null` 时改用 `news(query="<关键词>", 不传 asset_type, verbosity="concise")` 重试一次
5. **tradfi news 只返回标题** — FMP news 通道仅返回 title（~266 token / 10 条）。要正文改 `query` 走 opensearch 通道
6. **`news` 默认 verbosity=standard 带完整正文** — limit≥20 易炸 context（实战 56K 字符）。生产用 `verbosity="concise"` + `limit≤15`
7. **`news(asset_type="tradfi")` FMP 偏 WSJ/Bloomberg/Barron's** — 漏 **Reuters 独家 / X 突发 / 中文媒体爆点**。修复：刷新必跑 query 兜底 `news(query="<当周关键词>", 不传 asset_type, time_range="4h")`（实战 5/14 漏 NVIDIA H200 出口许可）
8. **TG `sources=["telegram"]` 返回 `tg_kol_feeds`** — 字段为 `tg_category / author_name / content / _source_quality / published_ts`，**无 `username`**。过滤用 `author_name` 或直接按 `tg_category` + content grep（"币安将上线" / "Whale Alert" / "巨鲸"）。Meme 打新 cat 全 low-quality spam，**可砍**
9. **🚫 大宗裸 keyword 会乱解析成同名股票（2026-06-03 实测）** — `metrics(keywords=["gold"])`→**Barrick Gold 金矿股 $39**、`["oil"]`→油股、`["CL"]`→Colgate 牙膏、`["BZ"]`→看准网中概，全是垃圾值。`query="price now"` **不能修**（数值照错、体积照炸 66K）。**正解 = 用现货符号**：金 `keywords=["XAUT"], asset_type="crypto"`（实测 $4,416/oz，PAXG 同效）｜油 `keywords=["CLUSD"], asset_type="tradfi"`（name="Crude Oil" 实测 WTI $94.95）｜美元 `keywords=["DXY"]`（返回 DXUSD 99.4，无需改）。`USO/BNO` 是油 ETF（追踪但非现货价），仅作兜底
10. **✅ metrics 溢出 + macro 噪音根治：所有价格调用加 `categories=["market"]`（2026-06-05 实测）** — 不传 categories 时，metrics 自动扇出到 macro+fundamentals 两个 bucket：tradfi 逐 ticker 返回全 fundamentals → **2 股就溢出 130K、12 股 700K**；crypto 则混入 ~10 行 macro 噪音（kw_not_canonical + EIA 汽油垃圾）。**加 `categories=["market"]` 锁定只要行情 bucket → 彻底根治**：
    - tradfi 内联返回不溢出，且直接带 `change / dayHigh / marketCap / yearHigh`（涨跌幅白送，无需 python 提取）。**板块矩阵 / Wave2C / 涨跌榜全部直接内联跑，旧的"存盘提取"全废弃。**
    - crypto 10 币纯 snapshot，零噪音。
    - **铁律**：`metrics` 凡是拉价格快照（crypto/tradfi/跨市场/板块矩阵），一律带 `categories=["market"]`。仅当真要财报/宏观点位才用 `["fundamentals"]`/`["macro"]`。
11. **🚫 `metrics` keywords 硬上限 = 10 个（2026-06-06 实测）** — 传 >10 个会**静默截断**到前 10 个，只返回 warning `keyword_count_over_max: keywords truncated: N → 10`，**不报错、不补返回**，极易漏数据而不自知。`categories=["market"]`（quirk⑩）只治 token 溢出，**不解此上限**。
    - **铁律**：板块矩阵（~28 股）等 >10 keywords 的批量价格拉取，**必须拆 ≤10/批 并行**（28 股 = 3×10）。一次只塞 10 个 ticker。
    - `change` 字段是**绝对额（美元）非百分比**；% 需自算 `change / previousClose`。
    - 涨榜 `biggest gainers` 配 `min_market_cap=1e9` 实测会 `source_dead:min_market_cap_excluded_all`（gainers 端点 marketCap 字段为 null）→ 涨榜不要传 min_market_cap，penny 噪音靠 Agent 后过滤。

### 价格数据铁律

简报中所有当前价格/涨跌幅，**只能引用 `followin.metrics` 返回的硬数据**。新闻标题、TG 帖子、KOL 推文里的价格描述一律视为"叙事来源"。输出分区：**📊 实时数据** vs **📰 叙事候选**。

### 🔁 价格应急扩列规则（首扫 / 刷新通用）

固定列表 `BTC,ETH,SOL,BNB,XRP,DOGE,HYPE,SUI,LINK,AVAX` 经常漏掉日内主线（实战漏掉 ZEC +30% / WIF +25%）。规则：

1. 跑完第一轮 `followin.metrics(keywords=[...], asset_type="crypto")` 拿到固定 10 币硬数据
2. 扫描 news / TG / twitter 文本里出现的**单代币涨幅描述**
3. 任一代币描述涨幅 **≥ +15%** 或 **≤ -15%** 且不在固定列表 → 收集 symbol，**第二轮**再调一次 `followin.metrics(keywords=漏网symbol列表, asset_type="crypto")` 核验
4. 第二轮硬数据进 📊 实时数据区；新闻里读到的数字只能写在 📰 叙事候选里加 ⚠️ 单源未核

> 铁律：**任何超过 ±15% 的代币若未经第二轮核验，不得写入"实时数据区"**，避免 KOL 数字误传到话题 desc。

### 🟢 首扫模式（每天早上 1 次，24h 窗口）

**目的**：建立当日全景，覆盖隔夜热点 + 跨市场宏观/美股素材。

#### Wave 1 — 加密热点 + 价格快照

| 工具 | 参数 |
|------|------|
| `followin.news` | `time_range="1d", asset_type="crypto", limit=20` — 24h 加密热门 |
| `followin.news` | `query="crypto market news", asset_type="crypto", time_range="1d", limit=15` — 加密时间序快讯（news 无 categories，用 query 措辞）|
| `followin.metrics` | `keywords=["BTC","ETH","SOL","BNB","XRP","DOGE","HYPE","SUI","LINK","AVAX"], asset_type="crypto", categories=["market"]`（quirk⑩：加 market 去 macro 噪音）|

#### Wave 2A — 加密交易信号（推特 list + KOL + TG 频道）

| 工具 | 参数 |
|------|------|
| `followin.twitter` | `action="list_timeline", list_id="2046422494643687464"`；**Agent 子进程**提取 text/author/likeCount/retweetCount/viewCount/createdAt，按 velocity top 15 + recency top 5 取 |
| **`followin.news` TG 频道扫描** | 见下方 **「📡 TG 频道扫描范式（v2.1.5）」**，5 个 category 并行 |

> **v2.2.7**：Wave 2A 不再跑 `signal(kol_call)` —— 个人 TA 喊单噪音多、与 TG「交易信号」cat 重复，已砍。

> v2.1.5 加 TG 频道扫描，覆盖 trend-scout v1.6.8 验证过的链上巨鲸 bot 信号源（PolyBeats_Bot / OnchainData / Whale_Alert / CoinbobAI 等）。
> v2.0 移除：`whale_trader_feeds` / `top_traders_live_24h` / `tg_kol_feeds`（旧 MCP 信噪比低）。

##### 📡 TG 频道扫描范式（v2.1.5）

**风向标场景的 category 矩阵**（精简到 5 个，去掉资讯聚合 / 项目研究 / 宏观研判 — 这些 Wave 1/2B/3 已覆盖）：

| 模式 | 扫的 category | 用途 |
|------|--------------|------|
| 🟢 首扫 (1d) | 交易信号 / 实盘跟踪 / 链上数据 / 叙事追踪 / Meme 打新 | 5 个并行 |
| 🔵 刷新 (4h) | 交易信号 / 实盘跟踪 | **2 个并行**（v2.1.7 砍 Meme 打新 — 实测全 spam）|
| 🔴 突发 | 按事件匹配 1-3 个 category | 定向 |

**调用范式（首扫 5 路并行）**：
```python
parallel for cat in ["交易信号","实盘跟踪","链上数据","叙事追踪","Meme 打新"]:
    followin.news(
        query=cat,            # query=category，Followin 已内建 category 索引
        sources=["telegram"],
        time_range="1d",
        limit=15,
        source_lang="zh-cn",
        verbosity="standard"  # 显式 standard 避免 concise 自动 trim
    )
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

**风向标用法**：TG 扫到的**具体链上事件**（巨鲸转账金额、聪明钱仓位变动、meme 早期打新）直接进 0b 双轴评分；**模糊讨论**不进。这一通道补足了 trader_position 数据死角（Followin 之前 v2.0 移除的 whale_trader_feeds 等价值）。

**避坑**：
- Followin session 跑 5-8 calls 易挂 → 5 个 category **必须分 2 批并行**（3+2 或 2+3）
- `query="<category>"` 必传（不要堆砌关键词），Followin 已按 category 内建索引
- `limit=15`/cat 是首扫；刷新 4h 窗口降到 `limit=20` 单批 3 cat

#### 🟣 Wave 2B — 美股 / 投资素材（v2.2.4 — 加板块涨跌扫描）

> 让宏观、美股财报、议员/内部人持仓异动 **+ 美股热门板块涨跌** 都进入热点风向标候选池。

| 工具 | 参数 / 说明 |
|------|-----------|
| `followin.news` | `asset_type="tradfi", time_range="1d", limit=15, verbosity="concise"` — FMP 策划美股头条（**仅返回标题**，~400 token / 15 条）|
| `followin.metrics` | `query="earnings calendar this week", categories=["fundamentals"], asset_type="tradfi"` — **周一必跑**，财报周每天跑（FMP calendar 含 estimate/actual/impact）|
| `followin.metrics` | 涨榜 `query="biggest gainers", asset_type="tradfi", categories=["market"], min_market_cap=1000000000`；跌榜 `query="top losers", ...` — 美股涨/跌榜（`min_market_cap=1e9` 已滤 penny + 多数 2x/3x ETF；残留 leveraged ETF 仍可 Agent 子进程过滤 name 含 `"2X"/"3X"/"Bull"`）|
| **`followin.metrics` 板块扫描（v2.2.4 新增）** | 见下方「📊 美股板块涨跌矩阵扫描」|

> **v2.2.7**：Wave 2B 不再跑 `signal(insider_trading)` —— LASR/WTTR 等小盘内部人交易噪音大、F-InKind 非主动卖出多，议员持仓被宏观新闻覆盖。

##### 📊 美股板块涨跌矩阵扫描（v2.2.4 — 首扫必跑）

风向标常漏掉**子板块异动**（如 5/18 存储 + 光通信集体崩盘只看大盘看不出来）。必须扫 8 大热门板块代表股：

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

调用范式（v2.5.1：加 `categories=["market"]` 后不溢出，但 **`metrics` keywords 硬上限 10 个**（2026-06-06 实测，28→10 静默截断 warning `keyword_count_over_max`）→ 必须**拆 3×10 批并行**，不再 python 提取）：
```python
# ⚠️ 单 call ≤10 keywords，28 股拆 3 批并行（同一 turn 内 3 call）
batches = [
  ["NVDA","AMD","AVGO","TSM","MSFT","GOOGL","META","AAPL","MU","SNDK"],
  ["WDC","STX","LITE","AAOI","GLW","COHR","ASML","AMAT","LRCX","KLAC"],
  ["CRCL","COIN","MSTR","HOOD","SOFI","PLTR","RKLB","MRVL"],
]
parallel for b in batches:
    followin.metrics(
        keywords=b,
        asset_type="tradfi",
        categories=["market"],   # ← 锁 market bucket，否则逐股 fundamentals 炸 700K（quirk⑩）
        query="price now"
    )
# 返回直接含 price/change/dayHigh/marketCap，涨跌幅白送（change 是绝对额，% 需 change/previousClose 自算）
```

**输出判定**：每个板块若有 ≥2 个标的同向 >3% 涨/跌 → 板块异动信号 → 进 0b 评分作板块候选话题（如本次 R-Mem 存储+光通信回调）。

#### 🟦 Wave 2C — 科技 / AI 素材（v2.1.1 修订）

| 工具 | 参数 |
|------|------|
| `followin.twitter` | `action="list_timeline", list_id="2051854001608724654"`（科技 AI + 宏观美股投资 list），Agent velocity top 10 + recency top 3 |
| `followin.metrics` | `keywords=["NVDA","AAPL","TSLA","MSFT","META","GOOGL","AMZN","AVGO","AMD","PLTR"], asset_type="tradfi", categories=["market"]` — 7 大科技股价+涨跌幅（quirk⑩：加 market 不溢出，直接带 change%）|

#### 🏛️ Wave 3 — 宏观 / 大宗（v1.5，v2.1 大幅简化）

| 工具 | 参数 |
|------|------|
| `followin.metrics` | `query="economic calendar this week US high impact", categories=["macro"]` — 一天一次。⚠️ **只用 query，绝不传 keywords**（传 US/nfp/PAYEMS 等会各回 10 条同样的 JP/KR 噪音 = 60-90 行垃圾）；query 字面过滤也不生效，**Agent 子进程自过滤** `country in ["US","CN","EU"]` 且 `impact="High"` |
| `followin.metrics` | `keywords=["10Y","2Y","DGS10"], categories=["macro"]` — 国债收益率 |
| `followin.metrics` | 大宗+美股全景：`keywords=["CLUSD","DXY","spx"], asset_type="tradfi", categories=["market"]`（油/美元/标普）+ 金另调 `keywords=["XAUT"], asset_type="crypto", categories=["market"]`。⚠️ **不要用裸 `gold`/`oil`**（quirk⑨ 解析成金矿股 / Colgate）；**加 `market`**（quirk⑩ 去 fundamentals 溢出）|
| `followin.metrics` | `keywords=["CPIAUCSL","UNRATE"], categories=["macro"]`（按需）— 关键宏观点位 |

**🛟 跨市场价格 Fallback 链（v2.1 — Followin 内部已统一，仍保留兜底）**：

> ⚠️ 主调符号已按 quirk⑨ 校正——**金=`XAUT`(crypto，实测 $4,416/oz)｜油=`CLUSD`(tradfi，实测 WTI $94.95)｜美元=`DXY`(返回 DXUSD)**。下表是这些主调失败时的兜底。

| 主调（已校正） | Fallback |
|---------|----------|
| `metrics(["XAUT"], crypto)` 金 | `metrics(["PAXG"], crypto)` → 另一只链上金 |
| `metrics(["spx"], tradfi)` | `metrics(["SPY","QQQ"], tradfi)` |
| `metrics(["DXY"], tradfi)` | `metrics(["DTWEXBGS"], macro)` 美元指数官方 |
| `metrics(["CLUSD"], tradfi)` 油 | `metrics(["USO","BNO"], tradfi)` → 油 ETF（追踪现货，非现货价）|

> 铁律：Primary 失败时必须跑 Fallback；Fallback 仍失败再标"⚠️ 数据缺失"。

#### 🔶 Wave 4 — 投资大师专项（仅周一 / 季度初）

| 工具 | 参数 |
|------|------|
| `followin.twitter` | `action="list_timeline", list_id="2051856808348987697"`（Buffett/Druck/Burry/Cathie/Ackman 等）|

> **v2.2.7**：Wave 4 不再跑 `signal(institutional)` —— 13F 是季度滞后数据，对日级别风向标价值低。

#### 🔍 Wave 5 — 二线候选 query 兜底（为接近 12 候选目标的扩窗手段）

风向标常漏掉**链上细节 / 上币公告 / 解锁 / 财库 / 鲸鱼**等二线信号。Wave 1-4 偏主线，必须加 query 兜底扫这些维度：

| query | 用途 |
|-------|------|
| `news(query="鲸鱼 巨鲸 whale transfer 大额转账", time_range="1d", limit=15)` | 链上鲸鱼异动 |
| `news(query="binance coinbase listing delisting 上币 下架", time_range="1d", limit=10)` | 交易所公告 |
| `news(query="unlock 解锁 vesting 财库 treasury", time_range="1d", limit=10)` | 解锁 + 财库 |
| `news(query="ETF inflow outflow 净流入 流出", time_range="1d", limit=10)` | ETF 资金流向 |

并行 4 调用（v2.2.7 — `signal(trader_position)` 已砍：同一鲸鱼仓位反复加减仓产生大量低价值 spam）。

执行完 → 进入第 0a 步。

> 首扫具体跑哪些批次 / 怎么并发 → 见顶部「⚡执行卡 §1」。下方各 Wave 章节只补判定细节。

### 🚨 强制铁律：Twitter list + TG 频道不可跳过（v2.2.4 实战教训）

实战教训（5/19）：跑首扫时漏掉 Twitter list 和 TG 频道扫描 → **直接缺 5+ 强候选**（Google×Blackstone / 马斯克 OpenAI 败诉 / 黄仁勋 Computex / 韩国零售融资 / Pumpfun 抛售）。这些 megaevent 只在 Twitter list + TG bot 出现，新闻通道捞不到 → 故执行卡 §1 把三栈 list + TG 列为必跑批次。

**失败处置**：任一批次失败 → **重试 1 次，仍失败标"⚠️ Wave 2A/TG 部分失败"**，不能直接进 0b。

**候选数量铁律**：跑完执行卡 §1 全部批次后，进 0b 评分前点 P0+P1 候选数（首扫 ≥12 / 刷新 ≥8 为目标）；不足则**先强制扩窗**（加 query 关键词 / TG 加 cat），扩窗后仍不足按 0b「候选池数量目标」如实报干轮。

### 🔵 刷新模式（日内每 2-4h，4h 窗口）

**目的**：追首扫之后的增量（含跨市场）。

#### 加密 + 跨媒体新闻

| 工具 | 参数 | 与首扫差异 |
|------|------|----------|
| `followin.news` | `query="crypto market", asset_type="crypto", time_range="4h", limit=20` | 4h 加密时序快讯 |
| `followin.news` | `query="listing unlock hack SEC ETF 上线 解锁", time_range="4h", limit=15` | 4h 基本面/事件（news 无 categories，用 query 覆盖）|
| `followin.metrics` | 固定 10 币 + 漏网核验 | 必刷价格 delta |

#### 双栈 List Timeline（刷新必跑；大师栈刷新砍）

| List | 参数 |
|------|------|
| 主 list `2046422494643687464` | `followin.twitter(action="list_timeline")`，4h，Agent velocity top 7 + recency top 3，<30min 硬保留，取 10 条 |
| 🆕 科技 AI list `2051854001608724654` | 同上，4h，Agent velocity top 5 + recency top 2 |
| ~~投资大师 list~~ | **刷新砍**（v2.5 — 4h 几乎每次"无新推"，移首扫；明确"看大师"才破例）|

#### 📡 TG 频道扫描（v2.1.7 — 刷新 2 路并行）

```python
parallel for cat in ["交易信号","实盘跟踪"]:
    followin.news(
        query=cat, sources=["telegram"], time_range="4h",
        limit=20, source_lang="zh-cn",
                 # 刷新看时效
        verbosity="standard"
    )
```
后处理见 Wave 2A「TG 频道扫描范式」。**刷新砍 3 个 cat**：
- ❌ 链上数据（与 signal 重复，且 4h 增量稀疏）
- ❌ 叙事追踪（媒体型，FMP 通道已覆盖）
- ❌ **Meme 打新**（v2.1.7 — 实测全 low quality 个号 spam，无白名单字段过滤，价值极低）

#### 🟣 美股 / 跨市场新闻（v2.1.7 — 双通道兜底）

| 工具 | 参数 | 作用 |
|------|------|------|
| `followin.news` | `asset_type="tradfi", time_range="4h", limit=15, verbosity="concise"` | FMP 严肃财经头条（WSJ/Bloomberg/Barron's）— 标题流，~300 token |
| **`followin.news` query 兜底**（v2.1.7 新增） | `query="<当周 tech/政策关键词>", time_range="4h", limit=10, verbosity="concise"` — **不传 asset_type** | 抓 Reuters 独家 / 中文媒体爆点 / X 突发，弥补 FMP 通道盲区 |

**query 兜底关键词模板**（每天根据热点轮换）：

| 当周热点 | query |
|---------|-------|
| 中美 AI 博弈 / 芯片出口（如 H200）| `"NVIDIA AMD chip China Trump tariff Huawei"` |
| Fed 主席换届 / 通胀 | `"Powell Warsh Fed Chair CPI PPI inflation"` |
| 地缘冲突 / 油价 | `"Iran Hormuz oil OPEC Brent ceasefire"` |
| 财报周 | `"earnings beat miss EPS guidance Q1 Q2"` |
| 政策立法 | `"CLARITY GENIUS SEC stablecoin Tillis Alsobrooks"` |

> 🐛 **v2.1.7 实战教训（2026-05-14）**：刷新模式只跑 `asset_type="tradfi"` 通道时**漏掉 H200 出口许可 megaevent**（路透社独家 + 中文媒体爆点）。FMP 通道偏严肃财经媒体，**漏掉 Reuters / X / 中文媒体**这类跨界新闻。query 兜底通道是必跑项。

#### 🔍 Wave 5 — 二线 query 兜底（v2.5 — 刷新只留 1 路）

刷新模式只留鲸鱼一路；上币/ETF 两路实测无效已砍：

| query | 用途 |
|-------|------|
| `news(query="鲸鱼 巨鲸 whale 大额转账 链上", time_range="4h", limit=10)` | 4h 链上鲸鱼增量 |
| ~~上币 query~~ | **砍**（4h 内永远返 9 天前陈旧 HACK ETF）|
| ~~ETF query~~ | **砍**（`spot` 总解析成 Spotify / degraded）→ ETF flow 改读 **TG 链上 bot**（Database52Hz/PolyBeats 稳定回 BTC/ETH/SOL/HYPE netflow）|

刷新砍掉首扫的 trader_position + 解锁/财库 query（4h 内增量稀疏）。

**候选数量铁律（刷新模式）**：跑完上述工具后 P0+P1 候选 ≥ 8 才能进 0b；不足则**单独跑 5 个不同 query 关键词**扩窗。
| `followin.metrics` | `query="biggest gainers" / "top losers", asset_type="tradfi", categories=["market"], min_market_cap=1000000000` — 4h 内涨/跌榜（可选，财报周必跑）|

> v2.1.1：tradfi news 仅返回标题（FMP 通道）。需要正文 → 改 `news(query="<事件>")` 不传 asset_type。突发事件 / C 入口才走 query 路径（如 `"DeepSeek"` / `"Hormuz"`）。
> ⚠️ 实测有偶发 `results=null`，触发 fallback：改 `news(query="stock market earnings Fed", verbosity="concise", limit=15)` 重试。

#### 🏛️ 跨市场价格快照（v1.6，v2.1 单次调用）

| 工具 | 参数 |
|------|------|
| `followin.metrics` | 油+美元：`keywords=["CLUSD","DXY"], asset_type="tradfi"`；金另调 `keywords=["XAUT"], asset_type="crypto"`（裸 gold/oil 会拿到金矿股/牙膏股，见 quirk⑨）|

> 实战教训：油价破 $100 / DXY 破 98 / 黄金回探都是当日跨市场风险开关，"日内变化不大"的假设会让刷新简报漏掉宏观主线。v2.1 由 `followin.metrics` 单次返回。

**🚫 刷新模式不跑**（v2.1.6 — `signal` 全部砍）：
- Wave 1 popularity 热门榜（首扫已覆盖）
- economic_calendar / 国债收益率 / metrics(keywords=["spx"])（跨市场看 DXY/oil/gold 即可）
- 候选池兜底等级 2 的 `followin.twitter(action="search")`（仅低候选时调）
- **`followin.signal` 全 4 个 category（kol_call / trader_position / insider_trading / institutional）全部不跑**
  - `trader_position` 4h 内同地址重复污染（实测 1 倍杠杆原油 4h 内 11 条加仓 / 麻吉大哥 4-7 次 ETH 多调整都是 spam 级）
  - `kol_call` 4h 内信号稀疏（<6 条），且已被 TG 频道扫描"交易信号"/"实盘跟踪" cat 覆盖
  - `insider_trading` / `institutional` 数据日级别变化，4h 无增量
  - **特殊情况例外**：用户明确说"看鲸鱼" / "看议员交易" 才单独跑 signal

**增量过滤铁律**：每次刷新结束写 `/tmp/trend-scout-last-refresh-YYYY-MM-DD.txt`，下次读取并按上表的 `last_refresh_ts` 字段过滤，避免"刷新读到首扫已读内容"的硬伤。

### 推特 L1 排序规则（刷新模式核心）

纯 `engagement DESC` 在 4h 窗口会压制新推（3-4h 老推累积互动 vs 30min 新推零互动），刷新和首扫严重 overlap，失去追增量意义。

**双轨制**：
- 🅰️ **Velocity 轨**：`(likes + 2×rt + 0.5×reply) / max(hours_since_post, 0.25)` 降序，取 top 7
- 🅱️ **Recency 轨**：`createdAt` 降序，取 top 3
- **绝对保护**：`createdAt` 在过去 **30 分钟内**的推文，无论 velocity 多低都必须进候选池
- 合并去重，最终 10 条

⚠️ **list_timeline schema 限制**：`followin.twitter` 只接受 `list_id` + `cursor`，**不接受时间窗参数**（与旧 MCP 一致）。Agent 子进程必须自己按 `createdAt > last_refresh_ts` 过滤。

#### Agent 子进程 Prompt 模板（必用）

```
调用 followin.twitter(action="list_timeline", list_id="<LIST_ID>")，对返回的推文按以下规则筛选 top 10：

1. 时间过滤：createdAt > <LAST_REFRESH_TS>（unix 秒）— 早于此时间的全部丢弃
2. 双轨制：
   - Velocity 轨：(likes + 2*retweets + 0.5*replies) / max(hours_since_post, 0.25) 降序取 top 7
   - Recency 轨：createdAt 降序取 top 3
3. 绝对保护：createdAt 在过去 30 分钟内的推文，无论 velocity 多低都必须保留
4. 合并去重，输出 10 条 — 每条只回传：text、author、likeCount、retweetCount、replyCount、viewCount、createdAt、tweet_url

不要按 engagement DESC 排序。不要返回 full_content / 媒体链接 / 完整 raw json。
```

直接把 LIST_ID 和 LAST_REFRESH_TS 替换到 prompt 里。三栈 list 各跑一次。

### 输出格式（v2.2 — 撤改补三件套统一）

**首扫 + 刷新通用主报告**（见第 0b 步 "输出格式" 详细模板）：

```
═══ 风向标 [首扫/刷新] 日报 — [时间戳 UTC+8] ═══

🆕 必须补充（首扫 ≥12 / 刷新 ≥8，按 A+B+C+D 总分降序）
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
- 🆕 候选数 < 目标 → 必须先扩窗重扫（扩窗后仍不足则如实报干轮）
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

## 第 0a 步：拉过去 24h 已建话题（去重对照）

**所有候选池**（首扫/刷新/检索）进入评分**前**、向用户**展示推荐选题前** — 都必须先调用：

```
list_trending_topics(start_date=昨日, end_date=今日, limit=80)   # 不传 status，覆盖 0/1/2/3 全状态
```

> ⚠️ **v1.7 规则收紧（2026-05-06）**：
> - **窗口**从"今日"扩到**过去 24h 滚动窗口**（昨日 + 今日 → 客户端再按 `created_at >= now - 24h` 过滤）
> - **状态**从 `status=0` 扩到**全状态**：
>   - `status=0` 正常上线 → 选题位已占用
>   - `status=2` 审核中 → 同样占用，避免重复建
>   - `status=1` 初始化 → 已建未发，仍是占用
>   - `status=3` 已隐藏 → 标记为"曾经建过"，新建前需说明差异化角度
> - **铁律**：**任何向用户输出的"推荐选题列表"前**，必须先跑这一步并在简报里展示 🟰 / 📈 / 🆕 三类标记，不允许跳过。

### 输出顺序（v2.2 — 撤改补三件套）

```
1. 调 list_trending_topics(过去 24h, 全状态)
2. **建索引**：按 symbol / keyword / event_type 分桶（供差异化前置判断）
3. 候选 vs 已建做一一比对，每条候选标注：
   - 🟰 重叠已建（不重建）/ 与 ID xxxx 的事件维度差异
   - 🔧 升温更新（已建话题数据脱锚 ≥10%）
   - 🆕 新建候选（带 vs 已建 ID 的差异锚点）
4. 输出三件套主报告（v2.2）：
   - 🆕 补充（首扫 ≥12 / 刷新 ≥8 条）
   - 🔧 更新
   - 🚨 撤回（含 0a.5 输出）
   - 🟰 已建覆盖（精简）+ 📊 数据（折叠）
```

### 0a 索引建立（v2.2 新增 — 差异化前置）

拉到 list 后，按 3 个维度建索引：

```python
existing_topics_index = {
    "by_symbol": {"BTC": [8915, 9114, 9120, 9129], "ETH": [9111, 9131, 9133], ...},
    "by_keyword": {"CLARITY": [8975, 9109], "CPI": [8965], ...},
    "by_event_type": {
        "price_breach": [8915, 9129],     # 价格突破/跌破
        "etf_flow": [9111, 9114],         # ETF 资金流
        "whale_action": [9115, 9131],     # 鲸鱼/链上转账
        "earnings": [8957, 9019],         # 财报
        "regulation": [8975, 9012, 9020], # 监管立法
        "listing": [9007, 9008, 9039],    # 上币/下架
        "macro": [8965, 9022]             # 宏观数据
    }
}
```

每条新候选评分时，**先查索引 → 得到 C 稀缺性分**：
- 同 symbol + 同 event_type ≥3 条 → C=0
- 同 symbol 或 同 event_type 1-2 条 → C=1
- 完全无重叠 → C=2

### 去重判定

| 重合判定 | 标记 | 处置 |
|----------|------|------|
| 标题/keywords 与已发布**完全同主题**（同代币 + 同事件） | 🟰 重叠已发 | **不重建**；有新数据建议 `update_trending_topic` |
| 同标的但**事件维度不同**（已发"X 上线"，候选是"X 链上巨鲸异动"） | 🆕 可建 | 保留进评分 |
| **完全新事件** | 🆕 可建 | 保留进评分 |
| （刷新模式额外）首扫已有但价格/持仓有重大新进展 | 📈 升温 | 建议 update 而非新建 |

仅 🆕 可建 进入第 0b 评分。

### 🚦 升温硬规则（v1.9 升级 — >25% 自动撤回）

**⏰ v2.2.6 适用范围铁律**：升温硬规则**只适用于「过去 24h 内创建」的 status=0 话题**。

| 话题年龄 | 数据脱锚处置 |
|---------|------------|
| **≤ 24h** | 走下方升温硬规则（update title / 撤回）|
| **> 24h（老话题）** | **不 update 老话题**，老话题保持历史原貌；当前行情 → **新建一条话题** |

> 理由：老话题已积累自己的 heat / source_count，强行改标题追新价会破坏历史一致性。当前行情应由**新话题**承接（例：8864 ZEC 5/9 建 $604，5/21 ZEC $678 时应新建 9213，而非改 8864）。

去重时若 🟰 重叠已发的话题（**且 ≤24h**）主标的当日涨幅 vs **创建时**已偏差 ≥ **10%**（绝对值），**必须**主动处置：

| 偏差幅度 | 操作 |
|---------|------|
| ≥ 10% 但 ≤ 25% | 必须 update title（数据点更新到当前值）+ keywords 不变 |
| **> 25%** | **自动判定主体不成立 → 直接 `status=3` 撤回**，进入用户复审池而非线上 |
| **> 50% 反向**（"暴涨"→"暴跌" 或反之） | **强制撤回，无需复审**（标题完全脱锚） |

**实战例**：8789 PLAY 建时 +40.2% → 刷新 +1.5%（偏差 38.7%>25%）→ 自动撤回；8775 LAB 建时"暴跌"→ 刷新 +63%（反向脱锚）→ 强制撤回。

**铁律**：
1. desc 不可改 → >25% 偏差就只能撤回，"提示用户复审"是延迟动作，绝不允许让脱锚话题继续挂在线上
2. 不允许"保留旧数据 + 不 update + 直接跑下一个候选"的处置——会让线上持续显示陈旧数字
3. 自动撤回执行后必须在简报里告知用户："已撤回 ID=xxxx 因 >25% 偏差，原数据 X → 现 Y"

---

## 第 0a.5 步：过去 8h 审核中话题预过滤（v1.8 新增 — 2026-05-07）

> **立意**：很多自动入池的 status=2 审核中话题质量参差，得在新建候选之前先把它们梳一遍——能优化的优化、不达标的撤回、强候选的优先发布——避免新建话题挤掉已有的强素材。

### 触发条件

每次扫描热点完成（首扫 / 刷新 / 检索）后，**第 0a 拉到的列表里**只要有 `status=2 审核中` 且 `created_at >= now - 8h` 的话题 —— **必须先走 0a.5**，再进 0b。

### 三档处置

| 决策 | 处置 |
|------|------|
| 🔴 **撤回** | `update_trending_topic(status=3)` |
| 🟠 **优化后发布** | `update_trending_topic(new_title, keywords)` 再 `status=0` |
| 🟢 **直接发布** | 标题/数据均符合 → `status=0` |
| 🟡 **保留观察** | 主体待核（单源未核 / 数据待验） → 保留 status=2，标注"待核"原因 |

### 撤回判定（v1.9 — 按类型分级，任一即撤回）

**类型 × 金额 × 锚点 三维矩阵**（替代单一金额阈值）：

| 类型 | 必撤阈值 | 加权放宽 | 加权收紧 |
|------|----------|---------|---------|
| **链上转账 / 鲸鱼动作** | < $1M | 含可识别身份（"内幕鲸鱼" / 官方地址 / 知名 KOL）→ 阈值降至 $200K | 匿名地址 → 阈值升至 $5M |
| **融资 / 收购** | < $20M | 含 a16z / Paradigm / Sequoia / Multicoin 等顶级 VC 领投 → 降至 $5M | 二线 VC + 无代币锚点 → 升至 $50M |
| **持仓变动 / 财库** | < $5M | 美股财库类（MSTR / Strategy 等） → 降至 $1M | 普通公司财库 → 升至 $20M |
| **上币 / 上线** | 任何金额 | — | 但必须 24h 内有 **具体涨跌幅**（≥ ±10%） |
| **财务事件**（财报 / 亏损） | 无 | — | 需 ≥ $1B 总规模 **或** ≥ 50% 同比变化 |
| **安全事件 / 漏洞** | < $1M | 头部协议 / 知名项目 → 阈值降至 $500K | — |

**其他撤回判定**：

- **空话标题**：触禁用词（"全解析" / "值得关注" / "速来" 等）或无具体标的
- **双轴硬不达标**：A=0 且 B=0（套 0b 双轴 mini 评分）
- **触发升温硬规则 >25% 偏差**：主体 narrative 已不成立 → desc 不可改 → 自动撤回（与 0a 升温硬规则联动）
- **反向脱锚**："暴涨"已变"暴跌"或反之 → 无条件强制撤回
- **多源核验失败**：宣称的关键数据（涨幅 / 上线 / 合作）查不到第二源
- **一票否决**：含政治站队 / 投顾 / 未证实重大指控 / 数据硬错（继承 0b 一票否决条款）

**实战判例**：8801 OpenTrade $1700万融资 → 二线 VC（Mercury/Notion）未达升档后的 $50M → 撤；8782 LAND 含贬义指控 + 单源 → 一票否决 + 多源失败 → 撤。

### 优化后发布判定

- 标题 > 25 字 → 必须压缩
- 标题里数字与扫描到的最新值有偏差但 ≤ 10% → 可保留原标题；> 10% → 改数字
- 主体正确但缺关键维度（如鲸鱼对赌 / 跨市场联动 / 抛压预警）→ 加进 title
- keywords 含项目全称（"WorldLibertyFi"）应改成代币符号（"WLFI"）— 避免 tag 自动匹配失败

### 输出格式（v1.9 — P0/P1/P2/P3 优先级排序）

```
🟡 过去 8h 在审池预过滤（共 N 条）

🚨 P0 必撤（X 条）  ←— 立即执行，无需复审
- ID 标题 — 撤回原因（类型/阈值/锚点）

🔥 P1 优化后发布（Y 条）  ←— 按操作复杂度升序
[仅改 keywords]
- ID 原 keywords → 新 keywords
[仅改 title]
- ID 原标题 → 新标题（含理由）
[改 title + keywords]
- ID 原 → 新 + keywords 调整

✅ P2 直接发布（Z 条）  ←— 一键全发
- ID 标题 — 主体/数据/格式均符合

🔍 P3 待核观察（W 条）  ←— 注明待核工具
- ID 标题 — 待核维度 + 推荐 verify 工具（multi-source / price / event）
```

**P1 内部排序铁律**：把"操作复杂度低"的放前，让用户能快速一键批准简单 update（仅改 keywords / 仅改 title），把复杂的（改 title + keywords + tags）放后单独审核。

**P2 直接发布判定 checklist（5 项全 ✅）**：
- ☐ title ≤ 25 字
- ☐ 主体明确（一眼看出什么币/什么事）
- ☐ 含具体数据点（价格 / 涨幅 / 金额 / 持仓）
- ☐ 不触禁用词
- ☐ 数据/动作前置（不"XX 升温"开头）

### 与 0a 升温硬规则的区别

| 步骤 | 对象 | 操作 |
|------|------|------|
| 0a 升温硬规则 | **status=0 已发布**话题，主体仍成立但数据偏差 ≥10% | update title 同步数据 |
| 0a.5 预过滤 | **status=2 审核中** 8h 内话题，可整体重判 | 撤回 / 优化发布 / 直接发布 / 保留观察 |

### 流程位置

0a.5 跑完之后再进 0b 双轴评分新建候选——这样新建池才知道"已经有哪些今日强候选已上线"，避免重复创建相似主题。

---

## 第 0b 步：四维评分（v2.2 — 加稀缺性 + 紧迫性）

热点风向标本质：**对市场行情影响大** 或 **大家讨论度高** 的热点。
准入采用**四维评分**（A/B/C/D），主轴 max(A, B) ≥ 2 才进入排序。

### 🕒 0b.0 时效性硬过滤（v2.2.8 — 评分前必跑）

**铁律**：任何候选进入 A/B/C/D 评分前，必须先核实**核心数据点的 published_ts**——而不是事件本身是否仍"在演进"。

| 模式 | published_ts 上限 | 处置 |
|------|-----------------|------|
| 🟢 首扫 | ≤ 24h（即 `now - 86400`）| 超期 → ❌ 直接剔除候选池 |
| 🔵 刷新 | ≤ 4h（即 `now - 14400`）| 超期 → ❌ 直接剔除 |
| 🔴 突发 | ≤ 2h | 超期 → ❌ 直接剔除 |
| 🔍 C 入口检索 | ≤ 1d（默认）| 用户指定窗口为准 |

**核实方法**：
1. 候选数据来源（news.published_ts / TG.published_ts / twitter.createdAt）必须有 unix 时间戳
2. 计算 `(now - published_ts) / 3600` 得到小时差
3. 多源时取**最新**那条作为锚（不是平均）

**两种典型违规（v2.2.8 实战教训）**：
- ❌「Saylor 说本周买债券非 BTC」首扫时已 24h+，被用户标"时效问题"——单源 published 5/24，5/26 首扫不应进表
- ❌「中本聪 OG 抛 2650 BTC」5/25 数据，5/26 首扫已 36h+，应直接砍

**例外（仅 1 类可豁免）**：
- 当前 **status=0 已上线话题的升温/反转**——属于 0a 升温硬规则范畴，不走 0b.0

> 「事件还在演进」不是豁免理由。如果今天有新发展应该用**今日的新数据点**重建候选；只有旧 published 信源 → 直接砍。

### A. 行情冲击力（0-3）

| 分 | 标准 |
|---|------|
| 0 | 无市场影响（纯娱乐八卦） |
| 1 | 间接传导（≥2 跳，需读者推理） |
| 2 | 直接影响某板块/标的（加密/美股/大宗/外汇/利率） |
| 3 | 全市场级冲击（BTC/ETH/大盘/全板块联动） |

### B. 讨论热度（0-3）

| 分 | 标准 |
|---|------|
| 0 | 无人关注 |
| 1 | 小圈层冷门讨论 |
| 2 | 圈内热议（多平台/多 KOL 转发） |
| 3 | 全网爆款/出圈（跨圈层刷屏） |

### C. 稀缺性（0-2）— v2.2 新增

**衡量"该补这条话题的紧迫度"**：已建话题池里同主题密度越低 → 分越高。

| 分 | 标准 | 检查方法 |
|---|------|---------|
| 0 | 同主题已建 ≥3 条 status=0 | 在 0a 索引里按 symbol/keyword grep |
| 1 | 同主题已建 1-2 条 | 同上 |
| 2 | 该主题完全未建 / 角度差异 ≥80% | 同上 |

### D. 紧迫性（0-2）— v2.2 新增

**衡量"等多久会失效"**：

| 分 | 标准 |
|---|------|
| 0 | 长效话题（解锁周期 / 13F / 季度财报）— 24h+ 仍有效 |
| 1 | 12-24h 内最佳窗口（财报次日 / 升温事件） |
| 2 | < 4h 必须建（链上突发 / 政策快讯 / 财报当时 / 巨鲸异动） |

### 综合评分 = A + B + C + D（总分 0-10）

**补充优先级排序**：
- **总分 ≥ 8** → P0 必建（顶优先级）
- **总分 6-7** → P1 强建议建
- **总分 4-5** → P2 待选（看候选池容量）
- **总分 < 4** → ❌ 不建

### 辅助维度（标注但不入综合分）

- **信号强度**：是否有具体价格/金额/地址/持仓数据
- **多源验证**：单源 / 双源 / 三源以上
- **独特角度**：通稿味 / 主流叙事 / 独家视角

### 一票否决（任一即拒绝，不论分数）

- 标题/描述含**明确政治立场或煽动性表达**（仅客观叙述事件 + 写明市场传导路径**不算**站队）
- 含**未经证实**的重大指控
- 含**投顾性质**操作建议（"该买/该卖/目标位"）
- 数据有明显**造假/逻辑硬伤**

> 关键区分：宏观/地缘/美股/AI 议题本身不是禁区，写法客观就放行。被否决的是**写法**，不是**主题**。

### 候选池数量目标（v2.3.2 — 目标值，非灌水门槛）

| 模式 | P0+P1 目标数 |
|------|-----------------|
| 🟢 首扫 | 12 条 |
| 🔵 刷新 | 8 条 |
| 🔴 突发 | 3 条 |

**这是"先扩窗扫够再下结论"的目标，不是"凑数发布"的门槛。** 流程：

1. **先扩窗**（达不到目标时，必须先做完才能说"不够"）：
   - 扩 `news(query=...)` 多组关键词（链上 / 上币 / 解锁 / 财库 / 鲸鱼）
   - TG 加 cat（链上数据 / 叙事追踪）；确认执行清单无跳波
2. **扩窗后仍不足** → **如实报"干轮"**：列出真实强候选（哪怕 2-3 条），写明"已扩窗，当日增量稀薄"。
   - 🚫 **禁止**为凑数把 P2 噪音抬进 P0/P1，或硬报"0"不扩窗——这两个都是错的。
   - ✅ 正确 = 扩窗尽力 + 诚实呈现真实候选数（行情确实清淡时，3 条强候选 > 12 条注水）。

### 输出格式（v2.2.2 — 三张表标准模板）

主报告 = **三张独立表 + 已建覆盖 + 实时数据折叠 + 一键行动**。

#### 🎯 v2.2.9 简化原则（每次报告必遵守）

**简报只聚焦 4 类内容**，其余 **不提**：

| 类别 | 范围 | 处置 |
|------|------|------|
| 🆕 今日新候选 | 24h 内 published 信源 | 进表 1 |
| 🔥 今日刚建话题 | ≤24h 创建（status=2/0）| 进表 2/3 处置 |
| 🔧 必须 update | 触发 v2.2.6 升温硬规则（≤24h status=0 数据偏差 ≥10%）| 进表 2 |
| 🚨 8h 在审池 | created_at ≥ now - 8h 且 status=2 | **每次报告强制扫描并列出处置（必出现在表 3）**|

**不提 / 不 push 的**：
- **status=0 已上线** 且 **>24h 老话题**：不动、不 update、不提（除非反向脱锚 >50% 强制撤）
- **status=2 审核中** 且 **>8h 创建**：从简报剔除、不再 push 发布
- **status=3 hidden** 已被团队过滤的话题：不重建、不分析

#### 🪦 v2.3.0 自动撤回铁律（status=2 时效过期）

**每次扫描必跑**：拉 status=2 全集合，凡 `created_at < now - 86400`（>24h 仍未发布）→ **自动 `update_trending_topic(status=3)`**，无需用户确认。

| 触发条件 | 操作 |
|---------|------|
| status=2 且 created_at >24h | 🪦 撤（status=3）|
| status=2 且 created_at ≤24h | 走 0a.5 处置流程 |

**🚦 规模闸（v2.3.2）**：
- 命中 **≤ 10 条** → 直接自动撤，简报告知。
- 命中 **> 10 条** → **先汇总成清单（ID + 标题 + created_at）报给用户确认**，再批量撤。理由：积压一旦上量（实测一次 86 条），无确认批撤有误杀风险；列清单确认成本低、可逆性差的操作值得这一步。

**理由**：审核中超 24h 未发布 = 已被搁置，保留只会让列表越滚越长。撤后历史仍可由 list 查询，无信息丢失。

**执行频率**：每次首扫 / 刷新开始时跑一次（在 0a 拉列表后立即清扫，再进 0a.5）。

**目的**：简报只承载今日可决策内容，避免老 backlog 噪音。

```
═══ 风向标 [首扫/刷新] 日报 — [YYYY-MM-DD HH:MM UTC+8] ═══

## 🆕 表 1：必须补充（共 N 条；vs 目标 ✅达标 / ⚠️已扩窗仍干轮）

| 优先级 | R# | 标题 | A | B | C | D | 总 | 差异化 vs 已建 | keywords | 备注 |
|--------|----|----|---|---|---|---|---|-------------|---------|------|
| **P0** | R1 | [标题草稿 ≤25 字] | 3 | 3 | 2 | 2 | **10** | 无重叠 / vs 8915 主体不同 | `BTC,比特币,Iran` | <4h 时效 |
| **P0** | R2 | … | 2 | 2 | 2 | 2 | **8** | … | … | … |
| P1 | R3 | … | 2 | 2 | 1 | 2 | 7 | … | … | … |
| P1 | R4 | … | … | | | | … | … | … | … |
| P2 | R5 | … (候选池容量允许才建) | … | | | | … | … | … | … |

## 🔧 表 2：必须更新（共 M 条）

| ID | 当前标题 | 改为 | 原因 | keywords 改动 |
|----|---------|------|------|-------------|
| 8915 | 旧标题 | 新标题 | 升温脱锚 -X% / 事件升级 / 数据陈旧 | 维持 / 加 / 改 |

## 🚨 表 3：撤回 + 在审池处置（共 K 条）

> **v2.2.9 强制铁律**：每次报告必须扫描 `created_at ≥ now - 8h 且 status=2` 的话题，逐条给出 ✅发 / 🟠改 / 🚨撤 / 🟡待核 决策，**不留空**。这是表 3 的核心职责。

| 动作 | ID | 标题 | 原因 / 处置 |
|------|----|----|-----------|
| 🚨 撤 | xxxx | … | 反向脱锚 / 重复 / 弱主体 / 类型阈值 / 时效过期 |
| ✅ 发 | xxxx | … | status=2 → 0 直发（数据齐全）|
| 🟠 改 | xxxx | … | 标题/keywords 调整后再发 |
| 🟡 待核 | xxxx | … | 数据需第二源核 / 行情关联待观察 |

─────────────────────────────────────────

## 🟰 重叠已建（不重建，反证差异化）

ID 列表，按主题聚类列出，注明已覆盖的事件维度。

## 📊 实时数据（fold 收起）

加密：BTC $X (±%) / ETH $X (±%) / ...（10 币）
美股：（首扫含 13 股，刷新可略）
跨市场：SPX / 黄金 / 油 / DXY

---

## 📋 一键行动

```
🚨 P0 全建 (N)：R1 / R2 / ...
🟠 P1 建 (M)：R3 / R4 / ...
🔧 update (K)：xxxx
🚨 撤 (J)：xxxx
✅ 发 (I)：xxxx
🟠 改 (H)：xxxx
```
```

### 三张表设计原则（v2.2.2）

1. **每张表独立，可单独阅读** — 用户只想看"今天该建什么"时只看表 1
2. **每条候选必含 7 列**：优先级 / R# / 标题 / A/B/C/D 评分 / 总分 / 差异化锚点 / keywords / 备注
3. **总分排序** — A+B+C+D 降序，自然把 P0 顶到前面
4. **差异化锚点必填** — 显式标注 vs 已建 ID + 事件维度差异
5. **一键行动作收尾** — 把所有动作按类型汇总，方便"全跑"

### 何时合并 / 何时拆分

- 候选 < 5 条 → 三张表合并为一张（紧凑模式）
- 候选 ≥ 5 条 → 三张独立表（详细模式，默认）
- 突发事件 < 4h → 简化为"主报告卡片"，只列 P0 候选 + 紧急 update

---

## 第 1 步：字段提取

### title — 必走「标题优化方法论」

**硬约束**：
- ≤ 25 字
- 数据/动作前置，不铺垫
- 主体明确（一眼看出什么币/什么事）
- 最多一个分句

### 🔤 中英混杂规则（v2.2.1 新增）

**默认中文写作**，仅以下情况允许英文：

✅ **允许英文（专有名词）**：
- 代币 / 股票符号：BTC、ETH、NVDA、AAPL、CRCL、HYPE、SUI、PPI、CPI
- 公司 / 项目名：Apple、Google、NVIDIA、Coinbase、Circle、ShapeShift、Tether
- 政策 / 法案名：CLARITY、GENIUS、FOMC
- 国际机构 / 交易所：Fed、SEC、BlackRock、Binance、Bithumb、KOSPI
- 人名：Trump、Putin、Powell、Warsh、Saylor、Cathie Wood
- 单位 / 符号：$、%、Q1、ATH、ETF、IPO、HBM、GPU

❌ **禁止英文（动词 / 形容词 / 状态词）**：
- ~~risk-off~~ → 避险 / ~~risk-on~~ → 风险偏好回暖
- ~~markup~~ → 审议 / ~~beat~~ → 超预期 / ~~miss~~ → 不及预期
- ~~liquidation~~ → 爆仓 / ~~inflow~~ → 净流入 / ~~outflow~~ → 净流出
- ~~bullish~~ → 看多 / ~~bearish~~ → 看空 / ~~rally~~ → 反弹
- ~~halt~~ → 停盘 / ~~delist~~ → 下架（如非交易所操作可保留 listing/delisting）

**判定铁律**：英文词如果能用 2-4 个中文字替代且不丢精度 → 必须替换；如果是行业内必须保留原文的术语（如 `Stablecoin Bill` / `13F`）→ 保留。

### 🎯 表达三要求（v2.2.1）

每个标题必须同时满足：

1. **清楚** — 不读 desc 就能看明白主体、动作、数据点
   - 好：`NVDA 4 天市值新增 1 个 Oracle，盘中破 $222 创新高`
   - 坏：`NVDA 摸 $222 创年内新高，AI 反扑带飞 TSLA +3.89%`（"反扑带飞"模糊）

2. **吸引力** — 必须有至少一个**吸睛点**：
   - 量级反差（"4 天 = 1 Oracle 市值" / "彩票流 +73 万倍"）
   - 戏剧性（"V 形反转" / "失守 $80K" / "财报日 +16%"）
   - 人物钩子（"黄仁勋随访华破局" / "Cathie Wood 喊 $150 万"）
   - 极端数据（"24h +263%" / "3 年新高" / "54-45 最分裂投票"）
   - 板块/标的并列（"AAPL 破 $300、NVDA $227、GOOGL $403"）

3. **精度** — 数据点必须精确到具体值，禁止"暴涨/暴跌/大涨/急跌"等无具体值表达（除非已有具体值 + 形容词作辅助）
   - 好：`SOL/HYPE 跌超 4%` / `4h 全网爆仓飙至 $5.79 亿`
   - 坏：`SOL/HYPE 大跌` / `爆仓潮涌现`

详见下文「标题优化方法论」。

### keywords（v2.1.2 — 加中英文别名）

keywords 同时承担两个职责：
1. **自动匹配 tag**（只看 ticker / 代币符号）
2. **内部搜索发现**（用户用中英文项目名搜索话题时命中）

因此 keywords 应分两档：

**第一档：ticker / 代币符号（必含 1-2 个）** — 触发自动 tag 匹配
- 加密：全大写代币符号（BTC、ETH、AAVE、HYPE、CRCLX、NVDAX 等）
- 美股 / 跨市场：股票符号本身（NVDA、CRCL、TSLA、COIN、MSTR 等）

**第二档：项目英中文别名（建议 1-3 个）** — 提升搜索发现
- 项目英文官方名（NVIDIA / Circle Internet Group / Apple / Tether）
- 中文常用名（英伟达 / 苹果 / 比特币 / 以太坊 / 黄金）
- 强相关具体概念名（USDC / CPI / PPI / 通胀 / 加密概念股 等）

**🚫 禁用笼统统称**：`山寨币` / `加密` / `加密货币` / `概念` / `板块` / `代币` / `数字资产` / `市场` 等过于宽泛的词不进 keywords。搜索价值低且污染 tag 关联。

**总量控制**：3-5 个（ticker 1-2 + 别名 1-3）；英文逗号分隔

**实战例**：
| 主标的 | keywords |
|--------|---------|
| NVDA AI 反扑 | `NVDAX,NVDA,NVIDIA,英伟达` |
| CRCL 财报 | `CRCLX,CRCL,Circle,USDC` |
| AAPL 财报 | `AAPLon,AAPL,Apple,苹果` |
| TSLA 拉升 | `TSLAX,TSLA,Tesla,特斯拉` |
| INTC × Apple 代工 | `INTC,Intel,英特尔,Apple,苹果`（INTC 无代币化版） |
| BTC 8.2万 | `BTC,比特币,Bitcoin` |
| ETH 巨鲸转账 | `ETH,以太坊,Ethereum` |
| 黄金 ATH | `XAUT,PAXG,黄金,Gold` |
| 美联储 / 利率 | `BTC,比特币,美联储,Fed,利率` |

> ⚠️ **铁律**：第一档 ticker 必含且**不超过 2 个**，避免 tag 关联过多冲淡主体；第二档别名是辅助，不要堆砌（≤3 个）。

### 宏观/跨市场话题的代币映射（v2.1.2 — 美股优先走代币化股票 tag）

| 宏观主题 | 优先 keywords（ticker） | 别名（中英文） | 已知 tag id |
|----------|---------------------|-------------|------------|
| 黄金 / 金价 | `XAUT,PAXG` | `黄金,Gold` | XAUt: 10226 |
| 原油 / 石油 | `OIL` | `原油,WTI,Brent` | CRUDE OIL BRENT: 520979 |
| **美股 / 个股** | **代币化股票优先**（`NVDAX,CRCLX,AAPLon,TSLAX,GOOGLX,COINX,MSTRX` 等） | 原股票符号 + 项目中英文名 | NVDAX: 522527, CRCLX: 522611, AAPLon: 546230, INTC: 548353；其余调 `followin.metrics(keywords=["XXXX","XXXon"])` 查 |
| **港股 / 中概** | 股票符号或港股代码（`9988,3690,9618` 或 `BABA,JD,PDD`） | 公司中英文名 | 多数无挂钩代币 → `followin.news(query=代码)` 查；无则 fallback BTC/ETH |
| AI 板块 | `WLD,FET,RNDR,TAO` 选 1-2 | `AI,人工智能` | WLD: 248008, FET: 10201 |
| 外汇 / DXY | 涉事货币挂钩代币 | `美元,DXY,USDT` | — |
| 美债 / 利率 / FOMC | `BTC` 或 `ETH`（风险资产联动） | `美联储,Fed,利率` | BTC: 10006, ETH: 10007 |
| 联储/CPI/非农/纯宏观 | `BTC` 或 `ETH` | `CPI,通胀,非农` | 同上 |

**判定流程（必按顺序）**：
1. **优先查代币化股票（XXX + X / on 后缀）** —— 美股 ticker 加 `X` 或 `on` 试调 `followin.metrics(keywords=["NVDAX","NVDAon"], asset_type=不传)`，命中则用代币化 ticker 做 tag
2. 无代币化股票 → 用原股票符号 + 手动绑 tag id（如 GOOGL → 522630）
3. 无挂钩但与某加密板块强联动 → 用板块代表代币
4. 纯宏观无板块联动 → 用 BTC / ETH

> ⚠️ **铁律**：第 1 档代币化股票判定**必须先做**。
> - ✅ 成功案例（v2.1.2）：8957 CRCL 财报 → `CRCLX (522611)`；8958 NVDA 新高 → `NVDAX (522527)`
> - ❌ 失误案例：8581 Google 财报误用 WLD/FET（板块代表），实际应当用 `GOOGLX` 或 `GOOGL` + 手动绑 522630

### desc（v2.1.1 — 创建时不写）

- **创建话题不传 desc**（`create_trending_topic` 调用时省略 `desc` 字段）
- 理由：desc 后续无法 update（`update_trending_topic` 不支持改 desc），且话题前台展示主要靠 title + tag + keywords，desc 只增加创建摩擦
- 历史背景信息全部压进 title（≤25 字硬约束）+ keywords 即可

### topic_type

- **0 = 主流币**：BTC/ETH 或以其为核心的衍生议题、宏观风险资产联动
- **1 = 山寨币**：已上主流交易所的非 BTC/ETH 代币（SOL/AAVE/HYPE 等），或链上正式项目
- **2 = meme 币**：纯社区驱动、无团队/白皮书背书的链上 meme

> 边界：有官网+团队+白皮书 → 山寨；纯社区驱动 → meme

---

## 标题优化方法论

### ⚓ 第一原则：市场锚点优先

每个标题必须能回答：**「这件事对持仓/下单意味着什么？」**

主轴优先级：
1. 价格 / 涨跌幅
2. 持仓 / 资金动作
3. 多空 / 板块分歧
4. 政策/事件冲击（仅当能直接传导）
5. 故事/人物钩子（只能作辅助修饰）

### 5 风格变体（全部需锚定市场）

| 风格 | 套路 | 示例 |
|------|------|------|
| **数据驱动** | 价格/涨跌/金额/资金流前置 | "AAVE 流出 3 亿，13 协议联合补血" |
| **多空分歧** | 仓位对立、板块对立 | "BTC 跌破 77K，鲸鱼仓位现罕见多空对立" |
| **行情传导** | 事件 → 价格/板块影响 | "霍尔木兹封锁升级，加密 risk-off 传导" |
| **持仓变化** | 鲸鱼/聪明钱具体动作 | "麻吉加多 BTC 4290 万，欧阳同日翻空" |
| **板块信号** | 板块轮动、资金面、解锁/清算 | "BTC 多盈 vs HYPE 空亏：主流山寨分歧" |

### 评分维度（每项 1-10，总分 ≥ 32 才能用）

- **吸引力**：3 秒抓眼能力
- **差异化**：与同题材通稿的区分度
- **时效性**：事件新鲜度的呈现
- **专业感**：避免标题党廉价感

### 加密圈层字典

| 类别 | 词库 |
|------|------|
| **角色** | 合约党 / 链上玩家 / L1 鲸鱼 / Maxi / 散户 / 聪明钱 / 多头 / 空头 / OG |
| **行情场景** | 插针夜 / 暴跌时 / 新高夜 / 横盘期 / 解锁日 / CPI 前夜 / 减半季 |
| **情绪** | 罕见对立 / 集体打脸 / 多空血战 / 真香 / 连环爆仓 / 一致性 / 分歧加剧 |
| **行动** | 翻空 / 加仓 / 砸盘 / 死扛 / 出清 / 解锁 / 增持 |

### 🚫 禁用词

- **合规雷区**：百倍 / 必涨 / 翻倍 / 财富自由 / 上车 / 抄底 / 暴富 / 稳赚
- **标题党**：速来 / 必看 / 速领 / 独家 / 首发 / 最强 / 最全
- **低俗/敏感**：性暗示 / 死亡威胁 / 央行直接对照 / 政治站队
- **空话**：值得关注 / 不容错过 / 重磅来袭

### 数字与单位格式（标题/desc 通用）

| 类型 | 标题 | desc | 反例 |
|------|------|------|------|
| 金额 ≥ 10K | 中文万/亿（"4290 万"） | 可中英混（"$42.9M / 4290 万美元"） | ❌ "$4290W" |
| 金额 < 10K | "$8.5K" | 同 | — |
| 涨跌幅 | 百分号（"+82% / -1.86%"） | 同 | ❌ "0.82 倍" |
| 价格 | $ + 数字（"$77,062 / $0.10"） | 同 | ❌ "77K 美元" |
| 代币符号 | 全大写（BTC / ASTEROID） | 同 | ❌ btc/Asteroid |
| 链/平台名 | 首字母大写（Base / Hyperliquid） | 同 | ❌ base 链 |
| 时间窗口 | "24h / 1h / 30min" | 同 | ❌ "24小时" |

预览前**强制走一遍格式扫描**——违反就改。

---

## 第 2 步：预览确认（不可跳过）

```
📋 话题预览
标题：{优化后最强标题}
（备选：{次优 1-2 条}）
关键词：{keywords}
类型：{topic_type_label}（{topic_type}）

确认创建？回复"确认"或"好"即可。
```

**用户确认前不得调任何 MCP 工具。**

---

## 第 3 步：create_trending_topic

确认后调用 `mcp__console-mcp__create_trending_topic`，成功后展示：

```
✅ 话题已创建
ID：{id}
匹配 Tags：{matched_tags}
状态：{status}
```

---

## 第 4 步：tag 命中校验

- `matched_tags` 为空或不准 → 主动用 `update_trending_topic` 修正
- 美股/大宗等"非加密原生标的"应**主动**手动绑 tag（不必等用户提示）

参考：第 1 步「宏观跨市场代币映射」表里的已知 tag id

---

## 🛡️ 第 4.5 步：数据核实（强制，发布前必过）

**铁律**：每条话题创建后、发布前**必须**逐条核对 title 中的所有数据点（v2.1.1：不再写 desc，仅核 title）。**不可跳过**。

### 核实清单

| 数据类型 | 核实方法 | 不达标处置 |
|---------|---------|-----------|
| **价格 / 涨跌幅** | 重新调 `followin.metrics(keywords=[SYMBOL])` 拿最新值 | 偏差 > 0.5% → update |
| **涨跌幅时间窗口** | 检查"X%"前是否标明窗口（24h/周内/月内） | 模糊 → 必须明确 |
| **链上持仓 / 金额** | 时效检查：数据是否仍代表当前状态 | 老数据需标"截至 X 日" |
| **第三方机构数据** | ≥2 源交叉，或注明来源（"据 SoSoValue"） | 单源未标 → 加来源 |
| **KOL 单源观点 / 技术分析** | 必须标注来源（"@xxx 指出..."）或弱化 | 不可作客观事实呈现 |
| **同标的对照数据** | 时间窗口一致 + 不会被误读 | 加时间限定词 |
| **事件被否认/辟谣** | 创建后扫最新 5-10 条快讯 | 有反转 → update 或撤回 |

### 不通过处置

- 🟢 全绿 → 进第 5 步
- 🟡 1-2 处歧义/单源未标 → `update_trending_topic` 修，再进第 5 步
- 🔴 数据硬错 / 事件被否认 → 走「紧急撤回」流程（status=3）

> 与第 5 步区别：4.5 是**事实核实**（客观真假），5 是**发布评估**（主观判断）。互补不可省。

### 🚀 批量数据核实路径（v1.9 新增）

当 0a.5 一次审 ≥ 5 条话题时，**禁止**逐条跑 4.5（每条都调一次 `followin.metrics` 是浪费）。改走批量路径：

**Step 1 批量价格核实**（一次性）：
```
收集所有候选标的的 token symbols（去重 → list）
→ 一次调 followin.metrics(keywords=union_list, asset_type="crypto")
→ 再分发到每条话题做偏差比对
```
- 标的数 ≤ 20 → 一次调用解决
- 标的数 > 20 → 拆成 ≤ 20 的批次，并行调用

**Step 2 批量多源核验**：
```
对所有"宣称 +X% 上线 / 合作"的关键数据
→ 并行调 N 次 followin.news(query=symbol/event_name, time_range="1d", limit=10) 取多源
→ 标"✅ 多源" / "⚠️ 单源未核" / "🔴 多源核验失败 → 走撤回"
```

**Step 3 批量预览矩阵**（合并输出）：

```
📋 批量数据核实矩阵（共 N 条）

| ID | 主体 | 价格核实 | 多源核验 | 时效 | 整体 |
|----|------|---------|---------|------|------|
| 8803 | ETH 内幕鲸 | 🟢 | 🟢 | 🟢 | 🟢 |
| 8797 | Paradigm ETH | 🟢 | 🟡 单源 | 🟢 | 🟡 |
| 8798 | sato +300% | ⚠️ 数据缺失 | 🔴 | 🟡 | 🔴 撤 |
```

**Step 4 一键批量发布**：
- 全 🟢 行 → 一次性 batch update status=0
- 🟡 行 → 单独 update title 后再发
- 🔴 行 → status=3 撤回

> 实战收益：今天 9 条话题严格走单条 4.5 = 约 9 次价格 API + 9 次多源 API ≈ 18 次调用 + 9 轮等待；批量路径 = 1-2 次价格 + 9 次并行多源 ≈ 总耗时降 70%。

---

## 第 5 步：发布评分（创建后闸门）

5 维框架，**3 项及以上达标 → 建议发布**：

| 维度 | 达标标准 |
|------|----------|
| ① 时效性 | 事件 < 12h，或行情仍在演进 |
| ② 行情相关性 | 直接影响盘面/持仓/板块 |
| ③ Tag 命中质量 | matched_tags 是真正主体 |
| ④ 数据可验证 | 有具体数据可查 |
| ⑤ 合规与争议 | 不涉地缘站队/监管点名/具体投顾 |

询问用户后调用 `update_trending_topic(title, status=0)`，回复 🚀 已发布。

---

## 🚨 紧急撤回 / 数据修正

发布后若发现错误，按以下处置：

| 严重度 | 场景 | 操作 |
|-------|------|------|
| 🔴 立即撤回 | 数据硬错 / 事件被否认 / 触合规雷区 | `update_trending_topic(title, status=3)` 隐藏，**先撤再修** |
| 🟡 修正后保留 | 数据有偏差但主体成立 | `update_trending_topic(new_title/keywords)` 修字段，保持 status=0 |
| 🟢 仅补数据 | 事件无错，只是有新进展 | update keywords/desc，不改 status |

🔴 撤回后说明：
```
⚠️ 已撤回话题 ID=xxxx
原因：[数据硬错 / 事件被否认 / 合规风险]
原标题：xxx
建议：[等数据核实 / 不再创建 / 改写后重发]
```

> **铁律**：撤回是降低长期信任成本的关键。宁可撤回 10 条，也不让 1 条错的留在线上。

---

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

> 找新美股 tag：`update_trending_topic(keywords=["XXX","XXXX","XXXon"])` 加代币化后缀试一次，看返回的 `auto_matched_tags` 即得 tag id，命中即用，否则原 ticker + 手动绑。
