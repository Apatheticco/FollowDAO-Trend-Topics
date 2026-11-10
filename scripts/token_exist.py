#!/usr/bin/env python3
"""token_exist.py — 小币保护闸的「这是不是一个真实在交易的代币」判据(v3.6.0,2026-09-26 用户定方案 B)。

为什么要有它:meme 铁律(v2.9.7)保护的是链上小币免于「核不了/市值小」式误撤(11815 FONE / 11859 COPPERINU),
  但作用域判定 lint.meme_scope 靠「标题里有个大写词」认代币——09-20~09-26 一周误拦 10 次,
  GALAXY/OKX/BACKPACK/LAYERZERO(公司/交易所/项目名)、FOMO(应用名)、JACKBUTCHER(人名)、QNT(主流币)……
  没有一次是真小币被误撤,每次都靠往 majors.json 补名单放行。名单补不完,判据方向本身错了。
方案 B:认代币要有交易证据——
  ① 已钉进合约注册表(contracts.json tokens/blocked)          → 是
  ② okx 或币安(现货/永续)有这个币                            → 是
  ③ dexscreener 同名池里有像样的一个(24h 成交额≥10 万美元;或 市值≥100 万美元 且 24h 成交额≥1 万美元) → 是
     (11-05 BLAST:polygon 一个死池 mcap 149 万、日成交 0.5 美元靠「市值」单项过了,复审员实测全部同名池日成交 ≤213 美元——
      市值/FDV 是挂牌数字不是交易证据,单独不作数)
  ④ 以上数据源都查成了、都没有                                → 否(不受小币保护)
  ⑤ 有数据源没查成、其余也没命中                              → None(未知,调用方按保守处理=照样保护)
缓存:交易所币种清单 12 小时(~/.trend-scout/token-exist-cache.json),dex 结果 6 小时。
注入(回归用):TOKEN_EXISTS_JSON 指向 {"SYM": true/false/null},命中即直接返回,不联网。
用法:token_exist.py <SYM> [...]   打印每个的判定与依据
"""
import json, os, sys, time, subprocess

CACHE = os.path.expanduser('~/.trend-scout/token-exist-cache.json')
REG = os.environ.get('CONTRACTS_JSON') or os.path.expanduser('~/.trend-scout/contracts.json')
LIST_TTL, DEX_TTL = 12 * 3600, 6 * 3600
DEX_MIN_VOL, DEX_MIN_MCAP, DEX_MCAP_VOL = 1e5, 1e6, 1e4


def _dex_ok(rows):
    """(True/False, 依据)。成交额≥10 万 单独成立;市值≥100 万 须同时日成交≥1 万(11-05 BLAST 死池教训)。"""
    best = None
    for r in rows or []:
        v, m = r.get('vol24h') or 0, r.get('mcap') or 0
        if v >= DEX_MIN_VOL or (m >= DEX_MIN_MCAP and v >= DEX_MCAP_VOL):
            return True, f"{r.get('chain')} 池 24h 成交 {v:.0f} 美元、市值 {m:.0f}"
        if best is None or v > best[0]: best = (v, m, r.get('chain'))
    if best: return False, f'同名池最大日成交仅 {best[0]:.0f} 美元(市值 {best[1]:.0f},{best[2]})'
    return False, '搜不到同名池'
_EXCH = {
    'okx_spot': ('https://www.okx.com/api/v5/public/instruments?instType=SPOT', lambda d: {x['baseCcy'].upper() for x in d.get('data', [])}),
    'okx_swap': ('https://www.okx.com/api/v5/public/instruments?instType=SWAP', lambda d: {x['instId'].split('-')[0].upper() for x in d.get('data', [])}),
    'bn_spot': ('https://api.binance.com/api/v3/exchangeInfo', lambda d: {x['baseAsset'].upper() for x in d.get('symbols', [])}),
    'bn_fut': ('https://fapi.binance.com/fapi/v1/exchangeInfo', lambda d: {x['baseAsset'].upper() for x in d.get('symbols', [])}),
}

def _curl(url, timeout=20):
    # 系统 curl(macOS 钥匙串证书);python.org 版 python3 无 CA 链会 CERTIFICATE_VERIFY_FAILED(b0_fetch.py 同一教训)
    r = subprocess.run(['curl', '-sS', '--max-time', str(timeout), '-A', 'trend-scout/1.0', url], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip(): return None
    try: return json.loads(r.stdout)
    except Exception: return None

def _load_cache():
    try: return json.load(open(CACHE))
    except Exception: return {}

def _save_cache(c):
    try: json.dump(c, open(CACHE, 'w'))
    except Exception: pass

def _exchange_sets(cache):
    """返回 {源名: set 或 None(没查成)}。"""
    now = time.time(); out = {}; dirty = False
    ex = cache.setdefault('exch', {})
    for name, (url, parse) in _EXCH.items():
        ent = ex.get(name)
        if ent and now - ent.get('ts', 0) < LIST_TTL:
            out[name] = set(ent['syms']); continue
        d = _curl(url)
        try: s = parse(d) if d else None
        except Exception: s = None
        if s:
            ex[name] = {'ts': now, 'syms': sorted(s)}; dirty = True; out[name] = s
        else:
            out[name] = set(ent['syms']) if ent else None   # 拉不到时用过期缓存,比没有强;连缓存都没有=没查成
    if dirty: _save_cache(cache)
    return out

def _dex(sym, cache):
    """True/False/None。复用 dex.search(同一套仿盘聚合逻辑)。"""
    now = time.time(); dx = cache.setdefault('dex', {})
    ent = dx.get(sym)
    if ent and now - ent.get('ts', 0) < DEX_TTL and 'why' in ent: return ent['v']   # 11-05 前的旧缓存无依据字段,重查
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import dex
        rows = dex.search(sym)
    except Exception:
        rows = None
    if rows is None: return None
    v, why = _dex_ok(rows)
    dx[sym] = {'ts': now, 'v': v, 'why': why}; _save_cache(cache)
    return v

def _registered(sym):
    try: ct = json.load(open(REG, encoding='utf-8'))
    except Exception: return False
    return sym in {k.upper() for k in list(ct.get('tokens') or {}) + list(ct.get('blocked') or {})}

def explain(sym):
    """返回 (True/False/None, 依据)。"""
    sym = sym.upper().lstrip('$')
    inj = os.environ.get('TOKEN_EXISTS_JSON')
    if inj:
        try:
            m = json.load(open(inj))
            if sym in m: return m[sym], 'injected'
        except Exception: pass
    if _registered(sym): return True, '合约注册表已钉'
    cache = _load_cache()
    sets = _exchange_sets(cache)
    hit = [n for n, s in sets.items() if s and sym in s]
    if hit: return True, '交易所有:' + '/'.join(hit)
    d = _dex(sym, cache)
    if d: return True, 'dex 有像样池子:' + (cache.get('dex', {}).get(sym) or {}).get('why', '')
    missing = [n for n, s in sets.items() if s is None] + (['dex'] if d is None else [])
    if missing: return None, '未知:没查成 ' + '/'.join(missing)
    return False, 'okx/币安均无、' + (cache.get('dex', {}).get(sym) or {}).get('why', 'dex 只有仿盘或搜不到')

def exists(sym):
    return explain(sym)[0]

if __name__ == '__main__':
    for s in sys.argv[1:] or ['--help']:
        if s == '--help': print(__doc__); break
        v, why = explain(s)
        print(f"{s.upper():14s} {'是' if v else ('否' if v is False else '未知')}  {why}")
