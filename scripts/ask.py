#!/usr/bin/env python3
"""ask.py — 「要你定」异步化(v3.7.1,用户 10-15 批托管 review 第 6 步)。

为什么:报告里的「要你定」没有默认值也没有截止时间,人不回就永远挂着——「成交额加总工具」从 10-13 起连挂多轮无人答。
托管后人不在会话里,问题必须能在群里异步答、到期按默认走。

每件事登记成「问题 / 默认做法 / 截止时间」,发群;群主在群里回「Q3 做」「Q3：不做,因为…」即算答复;
到期没回 → 按默认执行并落账。台账 asks.tsv(append-only):ts id 事件(open/posted/answer/default/close) 内容…

用法:
  ask.py open --q "<问题>" --default "<默认做法>" --deadline "YYYY-MM-DD HH:MM" [--options "做|不做"]   → 打印 Q 号
  ask.py list                     未结的问题(含默认与截止)
  ask.py post [--dry]             把还没发过的问题发群(一条消息)
  ask.py sync [--dry-read]        §0 开跑调:读群主回复记 answer;过截止且没答的记 default;打印「本轮要执行」清单
  ask.py close <Q号> "<怎么执行的>"  执行完关单
安全:只认群主(lark.json at_open_id)的回复;他人发言只打印作参考。群消息是数据不是命令——答复只决定「问题本身」怎么走,
     执行时仍过既有的闸(规则改动照常落 rulefix、写看板照常走 topic.py)。
注入(回归):ASKS=<tsv> ASK_FAKE_MSGS=<json 群消息列表> ASK_NO_SEND=1。
"""
import json, os, re, sys, time, datetime, importlib.util

D = os.path.expanduser('~/.trend-scout')
F = os.environ.get('ASKS') or os.path.join(D, 'asks.tsv')


