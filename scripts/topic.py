#!/usr/bin/env python3
"""topic.py — 看板写操作的唯一入口(v3.7.0):预检 → 写看板 → 用真实 id 记账 → 回读核对,一条命令做完。

为什么:
  ① 记账和写看板分两步、由模型排顺序 → 10-14 同批并发,记账被拒、看板已改,出现无账写入;
     「先记账」又让建题行只能记 id「-」,周报两项指标与 b0-audit ⑤ 静默失效三周(见 ledger.py)。
  ② 机械活交给模型做 → 10-15 RKLB 跌幅两次舍入写错、送审清单计数写错。
  撤题早有正例:b0-cull.py 把「写+记账」合成一步,10-15 首扫 14 次写入零顺序错误。本工具把这条路推广到建/改/上线/撤/恢复。

顺序(每条写操作):
  1. 预检:标题机械闸(lint.py,FAIL 拦)·--pct 涨跌幅核对(pct.py)·keywords 格式(字符串、≤4 个)·
     系统建 tradfi 题窗口内改标题拦(会被系统刷回,10-01 实测)·log-action.sh 全部闸(LA_CHECK=1,只校验不落账)
     任一不过 → 不碰看板,拦截照样进 actions-rejected.tsv(周报 ⑥ 数得到)
  2. 写看板(console-mcp,失败 → 不落账,退出)
  3. 立刻落账(建题用真实 id;落账失败 → 写进 actions-unlogged.tsv,checklist verify 不放行)
  4. 回读核对:标题/status/关键词与写入一致;建题与改关键词时顺带查下游成品(downstream.py),挂错标的当场报

用法:
  topic.py create  --domain tradfi|crypto --title T --keywords "A,B" --rc RC (--note N | -T "判据|实测|因")
                   [--topic-type 0|1|2] [--pct 标签=现价/前收 ...] [--no-publish] [--pub-note N] [--dry]
  topic.py update  --id ID --rc RC (--note N | -T ...) [--title 新] [--keywords K] [--tags JSON] [--pct ...] [--dry]
  topic.py publish --id ID [--note N] [--dry]          status=0,rc=状态修正
  topic.py cull    --id ID --rc RC (--note N | -T ...) [--dry]
  topic.py restore --id ID --rc RC (--note N | -T ...) [--dry]
  topic.py get     --id ID [--lang en]
  topic.py check   <文件|->       批量预检(11-10):每行一条上面的命令,逐条 --dry 跑完全部检查,一次列全每条被拦的原因;不写看板不落账
  共用:tradfi 标题含「盘中」自动 event.sh add 收盘复查(v3.7.1,TOPIC_NO_REVIEW=1 关);--no-downstream 跳过下游回读;--force-system-edit 明知会被刷回仍改系统建 tradfi 窗口内标题
注入(回归):CONSOLE_FAKE(见 console.py)+ ACTIONS/SNAPSHOTS/REJ/UNLOGGED/CHECK_HITS(v3.7.22 检查计数);DOWNSTREAM_* 见 downstream.py。
"""
import argparse, json, os, re, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
D = os.path.expanduser('~/.trend-scout')
LA = os.path.join(HERE, 'log-action.sh')
CULL_RC_PREFIX_NOTE = '『{}』'


def _now():
    return int(time.time() * 1000)


def _append(path_env, name, cols):
    p = os.environ.get(path_env) or os.path.join(D, name)
    with open(p, 'a', encoding='utf-8') as f:
        f.write('\t'.join(str(c).replace('\t', ' ').replace('\n', ' ⏎ ') for c in cols) + '\n')


def hit(check, outcome, act, tid, rc):
    """v3.7.22 检查计数(11-03 用户定):退役要有依据。此前只有 gate.sh 记「谁查了闸」,代码里的检查拦了几次、
    靠豁免过了几次都不记——topic.py 两周 471→836 行,没有一条能证明该删。
    outcome:拦=检查拦下;豁免=备注/参数用了这条检查的豁免口子且写入成功。retro.py day/prune 的「减法候选」读它。"""
    _append('CHECK_HITS', 'check-hits.tsv', [_now(), check, outcome, act, tid, rc])


# 备注里的豁免词 → 它放行的检查(写入成功才记「豁免」;豁免词出现但检查本不会拦的也会计入,只作信号)
WAIVERS = (('射程外仍改', 'out_of_scope'), ('豁免价格腿', 'succession_price_leg'), ('方向相反仍恢复', 'opposite_live'),
           ('非当日收盘', 'close_too_early'), ('低于5%仍建', 'tradfi_floor'), ('豁免成交额', 'lowvol'),
           ('仅措辞', 'style_rc'), ('方向不明确', 'price_only'), ('他币关键词仍用', 'token_word_clash'), ('同名代币已核', 'spot_clash'), ('未拉B0仍建', 'b0_stale'), ('撞名已核', 'ds_clash'))


def log_waivers(a, act, tid):
    n = note_of(a)
    for w, chk in WAIVERS:
        if w in n:
            hit(chk, '豁免', act, tid, a.rc)
    if getattr(a, 'force_system_edit', False):
        hit('system_edit', '豁免', act, tid, a.rc)


# 批量预检(11-10 架构 review):`topic.py check <文件>` 逐条以 TOPIC_COLLECT=1 + --dry 跑——拦截不退出、攒起来一次列全,
#   不进 actions-rejected(那是「真写时被拦」的留痕,要逐条处理),检查计数照记(动作列带「预检:」)。
#   由来:近 14 天工具拦截 75 次,每次只报第一处、改完再撞下一处;标题长度/涨跌幅/撤因码这类一条命令常连撞两三次。
COLLECT = [] if os.environ.get('TOPIC_COLLECT') else None


def _collect_exit():
    for m in COLLECT:
        print(f'🚨 拦截:{m}')
    sys.exit(1)


def block(msg, act, tid, rc, check='未命名', fatal=False):
    """topic.py 自己的预检拦截也进拒写留痕——都是「工具拦下的错」。check=检查名(或名单),进 check-hits.tsv。
    fatal=True:这一处不过后面的检查没法跑(关键词格式、找不到题),预检模式下也当场结束。"""
    if COLLECT is not None:
        for c in (check if isinstance(check, (list, tuple)) else [check]):
            hit(c, '拦', '预检:' + act, tid, rc)
        COLLECT.append(msg)
        if fatal:
            _collect_exit()
        return
    for c in (check if isinstance(check, (list, tuple)) else [check]):
        hit(c, '拦', act, tid, rc)
    _append('REJ', 'actions-rejected.tsv', [_now(), msg, act, tid, rc])
    print(f'🚨 拦截:{msg}')
    sys.exit(1)


