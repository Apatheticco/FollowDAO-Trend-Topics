#!/usr/bin/env python3
"""okx.py — okx 行情直连（v3.3.0，替代 okx MCP 的三个通道）。

**为什么不走 MCP**（09-08 用户裁定「skill 里去掉 OKX 的 MCP」，依据是同日两轮实测）：
  ① `market_filter` 的 `order` 参数对 `chg24hPct` **不生效**——09-08 14:40 轮传 order=asc 拿到的是涨序，
     换 order=ASC 再试仍是涨序，两种写法都拿不到跌榜，该轮「okx跌榜」通道判 ❌。
     跌榜是抓「昨天建的涨题今天翻绿」的主通道，丢了它这一项发现能力就下降。
  ② 退而用 quotes.py 的本地缓存排序（09-08 16:35 轮），但 quotes.py 只存 ticker→涨跌幅，
     **没有成交额也没有 OI**，于是「okx-OI」通道又判 ❌，且跌榜混进低流动性死币无法过滤。
  ③ 实测 okx 公开端点无需鉴权即可拿到全部所需字段（见下），本地排序方向自己控制，
     成交额与 OI 一并到手——**直连不是降级，是比 MCP 更全**。
  边界：okx 的 news 端点（/api/v5/orbit/news-search）**需要 OK-ACCESS-KEY**（实测返 50103），
  公开拿不到，故 news 能力不在本脚本内；新闻主源是 followin news，okx news 本就不是固定通道。

端点（全部公开、无鉴权）：
  /api/v5/market/tickers?instType=SWAP   473 条，含 last/open24h/high24h/low24h/vol24h/volCcy24h/sodUtc0
  /api/v5/public/open-interest?instType=SWAP  473 条，含 oi/oiCcy/oiUsd
  /api/v5/market/ticker?instId=<X>       单标的实测

用法:
  okx.py movers [--top N] [--minvol USD]   涨跌两榜（本地排序，带成交额）
  okx.py oi [--top N] [--minoi USD]        OI 榜 + 与上轮快照的变化率
  okx.py t <SYMBOL|instId> [...]           单标的/多标的实测
注入(回归用): OKX_TICKERS_JSON / OKX_OI_JSON 指向现成 JSON；OKX_OISNAP 改快照路径。
"""
import json, os, sys, time, subprocess, urllib.request

BASE = 'https://www.okx.com'
OISNAP = os.environ.get('OKX_OISNAP') or os.path.expanduser('~/.trend-scout/okx-oi-snap.json')


def _get(url):
    """先 urllib(带 certifi 的 CA)，失败退 curl。

    与 quotes.py 同源的双路取数：09-06 实测本机 python 默认 SSL 上下文没有 CA 根证书(macOS 常见)，
    urlopen 直接 CERTIFICATE_VERIFY_FAILED，而同一个 URL curl 拿得到——**两条路都留着，
    不要因为「python 拉不到」就断定拉不到**。
    """
    try:
        import ssl, certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(url, headers={'User-Agent': 'trend-scout/1.0'})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            return r.read()
    except Exception:
        return subprocess.run(['curl', '-s', '-m', '15', url],
                              capture_output=True, timeout=25).stdout


def _api(path, inject_env=None, tolerant=False):
    if inject_env:
        p = os.environ.get(inject_env)
        if p:
            return json.load(open(p)).get('data') or []
    raw = _get(BASE + path)
    if not raw:
        raise SystemExit('🚨 okx 取数失败(urllib 与 curl 两路都空): ' + path)
    d = json.loads(raw)
    if str(d.get('code')) != '0':
        # tolerant：批量实测里某个 instId 不存在不该中断其余标的（09-08 首版就是这么断的：
        # 查 SOPH/USELESS/CP/ZZZ 四个，前三个拿到了，ZZZ 不存在直接 SystemExit，
        # **前三条结果照样打印了但退出码是 1**——调用方若用 && 串联会误判整批失败）。
        if tolerant:
            return []
        raise SystemExit('🚨 okx code=%s msg=%s' % (d.get('code'), d.get('msg')))
    return d.get('data') or []


def _f(x, dflt=0.0):
    try:
        return float(x)
    except Exception:
        return dflt


def tickers():
    """SWAP 全量，附算 chg24hPct 与 volUsd24h。

    chg 用 open24h 作分母（滚动 24h），与题面「24h 涨跌」口径一致；
    成交额见下方 volUsd24h 的注释——**volCcy24h 不是 USD**。
    """
    out = []
    for r in _api('/api/v5/market/tickers?instType=SWAP', 'OKX_TICKERS_JSON'):
        o, l = _f(r.get('open24h')), _f(r.get('last'))
        if not o or not l:
            continue
        r['chg24hPct'] = (l - o) / o * 100
        # volCcy24h 是**基础货币数量(币的个数)，不是 USD**——必须乘 last 才是成交额。
        # 09-08 首版直接把 volCcy24h 当美元用，SOPH 显示 $31139M 而 MCP 时代同一标的是 $2.75 亿，
        # 差 96 倍(正好 1/0.0104=1/价格)。用 MCP 已知值交叉验证才发现：
        # DOT volCcy24h 66194972 × last 1.069 = $7076万 ≈ MCP 的 volUsd24h 69927813 ✔
        # USELESS 714339220 × 0.23221 = $1.66 亿 ≈ MCP 的 1.95 亿(有时间差) ✔
        # **不校对就用，低价币成交额被放大百倍、全部混过过滤，跌榜会塞满死币**。
        r['volUsd24h'] = _f(r.get('volCcy24h')) * l
        out.append(r)
    return out


