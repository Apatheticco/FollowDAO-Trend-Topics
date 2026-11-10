#!/usr/bin/env python3
# lint.py — 标题/池子机械闸引擎（v2.9.81）。正则与判据单一事实源；lint-title.sh / b0-audit.sh 是薄包装。
# 用法: python3 lint.py title "<标题>" [tradfi|crypto]
#       python3 lint.py b0 <b0.json> [--since <run_ts_ms>]
# 输出: LEVEL<TAB>闸<TAB>说明<TAB>(版本)   LEVEL ∈ FAIL/WARN/INFO；title 模式有 FAIL 则 exit 1
import re, sys, json, datetime, os, collections, time
sys.path.insert(0, os.path.expanduser("~/.trend-scout"))  # v3.1.5 供 ⑥ 段 import quotes

CORP     = re.compile(r'(Corporation|Corp\.|\bInc\.?(?=\W|$)|\bLtd\.?(?=\W|$)|Limited|Holdings|\bAG\b|N\.V\.|\bPLC\b|S\.A\.|Co\.,? ?Ltd|\bLLC\b|Group Inc|Technologies Inc|Systems Inc)')
QUESTION = re.compile(r'[?？]|能否|是否|吗$|你发现了吗|悬念|将变盘|会放大|还能|该不该|会不会|能不能')
PSEUDO   = re.compile(r'板块普跌|板块普涨|集体走高|集体走强|集体下挫|集体下跌|全线走强|热度(走高|升温|飙升|上升)|关注度(提升|上升)|概念受关注|受关注|技术面|金叉|死叉|突破均线|重返均线|站上均线|创新高后回调|波动加剧|短线升温|情绪(升温|加速|高涨)|叙事(升温|热度|热潮)|资金关注|市场关注|热度飙升|阶段性走强|阶段性走弱|阶段性拉升')
PCT      = re.compile(r'[涨跌]\s*(超|近|逾|约)?\s*[0-9.]+%|涨停|跌停|翻倍|腰斩')
# v3.4.10(用户 09-20 裁定:「报X美元」算价格腿) 静态报价也是价格腿,只给 junk_class 用。
#   不并进 PCT:PCT 还管着 tradfi「时段前缀」闸(有涨跌%才要求盘前/盘中/收),并进去会让
#   每条「报X美元」的美股题都被误要求带时段前缀。
#   负向前瞻排掉「财报/季报/年报/月报/周报/日报 + 数字」,那不是报价。
QUOTE    = re.compile(r'(?<![财季年月周日])报\s*[\d.]')
# v3.6.6(10-10 用户批):「跌破/升破/站上/失守 X美元」这类价位穿越也是价格腿。10-09 实测
#   「比特币一度跌破8.05万美元」「布伦特原油回落至102美元」被判缺价格腿,每轮要改成「报X」绕开。
#   必须带货币单位,避免把「突破100万用户」这类 vanity 当价格;紧跟在市值/TVL/营收/成交额等后面的不算(那是 vanity 指标)。
LEVEL    = re.compile(r'(?<!市值)(?<!规模)(?<!TVL)(?<!营收)(?<!收入)(?<!成交额)(?<!交易量)(?<!融资)(?<!估值)(?<!储备)(?<!锁仓)(?<!持仓)(跌破|升破|涨破|突破|站上|站稳|失守|重返|回落至|回落到|跌至|跌到|升至|涨至|涨到|冲上|下探至?)\s*[\d.]+\s*(万|千)?\s*(美元|美分|港元|日元|韩元|元)')
# v3.6.6:近 24 小时连续交易的品种(原油/贵金属/外汇/加密/期货)写「24小时涨跌X%」即为时段口径,不再报缺时段前缀。
#   10-08 布油题已写「24小时涨2.6%」,机审④仍报「时段前缀」。股票照旧要盘前/盘中/收涨跌。
#   ⚠️ plan-check.py 的 WRITER_SESSION 词表**故意不跟改**:它与 Evose 写手第 4 条提示词逐字一致(v3.6.5),
#   只改这边会造成「机检放行、写手拒改」;要放开须先改 Evose 写手提示词,再同步 plan-check。
H24      = re.compile(r'24\s*小时|24h')
ALLDAY   = re.compile(r'原油|布伦特|WTI|油价|黄金|金价|白银|银价|铜价|天然气|美元指数|DXY|期货|汇率|日元|欧元|英镑|比特币|以太坊|BTC|ETH')
SESSION  = re.compile(r'盘前|盘中|收涨|收跌|盘后|夜盘|尾盘|午盘|收平|一度|冲高|振幅|区间|开盘|早盘|收报|封涨停|封跌停|回吐|反转|次日')
WINDOW   = re.compile(r'短时|短期|短线|九小时|24小时|24h|日内|两日|三日|7日|一周|本周|即将|将于|临近')
# v3.1.8 ② 窗口题补「时效性数字断言」——09-07 实测:>48h 在线题 23 条,WINDOW 只命中 3 条,
#   漏的 20 条几乎全是「收涨/收跌 X%」「市值冲高至 X」这类定稿题:标题没说是哪天的数,读者读成当下。
#   **只对 crypto 生效**:tradfi 的收盘价在下一个 session 开始前仍是最新事实(gates 闸:时段 v2.7.8),
#   09-07 就是实例——09-04 周五收盘后接周末 + 劳动节,若不加这个限制会一次性刷出 12 条假阳性。
STALE    = re.compile(r'[收]?[涨跌]\s*\d+(\.\d+)?%|报\s*[\d.]|市值[^，。]{0,4}[\d.]|创?新高|创?新低')
RELATION = re.compile(r'连涨|连跌|新高|新低|首次|最长|最大|以来|创纪录|纪录|史上|翻倍|腰斩|N倍|[0-9]+倍')
CAUSAL   = re.compile(r'压涨幅|推升|拖累|抵消|受.{1,8}(影响|提振|拖累)|带动|提振|引发|推动|导致|因.{1,10}而')
FORECAST = re.compile(r'将于|拟于|将公布|待公布|即将|今晚|明日|定于|本周将|下周|本月将|将进行|待揭晓')   # 10-23 补:13473「本月将进行链上表决」、13495「规则待揭晓」


def preview_misfiled(rc, title):
    """10-23 复盘:预告形态的题被我用「灌水-产品公告」撤了两次(13473/13495),复审员两次挑出应记「预告题-准入不过」。
    撤因是产品公告、标题却是预告形态 → True(调用方拦下,提示换码;确非预告在备注写「非预告:<理由>」放行)。"""
    return rc == '灌水-产品公告' and bool(FORECAST.search(title or ''))
AMOUNT   = re.compile(r'[0-9.]+\s*(万亿|千亿|百亿|亿)美元')
CLOSEFIX = re.compile(r'收涨|收跌')
TICKER   = re.compile(r'\b[A-Z]{2,5}\b')
TICKERKW = re.compile(r'^[A-Z0-9.\-]{2,12}$')   # 关键词是否 ticker 型(纯 ASCII 大写/数字/点,如 HOOD、0700.HK、000660.KS)
DOLLAR   = re.compile(r'\$[A-Za-z]')


