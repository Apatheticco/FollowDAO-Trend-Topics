# HANDOFF — 会话交接（2026-07-17 更新）

> 新 session 接管指南：规则全在 `skills/create-trending-topic/`（SKILL.md 执行卡 + references 详章 + LESSONS 版本表，当前 v2.9.9），运行状态在 `~/.trend-scout/`（last-refresh.txt / actions.tsv / snapshots.tsv），话题池以 `list_trending_topics` 实查为准。**本文件只装未决事项**，处理完即可删除本文件。

## ✅ 已结（一行存档，细节见 LESSONS/actions）

- **SKHYX tag 已入库**（658686+658687，07-11 实测 keyword `SKHYX` 自动命中，韩企 tag 缺席对 SK 解除）
- **cron 定时器不上、维持手动**（07-08 用户拍板：OS crontab 撞订阅 OAuth 钥匙串坑；备选=会话内 CronCreate loop 或独立 API key 包装脚本 `~/.trend-scout/run-auto.sh`，细节见 actions 2026-07-08）
- **周复盘首跑已完成**（07-17，v2.9.9；采纳率 56%、误撤率 3.7%、打回 0——此后**每周一首扫后例行跑**，流程 `references/weekly-review.md`）

## ⏸ 未决事项（按优先级）

| # | 事项 | 细节 | 建议 |
|---|------|------|------|
| 1 | 🟡 **10422 keyword 撞实体** | 「英伟达否认 Kyber 延期」keyword 只有 `Kyber`，撞 DeFi Kyber/KNC 同名实体，tag 误 match 风险 | 改 `英伟达,NVDA,Kyber` 或交团队 |
| 2 | 📅 **周复盘常态化** | 每周一首扫后跑（下次 7/20）；本周基线：采纳 5/9、误撤 3/82（全为 meme、已被 v2.9.7 制度性修复）、打回 0、返工 1/9 | AUTO 周任务 |
| 3 | 📋 **dev 需求单**（转给 dev，重编号 v2.9.9） | ① list API 加 **PV/热度字段**（效果评估盲区）② `update_trending_topic` 加 **id 参数**——同名多条按标题匹配报错无法定位（07-11 复现：10000002118 事实错误清不掉；中文弯引号标题也易失配）③ 系统批**同名去重**（MSTR ×18 前例）④ tag 库补**韩/日/港主流标的** ⑤ followin **tradfi FMP 403** 间歇 source_dead（靠 okx/yahoo 降级）⑥ followin 主进程 **session-init 死锁**（隔夜 SSE 重连卡死、会话级永久；子进程能连=服务端活着）⑦ **数组参 -32602**（quirk⑬：ToolSearch 新 session 下 `news sources` 等数组参被序列化成 string 遭拒；**07-17 再双实证=TG 探针通道死因**，主进程另有 degraded/total=0 死法）⑧ **metrics keywords 硬上限 5** 静默截断（建议放宽或改硬报错）⑨ 🚨 **自动打标器打错标签（最高优先，07-14 用户报）**：解析标题非 keywords、错实体（Circle→OCC/SpaceX→SPC）+ 自造 11 位垃圾 tag；请改①只匹配 keywords ②匹配不到留空 ③ **list 输出加 tags 字段**（现在只读排查不了谁标错）| 用户转发 |

## 📌 本周关键上下文（一句话版，07-17）

- **宏观主线**：6 月 CPI（3.5%<3.8%）+ PPI（-0.3%）双爆冷 → 07-15 risk-on 两天 → 07-16 起**退潮**（美军再袭伊朗），BTC 62-65K 震荡、**Coinbase 溢价连负 60 天创纪录**[10643]=美机构持续流出
- **AI 内存链 4 连崩**：MU/SNDK/SKHY/SOXL 自 07-15 高点回落 10-30%，Burry 做空 MU 两周浮盈；TSMC 财报 beat+上调 capex 也没能止跌——反转题清理是本周主要处置负担
- **meme 默认保留新规（v2.9.7/9.8）**：BRIAN/INDEX/TENDIES 已恢复上线；RH 链 meme 轮动（CASHCAT→PONS→INDEX→BRIAN）是常驻热点源，**只去重/验伪/核数字，不判"值不值得"**
- **TG exploit 探针熔断中**（quirk⑬），漏洞面走 news 全源 query 兜底（实测捞全 BONK/OSTIUM/Summer.fi）

## 🔑 高频踩坑速记（详见 LESSONS）

- 价格：正股优先 followin 直查（韩`.KS`/日`.T`/港`.HK`），代币化不作主锚（v2.8.7）；正股锚话题 domain=tradfi
- movers：只走 okx（`sortBy:"chg24hPct"`、`instType` 必填），followin 涨跌榜是空货架，tradingview 单源不可信（v2.8.6）
- 执行序：扫热点→盘8h池→处置存量→**最后**补题（v2.8.5）；判模式：当天第一轮=首扫，其余=刷新（v2.8.8）
- create 后停 status=2，禁主动上线；>8h 默认不管（例外清单见 §2 表）；keywords ≤4 禁统称；tag 每轮必验（v2.9.5）
- **meme/热点小币默认保留（v2.9.7+9.8）**：撤只限「同标的重复/已证伪/事实错误」三类，禁以"小币/无锚/短时波动"为由
- **看不见的漏扫三守卫**：metrics keywords ≤5/批、B0 limit=100+total==limit 必拆、B0 date_range 必含今天（v2.9.4/9.8）
