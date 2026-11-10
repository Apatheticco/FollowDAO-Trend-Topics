#!/usr/bin/env python3
"""gate.py — Gate 交易所取价(v3.5.8,09-22 用户「按这个做」)。

为什么是 Gate:Evose 沙箱出口在中国大陆(阿里云杭州),币安/OKX/Bybit/DexScreener/GeckoTerminal/CoinGecko
全部连不上,**只有 api.gateio.ws 通**(迁移方案 §38.1);09-11 校准:Gate 与币安/OKX/Upbit 同一分钟成交价偏差 ≤0.3%(§38.4)。
09-21 第二十二轮扫描员给 16 道存量题取价,8 道「本轮未取到」;09-22 本机实测其中 6 道 Gate 有盘、且自带 24h 涨跌幅。

**同名币是最大的坑**:09-22 实测 Gate 上 ONE 现货 0.00503、ONE 永续 0.00381,差约 30%——永续是 Harmony(与币安 ONEUSDT 一致),
现货是另一个币。所以:同一代号的现货与永续价差 >5% 且注册表没钉市场 → 判「同名冲突」,**不给价**。
注册表 = contracts.json 的 price_map 段:{"ONE":{"gate":"futures","cg_id":"harmony","why":"…"}},
gate 可取 "spot"/"futures"/null(null=Gate 上同代号不是这个币,别用);cg_id 给 Gate 没有的币走 CoinGecko 用。

用法:
  gate.py t <SYM> [...]            单查(同名冲突照样判)
  gate.py list <清单文件>          逐行处理存量取价清单(每行 id｜domain｜keywords｜标题,｜ 或 | 分隔),末行 GATE: 汇总
注入(回归用):GATE_SPOT_JSON / GATE_FUT_JSON 指向现成的 tickers 快照;CONTRACTS_JSON 指向注册表。
"""
import json, os, re, sys, subprocess, time, urllib.request

SPOT_URL = 'https://api.gateio.ws/api/v4/spot/tickers'
FUT_URL = 'https://api.gateio.ws/api/v4/futures/usdt/tickers'
REG = os.environ.get('CONTRACTS_JSON') or os.path.expanduser('~/.trend-scout/contracts.json')
CONFLICT_PCT = 5.0


def _raw(url):
    """同 quotes.py:先 urllib(带 certifi),失败退 curl——沙箱 python 可能没 CA 根证书,别因此断定拉不到。"""
    try:
        import ssl, certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(url, headers={'User-Agent': 'trend-scout/1.0'})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return r.read()
    except Exception:
        try:
            return subprocess.run(['curl', '-s', '-m', '15', url], capture_output=True, timeout=25).stdout
        except Exception:
            return b''


def _load(env, url):
    p = os.environ.get(env)
    try:
        rows = json.load(open(p)) if p else json.loads(_raw(url) or b'[]')
    except Exception:
        rows = []
    return rows if isinstance(rows, list) else []


def fetch():
    spot = {x['currency_pair'][:-5]: x for x in _load('GATE_SPOT_JSON', SPOT_URL)
            if str(x.get('currency_pair', '')).endswith('_USDT')}
    fut = {x['contract'][:-5]: x for x in _load('GATE_FUT_JSON', FUT_URL)
           if str(x.get('contract', '')).endswith('_USDT')}
    return spot, fut


def pmap():
    try:
        return {k.upper(): v for k, v in (json.load(open(REG, encoding='utf-8')).get('price_map') or {}).items()}
    except Exception:
        return {}


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def _fmt(kind, x):
    last, chg = _f(x.get('last')), _f(x.get('change_percentage'))
    vol = _f(x.get('quote_volume') if kind == '现货' else x.get('volume_24h_quote'))
    s = 'Gate·%s·24h last=%s 24h=%+.2f%%' % (kind, x.get('last'), chg or 0.0)
    return s + (' 成交额=$%.2fM' % (vol / 1e6) if vol else '')


