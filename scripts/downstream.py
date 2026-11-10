#!/usr/bin/env python3
"""downstream.py — 回读看板题在 Followin 资讯流里的成品(v3.7.0)。

为什么要有:看板题不是终点。题上线的同一秒,下游按「标题+关键词匹配出的标签」生成一篇资讯
(英文标题、「发生了什么/交易指南」正文、asset_types)。10-15 首扫实测 5 条新题里 3 条在下游挂错标的:
  RKLB 题关键词含 Neutron → 被挂到 NTRN(Neutron 币);台积电题被写成「Robinhood Chain 上的代币化股票」;
  BSP 题下游判不清是不是币。建题时的 tag 检查只看 ID 位数,看不出它指向什么——只有回读成品才看得见。

取数:followin news 空 query + sort_by=time + time_range=2d(返回的就是看板在线题的成品,10-15 实测 14 篇全是我们的题);
      本题英文标题从 console list(lang=en) 取,与资讯标题逐字对上。
判定(每题一行,落 downstream.log.tsv):
  错标      asset_types 里有本题关键词/标题都没有的符号(RKLB → NTRN)            ← 必修
  域不符    资讯 asset_type 与本题 domain 不同                                    ← 必修
  (等效)    tradfi 题挂到同名的代币化股票/股票永续(TSM→Robinhood Chain 上的 TSM、BSP→股票永续)——同一家公司,
            用户 10-15 定「不算错标,默认等效」,判 OK 并在说明里标出
  正文不符  标题里的百分数正文一个都没有(改题后正文不重生成,或下游串了别的日期)  ← 只记录,不归我们修
  未见下游  资讯流里没找到这道题
修法:topic.py update --id X --rc tag修正 --keywords "<去掉误导词>" 或 --tags '[]'(宁空不错标),改完重跑本脚本。

用法:
  downstream.py <run_ts>        本轮建过/改过标题或关键词/上线/恢复的题(台账 ts≥run_ts)
  downstream.py --ids 1,2,3     指定题
  downstream.py --all           近 2 天全部在线题(体检)
  downstream.py equiv <下游符号> <本题符号> "<理由>"   登记等效(下游 ROBINHOOD = 本题 HOOD),之后不再报错标
  downstream.py false-alarm <题id> "<理由>"          把该题此前的错标行记为检测器误报(不计入资格线/每晚复盘)
  downstream.py clash <触发词> <错挂符号> [题id]     手工登记撞名表;clash-list 列全表。错标时能自动定位触发词的会自动登记
末行 DOWNSTREAM: 回读=N 匹配=M 错标=K 正文不符=J 未见=U;K>0 退出码 2。
注入(回归):DOWNSTREAM_FEED=<资讯 json> DOWNSTREAM_TOPICS=<题 json,含 title_en> DOWNSTREAM_LOG=<日志>,均不联网。
"""
import json, os, re, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
D = os.path.expanduser('~/.trend-scout')
LOG = os.environ.get('DOWNSTREAM_LOG') or os.path.join(D, 'downstream.log.tsv')
TOKENISH = re.compile(r'代币化|Robinhood Chain|加密代币|链上代币|tokeni[sz]ed', re.I)
# 11-10 架构 review:原写法用 \b 做边界,而中文在 Python 里也算「词内字符」——「VRT涨7.6%」「LITE盘中」这类紧贴中文的代码一个都抽不出来,
#   标题里明写的标的不进比对集,10000003686(Vertiv,关键词 Vertiv、标题 VRT)被报错标。边界改成「前后不是英文字母/数字」。
SYM = re.compile(r'(?<![A-Za-z0-9])[A-Z][A-Z0-9.]{1,9}(?![A-Za-z0-9])')
# 标题里常见的大写缩写不是标的:不进比对集(否则下游真挂到叫 AI/ETF 的代币时会被放过)
NOT_TICKER = {'AI', 'CPI', 'PPI', 'PCE', 'GDP', 'ETF', 'IPO', 'CEO', 'CFO', 'SEC', 'FED', 'FOMC', 'USD', 'OI', 'TVL', 'RWA', 'NFT',
              'KOL', 'DEX', 'CEX', 'ATH', 'EPS', 'HBM', 'DRAM', 'NAND', 'GPU', 'CPU', 'LLM', 'US', 'UK', 'EU', 'OPEC'}
