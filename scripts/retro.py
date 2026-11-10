#!/usr/bin/env python3
"""retro.py — 学习闭环:干一轮 → 记错 → 每晚复盘 → 修 → 次日开跑先读 → 每周验证有没有学会(v3.7.2,用户 10-15 定)。

为什么:错误原本散在 6 处(复审员挑战/自审发现/纠错-自纠/工具拦截/下游错标/漏建),只有单轮自审与周报,
没有「每天」这一层;复盘靠用户提醒才做(10-15 当天 8 个错里 4 个是用户推着修的),改完也不验证——
撤题 rc 记错 10-14(VCSEL)、10-15(硬件板块)连犯两天,没有任何环节看得见「这是重犯」。

授权(用户 10-15):每晚复盘里,脚本/测试用例/数据层的修复我可以直接改,前提是 run-tests 全过且补一条能拦住同类错的用例;
规则文字的改动只起草,用 ask.py 发群等用户批(默认不合入)。

用法:
  retro.py collect                 从 6 个来源抽错误,增量写 errors.tsv(去重,可反复跑)
  retro.py day [YYYY-MM-DD]        当日复盘:按错类分组 + 历史重犯次数 + 是否修过 + 修后是否又犯 → retro/<日期>.md
  retro.py fix <错类> <层:用例|脚本|规则|数据> "<修了什么/在哪>"   登记一次修复(fixes.tsv)
  retro.py tag <错误id> <错类>      人工改错类(启发式分错了时)
  retro.py brief                   次日首扫 §0 读:最近一份复盘的「今天注意」
  retro.py week [天数=7]           学习有效性:每个修过的错类,修复后又犯几次(周报 ⑨)
  retro.py prune [天数=30]         减法候选(v3.7.22,用户 11-03 定):零拦截/多靠豁免/反复拦下未修/越修越多,day 末尾也会打印
错类 = 来源·子类,如「复审挑战·撤因码」「复审挑战·数字」「工具拦截·涨跌幅不符」「漏建」「下游错标」。
注入(回归):ACTIONS REJ UNLOGGED DOWNSTREAM_LOG COVERAGE_LOG ERRORS FIXES RETRO_DIR CHECK_HITS GATE_USAGE GATES。
"""
import os, re, sys, time, json, hashlib, datetime, collections

D = os.path.expanduser('~/.trend-scout')
sys.path.insert(0, D)


def _kind(msg):
    """11-04 复盘:拦截消息直接截前 20 字当错类,带题号/引号内容/数字的同类拦截被拆成多类
    (「13827 10 分钟内…」「标题「24小时涨41%」与币安现读…」「tradfi 单名涨跌 4.8% < 5」)。去掉这些再截。"""
    k = msg.split(':')[0].split('：')[0]
    k = re.sub(r'^\d{4,}\s*', '', k)
    k = re.sub(r'「[^」]*」', '「…」', k)
    k = re.sub(r'[+-]?\d+(?:\.\d+)?', 'N', k)
    return k[:20] or '未知'


def _p(env, name):
    return os.environ.get(env) or os.path.join(D, name)


ERR = _p('ERRORS', 'errors.tsv')
FIX = _p('FIXES', 'fixes.tsv')
RD = _p('RETRO_DIR', 'retro')

# 子类启发式:按备注关键词归类(分错了用 tag 改)。顺序=优先级。
SUBCLASS = [
    ('撤因码', r'\brc\b|撤因|reason_code|分类|码不贴|应记 |应为'),
    ('价格腿', r'价格腿|价格反应|缺价格'),
    ('数字', r'舍入|四舍五入|计数|算错|算成|写成\d|数字不符|数字错'),   # 不认单独的「%」:几乎每条备注都带百分数
    ('归因', r'归因|借源|因果|原因|同句源'),
    ('时效口径', r'盘中|收盘|过期|窗口|时段|口径'),
    ('重复碎片', r'重复|碎片|同标的'),
    ('流程', r'先写|并行|同批|漏办|没跑|顺序|落账'),
]


def _fmt_day(ms):
    return time.strftime('%Y-%m-%d', time.localtime(int(ms) / 1000))


def _sub(text):
    for name, pat in SUBCLASS:
        if re.search(pat, text):
            return name
    return '其他'


