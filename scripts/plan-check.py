#!/usr/bin/env python3
# plan-check.py — 审核员决策表机检(v3.5.4…v3.6.7;v3.5.5 段尾只认行首段名)。写手执行前、Lead 落账前都跑它;FAIL 行打回审核员,不许 Lead 自己改。
# 用法: plan-check.py <审核员产出文件> [扫描员产出文件] [--b0 <b0-latest.json>]
#   v3.5.14:给了 --b0 时,在线题(数字 id)的 domain 必须与 B0 里该题的 domain 一致,不一致 FAIL;B0 里找不到该题记 WARN。
#   v3.6.3(09-30 用户定):给了 --b0 时,撤 meme 题且 reason_code 属 log-action 的 GUARD(缺价格腿/缺诱因-未达线/灌水-vanity指标/
#     灌水-悬念疑问)的行,判据前 150 字里必须有四查行(四格全 ✗)或写明 重复/证伪/事实错误,否则 FAIL。
#     与 log-action.sh 同一作用域(lint.meme_scope)同一正则;150 字=Evose log-writer 落账备注的截取长度——
#     审核员漏写或写在判据后半段时,原先机检照过、写手把题撤了、落账才被拒写(前台已撤、台账没记)。
#     不给 --b0 时不查(作用域要读 B0 里这道题的关键词;写手沙箱没有 B0,Lead 侧带 --b0 的那次已在写手动手前查过)。
#   v3.6.4(10-01 用户定,Evose 第 51 轮):建/改 行的新标题没有价格腿(lint 双要素-缺价格)从 WARN 升 FAIL,
#     除非判据写了「免价格腿:监管/上架/硬事件/预告」之一(lint 的预告题正则本来就不报)。
#     起因:审核员把 10000003028 改成无价格腿的事件标题(本轮有报价没写),机检只给 WARN 放行,写手按双要素拒改——
#     审核员定了改、写手不改,题原样留在线上。审核员当场补价格,或明写豁免类别交人复核。
#     v3.7.20(10-30 用户定,Evose 29c):reason_code=承接更新 的行只拿「免价格腿:预告」豁免 → FAIL。承接=预告的事件已经发生、
#     标题改成了完成时,预告豁免随之失效(10-29 22:00 影子轮 10000003362 GDP 公布后改题没写价格,机检只给 WARN)。
#   v3.6.5(10-02 用户定,Evose 第 53 轮):tradfi 建/改 新标题含涨跌% 却没有写手第 4 条认的时段词 → FAIL。
#     词表与写手提示词逐字一致(盘前/盘中/收涨/收跌/盘后/夜盘/尾盘/午盘/一度/冲高/振幅),比 lint 的时段 WARN 窄——
#     第 53 轮 10000003043、10000003033 机检照过、写手拒改,审核员定了改、题原样留在线上。
#   v3.6.7(10-14 用户定):改 行把原标题的诱因摘掉、新标题落成「缺诱因」(lint 双要素-缺诱因,纯价格且幅度不到线)→ FAIL,
#     除非判据写「免诱因:meme豁免」或「免诱因:纯行情-A定则」(lint 自己说的两种豁免)。只查「原标题有诱因、新标题没了」,
#     原标题本来就缺诱因的照旧 WARN。起因:09-28 Evose 正式轮 10000003016/10000003017 审核员判原诱因无源后直接摘掉,
#     改成「KOSPI收跌2.7%」「黄金盘中跌3.3%」这类 <10% 无诱因标题,机检只给 WARN 放行、上线后被用户点名撤/改。
#     原诱因站不住时只有两条路:换一个有出处的诱因,或者撤题——不许改成光秃秃的价格标题。
#   起因(09-23 第二十七轮):审核员拿不到在线题的 domain(机审清单与最后活动表都不带),只能按题号段位猜;
#   写手的时段前缀闸全靠这一列,tradfi 题被猜成 crypto 就静默跳过了前缀检查。
#   输出 PLAN: 汇总行 + 逐行 OK/WARN/FAIL;有 FAIL 则 exit 1
#   v3.5.9:另核【钉合约】段(没有这段不算错)。给了扫描员产出文件时,每个「钉」的地址必须出现在扫描员【待钉候选】段——
#   地址只能来自扫描员用 CoinGecko 核实过的候选,审核员不许自己写一个;不给扫描员文件则该项记 WARN。
# 起因(09-21 Evose 第二十轮):
#   ① Lead 派活时自拟「题号|动作|reason_code|判据」4 列,审核员照做,决策表偏离提示词的 7 列;
#   ② 审核员给「改」配了撤题枚举(反转错向/疑问句-悬念)和不存在的码(时效-窗口题),Lead 落账前按语义
#      自行映射成改题枚举——等于替审核员下判断,并绕开了 log-action.sh 的枚举闸;
#   ③ 新标题「AKE跌18.46%，报0.053美元」这类纯价格题一路无闸。
# 枚举不在本文件另写一份:从 log-action.sh 的 R_* 行解析(单一事实源)。
import re, sys, os
D = os.path.expanduser('~/.trend-scout')
sys.path.insert(0, D)
import lint