# v2.9.83 灌水形态机械分类(0.5 层五周居首的撤因前置成闸):只对无价格腿的题给出撤因建议,有 PCT 或 QUOTE 的一律不碰
OPINION  = re.compile(r'^[^：:，,]{2,24}[：:]')                       # 「某某：观点」
# 10-27 复盘(13582):「10/26报道：XRP Ledger增1.5亿美元基金份额」冒号前是日期/报道出处,不是说话人,被判成 KOL 观点题错码
NEWS_PREFIX = re.compile(r'^(\d{1,2}[/月.-]\d{1,2}日?|[^：:，,]{0,20}?(报道|消息|快讯|公告|数据|据悉|获悉))[：:]')
VANITY   = re.compile(r'供应量|占比|持有量|存入|TVL|累计|总量|创历史新高|突破.*万|突破.*亿|持币|地址数|交易量创')
FUNDING  = re.compile(r'融资|投资|估值|获.{0,6}(万|亿)美元|注资|入股')
# 10-15 retro:大公司/机构合作是 gate A闸列明的硬事件(不要求价格腿)——并进下方 HARD_EVENT(不进机械撤命令、交人判)。
#   病例:13265「PLASMA联手Stripe推出多币种加密卡」被⑥列成灌水-产品公告撤命令,我照单 b0-cull,复审挑战成立后 restore。
BIGCO = re.compile(r'Stripe|Visa|Mastercard|万事达|PayPal|贝宝|BlackRock|贝莱德|Fidelity|富达|JPMorgan|摩根大通|Goldman|高盛|Citadel|城堡|DTCC|SWIFT|CME|纳斯达克|Nasdaq|纽交所|NYSE'
                   r'|Google|谷歌|Microsoft|微软|Amazon|亚马逊|Apple|苹果|Nvidia|英伟达|Meta|Tesla|特斯拉|Samsung|三星|Shopify|Revolut|Coinbase|Robinhood|Binance|币安|Upbit|OKX|欧易|Bybit|Kraken|Circle|Tether', re.I)
ANNOUNCE = re.compile(r'集成|合作|推出|支持|升级|探索|布局|接入|宣布|计划|拟|将于|加入.*董事会|任命|出任')
# v3.6.6(10-10 用户批,周报 09-26~10-03 ③):硬事件词命中的题不进 ⑥ 机械撤命令,改为提示人判。
#   10-03 机审⑥把「BLAST宣布停运,用户需迁出资产」列成灌水-产品公告撤候选;v3.6.2 写明官方重大事件属硬事件。
#   这里只负责「别让机器一键撤掉」,留不留仍按 gates 判(无可交易标的的硬事件照样可以撤,但要人看过)。
# 11-05 复盘(13853「ELYSIUM主网11月9日上线，生态能否起势？」被⑥按疑问句机械撤,去问号后是官方重大事件)——主网上线/TGE 进硬事件
HARD_EVENT = re.compile(r'停运|关停|停止运营|清算|被盗|被黑|遭攻击|黑客|漏洞|失窃|盗币|暂停提现|暂停充提|破产|跑路|下架|退市|摘牌|起诉|诉讼|获批|批准'
                        r'|主网[^，,]{0,8}(上线|启动)|TGE'
                        # 11-07 周报通读:13906「FinCEN切断MEXC美国金融接入」被⑥列成灌水-产品公告——监管/执法动作是 gates 例外二的硬事件
                        r'|FinCEN|OFAC|\bSEC\b|CFTC|司法部|财政部|美联储|央行|监管|制裁|切断|禁令|禁止|罚款|罚单|吊销|牌照|执照|执法|查封|冻结|和解|指控|立案'
                        r'|(上线|上架|登陆|上币)\s*(Upbit|Coinbase|币安|Binance|Robinhood|OKX|Bithumb)|(Upbit|Coinbase|币安|Binance|Robinhood|OKX|Bithumb)\s*(上线|上架|将上线)', re.I)
PARTNER = re.compile(r'联手|携手|合作|牵手|集成|接入|入股|收购|并购')
def hard_event(title):
    m = HARD_EVENT.search(title or '')
    if m:
        return m.group(0)
    b, p = BIGCO.search(title or ''), PARTNER.search(title or '')    # 10-15 retro:大公司/机构合作
    return f'{b.group(0)}·{p.group(0)}' if b and p else None

# 热点候选阈值——**这一行字符串是单一事实源**:运行阈值从它解析,scatter.py 也拿它当指纹与 gates 闸:大热点/SKILL 索引行比对。
# 改阈值只改这一行;若把数字另写成常量,注释与代码就会各漂各的(scatter 看不见同一文件内的分叉)。
HOT_RULE='系统 ≤8h 对同一实体族建题 ≥3'
HOT_WINDOW_H=int(re.search(r'≤\s*(\d+)\s*h',HOT_RULE).group(1)); HOT_MIN=int(re.search(r'≥\s*(\d+)',HOT_RULE).group(1))

def meme_scope(t, exists=None):
    """v3.4.4(周报提案 P0-2) meme 铁律作用域的单一实现(log-action.sh 与 b0-cull.py 共用,禁止再内嵌副本)。
    返回 True = 题目确有小市值/meme 代币标的,撤因须落三类。旧判据「crypto 且标题关键词无主流 ticker」把
    Leopold/华为小米/利率板块 这类根本没有代币的题也当 meme 拦(09-05~09-12 实证 12266/12274/12276),
    逼出「跳过-待人裁」污染归因。新判据要求能指认出代币:
      ①关键词某项是纯大写 ticker(2-12 位,含字母) ②关键词逐词或标题 $TICKER 命中 contracts.json 注册表
      ③关键词某项在 majors.json 的 cjk_tickers(中文名代币)。命中主流白名单仍优先放行(与旧判据一致)。
    读不到白名单/注册表 = 空集(①仍生效);读不到题目由调用方按保守处理。"""
    if t.get('domain') != 'crypto': return False
    def _load(env, dflt):
        try: return json.load(open(os.environ.get(env) or os.path.expanduser(dflt), encoding='utf-8'))
        except Exception: return {}
    mj = _load('MAJORS_JSON', '~/.trend-scout/majors.json')
    majors = set(mj.get('majors') or []); cjk = set(mj.get('cjk_tickers') or [])
    non_token = {x.upper() for x in (mj.get('non_token_acronyms') or [])}   # v3.4.x(09-17) 非代币缩写排除
    ct = _load('CONTRACTS_JSON', '~/.trend-scout/contracts.json')
    reg = {k.upper() for k in list((ct.get('tokens') or {})) + list((ct.get('blocked') or {}))}
    title = t.get('title') or ''; kw = t.get('keywords') or ''
    # v3.5.6(09-22) 主流匹配与判据①长度对齐(2-12),并剥项目名后缀再比:『NEARPROTOCOL』曾被 {2,10} 切成 NEARPROTOC+OL 漏认 NEAR
    _runs = set(re.findall(r'[A-Z]{2,12}', f"{title} {kw}".upper()))
    _runs |= {re.sub(r'(PROTOCOL|NETWORK|CHAIN|FOUNDATION|LABS)$', '', r) for r in _runs}
    if _runs & majors: return False
    ents = [e.strip().lstrip('$') for e in re.split(r'[,，、]', kw) if e.strip()]
    # v3.4.x(09-17) 判据①收紧:大写关键词须在标题里以同样大写原样出现、且不在非代币缩写名单,才算代币。
    #   项目/公司名在标题里是首字母大写(Payward/Hyperliquid),监管/人物缩写(SEC/CZ)进名单;
    #   09-16 Evose 12421(HYPERLIQUID,PAYWARD)、12422(SEC) 撤题被误当 meme 拦下,见 tests/meme-scope-cases.tsv。
    cands = [e for e in ents if re.fullmatch(r'[A-Z0-9]{2,12}', e) and re.search('[A-Z]', e) and e in title and e.upper() not in non_token]
    if cands:
        # v3.6.0(09-26 用户定方案 B):认代币要有交易证据。exists(sym) 由调用方注入(token_exist.exists):
        #   True=交易所/注册表/dex像样池子有 → 保护;None=数据源没查成 → 保守照样保护;False=都没有 → 不是代币。
        #   不注入(回归用例、离线)时维持旧行为。09-20~09-26 误拦 10 次全是公司/交易所/项目/人名/主流币,见 token_exist.py 头注释。
        if exists is None or any(exists(e) is not False for e in cands): return True
    words = {w.upper() for e in ents for w in re.split(r'[\s/]+', e) if w}
    words |= {m.upper() for m in re.findall(r'\$([A-Za-z0-9]{2,12})', title)}
    if words & reg: return True
    return any(e in cjk for e in ents)