def _tsv(path):
    if not os.path.exists(path):
        return []
    return [l.rstrip('\n').split('\t') for l in open(path, encoding='utf-8') if l[:1].isdigit()]


def _eid(*parts):
    return hashlib.sha1('|'.join(str(x) for x in parts).encode()).hexdigest()[:10]


def gather():
    """[(ts, eid, 错类, 题id, 摘要, 来源)]"""
    import ledger
    out = []
    for r in ledger.rows():
        ts, act, tid, rc, note = r[0], r[1], r[2], r[3], r[4]
        if rc == '复审员挑战' and re.search(r'成立', note) and not re.search(r'不成立', note):
            out.append((ts, _eid('rv', ts, tid), '复审挑战·' + _sub(note), tid, note[:160], '复审员'))
        elif rc == '自审发现' and not note.startswith('自审七查'):   # 10-15 retro:七查例行留痕不是错误,曾被误归「价格腿」
            out.append((ts, _eid('self', ts, tid), '自审发现·' + _sub(note), tid, note[:160], '自审'))
        elif act == 'update' and rc == '纠错-自纠':
            out.append((ts, _eid('fix', ts, tid), '纠错·' + _sub(note + r[5]), tid, (r[5] or note)[:160], '纠错-自纠'))
    for p in _tsv(_p('REJ', 'actions-rejected.tsv')):
        msg = p[1] if len(p) > 1 else ''
        kind = _kind(msg)
        out.append((int(p[0]), _eid('rej', p[0]), '工具拦截·' + kind, p[3] if len(p) > 3 else '', msg[:160], '工具拦截'))
    for p in _tsv(_p('UNLOGGED', 'actions-unlogged.tsv')):
        out.append((int(p[0]), _eid('unl', p[0]), '看板已写未落账', p[3] if len(p) > 3 else '', (p[1] if len(p) > 1 else '')[:160], '未落账'))
    _dl = _tsv(_p('DOWNSTREAM_LOG', 'downstream.log.tsv'))
    _fa = {}                                     # 11-10:登记过「误报更正」的题,更正之前的错标行是检测器判错,不算错误
    for p in _dl:
        if len(p) >= 4 and p[3] == '误报更正':
            _fa[p[2]] = max(_fa.get(p[2], 0), int(p[0]))
    for p in _dl:
        if len(p) >= 4 and p[3] in ('错标', '域不符') and int(p[0]) > _fa.get(p[2], 0):
            out.append((int(p[0]), _eid('ds', _fmt_day(p[0]), p[2], p[3]), '下游错标', p[2], (p[4] if len(p) > 4 else '')[:160], '下游回读'))
    # 漏建:同一天同一标的只要有一次对账报「漏」就算一次(最后补上了也算——对账抓到的是本该自己发现的漏)
    for p in _tsv(_p('COVERAGE_LOG', 'coverage.log.tsv')):
        if len(p) >= 5 and p[4] == '漏':
            out.append((int(p[0]), _eid('cov', _fmt_day(p[0]), p[2]), '漏建', p[2], f'{p[1]} {p[2]} {p[3]}%', '漏建对账'))
    return out


def load_errors():
    rows = _tsv(ERR)
    tags = {}
    errs = {}
    for r in rows:
        if len(r) >= 3 and r[1] == 'TAG':
            tags[r[2]] = r[3]
        elif len(r) >= 7:
            errs[r[1]] = dict(ts=int(r[0]), eid=r[1], cls=r[2], tid=r[3], text=r[4], src=r[5], day=r[6])
    for e, c in tags.items():
        if e in errs:
            errs[e]['cls'] = c
    # 10-17 复盘:对账报「漏」后同日同标的又出现 有题/弃建 = 当轮拦下(流程起作用了),不与真正流出的漏建混算重犯
    caught = set()
    for p in _tsv(_p('COVERAGE_LOG', 'coverage.log.tsv')):
        if len(p) >= 5 and p[4] in ('有题', '弃建'):
            caught.add((_fmt_day(p[0]), p[2], int(p[0])))
    for e in errs.values():
        if e['cls'] == '漏建' and any(d == e['day'] and tk == e['tid'] and ts > e['ts'] for d, tk, ts in caught):
            e['cls'] = '漏建·当轮拦下'
    return errs


