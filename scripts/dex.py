#!/usr/bin/env python3
"""dex.py — 链上代币取价,**先查注册表按合约地址钉死,再退 symbol 搜索**(v3.3.6)。

**为什么要有注册表**(09-08 实录,同名不同币一天出现 5 次):dexscreener 按 symbol 搜是「仿盘丛林」——
  BEN 搜到 solana 同名币(+1801%,不是题里 BSC Flap 生态那个);HEMI 搜到的成交额是市值 19 倍;
  4Stock/BNC4/ZZZ 各有 26~30 个同名对。闸:大热点 第 2 步写着「按合约地址钉死」,**可没有地址时这条闸执行不了**——
  我实际做的仍是取成交额最大的同名对。注册表把「核实过一次」变成资产:核过就钉住,以后只认地址。
用法:
  dex.py t <SYM|chain:addr> [...]       查价:注册表命中→按地址;未命中→symbol 搜索并列候选+警告「未钉死」
  dex.py pin <SYM> <chain> <address> [备注]   核实地址存在后写入注册表(核不到的地址拒绝入册)
  dex.py pin <SYM> <chain> <address> <依据> --evidence '<核实原文>'
                                        (v3.5.9)不连 dexscreener,以别处的核实结果入册——Evose 沙箱连不上 dexscreener,
                                        核实改由扫描员用 CoinGecko token_data_contract_address 做,原文随 --evidence 存进 verified_by
  dex.py block <SYM> <备注>             标记「暂不可钉」(如 LAPTOP:官方 09-09 才上线,当前 base 池是仿盘)
  dex.py list                           打印注册表
注册表:~/.trend-scout/contracts.json(可用 CONTRACTS_JSON 注入);dexscreener 响应可用 DEX_INJECT_DIR 注入(回归用)。
"""
import json, os, sys, time, ssl, subprocess, urllib.request

REG = os.environ.get('CONTRACTS_JSON') or os.path.expanduser('~/.trend-scout/contracts.json')
INJ = os.environ.get('DEX_INJECT_DIR')
BASE = 'https://api.dexscreener.com'
# 登记表的链名一律用 dexscreener 叫法。GeckoTerminal(Evose 扫描员核实用)有 4 条链叫法不同(09-22 两边实测):
GT2DS = {'eth': 'ethereum', 'polygon_pos': 'polygon', 'avax': 'avalanche', 'sui-network': 'sui'}

def _get(url):
    """带 UA 的双路取数——dexscreener 对无 UA 的 python 默认请求返 403(09-08 实测),curl 自带 UA 反而能过。"""
    hdr = {'Accept': 'application/json', 'User-Agent': 'trend-scout/1.0'}
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=15, context=ctx) as r:
            return r.read()
    except Exception:
        return subprocess.run(['curl', '-s', '-m', '15', '-A', 'trend-scout/1.0', '-H', 'Accept: application/json', url],
                              capture_output=True, timeout=25).stdout

def _j(url, inj_name=None):
    if INJ and inj_name:
        p = os.path.join(INJ, inj_name)
        if os.path.exists(p): return json.load(open(p))
    raw = _get(url)
    try: return json.loads(raw) if raw else None
    except Exception: return None

def _f(x, d=0.0):
    try: return float(x)
    except Exception: return d

def load():
    if not os.path.exists(REG): return {'_doc': '代币注册表:ticker→链+合约,核实过才入册;lookup 先查这里', 'tokens': {}, 'blocked': {}}
    return json.load(open(REG, encoding='utf-8'))