def vol_claim_unsupported(title, note):
    """10-27 复盘(13585):meme 四查②「按题面判」——题面与来源都没主张成交额的记 ✗。
    备注四查写了「成交额✓」而标题里没有「成交」、备注也没写「来源主张成交额」→ 违规(把实测成交额当成了题面主张)。"""
    n = note or ''
    return bool(re.search(r'成交额\s*✓', n)) and '成交' not in (title or '') and '来源主张成交额' not in n


def junk_class(title):
    """返回 (reason_code, 依据) 或 None。有价格腿不判;疑问句优先。
    v3.4.10:价格腿 = 涨跌%/涨停/翻倍/腰斩(PCT) 或 静态报价「报X」(QUOTE)。
    09-20 Evose 第十六轮审核员指出 12497「ZEC报1470美元」、12449「UNI报8.77美元」
    都带价格腿却进了 ⑥ 清单,用户裁定「报X美元」算价格腿。"""
    if PCT.search(title) or QUOTE.search(title) or LEVEL.search(title): return None
    if QUESTION.search(title): return ('疑问句-悬念','问号/悬念且无价格腿')
    if OPINION.match(title) and not NEWS_PREFIX.match(title): return ('灌水-KOL观点','冒号观点题且无价格腿')
    if FUNDING.search(title) and not re.search(r'空投|奖励|赔偿|补偿', title): return ('灌水-融资无标的','融资/投资叙事且无价格腿')   # 10-17 复盘:13305「获声援，8万美元空投」被 获…万美元 误判成融资
    if VANITY.search(title): return ('灌水-vanity指标','vanity 指标且无价格腿')
    if ANNOUNCE.search(title): return ('灌水-产品公告','公告/合作/人事且无价格腿')
    return None

# v3.5.4 双要素机械闸(gates「闸:双要素」的可机检部分)。09-21 Evose 第二十轮审核员拟出
#   「AKE跌18.46%，报0.053美元」「NEAR涨17.69%，报4.178美元」这类纯价格标题,lint-title 全闸通过、
#   写手只核字数与关键词,整条链没有一道闸管「有没有诱因」。
#   WARN 不 FAIL:回测本机 660 条历史新标题有 68 条命中,几乎都是 meme豁免/纯行情-A定则 下的承接更新——
#   豁免成不成立机器判不了。plan-check.py 把命中行单列,交给人裁。
#   纯价格判据:剥掉价格腿(涨跌%/报X/市值X/成交额X)、时间修饰与标点后,只剩一个标的名(ASCII 代号
#   或 ≤4 个汉字)。纯价格题过闸只剩「幅度够大」一条路:crypto ≥±50%(11-06 由30%上调)、tradfi ≥±10%。
#   诱因真伪(伪诱因/有没有出处)机器判不了,仍归审核员与 gates;这里只拦「根本没写诱因」。
PRICE_BITS = re.compile(r'[涨跌]\s*(超|近|逾|约)?\s*[0-9.]+%|[涨跌]幅(收窄|扩大)?\s*(至|到)\s*[0-9.]+%|涨停|跌停|翻倍|腰斩|持平|几无反应|无反应'
                        r'|(?<![财季年月周日])报\s*[\d.]+\s*(美元|美分|港元|日元|韩元|元)?'
                        r'|(?<!市值)(?<!规模)(?<!TVL)(?<!营收)(?<!收入)(?<!成交额)(?<!交易量)(?<!融资)(?<!估值)(?<!储备)(?<!锁仓)(?<!持仓)(跌破|升破|涨破|突破|站上|站稳|失守|重返|回落至|回落到|跌至|跌到|升至|涨至|涨到|冲上|下探至?)\s*[\d.]+\s*(万|千)?\s*(美元|美分|港元|日元|韩元|元)'
                        r'|市值[^，,\d]{0,4}[\d.]+\s*(万亿|千亿|百亿|亿|万)?\s*(美元)?'
                        r'|(okx|OKX|币安|Binance|OKX永续)?\s*成交额\s*[\d.]+\s*(万亿|亿|万)?\s*(美元)?')
PRICE_FILLER = re.compile(r'24\s*小时|24h|单日|今日|日内|盘中|盘前|盘后|夜盘|尾盘|收盘|收|暴|大|再|一度|近\d+日|\d+日|两日|三日|本周|一周|现货|永续|[，,、；;：:\s$]')
PCT_NUM = re.compile(r'[涨跌]\s*(?:超|近|逾|约)?\s*([0-9.]+)%')
# 11-07 复盘(10000003649「12月加息概率升至近八成」被 lint 报缺价格):宏观事件题以市场定价读数作价格腿——
# 利率期货隐含概率、国债收益率、汇率等「指标+升降至+数值」;央行官宣利率(加息至1%)是事件本身,不算价格腿
MACRO_LEG = re.compile(r'(概率|收益率|利差|隐含|定价|汇率|美元指数|DXY)[^，,；;]{0,6}?(升至|降至|涨至|跌至|升破|跌破|达到?|报|升|降|回落至|飙升至|跳升至)\s*(近|约|逾|超)?\s*([0-9.]+\s*(%|个基点|bp|基点)|[一二三四五六七八九]成|[0-9.]+(?=$|[，,、；;]))')

