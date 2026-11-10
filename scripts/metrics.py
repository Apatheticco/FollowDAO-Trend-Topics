#!/usr/bin/env python3
# metrics.py — 周复盘第 0/0.5 层的机器算数（v2.9.83）。只读 actions.tsv + snapshots.tsv，不调 API。
# 用法: metrics.py [天数=7] [--write]      --write 时落 ~/.trend-scout/reports/weekly-<起>_<止>.md
# 五个数字: ①用户点名数(按类型) ②团队打回率 ③撤因TOP(灌水占比) ④复审员挑战/成立 ⑤返工率
# 附: 上游垃圾形态(给 dev 的固定工单) / 规则体积
import os, sys, re, datetime, collections
D=os.path.expanduser('~/.trend-scout'); A=os.environ.get('ACTIONS') or os.path.join(D,'actions.tsv'); S=os.environ.get('SNAPSHOTS') or os.path.join(D,'snapshots.tsv')
sys.path.insert(0, D)
import ledger   # v3.7.0 建题真实 id 解析单一实现(09-24 起 create 行 id 记成「-」,②⑤分母恒 1)
G=os.path.expanduser('~/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic')

def rows(path, ncol):
    out=[]
    if not os.path.exists(path): return out
    for l in open(path,encoding='utf-8'):
        if l.startswith('#') or not l.strip(): continue
        p=l.rstrip('\n').split('\t')
        if len(p)>=ncol:
            try: p[0]=int(p[0])
            except: continue
            out.append(p)
    return out