NAMES = os.environ.get('DS_NAMES') or os.path.join(D, 'ds-names.json')     # {"equiv": {"ROBINHOOD": ["HOOD"]}, "log": [...]}
CLASH = os.environ.get('DS_CLASH') or os.path.join(D, 'ds-clash.tsv')      # ts \t 触发词 \t 错挂符号 \t 方式 \t 来源题 \t 出现位置
WORD = re.compile(r'[A-Za-z][A-Za-z0-9]+')
PCTN = re.compile(r'(\d+(?:\.\d+)?)%')
MUST_FIX = ('错标', '域不符')
# 宏观/大宗题关键词多是中文,下游挂到这些符号属正常映射,不算错标
ALIAS = {'黄金': {'XAU', 'XAUT', 'PAXG', 'GC', 'GLD'}, '金价': {'XAU', 'XAUT', 'PAXG', 'GC'},
         '原油': {'CL', 'WTI', 'BRENT', 'USO'}, '比特币': {'BTC'}, '以太坊': {'ETH'},
         '纳指': {'QQQ', 'NDX', 'IXIC'}, '标普': {'SPY', 'SPX'}, '美债': {'TLT'}}


def norm(s):
    return re.sub(r'[\s\W_]+', '', (s or '').lower())


def feed():
    p = os.environ.get('DOWNSTREAM_FEED')
    if p:
        return json.load(open(p, encoding='utf-8'))
    import news_fetch as nf
    s = nf.SSE()
    r = s.call('news', {'time_range': '2d', 'limit': 50, 'sort_by': 'time', 'verbosity': 'standard'})
    if '_error' in r:
        raise SystemExit('🚨 资讯流取数失败: ' + r['_error'][:200])
    return (r.get('results') or {}).get('articles') or []


def topics_en(days=3):
    """{id: topic(含 title=英文、original_title=中文、keywords、domain、status)}"""
    p = os.environ.get('DOWNSTREAM_TOPICS')
    if p:
        out = {}
        for t in json.load(open(p, encoding='utf-8')):
            t = dict(t)
            t['original_title'] = t.get('original_title') or t.get('title')
            t['title'] = t.get('title_en') or t.get('title')
            out[str(t['id'])] = t
        return out
    from console import Console
    c = Console()
    out = {}
    today = datetime.date.today()
    for k in range(days):
        day = (today - datetime.timedelta(days=k)).isoformat()
        for t in c.list_day(day, lang='en'):
            out[str(t['id'])] = t
    return out


def targets(run_ts):
    import ledger
    rs = ledger.rows()
    ids = []
    links = ledger.create_links(rs)
    for i, r in enumerate(rs):
        if r[0] < int(run_ts):
            continue
        if r[1] == 'create':
            rid = links.get(i)
            if rid:
                ids.append(rid)
        elif r[1] in ('update', 'restore') and r[2] not in ('-', '') and (
                r[3] in ('状态修正', 'tag修正') or (r[5] and r[5] != '-')):
            ids.append(r[2])
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def tickers(t):
    s = set()
    kw = [k.strip() for k in re.split(r'[,，]', t.get('keywords') or '') if k.strip()]
    for k in kw:
        s |= set(SYM.findall(k))                          # 原样大写的 ticker(RKLB / 000660.KS)
        if re.fullmatch(r'[A-Za-z0-9.]{1,6}', k):         # 短英文词当 ticker 认(btc→BTC);「Rocket Lab」这类名字不拆成 ROCKET/LAB
            s.add(k.upper())
        elif not re.search(r'[A-Za-z]', k) and len(k) <= 6:   # 中文代币名原样认(龙虾);10-15 首次实跑把「龙虾」误判错标
            s.add(k)
        for a, syms in ALIAS.items():
            if a in k:
                s |= syms
    s |= {x for x in SYM.findall(t.get('original_title') or '') if x.rstrip('.') not in NOT_TICKER}
    s |= {x.split('.')[0] for x in list(s)}          # 000660.KS → 000660;BRK.B → BRK
    return s


def equiv_map():
    """下游符号 → 与之等效的本题符号(人工登记)。例:下游把 Robinhood 的代币化股票标成 ROBINHOOD,本题写的是 HOOD(用户 10-15 定等效)。"""
    try:
        return {k.upper(): [x.upper() for x in v] for k, v in (json.load(open(NAMES, encoding='utf-8')).get('equiv') or {}).items()}
    except Exception:
        return {}