def cmd_collect():
    have = load_errors()
    new = [g for g in gather() if g[1] not in have]
    new.sort()
    with open(ERR, 'a', encoding='utf-8') as f:
        for ts, eid, cls, tid, text, src in new:
            f.write('\t'.join([str(ts), eid, cls, str(tid), text.replace('\t', ' '), src, _fmt_day(ts)]) + '\n')
    print(f'ERRORS: 新增 {len(new)} 条,累计 {len(have) + len(new)} 条')
    return len(new)


def load_fixes():
    out = collections.defaultdict(list)
    for r in _tsv(FIX):
        if len(r) >= 4:
            out[r[1]].append(dict(ts=int(r[0]), layer=r[2], desc=r[3]))
    return out


def cmd_fix(a):
    if len(a) < 3 or a[1] not in ('用例', '脚本', '规则', '数据'):
        sys.exit('用法: retro.py fix <错类> <用例|脚本|规则|数据> "<修了什么/在哪>"')
    with open(FIX, 'a', encoding='utf-8') as f:
        f.write(f'{int(time.time() * 1000)}\t{a[0]}\t{a[1]}\t{a[2]}\n')
    print(f'✔ 已登记修复:{a[0]} → {a[1]}')


def cmd_tag(a):
    if len(a) < 2:
        sys.exit('用法: retro.py tag <错误id> <错类>')
    with open(ERR, 'a', encoding='utf-8') as f:
        f.write(f'{int(time.time() * 1000)}\tTAG\t{a[0]}\t{a[1]}\n')
    print(f'✔ {a[0]} 改归 {a[1]}')


def cmd_day(a):
    cmd_collect()
    day = a[0] if a else time.strftime('%Y-%m-%d')
    errs = load_errors()
    fixes = load_fixes()
    today = [e for e in errs.values() if e['day'] == day]
    by = collections.defaultdict(list)
    for e in today:
        by[e['cls']].append(e)
    L = [f'# 复盘 {day}', '', f'当日错误 {len(today)} 条,{len(by)} 类(来源:复审员挑战/自审发现/纠错-自纠/工具拦截/下游错标/漏建)。', '']
    watch = []
    for cls, es in sorted(by.items(), key=lambda kv: -len(kv[1])):
        hist = [e for e in errs.values() if e['cls'] == cls and e['day'] < day]
        fx = fixes.get(cls, [])
        last_fix = max((f['ts'] for f in fx), default=None)
        after = [e for e in es if last_fix and e['ts'] > last_fix]
        if cls == '漏建·当轮拦下':
            state = '🟢 对账当轮拦下并已补建/弃建(流程起效,不计流出)'
        elif after:
            state = f'🔴 修过({len(fx)}次)仍重犯——上次修法无效,换一层修(规则文字→脚本/用例)'
        elif fx and last_fix and all(e['ts'] <= last_fix for e in es):
            state = '🟢 当天已修'
        elif hist:
            state = f'🟠 重犯(此前 {len(hist)} 次,最早 {min(e["day"] for e in hist)}),未修'
        else:
            state = '🟡 首次出现,未修'
        L.append(f'## {cls} ×{len(es)}  {state}')
        for e in es[:6]:
            L.append(f'- {e["tid"] or "-"} [{e["src"]}] {e["text"][:120]}  `{e["eid"]}`')
        for f in fx[-2:]:
            L.append(f'  - 修复记录:{time.strftime("%m-%d %H:%M", time.localtime(f["ts"] / 1000))} [{f["layer"]}] {f["desc"][:100]}')
        L.append('')
        if not state.startswith('🟢'):
            watch.append(f'- **{cls}**({state.split("—")[0].strip()}):{es[0]["text"][:80]}')
    L.append('## 今天注意(次日首扫 §0 由 retro.py brief 读出)')
    L += watch or ['- 无未修错类']
    L += [''] + prune(errs=errs, fixes=fixes)
    L += ['', '## 修复动作(每晚复盘时填写)',
          '- 脚本/用例/数据层:直接改 → run-tests 全过 → 补一条能拦住同类错的用例 → `retro.py fix <错类> <层> "<说明>"`',
          '- 规则文字:起草补丁 → `ask.py open --q "合入规则补丁:…" --default "不合入" --deadline <次日 23:00>` → `ask.py post`',
          '- 判断类(没法机械化):写进「今天注意」,次日首扫照看']
    os.makedirs(RD, exist_ok=True)
    path = os.path.join(RD, f'{day}.md')
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print(f'\n→ {path}')


