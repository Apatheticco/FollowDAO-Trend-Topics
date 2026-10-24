# 数据速查（list ID / 币表 / 板块矩阵 / 宏观符号 / 取价坑 / tag id）

> 本文件是**数据**不是规则：数据过时直接改这里，不动规则文件；新 tag 实测到就补。通道清单与调用参数以 `~/.trend-scout/channels.json` 为唯一来源，本文件和它不一致时以 json 为准。v3.7.15 起实录叙事（SPCX 入表、earnings 日历误判、油价 11% 错值、HL 首用验证、volume 错 874 倍等）沉 LESSONS「gates 10-24 沉降」及对应版本行；旧全文在 git `0deeaa3` 版本。

## 双栈 Twitter list ID（json「A1主栈／A1科技栈」）

| 栈 | list_id |
|----|---------|
| 主 | 2046422494643687464 |
| 科技AI | 2051854001608724654 |

## 10 币（json「价格10币5+5」）

`[BTC, ETH, SOL, BNB, XRP]` ＋ `[DOGE, ADA, AVAX, LINK, HYPE]` 两批（metrics keywords ≤5/批，`gate.sh 调用约束`）。`verbosity="concise"` 不砍 history（每币仍返约 10 根小时线），照默认跑。

## 美股板块矩阵（首扫；拉取名单＝json「板块矩阵6批」，增删改 json）

**29 槽已满，加一个必须换一个**（换人判据：市值×活跃度×被点名频率三项都明显更弱的降「按需」）。批内有海外双重上市的标的（ASML 被服务端扩成 ASML＋ASML.AS 占 2 槽）时，该批只装得下 4 个。下表是**板块归属对照**（报告按板块聚合用，`gate.sh 报告格式`；≥2 标的同向 >3% 成行）：

| 板块 | 代表股 |
|------|--------|
| AI 算力 / GPU | `NVDA,AMD,AVGO,TSM`（TSLA 同批拉取） |
| AI 应用 / 大科技 | `MSFT,GOOGL,META,AAPL,AMZN` |
| 存储 / 内存 | `MU,SNDK,WDC,STX`（MRVL 同批拉取） |
| 光通信 / 网络 | `LITE,AAOI,GLW,COHR` |
| 半导体设备 | `ASML,AMAT,LRCX,KLAC` |
| 加密概念股 | `CRCL,COIN,MSTR`（GEMI 按需） |
| 量化交易 / Fintech | `HOOD,PLTR`（SOFI、IBKR 按需） |
| 航天 / 国防 | `SPCX`（RKLB、LMT、RTX、BA 按需） |

## 宏观 / 大宗

| 品种 | 主调（json） | 降级 |
|------|-------------|------|
| 金 | `XAUT`／`PAXG` @crypto | `yahoo_price GC=F`／`GLD` |
| 油 | `yahoo_price CL=F`（WTI）／`BZ=F`（Brent） | followin `USO/BNO/OIL` ETF（追踪期货，标题须写「油价 ETF」） |
| 美元 | followin `DXY` @tradfi | `DTWEXBGS`@macro；followin `DXUSD`（yahoo `DX-Y.NYB` 的前收常为 None） |
| 美股大盘 | followin `SPY/QQQ` @tradfi（`spx` 必失败，不再先调） | — |
| 国债 | followin macro `DGS10/DGS2`（首扫） | yahoo `^TNX/^TYX` → FRED 直连 `curl https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10`（滞后 1–2 个交易日，只作收盘值，不写「盘中」） |
| econ 日历 | metrics macro-calendar `date_from=今天 date_to=+5d`（首扫） | — |

- **按需取数**（不在 json 通道里）：亚洲指数 `^HSI/000001.SS/^N225/^KS11` 用 followin fmp 批（带 `previousClose`，一批 ≤5）或 yahoo。（亚洲存储行与日元通道 10-24 用户定删除，维持不跑。）
- **⚠️ 绝不用裸 `gold`/`oil`/`CL`**（解析成金矿股/Colgate）；`CLUSD` 已废（返回 FRED `DCOILWTICO` 历史值，差 11%）。
- **期货结算价不用 yahoo 的 `previous_close`**（不随交易日滚动，9/3 晨仍显 9/1 结算）：结算价用 `followin metrics(keywords=["GC=F"], asset_type=tradfi, categories=[market])` 的 `previousClose`；yahoo 只取现价。
- **yahoo 两种假数据**：① 偶发返回空对象（无 error 也无 price）——单次空返回先重试 1 次，连续 ≥2 次才算故障；② 亚洲时段「过期收盘复读」——`change` 恰为 0.0 且 `price == previous_close`，此值只能当上日收盘用，写现价必须拿别的源交叉（重试无用）。
- **earnings**：按 ticker 查最准——`metrics(keywords=[HD,WMT,...], query="next earnings date", asset_type=tradfi)` 返回精确日期＋EPS/营收预期＋上季 surprise＋目标价共识。市场级日历：带 `country=US` 可用但结果可能不全（10-24 复核：返回 partial，单页上限 50，有 next_cursor）。**判任何通道失效前，先读 meta 的 `filters_applied` 与 `pagination`。**