def add_equiv(ds_sym, my_sym, why):
    try:
        d = json.load(open(NAMES, encoding='utf-8'))
    except Exception:
        d = {}
    e = d.setdefault('equiv', {})
    cur = e.setdefault(ds_sym.upper(), [])
    if my_sym.upper() not in cur:
        cur.append(my_sym.upper())
    d.setdefault('log', []).append({'ts': int(time.time() * 1000), 'ds': ds_sym.upper(), 'mine': my_sym.upper(), 'why': why})
    json.dump(d, open(NAMES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def clash_rows():
    if not os.path.exists(CLASH):
        return []
    return [f for f in (l.rstrip('\n').split('\t') for l in open(CLASH, encoding='utf-8')) if len(f) >= 3 and f[0].isdigit()]


def add_clash(trigger, wrong, how, src='', where=''):
    trigger, wrong = trigger.strip().upper(), wrong.strip().upper()
    if any(r[1] == trigger and r[2] == wrong for r in clash_rows()):
        return False
    with open(CLASH, 'a', encoding='utf-8') as f:
        f.write('\t'.join(str(x) for x in (int(time.time() * 1000), trigger, wrong, how, src, where)) + '\n')
    return True


def learn_clash(t, bad):
    """撞名表(11-10 架构 review):回读发现错标后,自动找出是哪个词把下游带偏的,记下来给 topic.py 建题前查。
    由来:「Rocket Lab→LAB」11-05、11-10 各犯一次,「LITE→LIT」11-02、11-09 各犯一次——每次都是上线后才发现再改。
    能自动定位的两种:整词(Lab=LAB、Mask=MASK)、前缀(FERG→FER、LITE→LIT);定位不到的(Neutron→NTRN)打印提示,手工 clash 登记。
    回归注入(DOWNSTREAM_FEED)且没单独给 DS_CLASH 时不学,免得用例往生产撞名表里写。"""
    if os.environ.get('DOWNSTREAM_FEED') and not os.environ.get('DS_CLASH'):
        return []
    srcs = (('关键词', t.get('keywords') or ''), ('标题', t.get('original_title') or ''), ('英文标题', t.get('title') or ''))
    out = []
    for s0 in bad:
        s = s0.upper().split('.')[0]
        found = []
        for where, text in srcs:
            for w in WORD.findall(text):
                u = w.upper()
                if u == s:
                    found.append((u, '整词', where))
                elif len(s) >= 3 and u.startswith(s):
                    found.append((u, '前缀', where))
        seen = set()
        for u, how, where in found:
            if u in seen:
                continue
            seen.add(u)
            if add_clash(u, s, how, t.get('id', ''), where):
                out.append(f'撞名表+1:「{u}」→ {s}({how},出现在{where})')
        if not found:
            out.append(f'撞名表:没能自动定位是哪个词把下游带到 {s}——查清后登记:downstream.py clash <词> {s} {t.get("id", "")}')
    return out


def clash_hits(title, kws):
    """建题/改关键词前查撞名表。返回 [(触发词, 错挂符号, '关键词'|'标题', 来源题, 日期)]。
    本题关键词里就有那个符号(这道题说的就是它)不算撞名。"""
    kws = [k.strip() for k in (kws or []) if k and k.strip()]
    own = {k.upper() for k in kws}
    kw_words = {w.upper() for k in kws for w in WORD.findall(k)}
    ti_words = {w.upper() for w in WORD.findall(title or '')}
    out = []
    for r in clash_rows():
        trig, wrong = r[1], r[2]
        if wrong in own:
            continue
        day = datetime.datetime.fromtimestamp(int(r[0]) / 1000).strftime('%m-%d')
        src = r[4] if len(r) > 4 else ''
        if trig in kw_words:
            out.append((trig, wrong, '关键词', src, day))
        elif trig in ti_words:
            out.append((trig, wrong, '标题', src, day))
    return out


def false_alarms(rows):
    """{题id: 最晚一条「误报更正」的 ts}。该题在此之前的「错标/域不符」行不计入资格线与每晚复盘(检测器自己判错的,不是挂错)。"""
    fa = {}
    for x in rows:
        if len(x) >= 4 and x[3] == '误报更正' and x[0].isdigit():
            fa[x[2]] = max(fa.get(x[2], 0), int(x[0]))
    return fa


def judge(t, art):
    v = []
    at = art.get('asset_type')
    if at and at != t.get('domain'):
        v.append(('域不符', f"资讯 asset_type={at},本题 {t.get('domain')}"))
    syms = [str(x).lstrip('$') for x in (art.get('asset_types') or [])]   # 11-07 复盘:资讯流返回「$HUT」带美元号,原样比对把 Hut 8 股票永续误报错标
    tk = tickers(t)
    eq = equiv_map()
    bad = [s for s in syms if s.upper() not in tk and s.upper().split('.')[0] not in tk and not (set(eq.get(s.upper(), [])) & tk)]
    if bad:
        v.append(('错标', f"下游挂到 {','.join(bad)},本题标的 {','.join(sorted(tk)) or '无'}"))
    body = art.get('content') or ''
    equiv = t.get('domain') == 'tradfi' and syms and not bad and TOKENISH.search(body)   # 用户 10-15 定:同名代币化股票/股票永续=等效
    tp = set(PCTN.findall(art.get('title') or ''))
    if tp and body and not (tp & set(PCTN.findall(body))):
        v.append(('正文不符', f"标题 {','.join(sorted(tp))}% 正文里都没有(改题后正文不重生成或串了别的日期)"))
    return v or [('OK', f"下游标的 {','.join(syms) or '无标签'}" + ('(同名代币化股票/股票永续,等效)' if equiv else ''))]


def run(ids, show_all=False):
    arts = feed()
    by = {norm(a.get('title')): a for a in arts if a.get('title')}
    tp = topics_en()
    if show_all:
        ids = [i for i, t in tp.items() if t.get('status') == 0]
    rows, n_match, n_bad, n_txt, n_miss = [], 0, 0, 0, 0
    bad_ids = set()
    learned = []
    now = int(time.time() * 1000)
    for i in ids:
        t = tp.get(str(i))
        if not t:
            rows.append((i, '未见下游', '近 3 天 console 列表里没有这道题'))
            n_miss += 1
            continue
        a = by.get(norm(t.get('title')))
        if not a:
            rows.append((i, '未见下游', f"资讯流没有「{(t.get('title') or '')[:50]}」(status={t.get('status')})"))
            n_miss += 1
            continue
        n_match += 1
        for verdict, detail in judge(t, a):
            rows.append((i, verdict, detail))
            if verdict in MUST_FIX:
                bad_ids.add(i)
            if verdict == '错标':
                m = re.match(r'下游挂到 ([^,]+(?:,[^,]+)*),本题标的', detail)
                for msg in learn_clash(dict(t, id=i), m.group(1).split(',') if m else []):
                    learned.append(msg)
            if verdict == '正文不符':
                n_txt += 1
    n_bad = len(bad_ids)
    with open(LOG, 'a', encoding='utf-8') as f:
        for i, verdict, detail in rows:
            f.write(f"{now}\t{os.environ.get('RUN_TS', '')}\t{i}\t{verdict}\t{detail.replace(chr(9), ' ').replace(chr(10), ' ')}\n")
    title = {str(k): (v.get('original_title') or '')[:28] for k, v in tp.items()}
    for i, verdict, detail in rows:
        mark = '🚨' if verdict in MUST_FIX else ('ℹ️' if verdict in ('正文不符', '未见下游') else '✔')
        print(f"{mark} {i} {title.get(str(i), '')} | {verdict}: {detail}")
    for msg in learned:
        print('   ' + msg)
    if bad_ids:
        print("   修法: topic.py update --id <id> --rc tag修正 --keywords \"<去掉误导词>\" 或 --tags '[]'(宁空不错标),改完重跑")
    print(f"DOWNSTREAM: 回读={len(ids)} 匹配={n_match} 错标={n_bad} 正文不符={n_txt} 未见={n_miss}")
    return n_bad


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    if a[0] == 'equiv':
        if len(a) < 4:
            sys.exit('用法: downstream.py equiv <下游符号> <本题符号> "<为什么是同一标的>"')
        add_equiv(a[1], a[2], a[3])
        print(f'✔ 等效登记:下游 {a[1].upper()} = 本题 {a[2].upper()}({a[3]})')
        return
    if a[0] == 'false-alarm':
        if len(a) < 3:
            sys.exit('用法: downstream.py false-alarm <题id> "<为什么是检测器误报>"')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f"{int(time.time() * 1000)}\t\t{a[1]}\t误报更正\t{a[2].replace(chr(9), ' ').replace(chr(10), ' ')}\n")
        print(f'✔ {a[1]} 此前的错标行记为误报,不计入资格线/复盘({a[2]})')
        return
    if a[0] == 'clash':
        if len(a) < 3:
            sys.exit('用法: downstream.py clash <触发词> <错挂符号> [来源题id]')
        ok = add_clash(a[1], a[2], '手工', a[3] if len(a) > 3 else '', '')
        print(('✔ 撞名表+1' if ok else 'ℹ️ 已在撞名表') + f':「{a[1].upper()}」→ {a[2].upper()}')
        return
    if a[0] == 'clash-list':
        for r in clash_rows():
            print(f"  {datetime.datetime.fromtimestamp(int(r[0]) / 1000):%m-%d} 「{r[1]}」→ {r[2]} {' '.join(r[3:])}")
        return
    if a[0] == '--ids':
        ids = [x for x in a[1].split(',') if x]
        bad = run(ids)
    elif a[0] == '--all':
        bad = run([], show_all=True)
    else:
        os.environ.setdefault('RUN_TS', a[0])
        ids = targets(a[0])
        if not ids:
            print('DOWNSTREAM: 回读=0 匹配=0 错标=0 正文不符=0 未见=0(本轮没有建/改标题/上线的题)')
            sys.exit(0)
        bad = run(ids)
    sys.exit(2 if bad else 0)


if __name__ == '__main__':
    main()