def check_inventory():
    """在册检查 = topic.py 里所有 check='…' 与撤题闸 + lint.py 会 FAIL 的标题闸。log-action 内部闸没有清单,只计拦截不判零拦截。"""
    here = os.path.dirname(os.path.abspath(__file__))
    names = set()
    try:
        src = open(os.path.join(here, 'topic.py'), encoding='utf-8').read()
        names |= set(re.findall(r"check='([^']+)'", src)) | set(re.findall(r"\('(\w+)', lambda", src))
        names |= set(re.findall(r"\('[^']+', '(\w+)'\)", src.split('WAIVERS = ', 1)[1].split('\n\n', 1)[0]))
    except (OSError, IndexError):
        pass
    try:
        names |= {'lint:' + g for g in re.findall(r"\('FAIL',\s*'([^']+)',", open(os.path.join(here, 'lint.py'), encoding='utf-8').read())}
    except OSError:
        pass
    names.discard('未命名')
    return names


def _gate_names():
    g = os.environ.get('GATES') or os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic/references/gates.md')
    if os.path.isdir(g):   # 同 gate.sh:GATES 在 run-tests 里是目录
        g = os.path.join(g, 'references', 'gates.md')
    try:
        return [l[len('## 闸:'):].strip() for l in open(g, encoding='utf-8') if l.startswith('## 闸:')]
    except OSError:
        return []


def prune(days=30, errs=None, fixes=None, now=None):
    """v3.7.22 减法出口(用户 11-03 定):每晚复盘原来只有「换一层修」一条路,只加不减——10-15→11-02 topic.py 471→836 行、
    回归 284→369 条,每日错误 10~29 条没有往下走,工具拦截占比反而上升。这里列出该复核要不要留的规则,四类:
    ① 零拦截:在册检查 / gates 闸记满 days 天仍为 0(不满不判,只报还差几天)——零拦截≠没用,可能是写法已被教会;
    ② 多靠豁免:拦+豁免 ≥3 次且豁免过半——口子比闸常用,口径可能定错了;
    ③ 反复拦下未修:工具拦截类近 days 天 ≥5 次、一次没修过——要么限制定错了,要么这一步该交给工具做;
    ④ 越修越多:修过 ≥3 次、最后一次修后仍重犯——停止再加一层,先审规则本身。
    只列不删:退役/放宽是规则改动,起草后走 ask.py 群批(默认不合入)。"""
    now = now or time.time()
    cut = (now - days * 86400) * 1000
    errs = load_errors() if errs is None else errs
    fixes = load_fixes() if fixes is None else fixes
    L = [f'## 减法候选(近 {days} 天;只列不删——退役/放宽起草后走 ask.py 群批,默认不合入)']
    out = []

    def _span(rows):
        ts = [int(r[0]) for r in rows if r and r[0].isdigit()]
        return (now * 1000 - min(ts)) / 86400e3 if ts else 0

    def _due(span):
        return time.strftime('%m-%d', time.localtime(now + (days - span) * 86400))

    hits = _tsv(_p('CHECK_HITS', 'check-hits.tsv'))
    inv = check_inventory()
    blk, wv = collections.Counter(), collections.Counter()
    for r in hits:
        if len(r) >= 3 and int(r[0]) >= cut:
            if r[2] == '拦':
                blk[r[1]] += 1
            elif r[2] == '豁免':
                wv[r[1]] += 1
    span = _span(hits)
    if span >= days:
        z = sorted(n for n in inv if not blk[n] and not wv[n])
        if z:
            out.append(f'- ① 零拦截检查 {len(z)}/{len(inv)}:{"、".join(z)}')
    else:
        L.append(f'- ① 检查计数第 {span:.0f} 天,满 {days} 天(约 {_due(span)})起列零拦截;在册 {len(inv)} 个')
    usage = _tsv(_p('GATE_USAGE', 'gate-usage.tsv'))
    gq = collections.Counter(r[2] for r in usage if len(r) >= 3 and r[1] == 'gate' and int(r[0]) >= cut)
    gs, gn = _span(usage), _gate_names()
    if gs >= days:
        z = [g for g in gn if not gq[g]]
        if z:
            out.append(f'- ① 零查询闸(gates.md){len(z)}/{len(gn)}:{"、".join(z)}——脚本强制的闸不经 gate.sh,零查询只是「该复核」信号')
    elif gn:
        L.append(f'- ① gates 查询计数第 {gs:.0f} 天,满 {days} 天(约 {_due(gs)})起列零查询闸;在册 {len(gn)} 个')
    for n in sorted(wv, key=lambda n: -wv[n]):
        if blk[n] + wv[n] >= 3 and wv[n] * 2 > blk[n] + wv[n]:
            out.append(f'- ② {n}:拦 {blk[n]} 次、靠豁免过 {wv[n]} 次——口子比闸常用,收窄触发条件、放宽或删')
    win = [e for e in errs.values() if e['ts'] >= cut]
    by = collections.Counter(e['cls'] for e in win)
    for cls, k in by.most_common():
        if cls.startswith('工具拦截') and k >= 5 and not fixes.get(cls):
            out.append(f'- ③ {cls}:近 {days} 天拦 {k} 次、一次没修——要么限制定错了(放宽/删),要么这一步交给工具做')
    for cls, fx in fixes.items():
        if cls == '漏建·当轮拦下':   # 11-07 复盘:🟢 类=对账当轮捞出并补建,出现越多说明闸越起效,不是「越修越多」
            continue
        last = max(f['ts'] for f in fx)
        again = [e for e in errs.values() if e['cls'] == cls and e['ts'] > last]
        if len(fx) >= 3 and again:
            out.append(f'- ④ {cls}:修了 {len(fx)} 次、最后一次修后又犯 {len(again)} 次——停止再加一层,先审规则本身(口径对不对、该不该合并/删)')
    return L + (out or ['- 本晚无达标候选'])


