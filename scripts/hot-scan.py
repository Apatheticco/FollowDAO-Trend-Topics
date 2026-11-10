#!/usr/bin/env python3
"""hot-scan.py — 大热点前置扫描(v3.3.2)。三层公开信号,全部免鉴权、不走 MCP;⑦(池内建题密度)是第四层兜底。

**为什么要有它**(09-08 4Stock 实录):4Stock 09:30 上线,GeckoTerminal trending 当天就把它排第 1(池龄 6.4h、成交 $53M),
Binance BNCUSDT 资金费率打到 +2% 上限——这些信号 14:40 轮就能看到;而机审 ⑦ 要等系统建到第 3 条(14:35)才亮,
我自己更是到用户点名(16:5x)才认出是热点。**发现要靠外部前置信号,不能靠自家池子回声**。

三层:
  L1 dex   GeckoTerminal trending_pools + new_pools(bsc/solana/base):新池速通 / 老池放量  → 给出合约地址,直接喂实体图
  L3 cex   Binance premiumIndex |资金费率|≥1%(上限 2%) / Binance+okx 48h 内上新永续(交易所替你判了「热」)
  L2 names news-fetch.py(SSE 直连 followin)落 dump → hot-names.py 新名字跨语种共现(≥3源且≥2语种,或≥5源)
用法: hot-scan.py [dex|cex|names|all] [--chains bsc,solana,base]
注入(回归): HOTSCAN_GT_JSON=<dir> 指向含 <chain>-trending.json/<chain>-new.json 的目录;HOTSCAN_BN_JSON / HOTSCAN_BNX_JSON / HOTSCAN_OKX_JSON
判据(与 gates 闸:大热点 触发信号①③④对应):
  新池 ≤24h 且 (vol24h ≥ $10M 或 fdv ≥ $20M 且 vol ≥ $1M) → 速通(无成交量的 FDV 不算)
  任意池 vol24h ≥ $50M 且 |24h| ≥ 50%          → 放量异动
  |funding| ≥ 1%                                → 杠杆极端(2% 即上限)
  永续上新 ≤48h                                  → 交易所判热
"""
import json, os, sys, time, datetime, subprocess, urllib.request

def _get(url, hdr=None):
    """双路取数,与 okx.py/quotes.py 同源(urllib+certifi 失败退 curl)。"""
    try:
        import ssl, certifi
        ctx=ssl.create_default_context(cafile=certifi.where())
        req=urllib.request.Request(url, headers=dict({'User-Agent':'trend-scout/1.0','Accept':'application/json'}, **(hdr or {})))
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r: return r.read()
    except Exception:
        return subprocess.run(['curl','-s','-m','20','-H','Accept: application/json',url],capture_output=True,timeout=30).stdout

def _j(url, inj_path=None):
    if inj_path and os.path.exists(inj_path): return json.load(open(inj_path))
    raw=_get(url)
    if not raw: return None
    try: return json.loads(raw)
    except Exception: return None

def _f(x, d=0.0):
    try: return float(x)
    except Exception: return d

NOW=datetime.datetime.now(datetime.timezone.utc)
def _age_h(iso):
    try: return (NOW-datetime.datetime.fromisoformat(iso.replace('Z','+00:00'))).total_seconds()/3600
    except Exception: return None

def _pinned():
    try:
        reg=json.load(open(os.environ.get('CONTRACTS_JSON') or os.path.expanduser('~/.trend-scout/contracts.json'),encoding='utf-8'))
        return {(e['chain'],e['address'].lower()):k for k,e in (reg.get('tokens') or {}).items()}, set(reg.get('blocked') or {})
    except Exception: return {}, set()

def scan_dex(chains):
    out=[]; gtdir=os.environ.get('HOTSCAN_GT_JSON'); pinned,blocked=_pinned()
    for ch in chains:
        for kind in ('trending_pools','new_pools'):
            inj=os.path.join(gtdir, f"{ch}-{'trending' if kind=='trending_pools' else 'new'}.json") if gtdir else None
            d=_j(f'https://api.geckoterminal.com/api/v2/networks/{ch}/{kind}?page=1', inj)
            if d is None: out.append(('⚠️',ch,kind,'取数失败(两路都空)——本层半盲,不得据此说无异动')); continue   # None=失败;[]=真空不算半盲
            for p in d.get('data') or []:
                a=p.get('attributes') or {}
                name=(a.get('name') or '?').split(' / ')[0]
                vol=_f((a.get('volume_usd') or {}).get('h24')); fdv=_f(a.get('fdv_usd') or a.get('market_cap_usd'))
                ch24=_f((a.get('price_change_percentage') or {}).get('h24')); age=_age_h(a.get('pool_created_at') or '')
                addr=((p.get('relationships') or {}).get('base_token') or {}).get('data',{}).get('id','').split('_',1)[-1]
                tag=None
                # v3.3.3 修:新池 FDV 可由初始定价任意设(STRCx 池龄 0.1h、成交 $0、fdv $49.6M 首跑误报)——没有成交量就不算速通
                if age is not None and age<=24 and (vol>=10e6 or (fdv>=20e6 and vol>=1e6)): tag='速通·新池'
                elif vol>=50e6 and abs(ch24)>=50: tag='放量异动'
                if tag:
                    # v3.3.6:注册表联动——已钉的标 📌;⛔ 的(如 LAPTOP 仿盘)直接点名;其余给出一行 pin 命令,核实后一键钉住
                    if (ch,addr.lower()) in pinned: mark=f'📌已钉 {pinned[(ch,addr.lower())]}'
                    elif name.upper() in blocked: mark='⛔注册表标记暂不可钉(疑仿盘),见 dex.py list'
                    else: mark=f"未钉→核实后 dex.py pin {name.upper()} {ch} {addr} '<依据>'"
                    out.append(('🔥',ch,tag,f"{name:12s} 池龄={age:.1f}h vol24h=${vol/1e6:.0f}M fdv=${fdv/1e6:.1f}M 24h={ch24:+.0f}%  {addr[:12]}…  {mark}"))
    # 同一 token 可能在 trending 与 new 各出现一次,去重
    seen=set(); dedup=[]
    for r in out:
        k=(r[1],r[3][:12])
        if k in seen: continue
        seen.add(k); dedup.append(r)
    return dedup

