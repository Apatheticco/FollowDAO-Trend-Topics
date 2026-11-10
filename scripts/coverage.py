#!/usr/bin/env python3
"""coverage.py — 漏建对账(v3.7.1):过线的涨跌,要么有题、要么有弃建记录,否则报「漏」。第一个衡量漏建的数。

为什么:此前所有指标只量「建错了没有」,不量「该建的建了没有」——少建题,每个指标都会变好。
病例(10-15 首扫):系统题「遭遇证券法违规诉讼，AST SpaceMobile Inc.跌10%」原因写错,我撤得对,
  但 ASTS 当日真跌 10.5% 且有出处(247wallst「Piper Sandler Cuts Target to $54 on SpaceX Competition」),
  撤后既没按真因另建、也没落弃建——这种「撤了错题就忘了真事」只有对账看得见。

股票池(不用全市场涨跌榜:FMP 榜单被小盘股和杠杆 ETF 占满,10-15 实测前 10 名无一可写):
  美股/亚股 = channels.json 板块矩阵 ＋ 近 36h 看板题(任何状态,含系统建、已撤)关键词里的 ticker;Yahoo 日线算涨跌,|x| ≥ 10% 过线
  币       = 币安 USDT 永续 24h 成交额 ≥ 2000 万美元且 |24h| ≥ 30%;其中成交 <1 亿且无题无弃建的记「低量弃建」不算漏(v3.7.9 用户定)
指数/板块 ETF(10-30 retro)= IDX 表各自的线(QQQ ±2.5%、SPY ±2%、SOXX ±5%);个股线 10% 永远框不住指数级大跌。
「有题」= 近 36h status=0 的题关键词/标题里有该 ticker 或公司名;「弃建」= 近 36h 台账 note 含「弃建|<ticker 或名>」。

突发事件(11-10):~/news-alert 强关联入选事件也进对账(见 NEWS_DB 段),行首「突发」。
用法: coverage.py [--hours 36]      末行 COVERAGE: 过线=N 有题=a 弃建=b 漏=c
处置: 漏的逐条 建(topic.py create) 或 弃建(log-action.sh note - 留档 "弃建|<标的>|<原因>|<日期>"),重跑到 漏=0。
注入(回归): COVERAGE_QUOTES=<json {ticker:[last,prev,"EQUITY"]}> COVERAGE_BN=<json 币安24h列表> B0JSON ACTIONS CHANNELS NEWS_ALERT_DB。
"""
import json, os, re, subprocess, sys, time, datetime
COIN_LINE = float(os.environ.get('TS_CRYPTO_LINE', '50'))   # 11-06 用户定:crypto 纯行情线 30%→50%(与 topic.CRYPTO_LINE 同值)
from concurrent.futures import ThreadPoolExecutor

D = os.path.expanduser('~/.trend-scout')
sys.path.insert(0, D)
TK = re.compile(r'^(?:[A-Z]{1,5}(?:\.[A-Z]{1,2})?|\d{4,6}\.(?:KS|KQ|T|TW|HK|SS|SZ))$')
NOT_TICKER = {'AI', 'CPI', 'PPI', 'GDP', 'ETF', 'IPO', 'WTI', 'USD', 'KOSPI', 'HBM', 'DRAM', 'CEO', 'SEC', 'FED', 'OI', 'TVL', 'RWA', 'NFT'}
CORP = re.compile(r'\b(inc|corp|corporation|ltd|limited|holdings|co|plc|class a|ordinary shares)\b\.?', re.I)
BLIND = []
# 10-30 retro:费半ETF -7.4%、纳指 -3% 无题无弃建,复审员才抓到——个股池按 |x|≥10% 对账,指数级大跌永远进不了线。
# 这是对账线(过线=要么建、要么写弃建理由),不是建题线;建题仍按 gates 双要素/诱因质量判
IDX = {'QQQ': (2.5, {'纳指', '纳斯达克', 'nasdaq'}), 'SPY': (2.0, {'标普', 's&p'}), 'DIA': (2.0, {'道指', '道琼斯', 'dow'}), 'SOXX': (5.0, {'费半', '费城半导体', 'soxx'}),
       # 11-05:KOSPI 收跌 5.3%、日经芯片链 -14% 都靠复审员补——亚洲三大指数 ±3% 进对账
       '^KS11': (3.0, {'kospi', '韩股'}), '^N225': (3.0, {'日经', '日股'}), '^HSI': (3.0, {'恒指', '恒生', '港股'}),
       # 11-09 用户定:台股加权 11-09 收涨 4.94% 无题——本机 14:58 轮与 Evose 17:30 轮都漏,因本表没有台股;同亚洲线 ±3%
       '^TWII': (3.0, {'台股', '台湾加权', '加权指数', 'taiex'}),
       # 11-09 用户定(周一上午榜单题少):美股期货周日 18:00 ET(周一 07:00 北京)开盘,期货过线同现货指数线对账——现货题(标普/纳指/道指)可覆盖
       'ES=F': (2.0, {'标普期货', '标普', 's&p'}), 'NQ=F': (2.5, {'纳指期货', '纳指', '纳斯达克', 'nasdaq'}), 'YM=F': (2.0, {'道指期货', '道指', '道琼斯', 'dow'})}