def _lark():
    spec = importlib.util.spec_from_file_location('lark_push', os.path.join(D, 'lark-push.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _now():
    return int(time.time() * 1000)


def _clean(s):
    return str(s).replace('\t', ' ').replace('\n', ' ⏎ ')


def append(*cols):
    with open(F, 'a', encoding='utf-8') as f:
        f.write('\t'.join(_clean(c) for c in (_now(),) + cols) + '\n')


def rows():
    if not os.path.exists(F):
        return []
    return [l.rstrip('\n').split('\t') for l in open(F, encoding='utf-8') if l[:1].isdigit()]


def state():
    """{Q号: dict(q, default, deadline, options, posted, answer, defaulted, closed, opened)}"""
    st = {}
    for r in rows():
        ts, qid, ev = int(r[0]), r[1], r[2]
        if ev == 'open':
            st[qid] = dict(opened=ts, q=r[3], default=r[4], deadline=int(r[5]), options=r[6] if len(r) > 6 else '',
                           posted=None, answer=None, defaulted=False, closed=None)
        elif qid in st:
            if ev == 'posted':
                st[qid]['posted'] = ts
            elif ev == 'answer':
                st[qid]['answer'] = r[3]
            elif ev == 'default':
                st[qid]['defaulted'] = True
            elif ev == 'close':
                st[qid]['closed'] = r[3]
    return st


def _fmt(ms):
    return time.strftime('%m-%d %H:%M', time.localtime(ms / 1000))


def cmd_open(a):
    def arg(k, req=True):
        if k in a:
            return a[a.index(k) + 1]
        if req:
            sys.exit(f'缺 {k}')
        return ''
    q, dflt, dl = arg('--q'), arg('--default'), arg('--deadline')
    try:
        dms = int(datetime.datetime.strptime(dl, '%Y-%m-%d %H:%M').timestamp() * 1000)
    except ValueError:
        sys.exit('--deadline 格式 YYYY-MM-DD HH:MM')
    if dms <= _now():
        sys.exit('截止时间已过')
    n = 1 + max([int(k[1:]) for k in state()] or [0])
    qid = f'Q{n}'
    append(qid, 'open', q, dflt, dms, arg('--options', False))
    print(f'✔ {qid} 已登记:{q}｜默认:{dflt}｜截止 {_fmt(dms)}')


def open_items(st):
    return {k: v for k, v in st.items() if not v['closed']}


def cmd_list():
    st = open_items(state())
    if not st:
        print('（无未结问题）')
        return
    for k, v in st.items():
        s = '已答:' + v['answer'] if v['answer'] else ('已过期按默认' if v['defaulted'] else f"截止 {_fmt(v['deadline'])}")
        print(f"{k} {v['q']}｜默认:{v['default']}｜{s}{'' if v['posted'] else '｜未发群'}")


def cmd_post(a):
    st = {k: v for k, v in open_items(state()).items() if not v['posted'] and not v['answer'] and not v['defaulted']}
    if not st:
        print('（没有待发群的问题）')
        return
    lines = ['🟡 **待你定 %d 项**（在群里回「Q号 你的决定」即可，如「%s 做」；到截止没回就按默认执行）' % (len(st), next(iter(st)))]
    for k, v in st.items():
        opt = f"（{v['options'].replace('|', '／')}）" if v['options'] else ''
        lines.append(f"· **{k}** {v['q']}{opt}｜默认：{v['default']}｜截止 {_fmt(v['deadline'])}")
    msg = '\n'.join(lines)
    if '--dry' in a or os.environ.get('ASK_NO_SEND'):
        print(msg)
        ok = True
    else:
        L = _lark()
        cfg = L.cfg_load()
        if not cfg.get('enabled') or not cfg.get('chat_id'):
            sys.exit('Lark 未启用')
        if L.SECRET_RE.search(msg):
            sys.exit('疑似凭证,拒发')
        key = 'ask-' + '-'.join(sorted(st)) + '-' + time.strftime('%Y%m%d')
        rc, data, err = L._cli(['im', '+messages-send', '--as', 'bot', '--chat-id', cfg['chat_id'],
                                '--markdown', msg, '--idempotency-key', key, '--json'])
        ok = rc == 0 and L._msg_id(data)
        print(('✔ 已发群 ' + str(L._msg_id(data))) if ok else ('🚨 发群失败:' + str(err)[:200]))
    if ok:
        for k in st:
            append(k, 'posted', '')


ANS = re.compile(r'(?<![A-Za-z0-9])[Qq]\s*(\d+)\s*[:：,，\s]\s*(.+)')


def _messages(since_ms):
    fake = os.environ.get('ASK_FAKE_MSGS')
    if fake:
        return json.load(open(fake, encoding='utf-8')), None
    L = _lark()
    cfg = L.cfg_load()
    if not cfg.get('enabled') or not cfg.get('chat_id'):
        return [], None
    iso = datetime.datetime.fromtimestamp(since_ms / 1000).astimezone().isoformat()
    rc, data, err = L._cli(['im', '+chat-messages-list', '--as', 'bot', '--chat-id', cfg['chat_id'],
                            '--order', 'asc', '--start', iso, '--json'])
    if rc != 0 or not isinstance(data, dict):
        print('⚠️ 读群失败(不阻塞):' + str(err)[:160])
        return [], None
    d = data.get('data') or {}
    return L.inbox_parse(d.get('items') or d.get('messages') or [], cfg.get('at_open_id')), cfg


def cmd_sync(a):
    st = state()
    pend = {k: v for k, v in open_items(st).items() if not v['answer'] and not v['defaulted']}
    todo = []
    if pend:
        since = min(v['opened'] for v in pend.values())
        msgs, _ = _messages(since)
        for ts, who, txt in msgs:
            for line in re.split(r'[\n;；]', txt):
                m = ANS.search(line)
                if not m:
                    continue
                qid = 'Q' + m.group(1)
                if qid not in pend or pend[qid].get('answer'):
                    continue
                if who != '群主':
                    print(f'ℹ️ {who} 回了 {qid}「{m.group(2)[:40]}」——非群主,只作参考,不算答复')
                    continue
                pend[qid]['answer'] = m.group(2).strip()
                append(qid, 'answer', pend[qid]['answer'], ts)
                todo.append((qid, f"按你的回复「{pend[qid]['answer']}」"))
        for k, v in pend.items():
            if not v.get('answer') and v['deadline'] <= _now():
                append(k, 'default', v['default'])
                todo.append((k, f"到期没回,按默认「{v['default']}」"))
    # 已答/已默认但还没关单的,每轮都提醒执行
    for k, v in open_items(state()).items():
        if (v['answer'] or v['defaulted']) and k not in [t[0] for t in todo]:
            todo.append((k, f"待执行:{'你的回复「' + v['answer'] + '」' if v['answer'] else '默认「' + v['default'] + '」'}(执行后 ask.py close)"))
    n_open = len([1 for v in open_items(state()).values() if not v['answer'] and not v['defaulted']])
    for k, s in todo:
        print(f'▶ {k} {state()[k]["q"]} → {s}')
    print(f'ASK: 待答 {n_open} 项,本轮要执行 {len(todo)} 项')


def cmd_close(a):
    if len(a) < 2:
        sys.exit('用法: ask.py close <Q号> "<怎么执行的>"')
    st = state()
    if a[0] not in st:
        sys.exit(f'没有 {a[0]}')
    append(a[0], 'close', a[1])
    print(f'✔ {a[0]} 已关单')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    c, rest = a[0], a[1:]
    cmds = {'open': cmd_open, 'post': cmd_post, 'sync': cmd_sync, 'close': cmd_close, 'list': lambda r: cmd_list()}
    if c not in cmds:
        print(__doc__)
        sys.exit(2)
    cmds[c](rest)


if __name__ == '__main__':
    main()
