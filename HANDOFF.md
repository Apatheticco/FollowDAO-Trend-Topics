# HANDOFF — 会话交接（2026-07-07）

> 新 session 接管指南：规则全在 `skills/create-trending-topic/`（SKILL.md 执行卡 + references 详章 + LESSONS 版本表，当前 v2.9.6），运行状态在 `~/.trend-scout/`（last-refresh.txt / actions.tsv / snapshots.tsv），话题池以 `list_trending_topics` 实查为准。**本文件只装未决事项**，处理完即可删除本文件。

## ⏸ 未决事项（按优先级）

| # | 事项 | 细节 | 建议 |
|---|------|------|------|
| 1 | ✅ **SKHYX tag 已入库（2026-07-11 结清）** | SKHY 7/10 挂牌后 07-11 首扫实测：`keywords` 含 `SKHYX` 建题（10000002129）**auto-match 命中 `658686`+`658687`**，韩企 tag 缺席问题对 SK 海力士已解除（命名律 ticker+X 验证成立）。后续 SK 题带 `SKHYX` keyword 即自动绑 | 已结 |
| 2 | 🟡 **10422 keyword 撞实体** | 「英伟达否认 Kyber 延期」keyword 只有 `Kyber`，撞 DeFi Kyber/KNC 同名实体，tag 误 match 风险 | 改 `英伟达,NVDA,Kyber` 或交团队 |
| 3 | ✅ **cron 定时器 = 不上，维持手动**（2026-07-08 用户拍板 C）| **实测拦截：OS crontab 走不通**——本账号 claude 用订阅 OAuth、token 存 macOS 登录钥匙串靠宿主动态刷新，cron 后台裸环境够不到钥匙串（`env -i` 实测「Not logged in」，环境还带 `CLAUDE_CODE_DISABLE_CRON`）→ 装了就每轮"未登录"静默空跑。**要重启需先解鉴权**：A′ 本机 cron **必须配独立 `ANTHROPIC_API_KEY`**（console.anthropic.com 建、API 计费独立于订阅），塞进已备好的包装脚本 `~/.trend-scout/run-auto.sh`（逻辑/PATH/opus 模型已就绪，仅缺 key）；B 云端 routine 只能连远程 console/followin，本地 okx/tradingview 跑不了=movers/正股兜底残。**当前形态 C′（2026-07-08 二次修订）：运营会话内挂 session loop**——`CronCreate` job `78171a0e`，cron `33 9,11,16 * * *`（09:33 首扫 + 11:33/16:33 刷新，3 点位，2026-07-08 用户调整），AUTO prompt 自包含；鉴权=会话订阅 OAuth（绕开钥匙串坑）、全 MCP 全功能。**局限**：仅本会话存活期有效（关终端即失效、不落盘）、Mac 需醒着、REPL 空闲才触发、7 天自动过期需续挂。会话死了→下个 session 重挂一条同款 CronCreate 即可（prompt 见 actions.tsv 2026-07-08 12:26 或本条）。手动"跑 AUTO"仍随时可用 | 已决 |
| 4 | 📅 **周复盘首跑 7/13（周一）** | 流程见 `references/weekly-review.md`，吃 `~/.trend-scout/` 双留档。截至 07-07 采纳信号：10391(TCC)、10000002102(三星)、10000002103(SK海力士) 均被团队推上线 | 7/13 用户在场时跑 |
| 5 | 📋 **dev 需求单**（转给 dev） | ① list API 加 PV/热度字段（效果评估盲区）② update_trending_topic 加 id 参数（同名重复清不掉）③ 系统批同名去重（MSTR ×18 前例）④ tag 库补韩/日/港主流标的（三星/SK海力士建题只能裸奔 keywords）⑤ followin metrics tradfi 通道 FMP 403（07-08 09:51–11:46 三轮持续 source_dead，crypto 通道正常；影响油/美元/美股/韩股正股报价，全程靠 okx/yahoo 降级）⑥ followin 主进程 session-init 死锁：长闲置/隔夜后 SSE 重连卡死 "initializing"，所有 tools/call 被拒且**会话级永久**（07-04 与 07-09 两次实测，15min+ 重试无效）；同时**子进程新 session 能连** = 服务端活着、是单连接握手卡死——请查 session 恢复/超时逻辑 ⑦ 数组参调用 -32602：新 session（ToolSearch 加载 schema）下 `metrics keywords` / `news sources` 等数组参被序列化成 string 遭拒、重试无效，**纯 string 参工具（twitter/news query）免疫**；疑 union type `"type":["null","array"]` schema 在客户端被降级——若能改为标准 `"type":"array"` 或服务端宽容 string 化数组可解 ⑧ **metrics keywords 硬上限 5（2026-07-11 新增）**：单次 `keywords` >5 个静默截断到前 5、返回 `warning: keywords truncated: N→5`，多的直接丢——07-10 同调用 10 个还全返回，隔夜收紧。**是"看不见的漏扫"**（不报错、只 warning），已让 skill 全批次改 ≤5/批兜住；若可放宽回 10 或改硬报错（而非静默截断）更安全 ⑩ **🚨 自动打标器打错标签（2026-07-14 用户报，最高优先）**：打标器**解析话题标题**（非 keywords）fuzzy match，两种错法——(a) **错实体**：把标题里的机构/监管缩写当标的（Circle「获 **OCC** 批准」→ OCC tag 13924；SpaceX → SPC tag 11359）；(b) **自造 11 位垃圾占位 tag**（`34523806708` / `10478645335` / `10346157100` / `14127290595` / `10200232432`，正常 tag 是 5-6 位）。规律：干净单 token crypto 题标对，公司名+机构缩写的 tradfi 题必吐垃圾。**已人工 force-set 修好 15 条**，但系统新建的会继续错。**三项请修**：① 打标器只匹配 keywords、不匹配标题机构缩写；② 匹配不到就**留空**、禁止自造垃圾 tag；③ **`list_trending_topics` 输出加 `tags` 字段**——否则运营无法只读排查谁标错（现在只能靠覆盖时看 previous_tags，等于盲改）⑨ **update_trending_topic 同名多条无法定位（复现 HANDOFF#5②，2026-07-11）**：半导体板块 10000002118(status=0)+10000002110(status=3) 同域同名，update 按标题匹配命中多条即报错、无 ID 入口，**status=0 那条事实错误（NVDA 实收跌却写涨3.7%）清不掉**——急需 update 加 `id` 参数 | 用户转发 |

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
