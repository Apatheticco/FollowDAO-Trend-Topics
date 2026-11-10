#!/usr/bin/env python3
"""qualify.py — 切定时任务的资格线(v3.7.1,用户 10-15 定,取代「用户点名→0 稳 2~3 周」)。

为什么换:点名为 0 依赖用户在看。10-12~10-15 用户只敲「跑auto模式」不审,点名两周都是 0,
同期复审员确认成立的错误 3、7 次——旧北极星在「人退出」的那一刻自动达标,恰好在最不该放行时放行。

四条(按自然周算,连续 2 周全过才算达标):
  ① 盲审一致率 ≥ 阈值:你盲审(只看题面)判留/撤,与生产终态比对。来源 blind-audit.tsv(blind-audit.py 写)。
     阈值暂定 85%(QUALIFY_BLIND_MIN 可调),264 题复测出基线后再定;当周没盲审=✗(没测≠达标)。
  ② 下游错标 0:downstream.log.tsv 里「错标/域不符」(已登记「误报更正」的题,更正之前的行不算,11-10)。
  ③ 机械类错误 0:上了看板才发现的机械错——「纠错-自纠」改题 + 看板已写却没落账(actions-unlogged.tsv)。
     被工具当场拦下的不算(那是闸在起作用)。
  ④ 无「跑挂没消息」:该周每轮 checklist start 都有一条推送成功记录(lark-push.log.tsv 同 run_ts、status=ok)。

用法: qualify.py [周数=2]   打印最近 N 个自然周(周一起算,含本周)逐条结果
      import qualify; qualify.report()  → (文字行列表, 是否达标)
"""
import os, sys, time, datetime, re

D = os.path.expanduser('~/.trend-scout')
sys.path.insert(0, D)
BLIND_MIN = float(os.environ.get('QUALIFY_BLIND_MIN') or 0.85)


def _p(env, name):
    return os.environ.get(env) or os.path.join(D, name)


def _tsv(path):
    if not os.path.exists(path):
        return []
    out = []
    for l in open(path, encoding='utf-8'):
        x = l.rstrip('\n').split('\t')
        if x and x[0].isdigit():
            out.append(x)
    return out


def weeks(n=2, now=None):
    now = now or datetime.datetime.now()
    mon = (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for k in range(n):
        a = mon - datetime.timedelta(days=7 * k)
        b = a + datetime.timedelta(days=7)
        out.append((int(a.timestamp() * 1000), int(min(b, now).timestamp() * 1000), a))
    return out[::-1]


def check(lo, hi):
    """返回 [(条目, 是否过, 说明)]"""
    res = []
    # ① 盲审
    b = [x for x in _tsv(_p('BLIND_AUDIT', 'blind-audit.tsv')) if lo <= int(x[0]) < hi and len(x) >= 6]
    if b:
        agree = sum(1 for x in b if x[5] == '1')
        r = agree / len(b)
        res.append(('盲审一致率', r >= BLIND_MIN, f'{agree}/{len(b)}={r:.0%}(线 {BLIND_MIN:.0%})'))
    else:
        res.append(('盲审一致率', False, '本周未盲审(没测≠达标)'))
    # ② 下游错标
    # 11-10:检测器自己判错的(downstream.py false-alarm 登记的「误报更正」)不算——该题在更正之前的错标行剔掉
    _dl = _tsv(_p('DOWNSTREAM_LOG', 'downstream.log.tsv'))
    _fa = {}
    for x in _dl:
        if len(x) >= 4 and x[3] == '误报更正':
            _fa[x[2]] = max(_fa.get(x[2], 0), int(x[0]))
    ds = {x[2] for x in _dl
          if lo <= int(x[0]) < hi and len(x) >= 4 and x[3] in ('错标', '域不符') and int(x[0]) > _fa.get(x[2], 0)}
    res.append(('下游错标', not ds, f'{len(ds)} 题' + (f'({",".join(sorted(ds))})' if ds else '')))
    # ③ 机械类错误
    import ledger
    fix = [r for r in ledger.rows() if lo <= r[0] < hi and r[1] == 'update' and r[3] == '纠错-自纠']
    unl = [x for x in _tsv(_p('UNLOGGED', 'actions-unlogged.tsv')) if lo <= int(x[0]) < hi]
    res.append(('机械类错误', not fix and not unl, f'纠错-自纠 {len(fix)} 次、看板已写未落账 {len(unl)} 次'))
    # ④ 跑挂没消息
    starts = []
    cl = _p('CHECKLOG', 'checklists.log.tsv')
    if os.path.exists(cl):
        for l in open(cl, encoding='utf-8'):
            m = re.search(r'^# mode=\S+ ts=(\d{13})', l)
            if m and lo <= int(m.group(1)) < hi:
                starts.append(m.group(1))
    cur = _p('CHECKLIST_CUR', 'current-checklist.tsv')
    if os.path.exists(cur):
        m = re.search(r'ts=(\d{13})', open(cur, encoding='utf-8').readline())
        if m and lo <= int(m.group(1)) < hi:
            starts.append(m.group(1))       # 进行中的轮次也算:开了跑却没推,正是这条要抓的
    # 主消息发出即算有消息:partial=主卡已到、线程回复被 429 限流(10-09/10-13 各一次),不是「没消息」
    ok = {x[1] for x in _tsv(_p('LARK_LOG', 'lark-push.log.tsv')) if len(x) >= 8 and x[7] in ('ok', 'partial') and x[6] not in ('', '-')}
    miss = [s for s in starts if s not in ok and int(s) < hi - 3600 * 1000]   # 开跑不足 1 小时的不判
    res.append(('跑挂没消息', not miss, f'{len(starts)} 轮,无推送 {len(miss)} 轮'
                + (' (' + ','.join(time.strftime('%m-%d %H:%M', time.localtime(int(s) / 1000)) for s in miss[:4]) + ')' if miss else '')))
    return res


def report(n=2):
    lines, passed = [], []
    for lo, hi, a in weeks(n):
        r = check(lo, hi)
        ok = all(x[1] for x in r)
        passed.append(ok)
        lines.append(f"- {a:%m-%d} 起一周：{'✅ 四条全过' if ok else '❌ 未达标'}｜" +
                     '；'.join(f"{'✓' if p else '✗'}{k} {d}" for k, p, d in r))
    streak = 0
    for p in reversed(passed):
        if not p:
            break
        streak += 1
    return lines, streak


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    lines, streak = report(n)
    print('\n'.join(lines))
    print(f"连续达标 {streak} 周(需 2 周)")


if __name__ == '__main__':
    main()