def quote(sym, spot, fut, reg):
    """返回 (状态, 文本)。状态 ∈ ok / conflict / none / blocked。"""
    sym = sym.upper().lstrip('$')
    pin = reg.get(sym, {})
    cg = pin.get('cg_id')
    tail = ('｜Gate 没有→CoinGecko cg_id=%s' % cg) if cg else '｜Gate 没有→CoinGecko 未登记'
    if 'gate' in pin and pin['gate'] is None:
        return 'blocked', 'Gate 同代号不是这个币(注册表钉 null:%s)%s' % (pin.get('why', ''), tail.replace('Gate 没有', '改走'))
    s, f = spot.get(sym), fut.get(sym)
    if pin.get('gate') == 'spot':
        f = None
    elif pin.get('gate') == 'futures':
        s = None
    if not s and not f:
        return 'none', 'Gate 没有' + tail[len('｜Gate 没有'):]
    if s and f:
        ls, lf = _f(s.get('last')), _f(f.get('last'))
        if ls and lf and abs(ls / lf - 1) * 100 > CONFLICT_PCT:
            return 'conflict', ('同名冲突:Gate 现货 %s vs 永续 %s(差 %.1f%%>%.0f%%),不给价;在 contracts.json price_map 钉 gate=spot/futures/null 后重跑%s'
                                % (s.get('last'), f.get('last'), abs(ls / lf - 1) * 100, CONFLICT_PCT, ('｜cg_id=%s' % cg) if cg else ''))
        return 'ok', _fmt('永续', f) + '｜' + _fmt('现货', s)
    x, kind = (f, '永续') if f else (s, '现货')
    note = '' if pin.get('gate') else '(单市场,未能与另一市场交叉)'
    return 'ok', _fmt(kind, x) + note


def pick_sym(keywords, reg):
    toks = [t.strip().lstrip('$') for t in re.split(r'[,，、\s]+', keywords or '') if t.strip()]
    for t in toks:
        if t.upper() in reg:
            return t.upper()
    for t in toks:
        # 代号基本全大写：允许至多 1 个小写字母（USDe、sUSD 类），普通单词（Ethena）不算。
        # 09-22 第二十六轮：keywords「USDe,Ethena,ENA」只认纯大写，跳过 USDe 认成了 ENA，脱锚题拿到的是 ENA 的价。
        if re.fullmatch(r'[A-Za-z0-9]{2,12}', t) and re.search('[A-Z]', t) and sum(c.islower() for c in t) <= 1:
            return t.upper()
    return None


def main(a):
    if len(a) < 2 or a[0] not in ('t', 'list'):
        sys.exit(__doc__)
    spot, fut = fetch()
    reg = pmap()
    stamp = time.strftime('%m-%d %H:%M', time.localtime())
    if not spot and not fut:
        print('GATE: 取数失败(现货与永续两个端点都没拿到数据)——不许写「Gate 没有」,按通道故障处理')
        sys.exit(1)
    if a[0] == 't':
        for sym in a[1:]:
            st, txt = quote(sym, spot, fut, reg)
            print('%s｜%s｜取价 %s CST' % (sym.upper(), txt, stamp))
        return
    n = ok = cf = no = tf = nk = 0
    for line in open(a[1], encoding='utf-8'):
        c = [x.strip() for x in re.split(r'[｜|]', line.rstrip('\n'))]
        if len(c) < 3 or not re.fullmatch(r'\d+', c[0]):
            continue
        n += 1
        rid, dom, kw = c[0], c[1].lower(), c[2]
        if dom == 'tradfi':
            tf += 1
            print('%s｜-｜tradfi 不走 Gate(照手册用 metrics 取价)' % rid)
            continue
        sym = pick_sym(kw, reg)
        if not sym:
            nk += 1
            print('%s｜-｜keywords「%s」里认不出代号,人工给价' % (rid, kw))
            continue
        st, txt = quote(sym, spot, fut, reg)
        ok += st == 'ok'
        cf += st == 'conflict'
        no += st in ('none', 'blocked')
        print('%s｜%s｜%s｜取价 %s CST' % (rid, sym, txt, stamp))
    print('GATE: 行=%d 取到=%d 同名冲突=%d Gate没有=%d tradfi=%d 认不出代号=%d 取价时刻=%s CST 现货对=%d 永续=%d'
          % (n, ok, cf, no, tf, nk, stamp, len(spot), len(fut)))


if __name__ == '__main__':
    main(sys.argv[1:])
