---
name: create-trending-topic
description: >
  从原始素材或主动扫描热点，自动提取结构化字段，创建 Followin 热点风向标（TrendingTopic），并支持发布。
  三种触发场景：
  (A) 用户让"扫一下热点 / 找几个话题 / 批量创建今日话题" → 调 Followin/TG/链上/Twitter MCP 主动扫描；
  (B) 用户给一段素材（新闻/推文/描述）让创建话题 → 直接进评分；
  (C) 用户给一个标的或一句话（"查一下 REPPO" / "Aave 现在情况"）→ 多源补全资料再评分。
  全流程：采集 → 去重 → 评分 → 字段提取 + 标题优化 → 预览 → 创建 → tag 校验 → 数据核实 → 发布。
---

# 创建热点风向标

## 整体管线

```
[A 让扫描]    → 第 -1 步：扫描热点（首扫/刷新模式）
[C 给标的/句子] → 第 -1.5 步：定向检索深挖
                                      ↓
                第 0a 步：拉今日已发布话题（status=0）→ 去重对照
                                      ↓
[B 给素材] ──→ 第 0b 步：双轴准入评分（行情冲击 OR 讨论热度）
                                      ↓
                第 1 步：字段提取 + 标题优化
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

---

## 第 -1 步：扫描热点（A 入口）

### 模式自动判断（UTC+8）

| 用户指令 | 模式 |
|---------|------|
| "跑一遍今天热点 / 隔夜更新 / 早上扫一下" | 🟢 首扫 |
| "刷新一下 / 有什么新的 / 现在有什么可以做" | 🔵 刷新 |
| 模糊（"扫一下" / "创建话题"无素材） | 06:00-10:00 默认首扫；10:00 后默认刷新 |
| 例外 | 调 `list_trending_topics(today, status=0)`，今日已发布 0 条 → 强制首扫，不论时间 |

冲突时主动询问。

### 价格数据铁律

简报中所有当前价格/涨跌幅，**只能引用 `crypto_realtime_price_batch` 返回的硬数据**。新闻标题、TG 帖子、KOL 推文里的价格描述一律视为"叙事来源"。输出分区：**📊 实时数据** vs **📰 叙事候选**。

### 🟢 首扫模式（每天早上 1 次，24h 窗口）

**目的**：建立当日全景，覆盖隔夜热点 + 跨市场宏观/美股素材。

#### Wave 1 — 加密热点 + 价格快照

| 工具 | 参数 |
|------|------|
| `open_trending_topic_ranks` | `count=5, lang=zh-cn` ⚠️ count ≤ 5 |
| `open_feed_list_trending` | `type=hot_news, count=15`（只取 title+content） |
| `open_feed_list_trending` | `type=pop_info, count=10` |
| `crypto_realtime_price_batch` | `BTC,ETH,SOL,BNB,XRP,DOGE,HYPE,SUI,LINK,AVAX` |

#### Wave 2A — 加密交易信号 + TG 情报

| 工具 | 参数 |
|------|------|
| `whale_trader_feeds` | `hours=24, limit=30` |
| `top_traders_live_24h` | `limit=30` |
| `tg_kol_feeds` | `category=narrative, hours=12, limit=80` |
| `tg_kol_feeds` | `category=meme, hours=12, limit=100` |
| `twitter_list_timeline` | `listId=2046422494643687464`，24h；**Agent 子进程**提取 text/author/likeCount/retweetCount/viewCount/createdAt，按 velocity top 15 + recency top 5 取 |

#### 🟣 Wave 2B — 美股 / 投资素材（v1.5 新增 2026-05-06）

> 让宏观、美股财报、议员/内部人持仓异动都进入热点风向标候选池。

| 工具 | 参数 / 说明 |
|------|-----------|
| `finance_tool_earnings_calendar` | **周一必跑**，财报周每天跑 — 拉本周 Beat/Miss 候选 |
| `finance_tool_biggest_gainers` + `finance_tool_biggest_losers` | 美股异动榜，找加密联动（科技股 / 代币化股 / Crypto Equity） |
| `finance_tool_house_latest` + `finance_tool_senate_latest` | 议员持仓异动（每日扫，常带政策风向） |
| `finance_tool_insider_trading_latest` | `count=20` — 高管买卖（聚焦异常大额或方向反转） |

#### 🟦 Wave 2C — 科技 / AI 素材（v1.5 新增）

| 工具 | 参数 |
|------|------|
| `twitter_list_timeline` | `listId=2051854001608724654`（科技 AI + 宏观美股投资 list），24h，Agent velocity top 10 + recency top 3 |
| `search_finance_news` | 智能 keyword 按当周轮换（"AI" / "chip" / "earnings" / "tariff" / "Fed"），8 家精选 users |

#### 🏛️ Wave 3 — 宏观 / 大宗（v1.5 新增）

| 工具 | 参数 |
|------|------|
| `finance_tool_economic_calendar` | 一天跑一次即可。⚠️ 全球全量 7000+ 条 / 1.5M 字符，**必须 Agent 子进程**只取 `impact="High"` 且 `country="US"/"CN"/"EU"` |
| `finance_tool_treasury_rates` | 10Y/2Y 收益率，判断利率环境 |
| `realtime_price` × 4 | `gold` / `spx` / `DXY` / `oil` — 大宗 + 美股全景 |
| `fred_get_series`（按需） | `DGS10` / `CPIAUCSL` / `UNRATE` 等关键宏观点位 |

#### 🔶 Wave 4 — 投资大师专项（仅周一 / 季度初）

| 工具 | 参数 |
|------|------|
| `twitter_list_timeline` | `listId=2051856808348987697`（Buffett/Druck/Burry/Cathie/Ackman 等），过去 7d |
| `finance_tool_institutional_ownership_latest` | **季度初（2/5/8/11 月）追加** — 13F 季度更新 |

执行完 → TG Consensus 后处理 → 进入第 0a 步。

**首扫工具 checklist（v1.5，缺一可标记跳过原因）**：

```
🟢 Wave 1 加密+价格（4）  🟢 Wave 2A 加密信号（5）
🟣 Wave 2B 美股/投资（4）  🟦 Wave 2C 科技AI（2）
🏛️ Wave 3 宏观大宗（3）   🔶 Wave 4 投资大师（周一/季度初）
```

### 🔵 刷新模式（日内每 2-4h，4h 窗口）

**目的**：追首扫之后的增量（含跨市场）。

#### 加密 + 跨媒体新闻

| 工具 | 参数 | 与首扫差异 |
|------|------|----------|
| `open_feed_list_trending` | `type=hot_news, count=15` | 同 |
| `open_feed_news` | `only_important=true, count=20` | 仅刷新模式用 |
| `open_feed_articles` | `only_important=true` | 仅刷新模式用 |
| `crypto_realtime_price_batch` | 同上 | 必刷价格 delta |
| `whale_trader_feeds` | `hours=4, limit=30` | 24h → 4h |
| `top_traders_live_24h` | `limit=20`，jq 过滤 `created_at > last_refresh_ts` | 取增量 |
| `tg_kol_feeds` | `hours=4, limit=80`，跑 narrative/meme/trading_signal 三 cat | 12h → 4h，多 trading_signal |

#### 三栈 List Timeline（必跑）

| List | 参数 |
|------|------|
| 主 list `2046422494643687464` | 4h，Agent velocity top 7 + recency top 3，<30min 硬保留，取 10 条 |
| 🆕 科技 AI list `2051854001608724654` | 4h，Agent velocity top 5 + recency top 2 |
| 🆕 投资大师 list `2051856808348987697` | 4h，Agent velocity top 3 + recency top 2 |

#### 🟣 美股 / 跨市场新闻（v1.5）

| 工具 | 参数 |
|------|------|
| `search_finance_news` | 智能 keyword（"AI"/"chip"/"earnings"/"Fed"），8 家精选 users，传 `not_before_ts=last_refresh_ts` |

**🚫 刷新模式不跑**：`open_trending_topic_ranks` / `pop_info` / `economic_calendar` / `treasury_rates` / `realtime_price`（gold/spx/DXY/oil — 日内变化纳入加密对照即可）/ `twitter_advanced_search`（仅候选池兜底等级 2 才调）/ `house/senate_latest` / `insider_trading_latest`（首扫已覆盖，刷新不重复）。

**增量过滤铁律**：每次刷新结束写 `/tmp/trend-scout-last-refresh-YYYY-MM-DD.txt`，下次读取并按上表的 `last_refresh_ts` 字段过滤，避免"刷新读到首扫已读内容"的硬伤。

### 推特 L1 排序规则（刷新模式核心）

纯 `engagement DESC` 在 4h 窗口会压制新推（3-4h 老推累积互动 vs 30min 新推零互动），刷新和首扫严重 overlap，失去追增量意义。

**双轨制**：
- 🅰️ **Velocity 轨**：`(likes + 2×rt + 0.5×reply) / max(hours_since_post, 0.25)` 降序，取 top 7
- 🅱️ **Recency 轨**：`createdAt` 降序，取 top 3
- **绝对保护**：`createdAt` 在过去 **30 分钟内**的推文，无论 velocity 多低都必须进候选池
- 合并去重，最终 10 条

调用 Agent 子进程时**必须在 prompt 里明确**这套规则，否则 Agent 默认回退到 engagement DESC。

### TG Consensus 后处理（必做）

拉到 TG 数据后**不要直接进候选池**，先做共识聚合：

1. 抽取 `$[A-Z0-9]{2,10}` cashtag，关联 username + category
2. 聚合每个 symbol 的 `distinct_authors` / `categories_hit`
3. 分档：
   - **S-tier**：≥2 独立 KOL 且 ≥2 cat → 进候选池
   - **A-tier**：≥2 独立 KOL 但仅 1 cat（第二人 ≥2 条独立 post） → 候选
   - **B-tier**：单 KOL 或第二人仅 1 次提及 → 仅记录，不入池
4. **事件型过滤**：S-tier 若 Top 推文 >50% 来自官方账号且内容是 `launch/airdrop/TGE/mint live` → 判定事件型，**不作叙事选题**
5. **早期 alpha**：S-tier 但 Twitter 稀疏（<5 推文）= TG 领先，最强抢先窗口

### 输出格式

**首扫**：
```
📊 实时数据
- BTC $X (±%)  ETH $X (±%)  ...