def pure_price(t):
    """返回 (是否纯价格, 最大幅度%)。无价格腿返回 (False, None)。"""
    if not PRICE_BITS.search(t): return (False, None)
    rest = PRICE_FILLER.sub('', PRICE_BITS.sub('', t))
    nums = [float(x) for x in PCT_NUM.findall(t) if x.replace('.','',1).isdigit()]
    big = 999.0 if re.search(r'涨停|跌停|翻倍|腰斩', t) else (max(nums) if nums else 0.0)
    only_name = bool(re.fullmatch(r'[A-Za-z0-9.\-]{1,16}', rest)) or bool(re.fullmatch(r'[\u4e00-\u9fff]{1,4}', rest)) or rest == ''
    return (only_name, big)

def cross_midnight_word(title, hour):
    """10-28 复盘(10000003332):22:05 建预告题写「美联储今晨2点将公布」,事件在次日凌晨——「今晨」读作已过去的今天早晨。
    中午以后建题,标题里出现今晨/今早/今天凌晨/今日凌晨 → 应写明晨/次日凌晨或具体日期。返回提示或 None。"""
    if hour is None or hour < 12:
        return None
    m = re.search(r'今晨|今早|今天凌晨|今日凌晨', title or '')
    return f'跨午夜时间词:{hour}点后建题写「{m.group(0)}」,事件若在次日凌晨应写「明晨/次日凌晨/具体日期」' if m else None


def ratio_like_time(title):
    """10-29 复盘(10000003332):「美联储10:2维持利率不变」票数写成冒号,读者读成 10:02。
    冒号后只有一位数(时刻的分钟必是两位)且不接 % → 当作比分/票数写法拦。"""
    m = re.search(r'(?<![\d:])(\d{1,2}):(\d)(?![\d%])', title or '')
    return f'「{m.group(0)}」易被读成时刻,票数/比分写成「X票对Y票」或「X比Y」' if m else None


def mcap_gate_misjudged(note):
    """10-29 复盘(13658 PRIORS):四查③市值关口用「现已跌回关口下」记 ✗——闸A③看本轮是否首次突破,不看现在是否站稳。"""
    n = note or ''
    if re.search(r'市值关口\s*✗', n) and re.search(r'(跌回|回到|已回|回落|跌破)[^;；,，]{0,12}(关口|万|亿)', n):
        return '四查③市值关口看「本轮是否首次突破整数关口」,不看现在是否站稳;已跌回关口下仍记✓(10-29 13658)。确未突破就写30天高点'
    return None


CRYPTO_LINE = float(__import__('os').environ.get('TS_CRYPTO_LINE', '50'))   # 11-06 用户定:crypto 纯行情与 meme 豁免①幅度线 30%→50%(纯行情币题近7天占加密建题72%,太多)


def idx_line(t):
    """11-07 周报通读:指数题按 coverage.IDX 的对账线判幅度(单一定义在 coverage.py)。返回 (线, 命中名) 或 None。"""
    try:
        import importlib.util as _u, os as _o
        _s = _u.spec_from_file_location('_cov', _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'coverage.py'))
        _c = _u.module_from_spec(_s); _s.loader.exec_module(_c)
    except Exception:
        return None
    low = (t or '').lower()
    hits = [(thr, n) for sym, (thr, names) in _c.IDX.items() for n in (names | {sym.lower()}) if n and n in low]
    return min(hits) if hits else None


def major_line(t, kws=''):
    """11-09:BTC/ETH 纯行情另设线(单一定义 coverage.MAJOR)。标题或关键词命中返回 (线, 符号),否则 None。"""
    try:
        import importlib.util as _u, os as _o
        _s = _u.spec_from_file_location('_cov', _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'coverage.py'))
        _c = _u.module_from_spec(_s); _s.loader.exec_module(_c)
    except Exception:
        return None
    hay = ((t or '') + ' ' + (kws or '')).lower()
    for sym, (thr, names) in _c.MAJOR.items():
        if re.search(r'(?<![a-z])' + sym.lower() + r'(?![a-z])', hay) or any(n in hay for n in names):
            return (thr, sym)
    return None


# 11-09:主流币关口写法「跌破7.4万/站上8万美元/突破10万」是价格腿(lint 原先只认 %,报缺价格)
KEYLEVEL = re.compile(r'(跌破|站上|突破|失守|收复|重回|升破)\s*[0-9.]+\s*(万|千|k|K)?\s*(美元)?')
STAGE_HL = re.compile(r'(\d+\s*个?月|[0-9一二三四五六七八九十]+月(上旬|中旬|下旬|初|底)?|年内|今年)以来(新低|新高|最低|最高)|\d+\s*个月(新低|新高)')


