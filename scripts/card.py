#!/usr/bin/env python3
"""card.py — 判据卡:在做判断的那一步把相关闸的判据打印出来(v3.7.33 试跑,2026-11-10 用户「先拿5道闸试一周」)。

为什么要有:判例库 gates.md 只有我主动查才看得到,26 天真实查询约每轮 2 次,40 道闸 18 道零查询;
  近两周判断错误里「时效口径」最多(12 次),管它的两道闸却只查过 9 次。卡片把判据推到决策点,不靠我想起来查。
卡片正文在规则仓库 references/cards.md(单一事实源,本脚本只按 `## 卡:名` 分节打印)。

用法:
  card.py show <卡名>...             打印卡片(不去重)
  card.py list                       列出卡名与字节数
  card.py usage [天数]                打印次数统计
  card.py trial                      试跑结算(逐条判):上线前后各 7 天的判断类错误逐条列出,带卡片证据与判定,给出结论
  card.py judge <错误id> <类别> <卡名|-> "<理由>"   判一条错误:卡打了照犯/该打没打/管不到(写 card-trial-judged.tsv)
  python 内:import card; card.emit(card.pick(...), trigger='create')  按情形挑卡并打印,同一张卡 60 分钟内只打一次
注入(回归):CARDS(cards.md 路径) CARD_USAGE(打印记录) CARD_SEEN(去重状态) CARD_JUDGED(判定) CARD_NOW_MS CARD_QUIET=1(只记不打)
  ERRORS CHECK_HITS ACTIONS CHECKLOG(结算读的台账)。
文件或卡不存在时一律静默(沙箱/旧版规则包里没有 cards.md 也不能影响写题)。
"""
import json, os, re, sys, time

D = os.path.dirname(os.path.abspath(__file__))
CARDS = os.environ.get('CARDS') or os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic/references/cards.md')
USAGE = os.environ.get('CARD_USAGE') or os.path.join(D, 'card-usage.tsv')
SEEN = os.environ.get('CARD_SEEN') or os.path.join(D, 'card-seen.json')
DEDUP_MS = 60 * 60 * 1000

TIME_WORDS = re.compile(r'明日|明天|今日|今天|今晚|昨日|昨天|本周|下周|上周|将于|即将|周[一二三四五六日末]')
PRICE = re.compile(r'\d+(\.\d+)?%|涨停|跌停|收涨|收跌|盘前|盘中|盘后|夜盘|报\s*\d|涨|跌')


def _now():
    return int(os.environ.get('CARD_NOW_MS') or time.time() * 1000)


def load(path=None):
    try:
        txt = open(path or CARDS, encoding='utf-8').read()
    except OSError:
        return {}
    out, cur = {}, None
    for ln in txt.split('\n'):
        if ln.startswith('## 卡:'):
            cur = ln[len('## 卡:'):].strip(); out[cur] = []
        elif ln.startswith('## '):
            cur = None
        elif cur:
            out[cur].append(ln)
    return {k: '\n'.join(v).strip() for k, v in out.items()}


