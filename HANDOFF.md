# HANDOFF — 会话交接（2026-07-07）

> 新 session 接管指南：规则全在 `skills/create-trending-topic/`（SKILL.md 执行卡 + references 详章 + LESSONS 版本表，当前 v2.8.8），运行状态在 `~/.trend-scout/`（last-refresh.txt / actions.tsv / snapshots.tsv），话题池以 `list_trending_topics` 实查为准。**本文件只装未决事项**，处理完即可删除本文件。

## ⏸ 未决事项（按优先级）

| # | 事项 | 细节 | 建议 |
|---|------|------|------|
| 1 | ⏰ **7/10 SKHY 挂牌后复探 tag** | SK 海力士 [10000002103·tradfi] 现无 tag（韩企 tag 库整体缺席，双域 10 探全空）。7/10 SKHY 正式登纳斯达克后复探 `SKHYX`（美股代币化 tag 命名律 ticker+X，同 CRCLX 模式），命中则给话题补 tag | 7/10 后首轮扫描顺手探 |
| 2 | 🟡 **10422 keyword 撞实体** | 「英伟达否认 Kyber 延期」keyword 只有 `Kyber`，撞 DeFi Kyber/KNC 同名实体，tag 误 match 风险 | 改 `英伟达,NVDA,Kyber` 或交团队 |
| 3 | ⏸ **cron 定时器上不上** | AUTO 模式已 3 轮实测（边界全守：建≤3停2、不上线、不碰>8h、双留档、半盲熔断），v2.8.5 执行序 + v2.8.8 判模式已固化。方案 A 本机 cron（推荐）/ B 云端 routine；频率 08:30 首扫 + 12:30/16:30/20:30 刷新 | 等用户拍板 |
| 4 | 📅 **周复盘首跑 7/13（周一）** | 流程见 `references/weekly-review.md`，吃 `~/.trend-scout/` 双留档。截至 07-07 采纳信号：10391(TCC)、10000002102(三星)、10000002103(SK海力士) 均被团队推上线 | 7/13 用户在场时跑 |
| 5 | 📋 **dev 需求单**（转给 dev） | ① list API 加 PV/热度字段（效果评估盲区）② update_trending_topic 加 id 参数（同名重复清不掉）③ 系统批同名去重（MSTR ×18 前例）④ tag 库补韩/日/港主流标的（三星/SK海力士建题只能裸奔 keywords） | 用户转发 |

## 📌 本周关键上下文（一句话版）

- **AI 存储双雄行情**：三星 Q2 利润 19 倍 beat 但股价 -7.3%[10000002102]，SK 海力士 -6.1% + $280 亿 ADR 周五(7/10)登纳斯达克[10000002103]——7/10 挂牌日大概率有后续题
- **ANSEM**（Solana KOL meme）市值 4.4 亿刷新高[10418 系统建]，我方风险角度题 10348 上周建
- **BSC 名人币簇**：CZ 币/TCC[10391 已上线]/GIGGLE，热度回落中
- 无催化合约挤压（YFI/BLUR/TRIA/HMSTR 类）一律不建，系统合约异动批自己会收

## 🔑 高频踩坑速记（详见 LESSONS）

- 价格：正股优先 followin 直查（韩`.KS`/日`.T`/港`.HK`），代币化不作主锚（v2.8.7）；正股锚话题 domain=tradfi
- movers：只走 okx（`sortBy:"chg24hPct"`、`instType` 必填），followin 涨跌榜是空货架，tradingview 单源不可信（v2.8.6）
- 执行序：扫热点→盘8h池→处置存量→**最后**补题（v2.8.5）；判模式：当天第一轮=首扫，其余=刷新（v2.8.8）
- create 后停 status=2，禁主动上线；>8h 不碰；keywords ≤4 禁统称；tag 不硬塞