def lint_title(t, domain='crypto'):
    out=[]
    pp, big = pure_price(t)
    if pp:
        th = 10.0 if domain=='tradfi' else CRYPTO_LINE
        _mj = major_line(t) if domain != 'tradfi' else None
        if _mj:   # 11-09:BTC/ETH 纯行情线 5%/7%
            th = _mj[0]
        _ix = idx_line(t) if domain == 'tradfi' else None
        if _ix:   # 11-06 用户定:指数过 IDX 线必有题——指数不套个股 10% 线
            th = _ix[0]
            if big >= th:
                out.append(('INFO','双要素-指数过线',f'指数题 {_ix[1]} {big:g}% ≥ IDX 线 {th:g}%:11-06 用户定三大指数过线必建,不写弃建','11-06 coverage.IDX'))
                th = None
        if th is not None and big < th: out.append(('WARN','双要素-缺诱因',f'纯价格标题(只有标的+价格),幅度 {big:g}% < {th:g}%({domain} 线);除 meme豁免/纯行情-A定则 外须写出可指名的诱因——豁免与否机器判不了,判据列须写明','v3.5.4 gates 闸:双要素'))
        elif th is not None: out.append(('INFO','双要素-纯价格',f'纯价格标题靠幅度 {big:g}% ≥ {th:g}% 过闸;有诱因仍应写上','v3.5.4'))
    elif big is None and KEYLEVEL.search(t) and major_line(t):   # 只认主流币关口;「注册用户突破100万」不是价格
        out.append(('INFO','双要素-关口价格腿',f'关口读数「{KEYLEVEL.search(t).group(0)}」作价格腿(11-09)' + ('' if STAGE_HL.search(t) else ';主流币纯行情题须再写阶段新高/新低'),'11-09 主流币线'))
    elif big is None and MACRO_LEG.search(t):
        out.append(('INFO','双要素-宏观定价腿',f'宏观定价读数「{MACRO_LEG.search(t).group(0)}」作价格腿(11-07 同步:利率期货/债市定价读数合规)','11-07 review-agent 豁免'))
    elif big is None and not FORECAST.search(t):
        out.append(('WARN','双要素-缺价格',f'标题没有价格腿(涨跌%/报X/持平);除监管/上架豁免与预告题外须实测补上——「没拉所以不写」不是理由','v3.5.4 gates 闸:双要素'))
    n=len(t)
    if n>30: out.append(('FAIL','标题长度',f'{n}字>30 硬上限(09-02用户点名后升FAIL),目标20-28;主语+动作+≤2数字锚,其余证据不进标题','v2.9.33/81b'))
    if CORP.search(t): out.append(('FAIL','法人全名','带法人后缀的全称一律换 ticker(中文常用简称除外)','v2.9.43'))
    tk=collections.Counter(TICKER.findall(t)); d=[k for k,v in tk.items() if v>1]
    if d: out.append(('WARN','同标的重复',f'{",".join(d)} 在标题出现>1次,同一标的只出现一次','v2.9.43'))
    if DOLLAR.search(t): out.append(('INFO','样式','去掉 $ 前缀,直接写 ticker','样式'))
    if QUESTION.search(t): out.append(('FAIL','疑问句','去掉问号/悬念后不是「可核事件+标的」→撤;是硬事件→改陈述句','v2.9.68'))
    m=PSEUDO.search(t)
    if m: out.append(('WARN','伪诱因',f'「{m.group(0)}」只复述价格不是原因;板块普跌类仅板块级(≥4标的同向窄带)可作A定则播报,单标的=伪诱因','v2.9.35/48/53'))
    if domain=='tradfi' and PCT.search(t) and not SESSION.search(t) and not (H24.search(t) and ALLDAY.search(t)):
        out.append(('WARN','时段前缀','美股/亚股价格须带 盘前/盘中/收涨跌/盘后/夜盘/尾盘/午盘;无前缀默认读作收盘——确认确是收盘价','v2.9.54①'))
    if CLOSEFIX.search(t): out.append(('INFO','收盘定稿','「收涨/收跌」只在该时段收盘后允许;盘中只许区间/振幅或点值+「盘中」戳','v2.9.80'))
    m=WINDOW.search(t)
    if m and not re.search(r'\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}(至\d{1,2})?日', t): out.append(('INFO','窗口题',f'「{m.group(0)}」把主张绑死在建题时刻,过期后数字不改(gate.sh 过期题)','v2.9.62'))
    m=RELATION.search(t)
    if m: out.append(('INFO','关系型修饰',f'「{m.group(0)}」须当场校验(52w高低/源原句),复查时单独验关系是否仍成立','v2.9.30/40/10'))
    m=CAUSAL.search(t)
    if m: out.append(('WARN','因果连接词',f'「{m.group(0)}」须有源直接说出这句归因;把它换成「同时」念一遍,信息量不减=硬加的','v2.9.51/52'))
    if FORECAST.search(t): out.append(('INFO','预告题','豁免价格反应腿,禁拿事件前价格充数;同轮 event.sh add 挂承接','v2.9.57/65'))
    if AMOUNT.search(t): out.append(('INFO','量级自洽','写绝对金额前用市值除一次:成交额/市值>20倍、单日资金流/市值>50% 先当自己算错','v2.9.59'))
    return out

def fmt(rows):
    return '\n'.join(f'{l}\t{g}\t{m}\t({v})' for l,g,m,v in rows)

def load_b0(path):
    d=json.load(open(path,encoding='utf-8'))
    # 裸列表也要认:v3.3.1 用裸列表夹具测 ⑦ 时才发现这里对 list 调 .get 直接崩——生产 b0-latest.json 是字典所以两个月没触发。
    if isinstance(d,list): return d
    return d.get('topics') or d.get('data') or []

def us_session_open(now_utc=None):
    """v3.4.8 美股常规时段是否正在进行(09:30-16:00 ET = 夏令时 13:30-20:00 UTC / 冬令时 14:30-21:00 UTC)。
    只按工作日+UTC 时钟判,**不查节假日**——误报的代价只是多提示我核一次价,漏报才是真问题,故取两令时并集宁宽勿窄。
    TS_NOW_UTC=YYYY-MM-DDTHH:MM 可注入,供 run-tests.sh 两分支回归。"""
    env=os.environ.get('TS_NOW_UTC')
    if env:
        try: now_utc=datetime.datetime.strptime(env,'%Y-%m-%dT%H:%M')
        except Exception: now_utc=None
    if now_utc is None: now_utc=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    if now_utc.weekday()>=5: return False
    mins=now_utc.hour*60+now_utc.minute
    return 13*60+30 <= mins < 21*60

NON_US = re.compile(r'KOSPI|KOSDAQ|创业板|沪深|上证|深证|科创|恒指|恒生|港股|日股|A股|日经|韩股|台股|欧股|富时|DAX')
NON_US_KW = re.compile(r'\.(KS|KQ|T|HK|SS|SZ|TW)\b|^\d{4,6}$')


def us_close(t):
    """10-31 周报③:🔔 盘中进行时是「美股盘中拉价核收盘题」,亚股/欧股收盘题在美股盘中不交易,拉不到盘中价,
    名单每轮多 2~3 条噪声(KOSPI 10000003403/创业板 10000003414/村田 10000003415)。标题市场词或关键词交易所后缀命中即排除。"""
    if NON_US.search(t.get('title') or ''):
        return False
    kws = [k.strip() for k in re.split(r'[,，]', t.get('keywords') or '') if k.strip()]
    return not any(NON_US_KW.search(k) for k in kws)


def bell_fresh(age_h_, now_utc=None):
    """v3.7.19(10-28 影子跑 1027-2200):🔔 盘中进行时只管「收盘价仍是最近一次收盘」的题——建题在上一个交易日收盘(取 19:30 UTC,
    两令时里早的那个收盘再提前半小时)之后。更早的题已跨过一整场 session,归过期题处置表(数字不改、幅度衰减不是撤因),
    不进本块:10-27 22:00 Evose 照「不分题龄」把 10-23 的 CRDO/BE/COHR 收跌题按盘中反涨撤了。"""
    env=os.environ.get('TS_NOW_UTC')
    if env:
        try: now_utc=datetime.datetime.strptime(env,'%Y-%m-%dT%H:%M')
        except Exception: pass
    if now_utc is None: now_utc=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    if age_h_ is None: return True
    d=now_utc.date()-datetime.timedelta(days=1)
    while d.weekday()>=5: d-=datetime.timedelta(days=1)
    cut=datetime.datetime.combine(d, datetime.time(19,30))
    return now_utc-datetime.timedelta(hours=age_h_) >= cut

def age_h(created, now):
    try: c=datetime.datetime.strptime(created,'%Y-%m-%d %H:%M:%S')
    except Exception: return None
    return (now-c).total_seconds()/3600

def created_ids(actions_path):
    # v3.7.0 建题 id 解析收归 ledger.py:09-24 起 create 行 id 记成「-」,这里原样收「-」,
    #   于是 b0-audit ⑤「系统建 status=0 且非我建」把我自己当轮建的题全列进去(10-15 首扫 5 条新题都在 ⑤ 里)。
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ledger
        return ledger.created_ids(actions_path)
    except Exception:
        s=set()
        if not os.path.exists(actions_path): return s
        for l in open(actions_path,encoding='utf-8'):
            if l.startswith('#'): continue
            p=l.rstrip('\n').split('\t')
            if len(p)>=3 and p[1]=='create': s.add(str(p[2]))
        return s


