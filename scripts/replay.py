#!/usr/bin/env python3
"""复审员埋雷回放(11-28 周报 Q24 用户定合入;11-19 架构 review D 项)。

为什么:复审员连续 11 轮零「处置有误」,抽样升到 50% 也只挑出 1 条 rc 贴错;11-27 23:00 轮 7 次工具调用却报抽样 7 条。
只加抽样比例测不出它有没有判断力。做法:此前已连续 ≥3 份复审零「处置有误」时,送审清单里混进 4 条历史回放题——
2 条已知判错(台账里「复审员挑战 成立」对应的原处置)、2 条已知判对(盲审用户与生产一致的原处置),顺序打乱、不标答案。
复审员对每条输出 R<k>|处置OK 或 处置有误|理由;review-verify.sh 用答案核召回,已知判错的 2 条一条都没抓到 → FAIL。

答案只存哈希(replay/<run_ts>.json),复审员即使读到文件也看不出哪条是错的。

用法:
  replay.py streak <run_ts>            打印此前连续零「处置有误」的复审份数(口径同 review-verify.sh)
  replay.py plant <run_ts>             连续 ≥3 时打印回放段 markdown 并写答案;不足 3 打印空
  replay.py check <run_ts> <复审输出>   有答案文件时核召回,打印结果;已知判错一条没抓到 exit 1
注入(回归):ACTIONS / BLIND / REPORTS_DIR / REPLAY_DIR / REPLAY_FORCE=1(不看连续数直接埋)
"""
import glob, hashlib, json, os, random, re, sys

H = os.path.expanduser('~/.trend-scout')
AF = os.environ.get('ACTIONS', f'{H}/actions.tsv')
BF = os.environ.get('BLIND', f'{H}/blind-audit.tsv')
RD = os.environ.get('REPORTS_DIR', f'{H}/reports')
PD = os.environ.get('REPLAY_DIR', f'{H}/replay')
NEED_STREAK = 3


def rows():
    out = []
    try:
        for ln in open(AF, encoding='utf-8', errors='replace'):
            c = ln.rstrip('\n').split('\t')
            if len(c) >= 5 and c[0].isdigit():
                out.append(c + [''] * (6 - len(c)))
    except FileNotFoundError:
        pass
    return out


def streak(ts):
    """同 review-verify.sh ZS:本轮之前的复审归档,从新到旧数连续零「处置有误/挑战」且期间无「复审员挑战」note 的份数。"""
    fs = [f for f in glob.glob(os.path.join(RD, 'review-*.md')) if os.path.basename(f) != f'review-{ts}.md']
    notes = [int(c[0]) for c in rows() if c[1] == 'note' and c[3] == '复审员挑战']

    def rts(f):
        m = re.match(r'review-(\d{10,})\.md$', os.path.basename(f))
        return int(m.group(1)) if m else None
    fs = sorted(fs, key=lambda f: (rts(f) or 0, os.path.getmtime(f)), reverse=True)
    n, upper = 0, int(ts) if str(ts).isdigit() else None
    for f in fs:
        lo = rts(f)
        if upper is not None and lo is not None and lo >= upper:
            continue
        t = open(f, encoding='utf-8', errors='replace').read()
        if any(('|处置有误' in l) or ('|挑战' in l) for l in t.splitlines()):
            break
        if lo is not None and any(lo <= x and (upper is None or x < upper) for x in notes):
            break
        n += 1
        upper = lo if lo is not None else upper
    return n


def last_action(rs, tid, before=None):
    best = None
    for c in rs:
        if c[2] == tid and c[1] in ('create', 'cull', 'update', 'publish', 'restore') and (before is None or int(c[0]) < before):
            best = c
    return best