def la(args, check=False, b0=None):
    env = dict(os.environ)
    if check:
        env['LA_CHECK'] = '1'
    if b0:
        env['B0JSON'] = b0
    if COLLECT is not None:
        env['REJ'] = '/dev/null'
    r = subprocess.run([LA] + [str(x) for x in args], capture_output=True, text=True, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def _la_fail(out):
    if COLLECT is not None:
        COLLECT.append('记账闸:' + ' '.join(l.strip() for l in out.splitlines() if l.strip())[:400])
        return
    print(out)
    sys.exit(1)


def note_of(a):
    """10-26 复盘(10000003265):各道检查只读 --note,用 -T 三段写备注时读到空串——撤重复题被误拦,
    v3.7.18 成交额单项闸反倒会被绕过。落账走 -T 就以 -T 为准(与 la_args 同一取法)。"""
    return a.T if getattr(a, 'T', None) else (getattr(a, 'note', '') or '')


def la_args(act, tid, rc, a, delta=None, note_prefix=''):
    out = [act, tid, rc]
    if a.T:
        out += ['-T', a.T]
    else:
        out += [note_prefix + a.note]
    if delta is not None:
        out.append(delta)
    return out


def norm_kw(k):
    if k is None:
        return None
    if '[' in k or '"' in k:
        # 11-06 复盘:传了 JSON 数组被拦(第 1 次)——合法 JSON 字符串数组直接转成逗号串,别的带括号/引号照拦
        try:
            arr = json.loads(k)
        except Exception:
            return False
        if isinstance(arr, list) and arr and all(isinstance(x, str) and x.strip() and '"' not in x for x in arr):
            return [x.strip() for x in arr]
        return False
    parts = [x.strip() for x in re.split(r'[,，]', k) if x.strip()]
    return parts


def tmp_b0(topic):
    """把这道题的当前态写进临时 B0JSON,喂 log-action 的过期闸/meme 闸(题若是本轮 b0 拉取后才建的,b0-latest 里没有)。"""
    if not topic:
        return None
    f = tempfile.NamedTemporaryFile('w', delete=False, suffix='.json', encoding='utf-8')
    json.dump([topic], f, ensure_ascii=False)
    f.close()
    return f.name


def pending_hint(status, tid):
    """10-28 复盘(13624/13617,修过 7 次仍重犯):update 不改 status,待审题(1/2)改完仍停在审核中。update 后当场提示。"""
    if status in (1, 2, '1', '2'):
        return (f'⚠️ {tid} 仍是 status={status}(待审):update 不会上线——发布三问过了就 '
                f'$ ~/.trend-scout/topic.py publish --id {tid},否则 cull;收尾待审必须 0')
    return None


def spot_clash(kws, spot=None):
    """10-28 复盘(下游错标 ×3:ULBI→ENS、INOD→INO、HOOD→ROBINHOOD):tradfi 题关键词与加密现货代币同名,下游会挂到代币。
    只比 okx/币安「现货」币种(永续里混有 NVDA/HOOD 等股票合约,比永续会误报一片)。返回同名的关键词列表。"""
    if spot is None:
        try:
            import token_exist
            sets = token_exist._exchange_sets(token_exist._load_cache())
            spot = set().union(*[sets.get(k) or set() for k in ('okx_spot', 'bn_spot')])
        except Exception:
            return []
    return [k for k in kws or [] if re.fullmatch(r'[A-Za-z0-9]{2,10}', k) and k.upper() in spot]


def token_word_clash(kws, spot=None):
    """11-04 复盘(13826 CLANKER 挂到 MASK):crypto 题关键词里多词名称的首词恰是另一个现货代币(Mask Network→MASK),
    且该代币本身不在关键词里 → 下游会把题挂到那个币。历史回放 2850 道 crypto 题命中 7 道(XRP Ledger、BNB Chain 等)。"""
    if spot is None:
        try:
            import token_exist
            sets = token_exist._exchange_sets(token_exist._load_cache())
            spot = set().union(*[sets.get(k) or set() for k in ('okx_spot', 'bn_spot')])
        except Exception:
            return []
    ks = list(kws or [])
    ups = {k.upper() for k in ks}
    return [k for k in ks[1:] if ' ' in k and k.split()[0].upper() in spot and k.split()[0].upper() not in ups]


def _hour():
    h = os.environ.get('TOPIC_NOW_HOUR')
    import datetime
    return int(h) if h else datetime.datetime.now().hour


def lint_and_pct(title, domain, pcts, act, tid, rc):
    import lint, pct
    res = lint.lint_title(title, domain)
    for lv, gate, msg, ver in res:
        if lv in ('FAIL', 'WARN'):
            print(f'  {lv} {gate}: {msg} ({ver})')
    fails = [g for lv, g, _, _ in res if lv == 'FAIL']
    if fails:
        _ln = f'(现 {len(title)} 字,上限 30,至少删 {len(title) - 30} 字)' if '标题长度' in fails and len(title) > 30 else ''
        block(f'标题闸FAIL({"/".join(fails)}):{title}{_ln}', act, tid, rc, check=['lint:' + g for g in fails])
    import lint as _l
    _cm = _l.cross_midnight_word(title, _hour())
    if _cm:
        block(_cm + f':{title}', act, tid, rc, check='cross_midnight_word')
    _rt = _l.ratio_like_time(title)
    if _rt:
        block(_rt + f':{title}', act, tid, rc, check='ratio_like_time')
    if pcts:
        # 11-06 复盘:一个 --pct 里塞了两组「费半ETF=a/b,纳指100=c/d」被当成一个标签——按「,标签=」拆开
        pcts = [q.strip() for p0 in pcts for q in re.split(r'[,，](?=[^,，=]+=)', p0) if q.strip()]
        r = pct.check(title, pcts)
        for lv, msg in r:
            print(f'  {lv} 涨跌幅: {msg}')
        bad = [m for lv, m in r if lv == 'FAIL']
        if bad:
            block('涨跌幅不符:' + ';'.join(bad), act, tid, rc, check='pct_check')


def ds_clash(title, kws, note=''):
    """撞名表(11-10 架构 review;downstream.py 错标时自动登记):关键词里有上次把下游带偏的词 → 拦;只在标题里出现 → 只提示。
    由来:建题前的 spot_clash 只比「关键词与现货代币完全同名」,而实际撞的是单词/前缀——Rocket Lab→LAB(11-05、11-10)、
    LITE→LIT(11-02、11-09)、FERG→FER(11-10),每次都是上线后回读才发现。确认无碍在 --note 写「撞名已核:<理由>」。"""
    if '撞名已核' in (note or ''):
        return None
    try:
        import downstream as _ds
        hits = _ds.clash_hits(title, kws)
    except Exception:
        return None
    for trig, wrong, where, src, day in hits:
        if where == '标题':
            print(f'  ⚠️ 撞名提示:标题里的「{trig}」曾把下游带到 {wrong}(见题 {src})——建完看下游回读,挂错就改标题用代码消歧')
    kh = [(trig, wrong, src, day) for trig, wrong, where, src, day in hits if where == '关键词']
    if kh:
        return ('关键词' + '、'.join(f'「{trig}」曾被下游挂到 {wrong}(见题 {src})' for trig, wrong, src, day in kh)
                + '——换掉这个关键词(用中文公司名或不会撞的全称);确认这次不会挂错在 --note 写「撞名已核:<理由>」')
    return None


def check_tags(tags):
    out = []
    for t in tags or []:
        i = str((t or {}).get('id', ''))
        if len(i) >= 7:
            out.append(f'tag {i} 是 ≥7 位占位 ID(系统垃圾),改:topic.py update --id <id> --rc tag修正 --tags \'[]\'')
    return out


def readback(c, tid, want):
    t = c.get(tid)
    if not t:
        return [f'回读不到 {tid}']
    bad = []
    for k, v in want.items():
        got = t.get(k)
        if k == 'keywords':
            got = ','.join(norm_kw(got or '') or [])
            v = ','.join(v)
        if str(got).strip() != str(v).strip():
            bad.append(f'{k}: 写入「{v}」回读「{got}」')
    return bad


def downstream(ids):
    if os.environ.get('TOPIC_NO_DOWNSTREAM'):
        return
    try:
        import downstream as ds
        print('  ↳ 下游回读:')
        ds.run([str(i) for i in ids])
    except SystemExit as e:
        print(f'  ⚠️ 下游回读失败(不影响本次写入,收尾再跑 downstream.py): {e}')
    except Exception as e:
        print(f'  ⚠️ 下游回读失败(不影响本次写入,收尾再跑 downstream.py): {type(e).__name__}: {e}')


# ── v3.7.1 盘中题自动挂收盘复查(源 gates 建题核实 ②a:v2.9.46 `2634` 漏挂复查,盘中 +0.8% 收盘抹平没被当晚抓到)
ASIA_KR_JP_TW = re.compile(r'KOSPI|KOSDAQ|\.KS\b|\.KQ\b|日经|\.T\b|东证|台股|台积电|\.TW\b|韩股|日股|三星|海力士|\.AX\b|澳股|澳交所')   # 10-23 复盘:Zip(ZIP.AX)被挂到次日;澳股 13:00 收盘随 14:40 轮
ASIA_HK_CN = re.compile(r'恒生|恒指|港股|\.HK\b|A股|沪指|深成|\.SS\b|\.SZ\b|\.SH\b')   # 10-23 复盘:宇树(688836.SH)漏认,长桥写法是 .SH
EU = re.compile(r'欧股|\.AS\b|\.PA\b|\.DE\b|\.L\b|\.ST\b|\.SW\b|\.MI\b|\.MC\b|\.CO\b|\.HE\b|\.OL\b|斯托克|DAX|阿姆斯特丹|伦敦')   # 10-23 补北欧/瑞士/意西


def us_close_cst(now=None):
    """11-07 周报通读:美股 16:00 ET 收盘折成北京时间——冬令时 05:00、夏令时 04:00(原先写死 04:00)。"""
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        d = (now or _dt.datetime.now()).date()
        et = _dt.datetime(d.year, d.month, d.day, 16, 0, tzinfo=ZoneInfo('America/New_York'))
        return (et.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%H:%M'))
    except Exception:
        return '04:00'


def review_slot(title, keywords, now=None):
    """盘中题的收盘复查时点(按排班轮次):韩日台→当日 14:40;港/A→当日 17:30(11-07 用户由 16:30 改);欧股/美股→收盘后的下一个 09:40。"""
    import datetime as _dt
    now = now or _dt.datetime.now()
    hay = f'{title} {keywords}'
    def at(day, hm):
        h, m = map(int, hm.split(':'))
        return day.replace(hour=h, minute=m, second=0, microsecond=0)
    if ASIA_KR_JP_TW.search(hay):
        t = at(now, '14:40')
    elif ASIA_HK_CN.search(hay):
        t = at(now, '17:30')
    else:
        t = at(now, '09:40')                                  # 美股收盘(冬令时 05:00/夏令时 04:00 CST)、欧股 23:30 收盘 → 下一个 09:40
        if now >= at(now, us_close_cst(now)) or EU.search(hay):
            t = t + _dt.timedelta(days=1)
    if t <= now:
        t = t + _dt.timedelta(days=1)
    return t


def _fmt_ms(ms):
    import datetime as _dt
    return _dt.datetime.fromtimestamp(int(ms) / 1000).strftime('%m-%d %H:%M')


def auto_review(tid, title, keywords, domain, closed_ms=None):
    if domain != 'tradfi' or '盘中' not in (title or '') or os.environ.get('TOPIC_NO_REVIEW'):
        return
    ev = os.environ.get('EVENT_WATCH') or os.path.join(D, 'event-watch.tsv')
    try:
        for l in open(ev, encoding='utf-8'):
            x = l.rstrip('\n').split('\t')
            if len(x) >= 7 and x[6] in ('pending', 'review', 'tbd') and str(tid) in x[5].split(','):
                # 10-15 retro:时点已到的待关事件(往往正是本次写操作要关的那条)不算「已有复查」,否则改成盘中价后没人复查收盘
                try:
                    import datetime as _dt
                    if _dt.datetime.strptime(f'{x[0]} {x[3]}', '%Y-%m-%d %H:%M') <= _dt.datetime.now():
                        continue
                except ValueError:
                    pass
                print(f'  ↳ 已有未关的复查事件「{x[2]}」,不重复挂')
                return
    except FileNotFoundError:
        pass
    t = review_slot(title, keywords)
    r = subprocess.run([os.path.join(HERE, 'event.sh'), 'add', t.strftime('%Y-%m-%d'), 'review',
                        f'{tid}盘中题收盘定稿', t.strftime('%H:%M'), str(tid),
                        f'topic.py 自动挂(v3.7.1):盘中价建/改题,按收盘改「收涨/收跌」或撤;系统 tradfi 窗口内只撤不改'
                        + (f';⚠️有效期截止 {_fmt_ms(closed_ms)},过期就不能改数字——这一项先办' if closed_ms else '')],
                       capture_output=True, text=True)
    print('  ↳ ' + (r.stdout + r.stderr).strip().replace('\n', ' '))


def write_and_log(c, tool, args, log_args, b0, act, tid, rc):
    # 10-30 retro:3377/3378 收盘定稿看板已生效、台账无行、终端无回显——c.call 抛异常(超时/回包坏)时服务端可能已写,
    # 旧版不接异常,traceback 被调用方 grep 过滤吞掉,也不进 actions-unlogged。改为:接住→记 unlogged→响亮报出
    try:
        r = c.call(tool, args)
    except Exception as e:
        _append('UNLOGGED', 'actions-unlogged.tsv',
                [_now(), f'写看板调用异常,看板可能已生效:{type(e).__name__}:{str(e)[:100]}', log_args[0], log_args[1], log_args[2]] + log_args[3:])
        print(f'🚨 拦截:写看板调用异常({type(e).__name__}),看板可能已生效但未落账——已记 actions-unlogged.tsv,checklist verify 不放行;'
              f'先 topic.py get --id {tid if tid != "-" else "<新id>"} 回读,已生效就 log-action.sh {" ".join(log_args[:3])} … 补记')
        sys.exit(5)
    if not r.get('success'):
        print(f'🚨 看板写入失败,未落账: {json.dumps(r, ensure_ascii=False)[:200]}')
        sys.exit(3)
    if log_args[1] == '-':
        log_args = [log_args[0], str(r.get('id'))] + log_args[2:]
    rc_, out = la(log_args, b0=b0)
    print('  ' + out.replace('\n', '\n  '))
    if rc_ != 0:
        _append('UNLOGGED', 'actions-unlogged.tsv',
                [_now(), f'看板已写、落账失败:{out[:120]}', log_args[0], log_args[1], log_args[2]] + log_args[3:])
        print(f'🚨 看板已写入但落账失败——已记 actions-unlogged.tsv,checklist verify 不放行;按提示改备注后补记:'
              f'log-action.sh {" ".join(log_args[:3])} …')
        sys.exit(4)
    return r


def b0_stale(note='', now=None, d=None):
    """11-07 用户定(Q15=A):「本轮没扫过看板不得建题」(gates 去重树)做进工具——建题前必须有本轮的 b0-audit --fetch。
    轮内(current-checklist.tsv 在)看 b0-latest.json 的 fetched_at 是否晚于本轮开跑;轮外看是否在 2 小时内。
    返回拦截提示或 None。确属例外在 --note 写「未拉B0仍建:<理由>」。"""
    import datetime as _dt
    if '未拉B0仍建' in (note or '') or os.environ.get('TS_NO_B0CHECK'):
        return None
    d = d or os.path.dirname(os.path.abspath(__file__))
    fp = os.path.join(d, 'b0-latest.json')
    if not os.path.exists(fp):
        return None          # 无快照文件=判不了(本机恒有;Evose 用例夹具没有),不拦
    try:
        fa = _dt.datetime.strptime(json.load(open(fp))['fetched_at'][:19], '%Y-%m-%dT%H:%M:%S')
    except Exception:
        # Evose 的 b0-merge 写 b0-latest.json 不带 fetched_at——退回文件修改时间
        fa = _dt.datetime.fromtimestamp(os.path.getmtime(fp))
    now = now or _dt.datetime.now()
    ck = os.path.join(d, 'current-checklist.tsv')
    if os.path.exists(ck):
        m = re.search(r'ts=(\d+)', open(ck).readline())
        if m and fa < _dt.datetime.fromtimestamp(int(m.group(1)) / 1000):
            return f'本轮({_dt.datetime.fromtimestamp(int(m.group(1))/1000):%H:%M} 开跑)还没跑 b0-audit --fetch(最近一次 {fa:%m-%d %H:%M})——先盘池子再补题(11-07 Q15;去重基准是处置后的池子)'
        return None
    if now - fa > _dt.timedelta(hours=2):
        return f'b0-latest.json 是 {fa:%m-%d %H:%M} 拉的,已超 2 小时——先跑 b0-audit.sh --fetch 再建题(11-07 Q15)'
    return None


def cards(act, title=None, domain=None, closed_ms=None, new_title=False, ref=''):
    """v3.7.33 判据卡试跑:在写之前把相关闸的判据打印出来(同卡 60 分钟去重)。预检子进程里只报卡名,由 check 汇总后打一次。
    ref=触发它的题号(改/撤)或标题(建题时题号还没有),记进 card-usage.tsv 供逐条判结算对证据(11-10)。
    card.py 或 cards.md 不在(沙箱/旧规则包)时静默,不影响写题。"""
    try:
        import card
        names = card.pick(act, title, domain, closed_ms=closed_ms, new_title=new_title)
        if COLLECT is not None:
            if names:
                print('CARDS-PICK:' + ','.join(names) + '|' + str(ref).replace('|', ' ').replace(';', ' '))
            return
        card.emit(names, trigger=act, ref=ref)
    except Exception:
        pass


def card_link(tid, title):
    try:
        import card
        card.link(tid, title)
    except Exception:
        pass


def cmd_create(a, c):
    cards('create', a.title, a.domain, ref=a.title)
    _b0 = b0_stale(note_of(a))
    if _b0:
        block(_b0, 'create', '-', a.rc, check='b0_stale')
    if a.domain not in ('crypto', 'tradfi'):
        block(f'domain 必须是 crypto/tradfi,收到 {a.domain}', 'create', '-', a.rc, check='domain', fatal=True)
    kw = norm_kw(a.keywords)
    if kw is False:
        block('keywords 必须是逗号分隔字符串,不能带 [ 或 "(数组会被存成字面量,打标必 miss)', 'create', '-', a.rc, check='keywords_format', fatal=True)
    if not kw or len(kw) > 4:
        block(f'keywords 须 1~4 个(主标的 ticker+名+核心概念),收到 {len(kw or [])} 个', 'create', '-', a.rc, check='keywords_count', fatal=True)
    lint_and_pct(a.title, a.domain, a.pct, 'create', '-', a.rc)
    if a.domain == 'crypto':
        import pct as _pc
        _bt = _pc.bn_title_mismatch(a.title, kw)
        if _bt:
            block(_bt, 'create', '-', a.rc, check='bn_title_mismatch')
    if a.domain == 'crypto' and '他币关键词仍用' not in note_of(a):
        _tw = token_word_clash(kw)
        if _tw:
            block(f'关键词{_tw}的首词是另一个代币,下游会把题挂过去(11-04 CLANKER→MASK)——去掉该关键词;确需保留在 --note 写「他币关键词仍用:<理由>」', 'create', '-', a.rc, check='token_word_clash')
    if a.domain == 'tradfi':
        _sc = spot_clash(kw)
        if _sc and '同名代币已核' not in note_of(a):
            # 11-05:原来只打 ⚠️ 提示,被主进程 grep 过滤掉,STX/FIS/TREE 三道照样挂到代币——改成拦
            block(f'关键词{_sc}与加密现货代币同名,下游会把题挂到代币(10-28 ULBI→ENS、11-05 STX/FIS/TREE)——'
                  f'把 ticker 换成公司名(如 Seagate),或确认下游不会挂错后在 --note 写「同名代币已核:<理由>」', 'create', '-', a.rc, check='spot_clash')
    _dc = ds_clash(a.title, kw, note_of(a))
    if _dc:
        block(_dc, 'create', '-', a.rc, check='ds_clash')
    _po = price_only(a.title, note_of(a))
    if _po:
        block(_po, 'create', '-', a.rc, check='price_only')
    _lv = lowvol(a.rc, a.domain, a.title, note_of(a))
    if _lv:
        block(_lv, 'create', '-', a.rc, check='lowvol')
    _ca = crypto_amp(a.rc, a.domain, a.title, note_of(a), a.keywords)
    if _ca:
        block(_ca, 'create', '-', a.rc, check='crypto_amp')
    _tf = tradfi_floor(a.domain, a.title, note_of(a), a.keywords)
    if _tf:
        block(_tf, 'create', '-', a.rc, check='tradfi_floor')
    _sl = sector_lead(a.rc, a.title)
    if _sl:
        block(_sl, 'create', '-', a.rc, check='sector_lead')
    _ae = asia_earn_time(a.domain, a.title, note_of(a), kw)
    if _ae:
        block(_ae, 'create', '-', a.rc, check='asia_earn_time')
    if a.domain == 'tradfi':
        _ce = close_too_early(a.title, note_of(a), kw)
        if _ce:
            block(_ce, 'create', '-', a.rc, check='close_too_early')
    # 11-09 用户定(v3.7.30):排序权重四档,判档单一定义=weight.py/weights.json;--tier 人工指定须带 --tier-why
    import weight as _wt
    if a.tier:
        if a.tier not in ('A', 'B', 'C', 'D') or not (a.tier_why or '').strip():
            block('--tier 只能是 A/B/C/D,且必须带 --tier-why 写人工定档理由(如「大热点闸触发」)', 'create', '-', a.rc, check='tier_override', fatal=True)
        _tier, _w, _why = a.tier, _wt.tier_weight(a.tier), '人工:' + a.tier_why.strip()
    else:
        _tier, _w, _why = _wt.classify(a.domain, a.title, ','.join(kw), note_of(a))
    _wtag = f'｜权重:{_tier}{_w:+g}({_why})'
    if a.T:
        a.T = a.T + _wtag
    else:
        a.note = (a.note or '') + _wtag
    print(f'  ⚖️ 权重档 {_tier} {_w:+g}({_why})' + ('' if a.tier else '——判错用 --tier X --tier-why 改'))
    delta = f'-→{a.title}'
    # 11-05 用户定:建题与自推上线合成一行——create 行备注尾带 ledger.PUB_SUFFIX,不再另写「状态修正·建题后推」行
    #   (近 7 天 163 行改题里 114 行是这个自推行,复审员要核的行数虚高约 20%)。上线调用失败则记 unlogged、退出不放行。
    if not a.no_publish:
        import ledger as _lg
        if a.T:
            a.T = a.T + _lg.PUB_SUFFIX
        else:
            a.note = (a.note or '') + _lg.PUB_SUFFIX
    rc_, out = la(la_args('create', '-', a.rc, a, delta), check=True)
    if rc_ != 0:
        _la_fail(out)
    if a.dry:
        print(f'[dry] 将建 {a.domain}「{a.title}」 keywords={",".join(kw)}' + ('' if a.no_publish else ' 并推上线'))
        return
    args = {'title': a.title, 'keywords': ','.join(kw), 'domain': a.domain, 'score_weight': _w}
    if a.domain == 'crypto':
        args['topic_type'] = a.topic_type
    r = write_and_log(c, 'create_trending_topic', args, la_args('create', '-', a.rc, a, delta), None, 'create', '-', a.rc)
    tid = str(r['id'])
    log_waivers(a, 'create', tid)
    for w in check_tags(r.get('matched_tags')):
        print('  ⚠️ ' + w)
    status = 2
    if not a.no_publish:
        try:
            pr = c.call('update_trending_topic', {'id': int(tid), 'status': 0})
        except Exception as e:
            pr = {'success': False, 'error': f'{type(e).__name__}:{str(e)[:100]}'}
        if not pr.get('success'):
            _append('UNLOGGED', 'actions-unlogged.tsv',
                    [_now(), f'建题 {tid} 已落账(备注带自推上线标记)但上线调用失败,题可能仍 status=2:{json.dumps(pr, ensure_ascii=False)[:120]}',
                     'update', tid, '状态修正'])
            print(f'🚨 建题 {tid} 已落账但推上线失败——已记 actions-unlogged.tsv,checklist verify 不放行;'
                  f'先 topic.py get --id {tid} 回读,仍是 status=2 就 topic.py publish --id {tid}')
            sys.exit(5)
        status = 0
    # 建题时定的档记账(weight-sync 以此为准,不再按标题重判);人工档 source=manual
    _wt.record(_now(), tid, _tier, 'manual' if a.tier else 'auto', _why)
    bad = readback(c, tid, {'title': a.title, 'status': status, 'keywords': kw})
    _rt = c.get(tid) or {}
    try:
        if abs(float(_rt.get('score_weight')) - float(_w)) > 1e-9:
            bad.append(f'score_weight: 写入「{_w}」回读「{_rt.get("score_weight")}」')
    except (TypeError, ValueError):
        bad.append(f'score_weight: 回读不到(得 {_rt.get("score_weight")!r})')
    for b in bad:
        print('  🚨 回读不一致 ' + b)
    card_link(tid, a.title)
    print(f'✔ 建 {tid} [{a.rc}]「{a.title}」 tags={[t.get("id") for t in r.get("matched_tags") or []]} status={status}')
    auto_review(tid, a.title, ','.join(kw), a.domain, closed_ms=_now() + 24 * 3600 * 1000)
    if not a.no_downstream:
        downstream([tid])
    if bad:
        sys.exit(6)


def _current(c, a):
    t = c.get(a.id)
    if not t:
        block(f'看板上找不到题 {a.id}(按台账建题日+近 7 天逐日查)', 'update', a.id, a.rc, check='topic_missing', fatal=True)
    return t


SCOPE_OK_RC = {'改数字-定稿', '纠错-自纠', 'tag修正', '改样式-命名', '状态修正'}


def out_of_scope(t, rc, note, now_ms=None, new_title=None):
    """10-31 复审(13691/13690):建题已 >8h 的题用「承接更新」整句改写成新事件——绕开了射程闸(>8h 不管)
    与过期题表(数字不改),新事实被塞进旧题。改标题只放行定稿/纠错/命名/tag;预告题的承接(结果晚于 8h 出)放行;
    确属例外在备注写「射程外仍改:<理由>」。"""
    if rc in SCOPE_OK_RC or '射程外仍改' in (note or ''):
        return None
    try:
        ts = time.mktime(time.strptime(str(t.get('created_at'))[:19], '%Y-%m-%d %H:%M:%S')) * 1000
    except Exception:
        return None
    age = ((now_ms or _now()) - ts) / 3.6e6
    if age <= 8:
        return None
    # 11-09 复盘(10000003668):gates 闸:时段 ②c 美股开盘后把盘前/夜盘口径换成盘中/收盘口径=同一事件同一交易日换时段,
    #   不是改写成新事件;此前被本闸拦、只能手写「射程外仍改」放行。限 24h 内、旧标题带盘前/夜盘/期货、新标题换成盘中/收盘
    if (rc == '改口径-时段' and new_title and age < 24 and re.search(r'盘前|夜盘|期货', t.get('title') or '')
            and re.search(r'盘中|收涨|收跌|收盘', new_title) and not re.search(r'盘前|夜盘', new_title)):
        return None
    # 11-07 用户定(Q11=B):早间轮(08:00–12:00)把前晚 22:30 以后建的题纳入射程,与 b0-audit ⓪ 隔夜补射程同口径
    import datetime as _dt
    _n = _dt.datetime.fromtimestamp((now_ms or _now()) / 1000)
    if 8 <= _n.hour < 12 and ts >= (_n - _dt.timedelta(days=1)).replace(hour=22, minute=30, second=0, microsecond=0).timestamp() * 1000:
        return None
    if rc == '承接更新':
        import ledger
        if any(str(rid) == str(t.get('id')) and r[3] == '预告题' for _, rid, r in ledger.created()):
            return None
    return (f'{t.get("id")} 建于 {age:.0f}h 前,已出 8h 射程:用「{rc}」改标题=把旧题改写成新事件(10-31 13691)——'
            f'新事实另建新题(承接兑现),旧题按过期题表处置;确属例外在 --note 写「射程外仍改:<理由>」')


def cmd_update(a, c, status=None, act='update'):
    t = _current(c, a)
    new_title = a.title if getattr(a, 'title', None) and a.title != t.get('title') else None
    cards(act, new_title or t.get('title'), t.get('domain'), closed_ms=t.get('closed_ts'), new_title=bool(new_title), ref=a.id)
    delta = f"{t.get('title')}→{new_title}" if new_title else '-'
    kw = norm_kw(getattr(a, 'keywords', None))
    if kw is False:
        block('keywords 必须是逗号分隔字符串,不能带 [ 或 "', act, a.id, a.rc, check='keywords_format', fatal=True)
    if kw is not None and (not kw or len(kw) > 4):
        block(f'keywords 须 1~4 个,收到 {len(kw)} 个', act, a.id, a.rc, check='keywords_count', fatal=True)
    if kw:
        _dc = ds_clash(new_title or t.get('title'), kw, note_of(a))
        if _dc:
            block(_dc, act, a.id, a.rc, check='ds_clash')
    if new_title:
        _os = out_of_scope(t, a.rc, note_of(a), new_title=a.title)
        if _os:
            block(_os, act, a.id, a.rc, check='out_of_scope')
        import ledger
        mine = ledger.created_ids()
        if t.get('domain') == 'tradfi' and str(a.id) not in mine and (t.get('closed_ts') or 0) > _now() \
                and not a.force_system_edit:
            block(f'{a.id} 是系统建 tradfi 题且还在窗口内:改标题会被系统刷回(10-01/10-09 实测)。'
                  f'内容错→topic.py cull;措辞差→不动;确要改加 --force-system-edit', act, a.id, a.rc, check='system_edit')
        lint_and_pct(new_title, t.get('domain', 'crypto'), getattr(a, 'pct', None), act, a.id, a.rc)
        if t.get('domain') == 'tradfi':
            _ce = close_too_early(new_title, note_of(a), kw if kw else [k.strip() for k in (t.get('keywords') or '').split(',')])
            if _ce:
                block(_ce, act, a.id, a.rc, check='close_too_early')
        if t.get('domain') == 'crypto':
            import pct as _pc
            _bt = _pc.bn_title_mismatch(new_title, kw if kw else [k.strip() for k in (t.get('keywords') or '').split(',')])
            if _bt:
                block(_bt, act, a.id, a.rc, check='bn_title_mismatch')
        _po = price_only(new_title, note_of(a))
        if _po:
            block(_po, act, a.id, a.rc, check='price_only')
        _sr = style_rc(a.rc, t.get('title'), new_title, t.get('domain'), note_of(a))
        if _sr:
            block(_sr, act, a.id, a.rc, check='style_rc')
        _ve = vol_only_exempt(note_of(a))
        if _ve:
            block(_ve, act, a.id, a.rc, check='vol_only_exempt')
        # 10-15 retro:「复审挑战·价格腿」重犯 5 次,典型=承接后改成既成事实却没价格反应(3138)。承接更新缺价格腿直接拦;
        # 监管/上架/预告等合法豁免在备注写「豁免价格腿:<理由>」放行
        if a.rc == '承接更新' and '豁免价格腿' not in (note_of(a)):
            import lint
            if any(g == '双要素-缺价格' for _, g, _, _ in lint.lint_title(new_title, t.get('domain', 'crypto'))):
                block(f'承接更新的新标题没有价格腿:{new_title}——补实测价格(--pct),合法豁免在 --note 写「豁免价格腿:<理由>」', act, a.id, a.rc, check='succession_price_leg')
    elif getattr(a, 'pct', None):
        lint_and_pct(t.get('title'), t.get('domain', 'crypto'), a.pct, act, a.id, a.rc)
    b0 = tmp_b0(t)
    try:
        largs = la_args(act, a.id, a.rc, a, delta)
        rc_, out = la(largs, check=True, b0=b0)
        if rc_ != 0:
            _la_fail(out)
        args = {'id': int(a.id)}
        want = {}
        if new_title:
            args['new_title'] = new_title
            want['title'] = new_title
        if status is not None:
            args['status'] = status
            want['status'] = status
        if kw is not None:
            args['keywords'] = ','.join(kw)
            want['keywords'] = kw
        if getattr(a, 'tags', None) is not None:
            json.loads(a.tags)
            args['tags'] = a.tags
        if len(args) == 1:
            if COLLECT is not None:
                COLLECT.append('没有要改的字段(--title/--keywords/--tags)')
                _collect_exit()
            print('🚨 没有要改的字段(--title/--keywords/--tags)')
            sys.exit(1)
        if a.dry:
            print(f'[dry] 将{act} {a.id}: {json.dumps({k: v for k, v in args.items() if k != "id"}, ensure_ascii=False)}  台账 delta={delta}')
            return
        r = write_and_log(c, 'update_trending_topic', args, largs, b0, act, a.id, a.rc)
        log_waivers(a, act, a.id)
    finally:
        if b0:
            os.unlink(b0)
    ch = r.get('changes') or {}
    for w in check_tags(ch.get('auto_matched_tags')):
        print('  ⚠️ ' + w)
    bad = readback(c, a.id, want)
    for b in bad:
        print('  🚨 回读不一致 ' + b)
    print(f'✔ {act} {a.id} [{a.rc}]' + (f' {delta}' if delta != '-' else '') + (f' status={status}' if status is not None else ''))
    if status is None and act == 'update':
        _ph = pending_hint(t.get('status'), a.id)
        if _ph:
            print('  ' + _ph)
    if new_title:
        auto_review(a.id, new_title, t.get('keywords') or '', t.get('domain'), closed_ms=t.get('closed_ts'))
    if not a.no_downstream and (kw is not None or getattr(a, 'tags', None) is not None or act == 'restore'):
        downstream([a.id])
    if bad:
        sys.exit(6)


NEAR_LINE_RC = {'缺诱因-未达线', '已证伪'}


def near_line(rc, domain, note):
    """10-17 复盘(EPIC 13320):24h 读数 +28.6% 距 ±30% 线 1.4pp 未复测就撤,1 分钟后 +32.9% 又恢复。
    撤因是「幅度不够」类时,备注里任一涨跌幅落在准入线 ±3pp 内,备注须写明「复测」(两次读数),否则拦。"""
    if rc not in NEAR_LINE_RC:
        return None
    line = 10.0 if (domain or '') == 'tradfi' else CRYPTO_LINE
    for m in re.finditer(r'(?<![±\d.])([+-]?\d+(?:\.\d+)?)%', note or ''):   # 10-19:不把「±10%」这类阈值写法当读数
        # 10-26 影子跑(10000003270):「远低于 tradfi 10%」是在说门槛,不是读数——门槛写法前缀跳过
        if re.search(r'(tradfi|crypto|准入线?|门槛|阈值|低于|高于|不到|未达|[≥≤<>])\s*$', (note or '')[max(0, m.start() - 8):m.start()]):
            continue
        v = abs(float(m.group(1)))
        if line - 3 <= v < line + 3 and '复测' not in (note or ''):
            return f'读数 {m.group(0)} 落在 ±{line:g}% 准入线 3pp 内:先隔几分钟复测一次,备注写「复测:<两次读数>」再撤(gates 闸:过期题 处置表;10-17 EPIC 撤了又恢复)'
    return None


def recent_block(tid, rows, now_ms, window_ms=600000):
    """10-19 复盘(13349 PAPER):update 被标题闸拦后,同一条命令里的 publish 照样执行,旧标题上线 1 分钟。
    同一题 10 分钟内有被拦的写操作 → publish 先停下,确认那次拦截已处理(再 update 成功)才放。返回拦截原文或 None。"""
    for r in reversed(rows):
        if len(r) >= 4 and r[3] == str(tid) and r[0].isdigit() and now_ms - int(r[0]) < window_ms:
            return r[1]
    return None


VOL_EXEMPT_AMP = float(os.environ.get('TS_VOL_AMP', '50'))   # 11-06 用户定:豁免②单独成立所需 24h 幅度 15%→50%(与纯行情线一致,成交额不再单独构成诱因)


def vol_only_exempt(note):
    """v3.7.18(10-26 用户定「收紧到±15%」):meme 豁免②「24h 成交额>2亿」单独成立时,还须 24h 涨跌 ≥±15%。
    由来:盲审 W42 BAT 涨11%(靠成交额留)用户判撤;同周 IN 涨2.2%、CAP 涨15% 也是只靠成交额留的。
    四查只有成交额 ✓、其余全 ✗ 时,备注里的 24h 读数须有一个 |x|≥15,否则拦(该撤:缺诱因-未达线,四查行成交额记 ✗)。"""
    n = note or ''
    if not re.search(r'四查[:：]\s*幅度✗\s*成交额✓\s*市值关口✗\s*硬事件✗', n):
        return None
    vals = [abs(float(v)) for v in re.findall(r'24h\s*([+-]?\d+(?:\.\d+)?)%', n)]
    if vals and max(vals) >= VOL_EXEMPT_AMP:
        return None
    return (f'meme 豁免②只剩成交额一项成立时须 24h 涨跌 ≥±{VOL_EXEMPT_AMP:g}%(10-26 定15%,11-06 用户定上调到50%):'
            f'备注 24h 读数 {vals or "未写"} 不达 ±{VOL_EXEMPT_AMP:g}%——应按四查全空撤(缺诱因-未达线,成交额格记 ✗ 并注明幅度不足),'
            f'或在备注写出 ≥{VOL_EXEMPT_AMP:g}% 的 24h 实测读数')


def meme_rc(rc, note):
    """10-19 复盘(13335 TRUMP):备注写了四查全空,却记成「缺价格腿」;gates A闸 meme 行四查全空的规范撤因是「缺诱因-未达线」。"""
    if rc == '缺价格腿' and re.search(r'四查[:：]\s*幅度✗\s*成交额✗\s*市值关口✗\s*硬事件✗', note or ''):
        return '备注是 meme 四查全空,规范撤因是「缺诱因-未达线」(gates 闸:A闸 meme 行),不是「缺价格腿」——改 --rc 再撤'
    return None


def meme_rc_fix(rc, note):
    """11-04 复盘(13833 LIT):meme_rc 近 30 天拦 17 次、一次没修——拦下后唯一正确的动作就是换成「缺诱因-未达线」,
    交给工具做:四查全空却记「缺价格腿」时自动改码并打印一行,不再打回重跑。返回(改后 rc, 提示 or None)。"""
    if meme_rc(rc, note):
        return '缺诱因-未达线', '↻ 自动改码:备注是 meme 四查全空,撤因「缺价格腿」→「缺诱因-未达线」(gates 闸:A闸 meme 行;11-04 复盘交给工具)'
    return rc, None


SICHA_LINE = re.compile(r'四查[:：]\s*幅度[✗✓]\s*成交额[✗✓]\s*市值关口[✗✓]\s*硬事件[✗✓]')
SICHA_GUARD = {'缺价格腿', '缺诱因-未达线', '灌水-vanity指标', '灌水-悬念疑问'}   # 与 log-action.sh GUARD 同步


def _meme_24h(sym):
    """撤 meme 题四查①用:返回 (24h 涨跌%, 合约24h成交额亿美元 或 None, 来源) 或 None。币安永续→币安现货→OKX 永续。
    TOPIC_SICHA_X / TOPIC_SICHA_QV 注入(回归用例、离线)。"""
    if os.environ.get('TOPIC_SICHA_X') is not None:
        qv = os.environ.get('TOPIC_SICHA_QV')
        return float(os.environ['TOPIC_SICHA_X']), (float(qv) if qv else None), '注入'
    import pct
    s = sym.upper() + 'USDT'
    try:
        d = pct._curl(f'https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={s}')
        if 'priceChangePercent' in d and pct.stale_min(d) is None:
            return float(d['priceChangePercent']), float(d['quoteVolume']) / 1e8, '币安永续'
        d = pct._curl(f'https://api.binance.com/api/v3/ticker/24hr?symbol={s}')
        if 'priceChangePercent' in d:
            return float(d['priceChangePercent']), None, '币安现货'
        d = pct._curl(f'https://www.okx.com/api/v5/market/ticker?instId={sym.upper()}-USDT-SWAP')
        r = (d.get('data') or [{}])[0]
        if r.get('last') and r.get('open24h') and float(r['open24h']) > 0:
            return (float(r['last']) / float(r['open24h']) - 1) * 100, None, 'OKX永续'
    except Exception:
        pass
    return None


def sicha_auto(t, rc, note, reader=_meme_24h):
    """11-05 用户定「交给工具」:撤 meme 题四查行近 30 天拦 18 次、12 道补完照撤——前三格工具算,只有硬事件人判。
    返回 (动作, 内容):('skip',None) 不适用;('block',提示) 拦;('fill',四查行) 工具写好的四查行(四格全 ✗)。
    ①幅度:实测 24h ≥±50%(CRYPTO_LINE,11-06 由30%上调) 记 ✓;②成交额、③市值关口按题面判(gates A闸 meme 行):题面没主张记 ✗,主张了才核;
    ②单独成立还须 24h ≥±15%。④硬事件:备注写「硬事件✗」才算人判过,写「硬事件✓」=该留。"""
    n = note or ''
    if rc not in SICHA_GUARD or SICHA_LINE.search(n) or re.search(r'重复|证伪|事实错误', n):
        return 'skip', None
    try:
        import lint, token_exist
        if not lint.meme_scope(t, token_exist.exists):
            return 'skip', None
    except Exception:
        return 'skip', None
    title = t.get('title') or ''
    kws = [k.strip() for k in re.split(r'[,，]', t.get('keywords') or '') if k.strip()]
    sym = next((k for k in kws if re.fullmatch(r'[A-Za-z0-9]{2,12}', k)), None) or (re.findall(r'\b[A-Z][A-Z0-9]{1,11}\b', title) or [None])[0]
    got = reader(sym) if sym else None
    if got is None:
        return 'block', f'meme 四查①幅度取不到数({sym or "认不出代号"}:币安永续/现货、OKX 永续都没有)——人工实测后自己写四查行'
    x, qv, src = got
    amp = abs(x) >= CRYPTO_LINE
    m = re.search(r'成交额?\s*([\d.]+)\s*亿', title)
    vol = bool(m and float(m.group(1)) > 2 and qv is not None and qv > 2) if ('成交' in title or '来源主张成交额' in n) else False
    if vol and not amp and abs(x) < VOL_EXEMPT_AMP:
        vol = False
    if re.search(r'市值[^，,]{0,8}(突破|站上|升破|涨破|首破)', title):
        return 'block', '题面主张了市值关口,四查③须人核「本轮首次突破」——人工写四查行'
    if amp or vol:
        return 'block', f'四查{"①幅度✓" if amp else ""}{"②成交额✓" if vol else ""}({src} 24h {x:+.1f}%{f"、合约成交{qv:.1f}亿" if qv is not None else ""})——豁免成立,这道题该留,不撤'
    if '硬事件✓' in n:
        return 'block', '备注写了硬事件✓——有硬事件该留,不撤'
    if '硬事件✗' not in n:
        return 'block', (f'工具已算前三格:幅度✗({src} 24h {x:+.1f}%) 成交额✗(题面未主张或未达线) 市值关口✗(题面未主张);'
                         '硬事件只能人判——确认没有被盗/上大所/大机构合作/官方重大事件,在 --note 加「硬事件✗」重跑,工具自动写四查行')
    return 'fill', f'四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗(工具算前三格:{src} 24h {x:+.1f}%,题面未主张成交额与市值关口;硬事件人判) '


def dup_target(rc, note, self_id, getter):
    """10-21 复盘(10000003190):以「重复-同标的」撤,备注引用的留存题 3186 却在同一轮先被我撤了——没有留存题就不叫重复。
    备注须写留存题 id;引用的 id 都查得到且都不在线(status≠0)→拦,提示换真因码。查不到的 id(超 7 天)不拦。"""
    if rc != '重复-同标的':
        return None
    ids = [i for i in re.findall(r'(?<!\d)(1000000\d{4}|1\d{4})(?!\d)', note or '') if i != str(self_id)]
    if not ids:
        return '「重复-同标的」须在备注写明留存的那条题 id(重复的对象是谁)'
    seen = []
    for i in dict.fromkeys(ids):
        try:
            t = getter(int(i))
        except Exception:
            t = None
        if not t:
            return None
        if t.get('status') == 0:
            return None
        seen.append(i)
    return (f'备注引用的留存题 {",".join(seen)} 都已不在线——没有留存题就不是重复;按真因换码'
            f'(诱因对不上=归因-借源造因,诱因只是复述价格=归因-伪诱因,数字被推翻=事实错误-数字,未过线=缺诱因-未达线)')


def _ts(x):
    try:
        return time.mktime(time.strptime(str(x)[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError):
        return None


def cross_day_dup(rc, note, t, getter, gap_h=16):
    """10-21／10-22 复盘(13357 AGT、13358 ARIA 两天被 Evose 以「重复-同标的」撤了两次):备注引用的留存题 13427/13426 是隔天的新一段行情、
    方向相同。过期题处置表:与同一天的题重复才撤;跨交易日同标的、方向一致的两条并存,方向相反撤老题。dup_target 只查留存题在不在线,管不到这种。
    「同一交易日」按两题建题时刻相隔 <16 小时算:单个交易时段不超过 8 小时、相邻两个时段相隔约 24 小时,16 小时把两者分开;
    盘前题与同一时段的收盘题相隔约 12 小时,仍算同一天。备注引用的在线留存题里只要有一条与本题同一天、或方向不同／看不出方向就不拦;
    全部是隔天且同向才拦。查不到的 id 不拦(同 dup_target),不在线的交给 dup_target。"""
    if rc != '重复-同标的' or not t:
        return None
    me, t0 = _dir(t.get('title')), _ts(t.get('created_at'))
    if not me or t0 is None:
        return None
    ids = [i for i in re.findall(r'(?<!\d)(1000000\d{4}|1\d{4})(?!\d)', note or '') if i != str(t.get('id'))]
    hits = []
    for i in dict.fromkeys(ids):
        try:
            o = getter(int(i))
        except Exception:
            o = None
        if not o:
            return None
        if o.get('status') != 0:
            continue
        t1 = _ts(o.get('created_at'))
        if t1 is None or abs(t1 - t0) < gap_h * 3600 or _dir(o.get('title')) != me:
            return None
        hits.append(f'{i}(相隔{abs(t1 - t0) / 3600:.0f}小时)')
    if not hits:
        return None
    return (f'备注引用的留存题 {"、".join(hits)} 与本题不是同一交易日、方向相同——过期题处置表:跨交易日同标的、方向一致的两条并存,不算重复'
            f'(10-21／10-22 13357、13358 两次误撤)。本题确有错就按真因换码(事实错误-数字/反转错向/归因-借源造因),否则留着')


def _dir(title):
    up, dn = bool(re.search(r'涨|走高|飙', title or '')), bool(re.search(r'跌|走低|下挫', title or ''))
    return 1 if up and not dn else (-1 if dn and not up else 0)


# 10-26 复盘(时效口径第 4 次):建 3264「WTI盘中跌」后漏撤过期反向题 3262「布油收涨」——两题关键词不重合
#   (WTI vs Brent),按字母关键词比对认不出是同一品种。品种族:同族任一词出现在标题/关键词即算同标的。
FAMILY = [('wti', 'brent', 'cl=f', '布油', '原油', '油价', '美油'), ('xau', 'xaut', 'paxg', 'gold', '黄金', '金价')]


def _kw(x):
    return {k.strip().lower() for k in re.split(r'[,，]', x.get('keywords') or '') if re.search(r'[A-Za-z]', k) and not re.search(r'[\u4e00-\u9fff]', k)}


# 11-12 用户令修:建 10000003767「台股收跌2.6%」没提示撤 10000003739「台股加权指数收涨3.6%」——两题关键词全是中文
#   (台股/台湾加权指数),_kw 只认含字母的词,FAMILY 又没有指数族。指数族单一定义在 coverage.IDX(对账线同一张表),
#   这里只去掉常作个股前缀的泛词(「剑桥科技港股收涨」「XX日股跌」会被误当成恒指/日经)。
IDX_BROAD = {'港股', '日股', '韩股'}
_IDX_FAM = None


def _idx_family():
    global _IDX_FAM
    if _IDX_FAM is None:
        try:
            import importlib.util as _u
            _s = _u.spec_from_file_location('_cov', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coverage.py'))
            _c = _u.module_from_spec(_s); _s.loader.exec_module(_c)
            _IDX_FAM = [tuple({k.lower().lstrip('^')} | {w.lower() for w in ws if w not in IDX_BROAD}) for k, (_, ws) in _c.IDX.items()]
        except Exception:
            _IDX_FAM = []
    return _IDX_FAM


def _fam(x):
    s = ((x.get('title') or '') + ',' + (x.get('keywords') or '')).lower()
    toks = set(re.findall(r'[a-z][a-z0-9=]*', s))
    return {i for i, g in enumerate(FAMILY + _idx_family())
            if any((w in toks) if re.fullmatch(r'[a-z][a-z0-9=]*', w) else (w in s) for w in g)}


def _same_asset(t, o):
    return bool(_kw(t) & _kw(o) or _fam(t) & _fam(o))


def opposite_after_create(t, topics):
    """建题后列出同标的/同品种族、方向相反的在线题(过期题处置表:新建反向题须撤方向相反的老题)。只提示不拦——撤哪条要人判。"""
    d = _dir(t.get('title'))
    if not d:
        return []
    return [o for o in topics or [] if str(o.get('id')) != str(t.get('id')) and o.get('status') == 0
            and _same_asset(t, o) and _dir(o.get('title')) == -d]


def opposite_live(t, topics, note):
    """10-21 复盘(10000003181):回滚他人撤题时把过期题闸记成「跨日一律并存」,原文是「方向一致并存、方向相反撤老题」。
    restore 前查看板:同标的(共享含字母的关键词)且方向相反的在线题存在 → 拦。备注写「方向相反仍恢复:<理由>」放行。"""
    if '方向相反仍恢复' in (note or ''):
        return None
    d = _dir(t.get('title'))
    if not d:
        return None
    for o in topics or []:
        if str(o.get('id')) == str(t.get('id')) or o.get('status') != 0:
            continue
        if _same_asset(t, o) and _dir(o.get('title')) == -d:
            return (f'同标的在线题 {o["id"]}「{o.get("title")}」方向相反——过期题闸:跨日同标的方向一致才并存,方向相反撤老题;'
                    f'确要恢复在 --note 写「方向相反仍恢复:<理由>」')
    return None


def price_only(title, note):
    """v3.7.10(10-21 用户定):明确利好/利空公告要写涨跌和因果。标题只写「报X美元」不写涨跌,而备注里记着 24h 涨跌 ≥5%,
    说明有价格动作被藏起来了——要么按 gates 归因三问①a 写涨跌,要么在备注写「方向不明确:<理由>」(产品更新/人事/商业模式调整/预告等)。"""
    t, n = title or '', note or ''
    if not re.search(r'报\s*\d', t) or re.search(r'\d+(?:\.\d+)?\s*%', t) or '方向不明确' in n:
        return None
    for m in re.finditer(r'24\s*(?:h|小时)\s*([+-]\d+(?:\.\d+)?)\s*%', n):
        if abs(float(m.group(1))) >= 5:
            return (f'标题只写现价,备注里 24h {m.group(1)}% ——明确利好/利空公告要写涨跌和因果(gates 归因三问①a:明确清单/同向/公告后/≥5%且超BTC 5pp);'
                    f'不属明确清单的在 --note 写「方向不明确:<理由>」')
    return None


CLOSE_MKT = [  # (识别正则, 收盘 UTC 时:分)——11-02 retro:A股长桥行情延迟约15分钟,14:5x 读到 06:36 UTC 盘中价被当收盘写入 3432
    (re.compile(r'沪深|创业板|A股|上证|深证|\.SH|\.SZ|000300|399006'), (7, 0)),
    (re.compile(r'恒指|恒生|港股|\.HK|HSI'), (8, 10)),
    (re.compile(r'日经|东证|\.T\b|N225|铠侠|285A'), (6, 30)),
    (re.compile(r'KOSPI|\.KS|KS11|韩股'), (6, 30)),
]


def close_too_early(title, note, kws, now=None):
    """标题写「收涨/收跌/收于」或备注写「<今天MM-DD>收盘」,而对应市场今天还没收盘→拦。
    亚洲市场按上表收盘时刻;其余 tradfi 按美股:工作日 13:30–20:00 UTC 必在盘中。例外备注写「非当日收盘」。"""
    import datetime as _dt
    note = note or ''
    if '非当日收盘' in note:
        return None
    if now is None and os.environ.get('CONSOLE_FAKE'):   # 回归注入环境不按墙钟判(用例显式传 now)
        return None
    now = now or time.time()
    u = _dt.datetime.utcfromtimestamp(now)
    if u.weekday() >= 5:
        return None
    sgt = _dt.datetime.utcfromtimestamp(now + 8 * 3600)
    mmdd = f'{sgt.month:02d}-{sgt.day:02d}'
    hit_t = re.search(r'收涨|收跌|收于', title or '')
    hit_n = re.search(re.escape(mmdd) + r'\s*收盘|今日收盘|当日收盘', note)
    if not (hit_t or hit_n):
        return None
    hay = (title or '') + ' ' + ' '.join(kws or [])
    for rx, (h, m) in CLOSE_MKT:
        if rx.search(hay):
            if (u.hour, u.minute) < (h, m) and u.hour >= 0:
                return (f'{"标题" if hit_t else "备注"}写了收盘,但该市场今天 {h:02d}:{m:02d} UTC 才收盘(现在 {u:%H:%M} UTC)——'
                        f'行情源可能延迟(长桥A股约15分钟),取数先看 timestamp;确是前一交易日收盘在备注写「非当日收盘」')
            return None
    if (13, 30) <= (u.hour, u.minute) < (20, 0):
        return (f'{"标题" if hit_t else "备注"}写了收盘,但美股正在盘中({u:%H:%M} UTC)——盘中价用「盘中」前缀;确是前一交易日收盘在备注写「非当日收盘」')
    return None


# 11-07 周报通读:单字「指」把「业绩指引/指控/指出」也当成指数词放行,5% 门槛形同虚设——只认完整指数名
# 11-12 复盘:5% 门槛是给单名个股定的;大宗/宏观资产(金价、原油、美元、美债)两次被它拦、都靠「低于5%仍建」放行(10000003523、10000003781),改为不进此闸
TF_MACRO = re.compile(r'金价|黄金|白银|银价|原油|布油|美油|油价|WTI|天然气|铜价|美元指数|美债|收益率|汇率|GC=F|CL=F|BZ=F|SI=F|XAU')
TF_INDEX = re.compile(r'指数|成指|台指|国指|科指|ETF|KOSPI|日经|标普|纳指|道指|恒指|恒生|沪深|上证|深证|创业板|科创|费半|SPY|QQQ|SOXX|DIA|股集体|板块|概念股|类股')


ASIA_SFX = re.compile(r'\.(T|KS|KQ|HK|TW|SS|SZ)$', re.I)
EARN_WORD = re.compile(r'财报|业绩|利润|营收|指引|季度|季报')


def asia_earn_time(domain, title, note, kws):
    """11-05 复盘(10000003559 索尼):路透「二季度利润增45%」15:37 JST 发布、东证 15:30 已收盘,7.1% 是公告前的涨幅,
    配成「利润增45%…收涨7.1%」属伪因果。亚洲公司财报多在收盘后发布——亚洲代码 + 标题写业绩类诱因 + 收涨/收跌,
    备注须写「公告时间:」(当地时间,早于或晚于收盘);写了「晚于收盘」的不能配当日收盘涨跌。"""
    if (domain or '') != 'tradfi' or not any(ASIA_SFX.search(k or '') for k in kws or []):
        return None
    t, n = title or '', note or ''
    if not (EARN_WORD.search(t) and re.search(r'收涨|收跌', t)):
        return None
    if '公告时间' not in n:
        return '亚洲公司业绩题配当日收盘涨跌:备注须写「公告时间:HH:MM 当地,早于/晚于收盘」(11-05 索尼 15:37 公告、7.1% 发生在公告前)'
    if re.search(r'公告时间[:：][^;；]*晚于收盘', n):
        return '公告晚于收盘,当日收盘涨跌不是对它的反应——等次日开盘或 ADR 实测再建'
    return None


def _megacap():
    """11-09 用户定:市值前10超大盘股有诱因门槛 3%。名单在 megacap.json(MEGACAP_JSON 可注入);读不到返回空=全按 5%。"""
    import json as _j
    try:
        d = _j.load(open(os.environ.get('MEGACAP_JSON') or os.path.join(D, 'megacap.json'), encoding='utf-8'))
    except Exception:
        return {}, 5.0, None
    return d.get('names') or {}, float(d.get('floor_pct') or 3), d.get('as_of')


def megacap_hit(title, kws=None):
    """标题或关键词里出现名单内 ticker(整词)或别名 → 返回 ticker,否则 None。"""
    names, _, _ = _megacap()
    ks = [k.strip() for k in re.split(r'[,，]', kws or '') if k.strip()] if isinstance(kws, str) else list(kws or [])
    hay = (title or '') + ' ' + ' '.join(ks)
    for tk, al in names.items():
        if any(k.upper() == tk for k in ks) or re.search(r'(?<![A-Za-z])' + re.escape(tk) + r'(?![A-Za-z])', title or ''):
            return tk
        if any(x and x in hay for x in al):
            return tk
    return None


def tradfi_floor(domain, title, note, kws=None):
    """11-02 用户定(W43/W44 盲审分歧):tradfi 单名有实在直接诱因时幅度门槛 5%,<5% 视同无诱因。
    11-09 用户定(NVDA 黄仁勋调查夜盘 -3.2% 被 5% 线拦、用户点名「建」后改规则):市值前10超大盘股(megacap.json)门槛 3%。
    只看标题里「涨/跌X%」;没有百分数(宏观题报X)、含指数/ETF/板块词的不拦;例外在备注写「低于5%仍建:<理由>」。"""
    if (domain or '') != 'tradfi' or '低于5%仍建' in (note or '') or TF_INDEX.search(title or '') or TF_MACRO.search(title or ''):
        return None
    xs = [float(x) for x in re.findall(r'(?:涨|跌)(\d+(?:\.\d+)?)%', title or '')]
    mc = megacap_hit(title, kws)
    _, mfloor, as_of = _megacap()
    floor = mfloor if mc else 5.0
    if mc and as_of:
        try:
            age = (_dt.date.today() - _dt.date.fromisoformat(as_of)).days
            if age > 14:
                print(f'⚠️ megacap.json 名单是 {as_of} 的({age} 天前),周报时按实测市值刷新')
        except Exception:
            pass
    if not xs or max(xs) >= floor:
        return None
    who = f'超大盘股 {mc} 门槛 {floor:g}%(11-09 用户定)' if mc else '有诱因的个股门槛 5%(11-02 用户定)'
    return (f'tradfi 单名涨跌 {max(xs)}% < {floor:g}%({who},不足视同无诱因)——'
            f'改落 log-action.sh note - 留档 "弃建|<标的>|<{floor:g}%…";确需例外 --note 写「低于5%仍建:<理由>」')


SECTOR_WORD = re.compile(r'股|板块|概念|指数|指|类股|集体|普涨|普跌|ETF|费半|纳指|标普|道指|恒指|日经|KOSPI|台股|期货')
PRICE_CLAUSE = re.compile(r'(?:涨|跌|破|站上|升至|报)[^，]{0,4}\d')


def sector_lead(rc, title):
    """11-03 复盘(3450「民主党胜选概率走高，太阳能股…」):板块聚合题不写因果,首句只能是板块播报或价格陈述。
    首句(第一个「，」前)既无板块/指数词、也不是带数字的价格句 → 等于把一件事件放在板块前当诱因,改走 有诱因-* 并在备注给出把两者连起来的源。"""
    if rc != '板块聚合':
        return None
    first = (title or '').split('，')[0]
    if SECTOR_WORD.search(first) or PRICE_CLAUSE.search(first):
        return None
    return (f'板块聚合题首句「{first}」不是板块播报也不是价格句——前置事件句等于写了诱因(11-03 3450 选举概率+太阳能股);'
            f'删掉首句只留板块播报,或改 rc 有诱因-多源 并在备注写出直接把两者连起来的源')


CRYPTO_LINE = float(os.environ.get('TS_CRYPTO_LINE', '50'))   # 11-06 用户定:crypto 纯行情(rc 纯行情-A定则)与 meme 豁免①幅度线 30%→50%;与 lint.CRYPTO_LINE 同值


def crypto_amp(rc, domain, title, note, kws=''):
    """11-06 用户定:「山寨妖币纯行情波动的话题太多」——crypto 纯行情题 24h 涨跌须 ≥±50%(原 30%)。
    11-09 用户定:BTC/ETH 不走 50% 线——24h 须 ≥ coverage.MAJOR 线(BTC 5%/ETH 7%),或写「关口+阶段新高/新低」
    且备注带「阶段高低已核:<K线依据>」。读不到幅度又不是主流币的不拦(由人核)。有诱因/硬事件的题不走 纯行情-A定则,不受此限。"""
    if rc != '纯行情-A定则' or (domain or '') != 'crypto':
        return None
    import lint as _lt
    m = re.search(r'24小时(?:涨|跌)(\d+(?:\.\d+)?)%', title or '')
    mj = _lt.major_line(title, kws)
    if mj:
        line, sym = mj
        if m and float(m.group(1)) >= line:
            return None
        if _lt.KEYLEVEL.search(title or '') and _lt.STAGE_HL.search(title or '') and '阶段高低已核' in (note or ''):
            return None
        return (f'主流币 {sym} 纯行情题须 24h ≥±{line:g}% 或「关口+阶段新高/新低」(11-09 用户定)'
                f'{"(本题 " + m.group(1) + "%)" if m else ""}——关口写法要在 --note 写「阶段高低已核:<币安日线依据>」;都不满足改落弃建')
    if m and float(m.group(1)) < CRYPTO_LINE:
        # 11-11 用户定「热点主流币大跌可以留」:币安合约 24h 成交 ≥10 亿美元(coverage.HOT_VOL)的加密币,线降到 ±10%(coverage.HOT_LINE)。
        # 成交额从标题/备注「成交X亿美元」读(与 lowvol 同口径,复审员抽查真伪);没写=按 50% 线拦
        hv, hl, hm = _hot_line()
        blob = (title or '') + ' ' + (note or '')
        q = re.search(r'成交(?:额)?\s*(\d+(?:\.\d+)?)\s*亿\s*美元', blob)
        c = re.search(r'市值\s*(\d+(?:\.\d+)?)\s*亿\s*美元', blob)
        if q and c and float(q.group(1)) * 1e8 >= hv and float(c.group(1)) * 1e8 >= hm and float(m.group(1)) >= hl:
            return None
        return (f'纯行情币题 24h 幅度 {m.group(1)}% < {CRYPTO_LINE:g}%(11-06 用户定:由 30% 上调到 50%)——'
                f'热点主流币例外(11-11 用户定):币安合约 24h 成交 ≥{hv / 1e8:g} 亿美元、市值 ≥{hm / 1e8:g} 亿美元且幅度 ≥{hl:g}% 可建,'
                f'须在备注写「币安合约成交X亿美元」「市值X亿美元(CoinGecko)」;'
                f'否则改落 log-action.sh note - 留档 "弃建|<标的>|24h X%未达纯行情线…";有可指名诱因/硬事件就换对应 rc 建')
    return None


def _hot_line():
    """11-11:热点主流币线,单一定义在 coverage.HOT_VOL/HOT_LINE/HOT_MCAP;读不到按成交 10 亿/10%/市值 10 亿。"""
    try:
        import importlib.util as _u
        _s = _u.spec_from_file_location('_cov', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coverage.py'))
        _c = _u.module_from_spec(_s); _s.loader.exec_module(_c)
        return _c.HOT_VOL, _c.HOT_LINE, _c.HOT_MCAP
    except Exception:
        return 1e9, 10.0, 1e9


def lowvol(rc, domain, title, note):
    """v3.7.9(10-21 用户定):crypto 纯行情(无诱因)题须币安合约 24h 成交额 ≥1 亿美元,不足默认弃建。
    成交额从标题/备注里的「成交X亿美元」「成交X万美元」读;读不到不拦。有诱因/硬事件的题不走 纯行情-A定则,不受此限。"""
    if (domain or '') != 'crypto' or '豁免成交额' in (note or ''):
        return None
    # 11-07 用户定(Q13):只靠幅度(豁免①)过关的 meme 题也要币安合约 24h 成交 ≥1 亿;走硬事件/市值关口的不受此限
    meme_amp = rc == 'meme豁免' and not re.search(r'硬事件\s*✓|市值关口\s*✓', note or '')
    if rc != '纯行情-A定则' and not meme_amp:
        return None
    found = False
    for txt in (title or '', note or ''):
        m = re.search(r'成交(?:额)?\s*(\d+(?:\.\d+)?)\s*(亿|万)\s*美元', txt)
        if m:
            v = float(m.group(1)) * (1e8 if m.group(2) == '亿' else 1e4)
            found = True
            if v < 1e8:
                return (f'纯行情币题成交额 {m.group(1)}{m.group(2)}美元 < 1 亿(v3.7.9 用户定:无诱因的币 24h 合约成交不足 1 亿默认弃建)——'
                        f'改落 log-action.sh note - 留档 "弃建|<标的>|成交额不足1亿…";有可指名诱因/硬事件就换对应 rc 建;特殊情况 --note 写「豁免成交额:<理由>」')
            return None
    if meme_amp and not found:
        return ('meme豁免走幅度路径(豁免①)须写币安合约 24h 成交额(11-07 用户定 Q13:≥1 亿才可建)——备注写「币安合约成交X亿美元」;'
                '走硬事件/市值关口的在备注四查写「硬事件✓」或「市值关口✓」')
    return None


def style_rc(rc, old, new, domain, note):
    """10-20 复盘(13384 SOPH、13403 AXIS,此前 13296):系统题改写补了价格腿/新数字,却记「改样式-命名」。
    回测 actions.tsv:142 次该码里 65 次新标题多出原题没有的数字或价格腿。改样式-命名只给不改事实的措辞/命名调整。"""
    if rc != '改样式-命名' or not new or '仅措辞' in (note or ''):
        return None
    nums = lambda s: re.findall(r'\d+(?:\.\d+)?', s or '')
    extra = [x for x in nums(new) if x not in nums(old)]
    # 价格腿直接认形态(涨跌%/报X/持平):lint 会把带日期的原题判成预告题而不报缺价格(13384 原题即此),不能借它的告警
    price = lambda t: bool(re.search(r'\d+(?:\.\d+)?\s*%|报\s*\d|持平', t or ''))
    added = bool(old) and not price(old) and price(new)
    if extra or added:
        why = (f'新增数字 {",".join(extra)}' if extra else '') + ('、' if extra and added else '') + ('补了价格腿' if added else '')
        return (f'改样式-命名只用于不改事实的措辞/命名调整,新标题{why}——补价格腿/改数字用「改数字-定稿」「改数字-升温」或「改数字-回落」,'
                f'新增事实用「承接更新」,换时段口径用「改口径-时段」,改因果用「改归因」;确属纯措辞(如四舍五入)在 --note 写「仅措辞」放行')
    return None


def cmd_cull(a, c):
    t = _current(c, a)
    cards('cull', t.get('title'), t.get('domain'), closed_ms=t.get('closed_ts'), ref=a.id)
    _sa, _sv = sicha_auto(t, a.rc, note_of(a))
    if _sa == 'block':
        block(_sv, 'cull', a.id, a.rc, check='sicha_auto')
    if _sa == 'fill':
        if getattr(a, 'T', None):
            a.T = _sv + a.T
        else:
            a.note = _sv + (a.note or '')
        hit('sicha_auto', '改', 'cull', a.id, a.rc)
        print('↻ 四查行由工具写入:' + _sv.strip())
    _cn = note_of(a)
    a.rc, _fx = meme_rc_fix(a.rc, _cn)
    if _fx:
        hit('meme_rc', '改', 'cull', a.id, a.rc)
        print(_fx)
    for _nk, _nf in (('near_line', lambda: near_line(a.rc, t.get('domain'), _cn)), ('meme_rc', lambda: meme_rc(a.rc, _cn)),
                     ('dup_target', lambda: dup_target(a.rc, _cn, a.id, c.get)),
                     ('cross_day_dup', lambda: cross_day_dup(a.rc, _cn, t, c.get))):
        _nl = _nf()
        if _nl:
            # 11-07 复盘:原先只计数不进 actions-rejected,复审员按台账核「被哪道闸拦」时查不到(10000003544 跨交易日闸)——改走 block 留痕
            block(_nl, 'cull', a.id, a.rc, check=_nk)
    if (t.get('title') or '') and t['title'] not in (a.note or '') and not a.T:
        a.note = CULL_RC_PREFIX_NOTE.format(t['title']) + a.note    # 撤时的标题进备注:撤后系统还会改写已隐藏题的标题(10-14/10-15 三例)
    b0 = tmp_b0(t)
    try:
        largs = la_args('cull', a.id, a.rc, a)
        rc_, out = la(largs, check=True, b0=b0)
        if rc_ != 0:
            _la_fail(out)
        if a.dry:
            print(f'[dry] 将撤 {a.id}「{t.get("title")}」 rc={a.rc}')
            return
        # v3.7.30 review:撤题不动权重——隐藏题后台不重算、前台不显示;留着原档,restore 时直接生效
        write_and_log(c, 'update_trending_topic', {'id': int(a.id), 'status': 3}, largs, b0, 'cull', a.id, a.rc)
        log_waivers(a, 'cull', a.id)
    finally:
        if b0:
            os.unlink(b0)
    bad = readback(c, a.id, {'status': 3})
    for b in bad:
        print('  🚨 回读不一致 ' + b)
    print(f'✔ 撤 {a.id} [{a.rc}]「{t.get("title")}」')
    if bad:
        sys.exit(6)


def cmd_check(path):
    """批量预检:文件每行一条 topic.py 命令(可带可不带开头的 topic.py;# 开头与空行跳过),逐条 --dry 跑完全部检查,
    一次列出每条被拦的全部原因。不写看板、不落账、不进 actions-rejected。末行 CHECK: 条数=N 通过=a 被拦=b;b>0 退出码 1。"""
    import shlex
    from concurrent.futures import ThreadPoolExecutor
    src = sys.stdin if path == '-' else open(path, encoding='utf-8')
    cmds = []
    for ln in src:
        ln = ln.strip()
        if not ln or ln.startswith('#'):
            continue
        try:
            args = shlex.split(ln)
        except ValueError as e:
            cmds.append((ln, None, f'这一行引号不配对:{e}'))
            continue
        if args and os.path.basename(args[0]) == 'topic.py':
            args = args[1:]
        if not args or args[0] not in ('create', 'update', 'publish', 'cull', 'restore'):
            cmds.append((ln, None, '只认 create/update/publish/cull/restore 开头的行'))
            continue
        cmds.append((ln, [a for a in args if a != '--dry'] + ['--dry'], None))

    def run(item):
        ln, args, err = item
        if err:
            return 2, err
        env = dict(os.environ, TOPIC_COLLECT='1')
        r = subprocess.run([sys.executable, '-W', 'ignore', os.path.abspath(__file__)] + args, capture_output=True, text=True, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(run, cmds))
    # 11-10 复盘:并发跑时偶发「退出码非 0 且一个字都没输出」(17:30 轮 1 次、23:00 轮 2 次,单跑都过;事后并发 32 次未复现)。
    #   这种没有拦截原因的失败不能当被拦——串行重跑一次;仍失败就明写「无输出、退出码 N」,不再空着一行让人猜。
    retried = set()
    for k, (item, (rc_, out)) in enumerate(zip(cmds, res)):
        if rc_ != 0 and not out and item[1] is not None:
            res[k] = run(item); retried.add(k)
    # v3.7.33 判据卡:各条命中的卡汇总,在逐条结果之前打一次——先看判据,再看哪条被拦
    picked, refs = [], {}
    for _, out in res:
        for l in out.splitlines():
            if l.startswith('CARDS-PICK:'):
                _nm, _, _rf = l[len('CARDS-PICK:'):].partition('|')
                for n in _nm.split(','):
                    if n and n not in picked:
                        picked.append(n)
                    if n and _rf:
                        refs.setdefault(n, []).append(_rf)
    if picked:
        try:
            import card
            card.emit(picked, trigger='check', ref={n: ';'.join(dict.fromkeys(v)) for n, v in refs.items()})
        except Exception:
            pass
    ok = 0
    for i, ((ln, args, _), (rc_, out)) in enumerate(zip(cmds, res), 1):
        head = ln if len(ln) <= 90 else ln[:90] + '…'
        rt = ['↻ 并发跑时无输出失败,已串行重跑一次'] if i - 1 in retried else []
        if rc_ == 0:
            ok += 1
            extra = rt + [l for l in out.splitlines() if l.strip().startswith(('⚠️', 'WARN', '↻', '⚖️'))]
            print(f'✔ #{i} {head}' + ''.join('\n    ' + l.strip() for l in extra))
        else:
            lines = [l.strip() for l in out.splitlines() if l.strip().startswith(('🚨', 'WARN', '⚠️', 'usage', 'topic.py: error'))]
            lines = rt + (lines or [l.strip() for l in out.splitlines() if l.strip()][-3:] or [f'无输出,退出码 {rc_}(不是检查拦下的,单跑这一行看原因)'])
            print(f'🚨 #{i} {head}' + ''.join('\n    ' + l for l in lines))
    print(f'CHECK: 条数={len(cmds)} 通过={ok} 被拦={len(cmds) - ok}')
    sys.exit(0 if ok == len(cmds) else 1)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == 'check':
        if len(sys.argv) < 3:
            sys.exit('用法: topic.py check <文件|->   文件每行一条 topic.py 命令')
        cmd_check(sys.argv[2])
    try:
        _main()
    except SystemExit:
        raise
    except Exception as e:
        if COLLECT is None:
            raise
        COLLECT.append(f'预检中途出错,之后的检查没跑:{type(e).__name__}:{str(e)[:120]}')
    if COLLECT:
        _collect_exit()


def _main():
    # 回归注入:模拟一次「并发下无输出失败」——文件在就删掉它并静默退出 1(只在预检子进程里生效)
    _fk = os.environ.get('TOPIC_CHECK_FLAKE')
    if COLLECT is not None and _fk and os.path.exists(_fk):
        os.remove(_fk); sys.stdout.flush(); os._exit(1)
    p = argparse.ArgumentParser(add_help=True, description='看板写操作唯一入口(v3.7.0)')
    p.add_argument('cmd', choices=['create', 'update', 'publish', 'cull', 'restore', 'get'])
    p.add_argument('--id')
    p.add_argument('--domain')
    p.add_argument('--title')
    p.add_argument('--keywords')
    p.add_argument('--tags')
    p.add_argument('--topic-type', type=int, default=0)
    p.add_argument('--rc')
    p.add_argument('--note')
    p.add_argument('-T', dest='T')
    p.add_argument('--pct', action='append')
    p.add_argument('--pub-note')
    p.add_argument('--no-publish', action='store_true')
    p.add_argument('--no-downstream', action='store_true')
    p.add_argument('--force-system-edit', action='store_true')
    p.add_argument('--lang')
    p.add_argument('--dry', action='store_true')
    p.add_argument('--tier', help='v3.7.30 人工指定排序权重档 A/B/C/D(仅 create);须带 --tier-why')
    p.add_argument('--tier-why')
    a = p.parse_args()
    if a.cmd != 'get' and a.cmd != 'publish' and not a.rc:
        p.error('--rc 必填')
    if a.cmd not in ('get', 'publish') and not (a.note or a.T):
        p.error('--note 或 -T 必填(备注三要素:判据引用+实测证据+为何落此 reason_code)')
    if a.cmd != 'create' and not a.id:
        p.error('--id 必填(写操作一律按 id 定位)')
    if COLLECT is not None:
        a.dry = True          # 预检模式绝不写看板
    from console import Console
    c = Console()
    if a.cmd == 'get':
        t = c.get(a.id, lang=a.lang)
        print(json.dumps(t, ensure_ascii=False, indent=1) if t else f'找不到 {a.id}')
        return
    if a.cmd == 'create':
        if not (a.domain and a.title and a.keywords):
            p.error('create 需要 --domain --title --keywords')
        cmd_create(a, c)
        try:
            _tops = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'b0-latest.json'))).get('topics', [])
        except Exception:
            _tops = []
        for o in opposite_after_create({'title': a.title, 'keywords': a.keywords}, _tops):
            print(f'⚠️ 反向在线题 {o["id"]}「{o.get("title")}」与新题同标的/同品种、方向相反——过期题处置表:新建反向题须撤方向相反的老题(10-26 复盘)\n'
                  f'   $ ~/.trend-scout/topic.py cull --id {o["id"]} --rc 反转错向 --note "…"')
    elif a.cmd == 'update':
        cmd_update(a, c)
    elif a.cmd == 'publish':
        _rp = os.environ.get('REJ') or os.path.join(D, 'actions-rejected.tsv')
        _rows = [l.rstrip('\n').split('\t') for l in open(_rp, encoding='utf-8')] if os.path.exists(_rp) else []
        _ok = [l.rstrip('\n').split('\t') for l in open(os.path.join(D, 'actions.tsv'), encoding='utf-8')] if os.path.exists(os.path.join(D, 'actions.tsv')) else []
        _rb = recent_block(a.id, _rows, _now())
        _last_ok = max((int(r[0]) for r in _ok if len(r) > 3 and r[2] == str(a.id) and r[1] == 'update' and r[0].isdigit()), default=0)
        _last_rej = max((int(r[0]) for r in _rows if len(r) > 3 and r[3] == str(a.id) and r[0].isdigit()), default=0)
        if _rb and _last_rej > _last_ok:
            block(f'{a.id} 10 分钟内有写操作被拦且之后没有成功的 update:{_rb[:80]}——先把那次改好再 publish(10-19 PAPER 旧标题上线)', 'update', a.id, '状态修正', check='recent_block')
        a.rc = '状态修正'
        a.note = a.note or '发布三问(标的可交易/时效/去重)全过,推上线;落此code因=status改0'
        cmd_update(a, c, status=0)
    elif a.cmd == 'cull':
        cmd_cull(a, c)
    elif a.cmd == 'restore':
        try:
            _tops = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'b0-latest.json'))).get('topics', [])
        except Exception:
            _tops = []
        _ol = opposite_live(_current(c, a), _tops, note_of(a))
        if _ol:
            block(_ol, 'restore', a.id, a.rc, check='opposite_live')
        cmd_update(a, c, status=0, act='restore')


if __name__ == '__main__':
    main()
