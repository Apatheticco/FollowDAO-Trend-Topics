#!/usr/bin/env python3
"""review-packet.py — 送审清单从台账渲染(v3.7.0),不再手写。

病例:10-15 首扫手写清单先写「撤 19 条/共 32 行」,实际 17/30;10-12、10-13 两轮漏写「留-撤对照」。
计数与分组是纯机械活,手写只会出错;只有「留-撤对照」是判断,必须由主进程给(--keep),本轮有撤题而没给就拒出清单。

用法:
  review-packet.py <run_ts> --keep "<id>|<标题>|<为什么留(对照哪条撤题)>" [--keep ...] [--out 文件]
  review-packet.py <run_ts> --keep-file <每行一条 id|标题|理由> [--out 文件]
  本轮无撤题时 --keep 可省。
内容:头部计数(建/上线/撤/改/恢复/note/总行数)→ 撤 → 留-撤对照 → 改 → 建 → 恢复 → note → 复审员输出格式。
每条带 id、标题、rc、台账备注原文(判据+实测+出处原句都在备注里,不另写摘要——复审员审的是台账不是我的转述)。
注入(回归):ACTIONS / B0JSON / CHECKLOG。
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger

D = os.path.expanduser('~/.trend-scout')
NOTE_MAX = 700


def upper_bound(run_ts):
    p = os.environ.get('CHECKLOG') or os.path.join(D, 'checklists.log.tsv')
    hi = None
    if os.path.exists(p):
        for l in open(p, encoding='utf-8'):
            m = re.search(r'ts=(\d{13})', l)
            if m and int(m.group(1)) > run_ts and (hi is None or int(m.group(1)) < hi):
                hi = int(m.group(1))
    return hi or 9999999999999


def b0_titles():
    p = os.environ.get('B0JSON') or os.path.join(D, 'b0-latest.json')
    try:
        d = json.load(open(p, encoding='utf-8'))
        return {str(t['id']): t.get('title', '') for t in (d if isinstance(d, list) else d.get('topics') or [])}
    except Exception:
        return {}


def rule_version():
    p = os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic/LESSONS.md')
    try:
        vs = re.findall(r'^\| v(\d+)\.(\d+)\.(\d+) ', open(p, encoding='utf-8').read(), re.M)
        return 'v%s.%s.%s' % max(vs, key=lambda x: tuple(map(int, x)))
    except Exception:
        return '?'


def clip(s, n=NOTE_MAX):
    return s if len(s) <= n else s[:n] + '…(截断,全文见台账)'


def title_drift(rs, tol=10.0):
    """11-01 retro:本轮建/改过标题的币题,送审前复读币安 24h;与标题差 ≥tol 个百分点(route.sh 改数字线)即列出。
    标的取标题里第一个全大写代码(台账不存关键词)。注入同 pct.bn_title_mismatch(PCT_BN_FAKE)。"""
    import pct
    last = {}
    for r in rs:
        if r[1] in ('create', 'update') and r[5] and r[5] != '-':
            last[r[2]] = r[5].split('→')[-1]
    out = []
    for tid, t in last.items():
        if not pct.BN_TITLE.search(t):
            continue
        m = re.search(r'(?<![A-Za-z])([A-Z][A-Z0-9]{1,14})(?![A-Za-z])', t)
        if not m:
            continue
        msg = pct.bn_title_mismatch(t, [m.group(1)], tol=tol)
        if msg:
            # 11-03 用户定(Q9):纯行情币题同方向且现读仍过 A 定则线(≥±50%,11-06 由30%上调)→偏差多大都不动;只拦跌破线或方向反转
            mx = re.search(r'币安现读 ([+-]?\d+(?:\.\d+)?)%', msg)
            mt = pct.BN_TITLE.search(t)
            if mx and mt and '币安合约成交' in t:
                x = float(mx.group(1))
                tv = float(mt.group(2)) * (1 if mt.group(1) == '涨' else -1)
                if tv * x > 0 and abs(x) >= float(os.environ.get('TS_CRYPTO_LINE', '50')):   # 11-06 用户定 crypto 纯行情线 30→50
                    continue
            out.append(f'  {tid}「{t}」:{msg}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_ts', type=int)
    ap.add_argument('--keep', action='append', default=[])
    ap.add_argument('--keep-file')
    ap.add_argument('--out')
    ap.add_argument('--ack-drift', default='')
    a = ap.parse_args()
    keeps = list(a.keep)
    if a.keep_file:
        keeps += [l.strip() for l in open(a.keep_file, encoding='utf-8') if l.strip() and not l.startswith('#')]
    hi = upper_bound(a.run_ts)
    rs_all = ledger.rows()
    links = ledger.create_links(rs_all)
    idx = [i for i, r in enumerate(rs_all) if a.run_ts <= r[0] < hi]
    rs = [rs_all[i] for i in idx]
    if not rs:
        sys.exit(f'🚨 run_ts={a.run_ts} 之后台账无行')
    created_ids = {links[i] for i in idx if rs_all[i][1] == 'create' and i in links}
    creates, pubs, culls, updates, restores, notes, others = [], [], [], [], [], [], []
    for i in idx:
        r = rs_all[i]
        act = r[1]
        if act == 'create':
            creates.append((links.get(i, '-'), r))
        elif act == 'update' and r[3] == '状态修正' and r[2] in created_ids and r[5] in ('', '-'):
            pubs.append(r)
        elif act == 'update':
            updates.append(r)
        elif act == 'cull':
            culls.append(r)
        elif act == 'restore':
            restores.append(r)
        elif act == 'note':
            notes.append(r)
        else:
            others.append(r)
    if culls and not keeps:
        sys.exit('🚨 本轮撤了 %d 条,缺「留-撤对照」(--keep \"id|标题|为什么留\")——复审员靠对照组判同批判留是否一致,'
                 '10-12/10-13 两轮漏给过;没有可对照的同类题就写一条 --keep \"-|无|本轮撤题无同类留题,理由…\"' % len(culls))
    bad = [k for k in keeps if k.count('|') < 2]
    if bad:
        sys.exit('🚨 --keep 须三段「id|标题|为什么留」: ' + ' / '.join(bad))
    drift = title_drift(rs)
    if drift and not a.ack_drift:
        sys.exit('🚨 本轮建/改的币题标题与币安现读差 ≥10 个百分点(纯行情题只拦跌破50%线(11-06 由30%上调)或方向反转,11-03用户定同向过线不动),送审前先处置'
                 '(11-01 13763 ESPORTS 建题 70% 几分钟后回落 59% 被复审员抓到):\n' + '\n'.join(drift) +
                 '\n确属不改(如已出射程)加 --ack-drift "<说明>"')
    tb = b0_titles()
    pub_ids = {r[2] for r in pubs} | {rid for rid, r in creates if ledger.self_published(r)}
    L = []
    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(a.run_ts / 1000))
    L.append(f'# 送审清单 {when} RUN_TS={a.run_ts}(review-packet.py 从台账生成)\n')
    L.append(f'台账 = 建 {len(creates)}(其中 {len(pub_ids)} 条同轮自推上线)/ 撤 {len(culls)} / 改 {len(updates)}'
             f'{f" / 恢复 {len(restores)}" if restores else ""} / note {len(notes)}'
             f'{f" / 其他 {len(others)}" if others else ""}(共 {len(rs)} 行)。')
    L.append(f'**你只读**:`~/.trend-scout/` 下任何文件都不许改,只写自己的输出文件。规则 {rule_version()}。\n')

    def title_of_cull(r):
        m = re.match(r'『([^』]+)』', r[4])
        if m:
            return m.group(1), ''
        t = tb.get(r[2], '')
        return t, ('(取自 b0 快照,撤后系统可能改写过标题)' if t else '(标题未知)')

    if culls:
        L.append(f'## 撤({len(culls)})')
        for r in culls:
            t, warn = title_of_cull(r)
            L.append(f'- {r[2]}「{t}」{warn} rc={r[3]}\n  备注:{clip(r[4])}')
        L.append('\n## 留-撤对照(主进程给出:本轮考虑过但决定留的同类题)')
        for k in keeps:
            i, t, why = (x.strip() for x in k.split('|', 2))
            L.append(f'- [留] {i}「{t}」——{why}')
    if updates:
        L.append(f'\n## 改({len(updates)})')
        for r in updates:
            d = r[5] if r[5] and r[5] != '-' else '(标题未变:改 status/关键词/标签)'
            L.append(f'- {r[2]} rc={r[3]}:{d}\n  备注:{clip(r[4])}')
    if creates:
        L.append(f'\n## 建({len(creates)})')
        for rid, r in creates:
            t = r[5][2:] if r[5].startswith('-→') else r[5]
            on = '已推上线' if rid in pub_ids else '⚠️ 未见同轮上线行'
            L.append(f'- {rid}「{t}」rc={r[3]} · {on}\n  备注:{clip(r[4])}')
    if restores:
        L.append(f'\n## 恢复({len(restores)})')
        for r in restores:
            L.append(f'- {r[2]} rc={r[3]}\n  备注:{clip(r[4])}')
    if notes:
        L.append(f'\n## note({len(notes)})')
        for r in notes:
            L.append(f'- {r[2]} [{r[3]}] {clip(r[4], 300)}')
    if others:
        L.append(f'\n## 其他({len(others)})')
        for r in others:
            L.append(f'- {r[1]} {r[2]} [{r[3]}] {clip(r[4], 300)}')
    L.append(f"""
## 你要输出的格式(只写到你自己的输出文件)
第一行 LEDGER=<本轮台账行数>|<note 行数>|<涉及 id 逗号分隔>(自己从 actions.tsv 里 run_ts≥{a.run_ts} 的行数出来,不要抄本清单)
第二行 AUDITED=<你审了几行>
第三行 SAMPLED=<你实测价格的 id>
之后每个 id 一行:<id>|处置OK 或 处置有误|<理由;实测的写「自检:」+ 当前价>""")
    txt = '\n'.join(L) + '\n'
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(txt)
        print(f'✔ 送审清单 → {a.out}(建 {len(creates)} / 撤 {len(culls)} / 改 {len(updates)} / note {len(notes)},共 {len(rs)} 行)')
    else:
        print(txt)


if __name__ == '__main__':
    main()