## 美股分时段取价

主次以 `gate.sh 时段` 四时段表（铁律⓪：长桥 `quote` 为主，followin 15min 为降级）为准，下面只记降级通道的用法与坑：

- **followin 盘前/盘后在 history 叶不在 snapshot 叶**：snapshot 恒为 `regular_inactive`；`metrics(keywords=[X], asset_type=tradfi, categories=[market], query="intraday candles", interval="15min", limit=60)` 返回 05:00–19:45 ET 全时段（**时间戳是 ET**）。最后一根盘后 K 线的 close＝盘后价，自比 regular 收盘（16:00 那根的 open）；16:00 那根的高低点横跨收盘，盘后区间从 16:15 起算。
- **`tradingview stock_extended_hours`**：一次返回 `pre_market`／`regular`／`post_market` 三段带涨跌幅，核数时作交叉。**美股全休市时段（ET 00:00–04:00＝CST 12:00–16:00）字段错位**：`post_market` 为 null，`pre_market` 装的是上一交易日盘后最后一笔——看 `as_of_utc`，落在上一交易日约 23:59 UTC 的就读作盘后价。
- **事件发布时点决定用哪段价** → `gate.sh 双要素`／`gate.sh 时段`。

## 非美 / 特殊标的

- **A 股**：主＝长桥 `quote`（`.SH/.SZ`）；followin `metrics` 用 `.SS` 也能直查（10-24 复核 `688836.SS` 返回 fmp 现价与前收，旧版「followin 不覆盖 A 股」已过时）。韩 `.KS/.KQ`、日 `.T`、港 `.HK` 同样直查（正股优先，`gate.sh 通道故障`）。
- **followin `volume`／`volume_24h` 是币数不是美元**：美元成交额＝`volume_24h × 现价`，低价币会错 3 个数量级；`history[].volume` 是单根 K 线的量不是 24h。合约美元成交额直接用 `pct.py bn`。写金额前过量级自洽闸（`gate.sh 数字`：成交额÷市值 >20 倍先当自己算错）。HL 的 `dayNtlVlm` 确为美元。

## Hyperliquid / Trade.xyz（W-HL 条件通道；触发条件与口径边界 → `gate.sh 并发编排` W-HL 条）

```
curl -s -X POST https://api.hyperliquid.xyz/info -H "Content-Type: application/json" -d '{"type":"metaAndAssetCtxs","dex":"xyz"}'
```

- 无鉴权，返回 `[meta, ctxs]` 两段按下标对齐；ctx 有 `midPx`／`prevDayPx`／`openInterest`／`dayNtlVlm`。`dex="xyz"` 不可省（不在主 universe，直查 `allMids` 会误判不存在）；builder DEX 列表 `{"type":"perpDexs"}`。
- **名字带 `xyz:` 前缀**：取名一律 `u["name"].split(":")[-1]`；空结果先打印 `len(universe)` 再下结论（静默空集是看不见的漏扫）。
- **新上市合约的 `prevDayPx` 是上市锚定价、不滚动**（24h% 完全失真）：上一轮 dump 里没有的标的，改用正股或自己两次读数的差。量盘后/隔夜变化也用自己两次读数差，不用 24h%。
- **命名陷阱**：xyz 上非美标的多为「正股·美元计价」，个别是 ADR，同一公司可能两个合约并存（SK 海力士 `SKHX`＝正股、`SKHY`＝ADR）。写韩/日股价格取正股口径那个，并用「正股收盘价 ÷ 合约价 ≈ 即期汇率」当场验。
- **薄盘不可信**：先看 OI／成交额再用价（`VIX` 的 `midPx` 直接是 None）。

## 写看板