def cmd_prune(a):
    print('\n'.join(prune(int(a[0]) if a else 30)))


def cmd_brief():
    if not os.path.isdir(RD):
        print('RETRO: 还没有复盘记录')
        return
    fs = sorted(f for f in os.listdir(RD) if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.md', f))
    if not fs:
        print('RETRO: 还没有复盘记录')
        return
    txt = open(os.path.join(RD, fs[-1]), encoding='utf-8').read()
    m = re.search(r'## 今天注意[^\n]*\n(.*?)(\n## |\Z)', txt, re.S)
    print(f'📓 最近复盘 {fs[-1][:-3]} 的「今天注意」:')
    print((m.group(1).strip() if m else '- (无)'))


def week(days=7):
    cmd_collect() if os.environ.get('RETRO_COLLECT', '1') == '1' else None
    errs = load_errors()
    fixes = load_fixes()
    cut = int((time.time() - days * 86400) * 1000)
    wk = [e for e in errs.values() if e['ts'] >= cut]
    rows = []
    for cls, fx in fixes.items():
        first = min(f['ts'] for f in fx)
        after = [e for e in errs.values() if e['cls'] == cls and e['ts'] > max(f['ts'] for f in fx)]
        rows.append((cls, len(fx), len(after), fx[-1]['layer']))
    return len(wk), len({e['cls'] for e in wk}), rows


def cmd_week(a):
    n, c, rows = week(int(a[0]) if a else 7)
    print(f'近期错误 {n} 条 / {c} 类;修过的错类 {len(rows)} 个:')
    for cls, nf, na, layer in sorted(rows, key=lambda r: -r[2]):
        print(f"  {'🔴' if na else '🟢'} {cls}:修 {nf} 次(最近一次在{layer}层),修后又犯 {na} 次")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    c, rest = a[0], a[1:]
    cmds = {'collect': lambda r: cmd_collect(), 'day': cmd_day, 'fix': cmd_fix, 'tag': cmd_tag,
            'brief': lambda r: cmd_brief(), 'week': cmd_week, 'prune': cmd_prune}
    if c not in cmds:
        print(__doc__)
        sys.exit(2)
    cmds[c](rest)


if __name__ == '__main__':
    main()
