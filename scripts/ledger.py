#!/usr/bin/env python3
"""ledger.py — 台账读取的单一实现(v3.7.0):建题真实 id 解析 + 拒写/未落账的「已处理」判定。

病根(10-15 托管 review 实测):09-24 起建题改成「先记账、后建题」,create 行写台账时题还不存在,id 只能记「-」,
真实 id 落在随后那条「状态修正·建题后推」行。所有按 create 行 id 关联的消费者从此静默失效——
  周报 ②团队打回率、⑤返工率 分母恒为 1(三份周报都印着 0%)、b0-audit ⑤ 把我建的题当成系统建、
  上游垃圾统计把我撤我自己建的题算成系统垃圾。
v3.7.0 起 topic.py 建完题用真实 id 落账;本模块给历史「-」行补接:按出现顺序 FIFO 接到其后第一条带
「建题后推」的状态修正行(10-15 实测 09-24 以来 76/76 接上、无重复、无超 1h 间隔)。

用法(命令行):
  ledger.py created [天数]          列出我建的题(真实 id)
  ledger.py unresolved <run_ts>     列出本轮未处理的拒写/未落账行(checklist.sh verify 调用;有输出=不得出报告)
  ledger.py reject-stats [天数]     拒写(工具拦截)按周计数:总数/已处理
注入(回归):ACTIONS / REJ / REJ_OK / UNLOGGED 环境变量改路径。
"""
import os, sys, time, collections

D = os.path.expanduser('~/.trend-scout')
PUB_MARK = ('建题后推', 'create后')          # 建题后自推 status=0 那条「状态修正」行的备注标记(11-05 前旧写法)
PUB_SUFFIX = '｜建后自推上线(发布三问已核)'     # 11-05 用户定:建题与自推上线合成一行,create 行备注尾带此标记,不再另写状态修正行


def self_published(r):
    """create 行是否同轮自推上线(新写法看备注尾标记;旧写法由 create_links 接状态修正行,调用方自己并)。"""
    return r[1] == 'create' and PUB_SUFFIX in (r[4] or '')
WRITE = ('create', 'cull', 'update', 'restore', 'merge', 'publish')


def _p(env, name):
    return os.environ.get(env) or os.path.join(D, name)


def rows(path=None):
    """台账结构化行:[ts:int, action, id, rc, note, delta];非 13 位时间戳开头的行(孤儿续行/注释)跳过。"""
    path = path or _p('ACTIONS', 'actions.tsv')
    out = []
    if not os.path.exists(path):
        return out
    for l in open(path, encoding='utf-8'):
        if l.startswith('#') or not l.strip():
            continue
        p = l.rstrip('\n').split('\t')
        if len(p) < 4 or not p[0].isdigit():
            continue
        while len(p) < 6:
            p.append('')
        p[0] = int(p[0])
        out.append(p)
    return out


def create_links(rs):
    """{行下标: 真实 id}。带真实 id 的 create 行映射到自己;「-」行按 FIFO 接其后第一条带建题后推标记的状态修正行。
    间隔超 2 小时不接(那条建题没推上线,硬接会张冠李戴)。"""
    links, q = {}, []
    for i, r in enumerate(rs):
        if r[1] == 'create':
            if r[2] not in ('-', ''):
                links[i] = r[2]
            else:
                q.append(i)
        elif q and r[1] == 'update' and r[3] == '状态修正' and r[2] not in ('-', '') \
                and any(m in r[4] for m in PUB_MARK):
            j = q.pop(0)
            if r[0] - rs[j][0] <= 2 * 3600 * 1000:
                links[j] = r[2]
    return links


def created(rs=None, since_ms=0):
    """[(create_ts, 真实id, 行)],按时间顺序。"""
    rs = rows() if rs is None else rs
    L = create_links(rs)
    return [(rs[i][0], rid, rs[i]) for i, rid in sorted(L.items()) if rs[i][0] >= since_ms]


def created_ids(path=None):
    return {rid for _, rid, _ in created(rows(path))}


# ── 拒写 / 未落账:改成「标记已处理」,不再删行 ─────────────────────────────
# v3.7.0 之前 checklist verify 要求把拒写行删掉才放行——工具拦下的错误证据被清空,周报看不到「被拦了几次」
# (10-12~10-14 至少 4 次拒写,文件里是 0 条)。现在拒写行一律保留;已处理的判定:
#   ① 显式:log-action.sh reject-ok <拒写行ts> <说明>  → actions-rejected-resolved.tsv
#   ② 自动:拒写行带结构列(动作/id)且其后台账出现同动作同 id 的落账行(建题拒写 id 为「-」→ 其后任一建题行)
def _rej_rows(path):
    out = []
    if not os.path.exists(path):
        return out
    for l in open(path, encoding='utf-8'):
        p = l.rstrip('\n').split('\t')
        if p and p[0].isdigit():
            out.append(p)
    return out


def resolved_ts():
    s = set()
    p = _p('REJ_OK', 'actions-rejected-resolved.tsv')
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            x = l.rstrip('\n').split('\t')
            if len(x) >= 2 and x[1].isdigit():
                s.add(x[1])
    return s


def _auto_ok(act, tid, ts, rs):
    floor = (ts // 1000) * 1000      # 台账行 ts 是「秒+000」,拒写行是真毫秒:同一秒内先拒后落账,台账行 ts 反而更小
    for r in rs:
        if r[0] < floor or r[1] != act:
            continue
        if tid in ('-', '') and act == 'create':
            return True
        if r[2] == tid:
            return True
    return False


def unresolved(run_ts):
    run_ts = int(run_ts)
    rs = rows()
    ok = resolved_ts()
    bad = []
    for kind, path in (('拒写', _p('REJ', 'actions-rejected.tsv')), ('未落账', _p('UNLOGGED', 'actions-unlogged.tsv'))):
        for p in _rej_rows(path):
            ts = int(p[0])
            if ts < run_ts or p[0] in ok:
                continue
            act = p[2] if len(p) > 3 else ''
            tid = p[3] if len(p) > 3 else ''
            if act and _auto_ok(act, tid, ts, rs):
                continue
            bad.append((kind, p))
    return bad


def reject_stats(days=7):
    cut = int((time.time() - days * 86400) * 1000)
    ok = resolved_ts()
    rs = rows()
    tot = done = 0
    for p in _rej_rows(_p('REJ', 'actions-rejected.tsv')):
        ts = int(p[0])
        if ts < cut:
            continue
        tot += 1
        act = p[2] if len(p) > 3 else ''
        tid = p[3] if len(p) > 3 else ''
        if p[0] in ok or (act and _auto_ok(act, tid, ts, rs)):
            done += 1
    return tot, done


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('created', 'unresolved', 'reject-stats'):
        print(__doc__)
        sys.exit(2)
    if a[0] == 'created':
        days = float(a[1]) if len(a) > 1 else 7
        cut = int((time.time() - days * 86400) * 1000)
        for ts, rid, r in created(since_ms=cut):
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(ts / 1000))}\t{rid}\t{r[3]}\t{r[5][:60]}")
    elif a[0] == 'unresolved':
        if len(a) < 2:
            sys.exit('用法: ledger.py unresolved <run_ts>')
        for kind, p in unresolved(a[1]):
            print(f"{kind}\t" + '\t'.join(p[:5]))
    else:
        days = float(a[1]) if len(a) > 1 else 7
        tot, done = reject_stats(days)
        print(f"拒写 {tot} 次(已处理 {done} / 未处理 {tot - done})")


if __name__ == '__main__':
    main()
