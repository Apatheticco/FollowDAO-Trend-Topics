#!/usr/bin/env python3
"""pct.py — 涨跌幅由脚本从原始价格算(v3.7.0),不让模型手算。

病例:10-15 RKLB 收盘 59.18 / 前收 64.22 = -7.848%,我先把它近似成 -7.85 再进位成「7.9%」——两次舍入;
复审员抓到才改。百分比是纯算术,不该经过模型。

标题写法(看板现行惯例,本脚本是它的单一实现):|x| ≥ 10 写整数(跌11%、涨41%),|x| < 10 保留一位小数
(跌7.8%、涨4.8%);一位小数是 .0 时去掉(-0.96% → 「1%」);全部四舍五入(ROUND_HALF_UP),只舍入一次。
校验时 |x| ≥ 10 也接受正确的一位小数(41.2%)。

用法:
  pct.py calc <现价> <前收>                 算涨跌幅并给标题写法
  pct.py bn <SYMBOL>                        币安 USDT 永续 24h(交易所给的 24h 涨跌幅+成交额);行情超过 30 分钟没更新(下架结算/停牌)拒给数,退出 3
  pct.py yahoo <SYMBOL>                     Yahoo 日线:最后一根 vs 前一交易日收盘(打印两根 K 的日期,自己确认口径)
  pct.py check "<标题>" <标签=现价/前收> ...  标题里该标签后面的百分数必须等于算出来的写法(topic.py 建/改题预检调用)
"""
import sys, re, json, subprocess
from decimal import Decimal, ROUND_HALF_UP


def change(last, prev):
    last, prev = Decimal(str(last)), Decimal(str(prev))
    if prev == 0:
        raise ValueError('前收为 0')
    return (last / prev - 1) * 100


def _q(x, step):
    return x.quantize(Decimal(step), rounding=ROUND_HALF_UP)


def fmt(x):
    """标题写法(不带正负号与 %)。"""
    a = abs(Decimal(str(x)))
    v = _q(a, '1') if a >= 10 else _q(a, '0.1')
    if v >= 10:
        v = _q(v, '1')
    s = format(v, 'f')
    return s[:-2] if s.endswith('.0') else s


def accepted(x):
    """校验时接受的写法集合:标准写法;|x|≥10 时再接受正确的一位小数。"""
    a = abs(Decimal(str(x)))
    out = {fmt(x)}
    if a >= Decimal('9.95'):
        s = format(_q(a, '0.1'), 'f')
        out.add(s[:-2] if s.endswith('.0') else s)
    return out


def word(x):
    return '涨' if Decimal(str(x)) > 0 else ('跌' if Decimal(str(x)) < 0 else '持平')


_NUM = r'(\d+(?:\.\d+)?)%'
_UP = re.compile(r'涨|升|上扬|走高|反弹|飙')
_DN = re.compile(r'跌|降|挫|下滑|走低|回落|重挫|暴跌')


