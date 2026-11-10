#!/usr/bin/env python3
"""quotes.py — 机审用的 24h 涨跌快照(v3.1.5, 提案5-2)。

用途:b0-audit ⑥ 在给出机械撤候选前,先查该标的当下有没有真实价格动作。
  09-06 实录:12069(ARB)被列为「灌水-vanity指标」撤候选,而 ARB 当时 24h **+44%**——
  机审只看标题形态、不看价格动作,与 A闸「有真实价格动作一律留」直接冲突,照单执行就是误撤。

源:okx 公开行情端点(无需鉴权)。只覆盖 crypto;tradfi 标的拿不到 → 返回 None,调用方须按「未检查」处理而不是「无动作」。
缓存:~/.trend-scout/quotes-cache.json,默认 15 分钟内复用,避免每轮重复拉全量。
注入:QUOTES_JSON 指向一份现成快照(回归用);QUOTES_TTL 改缓存秒数。
"""
import json, os, time, subprocess, urllib.request

CACHE = os.path.expanduser('~/.trend-scout/quotes-cache.json')
URL   = 'https://www.okx.com/api/v5/market/tickers?instType=SPOT'
TTL   = int(os.environ.get('QUOTES_TTL', '900'))

def _raw():
    """先 urllib(带 certifi 的 CA),失败退 curl。
    09-06 实录:本机 python 默认 SSL 上下文没有 CA 根证书(macOS 常见),urlopen 直接 CERTIFICATE_VERIFY_FAILED,
    而同一个 URL curl 拿得到 437KB——**两条路都留着,不要因为『python 拉不到』就断定拉不到**。"""
    try:
        import ssl, certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        req = urllib.request.Request(URL, headers={'User-Agent': 'trend-scout/1.0'})
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            return r.read()
    except Exception:
        return subprocess.run(['curl', '-s', '-m', '12', URL],
                              capture_output=True, timeout=20).stdout

def _fetch():
    rows = json.loads(_raw()).get('data', [])
    out = {}
    for x in rows:
        inst = x.get('instId', '')
        if not inst.endswith('-USDT'):
            continue
        try:
            last, o24 = float(x['last']), float(x['open24h'])
        except (KeyError, TypeError, ValueError):
            continue
        if o24 > 0:
            out[inst[:-5]] = round((last / o24 - 1) * 100, 2)
    return out

def load(force=False):
    """返回 {ticker: 24h涨跌%}。取不到返回 {} —— 调用方据此走「未检查」分支。"""
    inj = os.environ.get('QUOTES_JSON')
    if inj:
        try: return json.load(open(inj))
        except Exception: return {}
    if not force and os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE))
            if time.time() - c.get('ts', 0) < TTL:
                return c.get('q', {})
        except Exception:
            pass
    try:
        q = _fetch()
    except Exception:
        try:  # 拉不到时退回过期缓存,标注陈旧总好过完全不检查
            return json.load(open(CACHE)).get('q', {})
        except Exception:
            return {}
    try:
        json.dump({'ts': time.time(), 'q': q}, open(CACHE, 'w'))
    except Exception:
        pass
    return q

if __name__ == '__main__':
    q = load(force='--force' in os.sys.argv)
    print(f'{len(q)} 个标的')
    for k in ('BTC', 'ARB', 'ZEC', 'RAY', 'JUP'):
        print(f'  {k}: {q.get(k, "—")}')
