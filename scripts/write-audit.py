#!/usr/bin/env python3
"""write-audit.py — 台账外写操作检测(v3.5.10,2026-09-22)。

为什么要有:09-22 实测 Evose 子 Agent 被项目派发时,能经 find_tool/exec_tool 调到没勾选的写工具
  (update_trending_topic 请求直达线上服务端,无权限拦截)。「只判不写」只剩提示词约束。
  本脚本不拦截,只保证这类写入不会悄悄发生:收尾时拿开跑 B0 与收尾 B0 逐题比,
  线上有变化而本轮台账没有对应写操作的,一律报 🚨。

用法:write-audit.py <开跑 B0> <收尾 B0> <run_ts> [actions.tsv]
  B0 = b0-latest.json 格式({"date_range": "YYYY-MM-DD ~ YYYY-MM-DD", "topics": [...]});只含 status 0/1/2,
  所以题目从 B0 里消失 = 被隐藏(撤)或滑出日期窗口,按 created_at 区分。
  台账默认 ~/.trend-scout/actions.tsv,取 run_ts_ms >= run_ts 的写操作(create/cull/update/merge/restore/publish)。
输出每条异常一行,末行 WRITE-AUDIT: 汇总;有台账外改动退出码 1。
新增而台账无记录的题只提示不报警:系统自己也会建题,单凭 B0 分不出是系统建的还是越权建的,交人看。
"""
import json, os, sys

WRITE = {'create', 'cull', 'update', 'merge', 'restore', 'publish'}
FIELDS = ('title', 'status', 'keywords')


def load(p):
    d = json.load(open(p, encoding='utf-8'))
    topics = d['topics'] if isinstance(d, dict) else d
    start = (d.get('date_range') or '').split('~')[0].strip() if isinstance(d, dict) else ''
    return {int(t['id']): t for t in topics}, start


def ledger(path, run_ts):
    ids = {}
    for ln in open(path, encoding='utf-8'):
        if ln.startswith('#'):
            continue
        c = ln.rstrip('\n').split('\t')
        if len(c) < 3 or not c[0].isdigit() or int(c[0]) < run_ts or c[1] not in WRITE:
            continue
        if c[2].isdigit():
            ids.setdefault(int(c[2]), []).append(c[1])
    return ids


def main(a):
    if len(a) < 3:
        sys.exit(__doc__)
    before, _ = load(a[0])
    after, start = load(a[1])
    if not start and after:
        # Evose 手册合并出的 B0 只有 topics、没有 date_range:以收尾 B0 里最早一题的日期作窗口起点,
        # 跨午夜时旧题滑出窗口才不会被误报成「消失」
        start = min((str(t.get('created_at', ''))[:10] for t in after.values() if t.get('created_at')), default='')
    run_ts = int(a[2])
    led = ledger(a[3] if len(a) > 3 else os.path.expanduser('~/.trend-scout/actions.tsv'), run_ts)
    bad = noeff = new = changed = 0
    for i in sorted(set(before) | set(after)):
        b, x = before.get(i), after.get(i)
        if b and x:
            diff = [f for f in FIELDS if str(b.get(f)) != str(x.get(f))]
        elif b and not x:
            if start and str(b.get('created_at', ''))[:10] < start:
                continue                       # 滑出日期窗口,不是改动
            diff = ['消失(被隐藏或撤)']
        else:
            diff = ['新增']
        if i in led:
            if not diff and set(led[i]) & {'update', 'cull', 'publish', 'restore', 'merge'}:
                noeff += 1
                print(f'⚠️ 台账无效果\t{i}\t台账记了 {"/".join(led[i])},线上标题/状态/关键词都没变(没执行成功,或被覆盖回去)')
            if diff:
                changed += 1
            continue
        if not diff:
            continue
        changed += 1
        if diff == ['新增']:
            new += 1
            print(f'ℹ️ 新增未记\t{i}\t{x.get("created_at")}\tstatus={x.get("status")}\t{x.get("title")}\t(系统建题或越权建题,人看)')
            continue
        bad += 1
        det = '；'.join(f'{f}: {b.get(f)!s} → {x.get(f)!s}' if x else f for f in diff)
        print(f'🚨 台账外改动\t{i}\t{det}\t(本轮台账没有这道题的写操作)')
    print(f'WRITE-AUDIT: 台账写题={len(led)} 线上有变化={changed} 台账外改动={bad} 台账无效果={noeff} 新增未记={new}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