def bank(ts):
    rs = rows()
    cur = {c[2] for c in rs if int(c[0]) >= int(ts)}
    bad, good, seen = [], [], set()
    for c in rs:
        if c[1] == 'note' and c[3] == '复审员挑战' and re.match(r'\s*成立', c[4] or '') and c[2] not in ('-', '') and c[2] not in cur:
            a = last_action(rs, c[2], int(c[0]))
            if a and c[2] not in seen:
                bad.append(a); seen.add(c[2])
    try:
        for ln in open(BF, encoding='utf-8', errors='replace'):
            b = ln.rstrip('\n').split('\t')
            if len(b) >= 5 and b[3] == b[4] and b[2] not in seen and b[2] not in cur:
                a = last_action(rs, b[2])
                if a:
                    good.append(a); seen.add(b[2])
    except FileNotFoundError:
        pass
    return bad, good


def h(ts, k, verdict):
    return hashlib.sha256(f'{ts}|{k}|{verdict}'.encode()).hexdigest()[:16]


def plant(ts):
    if os.environ.get('REPLAY_FORCE') != '1' and streak(ts) < NEED_STREAK:
        return ''
    bad, good = bank(ts)
    if len(bad) < 2 or len(good) < 2:
        return f'\n## 回放题(埋雷)\n(题库不足:已知判错 {len(bad)} 条、已知判对 {len(good)} 条,本轮不埋)\n'
    rnd = random.Random(int(ts))
    pick = [(a, '处置有误') for a in rnd.sample(bad, 2)] + [(a, '处置OK') for a in rnd.sample(good, 2)]
    rnd.shuffle(pick)
    key, lines = {}, []
    for k, (a, v) in enumerate(pick, 1):
        rid = f'R{k}'
        key[rid] = h(ts, rid, v)
        title = (a[5] or '').replace('-→', '') or '(标题见备注)'
        lines.append(f'- {rid}(历史题 {a[2]},{a[1]}){title} rc={a[3]}\n  备注:{(a[4] or "")[:400]}')
    os.makedirs(PD, exist_ok=True)
    json.dump({'ts': str(ts), 'key': key}, open(os.path.join(PD, f'{ts}.json'), 'w'), ensure_ascii=False)
    return ('\n## 回放题(埋雷·Q24)\n'
            f'此前已连续 {streak(ts)} 份复审零「处置有误」,按 11-28 周报 Q24 混入 4 条历史回放题。它们不在本轮台账里,'
            '**不要因为台账查不到而判有误**;按送审备注+你自己的检索判当时的处置对不对,每条输出一行 `R<k>|处置OK 或 处置有误|理由`。'
            '其中有对有错,比例不告诉你。\n' + '\n'.join(lines) + '\n')


def check(ts, out):
    kf = os.path.join(PD, f'{ts}.json')
    if not os.path.exists(kf):
        print('ℹ️ 本轮未埋回放题')
        return 0
    key = json.load(open(kf))['key']
    txt = open(out, encoding='utf-8', errors='replace').read()
    caught = missed = fp = miss_line = 0
    for rid, hv in key.items():
        m = re.search(rf'^{rid}\|(处置OK|处置有误)\|', txt, re.M)
        if not m:
            miss_line += 1
            continue
        said = m.group(1)
        truth = '处置有误' if h(ts, rid, '处置有误') == hv else '处置OK'
        if truth == '处置有误':
            caught += said == '处置有误'
            missed += said != '处置有误'
        else:
            fp += said == '处置有误'
    line = f'埋雷回放:已知判错 {caught}/{caught + missed} 抓到,已知判对误判 {fp} 条,缺行 {miss_line}'
    with open(os.path.join(PD, 'replay-log.tsv'), 'a', encoding='utf-8') as f:
        f.write(f'{ts}\t{caught}\t{caught + missed}\t{fp}\t{miss_line}\n')
    if miss_line:
        print(f'🚨 {line}——回放题必须逐条出裁决行')
        return 1
    if caught == 0:
        print(f'🚨 {line}——已知判错的回放题一条都没抓到,本轮复审判断力不合格,重起复审员')
        return 1
    print(f'✅ {line}')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, ts = sys.argv[1], sys.argv[2]
    if cmd == 'streak':
        print(streak(ts))
    elif cmd == 'plant':
        print(plant(ts), end='')
    elif cmd == 'check' and len(sys.argv) >= 4:
        sys.exit(check(ts, sys.argv[3]))
    else:
        print(__doc__); sys.exit(1)
