#!/usr/bin/env python3
"""排序权重批量同步(v3.7.30,11-09 用户定并当日 review 修订;试跑至 weights.json trial_until)。

  weight-sync.py [--apply]                       在期 status=0 题按档补设权重;不带 --apply 只打印计划。
                                                 档位来源:weights-tier.tsv 记过的(建题时 auto/人工 manual)优先,
                                                 没记过的(系统建题)才按 weight.py 现判。每次运行记 weights-snap.tsv 快照。
  weight-sync.py set --id ID --tier A --why "…"   人工改档:记 weights-tier.tsv(manual)并当场写看板
  weight-sync.py report                          试跑三条退出标准的现读数(按最近一次快照)

只管在期题:11-09 实测过期题后台不再重算(改权重不改分),且前台按建题日期分块、过期题不与当天题比,故不做过期复位。
数据源=b0-latest.json(--apply 时一律先重拉;只读计划时 30 分钟内拉过的直接用)。写操作只改 score_weight,逐条落 weights.log.tsv。
末行 WEIGHT: 在期=N 已对=a 改=b 记档=c 现判=d 人工档=e → 填清单「权重同步」行。
"""
import argparse, datetime, json, os, subprocess, sys, time

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import weight as W

B0 = os.environ.get('B0JSON') or os.path.join(D, 'b0-latest.json')
LOG = os.environ.get('WEIGHTS_LOG') or os.path.join(D, 'weights.log.tsv')
SNAP = os.environ.get('WEIGHTS_SNAP') or os.path.join(D, 'weights-snap.tsv')


def _now():
    return int(time.time() * 1000)


def _load_b0(refetch=True, force=False):
    # force=True(--apply 写之前):一律重拉——本轮开头拉的 b0 里没有本轮刚推上线/恢复的系统题,会漏到下一轮(11-09 review)
    try:
        d = json.load(open(B0, encoding='utf-8'))
        age = time.time() - datetime.datetime.fromisoformat(d['fetched_at']).timestamp()
    except Exception:
        d, age = None, 1e9
    if (force or d is None or age > 1800) and refetch and not os.environ.get('B0JSON'):
        subprocess.run([sys.executable, os.path.join(D, 'b0-fetch.py')], check=True, capture_output=True)
        d = json.load(open(B0, encoding='utf-8'))
    return d.get('topics') or []


def _in_period(t, now):
    return t.get('status') == 0 and (not t.get('closed_ts') or int(t['closed_ts']) >= now)


def tier_of(t):
    """(档, 依据, 来源):记过档的用记账,否则现判。"""
    rec = W.recorded(t['id'])
    if rec:
        return rec[0], rec[2], rec[1]
    tier, _, why = W.classify(t.get('domain'), t.get('title') or '', t.get('keywords') or '')
    return tier, why, 'now'


def plan(topics, now=None):
    """返回 [(topic, 期望权重, 档, 依据, 来源)],只含在期 status=0 题。"""
    now = now or _now()
    out = []
    for t in topics:
        if not _in_period(t, now):
            continue
        tier, why, src = tier_of(t)
        out.append((t, W.tier_weight(tier), tier, why, src))
    return out


def snap(rows, now):
    with open(SNAP, 'a', encoding='utf-8') as f:
        for t, w, tier, why, src in rows:
            f.write('\t'.join(str(x) for x in (now, t['id'], t.get('domain'), 1, t.get('score'), t.get('score_weight'),
                                                tier, t.get('created_at'), (t.get('title') or '').replace('\t', ' '))) + '\n')


def _write(c, tid, w):
    if c[0] is None:
        from console import Console
        c[0] = Console()
    return c[0].call('update_trending_topic', {'id': int(tid), 'score_weight': w})


def sync(apply):
    topics = _load_b0(force=apply)
    now = _now()
    rows = plan(topics, now)
    snap(rows, now)
    ok = chg = 0
    c = [None]
    todo = []
    for t, w, tier, why, src in rows:
        cur = t.get('score_weight')
        if cur is not None and abs(float(cur) - float(w)) < 1e-9:
            ok += 1
        else:
            todo.append((t, cur, w, tier, why, src))
    for t, cur, w, tier, why, src in todo:
        print(f'  {"✔" if apply else "·"} 设 {t["id"]} {cur}→{w:g} [{tier} {why}|{src}]「{(t.get("title") or "")[:30]}」')
        if not apply:
            continue
        r = _write(c, t['id'], w)
        if not r.get('success'):
            print(f'    🚨 写失败: {json.dumps(r, ensure_ascii=False)[:150]}')
            continue
        chg += 1
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('\t'.join(str(x) for x in (now, t['id'], cur, w, tier, why)) + '\n')
    if not apply and todo:
        print('  (只读计划;加 --apply 才写)')
    n_rec = sum(1 for r in rows if r[4] in ('auto', 'manual'))
    n_man = sum(1 for r in rows if r[4] == 'manual')
    print(f'WEIGHT: 在期={len(rows)} 已对={ok} 改={chg if apply else 0} 待改={0 if apply else len(todo)} '
          f'记档={n_rec} 现判={len(rows) - n_rec} 人工档={n_man}')