📰 叙事候选
🔥 强候选（行情 A≥2 或 热度 B≥2）
1. [事件] — 来源 — A=x B=y — 多源：[✅/⚠️]
⚠️ 弱候选（A<2 且 B<2）
🛑 一票否决（站队/投顾/未证实）
```

**刷新**：
```
📡 刷新扫描（距首扫 Xh / 距上次刷新 Yh）
💰 价格 Δ：BTC $X→$Y (±Δ%)  ...
🆕 新增候选：...
📈 升温候选：...
🟰 重叠已建（不重建，建议 update）：...
🛑 一票否决：...
```

### 🚨 候选池兜底（3 级）

经第 0a 去重后 **🆕 强候选 < 2 条** 时触发：

| 等级 | 操作 |
|------|------|
| 1 | 扩窗：whale 24h→48，TG 12h→24，Twitter 24h→48，重走 Consensus |
| 2 | 调 `twitter_advanced_search(query="crypto OR BTC OR ETH lang:zh OR lang:en", queryType="Top")` 兜底 |
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
| **代币深挖** | 单一符号 / `$XXX` | `crypto_realtime_price_batch` + `open_feed_list_tag(type=key_events)` + `open_feed_list_tag(type=news)` + `open_feed_list_tag_opinions` + `twitter_advanced_search(query="$SYMBOL", Top)` + `market_analyst`（可选）|
| **关键词深挖** | 项目/公司/事件/人名 | `open_search_feed(type=all, sort=time, count=30)` + `open_search_feed(type=flash, count=15)` + `twitter_advanced_search(Latest)` + `twitter_advanced_search(Top)` |
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

## 第 0a 步：拉今日已发布话题（去重对照）

**所有候选池**（首扫/刷新/检索）进入评分前**必须先**调用：

```
list_trending_topics(start_date=今日, end_date=今日, status=0, limit=50)
```

> 为什么只取 status=0？status=2（审核中）/3（已隐藏）不构成"已占用"的选题位。

### 去重判定

| 重合判定 | 标记 | 处置 |
|----------|------|------|
| 标题/keywords 与已发布**完全同主题**（同代币 + 同事件） | 🟰 重叠已发 | **不重建**；有新数据建议 `update_trending_topic` |
| 同标的但**事件维度不同**（已发"X 上线"，候选是"X 链上巨鲸异动"） | 🆕 可建 | 保留进评分 |
| **完全新事件** | 🆕 可建 | 保留进评分 |
| （刷新模式额外）首扫已有但价格/持仓有重大新进展 | 📈 升温 | 建议 update 而非新建 |

仅 🆕 可建 进入第 0b 评分。

---

## 第 0b 步：双轴准入评分（创建前闸门）

热点风向标本质：**对市场行情影响大** 或 **大家讨论度高** 的热点。
准入采用**双轴主导**：行情冲击力 / 讨论热度，二选一达标即可。

### 主轴：必须满足之一（max(A, B) ≥ 2）

**A. 行情冲击力（0-3）**

| 分 | 标准 |
|---|------|
| 0 | 无市场影响（纯娱乐八卦） |
| 1 | 间接传导（≥2 跳，需读者推理） |
| 2 | 直接影响某板块/标的（加密/美股/大宗/外汇/利率） |
| 3 | 全市场级冲击（BTC/ETH/大盘/全板块联动） |

**B. 讨论热度（0-3）**

| 分 | 标准 |
|---|------|
| 0 | 无人关注 |
| 1 | 小圈层冷门讨论 |
| 2 | 圈内热议（多平台/多 KOL 转发） |
| 3 | 全网爆款/出圈（跨圈层刷屏） |

### 辅助维度（每项 0/1/2，决定优先级）

- **信号强度**：是否有具体价格/金额/地址/持仓数据
- **多源验证**：单源 / 双源 / 三源以上
- **独特角度**：通稿味 / 主流叙事 / 独家视角
- **时效价值**：> 24h / 6-24h / < 6h

### 决策规则

| 主轴 | 辅助分 | 决策 |
|------|--------|------|
| A=3 或 B=3 | 任意 | ✅ 必发，最高优先 |
| A≥2 且 B≥2 | ≥4 | ✅ 立即创建发布 |
| A≥2 或 B≥2 | ≥4 | ✅ 创建后正常审核 |
| A≥2 或 B≥2 | <4 | ⚠️ 创建后留审核观察 |
| A<2 且 B<2 | 任意 | ❌ 不创建 |

### 一票否决（任一即拒绝）

- 标题/描述含**明确政治立场或煽动性表达**（仅客观叙述事件 + 写明市场传导路径**不算**站队）
- 含**未经证实**的重大指控
- 含**投顾性质**操作建议（"该买/该卖/目标位"）
- 数据有明显**造假/逻辑硬伤**

> 关键区分：宏观/地缘/美股/AI 议题本身不是禁区，写法客观就放行。被否决的是**写法**，不是**主题**。

### 输出格式

```
📊 准入评估（共 N 条）
| # | 摘要 | A | B | 信号 | 多源 | 独特 | 时效 | 决策 |
| 1 | ... | 3 | 2 | 2 | 2 | 2 | 2 | ✅ 必发 |
| 2 | ... | 1 | 3 | 2 | 2 | 1 | 2 | ✅ 创建（讨论度驱动） |
| 3 | ... | 1 | 1 | - | - | - | - | ❌ 双轴均不达标 |
```

---

## 第 1 步：字段提取

### title — 必走「标题优化方法论」

**硬约束**：
- ≤ 25 字
- 数据/动作前置，不铺垫
- 主体明确（一眼看出什么币/什么事）
- 最多一个分句

详见下文「标题优化方法论」。

### keywords

- 用**英文代币符号**全大写（BTC、ETH、AAVE、HYPE）
- 英文逗号分隔
- 中文/项目全称对自动 tag 匹配无效
- **数量硬约束：1-2 个，最多 3**。配角不进 keywords，避免 tag 关联过多导致主体模糊
- 选择优先级：标题里直接出现的标的 > 行情主线标的 > 板块代表标的

### 宏观/跨市场话题的代币映射（必按顺序判定）

| 宏观主题 | 优先 keywords | 已知 tag id |
|----------|-------------|------------|
| 黄金 / 金价 | `XAUT,PAXG` | XAUt: 10226 |
| 原油 / 石油 | `OIL` | CRUDE OIL BRENT: 520979 |
| **美股 / 个股** | **股票符号本身**（`GOOGL,TSLA,HOOD,COIN,MSTR,MSFT,AMZN,META,NVDA,AAPL` 等） | **GOOGL: 522630**，TSLA: 528245；其余 `open_search_feed(keyword=symbol)` 查 |
| **港股 / 中概** | 股票符号或港股代码（`9988,3690,9618` 或 `BABA,JD,PDD`） | 多数无挂钩代币 → `open_search_feed(keyword=代码)` 查；无则 fallback BTC/ETH |
| AI 板块 | `WLD,FET,RNDR,TAO` 选 1-2 | WLD: 248008, FET: 10201 |
| 外汇 / DXY | 涉事货币挂钩代币 | — |
| 美债 / 利率 / FOMC | `BTC` 或 `ETH`（风险资产联动） | BTC: 10006, ETH: 10007 |
| 联储/CPI/非农/纯宏观 | `BTC` 或 `ETH` | 同上 |

**判定流程（必按顺序）**：
1. **先查标的库里是否有挂钩代币 / 代币化股票** —— 美股/大宗/黄金优先用挂钩代币，不确定时调 `open_search_feed(keyword="$SYMBOL")` 查
2. 无挂钩但与某加密板块强联动 → 用板块代表代币
3. 纯宏观无板块联动 → 用 BTC / ETH

> ⚠️ **铁律**：第 1 档判定**必须先做**。失误案例：8581 Google 财报误用 WLD/FET（板块代表），实际应当用 `GOOGL` + 手动绑 522630。**不要跳过第 1 档**。

### desc

- 1-3 句话补充背景、数据、意义
- ≤ 200 字

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
描述：{desc}

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

**铁律**：每条话题创建后、发布前**必须**逐条核对 desc/title 中的所有数据点。**不可跳过**。

### 核实清单

| 数据类型 | 核实方法 | 不达标处置 |
|---------|---------|-----------|
| **价格 / 涨跌幅** | 重新调 `crypto_realtime_price_batch` 拿最新值 | 偏差 > 0.5% → update |
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

> ⚠️ `update_trending_topic` **不能改 desc**。desc 错严重 → 走撤回重建。

### 工具速查

| 工具 | 用途 |
|------|------|
| `create_trending_topic` | 创建新话题 |
| `update_trending_topic` | 修改 title/keywords/tags/status |
| `list_trending_topics` | 查看话题列表（去重对照必用） |

### 已知 tag id 速查

| 标的 | tag id |
|------|--------|
| BTC | 10006 |
| ETH | 10007 |
| XAUt（黄金） | 10226 |
| OIL（原油） | 520979 |
| GOOGL | 522630 |
| TSLA | 528245 |
| WLD | 248008 |
| FET | 10201 |
| DOGE | 10015 |
| AAVE | 10052 |
| SOL（Solana） | 10012 |