# 11-09 用户定(BTC 凌晨跌破 7.4 万创 8 月下旬以来新低、10 分钟爆仓数亿,因纯行情币线 50% 是按山寨定的、BTC 永远够不着而漏):
# 主流大币另设线——24h 涨跌 BTC ±5% / ETH ±7%,或创 MAJOR_DAYS 天(约 2 个月)新高/新低。单一定义在此,lint/topic 从这里读。
MAJOR = {'BTC': (5.0, {'比特币', 'bitcoin'}), 'ETH': (7.0, {'以太坊', 'ethereum'})}
MAJOR_DAYS = 60
LOWVOL = 1e8   # v3.7.9 纯行情币成交额下限(币安合约 24h,美元)
LOG = os.environ.get('COVERAGE_LOG') or os.path.join(D, 'coverage.log.tsv')

# 11-10 用户定(突发源对账):BWE/金十 不整条接进扫描(42h 1650 条、入选 3.5%,漏建主因是门槛与轮次间隔不是源),
# 改为读突发警报 ~/news-alert 已分级好的结果——强关联(linkage=3)入选事件,看板要么有题、要么有弃建。
# 当日实测:中美关税调整、谷歌 TPU 8、KKR 财报三件 L3 事件看板既无题也无弃建记录,别的漏建对账都看不到。
# 「有题」= 事件首条前 3h 起建的 status=0 题命中事件的**单名标的**(个股/山寨币)。指数/大宗/利率/汇率/BTC/ETH 这类宽标的
#   不认「有题」——首跑实测宽匹配会把中美关税调整算到『美股三大指数大涨』题、谷歌 TPU 算到 10h 前的黄仁勋题,正好盖住真漏;
#   宽标的事件已由别的题承接的,写「弃建|<event_key>|已由<题号>覆盖」。
# 「弃建」= 事件首条前 1h 起的台账 note 含「弃建|<event_key 或标的>」(宽标的也认,如『弃建|CL=F|…未过5%线』)。
NEWS_DB = os.environ.get('NEWS_ALERT_DB') or os.path.expanduser('~/news-alert/news.db')
NEWS_LINKAGE = int(os.environ.get('COVERAGE_NEWS_LINKAGE') or 3)
NEWS_ALIAS = {'WTI': {'cl=f', '原油', '美油', '油价'}, 'BRENT': {'bz=f', '布油', '布伦特', '原油', '油价'},
              'SPX': {'spy', '标普'}, 'NDX': {'qqq', '纳指', '纳斯达克'}, 'XAUUSD': {'gc=f', '黄金', '金价'},
              'DXY': {'美元指数'}, 'US10Y': {'美债'}, 'BTC': {'比特币', 'bitcoin'}, 'ETH': {'以太坊', 'ethereum'}}
NEWS_BROAD_MKT = {'index', 'commodity', 'rates', 'fx'}
NEWS_BROAD_SYM = {'BTC', 'ETH'}
NEWS_NOTE = []