def pick(act, title=None, domain=None, closed_ms=None, age_h=None, new_title=False):
    """按情形挑卡。act: create|update|cull|restore|route。返回有序卡名列表。"""
    names = []
    titled = act == 'create' or (act in ('update', 'restore') and new_title)
    if titled:
        names += ['双要素', '归因']
        if act == 'create' or (title and TIME_WORDS.search(title)):
            names.append('时效')
        if domain == 'tradfi' and title and PRICE.search(title):
            names.append('时段')
    elif title and TIME_WORDS.search(title) and act in ('update', 'restore'):
        names.append('时效')
    now = _now()
    expired = (closed_ms is not None and 0 < closed_ms <= now) or (age_h is not None and age_h >= 24)
    if act in ('update', 'cull', 'restore', 'route') and expired:
        names.insert(0, '过期题')
    seen = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def _seen():
    try:
        return json.load(open(SEEN, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _clean(s):
    return str(s or '').replace('\t', ' ').replace('\n', ' ')


def _log(row):
    try:
        with open(USAGE, 'a', encoding='utf-8') as f:
            f.write('\t'.join(_clean(x) for x in row) + '\n')
    except OSError:
        pass


def link(tid, title):
    """建题成功后记一行「题号↔标题」:建题前打卡时题号还不存在,只能按标题记,结算时靠这行接上题号。"""
    _log([_now(), '-', 'create', '关联', f'{tid}|{title}'])


def emit(names, trigger='', force=False, out=None, ref=''):
    """打印卡片(60 分钟去重),记 card-usage.tsv(第 5 列＝触发它的题号或标题,多条用 ; 分隔)。
    ref 可以是字符串(所有卡同一个)或 {卡名: ref}。返回实际打印的卡名。"""
    cards = load()
    if not cards or not names:
        return []
    now, st, shown = _now(), _seen(), []
    out = out or sys.stdout
    for n in names:
        body = cards.get(n)
        if not body:
            continue
        dup = not force and now - int(st.get(n, 0)) < DEDUP_MS
        _log([now, n, trigger, '去重' if dup else '打印', ref.get(n, '') if isinstance(ref, dict) else ref])
        if dup:
            continue
        st[n] = now; shown.append(n)
        if not os.environ.get('CARD_QUIET'):
            print(f'📇 判据卡·{n}(判例: gate.sh {n})\n' + '\n'.join('   ' + l for l in body.split('\n')), file=out)
    if shown:
        try:
            json.dump(st, open(SEEN, 'w', encoding='utf-8'), ensure_ascii=False)
        except OSError:
            pass
    return shown


def usage(days=7):
    cut = _now() - days * 86400e3
    c = {}
    try:
        for ln in open(USAGE, encoding='utf-8'):
            x = ln.rstrip('\n').split('\t')
            if len(x) >= 4 and x[0].isdigit() and int(x[0]) >= cut:
                k = (x[1], x[3]); c[k] = c.get(k, 0) + 1
    except OSError:
        pass
    names = list(load()) or sorted({k[0] for k in c})
    print(f'近 {days:g} 天判据卡:')
    for n in names:
        print(f'  {n:<6} 打印 {c.get((n, "打印"), 0):3d}  去重跳过 {c.get((n, "去重"), 0):3d}')


TRIAL_START = 1794293668000          # 2026-11-10 14:54 CST 换上线,用户「先拿5道闸试一周」
TRIAL_DAYS = 7
# 逐条判口径(11-10 用户「按逐条判的口径来」):判断类错误＝errors.tsv 第 3 列前缀是 自审发现/纠错/复审挑战 的行
#   (不含 工具拦截/漏建/下游错标——那些是工具层或对账层的事)。每条由我判成三类之一,写进 card-trial-judged.tsv:
JUDGE_CLASSES = ('卡打了照犯', '该打没打', '管不到')
JUDGE_PREFIX = ('自审发现', '纠错', '复审挑战')
HIT_CHECKS = ('tradfi_floor', 'price_only', 'close_too_early', 'succession_price_leg', 'out_of_scope', 'cross_day_dup')
JUDGED = os.environ.get('CARD_JUDGED') or os.path.join(D, 'card-trial-judged.tsv')
# 判定线(能管的＝卡打了照犯＋该打没打;基线逐条判得 3 条):≤1 通过 / 2~3 持平 / >3 失败;另两条底线:拦截不升、耗时中位涨幅 ≤10%
PASS_MAX, FLAT_MAX, TIME_UP = 1, 3, 0.10


def _tsv(env, name):
    try:
        p = os.environ.get(env) or os.path.join(D, name)
        return [l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8') if l[:1].isdigit()]
    except OSError:
        return []


def judged():
    """{错误 id: (类别, 卡名, 理由)};同一 id 判多次以最后一次为准。"""
    out = {}
    try:
        for ln in open(JUDGED, encoding='utf-8'):
            x = ln.rstrip('\n').split('\t')
            if len(x) >= 5 and x[0].isdigit():
                out[x[1]] = (x[2], x[3], x[4])
    except OSError:
        pass
    return out


def judge(eid, cls, card, why):
    if cls not in JUDGE_CLASSES:
        return f'类别只能是 {"/".join(JUDGE_CLASSES)},收到「{cls}」'
    if cls != '管不到' and card not in load():
        return f'「{cls}」必须写是哪张卡(卡名:{"/".join(load())}),收到「{card}」'
    if not why.strip():
        return '要写一句理由'
    ids = {x[1] for x in _tsv('ERRORS', 'errors.tsv') if len(x) > 2}
    if eid not in ids:
        return f'errors.tsv 里没有错误 id {eid}(看 card.py trial 列出的 id)'
    try:
        with open(JUDGED, 'a', encoding='utf-8') as f:
            f.write('\t'.join([str(_now()), eid, cls, card if cls != '管不到' else '-', _clean(why)]) + '\n')
    except OSError as e:
        return f'写不了 {JUDGED}:{e}'
    return None


def evidence(tid, before_ms, rows=None):
    """这道题在 before_ms 之前出现过哪些卡:按第 5 列的题号,或经「关联」行接上的标题。返回 [(卡名, 打印/去重, ts)]。"""
    rows = rows if rows is not None else _tsv('CARD_USAGE', 'card-usage.tsv')
    titles = {r[4].split('|', 1)[1] for r in rows if len(r) > 4 and r[3] == '关联' and r[4].split('|', 1)[0] == str(tid)}
    keys = {str(tid)} | titles
    out = []
    for r in rows:
        if len(r) > 4 and r[3] in ('打印', '去重') and int(r[0]) <= before_ms and keys & set(r[4].split(';')):
            out.append((r[1], r[3], int(r[0])))
    return out


def _errs(a, b):
    return [x for x in _tsv('ERRORS', 'errors.tsv') if len(x) > 3 and a <= int(x[0]) < b and x[2].split('·')[0] in JUDGE_PREFIX]


def _ops(a, b, now):
    import statistics
    hits = _tsv('CHECK_HITS', 'check-hits.tsv'); acts = sorted(int(x[0]) for x in _tsv('ACTIONS', 'actions.tsv'))
    try:
        p = os.environ.get('CHECKLOG') or os.path.join(D, 'checklists.log.tsv')
        starts = [int(m.group(1)) for l in open(p, encoding='utf-8') if (m := re.match(r'# mode=\S+ ts=(\d+)', l))]
    except OSError:
        starts = []
    h = sum(1 for x in hits if len(x) > 3 and a <= int(x[0]) < b and x[1] in HIT_CHECKS and not x[3].startswith('预检'))
    durs = []
    for i, s in enumerate(starts):
        if a <= s < b:
            nxt = starts[i + 1] if i + 1 < len(starts) else now
            inr = [t for t in acts if s <= t < min(nxt, s + 90 * 60e3)]
            if inr:
                durs.append((inr[-1] - s) / 60e3)
    return h, len(durs), (statistics.median(durs) if durs else None)


def trial(start=TRIAL_START, days=TRIAL_DAYS, now=None):
    """试跑结算(逐条判):上线前后各 N 天的判断类错误逐条列出,带「这道题之前出现过哪些卡」的证据和我的判定;
    再算能管的条数、拦截数、轮耗时,给出 通过/持平/失败/待判。返回 (文字行, 结论)。"""
    now = now or _now(); span = days * 86400e3; J = judged(); usage_rows = _tsv('CARD_USAGE', 'card-usage.tsv')
    lines, stat = [], {}
    for a, b, lab in ((start - span, start, '上线前'), (start, min(start + span, now), '上线后')):
        es = _errs(a, b); h, nr, med = _ops(a, b, now)
        cnt = {c: 0 for c in JUDGE_CLASSES}; pend = 0
        lines.append(f'── {lab}({time.strftime("%m-%d %H:%M", time.localtime(a / 1000))}～{time.strftime("%m-%d %H:%M", time.localtime(b / 1000))}):判断类错误 {len(es)} 条')
        for x in es:
            j = J.get(x[1]); ev = evidence(x[3], int(x[0]), usage_rows) if lab == '上线后' else []
            evs = '、'.join(sorted({f'{n}({s})' for n, s, _ in ev})) or ('没出现过卡' if lab == '上线后' else '(上线前无卡)')
            if j:
                cnt[j[0]] += 1
            else:
                pend += 1
            tag = f'{j[0]}' + (f'·{j[1]}' if j and j[1] != '-' else '') if j else '待判'
            lines.append(f'  [{tag}] {x[1]} {time.strftime("%m-%d %H:%M", time.localtime(int(x[0]) / 1000))} {x[2]} {x[3]}｜卡:{evs}｜{(x[4] if len(x) > 4 else "")[:60]}'
                         + (f'｜判:{j[2][:50]}' if j else ''))
        can = cnt['卡打了照犯'] + cnt['该打没打']
        stat[lab] = dict(can=can, pend=pend, hits=h, med=med, **cnt)
        lines.append(f'  小计:能管 {can}(卡打了照犯 {cnt["卡打了照犯"]}／该打没打 {cnt["该打没打"]})｜管不到 {cnt["管不到"]}｜待判 {pend}'
                     f'｜相关工具拦截 {h}｜轮数 {nr}｜耗时中位 {"%.1f" % med if med is not None else "-"} 分钟')
    pre, post = stat['上线前'], stat['上线后']
    if pre['pend'] or post['pend']:
        verdict = f'待判:还有 {pre["pend"] + post["pend"]} 条没判(card.py judge <错误id> <类别> <卡名|-> "<理由>")'
    elif now < start + span:
        verdict = f'未到期:试跑到 {time.strftime("%m-%d %H:%M", time.localtime((start + span) / 1000))},现在的数只作中途参考'
    else:
        slow = pre['med'] and post['med'] and post['med'] > pre['med'] * (1 + TIME_UP)
        if post['can'] > FLAT_MAX or slow:
            verdict = '失败' + (f':能管的错误 {post["can"]} 条 >{FLAT_MAX}' if post['can'] > FLAT_MAX else '') + (f':耗时中位涨超 {TIME_UP:.0%}' if slow else '')
        elif post['can'] <= PASS_MAX and post['hits'] <= pre['hits']:
            verdict = f'通过:能管的错误 {pre["can"]}→{post["can"]},拦截 {pre["hits"]}→{post["hits"]}'
        else:
            verdict = f'持平:能管的错误 {pre["can"]}→{post["can"]},拦截 {pre["hits"]}→{post["hits"]}——无害、效果未证,由用户定'
    lines.append(f'结论:{verdict}')
    return lines, verdict


def main(a):
    if not a:
        print(__doc__, file=sys.stderr); return 2
    if a[0] == 'list':
        for n, b in load().items():
            print(f'  {n:<6} {len(b.encode())} 字节')
        return 0
    if a[0] == 'show' and len(a) > 1:
        cards = load(); bad = [n for n in a[1:] if n not in cards]
        if bad:
            print(f'❌ 没有这张卡: {" ".join(bad)}(card.py list 查)', file=sys.stderr); return 1
        emit(a[1:], trigger='show', force=True); return 0
    if a[0] == 'usage':
        usage(float(a[1]) if len(a) > 1 else 7); return 0
    if a[0] == 'trial':
        print('判据卡试跑结算(逐条判):判断类错误＝errors.tsv 自审发现/纠错/复审挑战;能管＝卡打了照犯＋该打没打;'
              '拦截＝check-hits 六类不含预检;耗时＝开跑→本轮最后一笔台账')
        lines, _ = trial(); print('\n'.join(lines)); usage(TRIAL_DAYS); return 0
    if a[0] == 'judge':
        if len(a) != 5:
            print('用法: card.py judge <错误id> <卡打了照犯|该打没打|管不到> <卡名|-> "<理由>"', file=sys.stderr); return 2
        err = judge(a[1], a[2], a[3], a[4])
        if err:
            print('❌ ' + err, file=sys.stderr); return 1
        print(f'✔ 已判 {a[1]}:{a[2]}' + (f'·{a[3]}' if a[2] != '管不到' else '')); return 0
    if a[0] == 'route' and len(a) >= 3:
        # route.sh 调:status 0 ≤8h 复查数字→时段;>8h→过期题(含射程);status 1/2 ≤24h 质量复审→双要素/归因/时效;>24h→时效
        try:
            age = float(a[2])
        except ValueError:
            return 0
        s = a[1]
        names = (['时段'] if age <= 8 else ['过期题']) if s == '0' else \
                (['双要素', '归因', '时效'] if age <= 24 else ['时效']) if s in ('1', '2') else []
        emit(names, trigger=f'route:{s}'); return 0
    print(__doc__, file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
