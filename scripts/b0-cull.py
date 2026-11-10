#!/usr/bin/env python3
# b0-cull.py — 机审灌水形态的机械撤（v2.9.83）。复用 b0-fetch.py 的 console-mcp 传输，每条撤完立即 log-action.sh cull 落账。
# 用法: b0-cull.py --rc <reason_code> --note "<备注>" [--dry] <id> [<id>...]
#       只允许灌水族/疑问句/缺价格腿/重复 这几类机械撤因；meme 题的价格类撤因要四查，机械撤做不了 → 转人工（v3.6.2，与 log-action 同闸）。
import sys, os, subprocess, json
sys.path.insert(0, os.path.expanduser('~/.trend-scout'))
from b0_fetch import cfg, rpc  # 见 b0_fetch.py 软链
ALLOWED={'灌水-KOL观点','灌水-产品公告','灌水-vanity指标','灌水-融资无标的','灌水-立法程序','疑问句-悬念','缺价格腿','重复-碎片合并','重复-同标的','过期-窗口题','链上红线-托管流水/多空对赌'}
# v3.1.0 meme 铁律真正落到机械撤路径。
#   09-06 查出的根因:log-action.sh 的 meme 闸靠「备注里有没有出现 meme/小市值/微型 字样」触发,
#   而机械撤的备注是固定模板、永远不含该词——**绕过不是偶然是必然**,是个自证式的闸(不提就不查)。
#   这里改成从题目本身判:crypto 域 + 标的不在主流白名单 = 按小市值/meme 处理,rc 必须落三类正当理由。
MEME_OK_RC={'重复-同标的','重复-碎片合并','已证伪','事实错误-数字','事实错误-定义'}  # 三类:同标的重复/已证伪/事实错误
# v3.1.1 同轮即修:meme 铁律只对**可能误杀真实价格动作**的撤因启用。
#   v3.1.0 首跑即误伤 4/5——Vitalik 的 EIP 路线图、Jesse Pollak 账户被盗、Clarity Act 立法题全被当成 meme 拦下。
#   根因:我把「crypto 域+非主流标的」等同于 meme,但 v2.9.7 铁律原文写着「仍走 A 闸的只剩:纯公告无价格动作、纯 KOL 口水」
#   ——即豁免保护的对象是**小市值币的价格题**,纯观点/纯公告本就不在保护范围内,我的实现漏了这半句。
MEME_GUARDED_RC={'缺价格腿','缺诱因-未达线','灌水-vanity指标','灌水-悬念疑问'}   # 与 log-action GUARD 同步(v3.6.1 移出疑问句;v3.6.2 加缺诱因-未达线)
def _majors():
    """v3.1.4(提案5-3):主流标的白名单的单一事实源=majors.json。此前本文件与 log-action.sh 各内嵌一份副本,
    是 09-06 四问④ 抓到的散点。读不到文件时返回空集=全部按小币处理(保守方向,宁可多拦不可漏放)。"""
    import json as _j
    p=os.environ.get('MAJORS_JSON') or os.path.expanduser('~/.trend-scout/majors.json')
    try: return set(_j.load(open(p))['majors'])
    except Exception: return set()
def _preview_guard(ids, rc, note):
    if '非预告:' in (note or '') or '非预告：' in (note or ''):
        return []
    import json, sys as _sys
    _sys.path.insert(0, os.path.expanduser('~/.trend-scout'))
    import lint
    try:
        d=json.load(open(os.environ.get('B0JSON') or os.path.expanduser('~/.trend-scout/b0-latest.json')))
        rows=d if isinstance(d,list) else (d.get('topics') or [])
    except Exception:
        return []
    title={str(x.get('id')):(x.get('title') or x.get('original_title') or '') for x in rows}
    return [(i,title.get(str(i),'')) for i in ids if lint.preview_misfiled(rc, title.get(str(i),''))]