def _iso_ts(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def news_events(hours, now=None):
    """突发库里近 hours 小时的强关联入选事件 → [(event_key, 首条时间戳秒, [(标的, market)], 标题)]。
    回归注入 NEWS_ALERT_DB;注入了 COVERAGE_QUOTES 却没注入它=旧用例,不读生产库。只读打开。"""
    if not os.environ.get('NEWS_ALERT_DB') and os.environ.get('COVERAGE_QUOTES'):
        return []
    if not os.path.exists(NEWS_DB):
        NEWS_NOTE.append(f'没有突发库 {NEWS_DB},突发对账跳过')
        return []
    import sqlite3
    now = now or int(os.environ.get('COVERAGE_NOW_MS') or time.time() * 1000) / 1000
    try:
        c = sqlite3.connect(f'file:{NEWS_DB}?mode=ro', uri=True)
        its = c.execute("SELECT event_key, ts, assets, text FROM items WHERE (keep=1 OR keep_ops=1) AND linkage>=? "
                        "AND COALESCE(event_key,'')!='' ORDER BY ts", (NEWS_LINKAGE,)).fetchall()
        hl = dict(c.execute("SELECT event_key, headline FROM events WHERE COALESCE(headline,'')!=''").fetchall())
        st = dict(c.execute("SELECT k, v FROM state WHERE k IN ('jin10_last_ts','tg_since')").fetchall())
    except Exception as e:
        NEWS_NOTE.append(f'突发库读取失败({str(e)[:80]}),突发对账跳过')
        return []
    last = max([x for x in (_iso_ts(v) for v in st.values()) if x] or [0])
    if last and now - last > 3600:
        NEWS_NOTE.append(f'突发库已 {int((now - last) / 60)} 分钟没更新(news-alert 停了?),突发对账可能缺事件')
    ev = {}
    for ek, ts, assets, text in its:
        t = _iso_ts(ts)
        if t is None:
            continue
        e = ev.setdefault(ek, [t, [], hl.get(ek) or re.sub(r'\s+', ' ', text or '')[:40]])
        e[0] = min(e[0], t)
        try:
            for a in json.loads(assets or '[]'):
                s = (a.get('symbol') or '').strip()
                if s and s not in [x[0] for x in e[1]]:
                    e[1].append((s, a.get('market') or ''))
        except Exception:
            pass
    return sorted([(k, v[0], v[1], v[2]) for k, v in ev.items() if now - v[0] <= hours * 3600], key=lambda r: r[1])


def _created_ts(t):
    try:
        return datetime.datetime.strptime(t['created_at'], '%Y-%m-%d %H:%M:%S').timestamp()
    except Exception:
        return 0


def news_covered(ek, t0, syms, tp, lrows):
    """事件对账:event_key 与全部标的找弃建;单名标的另找题(宽标的不认有题,见 NEWS_DB 段)。"""
    lv = [t for t in tp if t.get('status') == 0 and _created_ts(t) >= t0 - 3 * 3600]
    nts = [r[4] for r in lrows if r[0] >= (t0 - 3600) * 1000 and r[1] == 'note' and '弃建' in r[4]]
    keys = [(ek, set(), False)] + [(s, NEWS_ALIAS.get(s.upper(), set()), m in NEWS_BROAD_MKT or s.upper() in NEWS_BROAD_SYM)
                                    for s, m in syms]
    for s, names, broad in keys:
        v, ref = covered(s, names, [] if broad or s == ek else lv, nts)
        if v:
            return v, ref
    return None, None


def _curl(url):
    r = subprocess.run(['curl', '-sS', '--max-time', '15', '-A', 'Mozilla/5.0', url], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def norm_name(s):
    return re.sub(r'\s+', ' ', CORP.sub('', s or '')).strip(' .,').lower()


def b0_start(now=None, hours=36):
    """11-02 首扫:现拉看板只拉近 2 天,周一早上拉不到周五建的 AAOI/COHR/COIN/SOXX 题,股票窗口(stock_hours)放宽了也匹配不上→全报漏。
    起始日 = min(今天-2 天, 股票窗口起点的本地日期)。"""
    import datetime as _dt
    now = now or time.time()
    w = _dt.datetime.fromtimestamp(now - stock_hours(hours, now) * 3600).date()
    return min(_dt.date.fromtimestamp(now) - _dt.timedelta(days=2), w)


def b0():
    # 现拉看板(近 2 天),不读 b0-latest.json:那是开跑时的快照,本轮新建的题在里面看不到,会被误报成漏(10-15 14:52 轮首跑实证)
    p = os.environ.get('B0JSON')
    if not p:
        import tempfile, datetime as _dt
        p = os.path.join(tempfile.gettempdir(), 'coverage-b0.json')
        t = _dt.date.today()
        r = subprocess.run([sys.executable, os.path.join(D, 'b0-fetch.py'), b0_start().isoformat(), t.isoformat(), '--out', p],
                           capture_output=True, text=True)
        if r.returncode != 0:
            p = os.path.join(D, 'b0-latest.json')
            print('⚠️ 现拉看板失败,退回开跑快照(本轮新建题可能被误报成漏)')
    d = json.load(open(p, encoding='utf-8'))
    return d if isinstance(d, list) else d.get('topics') or []


def age_h(t):
    try:
        return (time.time() - datetime.datetime.strptime(t['created_at'], '%Y-%m-%d %H:%M:%S').timestamp()) / 3600
    except Exception:
        return 999


def stock_hours(hours, now=None):
    """11-01 首扫:周日对账把周五收盘 INTC/COIN/AAOI/COHR/SOXX/QQQ 全报「漏」——题都在,只是建于 >36h 前;周末/节假日
    最近一次美股收盘仍是最新事实。股票/指数行的匹配窗口放宽到「最近一次美股收盘(20:00 UTC,只认工作日) 往前 26h」,
    覆盖当天盘前/盘中/收盘题与前一晚盘后题;不短于 hours。币不受影响。"""
    now = now or time.time()
    d = datetime.datetime.utcfromtimestamp(now)
    close = d.replace(hour=20, minute=0, second=0, microsecond=0)
    if close > d:
        close -= datetime.timedelta(days=1)
    while close.weekday() >= 5:
        close -= datetime.timedelta(days=1)
    start = close.replace(tzinfo=datetime.timezone.utc).timestamp() - 26 * 3600
    return max(hours, (now - start) / 3600)


def matrix_tickers():
    p = os.environ.get('CHANNELS') or os.path.join(D, 'channels.json')
    c = next((x for x in json.load(open(p, encoding='utf-8'))['channels'] if x['key'].startswith('板块矩阵')), None)
    return set(re.findall(r'\b[A-Z]{2,5}\b', (c or {}).get('call', ''))) - {'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'ASML'} | {'ASML'}


# 10-15 retro:矿企/AI 算力托管板块 10-14 集体跌 12% 首扫漏建,对账池(矩阵+题 ticker)里没有它们,对账也没抓到
EXTRA = ['IREN', 'CIFR', 'WULF', 'CORZ', 'HUT', 'APLD', 'BTDR', 'MARA', 'RIOT', 'CLSK', 'CRWV', 'NBIS']
# 10-31 复审:QCOM 10-30 收 -11.1% 不在对账池(矩阵与近 36h 题里都没有它)——芯片大票补进池
EXTRA += ['QCOM', 'AMD', 'MU', 'AVGO', 'TXN', 'ARM', 'INTC', 'MRVL', 'SNDK', 'WDC', 'STX']
# 11-05:亚洲大票单名 ±10% 一直不在池里(丰田 +17%、爱德万 -15%、Lasertec -14% 都是复审员补的)——日韩港市值前列补进池
ASIA = ['7203.T', '6758.T', '6857.T', '8035.T', '6920.T', '285A.T', '9984.T', '6861.T', '9983.T', '7267.T', '8306.T', '6501.T',
        '4063.T', '6146.T', '7974.T', '005930.KS', '000660.KS', '042700.KS', '373220.KS', '006400.KS', '005380.KS', '035420.KS',
        '0700.HK', '9988.HK', '3690.HK', '1810.HK', '9618.HK', '1211.HK', '0981.HK']
EXTRA += ASIA


def yh_movers(min_cap=None, line=10.0):
    """11-05:对账池只认「矩阵+手写名单+看板已有 ticker」,熟人之外的美股大异动(DJT -25%、DOX -30%、FIS -24%、AEHR +27%)全靠复审员补。
    Yahoo 预设榜 day_gainers/day_losers(全市场,带市值)补进池:EQUITY、市值≥200 亿美元(11-05 用户定)、|涨跌|≥10%。
    注入 COVERAGE_YH=json 列表 [[sym,pct,cap,type],...];注入了 COVERAGE_QUOTES 而没注入它=回归旧用例,不联网返回空。"""
    inj = os.environ.get('COVERAGE_YH')
    if inj:
        raw = json.load(open(inj))
    elif os.environ.get('COVERAGE_QUOTES'):
        return []
    else:
        raw = []
        for sid in ('day_gainers', 'day_losers'):
            d = _curl(f'https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={sid}&count=100')
            try:
                qs = d['finance']['result'][0]['quotes']
            except Exception:
                BLIND.append(f'Yahoo {sid} 没取到')
                continue
            raw += [[q.get('symbol'), q.get('regularMarketChangePercent'), q.get('marketCap'), q.get('quoteType')] for q in qs]
    if min_cap is None:   # 11-05 用户定 A:市值 200 亿美元以上才单独对账(11-04 轮动日 ≥10 亿 118 只、≥200 亿 20 只);COVERAGE_YH_MINCAP 可覆盖
        min_cap = float(os.environ.get('COVERAGE_YH_MINCAP') or 2e10)
    out = []
    for sym, pct, cap, typ in raw:
        if sym and typ == 'EQUITY' and (cap or 0) >= min_cap and pct is not None and abs(pct) >= line:
            out.append(sym)
    return out


def universe(tp, hours):
    """{ticker: {名字集合}}"""
    u = {t: set() for t in matrix_tickers()}
    for t in EXTRA:
        u.setdefault(t, set())
    for t in tp:
        if age_h(t) > hours or t.get('domain') != 'tradfi':
            continue
        kws = [k.strip() for k in re.split(r'[,，]', t.get('keywords') or '') if k.strip()]
        tks = [k for k in kws if TK.match(k) and k not in NOT_TICKER]
        names = {norm_name(k) for k in kws if not TK.match(k) and re.search(r'[A-Za-z]{3}', k)}
        for k in tks:
            u.setdefault(k, set()).update(names if len(tks) == 1 else set())
    return u


def prev_close(rows, meta):
    """10-22 CRCL 误报 +10.2%:Yahoo 日线还没长出最新交易日那根时,最后一根就是昨收,原逻辑仍取倒数第二根(=前天收)。
    按交易所时区比对最后一根 K 线日期与 regularMarketTime 日期:同一天→前收取倒数第二根;不同天→最后一根就是前收。
    10-23 复盘:Yahoo 日线还会**缺中间一天**(10-22 早上 MTSI/ENTG/SVRN 缺 10-21 那根,倒数第二根是前天收,
    SVRN 报 +36% 实为 -3.9%)。取到的前收那根与「今天」之间隔着一个以上工作日 → 返回 None,由调用方改用 range=1d 的官方前收补。"""
    off = int(meta.get('gmtoffset') or 0)
    day = lambda ts: time.strftime('%Y-%m-%d', time.gmtime(int(ts) + off))
    rmt = meta.get('regularMarketTime')
    if rows and rmt and day(rows[-1][0]) != day(rmt):
        ref, cur = rows[-1], rmt
    elif len(rows) >= 2:
        ref, cur = rows[-2], rows[-1][0]
    else:
        return None
    if _weekday_gap(day(ref[0]), day(cur)) > 1:
        return None
    return ref[1]


def _weekday_gap(d0, d1):
    """d0 到 d1 之间相隔的工作日数(d1 当天算,d0 不算);相邻交易日=1,跨周末的周五→周一也=1。"""
    import datetime as _dt
    a, b = _dt.date.fromisoformat(d0), _dt.date.fromisoformat(d1)
    n, x = 0, a
    while x < b:
        x += _dt.timedelta(days=1)
        n += x.weekday() < 5
    return n


def prev_close_official(sym):
    """日线缺天时的兜底:range=1d 的 meta.chartPreviousClose 就是交易所官方前收。
    10-23 复盘先用过 5 天小时线末根,KER.PA 得 215.10、官方收盘 213.50——小时线不含收盘竞价,不可用。"""
    d = _curl(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d')
    try:
        return d['chart']['result'][0]['meta'].get('chartPreviousClose')
    except Exception:
        return None


def quote(sym):
    inj = os.environ.get('COVERAGE_QUOTES')
    if inj:
        q = json.load(open(inj)).get(sym)
        return tuple(q) if q else None
    d = _curl(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10d')
    try:
        r = d['chart']['result'][0]
        m = r['meta']
        rows = [(t, c) for t, c in zip(r.get('timestamp') or [], r['indicators']['quote'][0]['close']) if c is not None]
        cl = [c for _, c in rows]
        pc = prev_close(rows, m)
        if pc is None:
            pc = prev_close_official(sym)
        if pc is None:
            return None
        return (m.get('regularMarketPrice') or cl[-1], pc, m.get('instrumentType'))
    except Exception:
        return None


STALE = []


def stale_min(x):
    """同 pct.stale_min:币安 24hr 行情 closeTime 距今 >30 分钟＝冻结(下架结算/停牌)。没有 closeTime 当新鲜。COVERAGE_NOW_MS 注入回归用。"""
    try:
        ct = int(x['closeTime'])
    except Exception:
        return None
    now = int(os.environ.get('COVERAGE_NOW_MS') or time.time() * 1000)
    age = (now - ct) // 60000
    return age if age > 30 else None


def bn_equity():
    """11-03:币安 TradFi 股票永续(MVLL=2倍做多MRVL的ETF)混在 24hr 表里,被当币报「漏」。
    exchangeInfo 里 underlyingType=EQUITY 的剔除;注入 COVERAGE_BN_EQUITY=逗号分隔;取不到=不剔(保守)。"""
    inj = os.environ.get('COVERAGE_BN_EQUITY')
    if inj is not None:
        return {x.strip() for x in inj.split(',') if x.strip()}
    if os.environ.get('COVERAGE_BN'):
        return set()
    try:
        d = _curl('https://fapi.binance.com/fapi/v1/exchangeInfo')
        return {x['symbol'] for x in d.get('symbols', []) if x.get('underlyingType') == 'EQUITY'}
    except Exception:
        return set()


def bn_movers():
    inj = os.environ.get('COVERAGE_BN')
    d = json.load(open(inj)) if inj else _curl('https://fapi.binance.com/fapi/v1/ticker/24hr')
    out = []
    eq = bn_equity()
    if not isinstance(d, list):
        # 10-21 15:53 实测:币安限流返回 {"code":-1003,...} 字典,原逻辑逐字符迭代直接崩;改为标半盲,不得报「币侧漏=0」
        BLIND.append(f'币安24hr取数失败:{str(d)[:120]}')
        return out
    for x in d or []:
        s = x.get('symbol', '')
        if not s.endswith('USDT') or s in eq:
            continue
        try:
            pc, qv = float(x['priceChangePercent']), float(x['quoteVolume'])
        except Exception:
            continue
        _ml = MAJOR.get(s[:-4], (None,))[0]
        if (abs(pc) >= COIN_LINE and qv >= 2e7) or (_ml and abs(pc) >= _ml):   # 11-06 用户定 30→50;11-09 BTC/ETH 用 MAJOR 线
            age = stale_min(x)
            if age is not None:   # 10-21:下架结算的合约(EPICUSDT SETTLING)行情冻结,不算过线,单列提示
                STALE.append(f'{s[:-4]}({pc:+.1f}% 已 {age} 分钟没更新)')
                continue
            out.append((s[:-4], pc, qv))
    return out



def major_milestones(days=None):
    """11-09:主流大币创 MAJOR_DAYS 天新高/新低也算过线。比较对象=今天与昨天两根币安永续日线的最低/最高 vs 再往前 days 根日线的极值。
    返回 [(sym, '新低'|'新高', 极值, 对照日期)];取数失败记半盲。注入(回归):COVERAGE_KLINES=<json {sym:[[openTime,o,h,l,c],...]}>"""
    days = days or MAJOR_DAYS
    inj = os.environ.get('COVERAGE_KLINES')
    if not inj and os.environ.get('COVERAGE_BN'):   # 回归注入了币安榜却没给 K 线:不联网
        return []
    allk = json.load(open(inj)) if inj else None
    out = []
    for sym in MAJOR:
        k = (allk or {}).get(sym) if allk is not None else _curl(f'https://fapi.binance.com/fapi/v1/klines?symbol={sym}USDT&interval=1d&limit={days + 2}')
        if not isinstance(k, list) or len(k) < days + 2:
            if allk is None:
                BLIND.append(f'{sym} 日线取数失败(阶段新高低未核)')
            continue
        recent, prior = k[-2:], k[-(days + 2):-2]
        lo, hi = min(float(r[3]) for r in recent), max(float(r[2]) for r in recent)
        plo, phi = min(float(r[3]) for r in prior), max(float(r[2]) for r in prior)
        if lo < plo:
            out.append((sym, '新低', lo, datetime.datetime.fromtimestamp(int(prior[0][0]) / 1000).strftime('%m-%d')))
        if hi > phi:
            out.append((sym, '新高', hi, datetime.datetime.fromtimestamp(int(prior[0][0]) / 1000).strftime('%m-%d')))
    return out


def _dir(title):
    up, dn = bool(re.search(r'涨|走高|飙', title or '')), bool(re.search(r'跌|走低|下挫', title or ''))
    return 1 if up and not dn else (-1 if dn and not up else 0)


def _note_dir(note):
    """弃建备注的方向:原因段里第一个带符号的百分数(-30.63%)定方向,没有就看涨/跌字;都没有或都有=0 不判。"""
    seg = note.split('|', 2)[2] if note.count('|') >= 2 else note
    m = re.search(r'(?<![\d.])([+-])\d+(?:\.\d+)?%', seg)
    if m:
        return 1 if m.group(1) == '+' else -1
    return _dir(seg)


def created_notes(hours=48):
    """{真实题号: 建题备注}。11-05:板块题把样本写在备注(NBIS/ALAB/LITE…),同名代币的题关键词只留公司名(DASH→DoorDash),
    对账只看关键词+标题就报漏;股票对账把建题备注一并当草堆。COVERAGE_CNOTES 注入 json {id: note}。"""
    inj = os.environ.get('COVERAGE_CNOTES')
    if inj:
        return json.load(open(inj))
    if os.environ.get('COVERAGE_QUOTES'):
        return {}
    try:
        import ledger
        rs = ledger.rows()
        cut = int((time.time() - hours * 3600) * 1000)
        return {rid: r[4] for ts, rid, r in ledger.created(rs, since_ms=cut)}
    except Exception:
        return {}


def covered(sym, names, live, notes, pct=None, line=None, cnotes=None, idx=False):
    """pct 给了就比方向(10-22 复盘:AGT 当日 +34% 被匹配到 10-21『AGT 24小时跌35%』算有题,漏建被盖住)——
    题目标题只含涨(或只含跌)且与当前涨跌方向相反,不算有题;涨跌都含或都不含的不判。"""
    keys = {sym.lower(), sym.split('.')[0].lower()} | {n for n in names if len(n) >= 3 or re.search(r'[\u4e00-\u9fff]{2}', n)}
    if re.fullmatch(r'\d+\.[A-Z]+', sym):                      # 0992.HK ↔ 992.HK(10-15 弃建写成 992.HK 对账认不出)
        keys |= {sym.lstrip('0').lower(), sym.split('.')[0].lstrip('0').lower()}
    def _hit(k, hay):
        # 11-06 复盘:「纳指100」里的「纳指」被 (?![a-z0-9]) 挡掉(后面跟数字)——中文名不需要 ascii 边界
        if re.search(r'[\u4e00-\u9fff]', k):
            return k in hay
        return re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', hay) is not None
    for t in live:
        # 11-06 复盘:QQQ +2.6% 被『纳斯达克批准INJ质押ETF上市』(crypto 题,交易所名)算有题——指数只认 tradfi 题
        if idx and (t.get('domain') or '').lower() == 'crypto':
            continue
        hay = ((t.get('keywords') or '') + ' ' + (t.get('title') or '') + ' ' + (t.get('original_title') or '') + ' '
               + ((cnotes or {}).get(str(t['id'])) or '')).lower()
        if any(_hit(k, hay) for k in keys):
            d = _dir(t.get('title') or t.get('original_title'))
            if pct is not None and d and d * pct < 0:
                continue
            return '有题', str(t['id'])
    for n in notes:
        low = n.lower()
        if any(re.search(r'弃建[|｜]' + re.escape(k) + r'(?![a-z0-9])', low) for k in keys):   # 11-05:P 被『弃建|PWR』前缀盖住
            # 10-23 复盘:AKE 当日 +40% 被匹配到 10-22『弃建|AKE|…-30.63%…』,漏建被盖住——弃建记录也比方向
            if pct is not None and _note_dir(n) * pct < 0:
                continue
            # 10-31 复审:SNDK 收盘 -13.5% 被前一天『弃建|SNDK|盘后跌8.9%…<10%』盖住——弃建时还没过线、现在过线了,
            # 弃建理由(未达线)已不成立,须重判;弃建时就已过线的(AKE -30.6% 弃建、现 -35%)照算已处置
            _nums = [abs(float(x)) for x in re.findall(r'(?<![<>≥≤＜＞\d.])[-+]?\d+(?:\.\d+)?(?=%)', n)]   # 「<10%」是线不是读数
            if line and pct is not None and _nums and max(_nums) < line <= abs(pct):
                continue
            # 11-06 用户点名(美股指数大跌是重点题,不要漏):SPY 收跌 4.4% 被前晚盘中 -2.7% 写的『弃建|SPY』盖住——
            # 指数的弃建只在当时读数与现读数相差 ≤1 个百分点时算数,行情明显扩大就得重判(多半该建)
            if idx and pct is not None and (not _nums or abs(pct) - max(_nums) > 1.0):
                continue
            return '弃建', n[:40]
    return None, None


def sticky_misses(log_rows, day_start_ms, current):
    """10-17 复盘(ZEREBRO):20:35 报 -30.0% 漏,我没处理;下一次对账它掉回 -28% 就从漏表里消失,再没人提醒。
    今日早前报过「漏」、之后没再出现 有题/弃建、且这次不在过线表里的标的 → 返回 [(kind, sym, 最后一次涨跌幅)],仍算漏。"""
    last = {}
    for r in log_rows:
        if len(r) < 5 or not r[0].isdigit() or int(r[0]) < day_start_ms:
            continue
        last[(r[1], r[2])] = (r[4], r[3])
    return [(k, s, float(x)) for (k, s), (v, x) in last.items() if v == '漏' and (k, s) not in current]


def main():
    a = sys.argv[1:]
    hours = float(a[a.index('--hours') + 1]) if '--hours' in a else 36
    tp = b0()
    live = [t for t in tp if t.get('status') == 0 and age_h(t) <= hours]
    import ledger
    cut = int((time.time() - hours * 3600) * 1000)
    notes = [r[4] for r in ledger.rows() if r[0] >= cut and r[1] == 'note' and '弃建' in r[4]]
    sh = stock_hours(hours, int(os.environ.get('COVERAGE_NOW_MS') or time.time() * 1000) / 1000)
    live_s = [t for t in tp if t.get('status') == 0 and age_h(t) <= sh]
    cut_s = int((time.time() - sh * 3600) * 1000)
    notes_s = [r[4] for r in ledger.rows() if r[0] >= cut_s and r[1] == 'note' and '弃建' in r[4]]
    rows = []
    u = universe(tp, hours)
    _yh = [s for s in yh_movers() if s not in u]
    for s in _yh:
        u[s] = set()
    if _yh:
        print(f'   全市场榜补入对账池 {len(_yh)} 只(不在矩阵/名单/看板里):' + ','.join(_yh[:20]))
    with ThreadPoolExecutor(8) as ex:
        qs = dict(zip(u, ex.map(quote, list(u))))
    for sym, q in qs.items():
        if not q or q[2] not in (None, 'EQUITY') or not q[1]:
            continue
        x = (q[0] / q[1] - 1) * 100
        if abs(x) >= 10:
            rows.append(('股', sym, x, u[sym]))
    for sym, (thr, nm) in IDX.items():
        q = quote(sym)
        if q and q[1]:
            x = (q[0] / q[1] - 1) * 100
            if abs(x) > 40:   # 11-05 SOXX 3 拆 1,Yahoo 前收未复权报 -69.7%——指数/ETF 单日 >40% 当拆股口径错位,不算过线
                print(f'⏸ {sym} 读数 {x:+.1f}% 疑似拆股前收未复权,不计入')
            elif abs(x) >= thr:
                rows.append(('指数', sym, x, set(nm)))
    qvs = {}
    for sym, pc, qv in bn_movers():
        rows.append(('币', sym, pc, set(MAJOR.get(sym, (0, set()))[1])))
        qvs[sym] = qv
    _ms = {}
    for sym, kd, lvl, since in major_milestones():
        if not any(r[0] == '币' and r[1] == sym for r in rows):   # 幅度已过线的不重复列
            rows.append(('币', sym, -0.001 if kd == '新低' else 0.001, set(MAJOR[sym][1])))
        _ms[sym] = f'{kd} {lvl:g}(对照 {since} 起 {MAJOR_DAYS} 天)'
    n_t = n_d = n_m = 0
    _cn = created_notes()
    now = int(time.time() * 1000)
    out = []
    for kind, sym, x, names in sorted(rows, key=lambda r: -abs(r[2])):
        _lv, _nt = (live, notes) if kind == '币' else (live_s, notes_s)
        _line = (MAJOR[sym][0] if kind == '币' and sym in MAJOR else None) or {'股': 10, '币': COIN_LINE}.get(kind) or IDX.get(sym, (None,))[0]
        v, ref = covered(sym, names, _lv, _nt, x, _line, _cn if kind == '股' else None, idx=(kind == '指数'))
        if sym in _ms and kind == '币':
            ref = ((ref or '') + ' ' + _ms[sym]).strip()
        if not v and kind == '币' and qvs.get(sym, 1e9) < LOWVOL:
            # v3.7.9(10-21 用户定):无诱因的币 24h 合约成交 <1 亿默认弃建,不算漏;有诱因/硬事件的照建(对账看不出诱因,只提示)
            v, ref = '低量弃建', f'成交{qvs[sym] / 1e8:.2f}亿<1亿·无诱因默认不建(有诱因/硬事件仍要建)'
        if v == '有题':
            n_t += 1
        elif v in ('弃建', '低量弃建'):
            n_d += 1
        else:
            n_m += 1
        out.append((kind, sym, x, v or '漏', ref or ''))
    _lr = ledger.rows()
    for ek, t0, syms, hl in news_events(hours):
        v, ref = news_covered(ek, t0, syms, tp, _lr)
        if v == '有题':
            n_t += 1
        elif v == '弃建':
            n_d += 1
        else:
            n_m += 1
        _at = time.strftime('%m-%d %H:%M', time.localtime(t0))
        out.append(('突发', ek, 0.0, v or '漏', f'{(ref + " ") if ref else ""}「{hl}」{_at} 标的:{",".join(x[0] for x in syms) or "无"}'.strip()))
    try:
        _rows = [l.rstrip('\n').split('\t') for l in open(LOG, encoding='utf-8')]
    except FileNotFoundError:
        _rows = []
    _d0 = int(time.mktime(time.strptime(time.strftime('%Y-%m-%d'), '%Y-%m-%d')) * 1000)
    for kind, sym, x in sticky_misses(_rows, _d0, {(o[0], o[1]) for o in out}):
        if kind == '突发':   # 事件按窗口对账,出窗口不再追
            continue
        v, ref = covered(sym, set(), live, notes)
        if v == '弃建':
            n_d += 1
        elif v == '有题':
            n_t += 1
        else:
            n_m += 1
        out.append((kind, sym, x, v or '漏', ref or '今日早前报漏·现已回落线内仍未处置'))
    with open(LOG, 'a', encoding='utf-8') as f:
        for kind, sym, x, v, ref in out:
            f.write(f'{now}\t{kind}\t{sym}\t{x:+.1f}\t{v}\t{ref}\n')
    for kind, sym, x, v, ref in out:
        mark = '🚨' if v == '漏' else '✔'
        print(f'{mark} {kind} {sym} → {v} {ref}' if kind == '突发' else f'{mark} {kind} {sym} {x:+.1f}% → {v} {ref}')
    if n_m:
        print('   处置:逐条 topic.py create 建,或 log-action.sh note - 留档 "弃建|<标的>|<原因>|<日期>",重跑到 漏=0')
        if any(o[0] == '突发' and o[3] == '漏' for o in out):
            print('   突发行:按 gates 双要素判;不建就写 "弃建|<event_key>|<原因,如价格未过线/非看板范围>|<日期>"')
    if NEWS_NOTE:
        print('⏸ 突发对账:' + ';'.join(NEWS_NOTE))
    if STALE:
        print('⏸ 冻结合约不算过线(行情超过 30 分钟没更新,多半下架结算/停牌;要写这个币改用现货或 Gate 实测):' + '、'.join(STALE))
    if BLIND:
        print('⚠️ 半盲:' + ';'.join(BLIND) + ' ——币侧未对账,隔几分钟重跑,不得据此报漏=0')
    print(f'COVERAGE: 过线={len(out)} 有题={n_t} 弃建={n_d} 漏={n_m}' + (' 半盲=币' if BLIND else ''))
    sys.exit(2 if n_m else 0)


if __name__ == '__main__':
    main()