def enums():
    src = open(os.path.join(D, 'log-action.sh'), encoding='utf-8').read()
    g = {}
    for k in ('R_CREATE', 'R_CULL', 'R_UPDATE', 'R_OTHER'):
        m = re.search(r'^%s="([^"]*)"' % k, src, re.M)
        if not m: sys.exit('🚨 log-action.sh 里找不到 %s,枚举无法解析' % k)
        g[k] = set(m.group(1).split())
    return g

WRITER_SESSION = re.compile(r'盘前|盘中|收涨|收跌|盘后|夜盘|尾盘|午盘|一度|冲高|振幅')
NOPRICE = re.compile(r'免价格腿\s*[:：]\s*(监管|上架|硬事件|预告)')
NOCAUSE = re.compile(r'免诱因\s*[:：]\s*(meme豁免|纯行情-A定则)')
ACT = {'建': 'R_CREATE', '改': 'R_UPDATE', '撤': 'R_CULL', '留': None, '上线': None}
EMPTY = {'', '-', '—', '无', '留', '留（不改）', '不改', '（不改）'}

def section(txt, name):
    i = txt.find('【%s】' % name)
    if i < 0: return None
    j = i + len(name) + 2
    m = re.search(r'^\s*【[^】]+】', txt[j:], re.M)
    return txt[j: j + m.start() if m else None]


ADDR = re.compile(r'^(0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}|\S{20,})$')


def pins(txt, scan):
    """【钉合约】段:每行 代号｜链｜地址｜钉 或 暂不可钉｜依据。返回 (行, fails, warns)。"""
    body = section(txt, '钉合约')
    if body is None: return [], 0, 0, {}
    cand = section(scan, '待钉候选') if scan is not None else None
    rows = []; f = w = 0; acts = {'钉': 0, '暂不可钉': 0}
    for ln in body.splitlines():
        s = ln.strip()
        if s.count('｜') + s.count('|') < 4: continue
        cols = [c.strip() for c in re.split(r'[｜|]', s, maxsplit=4)]
        if cols[0] in ('代号', 'SYM') or cols[3] in ('动作',): continue
        bad = []; wn = []
        sym, chain, addr, act, why = cols
        if act in acts: acts[act] += 1
        if not re.fullmatch(r'[A-Za-z0-9$]{1,20}', sym): bad.append('代号=%r' % sym)
        if act not in ('钉', '暂不可钉'): bad.append('动作=%r(只许 钉／暂不可钉)' % act)
        if not why: bad.append('依据为空(钉:为什么是题里那个币,要有新闻原文或项目名＋链的对应;暂不可钉:为什么不能钉)')
        if act == '钉':
            if not chain or chain in EMPTY: bad.append('钉 缺链')
            if not ADDR.match(addr): bad.append('地址=%r 格式不对' % addr)
            elif cand is None: wn.append('没给扫描员产出文件,无法核对地址来自【待钉候选】')
            elif addr.lower() not in cand.lower(): bad.append('地址不在扫描员【待钉候选】里——地址只能来自扫描员核实过的候选,不许自拟')
        if bad: rows.append(('FAIL', sym, bad)); f += 1
        elif wn: rows.append(('WARN', sym, wn)); w += 1
        else: rows.append(('OK', sym, []))
    return rows, f, w, acts


def b0_domains(path):
    import json
    d = json.load(open(path, encoding='utf-8'))
    tp = d['topics'] if isinstance(d, dict) else d
    global B0T
    B0T = {str(t['id']): t for t in tp}
    return {str(t['id']): t.get('domain') for t in tp}