def hot_families(tp):
    """⑦ 的核心:≤HOT_WINDOW_H 内按拉丁 token 连通聚成实体族,返回 [(共享key集, 成员id列表)],只含 ≥HOT_MIN 的族。
    抽成函数是为了让 ③ 聚簇在打印前就知道哪些簇属于热点族——否则 ③ 会对切面题喊「留超集」,
    下一轮 AUTO 照它撤切面题(v3.3.1 建完 4 个切面当轮就撞上了这个冲突)。"""
    _majors=set()
    try: _majors={m.upper() for m in json.load(open(os.path.expanduser('~/.trend-scout/majors.json')))['majors']}
    except Exception: pass
    _stop={'USDT','USD','USDC','ETF','CEO','THE','AND','FOR','NEW','TOKEN','COIN','CHAIN','SWAP','MEME','MEMES',
           'SPOT','PERP','DEX','CEX','DAT','NFT','DEFI','WEB3','APP','PRO','MAX','ONE','TOP','ALL'}|_majors
    _recent=[t for t in tp if t.get('_age') is not None and t['_age']<=HOT_WINDOW_H]
    def _toks(t):
        blob=(t.get('title') or '')+' '+(t.get('keywords') or '')
        out=set()
        for m in re.findall(r'[A-Za-z0-9][A-Za-z0-9.]{2,}', blob):
            k=m.upper().strip('.')
            # v3.3.8:剔除「数字+单个时间单位」形态(24H/12H/48H/7D/30D/1W/3M…)。
            #   正则允许数字开头本是为了认 4Stock→4STOCK,副作用是把标题里的「24h」也抽成了实体 ticker。
            #   而「24h」是本 skill 标题的高频固定写法(窗口题闸鼓励写 24h),09-09 实测误把
            #   12193「USELESS上线Upbit,24h涨29%」与 12202「4Stock 24h涨超14倍」聚成实体族 [24H],
            #   把 ⑦ 这道最滞后的兜底信号污染成噪音。用形态判而不是列停用词,免得漏 72H/90D 之类。
            if re.fullmatch(r'\d+[HDWMY]', k): continue
            if len(k)>=3 and k not in _stop and re.search(r'[A-Z]',k): out.add(k)
        return out
    _tk={str(t['id']):_toks(t) for t in _recent}
    def _link(a,b):
        for x in a:
            for y in b:
                if x==y or (len(x)>=3 and len(y)>=3 and (y.startswith(x) or x.startswith(y))): return x if len(x)<=len(y) else y
        return None
    _par={i:i for i in _tk}
    def _f(i):
        while _par[i]!=i: _par[i]=_par[_par[i]]; i=_par[i]
        return i
    _shared=collections.defaultdict(set); _ids=list(_tk)
    for a in range(len(_ids)):
        for b in range(a+1,len(_ids)):
            k=_link(_tk[_ids[a]],_tk[_ids[b]])
            if k:
                ra,rb=_f(_ids[a]),_f(_ids[b])
                if ra!=rb: _par[ra]=rb
                _shared[_f(_ids[a])].add(k)
    _comp=collections.defaultdict(list)
    for i in _ids: _comp[_f(i)].append(i)
    _shared2=collections.defaultdict(set)
    for r,ks in _shared.items(): _shared2[_f(r)]|=ks
    _byid={str(t['id']):t for t in _recent}
    out=[]
    for root,members in sorted(_comp.items(), key=lambda x:-len(x[1])):
        if len(members)<HOT_MIN: continue
        out.append((_shared2.get(root,set()), sorted(members, key=lambda i:_byid[i].get('created_at',''))))
    return out