def scan_cex():
    out=[]; now=time.time()*1000
    d=_j('https://fapi.binance.com/fapi/v1/premiumIndex', os.environ.get('HOTSCAN_BN_JSON'))
    if d is None: out.append(('⚠️','binance','funding','取数失败'))
    else:
        for x in d:
            r=_f(x.get('lastFundingRate'))
            if abs(r)>=0.01: out.append(('🔥','binance','杠杆极端',f"{x['symbol']:14s} 资金费率 {r*100:+.3f}%{'(=上限)' if abs(r)>=0.02 else ''}  标记价={x.get('markPrice')}"))
    d=_j('https://fapi.binance.com/fapi/v1/exchangeInfo', os.environ.get('HOTSCAN_BNX_JSON'))
    if d is not None:
        for s in d.get('symbols') or []:
            if now-_f(s.get('onboardDate'))<48*3600e3: out.append(('🆕','binance','永续上新≤48h',f"{s['symbol']:14s} {time.strftime('%m-%d %H:%M',time.localtime(_f(s['onboardDate'])/1000))}"))
    d=_j('https://www.okx.com/api/v5/public/instruments?instType=SWAP', os.environ.get('HOTSCAN_OKX_JSON'))
    if d is not None:
        for s in d.get('data') or []:
            lt=_f(s.get('listTime'))
            if lt and now-lt<48*3600e3: out.append(('🆕','okx','永续上新≤48h',f"{s['instId']:18s} {time.strftime('%m-%d %H:%M',time.localtime(lt/1000))}"))
    return out

def scan_names():
    """L2:每轮新拉一份 dump 再算共现;拉不到就退最近 ≤2h 的 dump;都没有→半盲。HOTSCAN_SKIP_FETCH=1 跳过拉取(回归用)。"""
    import importlib
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    nf=importlib.import_module('news_fetch'); hn=importlib.import_module('hot_names')
    dump=None
    if not os.environ.get('HOTSCAN_SKIP_FETCH'):
        try: dump,_,_=nf.fetch('6h',50)
        except Exception as e: print(f'  ⚠️ [L2·news-fetch] 拉取失败: {str(e)[:80]} → 退最近 dump')
    dumps=nf.recent(6.0)                       # v3.3.5:窗口内全部 dump,不只最新一份(召回缺口见 news_fetch.recent)
    if dump and dump not in dumps: dumps.insert(0,dump)
    if not dumps: return [('⚠️','social','L2','无 ≤6h 的 news dump——社媒层半盲,不得说「无新名字」')],0,0
    n,rows=hn.scan(dumps,6.0); out=[]
    for _,_,k,srcn,langs,first,ex,lvl in rows[:10]:
        out.append((lvl,'social','新名字共现' if lvl=='🔥' else '观察',f"{k:12s} 源={srcn} 语种={'/'.join(langs)} 首见={time.strftime('%H:%M',time.localtime(first/1000))}  e.g. [{ex[0][0]}] {ex[0][1][:14]}: {ex[0][2][:48]}"))
    return out,sum(1 for r in rows if r[-1]=='🔥'),sum(1 for r in rows if r[-1]=='👀')

if __name__=='__main__':
    a=sys.argv[1:]; mode=a[0] if a and a[0] in ('dex','cex','names','all') else 'all'
    chains=(a[a.index('--chains')+1] if '--chains' in a else 'bsc,solana,base').split(',')
    rows=[]
    if mode in ('dex','all'): rows+=scan_dex(chains)
    if mode in ('cex','all'): rows+=scan_cex()
    nf=nw=0
    if mode in ('names','all'):
        r2,nf,nw=scan_names(); rows+=r2
    hot=[r for r in rows if r[0]=='🔥']; blind=[r for r in rows if r[0]=='⚠️']
    print(f"hot-scan {time.strftime('%F %T')} | chains={','.join(chains)} | 🔥{len(hot)} 🆕{sum(1 for r in rows if r[0]=='🆕')} ⚠️{len(blind)}")
    for r in rows: print(f"  {r[0]} [{r[1]}·{r[2]}] {r[3]}")
    if not rows: print('  (无)')
    print(f"HOTSCAN: 候选={len(hot)} 新名字={nf} 观察={nw} 上新={sum(1 for r in rows if r[0]=='🆕')} 半盲={len(blind)}"+("  ← 有候选:切热点模式(gate.sh 大热点),先画实体图(合约地址已给)" if hot else ""))
