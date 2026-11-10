#!/usr/bin/env python3
"""blind-audit.py — 每周盲审(v3.7.1,用户 10-15 同意「每周 10 分钟盲审 20 题」)。资格线第①条的唯一数据源。

为什么:唯一一次拿你的口径量生产质量是 09-30 盲审 264 题——生产「留」约一半与你不符,而模型与生产一致 98%:
内部自查可以自洽 98% 同时一半是错的。托管后你不在会话里,只能每周抽样把这条「外部真值」续上。

流程(全在群里异步完成):
  sample  从近 7 天看板题里抽 20 道(终态留 10 / 撤 10,不足就有多少抽多少),只留题面,存 blind/<周>.json
  post    发群:编号+域+题面(不给终态);你回「盲审 <周> 撤 3,7,12」(没列的都算留),全留回「盲审 <周> 全留」
  sync    §0 开跑调:读群主回复 → 逐题与生产终态比对,写 blind-audit.tsv(ts 批 id 你 生产 一致),
          不一致的写 blind-disagree.tsv(周报规则梳理的输入,也是回归用例候选);打印一致率
  record <周> "<撤 3,7,12>"   不走群、手动录入同一格式
注入(回归):BLIND_DIR BLIND_AUDIT BLIND_B0(样本池 json,跳过联网拉取) ASK_FAKE_MSGS ASK_NO_SEND。
"""
import json, os, random, re, subprocess, sys, time, datetime

D = os.path.expanduser('~/.trend-scout')
sys.path.insert(0, D)
BD = os.environ.get('BLIND_DIR') or os.path.join(D, 'blind')
OUT = os.environ.get('BLIND_AUDIT') or os.path.join(D, 'blind-audit.tsv')
DIS = os.environ.get('BLIND_DISAGREE') or os.path.join(D, 'blind-disagree.tsv')
ACT = os.environ.get('BLIND_ACTIONS') or os.path.join(D, 'actions.tsv')

# v3.7.18(10-26 用户定「按你的建议调整出题」):W42/W43 的 8 道不一致里,2 道是系统/团队后台隐藏的(不是我的判断),
#   4 道是因重复/反转撤的(盲审只看题面,看不到同日重复与之后的价格)。出题时:① 撤题只抽我落过 cull 账的;
#   ② 重复/反转撤的题附一行背景,让盲审判的是「这条该不该在前台」,而不是「题面单看像不像好题」。
CONTEXT = {'重复': '附:同期已有同标的同切面的题,本条与之重复', '反转错向': '附:之后实测方向已与标题相反'}


def my_culls():
    out = {}
    try:
        for ln in open(ACT, encoding='utf-8'):
            c = ln.rstrip('\n').split('\t')
            if len(c) >= 4 and c[1] == 'cull' and c[2] not in ('-', ''):
                out[c[2]] = c[3]
    except FileNotFoundError:
        pass
    return out


def context_of(rc):
    for k, v in CONTEXT.items():
        if (rc or '').startswith(k):
            return v
    return ''


def week_id(now=None):
    y, w, _ = (now or datetime.date.today()).isocalendar()
    return f'{y}-W{w:02d}'