def set_tier(tid, tier, why):
    if tier not in ('A', 'B', 'C', 'D') or not (why or '').strip():
        sys.exit('🚨 --tier 只能 A/B/C/D,且 --why 必填(人工定档理由)')
    W.record(_now(), tid, tier, 'manual', why.strip())
    r = _write([None], tid, W.tier_weight(tier))
    print(('✔' if r.get('success') else '🚨') + f' {tid} → {tier}({W.tier_weight(tier):g}) {why}')
    if r.get('success'):
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('\t'.join(str(x) for x in (_now(), tid, '?', W.tier_weight(tier), tier, '人工:' + why.strip())) + '\n')


def report():
    if not os.path.exists(SNAP):
        print('还没有快照')
        return
    rows = [l.rstrip('\n').split('\t') for l in open(SNAP, encoding='utf-8')]
    last = max(int(r[0]) for r in rows)
    cur = [r for r in rows if int(r[0]) == last and r[3] == '1']

    def sc(r):
        try:
            return float(r[4])
        except ValueError:
            return float('-inf')
    cur.sort(key=sc, reverse=True)
    print(f'快照 {datetime.datetime.fromtimestamp(last / 1000):%m-%d %H:%M} 在期 {len(cur)} 条(按 score;前台同一天内带「热议」标签的题固定在前,接口看不到标签,以网页为准):')
    for i, r in enumerate(cur, 1):
        print(f'  {i:2d}. {r[6]} score={r[4]:>9} 权重={r[5]:>5} {r[8][:30]}')
    # ① 建题后 4 小时内的 tradfi 题里,A 档被非 A 档压住的对数(11-09 用户定改判据:分数前几小时不动、之后每小时掉约 80~100,
    #    早上建的 A 档晚上必然排到新题后面,那是衰减不是档位错;只比两道题都在建题 4h 内的那些快照)。
    #    币圈题多数带「热议」标签、在前台另成一组(11-09 网页实看),不放进来比。扫全部快照,同一对只计一次。
    def _age_h(r):
        try:
            return (int(r[0]) - datetime.datetime.strptime(r[7], '%Y-%m-%d %H:%M:%S').timestamp() * 1000) / 3.6e6
        except ValueError:
            return 1e9
    snaps = {}
    for r in rows:
        if r[3] == '1' and r[2] == 'tradfi' and _age_h(r) <= 4:
            snaps.setdefault(r[0], []).append(r)
    pairs = {}
    for ts, rs in snaps.items():
        for a in rs:
            for b in rs:
                if a[6] == 'A' and b[6] != 'A' and sc(b) > sc(a):
                    pairs.setdefault((a[1], b[1]), (a, b))
    print(f'① 建题 4h 内的美股/亚股题里 A 档分数低于非 A 档:{len(pairs)} 对' + ''.join(f'\n     {a[1]} < {b[1]} {b[8][:24]}' for a, b in list(pairs.values())[:5]))
    # ② D 档分数高于主流币 C 档
    majors = [r for r in cur if r[6] == 'C' and r[2] == 'crypto']
    lo = min((sc(r) for r in majors), default=None)
    d_above = [r for r in cur if r[6] == 'D' and lo is not None and sc(r) > lo]
    print(f'② D 档分数高于主流币 C 档:{len(d_above)} 条' + ''.join(f'\n     {r[1]} {r[8][:30]}' for r in d_above))
    # ③ 各档不含权重的分数每小时增长(首末快照之差,跨度≥1h)
    by = {}
    for r in rows:
        try:
            base = float(r[4]) - float(r[5])
        except ValueError:
            continue
        by.setdefault(r[1], []).append((int(r[0]), base, r[6]))
    agg = {}
    for tid, xs in by.items():
        xs.sort()
        if len(xs) < 2 or xs[-1][0] - xs[0][0] < 3600000:
            continue
        agg.setdefault(xs[-1][2], []).append((xs[-1][1] - xs[0][1]) / ((xs[-1][0] - xs[0][0]) / 3600000))
    # ③ 判档抽查清单:最近一次快照里的在期题逐条列档位与依据,人工核对(11-09 review:分数不跟点击走——JCT 热议数 3K→27.6K 时分数 251→236,
    #    所以「提权带没带来点击」用分数量不出来,不作判据;分数增长只作参考)
    last_rows = {r[1]: r for r in rows if int(r[0]) == last}
    print('③ 判档抽查(人工逐条核,错一条记一条;错误率 >10% 或同类错 ≥2 次当轮修 weight.py 并补用例):')
    for tid in [r[1] for r in cur]:
        rec = W.recorded(tid)
        r = last_rows[tid]
        why = rec[2] if rec else W.classify(r[2], r[8])[2]
        print(f'     {tid} {r[6]} {why[:18]:<18} {r[8][:30]}')
    print('   参考·不含权重的分数每小时变化(中位数,不代表点击):' + ('' if agg else ' 样本不足'))
    for k in sorted(agg):
        v = sorted(agg[k])
        print(f'     {k}: n={len(v)} 中位 {v[len(v) // 2]:.3f}/h')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'report':
        report()
    elif len(sys.argv) > 1 and sys.argv[1] == 'set':
        p = argparse.ArgumentParser()
        p.add_argument('cmd')
        p.add_argument('--id', required=True)
        p.add_argument('--tier', required=True)
        p.add_argument('--why', required=True)
        a = p.parse_args()
        set_tier(a.id, a.tier, a.why)
    else:
        sync('--apply' in sys.argv)