def check(title, specs):
    """specs: ['RKLB=59.18/64.22', '海力士=1257000/1419000'];返回 [(级别, 说明)],级别 FAIL/OK/WARN。"""
    out = []
    for sp in specs:
        m = re.fullmatch(r'\s*(.+?)\s*=\s*([\d.]+)\s*/\s*([\d.]+)\s*', sp)
        if not m:
            out.append(('FAIL', f'--pct 格式应为 标签=现价/前收,收到「{sp}」'))
            continue
        lab, last, prev = m.group(1), m.group(2), m.group(3)
        x = change(last, prev)
        want = accepted(x)
        raw = f'{x:+.4f}%'
        i = title.find(lab)
        if i < 0:
            # 11-04 复盘(3489):标签写「盘中跌」、标题前缀在别处(「日股盘中重挫，日经225跌3.1%」)——去掉时段前缀再找一次
            _bare = re.sub(r'^(盘中|盘前|盘后|夜盘|尾盘|午盘|收盘|收)', '', lab)
            if _bare and _bare != lab and title.find(_bare) >= 0:
                lab, i = _bare, title.find(_bare)
        if i < 0:
            out.append(('FAIL', f'标题里找不到标签「{lab}」——--pct 的标签要用标题里写的那个名字'))
            continue
        # 10-20 复盘(Elice):标签写成标题里的「跌32%」本身,原逻辑只看标签之后→报「后面没有百分数」。标签自带百分数时从标签起点找
        seg = title[i:] if re.search(_NUM + r'\s*$', lab) else title[i + len(lab):]
        n = re.search(_NUM, seg)
        if not n:
            out.append(('FAIL', f'「{lab}」后面没有百分数;原始价算出 {raw},应写 {word(x)}{fmt(x)}%'))
            continue
        got = n.group(1)
        # 10-28 复盘(恒瑞 10000003319):「恒瑞医药三季度净利增89%，港股收涨11%」标签后首个百分数是净利增幅不是涨跌幅,
        #   误报 FAIL。首个对不上时,再找标签后紧跟涨/跌动词的百分数,对得上就按它核(方向检查照旧)
        if got not in want:
            for n2 in re.finditer(_NUM, seg):
                pre = seg[max(0, n2.start() - 3):n2.start()]
                if n2.group(1) in want and (_UP.search(pre) or _DN.search(pre)):
                    n, got = n2, n2.group(1)
                    break
        if got not in want:
            out.append(('FAIL', f'「{lab}」标题写 {got}%,原始价 {last}/{prev} 算出 {raw},应写 {fmt(x)}%'))
            continue
        between = seg[:n.start()]
        if (x < 0 and _UP.search(between) and not _DN.search(between)) or (x > 0 and _DN.search(between) and not _UP.search(between)):
            out.append(('FAIL', f'「{lab}」方向写反:原始价算出 {raw},标题是「{between}{got}%」'))
            continue
        out.append(('OK', f'{lab} {raw} → {word(x)}{fmt(x)}% ✓'))
    return out


def _curl(url):
    r = subprocess.run(['curl', '-sS', '--max-time', '20', '-A', 'Mozilla/5.0', url], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'🚨 取数失败: {r.stderr.strip()[:200]}')
    return json.loads(r.stdout)


def _bn(sym):
    s = sym.upper()
    s = s if s.endswith('USDT') else s + 'USDT'
    d = _curl(f'https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={s}')
    if 'lastPrice' not in d:
        raise SystemExit(f'🚨 币安无 {s}: {str(d)[:120]}')
    # 10-21:EPICUSDT 永续 10-20 17:00 起 SETTLING(下架结算),24hr 接口照样返回、数字冻结在 -33.7%,
    #   「1 分钟后复测不变」也测不出来——10-20 22:19 轮据此建了 13404「EPIC 24小时跌34%」(同刻现货 -21%)。行情时刻过旧一律拒给数
    age = stale_min(d)
    if age is not None:
        print(f'🚨 {s} 合约行情 {age} 分钟没更新(最后 {_hm(d["closeTime"])}),多半已下架结算/停牌,这里的 24h 涨跌是冻结值——'
              f'不许用;改用币安现货 api.binance.com/api/v3/ticker/24hr?symbol={s} 或 Gate 取价')
        sys.exit(3)
    x = Decimal(d['priceChangePercent'])
    qv = Decimal(d['quoteVolume']) / Decimal(100000000)
    print(f'{s} last={d["lastPrice"]} 24h {x:+}%(交易所滚动24h) → 标题写「24小时{word(x)}{fmt(x)}%」 '
          f'合约成交额 {_q(qv, "0.1")}亿美元')


STALE_MIN = 30


BN_TITLE = re.compile(r'24小时(涨|跌)(\d+(?:\.\d+)?)%')