def oi_now():
    return {r['instId']: _f(r.get('oiUsd')) for r in
            _api('/api/v5/public/open-interest?instType=SWAP', 'OKX_OI_JSON')}


def cmd_movers(argv):
    top = int(_opt(argv, '--top', 12))
    minvol = _f(_opt(argv, '--minvol', 15e6))
    allrows = tickers()
    rows = [r for r in allrows if r['volUsd24h'] >= minvol]
    rows.sort(key=lambda r: r['chg24hPct'])
    print('okx SWAP %d 个标的，成交额≥$%.0fM 的 %d 个 | %s'
          % (len(allrows), minvol / 1e6, len(rows), time.strftime('%F %T %Z')))
    # 候选数 < 2×top 时两榜会重叠，各让一半，避免同一标的既在涨榜又在跌榜
    # （生产 67~149 个候选不会触发；但 minvol 调高时会，那时同标的两榜并列看着就像 bug）
    half = min(top, len(rows) // 2) if len(rows) < 2 * top else top
    down, up = rows[:half], rows[len(rows) - half:][::-1]
    print('== 跌榜 top%d ==' % len(down))
    for r in down:
        _pr(r)
    print('== 涨榜 top%d ==' % len(up))
    for r in up:
        _pr(r)


def _pr(r):
    print('  %+7.2f%%  %-22s last=%-12s vol=$%.0fM  high24h=%s low24h=%s'
          % (r['chg24hPct'], r['instId'], r.get('last'), r['volUsd24h'] / 1e6,
             r.get('high24h'), r.get('low24h')))


def cmd_oi(argv):
    """OI 榜 + 变化率。

    公开端点只给当下快照，没有 MCP 的 oiDeltaPct，故自己存快照对比：
    每次跑把 {instId: oiUsd, _ts} 落盘，下次跑算与上次的差。
    首次跑没有基线时如实标「首次·无基线」，**不假装有变化率**。
    """
    top = int(_opt(argv, '--top', 12))
    minoi = _f(_opt(argv, '--minoi', 10e6))
    now = oi_now()
    prev, prev_ts = {}, None
    if os.path.exists(OISNAP):
        try:
            s = json.load(open(OISNAP))
            prev, prev_ts = s.get('oi') or {}, s.get('ts')
        except Exception:
            pass
    px = {r['instId']: r for r in tickers()}
    rows = []
    for i, v in now.items():
        if v < minoi:
            continue
        p = prev.get(i)
        d = ((v - p) / p * 100) if p else None
        rows.append((d if d is not None else -999, v, i, d))
    rows.sort(reverse=True)
    age = ('上轮快照 %s' % time.strftime('%F %T', time.localtime(prev_ts))) if prev_ts else '首次·无基线'
    print('okx OI ≥$%.0fM 的 %d 个 | 基线=%s' % (minoi / 1e6, len(rows), age))
    for _, v, i, d in rows[:top]:
        r = px.get(i, {})
        ds = ('%+6.2f%%' % d) if d is not None else '   n/a'
        print('  OI %s  $%.1fM  %-22s px %+6.2f%%  last=%s'
              % (ds, v / 1e6, i, r.get('chg24hPct', 0.0), r.get('last', '?')))
    json.dump({'ts': time.time(), 'oi': now}, open(OISNAP, 'w'))
    print('(快照已更新 %s)' % OISNAP)


def cmd_t(argv):
    if not argv:
        raise SystemExit('用法: okx.py t <SYMBOL|instId> [...]')
    for s in argv:
        inst = s if '-' in s else '%s-USDT-SWAP' % s.upper()
        d = _api('/api/v5/market/ticker?instId=%s' % inst, tolerant=True)
        if not d:
            print('  %-22s ❌ 无此交易对(不等于该标的不可核，换 SPOT 或换源再试)' % inst)
            continue
        r = d[0]
        o, l = _f(r.get('open24h')), _f(r.get('last'))
        chg = (l - o) / o * 100 if o else 0.0
        sod = _f(r.get('sodUtc0'))
        print('  %-22s last=%s  24h=%+.2f%%  today=%+.2f%%  high24h=%s low24h=%s  vol=$%.1fM'
              % (inst, r.get('last'), chg, ((l - sod) / sod * 100 if sod else 0.0),
                 r.get('high24h'), r.get('low24h'), _f(r.get('volCcy24h')) * l / 1e6))


def _opt(argv, k, dflt):
    return argv[argv.index(k) + 1] if k in argv else dflt


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    c, rest = a[0], a[1:]
    {'movers': cmd_movers, 'oi': cmd_oi, 't': cmd_t}.get(c, lambda _: (_ for _ in ()).throw(
        SystemExit('未知子命令: %s（movers|oi|t）' % c)))(rest)