- 一律 `~/.trend-scout/topic.py create|update|publish|cull|restore|get --id`（用法 `topic.py -h`）；keywords 只收逗号分隔字符串、≤4 个；不写 desc。按标题定位的老坑随入口一起作废（案例见 LESSONS）。
- **系统建题会自己改标题**（行情题数字随行情滚动、已隐藏题也会被改写）：`topic.py cull` 已把撤时标题写进备注。
- **系统 keywords 自动切词缺陷**：`ETHERFI` 被切成 `ETHER,FI`，`FI` 命中 Fiserv——处置系统 crypto 题时顺手核有没有被切出两字母噪音段，有就 `topic.py update --keywords` 改掉。
- **端点 500**：`topic.py create` 整体报 500 而 list/update 正常 → 先 list 探服务在线、再用短标题 create 探一次排除内容；仍 500 就本轮放弃建题，用 `log-action.sh note` 留档「待建|<标的>|<原因>」下轮补，不要反复重试。
- **台账备注**：只经 `topic.py`／`log-action.sh` 写入；备注里不用反引号和 `$`（会被 shell 执行），引用用中文「」。

## 已知 tag id

- **打标规律**：系统打标器解析的是**标题**不是 keywords——① 错实体（标题里的机构/监管缩写被当标的：「获 OCC 批准」→ OCC、SpaceX→SPC）；② ≥7 位（尤其 11 位）是匹配不到时自造的垃圾占位 tag（`topic.py` 已自动标出）。干净单 token 的 crypto 题自动标对；公司名＋机构缩写的 tradfi 题最易出错。下游错实体由 `downstream.py` 回读，改关键词才生效（`gate.sh 建题核实`）。
- **找新美股 tag**：`topic.py update --id X --keywords "XXX,XXXX,XXXon" --rc tag修正 …` 加代币化后缀试一次，看回读的自动打标结果，命中即用，否则原 ticker。

**加密原生**

| 标的 | tag id |
|------|--------|
| BTC | 10006 |
| ETH | 10007 |
| SOL | 10012 |
| DOGE | 10015 |
| AAVE | 10052 |
| ZEC | 10058 |
| FET | 10201 |
| XAUt（黄金） | 10226 |
| WLD | 248008 |
| ONDO | 352019 |
| ENA | 399979 |
| BONK | 159920 |
| Hyperliquid | 416160 |
| OIL（原油） | 520979 |

**代币化美股 / 跨市场**（create 自动匹配常只给原票，要代币化 tag 需 keywords 带 `X`／`on` 后缀）

| 标的 | tag id | 备注 |
|------|--------|------|
| NVDAX | 522527 | |
| CRCLX | 522611 | |
| AAPLon | 546230 | Ondo 发行 |
| SPY-X | 522609 | |
| QQQ-X | 522709 | |
| COINX | 522512 | |
| MSTRX | 522610 | |
| AVGO | 550939 / 550614 | AVGOX/AVGOon |
| AMD | 634136 / 547619 | AMDX/AMDon |
| ORCL | 563897 / 549884 | ORCLX/ORCLon（裸 ORCL 不命中） |
| SNDK | 627019（代币化）／658100（原票） | tradfi 域同样生效；WDCX/STXX 无命中 |
| MU | 550032（代币化）／658099（原票） | |
| MRVL | 548352 | |
| COHR | 635980 | |
| INTC | 548353 | 无代币化版 |
| GOOGL | 522630 | |
| TSLA | 528245 | 可试 TSLAX |
| PLTR | 667111 | |
| SpaceX | 536083 | pre-IPO 代币化，keyword `SpaceX` 自动命中 |
| SK 海力士 | 658686 + 658687 | keyword 含 `SKHYX` 自动命中双标 |
| NASDAQ 指数 | 10646 | 手动绑；keywords 重匹配会顶掉，需以 tags 显式传回 |

- **待核（勿当已知用）**：`489344`——08-20 传 `HYPE,Hyperliquid,特朗普,白宫` 返回 489344＋416160，416160 已确认是 Hyperliquid，489344 是 HYPE／特朗普／白宫之一（最可能 HYPE）｜`148592`——Binance／代币化美股／永续合约之一｜`161127`——SEC／加密监管／Atkins 之一（最可能 SEC）。下次单 keyword 建题时分辨再入表。
- **实测无 tag（勿重复探）**：IREN、HUT8、SMCI、KOSPI、ZHIPU、Multicoin；日韩正股（`6976.T`、`005930.KS`，三星只能手动绑 SK 的 658686/658687）。