def pool():
    p = os.environ.get('BLIND_B0')
    if not p:
        today = datetime.date.today()
        p = os.path.join(BD, '_pool.json')
        os.makedirs(BD, exist_ok=True)
        r = subprocess.run([sys.executable, os.path.join(D, 'b0-fetch.py'), (today - datetime.timedelta(days=7)).isoformat(),
                            today.isoformat(), '--out', p], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit('🚨 拉 7 天看板失败: ' + (r.stdout + r.stderr)[-200:])
    d = json.load(open(p, encoding='utf-8'))
    return d if isinstance(d, list) else d.get('topics') or []


def cmd_sample(a):
    n = int(a[a.index('--n') + 1]) if '--n' in a else 20
    wk = a[a.index('--week') + 1] if '--week' in a else week_id()
    path = os.path.join(BD, f'{wk}.json')
    if os.path.exists(path) and '--force' not in a:
        sys.exit(f'{wk} 已抽过({path});重抽加 --force')
    tp = [t for t in pool() if t.get('status') in (0, 3)]
    rnd = random.Random(wk)
    keep = [t for t in tp if t['status'] == 0]
    mc = my_culls()
    cull = [t for t in tp if t['status'] == 3 and str(t['id']) in mc]   # v3.7.18 只抽我撤的,后台隐藏的不算我的判断
    rnd.shuffle(keep)
    rnd.shuffle(cull)
    half = n // 2
    pick = keep[:half] + cull[:n - min(half, len(keep))]
    pick = pick[:n]
    rnd.shuffle(pick)
    items = [{'n': i + 1, 'id': str(t['id']), 'domain': t.get('domain'), 'title': t.get('original_title') or t.get('title'),
              'keywords': t.get('keywords'), 'created_at': t.get('created_at'), 'prod': '留' if t['status'] == 0 else '撤',
              'context': context_of(mc.get(str(t['id']))) if t['status'] == 3 else ''}
             for i, t in enumerate(pick)]
    os.makedirs(BD, exist_ok=True)
    json.dump({'week': wk, 'sampled_at': int(time.time() * 1000), 'items': items}, open(path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'✔ {wk} 抽 {len(items)} 题(留 {sum(1 for x in items if x["prod"] == "留")} / 撤 {sum(1 for x in items if x["prod"] == "撤")}) → {path}')


def _load(wk):
    path = os.path.join(BD, f'{wk}.json')
    if not os.path.exists(path):
        sys.exit(f'没有 {wk} 的样本,先 sample')
    return json.load(open(path, encoding='utf-8'))


def cmd_post(a):
    wk = a[0] if a and not a[0].startswith('--') else week_id()
    b = _load(wk)
    L = [f'🔍 **本周盲审 {wk}**（{len(b["items"])} 题，只看题面判「留」还是「撤」，约 10 分钟）',
         f'回复：**盲审 {wk} 撤 3,7,12**（没列的都算留）；全留回 **盲审 {wk} 全留**。结果进周报「资格线·盲审一致率」。']
    for x in b['items']:
        L.append(f"{x['n']}. [{'币' if x['domain'] == 'crypto' else '美股/宏观'}] {x['title']}"
                 + (f"（{x['context']}）" if x.get('context') else ''))
    msg = '\n'.join(L)
    if '--dry' in a or os.environ.get('ASK_NO_SEND'):
        print(msg)
        return
    import ask
    Lk = ask._lark()
    cfg = Lk.cfg_load()
    if not cfg.get('enabled') or not cfg.get('chat_id'):
        sys.exit('Lark 未启用')
    rc, data, err = Lk._cli(['im', '+messages-send', '--as', 'bot', '--chat-id', cfg['chat_id'], '--markdown', msg,
                             '--idempotency-key', f'blind-{wk}', '--json'])
    print(('✔ 已发群 ' + str(Lk._msg_id(data))) if rc == 0 and Lk._msg_id(data) else ('🚨 发群失败:' + str(err)[:200]))


REPLY = re.compile(r'盲审\s*(\d{4}-W\d{2})\s*(全留|撤\s*([\d,，、\s]+))')


def _done():
    s = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            x = l.split('\t')
            if len(x) > 2:
                s.add(x[1])
    return s


def record(wk, spec, src='手动'):
    if wk in _done():
        print(f'ℹ️ {wk} 已录过,忽略重复回复')
        return
    b = _load(wk)
    m = re.match(r'\s*(全留|撤\s*([\d,，、\s]+))', spec)
    if not m:
        sys.exit('格式:「撤 3,7,12」或「全留」')
    culled = set() if m.group(1) == '全留' else {int(x) for x in re.findall(r'\d+', m.group(2))}
    now = int(time.time() * 1000)
    agree = 0
    with open(OUT, 'a', encoding='utf-8') as f, open(DIS, 'a', encoding='utf-8') as g:
        for x in b['items']:
            you = '撤' if x['n'] in culled else '留'
            ok = you == x['prod']
            agree += ok
            f.write(f"{now}\t{wk}\t{x['id']}\t{you}\t{x['prod']}\t{int(ok)}\n")
            if not ok:
                g.write(f"{now}\t{wk}\t{x['id']}\t你={you}\t生产={x['prod']}\t{x['domain']}\t{x['title']}\t{x.get('keywords') or ''}\n")
    n = len(b['items'])
    print(f'✔ 盲审 {wk}({src}):一致 {agree}/{n} = {agree / max(1, n):.0%};不一致 {n - agree} 题已写 blind-disagree.tsv')


def cmd_sync(a):
    import ask
    since = int(time.time() * 1000) - 8 * 86400 * 1000
    msgs, _ = ask._messages(since)
    hit = 0
    for ts, who, txt in msgs:
        for m in REPLY.finditer(txt):
            if who != '群主':
                print(f'ℹ️ {who} 回了盲审——非群主,只作参考')
                continue
            if not os.path.exists(os.path.join(BD, f'{m.group(1)}.json')):
                continue
            record(m.group(1), m.group(2), src=f'群 {ts}')
            hit += 1
    if not hit:
        print('BLIND: 无新盲审回复')


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('sample', 'post', 'sync', 'record'):
        print(__doc__)
        sys.exit(2)
    if a[0] == 'record':
        if len(a) < 3:
            sys.exit('用法: blind-audit.py record <周> "<撤 3,7,12|全留>"')
        record(a[1], a[2])
    else:
        {'sample': cmd_sample, 'post': cmd_post, 'sync': cmd_sync}[a[0]](a[1:])


if __name__ == '__main__':
    main()