def audit(path, since=None):
    # v3.7.19 补用例时发现:题龄用本机时钟、🔔 判盘中/收盘切点用 TS_NOW_UTC,注入时两个时钟对不上(v3.5.3 用例靠 >48h 列表碰巧通过)
    _tsnow=os.environ.get('TS_NOW_UTC')   # 别叫 _ts:audit() 里已有同名 helper
    try: now=datetime.datetime.strptime(_tsnow,'%Y-%m-%dT%H:%M')+datetime.timedelta(hours=8) if _tsnow else datetime.datetime.now()   # created_at 是 CST
    except Exception: now=datetime.datetime.now()
    tp=load_b0(path)
    mine=created_ids(os.path.expanduser('~/.trend-scout/actions.tsv'))
    rows=[]
    for t in tp:
        t['_age']=age_h(t.get('created_at',''),now)
    def hdr(s): rows.append(f'\n== {s} ==')
    # 1 待审积压
    hdr('① 待审积压 status=1/2(收尾必须 0)')
    pend=[t for t in tp if t.get('status') in (1,2)]
    for t in pend: rows.append(f"  {t['id']}  {t['_age']:.1f}h  {t['title']}")
    if not pend: rows.append('  (无)')
    online=[t for t in tp if t.get('status')==0]
    # 2 窗口题
    hdr('② 窗口题 >48h(必已过期→gate.sh 过期题:数字不改,只按单条撤因撤)')
    def _stale(t):
        if not (t['_age'] and t['_age']>48): return False
        if re.search(r'\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}(至\d{1,2})?日', t['title']): return False  # 带日期锚=预告题
        if WINDOW.search(t['title']): return True
        # v3.1.8 时效数字断言只对 crypto 判过期;tradfi 见下方边界说明
        return t.get('domain')=='crypto' and bool(STALE.search(t['title']))
    # v3.6.0(09-26 用户定「过期的题不用再继续改价」):已过 closed_ts 的题不进改价待办,只报个数
    _now_ms=float(os.environ.get('NOW_MS') or time.time()*1000)
    _expired=lambda t: bool(t.get('closed_ts')) and float(t['closed_ts'])<_now_ms
    w_all=[t for t in online if _stale(t)]
    w=[t for t in w_all if not _expired(t)]
    for t in w: rows.append(f"  {t['id']}  {t['_age']:.0f}h  {t['title']}")
    if not w: rows.append('  (无)')
    _ne=len(w_all)-len(w); _ot=sum(1 for t in online if _expired(t))
    if _ot: rows.append(f"  ── 在线题中已过 closed_ts {_ot} 条(其中窗口题 {_ne} 条):不改价(v3.6.0);事实错误/反转仍按撤题走 ──")
    nt=[t for t in online if t.get('domain')=='tradfi' and t['_age'] and t['_age']>48 and not WINDOW.search(t['title']) and STALE.search(t['title']) and not _expired(t)]  # v3.6.0 过期不改价
    if nt:
        rows.append(f"  ── 另有 {len(nt)} 条 tradfi 价格定稿题 >48h,**本段不判它们过期**(v3.1.8 边界) ──")
        rows.append("     判据在 gates 闸:时段 v2.7.8:tradfi 收盘价要看 create_at 之后有没有跨过一次美股 09:30-16:00 ET session;")
        rows.append("     没跨过(周末/节假日/盘后)则收盘价仍是最新事实。跨没跨过要自己看 _quote_snapshot_as_of,机审不判。")
        for t in nt[:6]: rows.append(f"     · {t['id']} {t['_age']:.0f}h {t['title'][:38]}")
        if len(nt)>6: rows.append(f"     · …另 {len(nt)-6} 条")
    # v3.5.3(09-21 自审发现) 🔔 盘中进行时独立成块,扫**全部**在线 tradfi 收盘价题,不再挂在 >48h 列表里。
    #   v3.4.8 原实现把提示塞进「>48h tradfi 边界列表」,而规则原文是「对每条 tradfi 收盘价题」不限题龄。
    #   首次真实触发(09-21 22:37 CST)就漏了:🔔 列出的5条(>48h)逐条核后0条触发,真正该触发的
    #   10000002963 BE(13h,题写「收跌5.4%」、盘中+2.09%)因为<48h根本没被列出,是我手工补抓的。
    if us_session_open():
        CLOSE=re.compile(r'收(涨|跌)|收盘')
        cl0=[t for t in online if t.get('domain')=='tradfi' and CLOSE.search(t.get('title') or '') and us_close(t)]   # 10-31:非美股收盘题不进🔔
        cl=[t for t in cl0 if bell_fresh(t.get('_age'))]   # v3.7.19:跨过 session 的老收盘题不进本块
        if cl:
            rows.append(f"  🔔 v3.4.8/v3.5.3 盘中进行时:美股常规时段正开着,以下 {len(cl)} 条「收涨/收跌」题说的是上一次收盘(建于上一交易日收盘后):")
            rows.append("     **逐条拉一次盘中价**:方向与标题相反 且 盘中幅度≥2% → 当场改盘中口径或撤;同向或反向<2% → 不动,等收盘定稿")
            for t in cl: rows.append(f"     · {t['id']} {t['_age']:.0f}h {t['title'][:40]}")
        if len(cl0)>len(cl):
            rows.append(f"  （另 {len(cl0)-len(cl)} 条收盘题建于上一交易日收盘前,已跨过一整场 session=过期题,按 gate.sh 过期题处置表:数字不改、盘中反向不是撤因——v3.7.19）")
    # 3 聚簇
    fams=hot_families(tp); hot_ids={m for _,ms in fams for m in ms}   # v3.3.1:③ 打印前先知道热点族
    hdr('③ 同标的聚簇 ≥2(v2.9.63: 留超集,盘前题被同日收盘题覆盖;🔥 标记的簇属热点族→按切面判,见 gate.sh 大热点) —— ticker 型')
    idx=collections.defaultdict(list)
    for t in online:
        # v3.4.9:同一条题的 keywords 里 ZAMA/Zama 会 upper 成同一个键,不按题去重就把它 append 两次,
        #   ③ 于是出 [ZAMA]×2 而两行是同一个 id(09-20 实录 12512「Zama机密金库扩至21个」keywords=ZAMA,Zama,…),
        #   聚簇组 g 也跟着虚增,审核员会照着假簇去判「留超集」。
        seen=set()
        for k in re.split(r'[,，]', t.get('keywords') or ''):
            k=k.strip()
            if len(k)<2: continue
            ku=k.upper()
            if ku in seen: continue
            seen.add(ku); idx[ku].append(t)
    g=0; generic=[]
    for k,ts in sorted(idx.items(), key=lambda x:-len(x[1])):
        if len(ts)<2: continue
        if TICKERKW.match(k):
            g+=1
            _tag=' 🔥热点族·按切面判,不按留超集' if any(str(t['id']) in hot_ids for t in ts) else ''
            rows.append(f"  [{k}] ×{len(ts)}{_tag}")
            for t in ts: rows.append(f"      {t['id']}  {t['_age']:.0f}h  {t['title'][:60]}")
        else: generic.append(f"{k}×{len(ts)}")
    if not g: rows.append('  (无)')
    if generic: rows.append('  ·泛词同主题(板块/宏观词,仅提示不算聚簇): '+', '.join(generic))
    # 4-6 标题机械闸(在线+待审)
    hdr('④ 在线/待审标题机械闸命中(FAIL/WARN;「标题长度」单独折叠计数,>45 字才逐条列)')
    hits=0; longn=0; longest=(0,None)
    for t in [x for x in tp if x.get('status') in (0,1,2)]:
        r=[x for x in lint_title(t['title'], t.get('domain','crypto')) if x[0] in ('FAIL','WARN')]
        n=len(t['title'])
        if n>30:
            longn+=1
            if n>longest[0]: longest=(n,t['id'])
        r2=[x for x in r if x[1]!='标题长度' or n>45]
        if r2:
            hits+=1; rows.append(f"  {t['id']} s={t['status']} {t['_age']:.0f}h {t['title'][:50]}")
            for l,gname,m,v in r2: rows.append(f"      {l} {gname}: {m[:70]} ({v})")
    if not hits: rows.append('  (无)')
    rows.append(f"  ·标题长度>30 字: {longn} 条(最长 {longest[0]} 字 id={longest[1]}) —— v2.9.33 硬上限 30/目标 20-28")
    # 7 系统建 status=0 新题
    hdr('⑤ 系统建 status=0 且非我建(过双要素闸;--since 后建的)')
    sysnew=[t for t in online if str(t['id']) not in mine and (since is None or _ts(t.get('created_at'))>since)]
    for t in sysnew: rows.append(f"  {t['id']}  {t['_age']:.1f}h  {t['title']}")
    if not sysnew: rows.append('  (无)')
    # ⑥ 灌水形态机械撤候选(v2.9.83):待审 + 系统新建 里无价格腿且命中形态的,给撤因;只列不撤,执行用 b0-cull.py
    # v3.1.5(提案5-2) 价格动作前置检查:形态命中 ≠ 可撤。A闸铁律「有真实价格动作一律留」优先于形态判定——
    #   09-06 实录 12069(ARB) 被列进 vanity 撤候选而当时 ARB 24h +44%,照单执行就是误撤。
    #   crypto 阈值 ±50%(CRYPTO_LINE,11-06 由30%上调)(与 meme 豁免① 同门槛)、tradfi ±10%(与双要素幅度闸同门槛);拿不到行情=「未检查」,仍留在候选里但标注。
    try:
        import quotes as _q; QMAP=_q.load()
    except Exception:
        QMAP={}
    def _mv(t):
        """返回 (是否有真实价格动作, 说明, 前置检查是否真的跑成了)。
        v3.4.9 补第三个返回值 checked:整张行情表都没拉到 = 一条都没查成,与「查过了、没到阈值」
        在输出里以前长得一样,⑥ 照样给出可直接执行的 b0-cull.py 批量命令,
        与 v3.1.5 立这道前置闸的本意(防误撤)相反。
        「标的未在行情表内」算查过了(表拉到了、标的不在表上=没有真实价格动作,09-06 规则);
        tradfi 算没查成(v3.4.10:okx 不覆盖 tradfi,从来就没验过价)。"""
        if not QMAP: return (False,'行情不可得',False)          # 整表没拉到=一条都没查
        # v3.4.10(用户 09-20 定):okx 行情源本就不覆盖 tradfi,这类候选从来没被价格验证过,
        #   与「整表没拉到」同型,一并算没查成 —— 照列但不进可执行的批量撤题命令。
        if t.get('domain')!='crypto': return (False,'tradfi 无行情源',False)
        blob=f"{t.get('title','')} {t.get('keywords','')}".upper()
        best=None
        for tk in set(re.findall(r'[A-Z]{2,10}', blob)):
            v=QMAP.get(tk)
            if v is not None and (best is None or abs(v)>abs(best[1])): best=(tk,v)
        # 表拉到了、标的不在表上 = 查过了,没有真实价格动作(09-06 规则,run-tests 8002 用例守着)
        if best is None: return (False,'标的未在行情表内',True)
        tk,v=best
        return (abs(v)>=CRYPTO_LINE, f'{tk} 24h {v:+.1f}%', True)
    hdr('⑥ 灌水形态机械撤候选(v2.9.83: 无价格腿+形态命中;v3.1.5 已剔除有真实价格动作的;执行用 b0-cull.py)')
    if not QMAP:
        rows.append('  ⚠️ 行情表为空,本轮价格前置检查整段没跑成(quotes.py 拉不到时的降级)——下面每条都带「未检查」,不给批量命令,逐条实测再定。')
    cand=collections.defaultdict(list); spared=[]; hard=[]
    for t in pend + sysnew:
        jc=junk_class(t['title'])
        if not jc: continue
        he=hard_event(t['title'])
        if he: hard.append((t,jc[0],he)); continue   # v3.6.6 硬事件不进机械撤
        moved,why,checked=_mv(t)
        if moved: spared.append((t,jc[0],why)); continue
        cand[jc[0]].append((t,jc[1],why,checked))
    nj=0; nck=0
    for rcode,items in cand.items():
        for t,why,mv,ck in items:
            nj+=1
            if not ck: nck+=1
            rows.append(f"  {t['id']} s={t['status']} {t['_age']:.1f}h [{rcode}] {t['title'][:48]}  ←{why} ｜{mv}{'' if ck else ' ⚠️未检查'}")
        # v3.4.9:只有价格前置检查真的跑成的那几条才给可直接执行的批量命令。
        #   没查成的照列(v3.1.5「仍留在候选里但标注」),但不进命令行——否则 ⚠️ 只是一行提示,
        #   而下一行就是能直接粘贴执行的撤题命令,09-20 实录审核员正是逐条查腿后判定两条都不该撤。
        ok=[t for t,_,_,ck in items if ck]
        if ok:
            rows.append(f"    $ ~/.trend-scout/b0-cull.py --rc {rcode} --note '机审⑥形态命中' "+' '.join(str(t['id']) for t in ok))
        no=[t for t,_,_,ck in items if not ck]
        if no:
            rows.append(f"    ⚠️ 另 {len(no)} 条价格前置检查没跑成,不给批量命令——逐条实测价格动作,确认无真实价格动作再自己撤: "+' '.join(str(t['id']) for t in no))
    if not nj: rows.append('  (无)')
    if hard:
        rows.append(f'  ── v3.6.6 硬事件词命中 {len(hard)} 条,不进批量撤命令——逐条人判(有标的补价格腿,无标的再撤) ──')
        for t,rcode,he in hard:
            rows.append(f"    ✋ {t['id']} s={t['status']} [形态:{rcode}|硬事件:{he}] {t['title'][:44]}")
    if spared:
        rows.append(f'  ── v3.1.5 已剔除 {len(spared)} 条(形态命中但有真实价格动作,A闸「一律留」优先)——这些要改标题不要撤 ──')
        for t,rcode,mv in spared:
            rows.append(f"    ✋ {t['id']} s={t['status']} [{rcode}] {t['title'][:44]}  ←{mv}")
    # 8 射程
    le8=[t for t in online if t['_age'] is not None and t['_age']<=8]
    # 11-07 用户定(Q11=B):23:00 轮建的题到次日 09:40 已隔 10h40m、超出 8h 射程,一次复审都没有——
    #   早间轮(08:00–12:00)把前一晚 22:30 以后建的在线题一并纳入射程(只扩这一段,8h 判据本身不动)
    ovn=[]
    if 8 <= now.hour < 12:
        _cut=(now-datetime.timedelta(days=1)).replace(hour=22,minute=30,second=0,microsecond=0).strftime('%Y-%m-%d %H:%M')
        ovn=[t for t in online if t['_age'] is not None and t['_age']>8 and (t.get('created_at') or '')[:16]>=_cut]
        hdr('⓪ 隔夜补射程(Q11:前晚 23:00 轮建题,超 8h 但本轮须过一遍——按 ≤8h 射程处置)')
        for t in ovn: rows.append(f"  {t['id']} s={t['status']} {t['_age']:.1f}h  {t['title'][:56]}")
        if not ovn: rows.append('  (无)')
    le8=le8+ovn
    # ⑦ 热点候选(v3.3.1 — 09-08 用户「4stock其实是今天的大热点」):按实体连通抓跨 ticker 的同一事件族。
    #   计算在 hot_families();这里只打印。信号=HOT_RULE;含已撤——建题密度本身就是信号。
    #   只列不动:这是「切换到热点模式」的触发器(判据在 gates 闸:大热点)。已知边界:v1 只抓拉丁 token。
    hdr('⑦ 热点候选(v3.3.1: '+HOT_RULE+';含已撤;判据→gate.sh 大热点)')
    _byid={str(t['id']):t for t in tp}
    hot=0
    for keys,members in fams:
        hot+=1
        rows.append(f"  🔥 实体族 [{'/'.join(sorted(keys))[:60]}] ×{len(members)} —— 切换热点模式:先画实体图,取价走到 dexscreener,找一手解释源,按切面立题")
        for m in members:
            t=_byid[m]; rows.append(f"      {t['id']}  s={t.get('status')}  {t['_age']:.1f}h  {t['title'][:56]}")
    if not hot: rows.append('  (无)')
    rows.append(f"\nAUDIT: 在线={len(online)} ≤8h={len(le8)}(含隔夜{len(ovn)}) 待审={len(pend)}(s2={sum(1 for t in pend if t.get('status')==2)},s1={sum(1 for t in pend if t.get('status')==1)}) 窗口题={len(w)} 聚簇组={g} 标题命中={hits} 超长={longn} 系统新建={len(sysnew)} 机械撤候选={nj}(未检查={nck}) 热点候选={hot}")
    return '\n'.join(rows)

def _ts(created):
    try: return int(datetime.datetime.strptime(created,'%Y-%m-%d %H:%M:%S').timestamp()*1000)
    except Exception: return 0

if __name__=='__main__':
    a=sys.argv[1:]
    if not a or a[0] not in ('title','b0'):
        print(__doc__ or 'usage: lint.py title <标题> [domain] | b0 <json> [--since ms]'); sys.exit(2)
    if a[0]=='title':
        t=a[1]; dom=a[2] if len(a)>2 else 'crypto'
        r=lint_title(t,dom)
        print(fmt(r) if r else 'OK\t全闸通过')
        sys.exit(1 if any(x[0]=='FAIL' for x in r) else 0)
    else:
        since=None
        if '--since' in a: since=int(a[a.index('--since')+1])
        print(audit(a[1], since))