def bn_title_mismatch(title, kws, tol=1.0):
    """10-31(13732 Quack AI):建题前一秒 pct.py bn 已报 -42.178%,标题仍沿用早先读数「跌41%」——crypto 标题没有 --pct 校验。
    建/改题时现拉一次币安永续 24h,标题百分数与现读差 >tol 个百分点即拦(行情在读数与建题之间又动了,重读再写)。
    标的取关键词里第一个全大写代码;取不到行情不拦。注入(回归):PCT_BN_FAKE=<json {SYM: 24h%}>;CONSOLE_FAKE 下无注入则跳过。"""
    import os
    m = BN_TITLE.search(title or '')
    if not m:
        return None
    sym = next((k.strip().upper() for k in kws or [] if re.fullmatch(r'[A-Z0-9]{1,15}', k.strip())), None)
    if not sym:
        return None
    inj = os.environ.get('PCT_BN_FAKE')
    if inj:
        v = json.load(open(inj)).get(sym)
        if v is None:
            return None
        x = float(v)
    elif os.environ.get('CONSOLE_FAKE'):
        return None
    else:
        try:
            r = subprocess.run(['curl', '-sS', '--max-time', '10', '-A', 'Mozilla/5.0',
                                f'https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={sym}USDT'], capture_output=True, text=True)
            x = float(json.loads(r.stdout)['priceChangePercent'])
        except Exception:
            return None
    t = float(m.group(2)) * (1 if m.group(1) == '涨' else -1)
    if abs(t - x) > tol:
        return (f'标题「24小时{m.group(1)}{m.group(2)}%」与币安现读 {x:+.2f}% 差 {abs(t - x):.1f} 个百分点(>{tol}),'
                f'行情在读数后又动了——pct.py bn {sym} 重读再写(10-31 13732)')
    return None




def stale_min(d, now_ms=None):
    """币安 24hr 行情的 closeTime 距今超过 STALE_MIN 分钟 → 返回分钟数(冻结);没有 closeTime 或新鲜 → None。PCT_NOW_MS 注入回归用。"""
    import os, time
    try:
        ct = int(d['closeTime'])
    except Exception:
        return None
    now = now_ms or int(os.environ.get('PCT_NOW_MS') or time.time() * 1000)
    age = (now - ct) // 60000
    return age if age > STALE_MIN else None


def _hm(ms):
    import time
    return time.strftime('%m-%d %H:%M', time.localtime(int(ms) / 1000))


def pick_prev(bar_prev, official_prev, tol=0.1):
    """日线前一根收盘 vs 交易所官方前收(range=1d 的 chartPreviousClose):相差超过 tol% 以官方为准。
    10-23 复盘:VOLCAR-B.ST 日线缺 10-22、KER.PA 我按旧提示改用 60m 末根(215.10,官方 213.50),标题多写了 1.7 个点。"""
    if not official_prev:
        return bar_prev, None
    if abs(bar_prev / official_prev - 1) * 100 > tol:
        return official_prev, f'日线前一根 {bar_prev:.4f} 与官方前收 {official_prev:.4f} 不一致(日线缺天或收盘竞价),按官方前收算'
    return bar_prev, None


def _yahoo(sym):
    import datetime
    d = _curl(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10d')
    r = d['chart']['result'][0]
    ts, cl = r['timestamp'], r['indicators']['quote'][0]['close']
    bars = [(datetime.datetime.fromtimestamp(t).strftime('%Y-%m-%d'), c) for t, c in zip(ts, cl) if c is not None]
    if len(bars) < 2:
        raise SystemExit('🚨 有效日线不足两根')
    (d0, p0), (d1, p1) = bars[-2], bars[-1]
    m = r['meta']
    try:
        off = _curl(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d')['chart']['result'][0]['meta'].get('chartPreviousClose')
    except Exception:
        off = None
    p0, warn = pick_prev(p0, off)
    last = m.get('regularMarketPrice') or p1
    x = change(last, p0)
    print(f'{sym} 前一交易日 {d0} 收 {p0:.4f} → 最后一根 {d1} 现价 {last}(盘中则为实时) {x:+.4f}% → 写 {word(x)}{fmt(x)}%')
    if warn:
        print(f'  ⚠️ {warn}')
    elif off is None:
        print('  ⚠️ 没取到官方前收(range=1d chartPreviousClose),日线可能缺天——别用 60m 末根(不含收盘竞价),改用 fmp previousClose 核')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    if a[0] == 'calc' and len(a) == 3:
        x = change(a[1], a[2])
        print(f'{x:+.4f}% → 标题写「{word(x)}{fmt(x)}%」')
    elif a[0] == 'bn' and len(a) == 2:
        _bn(a[1])
    elif a[0] == 'yahoo' and len(a) == 2:
        _yahoo(a[1])
    elif a[0] == 'check' and len(a) >= 3:
        res = check(a[1], a[2:])
        for lv, msg in res:
            print(f'{lv}\t{msg}')
        sys.exit(1 if any(lv == 'FAIL' for lv, _ in res) else 0)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