def _meme_guard(ids, rc):
    """返回需要人工判的 id 列表(crypto 小币 + rc 不在三类内)。查不到题目信息的按保守=需人工判。"""
    import re
    _snap=os.environ.get('B0JSON') or os.path.expanduser('~/.trend-scout/b0-latest.json')  # v3.1.2 可注入
    try: rows=json.load(open(_snap))
    except Exception: return list(ids)  # 快照读不到 → 全部转人工,不放行
    rows = rows if isinstance(rows,list) else (rows.get('topics') or rows.get('data') or [])
    m={str(t.get('id')):t for t in rows}
    if rc in MEME_OK_RC: return []
    if rc not in MEME_GUARDED_RC: return []   # v3.1.1 形态明确的撤因(KOL观点/产品公告/融资/立法/窗口题/链上红线)不走 meme 闸
    need=[]
    for i in ids:
        t=m.get(str(i))
        if t is None: need.append(i); continue
        # v3.4.4(P0-2) 作用域判定收归 lint.meme_scope(与 log-action.sh 同一实现):无代币标的的题不受铁律保护
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import lint as _lint
        try:
            import token_exist as _te; _ex = _te.exists   # v3.6.0 方案B:与 log-action.sh 同一判据
        except Exception:
            _ex = None
        if not _lint.meme_scope(t, _ex): continue
        need.append(i)
    return need
def main():
    a=sys.argv[1:]; rc=note=None; dry=False; ids=[]
    i=0
    while i<len(a):
        if a[i]=='--rc': rc=a[i+1]; i+=2
        elif a[i]=='--note': note=a[i+1]; i+=2
        elif a[i]=='--dry': dry=True; i+=1
        else: ids.append(a[i]); i+=1
    if not (rc and note and ids): raise SystemExit(__doc__ or 'usage: b0-cull.py --rc <rc> --note <备注> [--dry] <id>...')
    if rc not in ALLOWED: raise SystemExit(f'🚨 {rc} 不是机械撤允许的撤因(只许灌水族/疑问句/缺价格腿/重复/窗口题/链上红线)')
    _pv=_preview_guard(ids, rc, note)
    if _pv:
        print(f'🚨 10-23 复盘:以下 {len(_pv)} 条标题是预告形态,撤因不该记「灌水-产品公告」——按预告题准入三档判,'
              f'不过就用 topic.py cull --rc 预告题-准入不过 逐条撤(确非预告:备注写「非预告:<理由>」)')
        for i,t in _pv: print(f'   ✋ {i} {t[:40]}')
        ids=[i for i in ids if i not in {x for x,_ in _pv}]
    blocked=_meme_guard(ids, rc)
    if blocked:
        print(f'🚨 v2.9.7 meme铁律(v3.1.0 机械撤路径补齐):以下 {len(blocked)} 条是 crypto 小市值/meme 题,'
              f'撤因「{rc}」须过四查(幅度/成交额/市值关口/硬事件全否,v3.6.2)——转人工实测后用 log-action.sh 带四查行落账,不得机械撤')
        for i in blocked: print(f'   ✋ {i}')
        print('   提示:缺价格腿/vanity 是**改题**的理由,不是撤 meme 的理由(09-05 12041 实录);'
              '「核不了/市值小/纯投机」是禁用撤因;拿不准→留')
        ids=[i for i in ids if i not in blocked]
        if not ids: raise SystemExit(1)
        print(f'   → 其余 {len(ids)} 条继续机械撤')
    if dry:
        print(f'[dry] 将撤 {len(ids)} 条 rc={rc}: {" ".join(ids)}'); return
    url,headers=cfg()
    r,sid=rpc(url,headers,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trend-scout-cull","version":"1"}}})
    if 'error' in r: raise SystemExit(f"🚨 initialize 失败: {r['error']}")
    try: rpc(url,headers,{"jsonrpc":"2.0","method":"notifications/initialized"},sid)
    except Exception: pass
    n=0
    for k,i in enumerate(ids):
        r,sid=rpc(url,headers,{"jsonrpc":"2.0","id":10+k,"method":"tools/call","params":{"name":"update_trending_topic","arguments":{"id":int(i),"status":3}}},sid)
        txt=next((c.get('text') for c in r.get('result',{}).get('content',[]) if c.get('type')=='text'),'')
        ok=('"success":true' in txt.replace(' ',''))
        print(('✔' if ok else '❌'), i, txt[:120].replace('\n',' '))
        if ok:
            # v3.7.0 撤时标题进备注:撤后系统还会改写已隐藏题的标题(10-14/10-15 三例),送审清单要的是撤的那一刻的标题
            try: _t=json.loads(txt).get('title') or ''
            except Exception: _t=''
            subprocess.run([os.path.expanduser('~/.trend-scout/log-action.sh'),'cull',str(i),rc,(f'『{_t}』' if _t else '')+f'{note}(b0-cull机械撤)'],check=False)
            n+=1
    print(f'机械撤完成 {n}/{len(ids)} [{rc}]')
if __name__=='__main__': main()