def save(reg):
    json.dump(reg, open(REG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def by_address(chain, addr):
    """token 级汇总:多个交易对取成交额最大的报价,成交额跨对求和,mcap/fdv 取 token 级。"""
    ps = _j(f'{BASE}/tokens/v1/{chain}/{addr}', f'{chain}-{addr.lower()}.json')
    if ps is None: return None
    ps = ps if isinstance(ps, list) else (ps.get('pairs') or [])
    ps = [p for p in ps if (p.get('baseToken') or {}).get('address', '').lower() == addr.lower()]
    if not ps: return {}
    ps.sort(key=lambda p: -_f((p.get('volume') or {}).get('h24')))
    top = ps[0]
    created = min((_f(p.get('pairCreatedAt')) for p in ps if p.get('pairCreatedAt')), default=0)
    return {'symbol': top['baseToken'].get('symbol'), 'name': top['baseToken'].get('name'), 'chain': chain, 'address': addr,
            'px': _f(top.get('priceUsd')), 'chg24h': _f((top.get('priceChange') or {}).get('h24')),
            'vol24h': sum(_f((p.get('volume') or {}).get('h24')) for p in ps),
            'mcap': _f(top.get('marketCap')) or _f(top.get('fdv')), 'fdv': _f(top.get('fdv')),
            'pairs': len(ps), 'age_h': (time.time() * 1000 - created) / 3600e3 if created else None,
            'url': top.get('url')}

def search(sym):
    d = _j(f'{BASE}/latest/dex/search?q={sym}', f'search-{sym.upper()}.json')
    if d is None: return None
    agg = {}
    for p in d.get('pairs') or []:
        b = p.get('baseToken') or {}
        if b.get('symbol', '').upper() != sym.upper(): continue
        k = (p.get('chainId'), b.get('address'))
        a = agg.setdefault(k, {'chain': k[0], 'address': k[1], 'vol24h': 0.0, 'mcap': 0.0, 'px': None, 'chg24h': None, 'created': None})
        a['vol24h'] += _f((p.get('volume') or {}).get('h24'))
        a['mcap'] = a['mcap'] or _f(p.get('marketCap')) or _f(p.get('fdv'))
        if a['px'] is None: a['px'] = _f(p.get('priceUsd')); a['chg24h'] = _f((p.get('priceChange') or {}).get('h24'))
        c = _f(p.get('pairCreatedAt'))
        if c and (a['created'] is None or c < a['created']): a['created'] = c
    return sorted(agg.values(), key=lambda a: -a['vol24h'])

def _line(r):
    age = f"{r['age_h']:.1f}h" if r.get('age_h') is not None else '?'
    return (f"{r['symbol']:10s} {r['chain']:10s} px=${r['px']:.6g}  24h={r['chg24h']:+.1f}%  vol24h=${r['vol24h']/1e6:.2f}M  "
            f"mcap=${r['mcap']/1e6:.1f}M  对={r['pairs']}  池龄={age}  {r['address'][:10]}…")

def cmd_t(argv):
    if not argv: raise SystemExit('用法: dex.py t <SYM|chain:addr> [...]')
    reg = load(); unpinned = 0
    for q in argv:
        if ':' in q:
            chain, addr = q.split(':', 1); r = by_address(chain, addr)
            print(f"  📌 {_line(r)}" if r else f"  {q}  ❌ 该链上无此地址" if r == {} else f"  {q}  ⚠️ 取数失败")
            continue
        k = q.upper().lstrip('$')
        if k in reg.get('blocked', {}):
            print(f"  ⛔ {k:10s} 暂不可钉:{reg['blocked'][k].get('note','')}  ——不要按 symbol 搜索结果写它的价格"); unpinned += 1; continue
        ent = reg.get('tokens', {}).get(k)
        if ent:
            r = by_address(ent['chain'], ent['address'])
            if r: print(f"  📌 {_line(r)}")
            elif r == {}: print(f"  📌 {k:10s} ⚠️ 注册地址在 dexscreener 已无交易对({ent['chain']} {ent['address'][:10]}…)——池子可能撤了,不要用 symbol 搜索替代")
            else: print(f"  📌 {k:10s} ⚠️ 取数失败")
            continue
        cs = search(k)
        if cs is None: print(f"  {k:10s} ⚠️ 搜索失败"); continue
        if not cs: print(f"  {k:10s} ❌ dexscreener 无同名对"); continue
        unpinned += 1
        print(f"  ❓ {k:10s} **未钉死**——同名对 {len(cs)} 个(按链+地址聚合),成交额最大 3 个:")
        for c in cs[:3]:
            age = f"{(time.time()*1000-c['created'])/3600e3:.1f}h" if c['created'] else '?'
            print(f"       {c['chain']:10s} {c['address']}  vol24h=${c['vol24h']/1e6:.2f}M mcap=${c['mcap']/1e6:.1f}M 24h={c['chg24h']:+.1f}% 池龄={age}")
        print(f"       ↳ 确认是题里那个后: dex.py pin {k} <chain> <address> '<依据>'   ——**未钉死前不得把上面任一价格写进标题**")
    if unpinned: print(f"DEX: 未钉死 {unpinned} 个(见 ❓/⛔)")

def cmd_pin(argv):
    ev = None
    if '--evidence' in argv:
        i = argv.index('--evidence')
        if i + 1 >= len(argv) or not argv[i + 1].strip():
            raise SystemExit('🚨 --evidence 后面必须跟核实原文(扫描员【待钉候选】那一行),不许空')
        ev = argv[i + 1].strip(); argv = argv[:i] + argv[i + 2:]
    if len(argv) < 3: raise SystemExit('用法: dex.py pin <SYM> <chain> <address> [依据] [--evidence <核实原文>]')
    k, chain, addr = argv[0].upper().lstrip('$'), argv[1], argv[2]; note = ' '.join(argv[3:])
    if ev is not None:
        # 依据与核实原文都要有:依据说「为什么是这个币」(新闻原文/项目名),核实原文说「这个地址真实存在」
        if not note.strip(): raise SystemExit('🚨 --evidence 模式必须写依据(为什么是题里那个币),不许只给核实原文')
        if chain in GT2DS:
            print(f'  链名 {chain}(GeckoTerminal)→ {GT2DS[chain]}(登记表统一用 dexscreener 叫法)'); chain = GT2DS[chain]
        if addr.lower() not in ev.lower():
            raise SystemExit(f'🚨 拒绝入册:核实原文里没有地址 {addr}——核实的不是这个地址')
        r = {'name': None, 'mcap': None}
    else:
        r = by_address(chain, addr)
        if not r:
            raise SystemExit(f"🚨 拒绝入册:{chain} 上找不到 {addr} 的交易对(核不到的地址不能钉——钉错比不钉更糟)")
    reg = load(); ent = {'chain': chain, 'address': addr, 'name': r.get('name'),
        'pinned_at': time.strftime('%F %H:%M'), 'note': note, 'mcap_at_pin': r['mcap']}
    if ev is not None: ent['verified_by'] = ev[:500]
    reg.setdefault('tokens', {})[k] = ent
    reg.get('blocked', {}).pop(k, None); save(reg)
    if ev is not None: print(f"✔ 已钉 {k} → {chain} {addr}  (依据别处核实:{ev[:80]})")
    else: print(f"✔ 已钉 {k} → {chain} {addr}  ({r.get('name')}, mcap=${r['mcap']/1e6:.1f}M, 对={r['pairs']})")

def cmd_block(argv):
    if len(argv) < 2: raise SystemExit('用法: dex.py block <SYM> <备注>')
    k = argv[0].upper().lstrip('$'); reg = load()
    reg.setdefault('blocked', {})[k] = {'note': ' '.join(argv[1:]), 'at': time.strftime('%F %H:%M')}; save(reg)
    print(f"⛔ 已标 {k} 暂不可钉:{' '.join(argv[1:])}")

def cmd_list(argv):
    reg = load()
    print(f"注册表 {REG}:已钉 {len(reg.get('tokens',{}))} / 暂不可钉 {len(reg.get('blocked',{}))}")
    for k, e in sorted(reg.get('tokens', {}).items()): print(f"  📌 {k:10s} {e['chain']:10s} {e['address']}  {e.get('pinned_at','')}  {e.get('note','')[:60]}")
    for k, e in sorted(reg.get('blocked', {}).items()): print(f"  ⛔ {k:10s} {e.get('note','')[:80]}")

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    {'t': cmd_t, 'pin': cmd_pin, 'block': cmd_block, 'list': cmd_list}.get(a[0], lambda _: (_ for _ in ()).throw(SystemExit('未知子命令: ' + a[0])))(a[1:])