def main():
    a=[x for x in sys.argv[1:] if not x.startswith('--')]; days=int(a[0]) if a else 7
    write='--write' in sys.argv
    now=datetime.datetime.now(); cut=int((now-datetime.timedelta(days=days)).timestamp()*1000)
    acts=[r for r in rows(A,5) if r[0]>=cut]
    snaps=rows(S,5)
    def ts(ms): return datetime.datetime.fromtimestamp(ms/1000)
    out=[]; P=out.append
    P(f"# 周复盘机器算数 {ts(cut):%m-%d}~{now:%m-%d}（{days} 天，actions {len(acts)} 行）\n")

    # ① 用户点名
    call=[r for r in acts if r[3]=='用户点名']
    # v3.7.1(用户 10-15 定) 资格线换成四条,点名降为参考:点名为 0 依赖用户在看,用户不审时它天然为 0
    try:
        import qualify
        _ql, _qs = qualify.report(2)
        P(f"## 资格线（切定时任务，10-15 用户定·四条连续 2 周全过）：{'✅ 达标' if _qs >= 2 else f'❌ 未达标（连续 {_qs} 周）'}")
        for _l in _ql: P('  ' + _l)
        P('')
    except Exception as _e:
        P(f"## 资格线：⚠️ 计算失败 {type(_e).__name__}: {_e}\n")
    P(f"## ① 用户点名：{len(call)} 次（参考，不再作资格线——你不审时它天然为 0）")
    bydate=collections.Counter(ts(r[0]).strftime('%m-%d') for r in call)
    P("  按日: "+(', '.join(f"{d}×{n}" for d,n in sorted(bydate.items())) or '无'))
    for r in call: P(f"  - {ts(r[0]):%m-%d} [{r[1]} {r[2]}] {r[4][:70]}")

    # ② 团队打回率：我建且推上线的题，之后快照里出现 status=3 且我没撤
    # v3.7.0 建题 id 经 ledger 解析:09-24~10-14 的 create 行 id 全是「-」,旧写法 mine_create={'-'} → ②⑤ 分母恒 1、
    #   三份周报印着「团队打回率 0/1」「返工率 0/1」;下面「上游垃圾」也拿它判非我建,会把撤我自建题算成系统垃圾。
    _cr=ledger.created(ledger.rows(A), since_ms=cut)
    mine_create={rid for _,rid,_ in _cr}
    mine_cull={str(r[2]) for r in acts if r[1] in ('cull',)}
    last_status={}
    for r in snaps:
        if r[0]>=cut: last_status[str(r[1])]=(r[3], r[0])
    bounced=[i for i in mine_create if i not in mine_cull and last_status.get(i,('',0))[0]=='3']
    P(f"\n## ② 团队打回率：{len(bounced)}/{len(mine_create)} = {100*len(bounced)/max(1,len(mine_create)):.0f}%（我建、非我撤、终态隐藏）")
    for i in bounced: P(f"  - {i}")

    # ③ 撤因 TOP
    culls=[r for r in acts if r[1]=='cull']
    rc=collections.Counter(r[3] for r in culls)
    # v3.5.0(09-20 用户点名「都做」) 撤因码本来就是「族-形态」两段式(灌水-KOL观点/重复-同标的/事实错误-数字…),
    #   但旧版只按完整码排 TOP,把族拆散了:09-13~09-20 榜首显示「重复-同标的 33」,而灌水族合计 56 才是真第一。
    #   **不合并枚举**——六个子码喂的是 dev 侧「上游垃圾形态」工单,合掉会丢粒度、且 1200+ 历史行要重写。
    #   只改报表:族聚合置顶,子码明细缩进跟随。
    def _fam(k):   # v3.7.6 历史码「灌水-悬念疑问」并入疑问句族
        if k=='灌水-悬念疑问': return '疑问句'
        return 'A闸不过-灌水' if k=='A闸不过-灌水' else (k.split('-')[0] if '-' in k else k)
    fam=collections.Counter(_fam(k) for k in (r[3] for r in culls))
    fill=sum(n for k,n in rc.items() if k.startswith('灌水') or k=='A闸不过-灌水')
    P(f"\n## ③ 撤题 {len(culls)} 条，灌水族 {fill} 条 = {100*fill/max(1,len(culls)):.0f}%（连续 2 周居首 → 必须前置成机械闸）")
    P("  ——按族（v3.5.0：真实榜首看这一栏，子码只是形态标签）——")
    for k,n in fam.most_common(6):
        P(f"  {n:3d}  {k}")
        for sk,sn in rc.most_common():
            if _fam(sk)==k and sk!=k: P(f"        {sn:3d}  {sk}")

    # ④ 复审员挑战
    ch=[r for r in acts if r[3]=='复审员挑战']
    # v3.5.0(09-20 用户点名「都做」) 旧口径只认行首 ^成立:,实测 09-13~09-20 漏掉 2/4——
    #   我把成立案写成了「**复审员挑战成立,我错了…」「**复审员挑战成立,我接受并改判为撤」,
    #   星号与「复审员」三字挡在前面,^ 锚点够不着。与 v2.9.71 北极星漏数(7 vs 真实 48)同病:
    #   判据挂在「我记得按格式写」上,就一定会漏。改成全文匹配 + 否定词优先。
    NEG=re.compile(r'不成立')
    POS=re.compile(r'挑战成立|成立[:：]|复审员.{0,6}成立|据此改判|改判为撤|我错了|接受并改判')
    ok=[r for r in ch if POS.search(r[4]) and not NEG.search(r[4])]
    amb=[r for r in ch if not POS.search(r[4]) and not NEG.search(r[4])]
    P(f"\n## ④ 复审员挑战 {len(ch)} 次，成立 {len(ok)} 次（成立=确实改/撤/订正；v3.5.0 全文匹配，不再只认行首前缀）")
    if amb: P(f"  ⚠️ {len(amb)} 条既无成立也无不成立字样，未计入分子（id: {','.join(str(r[2]) for r in amb[:6])}）——这类是纯轮次小结，不是裁决")
    zero_rounds=None
    P("  " + ('; '.join(f"{str(r[2])}:{r[4][:40]}" for r in ch[:8]) or '无'))

    # ⑤ 返工率：我建的题在 8h 内被我 update(非状态修正)
    ct={rid:ts for ts,rid,_ in _cr}
    REWORK_RC={'改归因','改口径-时段','事实错误-数字','事实错误-定义','反转错向','归因-借源造因','归因-反向','tag修正','纠错-自纠'}   # v3.7.0 加 纠错-自纠  # 定稿/命名/承接是正常代谢,不算返工
    rework={str(r[2]) for r in acts if r[1]=='update' and r[3] in REWORK_RC and str(r[2]) in ct and 0<r[0]-ct[str(r[2])]<=8*3600*1000}
    P(f"\n## ⑤ 返工率：{len(rework)}/{len(ct)} = {100*len(rework)/max(1,len(ct)):.0f}%（建后 8h 内改归因/改口径/事实错误/反转；定稿与命名不算）")
    for i in sorted(rework): P(f"  - {i}")

    # v3.7.0 ⑥ 工具拦截:拒写行不再删,按「其后同动作同 id 落账/显式 reject-ok」判已处理
    _rt,_rd=ledger.reject_stats(days)
    P(f"\n## ⑥ 工具拦截：{_rt} 次（已处理 {_rd}，未处理 {_rt-_rd}）——被闸拦下的写操作,v3.7.0 前删行放行、本项恒 0")
    # v3.7.0 ⑦ 下游错标:downstream-check.py 回读 Followin 资讯流成品,标的/域挂错的次数
    _dl=os.environ.get('DOWNSTREAM_LOG') or os.path.join(D,'downstream.log.tsv'); _dn=collections.Counter(); _dids=set()
    if os.path.exists(_dl):
        for l in open(_dl,encoding='utf-8'):
            x=l.rstrip('\n').split('\t')
            if len(x)>=4 and x[0].isdigit() and int(x[0])>=cut and x[3] in ('错标','域不符'):
                _dn[x[3]]+=1; _dids.add(x[2])
    P(f"\n## ⑦ 下游错标：{len(_dids)} 题（{'、'.join(f'{k}{v}' for k,v in _dn.items()) or '无'}）——看板成品里标的/领域挂错,建题时 tag 检查只看 ID 位数看不出")

    # v3.7.1 ⑧ 漏建对账:coverage.py 每轮落账,按标的去重取本周最后一次结论
    _cl=os.environ.get('COVERAGE_LOG') or os.path.join(D,'coverage.log.tsv'); _last={}
    if os.path.exists(_cl):
        for l in open(_cl,encoding='utf-8'):
            x=l.rstrip('\n').split('\t')
            if len(x)>=5 and x[0].isdigit() and int(x[0])>=cut: _last[(x[1],x[2])]=x[4]
    _cv=collections.Counter(_last.values())
    P(f"\n## ⑧ 漏建对账：过线 {len(_last)} 个标的，有题 {_cv['有题']}、弃建 {_cv['弃建']}、漏 {_cv['漏']}（按标的取本周最后一次对账结论）——第一个量「该建没建」的数")

    # v3.7.2 ⑨ 学习闭环:修过的错类,修后又犯几次(重犯=那次修法无效,换一层修)
    try:
        os.environ['RETRO_COLLECT']='1'
        import retro
        _n,_c,_rows=retro.week(days)
        _bad=[r for r in _rows if r[2]>0]
        P(f"\n## ⑨ 学习闭环：本周错误 {_n} 条 / {_c} 类；修过的错类 {len(_rows)} 个，修后又犯 {len(_bad)} 个" + ("（" + "、".join(f"{r[0]}×{r[2]}" for r in _bad) + "）" if _bad else ""))
    except Exception as _e:
        P(f"\n## ⑨ 学习闭环：⚠️ 计算失败 {type(_e).__name__}: {_e}")

    # 上游垃圾形态：非我建、被我以灌水/缺价格腿/疑问句撤的题 → 按形态聚类
    junk=[r for r in culls if str(r[2]) not in mine_create and (r[3].startswith('灌水') or r[3] in ('缺价格腿','疑问句-悬念','A闸不过-灌水'))]
    pat=collections.Counter()
    for r in junk:
        t=r[5] if len(r)>5 else ''
        note=r[4]
        if re.search(r'观点|KOL',r[3]): pat['冒号观点题(某某：…)']+=1
        elif 'vanity' in r[3]: pat['vanity指标(供应量/占比/TVL)']+=1
        elif '融资' in r[3]: pat['融资/投资无标的']+=1
        elif '公告' in r[3]: pat['产品公告/集成/合作']+=1
        elif '疑问' in r[3]: pat['疑问句悬念']+=1
        else: pat['无价格腿其他']+=1
    P(f"\n## 上游垃圾形态（系统建、被我撤）{len(junk)} 条 —— 给 dev 的固定工单：改生成器比每天手撤便宜")
    for k,n in pat.most_common(): P(f"  {n:3d}  {k}")

    # 规则体积
    def sz(p):
        p=os.path.join(G,p); return os.path.getsize(p)//1024 if os.path.exists(p) else -1
    # v3.1.6(周报提案5-1) 回归用例数改为跑一次 run-tests.sh 取真实值。
    #   旧实现只数 tests/lint-cases.tsv 的数据行(18),漏掉全部脚本层测试块(review-verify/weekly-verify/
    #   b0-cull meme闸/log-action meme闸/机审⑥价格前置…),而 run-tests.sh 自己报的是 39——周报连续多周
    #   印着一个偏低一半的数字。副作用是好的:周报生成时顺带跑一次全量回归,规则退化会当场暴露在周报里。
    import subprocess as _sp
    nt, tstat = '?', ''
    try:
        r = _sp.run([os.path.join(D,'run-tests.sh')], capture_output=True, text=True, timeout=120)
        m = re.search(r'回归 (\d+) 用例', r.stdout)
        if m: nt = m.group(1)
        if r.returncode != 0:
            tstat = f"｜🚨 **回归未通过**:{(r.stdout.strip().splitlines() or ['(无输出)'])[-1]}"
    except Exception as e:
        tstat = f"｜⚠️ 回归未能执行({type(e).__name__}),用例数不可信"
    # v3.4.4(周报提案 P1-4) 体积口径二选一=散点(run-tests 硬闸同源 scatter.py);KB 降为提示,不再作体检结论
    try:
        _sc = __import__('json').loads(_sp.run([os.path.join(D,'scatter.py'),'--json'], capture_output=True, text=True, timeout=60).stdout)
        sct = f"散点 {_sc['total']}（基线 {_sc['baseline']}）"
    except Exception as e:
        sct = f"散点 ?({type(e).__name__})"
    P(f"\n## 规则体积：{sct}｜gates.md {sz('references/gates.md')}KB(硬上限128KB,余{131072-os.path.getsize(os.path.join(G,'references/gates.md'))}B)｜LESSONS {sz('LESSONS.md')}KB｜SKILL {sz('SKILL.md')}KB｜回归用例 {nt} 条（每条 lesson 先问能不能写成用例）{tstat}")
    txt='\n'.join(out); print(txt)
    if write:
        os.makedirs(os.path.join(D,'reports'),exist_ok=True)
        p=os.path.join(D,'reports',f"weekly-{ts(cut):%Y-%m-%d}_{now:%m-%d}.md"); open(p,'w',encoding='utf-8').write(txt+'\n'); print(f"\n→ {p}")
if __name__=='__main__': main()