B0T = {}
SICHA = re.compile(r'四查(:|：) *幅度✗ *成交额✗ *市值关口✗ *硬事件✗')   # 与 log-action.sh 同一正则
NOTE_CUT = 150                                                          # 与 evose-round.py log-writer 的 why[:150] 一致


def guard_codes():
    """撤 meme 要四查的 reason_code 集合:从 log-action.sh 的 GUARD 解析,不另抄一份。"""
    src = open(os.path.join(D, 'log-action.sh'), encoding='utf-8').read()
    m = re.search(r"^GUARD=\{([^}]*)\}", src, re.M)
    if not m: sys.exit('🚨 log-action.sh 里找不到 GUARD,四查闸无法解析')
    return set(re.findall(r"'([^']+)'", m.group(1)))


def is_meme(rid):
    """与 log-action.sh 同判:B0 里找不到这道题按 meme 处理(保守);token_exist 坏了退回旧判据。"""
    t = B0T.get(rid)
    if t is None: return True
    try:
        import token_exist; ex = token_exist.exists
    except Exception:
        ex = None
    return bool(lint.meme_scope(t, ex))


def main():
    argv = sys.argv[1:]; b0 = None
    if '--b0' in argv:
        k = argv.index('--b0')
        if k + 1 >= len(argv): sys.exit('--b0 后面要跟 b0-latest.json 路径')
        b0 = b0_domains(argv[k + 1]); del argv[k:k + 2]
    if len(argv) < 1: sys.exit('用法: plan-check.py <审核员产出文件> [扫描员产出文件] [--b0 <b0-latest.json>]')
    txt = open(argv[0], encoding='utf-8').read()
    scan = open(argv[1], encoding='utf-8').read() if len(argv) > 1 else None
    i = txt.find('【决策表】')
    if i < 0: print('PLAN: FAIL 找不到【决策表】段'); sys.exit(1)
    # v3.5.5 段尾=下一个「行首」【…】段名。09-21 第二十一轮实测:第二十轮原件第一行判据正文里写着
    #   「【存量取价】段本轮未送达」,按「下一个【」截段,19 行的表只数到 2 行——机检自己漏行。
    m = re.search(r'^\s*【[^】]+】', txt[i + 5:], re.M)
    body = txt[i + 5: i + 5 + m.start() if m else None]
    g = enums(); allr = set().union(*g.values())
    guard = guard_codes() if b0 is not None else set()
    rows = []; fails = warns = 0; cnt = {}
    for ln in body.splitlines():
        s = ln.strip()
        if s.count('｜') + s.count('|') < 4: continue          # 说明文字/空行
        cols = [c.strip() for c in re.split(r'[｜|]', s, maxsplit=6)]
        if cols[0].lower() in ('id', '题号') or ('reason_code' in s and '判据' in s and not re.match(r'\s*(\d+|NEW-\d+)\s*$', cols[0])):
            continue                                              # 表头(含「列序：题号 | … | reason_code | 判据」这类带前缀的)
        rid = cols[0]; bad = []; wn = []
        if len(cols) != 7:
            bad.append('列数=%d≠7(应为 id｜domain｜当前标题｜动作｜新标题｜reason_code｜判据,以审核员提示词为准,Lead 不许另拟格式)' % len(cols))
            rows.append(('FAIL', rid, bad)); fails += 1; continue
        _, dom, cur, act, new, rc, why = cols
        if not re.fullmatch(r'\d+|NEW-\d+', rid): bad.append('id 非题号/NEW-序号')
        if dom not in ('crypto', 'tradfi'): bad.append('domain=%r(必填 crypto/tradfi)' % dom)
        elif b0 is not None and rid.isdigit():
            if rid not in b0: wn.append('B0 里找不到这道题,domain 无法核对')
            elif b0[rid] in ('crypto', 'tradfi') and b0[rid] != dom:
                bad.append('domain=%s 与 B0 不符(B0=%s)——在线题 domain 只能照最后活动表/B0 抄,不许按标的名猜' % (dom, b0[rid]))
        if act not in ACT: bad.append('动作=%r(只许 建/改/撤/留/上线)' % act)
        else:
            cnt[act] = cnt.get(act, 0) + 1
            grp = ACT[act]
            if grp and rc not in g[grp]:
                hint = ''
                if act == '改' and rc in g['R_CULL']: hint = '——这是撤题枚举,「改」只能从改题枚举(%s)里选,选哪个由审核员定' % '/'.join(sorted(g['R_UPDATE']))
                elif rc not in allr: hint = '——不在任何枚举里'
                bad.append('reason_code=%r 不属于「%s」枚举%s' % (rc, act, hint))
            elif not grp and rc not in allr:
                bad.append('reason_code=%r 不在任何枚举里' % rc)
            if act in ('建', '改'):
                if new in EMPTY: bad.append('建/改 缺新标题')
                else:
                    for lv, gate, msg, _v in lint.lint_title(new, dom if dom in ('crypto', 'tradfi') else 'crypto'):
                        if lv == 'FAIL': bad.append('lint %s: %s' % (gate, msg))
                        elif gate == '双要素-缺价格' and not NOPRICE.search(why):
                            bad.append('新标题没有价格腿(涨跌%%/报X/持平):把本轮实测价写进标题;确属豁免的,判据写「免价格腿:监管/上架/硬事件/预告」之一(v3.6.4)')
                        elif gate == '双要素-缺价格' and rc == '承接更新' and set(NOPRICE.findall(why)) == {'预告'}:
                            bad.append('承接更新=事件已经发生,新标题是完成时,不再是预告——「免价格腿:预告」不成立:把本轮实测价写进标题(v3.7.20)')
                        elif (gate == '双要素-缺诱因' and act == '改' and cur not in EMPTY and not NOCAUSE.search(why)
                              and not any(g2 == '双要素-缺诱因' for _l, g2, _m, _w in lint.lint_title(cur, dom if dom in ('crypto', 'tradfi') else 'crypto'))):
                            bad.append('改题把原标题的诱因摘掉了,新标题成了缺诱因的纯价格标题(%s):原诱因站不住就换一个有出处的诱因写进标题,'
                                       '找不到就改判「撤」;确属豁免的,判据写「免诱因:meme豁免」或「免诱因:纯行情-A定则」(v3.6.7)' % msg)
                        elif gate.startswith('双要素'): wn.append('lint %s: %s' % (gate, msg))
                    if dom == 'tradfi' and lint.PCT.search(new) and not WRITER_SESSION.search(new):
                        bad.append('tradfi 新标题有涨跌%却没有时段词(盘前/盘中/收涨/收跌/盘后/夜盘/尾盘/午盘/一度/冲高/振幅 之一),写手第 4 条会拒执行(v3.6.5)')
            if act == '改' and new == cur: bad.append('改 但新标题与当前标题相同')
            if act == '撤' and rc in guard and rid.isdigit() and is_meme(rid):
                head = why[:NOTE_CUT]
                if not re.search(r'重复|证伪|事实错误', head) and not SICHA.search(head):
                    bad.append('撤 meme 行判据前 %d 字里没有四查行(须以「四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗」开头,四格全 ✗;'
                               '任一格命中应留)——落账只取判据前 %d 字,写在后面等于没写' % (NOTE_CUT, NOTE_CUT))
        if not why: bad.append('判据为空')
        if bad: rows.append(('FAIL', rid, bad)); fails += 1
        elif wn: rows.append(('WARN', rid, wn)); warns += 1
        else: rows.append(('OK', rid, []))
    if not rows: print('PLAN: FAIL【决策表】段里没有任何数据行'); sys.exit(1)
    summ = ' '.join('%s%d' % (k, cnt.get(k, 0)) for k in ('建', '改', '撤', '留', '上线'))
    print('PLAN: 行=%d %s FAIL=%d WARN=%d' % (len(rows), summ, fails, warns))
    for lv, rid, why in rows:
        if lv != 'OK': print('%s\t%s\t%s' % (lv, rid, '；'.join(why)))
    prow, pf, pw, acts = pins(txt, scan)
    if prow:
        print('PIN: 行=%d 钉=%d 暂不可钉=%d FAIL=%d WARN=%d' % (len(prow), acts['钉'], acts['暂不可钉'], pf, pw))
        for lv, sym, why in prow:
            if lv != 'OK': print('%s\tPIN %s\t%s' % (lv, sym, '；'.join(why)))
        fails += pf; warns += pw
    if fails: print('🚨 有 FAIL 行:整张表打回审核员重出。Lead 不许自己改列、改码、改标题来凑过(09-21 第二十轮的映射就是这么绕开枚举闸的)')
    if warns: print('⚠️ WARN 行须在写前确认/报告里逐行列出,由人裁豁免是否成立')
    sys.exit(1 if fails else 0)

if __name__ == '__main__': main()
