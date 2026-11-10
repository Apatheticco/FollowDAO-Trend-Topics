#!/usr/bin/env python3
"""scatter.py — 规则散点度量(v3.1.7, 周报提案「字节上限换散点指标」)。

**为什么不用字节数**:gates.md 的 112KB 上限度量的是「规则集有多大」,而真正伤人的是
「同一条判据在几个地方各写了一份」——改一处漏另一处,同一道题两版可判反。三条实证:
  · meme 豁免三选一:gates A闸写 5 项、review-agent.md 写三选一,09-03 BONK 按两版可判反(v3.0.5 归一)
  · 美股四时段表:gates 1-1 + 双要素⏰ + 事件日历③ + data-quickref ×2,五处(v3.0.7 改指针)
  · MAJORS 白名单:b0-cull.py + log-action.sh 各写 62 个 ticker(v3.1.4 抽 majors.json)
**三次归一,字节数几乎没动**(103KB→103KB),散点数从 9 降到 3——字节和散点是两个正交的量,
而只有散点会让规则**自相矛盾**。

判据形状:每个受监控概念给一条只匹配「完整定义」的正则(必须含具体数值/枚举项),
纯指针("见 闸:A闸"、"单点事实源＝本行")不该命中。命中 >1 处 = 散点。
用法: scatter.py [--json]   退出码:超基线=1
"""
import json, os, re, sys

D = os.path.expanduser('~/.trend-scout')
# v3.5.1:与 run-tests.sh 第 4 行同约定,认 GATES 环境变量。
#   原先写死 ~/Desktop/... ,导致「把脚本包装进隔离环境跑回归」这件事做不了——
#   run-tests.sh 明明让 GATES 可注入,scatter.py 却忽略它,隔离环境里必报两条假分叉。
G = os.environ.get('GATES') or os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic')
WATCH = os.environ.get('SCATTER_WATCH') or os.path.join(D, 'scatter-watch.json')

def _files(scope):
    out = []
    for pat in scope:
        base = G if pat.startswith(('references/', 'SKILL', 'LESSONS')) else D
        p = os.path.join(base, pat)
        if os.path.exists(p): out.append((pat, p))
    return out

def _vals(txt, pat):
    """抽该判据的**关键值**(由 watch 的 value_pattern 声明),不是抽范围内所有数字。
    第一版抽了所有数字,gates 那处多抓到反例里的 7.2% 就误报分叉——**指标自己产生假阳性,
    比没有指标更糟:它会训练人忽略告警**。改为只认声明过的关键值。"""
    return {v.replace(' ', '') for v in re.findall(pat, txt)}

def scan():
    w = json.load(open(WATCH, encoding='utf-8'))
    res = []
    for c in w['concepts']:
        if c.get('disabled'): continue
        rx = re.compile(c['fingerprint'], re.S)
        mode = c.get('mode', 'single')
        hits, sigs = [], []
        for name, path in _files(c['scope']):
            try: txt = open(path, encoding='utf-8', errors='ignore').read()
            except Exception: continue
            ms = rx.findall(txt)
            ms = [m if isinstance(m, str) else ''.join(m) for m in ms]
            if ms:
                hits.append((name, len(ms)))
                for m in ms: sigs.append((name, m))
        total = sum(n for _, n in hits)
        exp = c.get('expect', 1)
        if mode == 'sync':
            # 允许多副本(跨进程/跨文件必要),但每个副本都必须含齐单点事实源里的关键值
            vp = c['value_pattern']; src = c['source_file']
            per = {}
            for n, m in sigs: per.setdefault(n, set()).update(_vals(m, vp))
            sv = per.get(src, set())
            detail, scat = [], 0
            if not sv:
                scat = 1; detail = [f"⚠️ 单点事实源 {src} 没抽到关键值——指纹或 value_pattern 已失效,不是真分叉"]
            else:
                for n, vs in per.items():
                    if n == src: continue
                    miss = sv - vs
                    if miss:
                        scat += 1; detail.append(f"{n} 缺 {'/'.join(sorted(miss))}（源 {src} 有 {'/'.join(sorted(sv))}）")
            detail = detail or None
        elif total == 0 and exp >= 1:
            # 11-03:零命中原先算 0 散点、报 ✅——「主流标的白名单」指纹因 majors.json 改成多行排序后失效,一直显示通过。
            # 看不见单点事实源 = 这一项没人看守,和 sync 模式「源没抽到关键值」同等处理:计 1,让回归失败。
            scat = 1; detail = [f"⚠️ 一处定义都没命中(应有 {exp} 处)——指纹已失效,不是真散点;改指纹让它重新命中单点事实源"]
        else:
            scat = max(0, total - exp); detail = None
        res.append({'name': c['name'], 'source': c['source'], 'hits': hits, 'expect': exp,
                    'mode': mode, 'total': total, 'scatter': scat, 'detail': detail})
    return w, res

def main():
    w, res = scan()
    total_scatter = sum(r['scatter'] for r in res)
    base = w.get('baseline', total_scatter)
    if '--json' in sys.argv:
        print(json.dumps({'total': total_scatter, 'baseline': base, 'items': res},
                         ensure_ascii=False, indent=2)); 
    else:
        print(f"散点总数 {total_scatter}（基线 {base}）")
        for r in sorted(res, key=lambda x: -x['scatter']):
            mark = '🔴' if r['scatter'] else '✅'
            loc = ', '.join(f"{n}×{k}" for n, k in r['hits']) or '(未命中——指纹可能已失效,需复核)'
            tag = '副本一致' if r['mode'] == 'sync' and not r['scatter'] else ('副本已分叉' if r['mode'] == 'sync' else f"允许 {r['expect']}")
            print(f"  {mark} {r['name']}: {r['total']} 处定义 / {tag} [{loc}]")
            if r['scatter']:
                print(f"      单点事实源应为: {r['source']}")
                if r.get('detail'):
                    for d in r['detail']: print(f"      · {d}")
        if not any(r['total'] for r in res):
            print("  ⚠️ 全部概念都未命中——watch 文件的指纹可能整体失效,这比散点更危险")
    if total_scatter > base:
        print(f"❌ 散点 {total_scatter} > 基线 {base}:新规则又把同一条判据写了第二遍——先归一到单点事实源再加")
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
