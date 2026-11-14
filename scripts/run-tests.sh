#!/bin/bash
# run-tests.sh — 规则回归测试(v2.9.83)。checklist.sh verify 调用;任一失败 exit 1 不得出报告。
# 用例: tests/lint-cases.tsv(标题闸) tests/junk-cases.tsv(灌水形态) + 体积上限 + 枚举一致性
D="$HOME/.trend-scout"; G="${GATES:-$HOME/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic}"
# v3.4.3 跨平台:BSD `date -v` 在 Linux 沙箱不认(09-10 Evose 首轮 ⑦/hot-scan 一批假失败),相对时刻统一走 python。
#   用法: ago <小时> <strftime 格式> [u]   —— 第三参给 u 则取 UTC
ago(){ python3 -c 'import sys,time;t=time.time()-float(sys.argv[1])*3600;print(time.strftime(sys.argv[2],time.gmtime(t) if len(sys.argv)>3 else time.localtime(t)))' "$@"; }
# v3.7.22 检查计数:topic.py / log-action.sh 拦截时写 check-hits.tsv——回归里一律落临时文件,不污染生产计数(退役判据靠它)
export CHECK_HITS="$(mktemp)"
# 11-10 架构 review:查闸计数同理——此前回归每跑一次就往生产 gate-usage.tsv 记「大热点」「过期题」「grep 价格」各一行,
#   26 天账面 大热点 310 次/过期题 286 次几乎全是回归刷的,「零查询闸退役」判据失真。回归里一律落临时文件;文件末尾有守卫用例。
_GU_PROD="$D/gate-usage.tsv"; _GUG0=$(grep -c $'\tgrep\t价格$' "$_GU_PROD" 2>/dev/null); _GUG0=${_GUG0:-0}
export GATE_USAGE="$(mktemp)"
# 撞名表/等效表(11-10):回归用空表,生产表里登记的词不许影响旧用例,用例也不许往生产表里写
export DS_CLASH="$(mktemp)" DS_NAMES="$(mktemp)"; echo '{}' > "$DS_NAMES"
# 11-10:「建题前须有本轮 B0」这道检查读的是生产 b0-latest.json 的新旧——轮外跑回归、B0 超 2 小时时,凡是走 topic.py create 的旧用例
#   全被它先拦下(11-10 12:30 实测 12 条假失败)。回归里统一关掉;这道检查自己的用例(q1107)用 env -u 单独打开。
export TS_NO_B0CHECK=1
# v3.7.33 判据卡试跑:打印记录/去重状态落临时文件(试跑结算靠生产 card-usage.tsv,回归不许刷);
#   旧用例不看卡片,一律只记不打(CARD_QUIET),免得改变它们比对的输出。卡片自己的用例(cards1110)单独打开。
export CARD_USAGE="$(mktemp)" CARD_SEEN="$(mktemp)" CARD_QUIET=1
# 11-10 本机 14:40 轮自审发现:topic.py 建题测试会给新题记权重档,除 _tw9 外的封装没注入 WEIGHTS_TIER,
#   自 11-09 21:44 起每跑一次回归就往生产 weights-tier.tsv 写假题号(10000090001/2,已积 96 行)。统一指临时文件;末尾守卫。
export WEIGHTS_TIER="$(mktemp)"
_WT_PROD="$D/weights-tier.tsv"; _WT0=$(wc -l < "$_WT_PROD" 2>/dev/null | tr -d ' '); _WT0=${_WT0:-0}
_CU_PROD="$D/card-usage.tsv"; _CU0=$({ wc -l < "$_CU_PROD"; } 2>/dev/null | tr -d ' '); _CU0=${_CU0:-0}
export TS_VOL_AMP=15   # 11-06:旧用例按豁免②15%写;新值50由 volamp1106 用例验
export TS_CRYPTO_LINE=30   # 11-06:旧用例夹具按 crypto 30% 线写;新线 50% 由 line50-1106 用例在未设该变量时单独验
fail=0; n=0; skip=0; skipmsg=''
while IFS=$'\t' read -r title dom exp; do
  [ -z "$title" ] || [ "${title:0:1}" = "#" ] && continue
  n=$((n+1)); out=$(python3 "$D/lint.py" title "$title" "$dom" 2>&1)
  IFS=',' read -ra E <<< "$exp"
  for e in "${E[@]}"; do
    case "$e" in
      OK) echo "$out" | grep -qE '^(FAIL|WARN)' && { echo "❌ lint[$title]: 期望无 FAIL/WARN, 得到: $(echo "$out"|grep -E '^(FAIL|WARN)'|cut -f1,2|tr '\n' ' ')"; fail=$((fail+1)); } ;;
      !*) k="${e:1}"; echo "$out" | grep -q "^${k%%:*}	${k#*:}" && { echo "❌ lint[$title]: 不应命中 $k"; fail=$((fail+1)); } ;;
      *) echo "$out" | grep -q "^${e%%:*}	${e#*:}" || { echo "❌ lint[$title]: 应命中 $e, 得到: $(echo "$out"|cut -f1,2|tr '\n' ' ')"; fail=$((fail+1)); } ;;
    esac
  done
done < "$D/tests/lint-cases.tsv"
while IFS=$'\t' read -r title exp; do
  [ -z "$title" ] || [ "${title:0:1}" = "#" ] && continue
  n=$((n+1)); got=$(python3 -c "import sys;sys.path.insert(0,'$D');import lint;r=lint.junk_class(sys.argv[1]);print(r[0] if r else '-')" "$title")
  [ "$got" = "$exp" ] || { echo "❌ junk[$title]: 期望 $exp 得到 $got"; fail=$((fail+1)); }
done < "$D/tests/junk-cases.tsv"
# v3.4.x(09-17) meme 铁律作用域回归:标题<TAB>keywords<TAB>domain<TAB>期望(1/0)
while IFS=$'\t' read -r title kw dom exp; do
  [ -z "$title" ] || [ "${title:0:1}" = "#" ] && continue
  n=$((n+1)); got=$(python3 -c "import sys;sys.path.insert(0,'$D');import lint;print('1' if lint.meme_scope({'title':sys.argv[1],'keywords':sys.argv[2],'domain':sys.argv[3]}) else '0')" "$title" "$kw" "$dom")
  [ "$got" = "$exp" ] || { echo "❌ meme_scope[$title|$kw]: 期望 $exp 得到 $got"; fail=$((fail+1)); }
done < "$D/tests/meme-scope-cases.tsv"
# v3.6.0(09-26 用户定方案 B) 认代币要有交易证据:token_exist 结果注入,不联网
while IFS=$'\t' read -r title kw dom exp; do
  [ -z "$title" ] || [ "${title:0:1}" = "#" ] && continue
  n=$((n+1)); got=$(TOKEN_EXISTS_JSON="$D/tests/token-exist-fixture.json" python3 -c "import sys;sys.path.insert(0,'$D');import lint,token_exist;print('1' if lint.meme_scope({'title':sys.argv[1],'keywords':sys.argv[2],'domain':sys.argv[3]},token_exist.exists) else '0')" "$title" "$kw" "$dom")
  [ "$got" = "$exp" ] || { echo "❌ meme_scope+exist[$title|$kw]: 期望 $exp 得到 $got"; fail=$((fail+1)); }
done < "$D/tests/meme-scope-exist-cases.tsv"
# v3.6.0 过期题不改价:log-action 对已过 closed_ts 的题拒写「改数字-*」,未过期放行,改归因不受影响
_T=$(mktemp -d)
printf '[{"id":9801,"domain":"crypto","title":"AAA 24小时涨5%%","keywords":"AAA","status":0,"closed_ts":1000},{"id":9802,"domain":"crypto","title":"BBB 24小时涨5%%","keywords":"BBB","status":0,"closed_ts":9999999999999}]' > "$_T/b0.json"
_la(){ ACTIONS="$_T/a.tsv" SNAPSHOTS="$_T/s.tsv" REJ="$_T/r.tsv" B0JSON="$_T/b0.json" "$D/log-action.sh" "$@" >/dev/null 2>&1; echo $?; }
n=$((n+1)); [ "$(_la update 9801 改数字-定稿 "回归用例:v3.6.0过期闸" 'AAA 24小时涨5%→AAA 24小时涨9%')" != "0" ] || { echo "❌ v3.6.0 过期题改数字未被拦"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_la update 9802 改数字-定稿 "回归用例:v3.6.0过期闸" 'BBB 24小时涨5%→BBB 24小时涨9%')" = "0" ] || { echo "❌ v3.6.0 未过期题改数字被误拦"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_la update 9801 改归因 "回归用例:v3.6.0过期闸" 'AAA 24小时涨5%→AAA上线X，AAA涨5%')" = "0" ] || { echo "❌ v3.6.0 过期题改归因被误拦(只该拦改数字)"; fail=$((fail+1)); }
rm -rf "$_T"
# v3.1.7 规则健康度:硬闸从「字节上限」换成「散点」。
#   字节数度量的是规则集有多大,而真正伤人的是同一条判据在几处各写一份、改一处漏另一处——
#   09-03 BONK 就是 gates 写 5 项、review-agent 写三选一,同一条题两版可判反。
#   三次归一(v3.0.5 meme三选一 / v3.0.7 四时段 / v3.1.4 白名单)字节几乎没动(105KB→103KB),
#   而分叉风险实打实降了 —— 两个量正交,只有散点会让规则自相矛盾。
n=$((n+1))
gs=$(wc -c < "$G/references/gates.md" 2>/dev/null); gs=${gs//[!0-9]/}; gs=${gs:-0}   # v3.4.3: 原用 BSD stat 的 -f%z,Linux 不认
# v3.7.1(用户 10-15 批托管 review 第 5 步) 体积恢复硬上限 128KB:散点管「分叉」,上限管「只增不减」——09-09 110KB→10-10 131KB,
#   112KB 硬上限 v3.4.4 降成提示后一个月涨了 20KB。现在加一条就得合并或删一条(退役候选看 gate.sh usage 30)。
n=$((n+1)); [ "$gs" -gt 131072 ] && { echo "❌ gates.md $((gs/1024))KB 超 128KB 硬上限——加规则前先合并/退役(gate.sh usage 30 看零查询的闸)"; fail=$((fail+1)); }
SC=$("$D/scatter.py" 2>&1); echo "$SC" | tail -n +2 | grep '🔴' >/dev/null && { echo "$SC"; }
sc=$("$D/scatter.py" --json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["total"])' 2>/dev/null)   # v3.4.4(P1-4) 体检口径=散点
"$D/scatter.py" >/dev/null 2>&1 || { echo "❌ 规则散点超基线——同一条判据的多处副本已分叉,先同步再加新规则(详见 scatter.py 输出)"; fail=$((fail+1)); }
sl=$(grep -c . "$G/SKILL.md" 2>/dev/null || echo 0); [ "$sl" -gt 130 ] && { echo "❌ SKILL.md $sl 行 > 130:跑单只放「何时调它」"; fail=$((fail+1)); }
# 枚举一致性:用例里出现的撤因必须在 log-action 枚举内
for rc in $(awk -F'\t' '!/^#/ && $2!="-" && $2!="" {print $2}' "$D/tests/junk-cases.tsv" | sort -u); do
  "$D/log-action.sh" codes | grep -q -- "$rc" || { echo "❌ 撤因 $rc 不在 log-action.sh 枚举"; fail=$((fail+1)); }
done

# lark-push 渲染回归(v1.0):六块齐 + 计数与 fixture 一致 + 无未映射 rc + 无凭证泄漏
LP="/tmp/lark-render.$$"
if python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" > "$LP" 2>"$LP.err"; then
  n=$((n+1))
  for pat in '建2 改1 撤4' '🗑 撤 4' '✏️ 改 1' '➕ 建 2' '⚠️ 发现的问题' '🔧 修复／处置' '🟡 待裁 1' '📅 到期事件' 'R1 · 处置全清单' 'R2 · 复审与自审' 'R3 · 当前话题' 'R4 · 弃建记录' '独立重算' '覆盖不全，缺 1 条：11985' '挑战 1 条（逐条附处置）' '条发现（全文见台账' '没有标的被定价' '已自推上线' '通道 4/5 ✅' '通道故障 TG探针' '工具层拒写 1 次' '通道恢复 okx跌榜' '📍 用户点名 1 条' '补丁草稿待拍板' 'dev 单 2 条待评估' 'v3.0.1 复审对账改由推送独立重算' '📉 漂移哨兵' 'reason_code 全在 46 项内' '复审抽样自检率'; do
    grep -q "$pat" "$LP" || { echo "❌ lark-push render 缺: $pat"; fail=$((fail+1)); }
  done
  grep -qE 'api_key=|Bearer [A-Za-z0-9]|sk-ant-' "$LP" && { echo "❌ lark-push render 疑似凭证泄漏"; fail=$((fail+1)); }
  # v3.3.9 ③ R3 只列本轮动过/≤8h 新增并折叠其余;R2 自审只一行,不再贴 700 字全文
  n=$((n+1)); grep -q '列本轮动过／≤8h 新增' "$LP" || { echo "❌ lark-push render: R3 应折叠成「列本轮动过／≤8h 新增 N,其余 M 条略」"; fail=$((fail+1)); }
  n=$((n+1)); grep -q '自审七查（主进程收尾第 1 步）' "$LP" && { echo "❌ lark-push render: R2 不该再整段贴自审 note 全文"; fail=$((fail+1)); }
  # v3.3.9 render 必须认 --since(此前 send 认 render 不认,预览与实发不同):--since 0 覆盖全部 fixture 台账,建/改/撤计数 ≥ 默认 12h 窗
  _h0=$(python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" 2>/dev/null | head -1)
  # 对照要能在回滚后失败:fixture 里 11954 那条 cull 在 run_ts 之前 25 分钟,默认 12h 窗算进去(撤4),--since run_ts 应排除它(撤3)
  _h1=$(python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" --since 1788399480000 2>/dev/null | head -1)
  _c0=$(echo "$_h0" | grep -oE '撤[0-9]+' | tr -dc 0-9); _c1=$(echo "$_h1" | grep -oE '撤[0-9]+' | tr -dc 0-9)
  n=$((n+1)); [ "${_c1:-0}" -lt "${_c0:-0}" ] || { echo "❌ lark-push render: --since run_ts 的撤计数($_c1)应 < 默认12h窗($_c0),说明 --since 没生效"; fail=$((fail+1)); }
  # v3.4.0 ⑤ R1「理由」≤120 字(fixture 11970 那条 note 已加长到 >200 字作探针);主卡「改」段不带「旧→新」
  # awk length 在 macOS 按字节数 CJK,120 字=360 字节会误判;用 python 按字符数
  n=$((n+1)); grep '^　理由：' "$LP" | python3 -c 'import sys;sys.exit(any(len(l.rstrip())>140 for l in sys.stdin))' \
    || { echo "❌ lark-push render: R1 理由应 clip 到 120 字(台账备注不原样进群)"; fail=$((fail+1)); }
  n=$((n+1)); awk '/^\*\*✏️ 改/{f=1;next} /^\*\*/{f=0} f&&/→/{bad=1} END{exit bad}' "$LP" \
    || { echo "❌ lark-push render: 主卡「改」段不该再带「旧→新」,旧标题只留 R1"; fail=$((fail+1)); }
  # v3.2.1 卡片格式两条(09-07 用户直接指出「第一段有点乱」的两个成因)
  python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" --summary '第一段。\n\n第二段。' 2>/dev/null | grep -q '第一段。\\n' \
    && { echo "❌ 卡片格式(v3.2.1): summary 里的字面 \\n 应转成真换行,不能原样渲染"; fail=$((fail+1)); }
  python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" --summary '本轮撤 9 改 1 建 2。' 2>&1 >/dev/null | grep -q '计数自相矛盾' \
    || { echo "❌ 卡片格式(v3.2.1): summary 手写计数与台账不符时应报警(标题行「撤4」vs summary「撤9」)"; fail=$((fail+1)); }
  python3 "$D/lark-push.py" render 1788399480000 --fixture "$D/tests/lark-fixtures" --summary '本轮撤 4 改 1 建 2。' 2>&1 >/dev/null | grep -q '计数自相矛盾' \
    && { echo "❌ 卡片格式(v3.2.1): summary 计数与台账一致时不该报警(假阳性会训练人忽略告警)"; fail=$((fail+1)); }
  grep -q '未映射 reason_code' "$LP.err" && { echo "❌ lark-push 有未映射 reason_code(补 RC_HUMAN): $(cat "$LP.err")"; fail=$((fail+1)); }
else
  echo "❌ lark-push render 跑挂: $(tail -2 "$LP.err")"; fail=$((fail+1))
fi
# 秘密过滤反例:含凭证的文本必须被 SECRET_RE 拦住
n=$((n+1))
python3 -c "
import importlib.util,sys
sp=importlib.util.spec_from_file_location('lp','$D/lark-push.py');lp=importlib.util.module_from_spec(sp);sp.loader.exec_module(lp)
sys.exit(0 if lp.SECRET_RE.search('x api_key=abc') and lp.SECRET_RE.search('Authorization: Bearer sk1234567890abcd') else 1)
" || { echo "❌ SECRET_RE 未拦住凭证反例"; fail=$((fail+1)); }
rm -f "$LP" "$LP.err"


# lark-push 复审对账反例:①有写操作却无复审产物 → 必须 🚨 不合格(治「复审没跑却显示✔」的静默通过)
#                        ②干轮零写操作无复审 → 不得误报
n=$((n+1))
TD="/tmp/lark-nr.$$"; rm -rf "$TD"; cp -r "$D/tests/lark-fixtures" "$TD"; rm -rf "$TD/reports"
python3 "$D/lark-push.py" render 1788399480000 --fixture "$TD" 2>/dev/null | grep -q '复审 未跑' \
  || { echo "❌ 无复审产物时未报「复审 未跑」——静默通过风险"; fail=$((fail+1)); }
rm -rf "$TD"
n=$((n+1))
TD2="/tmp/lark-dry.$$"; rm -rf "$TD2"; mkdir -p "$TD2"
for f in actions.tsv snapshots.tsv circuit-log.tsv event-watch.tsv; do : > "$TD2/$f"; done
printf '# mode=刷新 ts=1788420000000 src=channels.json\nB0console\t✅(69条)\n' > "$TD2/checklists.log.tsv"
printf '1788420100000\n' > "$TD2/last-refresh.txt"; echo '{"topics":[]}' > "$TD2/b0-latest.json"
OUT2=$(python3 "$D/lark-push.py" render 1788420000000 --fixture "$TD2" 2>/dev/null)
echo "$OUT2" | grep -q '本轮干轮' || { echo "❌ 干轮未显式声明「本轮干轮」"; fail=$((fail+1)); }
echo "$OUT2" | grep -q '复审 未跑' && { echo "❌ 干轮误报「复审 未跑」"; fail=$((fail+1)); }
rm -rf "$TD2"

# v3.4.2 裁决词换代:v3.0.9 起复审员写「处置OK／处置有误」,lark-push 只认「通过/挑战」→ 挑战数恒 0、零挑战连续 N 轮误报、「通过 0 条」
#   ①「处置有误」要计入挑战 ②本轮有「处置有误」则零挑战连续轮数归零(另放两份更早的全「处置OK」复审作对照,旧脚本会报连续 3 轮)
#   ③全「处置OK」时「通过 N 条」要数对。改写夹具时保留原 mtime——lark-push 按 mtime 认本轮复审
TD3="/tmp/lark-verb.$$"; rm -rf "$TD3"; cp -Rp "$D/tests/lark-fixtures" "$TD3"
python3 - "$TD3/reports" <<'PY'
import os, sys, glob
rd = sys.argv[1]
f = glob.glob(os.path.join(rd, 'review-*'))[0]; st = os.stat(f)
s = open(f, encoding='utf-8').read().replace('|通过|', '|处置OK|').replace('|挑战|', '|处置有误|')
open(f, 'w', encoding='utf-8').write(s); os.utime(f, (st.st_atime, st.st_mtime))
ok = ''.join(l.replace('|处置有误|', '|处置OK|') + '\n' for l in s.splitlines())
for i, name in enumerate(('review-1788200000000.md', 'review-1788300000000.md')):
    q = os.path.join(rd, name); open(q, 'w', encoding='utf-8').write(ok)
    t = st.st_mtime - 86400 * (2 - i); os.utime(q, (t, t))
PY
OUT3=$(python3 "$D/lark-push.py" render 1788399480000 --fixture "$TD3" 2>/dev/null)
n=$((n+1)); echo "$OUT3" | grep -q '挑战 1 条（逐条附处置）' || { echo "❌ 裁决词(v3.4.2): 「处置有误」应计入挑战"; fail=$((fail+1)); }
n=$((n+1)); echo "$OUT3" | grep -q '零挑战' && { echo "❌ 裁决词(v3.4.2): 本轮有「处置有误」,不该报零挑战连续轮数"; fail=$((fail+1)); }
python3 - "$TD3/reports" <<'PY'
import os, sys, glob
rd = sys.argv[1]
for q in glob.glob(os.path.join(rd, 'review-17882*')) + glob.glob(os.path.join(rd, 'review-17883*')):
    os.remove(q)
f = glob.glob(os.path.join(rd, 'review-*'))[0]; st = os.stat(f)
s = open(f, encoding='utf-8').read().replace('|处置有误|', '|处置OK|')
open(f, 'w', encoding='utf-8').write(s); os.utime(f, (st.st_atime, st.st_mtime))
PY
n=$((n+1)); python3 "$D/lark-push.py" render 1788399480000 --fixture "$TD3" 2>/dev/null | grep -q '挑战 0 条\*\*——通过 6 条' \
  || { echo "❌ 裁决词(v3.4.2): 全「处置OK」时应显示「通过 6 条」"; fail=$((fail+1)); }
rm -rf "$TD3"


# lark-push 入站解析:机器人自己的发言/已删除必须剔除,群主要被认出,post 富文本要解开
n=$((n+1))
python3 - <<'PYEOF' || { echo "❌ inbox_parse 行为不符"; fail=$((fail+1)); }
import importlib.util,os,sys
sp=importlib.util.spec_from_file_location('lp',os.path.expanduser('~/.trend-scout/lark-push.py'))
lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
o='ou_owner'
msgs=[
 {"msg_type":"text","content":"bot 自己发的","create_time":"t1","sender":{"id":"cli_x","sender_type":"app"}},
 {"msg_type":"text","content":"群主说的","create_time":"t2","sender":{"id":o,"sender_type":"user"}},
 {"msg_type":"post","content":'{"zh_cn":{"content":[[{"tag":"text","text":"富文本"}]]}}',"create_time":"t3","sender":{"id":"ou_b","sender_type":"user","name":"同事"}},
 {"msg_type":"text","content":"删了的","create_time":"t4","deleted":True,"sender":{"id":o,"sender_type":"user"}},
]
r=lp.inbox_parse(msgs,o)
assert len(r)==2, r
assert r[0][1]=='群主' and r[0][2]=='群主说的', r
assert r[1][1]=='同事' and r[1][2]=='富文本', r
PYEOF


# T3+ 漂移哨兵:两个告警必须响(超30字标题 / 枚举外 reason_code),且枚举取自 log-action.sh 而非推送自带
n=$((n+1))
python3 - <<'PYEOF' || { echo "❌ 漂移哨兵告警未按预期触发"; fail=$((fail+1)); }
import importlib.util,os,sys,json,tempfile,shutil,subprocess
D=os.path.expanduser('~/.trend-scout')
sp=importlib.util.spec_from_file_location('lp',os.path.join(D,'lark-push.py'))
lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
assert len(lp.enum_rcs())==46, ('枚举应从 log-action.sh 解析到 46 项(v3.7.0 加 纠错-自纠;11-02 加 改数字-回落;11-13 加 归因-伪诱因)', len(lp.enum_rcs()))
T=tempfile.mkdtemp()
shutil.copytree(os.path.join(D,'tests/lark-fixtures'), T, dirs_exist_ok=True)
shutil.copy2(os.path.join(D,'log-action.sh'), T)
open(os.path.join(T,'actions.tsv'),'a').write(
 "1788400450000\tcreate\t19001\t有诱因-多源\t长标题\n1788400460000\tcull\t19002\t自造撤因ABC\t枚举外\n")
f=os.path.join(T,'b0-latest.json'); j=json.load(open(f))
j['topics'].append({"id":19001,"domain":"crypto","title":"英伟达认购联发科可转债并深化合作，MediaTek Inc.涨9.9%","status":0,"created_at":"2026-09-03 09:50:00"})
json.dump(j,open(f,'w',encoding='utf-8'),ensure_ascii=False)
open(os.path.join(T,'last-refresh.txt'),'w').write("1788399480000\n1788400500000\n")
r=lp.Round(T,1788399480000,'round','',{'deploy_source':'t'}); r.load(win_from=0)
d=r.drift()
assert d['title_max']==35 and len(d['over'])==1, d
assert d['rc_new']==['自造撤因ABC'], d
shutil.rmtree(T)
PYEOF


# v3.0.4 周报门禁反例:缺四问任一段 → FAIL;本周 rulefix 版本号周报没提 → FAIL;齐全 → PASS
n=$((n+1))
TW="/tmp/wv.$$"; mkdir -p "$TW"
printf '%s\n' '# 周复盘' '## ① 用户点名：0 次' '## ② 团队打回率：0/1' '## ③ 撤题 1 条' '## ④ 复审员挑战 0 次' '## ⑤ 返工率：0/1' '## 规则体积：gates.md 100KB' '## 规则卫生' '本周无' '## ① 过期' '无' '## ② 矛盾' '无' '## ③ 被实践推翻' '无' '## ④ 冗余' '无' '## 行数体检' '- 散点总数 0（基线 0）｜gates.md 100KB(提示)' '规则集本周无梳理项' '> 通读完成: SKILL.md 98｜gates.md 458｜channels.json 167｜data-quickref.md｜dedup-scoring.md｜fields-style.md｜review-agent.md｜scan-playbook.md｜weekly-review.md｜cards.md' > "$TW/full.md"
grep -v '^## ③ 被实践推翻' "$TW/full.md" > "$TW/miss.md"
sed 's/^- 散点总数.*/- gates.md 100KB \/ 112KB/' "$TW/full.md" > "$TW/kbonly.md"   # v3.4.4(P1-4) 只写 KB 不写散点 → 应 FAIL
printf '%s\t%s\t%s\t%s\t%s\n' "$(( $(date +%s) * 1000 - 3600000 ))" rulefix - 规则演进 'v9.9.9 测试用版本' > "$TW/actions.tsv"
: > "$TW/empty.tsv"
ACTIONS="$TW/empty.tsv" "$D/weekly-verify.sh" "$TW/full.md" >/dev/null 2>&1 || { echo "❌ weekly-verify: 齐全周报应 PASS"; fail=$((fail+1)); }
ACTIONS="$TW/empty.tsv" "$D/weekly-verify.sh" "$TW/miss.md" >/dev/null 2>&1 && { echo "❌ weekly-verify: 缺「③ 被实践推翻」段应 FAIL"; fail=$((fail+1)); }
n=$((n+1)); ACTIONS="$TW/empty.tsv" "$D/weekly-verify.sh" "$TW/kbonly.md" >/dev/null 2>&1 && { echo "❌ weekly-verify(v3.4.4): 行数体检只有 KB 没有散点数应 FAIL(口径已定为散点)"; fail=$((fail+1)); }
ACTIONS="$TW/actions.tsv" "$D/weekly-verify.sh" "$TW/full.md" >/dev/null 2>&1 && { echo "❌ weekly-verify: 台账有 rulefix v9.9.9 而周报未提应 FAIL"; fail=$((fail+1)); }
echo '回看 v9.9.9：无冲突' >> "$TW/full.md"
ACTIONS="$TW/actions.tsv" "$D/weekly-verify.sh" "$TW/full.md" >/dev/null 2>&1 || { echo "❌ weekly-verify: 补上 v9.9.9 后应 PASS"; fail=$((fail+1)); }
rm -rf "$TW"
# v3.0.4 send 门禁:review-verify 无 PASS 记录的 run_ts 必须拒发(_rv_passed 直测,不真发)
n=$((n+1))
python3 - <<'PYEOF' || { echo "❌ send 门禁 _rv_passed 行为不符"; fail=$((fail+1)); }
import importlib.util,os,tempfile
D=os.path.expanduser('~/.trend-scout')
sp=importlib.util.spec_from_file_location('lp',os.path.join(D,'lark-push.py')); lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
T=tempfile.mkdtemp(); lp.REAL=T
assert lp._rv_passed(123)==False, '无日志应拒'
open(os.path.join(T,'review-verify.log.tsv'),'w').write("1\t123\tFAIL\tx\n1\t123\tPASS\ty\n1\t456\tFAIL\tz\n")
assert lp._rv_passed(123)==True, '最近一次 PASS 应放行'
assert lp._rv_passed(456)==False, '最近一次 FAIL 应拒'
PYEOF


# v3.0.6 台账自取契约:无 LEDGER 行 / 漏写操作id / 自取到却没审 / 台账有note而报0 → 全 FAIL;齐全 → PASS
n=$((n+1))
TR="/tmp/rv.$$"; mkdir -p "$TR"; T0=1788600000000
{ printf '%s\tcreate\t11001\t有诱因-多源\tx\t-\n' "$T0"
  printf '%s\tcull\t11002\t灌水-KOL观点\ty\t-\n' "$T0"
  printf '%s\tnote\t-\t自审发现\t七查\t-\n' "$T0"; } > "$TR/a.tsv"
mk(){ printf '%s\nAUDITED=2\nSAMPLED=11001,11002\n11001|通过|自检:原句A\n11002|通过|自检:原句B\n' "$1" > "$TR/$2"; }
mk 'LEDGER=3|1|11001,11002' ok.txt            # 齐全
mk 'LEDGER=999|1|11001,11002' win.txt         # 窗口错(报 999 行,实 3 行)
mk 'X=1'                    noled.txt          # 无 LEDGER
mk 'LEDGER=3|1|11001'       missid.txt         # 漏写操作 id 11002
mk 'LEDGER=3|0|11001,11002' note0.txt          # 台账有 note 却报 0
printf 'LEDGER=4|1|11001,11002,19999\nAUDITED=2\nSAMPLED=11001,11002\n11001|通过|自检:A\n11002|通过|自检:B\n' > "$TR/unaudited.txt"  # 自取到 19999 却无裁决行
# v3.0.8:全角冒号「自检：」必须与半角等价——中文输出天然写全角,09-04 实跑 5 条真自检被判 0 条,判据形状歧视了正确行为
printf 'LEDGER=3|1|11001,11002\nAUDITED=2\nSAMPLED=11001,11002\n11001|通过|自检：原句A\n11002|通过|自检：原句B\n' > "$TR/fullwidth.txt"
# v3.0.9:裁决词歧义哨兵——判「挑战」却通篇肯定词=它其实在支持我的处置,须 WARN 但不阻断(exit 仍 0)
printf 'LEDGER=3|1|11001,11002\nAUDITED=2\nSAMPLED=11001,11002\n11001|挑战|自检：张冠李戴确实,撤得准确\n11002|通过|自检：原句B\n' > "$TR/susverb.txt"
# v3.4.1:SAMPLED= 取末条——复审员 append-only,首条清单漏 id 而末条补齐时必须以末条为准(09-10 实证 head -1 逼出 2 趟纯格式重跑)
printf 'LEDGER=3|1|11001,11002\nAUDITED=2\nSAMPLED=11001\n11001|处置OK|自检:原句A\n11002|处置OK|自检:原句B\nSAMPLED=11001,11002\n' > "$TR/sampdup.txt"
# v3.3.9:REPORTS_DIR/CHECKLOG 注入,否则回归会把假复审文件 cp 进真 reports/、把真 checklists.log 当上界
printf 'ts=%s\n' "$((T0+1000))" > "$TR/cl.tsv"                        # 假「下一轮」起点=T0+1s
printf '%s\tcreate\t11003\t有诱因-多源\t下一轮的题\t-\n' "$((T0+2000))" >> "$TR/a.tsv"   # 下一轮的写操作,不该算进本轮
# retro1103:SAMPLED 带括号注释(10000003452(EVGO))须剥掉再匹配,否则 grep 报错、自检被少计
printf 'LEDGER=3|1|11001,11002\nAUDITED=2\nSAMPLED=11001(甲),11002（乙）\n11001|处置OK|自检:原句A\n11002|处置OK|自检:原句B\n' > "$TR/sampnote.txt"
for c in "sampnote.txt:0" "ok.txt:0" "noled.txt:1" "missid.txt:1" "note0.txt:1" "unaudited.txt:1" "win.txt:1" "fullwidth.txt:0" "susverb.txt:0" "sampdup.txt:0"; do
  f="${c%%:*}"; want="${c##*:}"
  ACTIONS="$TR/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$T0" "$TR/$f" >/dev/null 2>&1; got=$?
  [ "$got" = "$want" ] || { echo "❌ review-verify[$f]: 期望 exit $want 得到 $got"; fail=$((fail+1)); }
done
# v3.6.1:演练新建题占位题号 NEW-<k> 必须能过台账自取契约(第 44 轮卡在 tr -dc 0-9 把 NEW-1 截成 1)
mkdir -p "$TR/drill"; printf '%s\tcreate\tNEW-1\t有诱因-多源\t演练\t→x\n%s\tupdate\t11001\t改数字-定稿\t演练\ta→b\n' "$T0" "$T0" > "$TR/drill/a.tsv"
printf 'LEDGER=2|0|11001,NEW-1\nAUDITED=2\nSAMPLED=11001,NEW-1\n11001|处置OK|自检:A\nNEW-1|处置OK|自检:B\n' > "$TR/drill/r.txt"
ACTIONS="$TR/drill/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$T0" "$TR/drill/r.txt" >/dev/null 2>&1 \
  || { echo "❌ review-verify: 演练占位题号 NEW-1 应能过台账自取契约(v3.6.1)"; fail=$((fail+1)); }
ACTIONS="$TR/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$T0" "$TR/win.txt" 2>&1 | grep -q '窗口错' \
  || { echo "❌ review-verify: 窗口错应报「窗口错」根因,不应被「无裁决行」噪音淹掉"; fail=$((fail+1)); }
ACTIONS="$TR/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$T0" "$TR/susverb.txt" 2>&1 | grep -q '裁决词存疑' \
  || { echo "❌ review-verify: 判「挑战」却理由含肯定词,应报「裁决词存疑」哨兵(v3.0.9)"; fail=$((fail+1)); }
grep -q 'PASS' "$TR/log.tsv" || { echo "❌ review-verify 未落 PASS 到 RVLOG"; fail=$((fail+1)); }
# v3.3.9 ① PASS 即归档到 REPORTS_DIR/review-<run_ts>.md(lark-push 只认这个路径;09-03 起复审落在 /tmp,群里连报 6 天「复审未跑」)
n=$((n+1)); [ -f "$TR/reports/review-$T0.md" ] || { echo "❌ review-verify[归档]: PASS 后应 cp 到 REPORTS_DIR/review-<run_ts>.md"; fail=$((fail+1)); }
# v3.3.9 时间上界:a.tsv 里 T0+2s 的 11003 属下一轮(cl.tsv 说下一轮 T0+1s 开始),不带上界会把它算进来判「未覆盖」
n=$((n+1)); ACTIONS="$TR/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$T0" "$TR/ok.txt" 2>&1 | grep -q '11003' \
  && { echo "❌ review-verify[上界]: 下一轮起点之后的写操作 11003 不该算进本轮"; fail=$((fail+1)); }
n=$((n+1)); ACTIONS="$TR/a.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="/dev/null" "$D/review-verify.sh" "$T0" "$TR/ok.txt" >/dev/null 2>&1 \
  && { echo "❌ review-verify[上界·对照]: 没有下一轮起点时应无上界,11003 应被算进来并报未覆盖(否则上一条用例是假通过)"; fail=$((fail+1)); }
# v3.7.20(11-02):干轮(0 写操作)也要归档,否则 Evose challenges 找不到 review-<ts>.md 停下(11-02 演练看门一那轮卡 57 分钟)
n=$((n+1)); : > "$TR/empty.tsv"; rm -f "$TR/reports/review-$((T0+5)).md"
ACTIONS="$TR/empty.tsv" RVLOG="$TR/log.tsv" REPORTS_DIR="$TR/reports" CHECKLOG="$TR/cl.tsv" "$D/review-verify.sh" "$((T0+5))" "$TR/ok.txt" >/dev/null 2>&1 \
  && [ -f "$TR/reports/review-$((T0+5)).md" ] || { echo "❌ review-verify[干轮归档]: 0 写操作 PASS 也应 cp 到 REPORTS_DIR/review-<run_ts>.md"; fail=$((fail+1)); }
# v3.7.20(11-02):event.sh defer——未到时点延后:状态仍待办(不带 --since 照列),due --since <run_ts> 扣出并报 DEFERRED
n=$((n+1)); EVD=$(mktemp -d); td=$(date +%F)
for k in 事件甲 事件乙; do EV_DIR="$EVD" "$D/event.sh" add "$td" review "$k" 23:00 - 测试 >/dev/null; done
S0=$(date +%s)000; EV_DIR="$EVD" "$D/event.sh" defer 事件甲 "未到时点 23:00" >/dev/null
o=$(EV_DIR="$EVD" "$D/event.sh" due --since "$S0"); o2=$(EV_DIR="$EVD" "$D/event.sh" due)
echo "$o" | grep -q '^DUE=1$' && echo "$o" | grep -q '^DEFERRED=1$' && echo "$o2" | grep -q '^DUE=2$' && ! echo "$o2" | grep -q DEFERRED \
  || { echo "❌ event.sh defer: 期望 due --since 得 DUE=1/DEFERRED=1、不带 --since 得 DUE=2: $(echo "$o" | tail -2 | tr '\n' ' ')"; fail=$((fail+1)); }
rm -rf "$EVD"
rm -rf "$TR"

# v3.1.0 b0-cull.py 的 meme 铁律:crypto 小币 + rc 不在三类 → 必须拦下转人工;主流标的/tradfi/三类rc → 放行
n=$((n+1))
BT="/tmp/bc.$$"; mkdir -p "$BT"
cat > "$BT/b0.json" <<'JSON'
[{"id":9001,"domain":"crypto","title":"SHROOM市值逼近2000万美元，短线风险加剧？","keywords":"SHROOM","status":0},
 {"id":9002,"domain":"crypto","title":"LTC突破DSMA 200，短线能否延续反弹？","keywords":"LTC","status":0},
 {"id":9003,"domain":"tradfi","title":"某股涨7%","keywords":"XYZ","status":0}]
JSON
# v3.1.4 改用环境变量注入,不再 mock os.path.expanduser——旧写法的 lambda 里调用了自己刚替换掉的
#   os.path.expanduser,只有一次调用时侥幸没暴露;加了 majors.json 后变成第二次调用即无限递归。
BC_OUT=$(cd "$D" && B0JSON="$BT/b0.json" python3 - <<'PYEOF'
import sys,os,json,importlib.util
spec=importlib.util.spec_from_file_location("bc",os.path.expanduser("~/.trend-scout/b0-cull.py"))
m=importlib.util.module_from_spec(spec)
import unittest.mock as um
with um.patch.dict(sys.modules,{"b0_fetch":um.MagicMock()}):
    spec.loader.exec_module(m)
print("A",sorted(m._meme_guard(["9001","9002","9003"],"缺价格腿")))
print("B",sorted(m._meme_guard(["9001"],"事实错误-数字")))
print("C",sorted(m._meme_guard(["9999"],"缺价格腿")))
print("D",sorted(m._meme_guard(["9001"],"灌水-KOL观点")))
PYEOF
)
echo "$BC_OUT" | grep -q "^A \['9001'\]$" || { echo "❌ b0-cull meme闸: 应只拦 9001(小币),放行 9002(LTC主流)/9003(tradfi);实得 $(echo "$BC_OUT"|grep '^A ')"; fail=$((fail+1)); }
echo "$BC_OUT" | grep -q "^B \[\]$"       || { echo "❌ b0-cull meme闸: rc 落三类时应全放行;实得 $(echo "$BC_OUT"|grep '^B ')"; fail=$((fail+1)); }
echo "$BC_OUT" | grep -q "^C \['9999'\]$" || { echo "❌ b0-cull meme闸: 快照里查不到的 id 应保守转人工;实得 $(echo "$BC_OUT"|grep '^C ')"; fail=$((fail+1)); }
echo "$BC_OUT" | grep -q "^D \[\]$" || { echo "❌ b0-cull meme闸(v3.1.1): 形态明确的撤因(灌水-KOL观点)不该走 meme 闸,应放行;实得 $(echo "$BC_OUT"|grep '^D ')"; fail=$((fail+1)); }
rm -rf "$BT"

# v3.1.2 log-action.sh 的 meme 闸判据=题目本身,不再看备注文本(自证式闸的根治)
n=$((n+1))
LT="/tmp/la.$$"; mkdir -p "$LT"
cat > "$LT/b0.json" <<'JSON'
[{"id":99990101,"domain":"crypto","title":"SHROOM市值2000万","keywords":"SHROOM","status":0},
 {"id":99990102,"domain":"crypto","title":"LTC突破均线","keywords":"LTC","status":0},
 {"id":99990103,"domain":"crypto","title":"华为小米联手布局Web3？","keywords":"华为,小米","status":0},
 {"id":99990104,"domain":"crypto","title":"牛来还能涨吗？","keywords":"币安,牛来","status":0}]
JSON
# ①备注里出现「meme」但 rc 是形态类(灌水-KOL观点)→ 必须放行(09-06 实录:解释「这不是meme」反被拦)
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json"   "$D/log-action.sh" cull 99990101 灌水-KOL观点 '这不是 meme 题,纯 KOL 口水' >/dev/null 2>&1
la1=$?
# v3.1.3 泄漏哨兵:测试写操作绝不能落进真台账/真快照(09-06 实录两次污染;v3.1.9 改用 9999xxxx 专用段)
grep -qE "9999[0-9]{4}" "$D/actions.tsv" "$D/snapshots.tsv" "$D/actions-rejected.tsv" "$D/check-hits.tsv" 2>/dev/null \
  && { echo "❌ 回归污染生产数据:测试 id(9999xxxx 段)出现在真 actions.tsv/snapshots.tsv/actions-rejected.tsv——检查被测脚本的写入路径是否全部可注入。**测试 id 一律用 9999xxxx 八位段**:v3.1.3 只盯死 9101/9102,09-07 手工验证用 99999 又污染一次;改成通用的 9xxx 又误报(snapshots 里 id=9725 是 08-22 的真题)——按「像不像测试 id」猜必然两头错,只能约定专用段"; fail=$((fail+1)); }
# ②crypto 小币 + rc=缺价格腿 + 备注不含三类 → 必须拒
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json"   "$D/log-action.sh" cull 99990101 缺价格腿 '去掉问号后无可核事件' >/dev/null 2>&1
la2=$?
# ③主流标的 LTC + rc=缺价格腿 → 必须放行
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json"   "$D/log-action.sh" cull 99990102 缺价格腿 '技术指标穿越非可核事件' >/dev/null 2>&1
la3=$?
[ "$la1" = "0" ] || { echo "❌ log-action meme闸(v3.1.2): 备注含「meme」但 rc 为形态类应放行(exit 0),实得 $la1"; fail=$((fail+1)); }
[ "$la2" = "1" ] || { echo "❌ log-action meme闸(v3.1.2): crypto 小币+缺价格腿撤因应拒(exit 1),实得 $la2"; fail=$((fail+1)); }
[ "$la3" = "0" ] || { echo "❌ log-action meme闸(v3.1.2): 主流标的 LTC 不受小市值铁律约束,应放行(exit 0),实得 $la3"; fail=$((fail+1)); }
# v3.4.4(P0-2) 作用域:无代币标的的题(华为,小米)不受铁律 → 放行;中文名代币(牛来)仍受保护 → 拒;两个工具判定一致
n=$((n+1))
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990103 缺价格腿 '去掉问号后无可核事件' >/dev/null 2>&1
[ "$?" = "0" ] || { echo "❌ meme闸作用域(v3.4.4): 关键词无代币(华为,小米)的题不该被 meme 铁律拦"; fail=$((fail+1)); }
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990104 缺价格腿 '去掉问号后无可核事件' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ meme闸作用域(v3.4.4): 中文名代币(牛来)仍应受 meme 铁律保护"; fail=$((fail+1)); }
B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 缺价格腿 --note x --dry 99990103 99990104 2>&1 | grep -q '✋ 99990104' && ! B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 缺价格腿 --note x --dry 99990103 99990104 2>&1 | grep -q '✋ 99990103' \
  || { echo "❌ meme闸作用域(v3.4.4): b0-cull 与 log-action 判定不一致(应拦 99990104 放 99990103)"; fail=$((fail+1)); }
# v3.1.4(提案5-3) 单一事实源:改 majors.json 必须同时改变 b0-cull.py 与 log-action.sh 两处的行为。
#   造一份只含 ZZZTEST 的白名单 → LTC 从"主流"变成"小币",两个工具都应改判,证明没有内嵌副本残留。
printf '{"majors":["ZZZTEST"]}' > "$LT/m.json"
MAJORS_JSON="$LT/m.json" B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 缺价格腿 --note x --dry 99990102 2>&1 | grep -q '✋ 99990102' \
  || { echo "❌ 单一事实源(b0-cull): 换掉 majors.json 后 LTC 应改判为小币被拦,说明仍有内嵌副本"; fail=$((fail+1)); }
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" MAJORS_JSON="$LT/m.json" \
  "$D/log-action.sh" cull 99990102 缺价格腿 '技术指标穿越非可核事件' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ 单一事实源(log-action): 换掉 majors.json 后 LTC 应改判为小币被拒,说明仍有内嵌副本"; fail=$((fail+1)); }
rm -rf "$LT"
# v3.6.1(09-29 用户裁决＋留撤测评) 疑问句①对 meme 照常生效:小币+疑问句-悬念 两个工具都必须放行,缺价格腿仍拦
n=$((n+1))
LT="/tmp/la361.$$"; mkdir -p "$LT"
printf '[{"id":99990105,"domain":"crypto","title":"SHROOM情绪升温，能否引爆新行情？","keywords":"SHROOM","status":0}]' > "$LT/b0.json"
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990105 疑问句-悬念 '去掉问号后只剩悬念' >/dev/null 2>&1
[ "$?" = "0" ] || { echo "❌ v3.6.1 疑问句①对 meme 生效: log-action 应放行 小币+疑问句-悬念"; fail=$((fail+1)); }
B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 疑问句-悬念 --note x --dry 99990105 2>&1 | grep -q '✋ 99990105' \
  && { echo "❌ v3.6.1 疑问句①对 meme 生效: b0-cull 不应拦 小币+疑问句-悬念"; fail=$((fail+1)); }
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990105 缺价格腿 '无价格反应' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ v3.6.1 边界: 小币+缺价格腿 仍应被 meme 铁律拒"; fail=$((fail+1)); }
# v3.6.2(09-30 用户定收紧 meme 铁律):四查全否才放行;任一为 ✓ 或缺四查行 → 拒;新撤因在枚举内;机械撤不收新撤因
n=$((n+1))
LA="ACTIONS=$LT/a.tsv SNAPSHOTS=$LT/s.tsv REJ=$LT/rej.tsv B0JSON=$LT/b0.json"
env $LA "$D/log-action.sh" cull 99990105 缺诱因-未达线 '四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ 24h涨5%无事件' >/dev/null 2>&1
[ "$?" = "0" ] || { echo "❌ v3.6.2 四查: 小币+缺诱因-未达线+四查全否 应放行"; fail=$((fail+1)); }
env $LA "$D/log-action.sh" cull 99990105 缺价格腿 '四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ 纯公告无价格' >/dev/null 2>&1
[ "$?" = "0" ] || { echo "❌ v3.6.2 四查: 小币+缺价格腿+四查全否 应放行"; fail=$((fail+1)); }
env $LA "$D/log-action.sh" cull 99990105 缺诱因-未达线 '四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✓ 上线币安现货' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ v3.6.2 四查: 硬事件✓ 应拒(该留)"; fail=$((fail+1)); }
env $LA "$D/log-action.sh" cull 99990105 缺诱因-未达线 '24h只涨5%没有事件所以撤掉' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ v3.6.2 四查: 缺四查行 应拒"; fail=$((fail+1)); }
"$D/log-action.sh" codes 2>/dev/null | grep -qx '  缺诱因-未达线' || { echo "❌ v3.6.2: 撤因枚举缺「缺诱因-未达线」"; fail=$((fail+1)); }
B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 缺诱因-未达线 --note x --dry 99990105 2>&1 | grep -q '不是机械撤允许的撤因' || { echo "❌ v3.6.2: b0-cull 机械撤不应接受「缺诱因-未达线」"; fail=$((fail+1)); }


# v3.1.5(提案5-2) 机审⑥ 价格动作前置检查:形态命中但有真实价格动作的,必须剔出撤候选(A闸「一律留」优先)
n=$((n+1))
QT="/tmp/q.$$"; mkdir -p "$QT"
cat > "$QT/b0.json" <<'JSON'
{"total":2,"topics":[
 {"id":8001,"domain":"crypto","title":"ARB链上日费收入创新高，7日累计达11亿美元","keywords":"ARB","status":2,"created_at":"2026-09-06 18:00:00"},
 {"id":8002,"domain":"crypto","title":"某小币市值突破2000万美元，热度升温","keywords":"NOSUCHCOIN","status":2,"created_at":"2026-09-06 18:00:00"}]}
JSON
printf '{"ARB":44.38}' > "$QT/q.json"
QO=$(QUOTES_JSON="$QT/q.json" "$D/b0-audit.sh" "$QT/b0.json" --since 0 2>&1)
echo "$QO" | grep -q '✋ 8001' \
  || { echo "❌ 机审⑥价格前置(v3.1.5): ARB 24h+44% 应被剔出撤候选并标 ✋,实际仍在候选里(09-06 误撤实录的正是这条)"; fail=$((fail+1)); }
echo "$QO" | grep -qE "b0-cull.py --rc 灌水-vanity指标 --note '机审⑥形态命中' 8002$" \
  || { echo "❌ 机审⑥价格前置(v3.1.5): 无价格动作的 8002 应仍留在撤候选命令行里"; fail=$((fail+1)); }
echo "$QO" | grep -q '8001' && echo "$QO" | grep -E "机械撤候选' .*8001" >/dev/null \
  && { echo "❌ 机审⑥价格前置(v3.1.5): 8001 不该出现在可执行的 b0-cull 命令行里"; fail=$((fail+1)); }
QE=$(QUOTES_JSON=/dev/null "$D/b0-audit.sh" "$QT/b0.json" --since 0 2>&1)
echo "$QE" | grep -q '行情表为空' \
  || { echo "❌ 机审⑥价格前置(v3.1.5): 行情拉不到时必须输出降级警告,否则会静默退化成旧行为"; fail=$((fail+1)); }
echo "$QE" | grep -q '✋ 8001' \
  && { echo "❌ 机审⑥价格前置(v3.1.5): 行情为空时不得声称某条有价格动作"; fail=$((fail+1)); }
# v3.4.9(09-20 Evose 第十六轮实录):行情表为空时 ⑥ 仍吐出可直接粘贴执行的 b0-cull 命令,
#   ⚠️ 只是段尾一行提示 —— 等于把「没查过」的候选做成一键撤题。现在这种候选照列但不进命令行。
echo "$QE" | grep -q "b0-cull.py --rc" \
  && { echo "❌ 机审⑥降级(v3.4.9): 行情表为空时不得给出可执行的 b0-cull 批量命令"; fail=$((fail+1)); }
echo "$QE" | grep -q '未检查' \
  || { echo "❌ 机审⑥降级(v3.4.9): 行情表为空时每条候选都要标「未检查」"; fail=$((fail+1)); }
echo "$QE" | grep -q '8002' \
  || { echo "❌ 机审⑥降级(v3.4.9): 没查成不等于不列,候选本身仍要留在清单里(v3.1.5「仍留在候选里但标注」)"; fail=$((fail+1)); }
echo "$QE" | grep -qE '^AUDIT:.*机械撤候选=2\(未检查=2\)' \
  || { echo "❌ 机审⑥降级(v3.4.9): AUDIT 行要带「未检查」计数,否则只看汇总看不出这轮降级过"; fail=$((fail+1)); }
rm -rf "$QT"

# v3.4.9(09-20 Evose 第十六轮实录):③ 聚簇按 keywords 的大写键归组,同一条题的 ZAMA/Zama
#   会 upper 成同一个键被 append 两次,于是出 [ZAMA]×2 而两行是同一个 id,聚簇组也虚增。
n=$((n+1))
CT="/tmp/c.$$"; mkdir -p "$CT"
cat > "$CT/b0.json" <<'JSON'
{"total":2,"topics":[
 {"id":8101,"domain":"crypto","title":"Zama机密金库扩至21个，ZAMA涨29%","keywords":"ZAMA,Zama,Morpho,机密金库","status":0,"created_at":"2026-09-06 18:00:00"},
 {"id":8102,"domain":"crypto","title":"某币收涨3%，报1美元","keywords":"OTHER","status":0,"created_at":"2026-09-06 18:00:00"}]}
JSON
CO=$("$D/b0-audit.sh" "$CT/b0.json" --since 0 2>&1)
echo "$CO" | grep -q '\[ZAMA\] ×2' \
  && { echo "❌ ③聚簇去重(v3.4.9): 同一条题的 ZAMA/Zama 不该聚成 ×2 的假簇"; fail=$((fail+1)); }
echo "$CO" | grep -qE '^AUDIT:.*聚簇组=0' \
  || { echo "❌ ③聚簇去重(v3.4.9): 只有一条题时聚簇组应为 0"; fail=$((fail+1)); }
rm -rf "$CT"

# v3.4.10(用户 09-20 裁定) 价格腿 = 涨跌%/涨停/翻倍/腰斩 或 静态报价「报X」。
#   09-20 Evose 第十六轮审核员指出 12497「ZEC报1470美元」、12449「UNI报8.77美元」带价格腿却进了 ⑥。
#   「财报/季报/年报/月报/周报/日报 + 数字」不是报价,不得误判成价格腿。
n=$((n+1))
for _t in "某链宣布集成某协议，XYZ报3.5美元" "某协议升级，ABC收报223.54美元" "某链推出新功能，DEF报91.6"; do
  python3 "$D/lint.py" title "$_t" >/dev/null 2>&1
  python3 - "$D" "$_t" <<'PYQ' || { echo "❌ 价格腿(v3.4.10): 「$_t」含静态报价,junk_class 应返回 None"; fail=$((fail+1)); }
import importlib.util,sys
spec=importlib.util.spec_from_file_location('lint',sys.argv[1]+'/lint.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.exit(0 if m.junk_class(sys.argv[2]) is None else 1)
PYQ
done
for _t in "某公司宣布季报3.5亿美元" "某公司宣布财报2亿美元"; do
  python3 - "$D" "$_t" <<'PYQ' || { echo "❌ 价格腿(v3.4.10): 「$_t」的「季报/财报+数字」不是报价,应仍判为灌水候选"; fail=$((fail+1)); }
import importlib.util,sys
spec=importlib.util.spec_from_file_location('lint',sys.argv[1]+'/lint.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.exit(0 if m.junk_class(sys.argv[2]) is not None else 1)
PYQ
done
# PCT 不得被放宽:tradfi「报X美元」无涨跌% 时不该触发「时段前缀」闸
python3 "$D/lint.py" title "某股收报223.54美元" tradfi 2>&1 | grep -q '时段前缀' \
  && { echo "❌ 价格腿(v3.4.10): 静态报价不该触发 tradfi 时段前缀闸(说明 PCT 被误放宽)"; fail=$((fail+1)); }

# v3.5.1(09-20 Evose 第十七轮机制空跑实证):log-action.sh 台账写入失败时必须炸,不许打✔。
#   旧版目录缺失时 stderr 报 No such file or directory、stdout 却打「✔ note 0 [留档]」且 EXIT=0,
#   整个跑单的强制力建立在「写操作一律走 log-action.sh」+双留档上,这个假成功把强制力掏空。
n=$((n+1))
LA="/tmp/la.$$"; mkdir -p "$LA"
_LAO=$(ACTIONS="$LA/nodir/actions.tsv" "$D/log-action.sh" note 0 留档 '回归:写入路径不存在' 2>/dev/null); _LAC=$?
[ "$_LAC" = "0" ] \
  && { echo "❌ 台账写入失败闸(v3.5.1): 写入路径不存在时退出码仍为 0(假成功)"; fail=$((fail+1)); }
echo "$_LAO" | grep -q '✔' \
  && { echo "❌ 台账写入失败闸(v3.5.1): 写入失败时 stdout 不得出现「✔」"; fail=$((fail+1)); }
# 正常路径必须不受影响
: > "$LA/actions.tsv"
_LAO2=$(ACTIONS="$LA/actions.tsv" SNAPSHOTS="$LA/snapshots.tsv" "$D/log-action.sh" note 0 留档 '回归:正常路径' 2>/dev/null); _LAC2=$?
[ "$_LAC2" = "0" ] \
  || { echo "❌ 台账写入失败闸(v3.5.1): 正常路径不该被改坏,退出码应为 0"; fail=$((fail+1)); }
grep -q '回归:正常路径' "$LA/actions.tsv" \
  || { echo "❌ 台账写入失败闸(v3.5.1): 正常路径下该行未真正写入 actions.tsv"; fail=$((fail+1)); }
rm -rf "$LA"

# v3.4.10(用户 09-20 定) okx 行情源不覆盖 tradfi,tradfi 撤候选从来没被价格验证过,不得给可执行批量命令
n=$((n+1))
FT="/tmp/f.$$"; mkdir -p "$FT"
cat > "$FT/b0.json" <<'JSON'
{"total":2,"topics":[
 {"id":8201,"domain":"tradfi","title":"某公司宣布与某厂商合作拓展数据中心","keywords":"ABCD","status":2,"created_at":"2026-09-06 18:00:00"},
 {"id":8202,"domain":"crypto","title":"某小币市值突破2000万美元，热度升温","keywords":"NOSUCHCOIN","status":2,"created_at":"2026-09-06 18:00:00"}]}
JSON
printf '{"ARB":44.38}' > "$FT/q.json"
FO=$(QUOTES_JSON="$FT/q.json" "$D/b0-audit.sh" "$FT/b0.json" --since 0 2>&1)
echo "$FO" | grep -qE "b0-cull.py --rc .* 8201" \
  && { echo "❌ tradfi 未验价(v3.4.10): tradfi 候选不得出现在可执行的 b0-cull 命令行里"; fail=$((fail+1)); }
echo "$FO" | grep -q '8201.*⚠️未检查' \
  || { echo "❌ tradfi 未验价(v3.4.10): tradfi 候选要标「未检查」"; fail=$((fail+1)); }
echo "$FO" | grep -qE "b0-cull.py --rc 灌水-vanity指标 --note '机审⑥形态命中' 8202$" \
  || { echo "❌ tradfi 未验价(v3.4.10): crypto 且标的不在行情表内的 8202 仍算查过,命令行不该受影响(09-06 规则)"; fail=$((fail+1)); }
rm -rf "$FT"

# v3.1.8 ②窗口题:crypto 的时效数字断言要判过期,tradfi 的价格定稿题不判(收盘价跨 session 才失效)
n=$((n+1))
WT="/tmp/wt.$$"; mkdir -p "$WT"
OLD=$(python3 - <<'PYEOF'
import datetime; print((datetime.datetime.now()-datetime.timedelta(hours=60)).strftime('%Y-%m-%d %H:%M:%S'))
PYEOF
)
cat > "$WT/b0.json" <<JSON
{"total":4,"topics":[
 {"id":7001,"domain":"crypto","title":"SLINK市值冲高至8000万美元后回撤","keywords":"SLINK","status":0,"created_at":"$OLD"},
 {"id":7002,"domain":"tradfi","title":"企业级SSD需求增长，SNDK收涨11.9%","keywords":"SNDK","status":0,"created_at":"$OLD"},
 {"id":7003,"domain":"crypto","title":"Circle Arc主网9月16日上线，USDC成唯一Gas资产","keywords":"CIRCLE","status":0,"created_at":"$OLD"},
 {"id":7004,"domain":"crypto","title":"ENA启动自动回购,达标后扩规模","keywords":"ENA","status":0,"created_at":"$OLD"}]}
JSON
WO=$(QUOTES_JSON=/dev/null "$D/b0-audit.sh" "$WT/b0.json" --since 0 2>&1 | sed -n '/② 窗口题/,/③ 同标的/p')
echo "$WO" | grep -q '7001' || { echo "❌ ②窗口题(v3.1.8): crypto 的时效数字断言(市值冲高至X)应判过期"; fail=$((fail+1)); }

# v3.4.8 盘中进行时:美股常规时段正开着时,②段必须多打一条「逐条拉盘中价」提示;休市/周末不得打
_v348(){ TS_NOW_UTC="$1" python3 -c "
import sys,os;sys.path.insert(0,os.path.expanduser('~/.trend-scout'));import lint;print(lint.us_session_open())"; }
[ "$(_v348 2026-09-18T14:36)" = "True" ]  || { echo "❌ v3.4.8: 周五10:36ET 应判盘中进行时"; fail=$((fail+1)); }
[ "$(_v348 2026-09-18T23:00)" = "False" ] || { echo "❌ v3.4.8: 周五19:00ET 盘后不应判盘中"; fail=$((fail+1)); }
[ "$(_v348 2026-09-18T13:00)" = "False" ] || { echo "❌ v3.4.8: 周五09:00ET 盘前不应判盘中"; fail=$((fail+1)); }
[ "$(_v348 2026-09-20T18:00)" = "False" ] || { echo "❌ v3.4.8: 周日不应判盘中"; fail=$((fail+1)); }
# v3.7.19 🔔 只列未跨 session 的收盘题(10-27 22:00 影子跑:10-23 的 CRDO/BE/COHR 被按盘中反涨撤)
_bf(){ TS_NOW_UTC="$1" python3 -c "
import sys,os;sys.path.insert(0,os.path.expanduser('~/.trend-scout'));import lint;print(lint.bell_fresh($2))"; }
[ "$(_bf 2026-10-27T14:01 95)" = "False" ] || { echo "❌ v3.7.19: 周二盘中 95h 老收盘题(10-23 建)不该进🔔"; fail=$((fail+1)); }
[ "$(_bf 2026-10-27T14:01 13)" = "True" ]  || { echo "❌ v3.7.19: 周二盘中 13h 题(周一收盘后建)应进🔔"; fail=$((fail+1)); }
[ "$(_bf 2026-10-26T14:01 40)" = "True" ]  || { echo "❌ v3.7.19: 周一盘中、上周五收盘后(22:00 UTC)建的题应进🔔"; fail=$((fail+1)); }
[ "$(_bf 2026-10-26T14:01 70)" = "False" ] || { echo "❌ v3.7.19: 周一盘中、上周五盘中建的题已跨过周五收盘"; fail=$((fail+1)); }
# v3.7.19 端到端:b0-audit 🔔 块只列上一交易日收盘后建的收盘题,老题合并成一行计数(10-28 补用例)
V319="/tmp/v319.$$"; mkdir -p "$V319"
cat > "$V319/b0.json" <<'JSON'
{"total":2,"topics":[{"id":9911,"domain":"tradfi","title":"某股财报超预期，收涨12%","keywords":"XA","status":0,"created_at":"2026-10-27 08:00:00"},{"id":9912,"domain":"tradfi","title":"某股业绩不及预期，收跌9.5%","keywords":"XB","status":0,"created_at":"2026-10-23 20:00:00"}]}
JSON
n=$((n+1)); V9=$(TS_NOW_UTC=2026-10-27T14:01 "$D/b0-audit.sh" "$V319/b0.json" --since 0 2>&1)
BL9=$(echo "$V9" | awk '/🔔/{f=1;next} f&&/^     /{print;next} f{exit}')   # 只看 🔔 块,别让 >48h 列表里的同 id 蒙混
{ echo "$BL9" | grep -q '· 9911' && ! echo "$BL9" | grep -q '· 9912' && echo "$V9" | grep -q '另 1 条收盘题建于上一交易日收盘前'; } \
  || { echo "❌ v3.7.19: 🔔 应只列 9911(周一收盘后建),9912(上周五建)合并为一行计数"; fail=$((fail+1)); }
rm -rf "$V319"
# v3.5.3 覆盖漏洞回归:🔔 必须覆盖 <48h 的 tradfi 收盘价题(09-21 实证 BE 13h 被漏)
V352="/tmp/v352.$$"; mkdir -p "$V352"
cat > "$V352/b0.json" <<'JSON'
{"total":1,"topics":[{"id":9901,"domain":"tradfi","title":"某股纳入指数今日生效，收跌5.4%","keywords":"XX","status":0,"created_at":"2026-09-21 09:00:00"}]}
JSON
VO=$(TS_NOW_UTC=2026-09-21T14:37 "$D/b0-audit.sh" "$V352/b0.json" --since 0 2>&1)
echo "$VO" | awk '/🔔/{f=1;next} f&&/^     /{print;next} f{exit}' | grep -q '· 9901' || { echo "❌ v3.5.3: 盘中 🔔 必须列出 <48h 的 tradfi 收盘价题(9901 仅 13h)"; fail=$((fail+1)); }
VW=$(TS_NOW_UTC=2026-09-20T14:37 "$D/b0-audit.sh" "$V352/b0.json" --since 0 2>&1)
echo "$VW" | grep -q '🔔' && { echo "❌ v3.5.3: 周日不得打 🔔"; fail=$((fail+1)); }
rm -rf "$V352"
echo "$WO" | grep -qE '^  7002' && { echo "❌ ②窗口题(v3.1.8): tradfi 价格定稿题不该被判过期(收盘价要跨 session 才失效),应只列在边界说明里"; fail=$((fail+1)); }
echo "$WO" | grep -q '本段不判它们过期' || { echo "❌ ②窗口题(v3.1.8): tradfi 那批必须显式列出边界说明,否则等于静默漏掉"; fail=$((fail+1)); }
echo "$WO" | grep -q '7003' && { echo "❌ ②窗口题: 带明确日期锚的预告题(9月16日)不该判过期"; fail=$((fail+1)); }
echo "$WO" | grep -q '7004' && { echo "❌ ②窗口题: 无时效断言的永真描述不该判过期"; fail=$((fail+1)); }
rm -rf "$WT"

# v3.1.9 action × rc 组合合法性:rc 在全集内还不够,还得属于该 action 那一组
n=$((n+1))
AT="/tmp/ax.$$"; mkdir -p "$AT"
_la(){ ACTIONS="$AT/a.tsv" SNAPSHOTS="$AT/s.tsv" REJ="$AT/r.tsv" B0JSON="$AT/nope.json" "$D/log-action.sh" "$@" >/dev/null 2>&1; echo $?; }
# 注:下面几条用的备注都要 ≥12 字符,否则会先被 v3.2.0 的备注实质性闸拦掉,测不到组合校验
[ "$(_la update 99991001 反转错向 '组合校验用的长备注' '-')" = "1" ] || { echo "❌ action×rc(v3.1.9): update 用撤题 rc「反转错向」应拒(09-07 复审员实际抓到的那条)"; fail=$((fail+1)); }
[ "$(_la update 99991001 改归因 '组合校验用的长备注' '-')" = "0" ] || { echo "❌ action×rc(v3.1.9): update 用改题 rc「改归因」应放行"; fail=$((fail+1)); }
[ "$(_la cull 99991001 反转错向 '组合校验用的长备注')" = "0" ]     || { echo "❌ action×rc(v3.1.9): cull 用撤题 rc「反转错向」应放行"; fail=$((fail+1)); }
[ "$(_la cull 99991001 改归因 '组合校验用的长备注')" = "1" ]       || { echo "❌ action×rc(v3.1.9): cull 用改题 rc「改归因」应拒"; fail=$((fail+1)); }
# v3.4.4(P0-1) locale 无关:同一条备注在 UTF-8 locale 下判定必须与 C 下一致(周报经 python 跑回归时继承 UTF-8,曾假失败 7 项)
n=$((n+1)); [ "$(LC_ALL=en_US.UTF-8 _la cull 99991001 反转错向 '组合校验用的长备注')" = "0" ] \
  || { echo "❌ 备注长度闸 locale 依赖(v3.4.4): en_US.UTF-8 下 9 个汉字(27 字节)的备注应与 C 下同样放行"; fail=$((fail+1)); }
[ "$(_la note 99991001 复审员挑战 '组合校验用的长备注' '-')" = "0" ] || { echo "❌ action×rc(v3.1.9): note 不该受组合限制(它本就跨组用 rc)"; fail=$((fail+1)); }
[ "$(_la create 99991001 有诱因-多源 '测试用的长度足够的备注')" = "0" ] || { echo "❌ action×rc(v3.1.9): create 用建题 rc 应放行"; fail=$((fail+1)); }
# v3.2.0 备注实质性:防的是「在生产台账上敲验证命令」这类误操作(09-07 一天内犯两次)
[ "$(_la cull 99991001 用户点名 'x')" = "1" ] || { echo "❌ 备注实质性(v3.2.0): 备注 'x' 应被拒(<12字符)"; fail=$((fail+1)); }
[ "$(_la cull 99991001 用户点名 '这是一条长度足够的正常备注')" = "0" ] || { echo "❌ 备注实质性(v3.2.0): 正常长度备注应放行"; fail=$((fail+1)); }
[ "$(_la note 99991001 留档 '短')" = "0" ] || { echo "❌ 备注实质性(v3.2.0): note 不受此闸约束(它常用于极短留痕)"; fail=$((fail+1)); }
rm -rf "$AT"

# ── okx.py 直连（v3.3.0，用户 09-08「skill 里去掉 OKX 的 MCP」）──────────────
OKXT=/tmp/tstc-okx-t.json; OKXO=/tmp/tstc-okx-oi.json; OKXO2=/tmp/tstc-okx-oi2.json; OKXS=/tmp/tstc-oisnap.json
cat > "$OKXT" <<'JEOF'
{"code":"0","data":[
 {"instId":"LOWPX-USDT-SWAP","last":"0.01","open24h":"0.005","high24h":"0.012","low24h":"0.004","volCcy24h":"3000000000","vol24h":"1"},
 {"instId":"HIPX-USDT-SWAP","last":"1000","open24h":"1100","high24h":"1200","low24h":"990","volCcy24h":"30000","vol24h":"1"},
 {"instId":"THIN-USDT-SWAP","last":"0.02","open24h":"0.04","high24h":"0.05","low24h":"0.019","volCcy24h":"100000","vol24h":"1"}]}
JEOF
cat > "$OKXO" <<'JEOF'
{"code":"0","data":[{"instId":"LOWPX-USDT-SWAP","oiUsd":"50000000"},{"instId":"HIPX-USDT-SWAP","oiUsd":"20000000"}]}
JEOF
cat > "$OKXO2" <<'JEOF'
{"code":"0","data":[{"instId":"LOWPX-USDT-SWAP","oiUsd":"75000000"},{"instId":"HIPX-USDT-SWAP","oiUsd":"10000000"}]}
JEOF

# 成交额必须 volCcy24h×last：LOWPX 30亿币 × $0.01 = $30M（漏乘会算成 $3000M，低价币全混过 minvol 过滤）
n=$((n+1)); _O=$(OKX_TICKERS_JSON="$OKXT" "$D/okx.py" movers --top 3 --minvol 1000000 2>&1)
echo "$_O" | grep -q 'LOWPX.*vol=\$30M' || { echo "❌ okx[成交额]: 应 volCcy24h×last=\$30M"; fail=$((fail+1)); }
n=$((n+1)); echo "$_O" | grep -q 'vol=\$3000M' && { echo "❌ okx[成交额]: 漏乘 last(出现\$3000M)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_O" | grep -q 'THIN' && { echo "❌ okx[minvol]: 未过滤低成交额标的 THIN(\$2000)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(echo "$_O" | grep -c 'LOWPX')" -eq 1 ] || { echo "❌ okx[两榜]: 候选<2×top 时涨跌榜重叠"; fail=$((fail+1)); }
# OI 首轮无基线必须 n/a，不得假装有变化率
n=$((n+1)); rm -f "$OKXS"
_O1=$(OKX_TICKERS_JSON="$OKXT" OKX_OI_JSON="$OKXO" OKX_OISNAP="$OKXS" "$D/okx.py" oi --top 2 --minoi 1000000 2>&1)
{ echo "$_O1" | grep -q '首次·无基线' && echo "$_O1" | grep -q 'n/a'; } || { echo "❌ okx[OI]: 首轮未标无基线/未显示 n/a"; fail=$((fail+1)); }
# 第二轮必须算出变化率（50M→75M=+50%，20M→10M=-50%）
n=$((n+1)); _O2=$(OKX_TICKERS_JSON="$OKXT" OKX_OI_JSON="$OKXO2" OKX_OISNAP="$OKXS" "$D/okx.py" oi --top 2 --minoi 1000000 2>&1)
{ echo "$_O2" | grep -q '+50.00%' && echo "$_O2" | grep -q -- '-50.00%'; } || { echo "❌ okx[OI]: 第二轮变化率算错"; fail=$((fail+1)); }
# 不存在的 instId 不得中断整批、不得污染退出码
# v3.5.2(09-20 Evose 第十八轮实证):这是全套 okx 用例里**唯一真打网络**的一条,其余都走注入夹具。
#   沙箱连不上 api.okx.com 时 okx.py 会如实报「取数失败(urllib 与 curl 两路都空)」并 rc=1——
#   那是**没测成**,不是**测了但容错坏了**。旧版一律判 FAIL,于是 checklist.sh verify 在 Evose
#   沙箱里永远过不去、正式轮永远出不了报告。现在把两者分开:网络不可达记 SKIP 并在汇总行显式写出来,
#   **绝不静默当过**——同 v3.4.9(价格前置检查没跑成)/v3.5.1(台账写入失败)是同一条病根的第三次。
n=$((n+1)); _O3=$("$D/okx.py" t NOSUCHTICKERXYZ 2>&1); _RC3=$?
if echo "$_O3" | grep -q '取数失败'; then
  skip=$((skip+1)); skipmsg="${skipmsg}okx[容错]=网络不可达 "
elif [ "$_RC3" -eq 0 ] && echo "$_O3" | grep -q '无此交易对'; then
  :
else
  echo "❌ okx[容错]: 不存在 instId 中断了(rc=$_RC3)"; fail=$((fail+1))
fi
# skill 文档不得再残留 okx MCP 的调用写法（用户已裁定去掉）
n=$((n+1)); grep -rqE 'market_filter\(instType|market_filter_oi_change\(|okx `market_get_ticker`' "$G" 2>/dev/null \
  && { echo "❌ okx[文档]: skill 仍残留 okx MCP 调用写法"; fail=$((fail+1)); }
rm -f "$OKXT" "$OKXO" "$OKXO2" "$OKXS"


# ── ⑦ 热点候选(v3.3.1: 跨 ticker 实体族连通;09-08 4Stock 四条系统题 ③ 一条没抓到)──────
HT=$(mktemp -d); H1=$(ago 1 '%Y-%m-%d %H:%M:%S'); H3=$(ago 3 '%Y-%m-%d %H:%M:%S'); H5=$(ago 5 '%Y-%m-%d %H:%M:%S'); H30=$(ago 30 '%Y-%m-%d %H:%M:%S')
cat > "$HT/hot.json" <<JEOF
[{"id":99990201,"domain":"crypto","status":3,"created_at":"$H5","title":"4Stock上线首日市值破1900万美元","keywords":"4Stock"},
 {"id":99990202,"domain":"crypto","status":3,"created_at":"$H3","title":"BNC4、4Stock盘整，MarsCoin涨超10%","keywords":"BNC4,MarsCoin"},
 {"id":99990203,"domain":"crypto","status":0,"created_at":"$H1","title":"BNC合约溢价拉升，申购单量激增","keywords":"BNC,BNC4"},
 {"id":99990204,"domain":"crypto","status":0,"created_at":"$H30","title":"BNC4成Four.meme新核心","keywords":"BNC4"},
 {"id":99990205,"domain":"crypto","status":0,"created_at":"$H1","title":"ZEC空头爆仓5455万美元","keywords":"ZEC"}]
JEOF
cat > "$HT/cold2.json" <<JEOF
[{"id":99990221,"domain":"crypto","status":0,"created_at":"$H1","title":"XYZ上线Binance","keywords":"XYZ"},
 {"id":99990222,"domain":"crypto","status":0,"created_at":"$H3","title":"XYZ市值破1亿","keywords":"XYZ"}]
JEOF
cat > "$HT/cold.json" <<JEOF
[{"id":99990211,"domain":"crypto","status":0,"created_at":"$H1","title":"AAA上线Binance","keywords":"AAA"},
 {"id":99990212,"domain":"crypto","status":0,"created_at":"$H1","title":"BBB市值破1亿","keywords":"BBB"},
 {"id":99990213,"domain":"crypto","status":0,"created_at":"$H1","title":"CCC 24h涨40%","keywords":"CCC"},
 {"id":99990214,"domain":"crypto","status":0,"created_at":"$H1","title":"比特币重返8万美元","keywords":"BTC"}]
JEOF
_HO=$(cd "$D" && python3 lint.py b0 "$HT/hot.json" 2>&1 | sed -n '/⑦ 热点候选/,/AUDIT:/p')   # 只看 ⑦ 段:204/205 会正常出现在 ②/⑤ 段,整段 grep 会误判
# 正例:4Stock/BNC4/BNC 三条在 8h 内(第四条 30h 前的不计入)→ 实体族 ×3,热点候选=1,且 key 里必须有 4STOCK(数字开头)和 BNC
n=$((n+1)); echo "$_HO" | grep -q '热点候选=1' || { echo "❌ 热点候选[正例]: 4Stock/BNC4/BNC 三条 8h 内应报 1 个实体族"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HO" | grep -q '🔥 实体族 \[.*4STOCK' || { echo "❌ 热点候选[数字开头]: 4Stock 应识别为 4STOCK 而非 STOCK"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HO" | grep -q '🔥 实体族 \[.*BNC' || { echo "❌ 热点候选[前缀连通]: BNC⊂BNC4 的连接 key 应保留"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HO" | grep -q '99990204' && { echo "❌ 热点候选[窗口]: 30h 前的题不该进 8h 实体族"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HO" | grep -q '99990205' && { echo "❌ 热点候选[误连]: ZEC 与 4Stock 族无共享 token 不该被连入"; fail=$((fail+1)); }
# 反例:三条互不相干 + 一条主流币 → 0
_CO=$(cd "$D" && python3 lint.py b0 "$HT/cold.json" 2>&1 | sed -n '/⑦ 热点候选/,/AUDIT:/p')
n=$((n+1)); echo "$_CO" | grep -q '热点候选=0' || { echo "❌ 热点候选[反例]: 互不相干的题不该报实体族"; fail=$((fail+1)); }
# ③ 聚簇对热点族簇必须打 🔥 标记(否则下一轮 AUTO 会按「留超集」撤切面题);冷夹具的簇不得带标记
n=$((n+1)); _H3=$(cd "$D" && python3 lint.py b0 "$HT/hot.json" 2>&1 | sed -n '/③ 同标的聚簇/,/④/p')
echo "$_H3" | grep -q '\[BNC4\] ×2 🔥热点族' || { echo "❌ 聚簇[热点标记]: 热点族内的 [BNC4] 簇应标 🔥按切面判"; fail=$((fail+1)); }
n=$((n+1)); _C3=$(cd "$D" && python3 lint.py b0 "$HT/cold2.json" 2>&1 | sed -n '/③ 同标的聚簇/,/④/p')
echo "$_C3" | grep -q '🔥热点族' && { echo "❌ 聚簇[热点标记]: 非热点族的簇不该带 🔥"; fail=$((fail+1)); }

# ── ⑦ 时间窗 token 不得当实体(v3.3.8;09-09 实测误报实体族 [24H/FOUR.MEME]×3)────────
# 「24h」是本 skill 标题的高频固定写法(窗口题闸鼓励写),被 [A-Za-z0-9] 正则抽成 ticker 后
# 会把互不相干的题聚成族,污染 ⑦ 这道最滞后的兜底信号。
cat > "$HT/tw.json" <<JEOF
[{"id":99990231,"domain":"crypto","status":0,"created_at":"$H1","title":"USELESS上线Upbit，24h涨29%","keywords":"USELESS"},
 {"id":99990232,"domain":"crypto","status":0,"created_at":"$H1","title":"ZCAT市值1.1亿美元，24h跌14%","keywords":"ZCAT"},
 {"id":99990233,"domain":"crypto","status":0,"created_at":"$H3","title":"NUDES 24h跌34%，市值1110万美元","keywords":"NUDES"},
 {"id":99990234,"domain":"crypto","status":0,"created_at":"$H1","title":"PAIR 72h回撤,7d成交萎缩,30d新低","keywords":"PAIR"}]
JEOF
_TW=$(cd "$D" && python3 lint.py b0 "$HT/tw.json" 2>&1 | sed -n '/⑦ 热点候选/,/AUDIT:/p')
n=$((n+1)); echo "$_TW" | grep -q '热点候选=0' || { echo "❌ 时间窗token[聚族]: 四条互不相干的题只因都含 24h/72h/7d/30d 就被聚成实体族"; fail=$((fail+1)); }
n=$((n+1)); echo "$_TW" | grep -qE '实体族 \[(24H|72H|7D|30D)' && { echo "❌ 时间窗token[抽取]: 24H/72H/7D/30D 不该被抽成实体 ticker"; fail=$((fail+1)); }
# 反向守卫:剔时间窗不能误伤数字开头的真 ticker(4Stock→4STOCK 已在上面正例覆盖,这里守 BNC4 尾数字)
n=$((n+1)); echo "$_HO" | grep -q 'BNC4' || { echo "❌ 时间窗token[误伤]: 剔除 \\d+[HDWMY] 不该波及 BNC4 这类尾数字 ticker"; fail=$((fail+1)); }
# 判据闸必须存在且可查
# v3.4.5 gate.sh 截断按字符:C locale(生产)下 list/grep 输出不得含被切半的中文
n=$((n+1)); for _gm in list "grep 价格"; do LC_ALL=C "$D/gate.sh" $_gm 2>/dev/null | python3 -c 'import sys;sys.stdin.buffer.read().decode("utf-8")' 2>/dev/null \
  || { echo "❌ gate.sh $_gm(v3.4.5): 输出含非法 UTF-8(按字节截断切坏中文)"; fail=$((fail+1)); }; done
n=$((n+1)); "$D/gate.sh" 大热点 >/dev/null 2>&1 || { echo "❌ gates 缺 闸:大热点(⑦ 亮灯后无判据可查)"; fail=$((fail+1)); }
rm -rf "$HT"


# ── hot-scan.py(v3.3.2 大热点前置扫描)──────────────────────────────────────
HS=$(mktemp -d); NOWISO=$(ago 3 '%Y-%m-%dT%H:%M:%SZ' u); OLDISO=$(ago 400 '%Y-%m-%dT%H:%M:%SZ' u)
cat > "$HS/bsc-trending.json" <<JEOF
{"data":[{"attributes":{"name":"NEWX / USDT","volume_usd":{"h24":"12000000"},"fdv_usd":"3000000","price_change_percentage":{"h24":"900"},"pool_created_at":"$NOWISO"},"relationships":{"base_token":{"data":{"id":"bsc_0xabc123def456"}}}},
 {"attributes":{"name":"OLDY / USDT","volume_usd":{"h24":"8000000"},"fdv_usd":"300000000","price_change_percentage":{"h24":"5"},"pool_created_at":"$OLDISO"},"relationships":{"base_token":{"data":{"id":"bsc_0xold"}}}}]}
JEOF
echo '{"data":[]}' > "$HS/bsc-new.json"
cat > "$HS/bn.json" <<'JEOF'
[{"symbol":"CAPUSDT","lastFundingRate":"0.02000000","markPrice":"1"},{"symbol":"CALMUSDT","lastFundingRate":"0.00010000","markPrice":"1"}]
JEOF
echo '{"symbols":[]}' > "$HS/bnx.json"; echo '{"data":[]}' > "$HS/okx.json"
mkdir -p "$HS/dump"; _TSMS=$(python3 -c 'import time;print(int(time.time()*1000))'); echo "{\"ts\":$_TSMS,\"range\":\"6h\",\"pulls\":{\"telegram\":[],\"twitter\":[],\"media\":[]},\"errors\":{}}" > "$HS/dump/$_TSMS.json"
_HS=$(HOTSCAN_SKIP_FETCH=1 NEWS_DUMP_DIR="$HS/dump" HOTSCAN_GT_JSON="$HS" HOTSCAN_BN_JSON="$HS/bn.json" HOTSCAN_BNX_JSON="$HS/bnx.json" HOTSCAN_OKX_JSON="$HS/okx.json" "$D/hot-scan.py" all --chains bsc 2>&1)   # v3.3.3 起 all 含 L2:跳过拉取,给空 dump
n=$((n+1)); echo "$_HS" | grep -q '速通·新池\] NEWX' || { echo "❌ hot-scan[速通]: 3h 新池 vol \$12M 应触发"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HS" | grep -q 'OLDY' && { echo "❌ hot-scan[老池]: 400h 老池 vol \$8M/+5% 不该触发"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HS" | grep -q 'CAPUSDT.*+2.000%(=上限)' || { echo "❌ hot-scan[费率]: 2% 应标 =上限"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HS" | grep -q 'CALMUSDT' && { echo "❌ hot-scan[费率]: 0.01% 不该触发"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HS" | grep -q 'HOTSCAN: 候选=2 新名字=0 观察=0 上新=0 半盲=0' || { echo "❌ hot-scan[汇总行]: 期望 候选=2 新名字=0 观察=0 上新=0 半盲=0，得到: $(echo "$_HS"|tail -1)"; fail=$((fail+1)); }
# 取数失败必须标半盲且不崩(指向空目录→GT 两路走网络;这里用不存在的域名不可控,改为验证:夹具缺 solana 文件时脚本仍应跑完并给出 ⚠️ 或真实数据,不得异常退出)
n=$((n+1)); HOTSCAN_GT_JSON="$HS" HOTSCAN_BN_JSON="$HS/bn.json" HOTSCAN_BNX_JSON="$HS/bnx.json" HOTSCAN_OKX_JSON="$HS/okx.json" "$D/hot-scan.py" dex --chains bsc >/dev/null 2>&1 || { echo "❌ hot-scan[退出码]: 正常夹具应 exit 0"; fail=$((fail+1)); }
rm -rf "$HS"


# ── L2 hot-names / news-fetch dump(v3.3.3)──────────────────────────────────
HN=$(mktemp -d); mkdir -p "$HN/dump"; NOWMS=$(python3 -c 'import time;print(int(time.time()*1000))'); AGO=$((NOWMS-1800000))
cat > "$HN/dump/$NOWMS.json" <<JEOF
{"ts":$NOWMS,"range":"6h","pulls":{"telegram":[
 {"ts":$AGO,"src":"telegram:social","name":"vi_guy@telegram","kol":"vi_guy@telegram","lang":null,"text":"Token \$NEWCO mới ra mắt bay lên MC 30M https://x.com/abc/status/1"},
 {"ts":$AGO,"src":"telegram:social","name":"ko_guy@telegram","kol":"ko_guy@telegram","lang":null,"text":"NEWCO의 시총 일시적으로 6천만 달러를 돌파 https://dexscreener.com/bsc/0xabc"},
 {"ts":$AGO,"src":"telegram:social","name":"en_guy@telegram","kol":"en_guy@telegram","lang":null,"text":"\$NEWCO was invested by Yzi labs btw"},
 {"ts":$AGO,"src":"telegram:social","name":"zh_guy@telegram","kol":"zh_guy@telegram","lang":null,"text":"NEWCO 速通 5000 万市值，BSC 又出速通盘"},
 {"ts":$AGO,"src":"telegram:social","name":"a@telegram","kol":"a@telegram","lang":null,"text":"\$DUO looks good"},
 {"ts":$AGO,"src":"telegram:social","name":"b@telegram","kol":"b@telegram","lang":null,"text":"\$DUO chart"},
 {"ts":$AGO,"src":"telegram:social","name":"c@telegram","kol":"c@telegram","lang":null,"text":"OLDNAME 又涨了"},
 {"ts":$AGO,"src":"telegram:social","name":"d@telegram","kol":"d@telegram","lang":null,"text":"OLDNAME 太强了"},
 {"ts":$AGO,"src":"telegram:social","name":"e@telegram","kol":"e@telegram","lang":null,"text":"OLDNAME to the moon"}
],"twitter":[],"media":[]},"errors":{}}
JEOF
OLDCA=$(ago 30 '%Y-%m-%d %H:%M:%S')
echo "[{\"id\":99990301,\"domain\":\"crypto\",\"status\":0,\"created_at\":\"$OLDCA\",\"title\":\"OLDNAME上线Binance\",\"keywords\":\"OLDNAME\"}]" > "$HN/b0.json"
: > "$HN/actions.tsv"; echo '{"majors":["BTC","ETH"]}' > "$HN/majors.json"
_HN=$(cd "$D" && NEWS_DUMP_DIR="$HN/dump" HOTNAMES_B0="$HN/b0.json" HOTNAMES_ACTIONS="$HN/actions.tsv" MAJORS_JSON="$HN/majors.json" python3 hot-names.py 2>&1)
n=$((n+1)); echo "$_HN" | grep -q '🔥 NEWCO .*源=4 语种=en/ko/vi/zh' || { echo "❌ hot-names[四语种]: NEWCO 4源4语种应 🔥，得到: $(echo "$_HN"|grep NEWCO|head -1)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HN" | grep -qE 'X\.COM|DEXSCREENER' && { echo "❌ hot-names[URL]: URL 碎片不该成为名字"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HN" | grep -q '👀 DUO ' || { echo "❌ hot-names[两源]: 2 源应只到 👀"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HN" | grep -q '🔥 DUO ' && { echo "❌ hot-names[两源]: 2 源不该 🔥"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HN" | grep -q 'OLDNAME' && { echo "❌ hot-names[新颖性]: 30h 前已在池内的名字不该再列"; fail=$((fail+1)); }
# hot-scan all 串起 L2(跳过拉取,用注入 dump);L1 零成交量高 FDV 新池不得触发
cat > "$HN/bsc-trending.json" <<JEOF
{"data":[{"attributes":{"name":"ZEROV / USDT","volume_usd":{"h24":"0"},"fdv_usd":"49000000","price_change_percentage":{"h24":"0"},"pool_created_at":"$(ago 1 '%Y-%m-%dT%H:%M:%SZ' u)"},"relationships":{"base_token":{"data":{"id":"bsc_0xzero"}}}}]}
JEOF
echo '{"data":[]}' > "$HN/bsc-new.json"; echo '[]' > "$HN/bn.json"; echo '{"symbols":[]}' > "$HN/bnx.json"; echo '{"data":[]}' > "$HN/okx.json"
_HA=$(cd "$D" && HOTSCAN_SKIP_FETCH=1 NEWS_DUMP_DIR="$HN/dump" HOTNAMES_B0="$HN/b0.json" HOTNAMES_ACTIONS="$HN/actions.tsv" MAJORS_JSON="$HN/majors.json" HOTSCAN_GT_JSON="$HN" HOTSCAN_BN_JSON="$HN/bn.json" HOTSCAN_BNX_JSON="$HN/bnx.json" HOTSCAN_OKX_JSON="$HN/okx.json" "$D/hot-scan.py" all --chains bsc 2>&1)
n=$((n+1)); echo "$_HA" | grep -q 'ZEROV' && { echo "❌ hot-scan[零成交量]: 成交 \$0 的新池不该按 FDV 触发"; fail=$((fail+1)); }
n=$((n+1)); echo "$_HA" | grep -q 'HOTSCAN: 候选=1 新名字=1 观察=1' || { echo "❌ hot-scan[L2 汇总]: 期望 候选=1 新名字=1 观察=1，得到: $(echo "$_HA"|tail -1)"; fail=$((fail+1)); }
# 无 dump 时必须半盲而不是「无新名字」
n=$((n+1)); _HB=$(cd "$D" && HOTSCAN_SKIP_FETCH=1 NEWS_DUMP_DIR="$HN/empty" HOTSCAN_GT_JSON="$HN" HOTSCAN_BN_JSON="$HN/bn.json" HOTSCAN_BNX_JSON="$HN/bnx.json" HOTSCAN_OKX_JSON="$HN/okx.json" "$D/hot-scan.py" all --chains bsc 2>&1)
echo "$_HB" | grep -q '半盲=1' && echo "$_HB" | grep -q 'L2\] 无' || { echo "❌ hot-scan[无dump]: 应标半盲=1"; fail=$((fail+1)); }
# v3.3.5 多 dump 召回:名字只在窗口内较旧的 dump 里出现,也必须被计入(followin 热门召回会把旧帖挤出最新一份)
n=$((n+1)); OLDMS=$((NOWMS-14400000)); AGO2=$((OLDMS-600000))
cat > "$HN/dump/$OLDMS.json" <<JEOF
{"ts":$OLDMS,"range":"6h","pulls":{"twitter":[
 {"ts":$AGO2,"src":"twitter:social","name":"x1","kol":"x1","lang":null,"text":"\$OLDPOST is ripping"},
 {"ts":$AGO2,"src":"twitter:social","name":"x2","kol":"x2","lang":null,"text":"OLDPOST 又拉了"},
 {"ts":$AGO2,"src":"twitter:social","name":"x3","kol":"x3","lang":null,"text":"OLDPOST 시총 돌파"}]},"errors":{}}
JEOF
_HM=$(cd "$D" && NEWS_DUMP_DIR="$HN/dump" HOTNAMES_B0="$HN/b0.json" HOTNAMES_ACTIONS="$HN/actions.tsv" MAJORS_JSON="$HN/majors.json" python3 hot-names.py --window 6 2>&1)
echo "$_HM" | grep -q '🔥 OLDPOST ' || { echo "❌ hot-names[多dump]: 4h 前那份 dump 里的 OLDPOST(3源3语种)应被计入"; fail=$((fail+1)); }
echo "$_HM" | grep -q 'dumps=2' || { echo "❌ hot-names[多dump]: 窗口内 2 份 dump 应都被读取"; fail=$((fail+1)); }
rm -rf "$HN"


# ── v3.3.4 备注模板(-T) + update-batch + 注入路径潜伏bug ────────────────────
LB=$(mktemp -d)
# -T 三段展开成标准备注
n=$((n+1)); ACTIONS="$LB/a.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" \
  update 99990501 改数字-定稿 -T 'v2.9.62窗口题72h|0.1537→0.1412=-9.7%|价格腿刷新' '旧 → 新' >/dev/null 2>&1
grep -q '判据=v2.9.62窗口题72h；实测=0.1537→0.1412=-9.7%；落此code因=价格腿刷新' "$LB/a.tsv" 2>/dev/null \
  || { echo "❌ log-action[-T]: 三段未展开成标准备注"; fail=$((fail+1)); }
# v3.4.4(P0-1) 同一条 -T 在 UTF-8 locale 下必须逐字节展开一致(bash 3.2 多字节切段曾静默写坏台账)
n=$((n+1)); LC_ALL=en_US.UTF-8 ACTIONS="$LB/u.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" \
  update 99990503 改数字-定稿 -T 'v2.9.62窗口题72h|0.1537→0.1412=-9.7%|价格腿刷新' '旧 → 新' >/dev/null 2>&1
grep -q '判据=v2.9.62窗口题72h；实测=0.1537→0.1412=-9.7%；落此code因=价格腿刷新' "$LB/u.tsv" 2>/dev/null \
  || { echo "❌ log-action[-T](v3.4.4): en_US.UTF-8 下展开结果与 C 下不一致(多字节切段写坏台账)"; fail=$((fail+1)); }
# 三段缺一必须拒(防模板化变成少写一要素的后门)
n=$((n+1)); ACTIONS="$LB/a.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" \
  update 99990502 改数字-定稿 -T '只有两段|缺第三段' '旧 → 新' >/dev/null 2>&1
[ $? -ne 0 ] || { echo "❌ log-action[-T]: 三段缺一应拒写"; fail=$((fail+1)); }
# update-batch 逐条落账,判据/why 共用、实测各自
n=$((n+1)); ACTIONS="$LB/a.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" update-batch 改数字-定稿 \
  'J共用判据' 'W共用原因' '99990511|旧A → 新A|实测A' '99990512|旧B → 新B|实测B' >/dev/null 2>&1
[ "$(grep -c 'J共用判据' "$LB/a.tsv" 2>/dev/null)" -eq 2 ] || { echo "❌ update-batch: 应逐条落账2条共用判据"; fail=$((fail+1)); }
n=$((n+1)); grep -q '实测=实测A' "$LB/a.tsv" && grep -q '实测=实测B' "$LB/a.tsv" \
  || { echo "❌ update-batch: 每条实测应各自独立"; fail=$((fail+1)); }
# update-batch 的 rc 必须是改题族(撤题 rc 要被拒)
n=$((n+1)); ACTIONS="$LB/a.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" update-batch 反转错向 'J' 'W' '99990513|旧 → 新|实测' >/dev/null 2>&1
[ $? -ne 0 ] || { echo "❌ update-batch: 撤题 rc「反转错向」应被拒"; fail=$((fail+1)); }
# spec 少一段:该条拒、其余照落
n=$((n+1)); _B4=$(wc -l < "$LB/a.tsv")
ACTIONS="$LB/a.tsv" SNAPSHOTS="$LB/s.tsv" REJ="$LB/r.tsv" "$D/log-action.sh" update-batch 改数字-定稿 'J2' 'W2' \
  '99990521|旧C → 新C|实测C' '99990522|少了实测段' '99990523|旧E → 新E|实测E' >/dev/null 2>&1
[ "$(( $(wc -l < "$LB/a.tsv") - _B4 ))" -eq 2 ] || { echo "❌ update-batch: 坏 spec 应只拒该条、其余照落"; fail=$((fail+1)); }
# **潜伏 bug 哨兵**:批量子命令的注入路径必须真的生效。
#   v3.3.4 前脚本内 ACTIONS= 枚举覆盖了注入用的同名环境变量(命令前缀=export),子调用继承到枚举串,
#   台账被写进一个名叫「create cull update...」的文件——cull-batch 从 v2.9.73 起一直如此,
#   而用例只断言了命令输出、没断言文件内容,于是「通过」了几十轮。
n=$((n+1)); LB2=$(mktemp -d); ACTIONS="$LB2/a.tsv" SNAPSHOTS="$LB2/s.tsv" REJ="$LB2/r.tsv" \
  "$D/log-action.sh" cull-batch 重复-同标的 '注入路径哨兵,验证子调用继承正确' 99990531 99990532 >/dev/null 2>&1
[ -f "$LB2/a.tsv" ] && [ "$(wc -l < "$LB2/a.tsv")" -eq 2 ] \
  || { echo "❌ cull-batch[注入哨兵]: 子调用未写入注入路径(枚举变量又和环境变量撞名了?)"; fail=$((fail+1)); }
n=$((n+1)); [ -e "$D/create cull update merge restore publish rulefix note" ] \
  && { echo "❌ 批量子命令把台账写进了枚举串命名的文件"; fail=$((fail+1)); }
rm -rf "$LB" "$LB2"


# ── dex.py 注册表(v3.3.6 同名不同币)────────────────────────────────────────
DX=$(mktemp -d); mkdir -p "$DX/inj"
cat > "$DX/inj/search-REALX.json" <<'JEOF'
{"pairs":[
 {"chainId":"solana","baseToken":{"symbol":"REALX","address":"SoLcopy111"},"priceUsd":"0.001","priceChange":{"h24":"3000"},"volume":{"h24":"139000000"},"marketCap":"9000000","pairCreatedAt":1788800000000},
 {"chainId":"bsc","baseToken":{"symbol":"REALX","address":"0xrealx"},"priceUsd":"0.04","priceChange":{"h24":"1100"},"volume":{"h24":"115000000"},"marketCap":"40000000","pairCreatedAt":1788790000000}]}
JEOF
cat > "$DX/inj/bsc-0xrealx.json" <<'JEOF'
[{"chainId":"bsc","baseToken":{"symbol":"REALX","name":"Real X","address":"0xrealx"},"priceUsd":"0.04","priceChange":{"h24":"1100"},"volume":{"h24":"115000000"},"marketCap":"40000000","fdv":"40000000","pairCreatedAt":1788790000000}]
JEOF
echo '[]' > "$DX/inj/bsc-0xnothing.json"
# 未钉:按 symbol 搜必须列候选并标未钉死(仿盘成交额更大也不得默认选它)
n=$((n+1)); _D1=$(CONTRACTS_JSON="$DX/c.json" DEX_INJECT_DIR="$DX/inj" "$D/dex.py" t REALX 2>&1)
echo "$_D1" | grep -q '未钉死' && echo "$_D1" | grep -q 'DEX: 未钉死 1' || { echo "❌ dex[未钉]: 未入册 symbol 应列候选并标未钉死"; fail=$((fail+1)); }
n=$((n+1)); echo "$_D1" | grep -q '📌' && { echo "❌ dex[未钉]: 未入册不得输出 📌 钉死行"; fail=$((fail+1)); }
# pin:核不到的地址必须拒且不写注册表
n=$((n+1)); CONTRACTS_JSON="$DX/c.json" DEX_INJECT_DIR="$DX/inj" "$D/dex.py" pin REALX bsc 0xnothing x >/dev/null 2>&1
[ $? -ne 0 ] && [ ! -e "$DX/c.json" ] || { echo "❌ dex[pin]: 核不到的地址应拒绝入册且不创建注册表"; fail=$((fail+1)); }
# pin 成功后 t 必须按地址取(📌),不再列候选
n=$((n+1)); CONTRACTS_JSON="$DX/c.json" DEX_INJECT_DIR="$DX/inj" "$D/dex.py" pin REALX bsc 0xrealx '测试依据' >/dev/null 2>&1
_D2=$(CONTRACTS_JSON="$DX/c.json" DEX_INJECT_DIR="$DX/inj" "$D/dex.py" t REALX 2>&1)
echo "$_D2" | grep -q '📌 REALX' && echo "$_D2" | grep -q 'mcap=\$40.0M' || { echo "❌ dex[已钉]: 入册后应按地址取并输出 📌"; fail=$((fail+1)); }
n=$((n+1)); echo "$_D2" | grep -q '未钉死' && { echo "❌ dex[已钉]: 入册后不应再报未钉死"; fail=$((fail+1)); }
# block:⛔ 且计入未钉死
n=$((n+1)); CONTRACTS_JSON="$DX/c.json" "$D/dex.py" block FAKEY '仿盘期' >/dev/null 2>&1
_D3=$(CONTRACTS_JSON="$DX/c.json" DEX_INJECT_DIR="$DX/inj" "$D/dex.py" t FAKEY 2>&1)
echo "$_D3" | grep -q '⛔ FAKEY' && echo "$_D3" | grep -q 'DEX: 未钉死 1' || { echo "❌ dex[block]: 标记暂不可钉的应输出 ⛔ 并计入未钉死"; fail=$((fail+1)); }
rm -rf "$DX"

# ── v3.4.3 跨平台(Evose 沙箱=Linux:无 jq、GNU date/stat;09-10 首轮 verify 与 json 直灌两道闸被手工替代)──────
XP=$(mktemp -d); mkdir -p "$XP/home/.trend-scout" "$XP/bin"
# 静态守卫:脚本非注释行不得再用 BSD 专用写法或调 jq(macOS 上这类写法照常过,只有静态查才拦得住)
n=$((n+1)); _XG=$(grep -nE 'date( -u)? -v[-+]|date -r ["$0-9]|stat[ ]-f|(^|[;&|(]|\$\()[[:space:]]*jq[[:space:]]' "$D"/*.sh "$D"/*.py 2>/dev/null | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#')
[ -z "$_XG" ] || { echo "❌ 跨平台[BSD写法]: Linux 沙箱不认: $(echo "$_XG" | head -3 | tr '\n' ' ')"; fail=$((fail+1)); }
# json 直灌不依赖 jq:jq 换成一调就失败的桩;输出须与原 jq 表达式逐字节一致(期望值由 v3.4.2 jq 版实跑得出)
printf '#!/bin/sh\necho "jq 被调用" >&2; exit 127\n' > "$XP/bin/jq"; chmod +x "$XP/bin/jq"
cat > "$XP/b0.json" <<'JEOF'
{"topics":[{"id":11,"domain":"crypto","status":0,"keywords":"BTC,ETF"},{"id":"12","domain":"tradfi","status":2,"keywords":""},{"id":13,"status":1,"keywords":null},{"id":14,"domain":"crypto","status":3,"keywords":"a\tb\\c"}]}
JEOF
n=$((n+1)); _XS=$(HOME="$XP/home" PATH="$XP/bin:$PATH" "$D/log-snapshot.sh" json "$XP/b0.json" 2>&1)
_XE=$(printf '11\tcrypto\t0\tBTC,ETF\n12\ttradfi\t2\t-\n13\t\t1\t-\n14\tcrypto\t3\ta\\tb\\\\c')
{ echo "$_XS" | grep -q 'snapshots: +4 行' && [ "$(cut -f2- "$XP/home/.trend-scout/snapshots.tsv" 2>/dev/null)" = "$_XE" ]; } || { echo "❌ 跨平台[json直灌]: 无 jq 时应照常写 4 行且与 jq 版一致，得到: $(echo "$_XS" | head -2 | tr '\n' ' ')"; fail=$((fail+1)); }
# circuit 时间列:BSD `date -r <秒>` 在 Linux 是取文件 mtime,时间列会变空。TZ 用 POSIX 串(沙箱可能没装 tzdata);期望值由 macOS /bin/date -r 独立算出
printf '1788399480000\tTG探针\tfused\t-\t测试\n' > "$XP/home/.trend-scout/circuit-log.tsv"
n=$((n+1)); _XC=$(HOME="$XP/home" TZ=CST-8 "$D/circuit.sh" history TG探针 2>&1; HOME="$XP/home" TZ=CST-8 "$D/circuit.sh" get 2>&1)
{ echo "$_XC" | grep -q '^09-03 09:38 fused' && echo "$_XC" | grep -q '\[自09-03 09:38\]'; } || { echo "❌ 跨平台[circuit时间列]: 期望 09-03 09:38，得到: $(echo "$_XC" | tr '\n' ' ')"; fail=$((fail+1)); }
rm -rf "$XP"

# ── v3.5.4(09-21 Evose 第二十轮缝合试跑实证)────────────────────────────────
# ① 双要素机械闸:纯价格且幅度不够 → WARN 双要素-缺诱因;有诱因/幅度够/有价格腿的不误报
n=$((n+1)); python3 "$D/lint.py" title "AKE跌18.46%，报0.053美元" crypto | grep -q $'^WARN\t双要素-缺诱因' || { echo "❌ 双要素(v3.5.4): 纯价格 18.46%<30% 应 WARN 缺诱因"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/lint.py" title "ORBIO 24小时涨106%，市值8670万美元" crypto | grep -q '双要素-缺诱因' && { echo "❌ 双要素(v3.5.4): 幅度 106% 已过 crypto 30% 线,不该报缺诱因"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/lint.py" title "SK海力士考虑在美建闪存厂，收涨6.4%" tradfi | grep -q '双要素' && { echo "❌ 双要素(v3.5.4): 有诱因有价格的题被误报"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/lint.py" title "SK Hynix Inc.涨5.4%" tradfi | grep -q $'^WARN\t双要素-缺诱因' || { echo "❌ 双要素(v3.5.4): tradfi 纯价格 5.4%<10% 应 WARN 缺诱因"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/lint.py" title "美国制裁伊朗加密交易所BitBank" crypto | grep -q $'^WARN\t双要素-缺价格' || { echo "❌ 双要素(v3.5.4): 无价格腿应 WARN 缺价格"; fail=$((fail+1)); }
# ② plan-check.py:撤题码配「改」、编造的码、列数不对 → FAIL 且 exit 1;合规表 exit 0
PC=$(mktemp -d)
printf '【决策表】\nid｜domain｜当前标题｜动作｜新标题｜reason_code｜判据\n12557｜crypto｜GENIUS下月解锁，抛压会来吗？｜改｜GENIUS传下月解锁，24小时涨3%%｜疑问句-悬念｜④\n12467｜crypto｜NEAR涨17%%｜改｜NEAR涨17.69%%，报4.178美元｜时效-窗口题｜②\n12513 | crypto | update | 改归因 | OFC跌25.55%% | x\n【弃建】\n' > "$PC/bad.txt"
printf '【决策表】\n12489｜crypto｜Hyperliquid借贷首日2.69亿，HYPE报91.6｜改｜Hyperliquid借贷首日2.69亿，HYPE报93｜承接更新｜②窗口题 实测 OKX\n12487｜crypto｜SEC放行代币化股票，BP涨13.2%%｜留｜—｜留档｜无实测\n【弃建】\n' > "$PC/ok.txt"
_PB=$(python3 "$D/plan-check.py" "$PC/bad.txt" 2>&1); _pbrc=$?
n=$((n+1)); { [ $_pbrc -eq 1 ] && echo "$_PB" | grep -q $'^FAIL\t12557.*撤题枚举' && echo "$_PB" | grep -q $'^FAIL\t12467.*不在任何枚举' && echo "$_PB" | grep -q $'^FAIL\t12513.*列数'; } || { echo "❌ plan-check(v3.5.4): 撤码配改/编造码/列数错 应逐行 FAIL 且 exit 1,得到 rc=$_pbrc: $(echo "$_PB" | head -3 | tr '\n' ' ')"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/plan-check.py" "$PC/ok.txt" >/dev/null 2>&1 || { echo "❌ plan-check(v3.5.4): 合规决策表不该 FAIL"; fail=$((fail+1)); }
# v3.5.5(09-21 第二十一轮 Evose 实测):判据正文里出现「【存量取价】」不得截断决策表段;带前缀的表头不算数据行
printf '【决策表】\n列序：题号 | domain | 动作 | reason_code | 新标题 | 判据\n12557｜crypto｜旧题｜改｜GENIUS传下月解锁，24小时涨3%%｜承接更新｜价格腿：【存量取价】段本轮未送达\n12487｜crypto｜SEC放行代币化股票，BP涨13.2%%｜留｜—｜留档｜【存量取价】段未送达\n12485｜crypto｜CFG题｜留｜—｜留档｜同上\n【留-撤对照】\n无\n' > "$PC/mid.txt"
n=$((n+1)); python3 "$D/plan-check.py" "$PC/mid.txt" 2>&1 | grep -q '^PLAN: 行=3 ' || { echo "❌ plan-check(v3.5.5): 判据里的【…】截断了决策表段,或表头被当成数据行: $(python3 "$D/plan-check.py" "$PC/mid.txt" 2>&1 | head -1)"; fail=$((fail+1)); }
# ③ lark-push:缺 lark-cli 不崩(_cli 返回 127);.BOOTSTRAP-NOKEY 在位默认转预演,LARK_ALLOW_NOKEY=1 才真发
_LK=$(PC="$PC" D="$D" python3 - <<'LKEOF' 2>&1
import os, importlib.util
from unittest import mock
sp=importlib.util.spec_from_file_location('lp',os.path.join(os.environ['D'],'lark-push.py')); lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
lp.LARK_CLI='/nonexistent-lark-cli'
rc,_d,err=lp._cli(['im','+messages-send'])
print('CLI', rc, 'lark-cli' in err)
R=os.path.join(os.environ['PC'],'real'); os.makedirs(R); lp.REAL=R
open(os.path.join(R,'.BOOTSTRAP-NOKEY'),'w').write('x')
seen=[]
pl={'run_ts':1,'kind':'abort','main':'m','threads':[],'attach':[],'win_from':0,'win_to':1}
with mock.patch.object(lp,'save_report',lambda p:None), mock.patch.object(lp,'send_payload',lambda p,c,dry=False:(seen.append(dry) or (True,'dry-run',''))):
    r1=lp.deliver(pl,{'enabled':True,'chat_id':'c'})
    os.environ['LARK_ALLOW_NOKEY']='1'; r2=lp.deliver(pl,{'enabled':True,'chat_id':'c'})
print('NOKEY', r1, seen)
LKEOF
)
n=$((n+1)); echo "$_LK" | grep -q '^CLI 127 True' || { echo "❌ lark-push(v3.5.4): 缺 lark-cli 应返回 127 而不是抛异常: $(echo "$_LK" | tail -2 | tr '\n' ' ')"; fail=$((fail+1)); }
n=$((n+1)); echo "$_LK" | grep -q '^NOKEY 0 \[True, False\]' || { echo "❌ lark-push(v3.5.4): .BOOTSTRAP-NOKEY 在位应默认预演、LARK_ALLOW_NOKEY=1 才真发: $(echo "$_LK" | tail -2 | tr '\n' ' ')"; fail=$((fail+1)); }
rm -rf "$PC"

# ── v3.5.6(09-21 Evose 第二十三轮):「不成立」必须带证据、不许一句理由批量驳回 ─────────────
CH=$(mktemp -d); printf '# h\n' > "$CH/a.tsv"
_la(){ ACTIONS="$CH/a.tsv" SNAPSHOTS="$CH/s.tsv" REJ="$CH/r.tsv" "$D/log-action.sh" "$@" >/dev/null 2>&1; }
n=$((n+1)); _la note 12467 复审员挑战 "不成立:演练·未实调console｜时点差，复审站在现在时点复检，价格滚动不可比" && { echo "❌ 不成立证据闸(v3.5.6): 无数字无引文的「不成立」应拒写"; fail=$((fail+1)); }
n=$((n+1)); _la note 12467 复审员挑战 "不成立:演练·未实调console｜r22 原文 NEAR +23.47% last=4.339，复审晚 5 小时取价" || { echo "❌ 不成立证据闸(v3.5.6): 带实测数字的「不成立」不该被拒"; fail=$((fail+1)); }
n=$((n+1)); _la note 12545 复审员挑战 "不成立:演练·未实调console｜r22 原文 NEAR +23.47% last=4.339，复审晚 5 小时取价" && { echo "❌ 不成立一刀切闸(v3.5.6): 与另一题逐字相同的「不成立」理由应拒写"; fail=$((fail+1)); }
n=$((n+1)); _la note 12035 复审员挑战 "不成立:理由『张冠李戴确实』『热度升温与价格反向』全部支持我的撤" || { echo "❌ 不成立证据闸(v3.5.6): 『』引文应算证据(本机 12035 历史写法)"; fail=$((fail+1)); }
n=$((n+1)); _la note 10000002963 复审员挑战 "不成立:演练·未实调console｜盘前274.05来自本轮取价记录(auditor-01.txt第12行「本轮只有BE盘前274.05」)，复审员检ask 270.7为另一时点" && { echo "❌ 不成立自证闸(v3.5.7): 只引审核员决策表的「不成立」应拒写"; fail=$((fail+1)); }
n=$((n+1)); _la note 12489 复审员挑战 "不成立:演练·未实调console｜HYPE 94.68 见 scanner-1789979164000-02.txt 取价记录第 31 行，决策表 auditor-01 第 20 行照抄" || { echo "❌ 不成立自证闸(v3.5.7): 同时引了扫描员原件的不该被拒"; fail=$((fail+1)); }
rm -rf "$CH"

# ── v3.5.8(09-22):gate.py Gate 取价——同名冲突不给价、注册表钉市场、Gate 没有转 CoinGecko、tradfi 跳过 ─────
GT=$(mktemp -d)
printf '[{"currency_pair":"ONE_USDT","last":"0.00503","change_percentage":"6.3","quote_volume":"1830000"},{"currency_pair":"CFG_USDT","last":"0.1345","change_percentage":"-3.2","quote_volume":"410000"}]' > "$GT/s.json"
printf '[{"contract":"ONE_USDT","last":"0.00381","change_percentage":"-2.2","volume_24h_quote":"13800000"},{"contract":"CFG_USDT","last":"0.1346","change_percentage":"-3.0","volume_24h_quote":"360000"}]' > "$GT/f.json"
printf '{"tokens":{},"blocked":{},"price_map":{"KNOTS":{"cg_id":"knots"}}}' > "$GT/c0.json"
printf '{"tokens":{},"blocked":{},"price_map":{"ONE":{"gate":"futures","cg_id":"harmony"}}}' > "$GT/c1.json"
_gt(){ GATE_SPOT_JSON="$GT/s.json" GATE_FUT_JSON="$GT/f.json" CONTRACTS_JSON="$1" python3 "$D/gate.py" "${@:2}" 2>&1; }
n=$((n+1)); _gt "$GT/c0.json" t ONE | grep -q '同名冲突' || { echo "❌ gate.py(v3.5.8): 未登记且现货/永续差>5% 应判同名冲突不给价"; fail=$((fail+1)); }
n=$((n+1)); _gt "$GT/c1.json" t ONE | grep -q 'Gate·永续·24h last=0.00381' || { echo "❌ gate.py(v3.5.8): 注册表钉 futures 应只取永续"; fail=$((fail+1)); }
n=$((n+1)); _gt "$GT/c0.json" t KNOTS | grep -q 'CoinGecko cg_id=knots' || { echo "❌ gate.py(v3.5.8): Gate 没有时应给出 CoinGecko cg_id"; fail=$((fail+1)); }
printf '12564｜crypto｜ONE｜ONE 题\n12529｜crypto｜ENA,Ethena｜x\n10000002963｜tradfi｜BE｜y\n12485｜crypto｜CFG｜z\n' > "$GT/l.txt"
_GL=$(_gt "$GT/c1.json" list "$GT/l.txt")
n=$((n+1)); echo "$_GL" | grep -q '^GATE: 行=4 取到=2 同名冲突=0 Gate没有=1 tradfi=1' || { echo "❌ gate.py(v3.5.8): list 汇总不对: $(echo "$_GL" | tail -1)"; fail=$((fail+1)); }
printf '12605｜crypto｜USDe,Ethena,ENA｜USDe脱锚\n' > "$GT/l2.txt"
n=$((n+1)); _gt "$GT/c0.json" list "$GT/l2.txt" | grep -q '^12605｜USDE｜' || { echo "❌ gate.py(v3.5.10): keywords 首个代号 USDe(混写)应认成 USDE,不许跳到 ENA"; fail=$((fail+1)); }
printf '[]' > "$GT/e.json"
n=$((n+1)); GATE_SPOT_JSON="$GT/e.json" GATE_FUT_JSON="$GT/e.json" CONTRACTS_JSON="$GT/c0.json" python3 "$D/gate.py" t ONE >/dev/null 2>&1 && { echo "❌ gate.py(v3.5.8): 两个端点都空时应退出码非0(通道故障),不许报 Gate 没有"; fail=$((fail+1)); }
rm -rf "$GT"

# ── v3.5.9(09-22,待办 20):Evose 里钉合约——dex.py --evidence 不连网入册、contracts-sync 每轮写回与叠加、plan-check 钉合约段 ─────
CS=$(mktemp -d); mkdir -p "$CS/st"
printf '{"tokens":{"OLD":{"chain":"bsc","address":"0x9999999999999999999999999999999999999999"}},"blocked":{},"price_map":{}}' > "$CS/base.json"
cp "$CS/base.json" "$CS/c.json"; cp "$CS/c.json" "$CS/start.json"
_A=0x1111111111111111111111111111111111111111
n=$((n+1)); CONTRACTS_JSON="$CS/c.json" python3 "$D/dex.py" pin NEWT bsc $_A '深潮原文' --evidence "NEWT｜bsc｜$_A" >/dev/null 2>&1 || { echo "❌ dex.py(v3.5.9): --evidence 带地址与依据应入册"; fail=$((fail+1)); }
n=$((n+1)); CONTRACTS_JSON="$CS/c.json" python3 "$D/dex.py" pin QQQ bsc 0x2222222222222222222222222222222222222222 '依据' --evidence "QQQ｜bsc｜$_A" >/dev/null 2>&1 && { echo "❌ dex.py(v3.5.9): 核实原文里没有该地址应拒绝入册"; fail=$((fail+1)); }
n=$((n+1)); CONTRACTS_JSON="$CS/c.json" python3 "$D/dex.py" pin EEE eth 0x3333333333333333333333333333333333333333 '依据' --evidence "EEE eth 0x3333333333333333333333333333333333333333" >/dev/null 2>&1; python3 -c "import json,sys;sys.exit(json.load(open('$CS/c.json'))['tokens']['EEE']['chain']!='ethereum')" || { echo "❌ dex.py(v3.5.9): GeckoTerminal 链名 eth 应换算成登记表的 ethereum"; fail=$((fail+1)); }
python3 "$D/contracts-sync.py" diff "$CS/start.json" "$CS/c.json" 1790000000001 "$CS/st" >/dev/null
n=$((n+1)); [ -f "$CS/st/contracts-delta-1790000000001.json" ] || { echo "❌ contracts-sync(v3.5.9): 有变化应写出变化文件"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/contracts-sync.py" diff "$CS/start.json" "$CS/c.json" 1790000000001 "$CS/st" >/dev/null 2>&1 && { echo "❌ contracts-sync(v3.5.9): 同名变化文件已存在应拒写"; fail=$((fail+1)); }
cp "$CS/base.json" "$CS/r.json"; python3 "$D/contracts-sync.py" apply "$CS/r.json" "$CS/st" >/dev/null
n=$((n+1)); python3 -c "import json,sys;d=json.load(open('$CS/r.json'));sys.exit(not('NEWT' in d['tokens'] and 'OLD' in d['tokens']))" || { echo "❌ contracts-sync(v3.5.9): 叠加后应既有底版又有本轮钉的"; fail=$((fail+1)); }
CONTRACTS_JSON="$CS/base.json" python3 "$D/contracts-sync.py" pull "$CS/st" >/dev/null; cp "$CS/base.json" "$CS/r2.json"
n=$((n+1)); python3 "$D/contracts-sync.py" apply "$CS/r2.json" "$CS/st" | grep -q '跳过(≤底版cut 1790000000001)=1' || { echo "❌ contracts-sync(v3.5.9): 本机 pull 过的变化文件开跑时应跳过"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/contracts-sync.py" diff "$CS/start.json" "$CS/start.json" 1790000000002 "$CS/st" | grep -q '无变化' && [ ! -f "$CS/st/contracts-delta-1790000000002.json" ] || { echo "❌ contracts-sync(v3.5.9): 无变化不应写文件"; fail=$((fail+1)); }
cp "$CS/st/contracts-delta-1790000000001.json" "$CS/st/contracts-delta-1790000000009.json"
n=$((n+1)); python3 "$D/contracts-sync.py" apply "$CS/r.json" "$CS/st" >/dev/null 2>&1 && { echo "❌ contracts-sync(v3.5.9): 文件名与内容 run_ts 不一致应拒绝叠加"; fail=$((fail+1)); }
printf '【决策表】\n12604｜crypto｜T｜留｜-｜留档｜判据\n【钉合约】\nNEWT｜bsc｜%s｜钉｜深潮原文\nFAKE｜bsc｜0x4444444444444444444444444444444444444444｜钉｜自拟\n' $_A > "$CS/aud.txt"
printf '【待钉候选】\nNEWT｜bsc｜%s｜NewT｜vol 1.2M\n' $_A > "$CS/scan.txt"
n=$((n+1)); python3 "$D/plan-check.py" "$CS/aud.txt" "$CS/scan.txt" | grep -q 'FAIL	PIN FAKE' || { echo "❌ plan-check(v3.5.9): 地址不在扫描员【待钉候选】里的「钉」应 FAIL"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/plan-check.py" "$CS/aud.txt" "$CS/scan.txt" | grep -q 'FAIL	PIN NEWT' && { echo "❌ plan-check(v3.5.9): 地址来自候选的「钉」不应 FAIL"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/contracts-sync.py" apply "$CS/base.json" "$CS/none/contracts-delta-*.json" | grep -q '变化文件=0' || { echo "❌ contracts-sync(v3.5.9): 项目里还没有变化文件(通配符没匹配到)应视为 0 个,不许报错停跑"; fail=$((fail+1)); }
rm -rf "$CS"

# ── v3.5.10(09-22):write-audit.py 台账外写操作检测——Evose 子 Agent 能经 exec_tool 调到写工具,收尾比对开跑/收尾 B0 ─────
WA=$(mktemp -d)
printf '{"date_range":"2026-09-19 ~ 2026-09-22","topics":[{"id":1,"title":"A","status":0,"keywords":"a","created_at":"2026-09-21 10:00:00"},{"id":2,"title":"B","status":0,"keywords":"b","created_at":"2026-09-21 10:00:00"},{"id":3,"title":"C","status":0,"keywords":"c","created_at":"2026-09-21 10:00:00"},{"id":4,"title":"D","status":0,"keywords":"d","created_at":"2026-09-18 10:00:00"},{"id":6,"title":"F","status":2,"keywords":"f","created_at":"2026-09-21 10:00:00"}]}' > "$WA/b.json"
printf '{"date_range":"2026-09-19 ~ 2026-09-22","topics":[{"id":1,"title":"A2","status":0,"keywords":"a","created_at":"2026-09-21 10:00:00"},{"id":2,"title":"B被改","status":0,"keywords":"b","created_at":"2026-09-21 10:00:00"},{"id":5,"title":"E","status":2,"keywords":"e","created_at":"2026-09-22 11:00:00"},{"id":6,"title":"F","status":2,"keywords":"f","created_at":"2026-09-21 10:00:00"}]}' > "$WA/a.json"
printf '# hdr\n1790000000000\tupdate\t1\t改数字-定稿\t-\tA→A2\n1790000000000\tupdate\t6\t改数字-定稿\t-\tF→F2\n1780000000000\tupdate\t2\t旧轮\t-\t-\n' > "$WA/act.tsv"
_WO=$(python3 "$D/write-audit.py" "$WA/b.json" "$WA/a.json" 1790000000000 "$WA/act.tsv"); _WR=$?
n=$((n+1)); echo "$_WO" | grep -q '🚨 台账外改动	2	title: B → B被改' || { echo "❌ write-audit(v3.5.10): 台账外改标题应报 🚨"; fail=$((fail+1)); }
n=$((n+1)); echo "$_WO" | grep -q '🚨 台账外改动	3	消失' || { echo "❌ write-audit(v3.5.10): 窗口内的题台账外消失应报 🚨"; fail=$((fail+1)); }
n=$((n+1)); echo "$_WO" | grep -q '	4	' && { echo "❌ write-audit(v3.5.10): 滑出日期窗口的题不该报"; fail=$((fail+1)); }
n=$((n+1)); echo "$_WO" | grep -q 'ℹ️ 新增未记	5' || { echo "❌ write-audit(v3.5.10): 新增未记应提示"; fail=$((fail+1)); }
n=$((n+1)); echo "$_WO" | grep -q '⚠️ 台账无效果	6' || { echo "❌ write-audit(v3.5.10): 台账记了改但线上没变应提醒"; fail=$((fail+1)); }
n=$((n+1)); echo "$_WO" | grep -q '	1	' && { echo "❌ write-audit(v3.5.10): 台账有记录且线上变了不该报"; fail=$((fail+1)); }
n=$((n+1)); [ "$_WR" -eq 1 ] && echo "$_WO" | tail -1 | grep -q '^WRITE-AUDIT: 台账写题=2 线上有变化=4 台账外改动=2 台账无效果=1 新增未记=1' || { echo "❌ write-audit(v3.5.10): 汇总或退出码不对: $(echo "$_WO" | tail -1) rc=$_WR"; fail=$((fail+1)); }
printf '{"topics":[{"id":7,"title":"G","status":0,"keywords":"g","created_at":"2026-09-18 23:00:00"},{"id":8,"title":"H","status":0,"keywords":"h","created_at":"2026-09-20 10:00:00"}]}' > "$WA/b2.json"
printf '{"topics":[{"id":8,"title":"H","status":0,"keywords":"h","created_at":"2026-09-20 10:00:00"}]}' > "$WA/a2.json"
n=$((n+1)); python3 "$D/write-audit.py" "$WA/b2.json" "$WA/a2.json" 1790000000000 "$WA/act.tsv" >/dev/null || { echo "❌ write-audit(v3.5.10): B0 无 date_range 时,早于收尾最早题日期的消失应视为滑出窗口"; fail=$((fail+1)); }
rm -rf "$WA"

# ── v3.5.11(09-23):leak-guard.py 导出/推送前查凭证——项目文件与附件链接公开,密钥落进去才是真外泄 ─────
LG=$(mktemp -d); mkdir -p "$LG/out" "$LG/h/.trend-scout"
_K='FAKEkeyAAAAbbbbCCCCddddEEEEffff0123456789+/='; _S='larkFakeSecret0123456789abcdefXY'
_KFP=$(python3 -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$_K")
printf '正常报告\n' > "$LG/out/ok.md"
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/leak-guard.py" --fp "$_KFP" "$LG/out" >/dev/null || { echo "❌ leak-guard(v3.5.11): 干净目录应退出 0"; fail=$((fail+1)); }
printf 'x %s y\n' "$_K" > "$LG/out/full.md"
_LO=$(LEDGER_KEY="$_K" python3 "$D/leak-guard.py" "$LG/out" 2>&1); _LR=$?
n=$((n+1)); [ "$_LR" -eq 1 ] && echo "$_LO" | grep -q "full.md	LEDGER_KEY" || { echo "❌ leak-guard(v3.5.11): 含密钥全串应命中退出 1"; fail=$((fail+1)); }
n=$((n+1)); echo "$_LO" | grep -qF "${_K:5:16}" && { echo "❌ leak-guard(v3.5.11): 输出里不许出现密钥片段"; fail=$((fail+1)); }
rm "$LG/out/full.md"; printf '规则面板给的是 %s…\n' "${_K:10:17}" > "$LG/out/part.md"
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/leak-guard.py" "$LG/out" >/dev/null 2>&1; [ $? -eq 1 ] || { echo "❌ leak-guard(v3.5.11): 截出 ≥16 字符的一段也应命中"; fail=$((fail+1)); }
rm "$LG/out/part.md"; printf '%s\n' "$_K" | gzip > "$LG/out/j.md.gz"
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/leak-guard.py" "$LG/out" >/dev/null 2>&1; [ $? -eq 1 ] || { echo "❌ leak-guard(v3.5.11): .gz 应解开查"; fail=$((fail+1)); }
rm "$LG/out/j.md.gz"; mkdir -p "$LG/t"; printf 'secret=%s\n' "$_S" > "$LG/t/r.txt"; tar -czf "$LG/out/b.tar.gz" -C "$LG/t" r.txt
n=$((n+1)); LEDGER_KEY="$_K" LARK_APP_SECRET="$_S" python3 "$D/leak-guard.py" "$LG/out" 2>&1 | grep -q 'b.tar.gz!r.txt	LARK_APP_SECRET' || { echo "❌ leak-guard(v3.5.11): tar.gz 成员里的 App Secret 应命中"; fail=$((fail+1)); }
rm "$LG/out/b.tar.gz"; printf '%s' "$_K" > "$LG/out/x.csv.enc"
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/leak-guard.py" "$LG/out" | grep -q '跳过密文=1 命中=0' || { echo "❌ leak-guard(v3.5.11): .enc 是密文应跳过"; fail=$((fail+1)); }
n=$((n+1)); env -u LEDGER_KEY HOME="$LG/h" python3 "$D/leak-guard.py" "$LG/out" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ leak-guard(v3.5.11): 没有密钥应退出 2,不许当作查过"; fail=$((fail+1)); }
n=$((n+1)); LEDGER_KEY="wrong$_K" python3 "$D/leak-guard.py" --fp "$_KFP" "$LG/out" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ leak-guard(v3.5.11): 指纹不符应退出 2"; fail=$((fail+1)); }
touch "$LG/h/.trend-scout/.BOOTSTRAP-NOKEY"
n=$((n+1)); env -u LEDGER_KEY HOME="$LG/h" python3 "$D/leak-guard.py" --allow-nokey "$LG/out" | grep -q 'SKIP' || { echo "❌ leak-guard(v3.5.11): 免解密环境加 --allow-nokey 应 SKIP 退出 0"; fail=$((fail+1)); }
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/leak-guard.py" "$LG/nosuch" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ leak-guard(v3.5.11): 路径不存在应退出 2"; fail=$((fail+1)); }
rm -rf "$LG"

# ── v3.5.12(09-23):ledger-sync.py 本机台账→项目持续同步——长期密钥、公钥打包、开跑以同步包为底版再追加 Evose 分片 ─────
LS=$(mktemp -d); mkdir -p "$LS/loc/reports" "$LS/sb" "$LS/in" "$LS/k" "$LS/sb2"
_K='FAKEkeyAAAAbbbbCCCCddddEEEEffff0123456789+/='
_KFP=$(python3 -c "import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:16])" "$_K")
for f in actions.tsv snapshots.tsv checklists.log.tsv event-watch.tsv circuit-log.tsv drift.tsv lark-push.log.tsv review-verify.log.tsv actions-rejected.tsv; do printf '# hdr\n1790000000000\tloc\n' > "$LS/loc/$f"; done
printf '1789000000000\n1790000000000\n' > "$LS/loc/last-refresh.txt"; echo rev > "$LS/loc/reports/review-1790000000000.md"; echo r > "$LS/loc/reports/round-1790000000000.md"
touch -t 202609201200 "$LS/loc/reports/review-1790000000000.md"
n=$((n+1)); LEDGER_KEY="$_K" python3 "$D/ledger-sync.py" keygen --fp "$_KFP" "$LS/k" 2>/dev/null | grep -q '自检=一致' || { echo "❌ ledger-sync(v3.5.12): keygen 应生成并自检私钥密文"; fail=$((fail+1)); }
n=$((n+1)); LEDGER_KEY="wrong$_K" python3 "$D/ledger-sync.py" keygen --fp "$_KFP" "$LS/k2" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.12): 指纹不符 keygen 应退出 2"; fail=$((fail+1)); }
_PO=$(LEDGER_SYNC_HOME="$LS/loc" python3 "$D/ledger-sync.py" pack "$LS/k/inbox-pub.pem" "$LS/in" 2>&1)
n=$((n+1)); echo "$_PO" | grep -q '^PACK: cut=1790000000000 台账=10 复审=1 周报=0 文件=11' || { echo "❌ ledger-sync(v3.5.12): pack 汇总不对(round- 报告不该进包): $(echo "$_PO" | head -1)"; fail=$((fail+1)); }
# v3.7.11(10-22 回流):evose-included.txt 里记的 Evose 分片进 includes_shards,Evose 开跑不再重复追加
n=$((n+1)); echo "$_PO" | grep -q '包内已含 Evose 分片=0' || { echo "❌ ledger-sync(v3.7.11): 没有 evose-included.txt 时应报 0 片: $(echo "$_PO" | head -1)"; fail=$((fail+1)); }
printf 'actions-1790000000001.csv.enc\npushes-1790000000002.csv.enc\nactions-1790000000001.csv.enc\n' > "$LS/loc/evose-included.txt"
_PO2=$(LEDGER_SYNC_HOME="$LS/loc" python3 "$D/ledger-sync.py" pack "$LS/k/inbox-pub.pem" "$LS/in-inc" 2>&1)
n=$((n+1)); echo "$_PO2" | grep -q '包内已含 Evose 分片=2' || { echo "❌ ledger-sync(v3.7.11): evose-included.txt 应去重后进 includes_shards(2 片): $(echo "$_PO2" | head -1)"; fail=$((fail+1)); }
rm -f "$LS/loc/evose-included.txt"
# v3.7.11(10-22 循环第 3、4 环):包里带最近一份复盘;--final 终版包 cut 取打包时刻(本机不再出 last-refresh)
mkdir -p "$LS/loc/retro"; echo '## 今天注意' > "$LS/loc/retro/2026-10-20.md"; echo '## 今天注意' > "$LS/loc/retro/2026-10-21.md"
_PO3=$(LEDGER_SYNC_HOME="$LS/loc" python3 "$D/ledger-sync.py" pack "$LS/k/inbox-pub.pem" "$LS/in-fin" --final 2>&1)
n=$((n+1)); echo "$_PO3" | grep -q '复盘=1 终版(本机已停写)' && ! echo "$_PO3" | grep -q '^PACK: cut=1790000000000' && ls "$LS/in-fin" | grep -q '^sync-17[0-9]\{11\}\.tar\.gz\.enc$' || { echo "❌ ledger-sync(v3.7.11): pack --final 应只带最近一份复盘、cut 取打包时刻: $(echo "$_PO3" | head -1)"; fail=$((fail+1)); }
rm -rf "$LS/loc/retro"
n=$((n+1)); LEDGER_SYNC_HOME="$LS/loc" python3 "$D/ledger-sync.py" pack "$LS/k/inbox-pub.pem" "$LS/in" >/dev/null 2>&1 && { echo "❌ ledger-sync(v3.5.12): 同 cut 的同步包已存在应拒写"; fail=$((fail+1)); }
cp "$LS/k/inbox-priv.pem.enc" "$LS/in/"
printf '1790500000000\tevose\n' > "$LS/in/actions-1790500000000.csv"; : > "$LS/in/actions-1790500000000.csv.enc"
printf '1789500000000\n' > "$LS/in/last-refresh-1789500000000.csv"; : > "$LS/in/last-refresh-1789500000000.csv.enc"
printf 'old\n' > "$LS/in/actions-migration-1789029709000.csv"; : > "$LS/in/actions-migration-1789029709000.csv.enc"
echo agent > "$LS/in/review-agent.md"; echo evrev > "$LS/in/review-1790500000000.md"; : > "$LS/in/review-1790500000000.md.enc"
echo other > "$LS/in/review-1790000000000.md"; : > "$LS/in/review-1790000000000.md.enc"
n=$((n+1)); LEDGER_KEY="$_K" LEDGER_SYNC_HOME="$LS/sb" python3 "$D/ledger-sync.py" open --fp "$_KFP" "$LS/in" 2>/dev/null | grep -q '^SYNC: cut=1790000000000 文件=11 台账=10 复审=1 周报=0 清单核对=一致' || { echo "❌ ledger-sync(v3.5.12): open 应解开同步包并核清单"; fail=$((fail+1)); }
n=$((n+1)); python3 -c "import os,sys;sys.exit(int(os.path.getmtime(sys.argv[1]))!=int(os.path.getmtime(sys.argv[2])))" "$LS/sb/reports/review-1790000000000.md" "$LS/loc/reports/review-1790000000000.md" || { echo "❌ ledger-sync(v3.5.12): 复审文件 mtime 应原样保留(lark-push 按 mtime 认当前复审)"; fail=$((fail+1)); }
n=$((n+1)); LEDGER_KEY="$_K" LEDGER_SYNC_HOME="$LS/sb" python3 "$D/ledger-sync.py" open --fp "$_KFP" "$LS/in" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.12): 台账已存在且非空时 open 应拒绝(防把同步包铺在有数据的环境上)"; fail=$((fail+1)); }
_AO=$(LEDGER_SYNC_HOME="$LS/sb" python3 "$D/ledger-sync.py" append "$LS/in" 2>&1)
n=$((n+1)); echo "$_AO" | grep -q '^APPEND: 分片=2 追加行=2 复审/周报放入=1 同名以同步包为准=1 待补发=0 跳过迁移分片=1 跳过包内已含=0 last-refresh末行补正=1' || { echo "❌ ledger-sync(v3.5.12): append 汇总不对: $_AO"; fail=$((fail+1)); }
n=$((n+1)); [ -f "$LS/sb/.sync-mark.json" ] || { echo "❌ ledger-sync(v3.5.13): append 结束应自动 mark(第 13 步 delta 从这里算起)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(tail -1 "$LS/sb/last-refresh.txt")" = 1790000000000 ] && grep -q 'evose' "$LS/sb/actions.tsv" && ! grep -q '^old' "$LS/sb/actions.tsv" && [ "$(cat "$LS/sb/reports/review-1790000000000.md")" = rev ] && [ ! -f "$LS/sb/reports/review-agent.md" ] || { echo "❌ ledger-sync(v3.5.12): 追加后内容不对(末行应为最大值/迁移分片不追加/同名复审以包为准/无 .enc 的文件不收)"; fail=$((fail+1)); }
n=$((n+1)); python3 -c "import os,sys;sys.exit(int(os.path.getmtime(sys.argv[1]))!=1790500000)" "$LS/sb/reports/review-1790500000000.md" || { echo "❌ ledger-sync(v3.5.12): 追加进来的 Evose 复审 mtime 应按文件名 run_ts 摆回,不能是解密时刻(否则被 lark-push 当成最新复审)"; fail=$((fail+1)); }
cp "$LS/in/sync-1790000000000.tar.gz.enc" "$LS/in/sync-1790000000001.tar.gz.enc"; cp "$LS/in/sync-1790000000000.key.rsa" "$LS/in/sync-1790000000001.key.rsa"
n=$((n+1)); LEDGER_KEY="$_K" LEDGER_SYNC_HOME="$LS/sb2" python3 "$D/ledger-sync.py" open --fp "$_KFP" "$LS/in" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.12): 文件名 cut 与包内不一致(被改名)应拒绝"; fail=$((fail+1)); }
rm -rf "$LS"

# ── v3.5.13(09-23):ledger-sync.py mark/delta——写回增量由脚本按字节切,不再让 Lead 手挑(第 27 轮漏了 review-verify.log) ─────
LD=$(mktemp -d); mkdir -p "$LD/h/reports" "$LD/o"
for f in actions.tsv snapshots.tsv checklists.log.tsv event-watch.tsv circuit-log.tsv drift.tsv lark-push.log.tsv review-verify.log.tsv actions-rejected.tsv last-refresh.txt; do printf '# hdr\n1790000000000\told\n' > "$LD/h/$f"; done
echo old > "$LD/h/reports/review-1790000000000.md"; echo agent > "$LD/h/reports/round-1790000000000.md"
n=$((n+1)); LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" mark | grep -q '^MARK: 台账=10' || { echo "❌ ledger-sync(v3.5.13): mark 应记下 10 份台账"; fail=$((fail+1)); }
printf '1790600000000\tupdate\t1\t新\n1790600000001\tcreate\t2\t新\n' >> "$LD/h/actions.tsv"; printf '1790600000002\t1790600000000\tPASS\tx\n' >> "$LD/h/review-verify.log.tsv"; echo new > "$LD/h/reports/review-1790600000000.md"
_DO=$(LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" delta 1790600000000 "$LD/o" 2>&1)
n=$((n+1)); echo "$_DO" | grep -q '^DELTA: run_ts=1790600000000 写出分片=2 新复审/周报=1 未变=8' || { echo "❌ ledger-sync(v3.5.13): delta 汇总不对: $(echo "$_DO" | tail -1)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(cat "$LD/o/actions-1790600000000.csv")" = "$(printf '1790600000000\tupdate\t1\t新\n1790600000001\tcreate\t2\t新')" ] && [ -f "$LD/o/review-verify-1790600000000.csv" ] && [ -f "$LD/o/review-1790600000000.md" ] && [ ! -f "$LD/o/round-1790000000000.md" ] || { echo "❌ ledger-sync(v3.5.13): delta 切出的增量不对(应只含 mark 之后追加的字节,新复审拷出,round- 不收)"; fail=$((fail+1)); }
n=$((n+1)); LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" delta 1790600000009 "$LD/o" | grep -q '写出分片=0 新复审/周报=0' || { echo "❌ ledger-sync(v3.5.13): delta 后 mark 应前移,再跑一次应为 0"; fail=$((fail+1)); }
printf '1790600000003\tnote\t3\t再\n' >> "$LD/h/actions.tsv"
n=$((n+1)); LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" delta 1790600000000 "$LD/o" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.13): 同一台账同一 run_ts 已写过一片应拒绝,不覆盖"; fail=$((fail+1)); }
sed -i.bak 's/old/OLD/' "$LD/h/drift.tsv"
n=$((n+1)); LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" delta 1790600000005 "$LD/o" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.13): 开跑后台账被改写(不是只追加)应退出 2"; fail=$((fail+1)); }
rm -f "$LD/h/.sync-mark.json"
n=$((n+1)); LEDGER_SYNC_HOME="$LD/h" python3 "$D/ledger-sync.py" delta 1790600000006 "$LD/o" >/dev/null 2>&1; [ $? -eq 2 ] || { echo "❌ ledger-sync(v3.5.13): 没有 mark 应退出 2"; fail=$((fail+1)); }
rm -rf "$LD"

# ── v3.5.14(09-23):plan-check --b0 核在线题 domain——第 27 轮审核员拿不到 domain 只能按题号猜,tradfi 猜成 crypto 会让写手跳过时段前缀闸 ─────
PB=$(mktemp -d)
printf '{"topics":[{"id":10000002981,"domain":"tradfi","title":"T","status":0},{"id":12633,"domain":"crypto","title":"C","status":0}]}' > "$PB/b0.json"
printf '【决策表】\n10000002981｜crypto｜T｜留｜-｜留档｜判据\n12633｜crypto｜C｜留｜-｜留档｜判据\n' > "$PB/a1.txt"
n=$((n+1)); python3 "$D/plan-check.py" "$PB/a1.txt" --b0 "$PB/b0.json" | grep -q 'FAIL	10000002981	domain=crypto 与 B0 不符(B0=tradfi)' || { echo "❌ plan-check(v3.5.14): 在线题 domain 与 B0 不符应 FAIL"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/plan-check.py" "$PB/a1.txt" --b0 "$PB/b0.json" | grep -q '	12633	' && { echo "❌ plan-check(v3.5.14): domain 与 B0 一致的行不该报"; fail=$((fail+1)); }
printf '【决策表】\n99999｜crypto｜X｜留｜-｜留档｜判据\n' > "$PB/a2.txt"
n=$((n+1)); python3 "$D/plan-check.py" "$PB/a2.txt" --b0 "$PB/b0.json" | grep -q 'WARN	99999	B0 里找不到这道题' || { echo "❌ plan-check(v3.5.14): B0 里没有的在线题应 WARN"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/plan-check.py" "$PB/a1.txt" >/dev/null; [ $? -eq 0 ] || { echo "❌ plan-check(v3.5.14): 不给 --b0 时保持旧行为(不核 domain 对错)"; fail=$((fail+1)); }
# ── v3.6.3(09-30 用户定):plan-check --b0 查撤 meme 行的四查行——漏写或写在判据 150 字之后,落账会被 log-action 拒写(前台已撤、台账没记) ─────
printf '{"topics":[{"id":12901,"domain":"crypto","title":"ZZMEME热度升温","keywords":"ZZMEME","status":0},{"id":12902,"domain":"crypto","title":"ZZMEME再度走强","keywords":"ZZMEME","status":0},{"id":12903,"domain":"crypto","title":"ZZMEME情绪升温","keywords":"ZZMEME","status":0},{"id":10000002990,"domain":"tradfi","title":"ZZ公司跌2%%","keywords":"ZZCO","status":0},{"id":12904,"domain":"crypto","title":"BTC热度升温","keywords":"BTC","status":0}]}' > "$PB/b0m.json"
_PAD=$(python3 -c "print('判据正文'*40)")
{ printf '【决策表】\n'
  printf '12901｜crypto｜ZZMEME热度升温｜撤｜-｜缺诱因-未达线｜四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ 本轮实测 24h +3%%\n'
  printf '12902｜crypto｜ZZMEME再度走强｜撤｜-｜缺诱因-未达线｜%s 四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗\n' "$_PAD"
  printf '12903｜crypto｜ZZMEME情绪升温｜撤｜-｜缺诱因-未达线｜四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✓ 上所\n'
  printf '10000002990｜tradfi｜ZZ公司跌2%%｜撤｜-｜缺诱因-未达线｜涨跌不到 10%% 且诱因只是传闻\n'
  printf '12904｜crypto｜BTC热度升温｜撤｜-｜缺价格腿｜主流币,没有标的被定价\n'; } > "$PB/a3.txt"
_P4=$(TOKEN_EXISTS_JSON="$D/tests/token-exist-fixture.json" python3 "$D/plan-check.py" "$PB/a3.txt" --b0 "$PB/b0m.json" 2>&1)
n=$((n+1)); echo "$_P4" | grep -q $'^FAIL\t12901\t' && { echo "❌ plan-check(v3.6.3): 四查行在判据开头应 OK: $(echo "$_P4" | grep 12901 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P4" | grep -q $'^FAIL\t12902\t.*没有四查行' || { echo "❌ plan-check(v3.6.3): 四查行在第 150 字之后应 FAIL: $(echo "$_P4" | grep 12902 | cut -c1-80)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P4" | grep -q $'^FAIL\t12903\t.*没有四查行' || { echo "❌ plan-check(v3.6.3): 「硬事件✓」不是四格全否,应 FAIL: $(echo "$_P4" | grep 12903 | cut -c1-80)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P4" | grep -q $'^FAIL\t10000002990\t' && { echo "❌ plan-check(v3.6.3): tradfi 行用 缺诱因-未达线 不要求四查行: $(echo "$_P4" | grep 10000002990 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P4" | grep -q $'^FAIL\t12904\t' && { echo "❌ plan-check(v3.6.3): 主流币撤行不要求四查行: $(echo "$_P4" | grep 12904 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P4" | grep -q '^PLAN: 行=5 .*FAIL=2 ' || { echo "❌ plan-check(v3.6.3): 5 行里应恰好 2 行 FAIL: $(echo "$_P4" | head -1)"; fail=$((fail+1)); }
n=$((n+1)); TOKEN_EXISTS_JSON="$D/tests/token-exist-fixture.json" python3 "$D/plan-check.py" "$PB/a3.txt" >/dev/null; [ $? -eq 0 ] || { echo "❌ plan-check(v3.6.3): 不给 --b0 时不查四查行(写手沙箱没有 B0)"; fail=$((fail+1)); }
# ── v3.6.4(10-01 用户定,Evose 第 51 轮):建/改 新标题缺价格腿从 WARN 升 FAIL,判据写「免价格腿:监管/上架/硬事件/预告」才放行 ─────
{ printf '【决策表】\n'
  printf '12911｜tradfi｜ZZ Holdings Inc.宣布展示新模块涨5.7%%｜改｜ZZ宣布将展示新模块｜改样式-命名｜去掉法人全名\n'
  printf '12912｜crypto｜旧标题ZZ｜改｜SEC批准ZZ现货ETF｜改样式-命名｜免价格腿：监管 SEC 公告\n'
  printf '12913｜crypto｜旧标题YY｜改｜YY宣布将于10月5日主网上线｜改样式-命名｜预告题\n'
  printf '12914｜tradfi｜ZZ Holdings Inc.宣布展示新模块｜改｜ZZ宣布展示新模块，盘中涨5.7%%｜改样式-命名｜补本轮实测价\n'
  printf '12915｜crypto｜旧标题WW｜改｜WW宣布新合作｜改样式-命名｜免价格腿：合作\n'; } > "$PB/a4.txt"
_P5=$(python3 "$D/plan-check.py" "$PB/a4.txt" 2>&1); _p5rc=$?
n=$((n+1)); echo "$_P5" | grep -q $'^FAIL\t12911\t.*没有价格腿' || { echo "❌ plan-check(v3.6.4): 改出无价格腿新标题应 FAIL: $(echo "$_P5" | grep 12911 | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P5" | grep -q $'^FAIL\t12912\t' && { echo "❌ plan-check(v3.6.4): 判据写明 免价格腿：监管 应放行(留 WARN 交人复核): $(echo "$_P5" | grep 12912 | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P5" | grep -q $'\t12913\t' && { echo "❌ plan-check(v3.6.4): 预告题不要求价格腿: $(echo "$_P5" | grep 12913 | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P5" | grep -q $'^FAIL\t12914\t' && { echo "❌ plan-check(v3.6.4): 带价格腿的新标题不该 FAIL: $(echo "$_P5" | grep 12914 | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P5" | grep -q $'^FAIL\t12915\t.*没有价格腿' || { echo "❌ plan-check(v3.6.4): 免价格腿只认 监管/上架/硬事件/预告,自造类别应 FAIL"; fail=$((fail+1)); }
n=$((n+1)); [ $_p5rc -eq 1 ] && echo "$_P5" | grep -q '^PLAN: 行=5 .*FAIL=2 ' || { echo "❌ plan-check(v3.6.4): 5 行应恰好 2 行 FAIL、exit 1: rc=$_p5rc $(echo "$_P5" | head -1)"; fail=$((fail+1)); }
# ── v3.7.20(10-30 用户定,Evose 29c):承接更新只拿「免价格腿:预告」→ FAIL;别的豁免照放;非承接的预告照放 ─────
{ printf '【决策表】\n'
  printf '10000009801｜tradfi｜美国今晚20:30将公布三季度GDP，预期增3.2%%｜改｜美国三季度GDP年化增3.4%%，超预期3.2%%｜承接更新｜免价格腿：预告 到期承接\n'
  printf '10000009802｜crypto｜SEC将于今晚表决ZZ现货ETF｜改｜SEC批准ZZ现货ETF｜承接更新｜免价格腿：监管 SEC 公告\n'
  printf '10000009803｜crypto｜旧标题YY｜改｜YY宣布将于11月5日主网上线｜改样式-命名｜免价格腿：预告\n'; } > "$PB/a20.txt"
_P20=$(python3 "$D/plan-check.py" "$PB/a20.txt" 2>&1)
n=$((n+1)); echo "$_P20" | grep -q $'^FAIL\t10000009801\t.*承接更新' || { echo "❌ plan-check(v3.7.20): 承接更新拿预告免价格腿应 FAIL: $(echo "$_P20" | grep 9801 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P20" | grep -q $'^FAIL\t10000009802\t' && { echo "❌ plan-check(v3.7.20): 承接更新写监管豁免应放行: $(echo "$_P20" | grep 9802 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P20" | grep -q $'^FAIL\t10000009803\t' && { echo "❌ plan-check(v3.7.20): 非承接的预告题照放: $(echo "$_P20" | grep 9803 | cut -c1-120)"; fail=$((fail+1)); }
# ── v3.6.5(10-02 用户定,Evose 第 53 轮):tradfi 建/改 新标题有涨跌%没时段词 → FAIL(与写手第 4 条同一词表) ─────
{ printf '【决策表】\n'
  printf '10000009901｜tradfi｜旧标题A｜改｜Vicor获大单涨12%%｜改样式-命名｜补价\n'
  printf '10000009902｜tradfi｜旧标题B｜改｜Vicor获大单，盘中涨12%%｜改样式-命名｜补价\n'
  printf '10000009903｜tradfi｜旧标题C｜改｜Vicor获大单，收报35美元｜改样式-命名｜补价\n'
  printf '12921｜crypto｜旧标题D｜改｜ZZ上线币安涨32%%｜改样式-命名｜补价\n'; } > "$PB/a5.txt"
_P6=$(python3 "$D/plan-check.py" "$PB/a5.txt" 2>&1)
n=$((n+1)); echo "$_P6" | grep -q $'^FAIL\t10000009901\t.*时段词' || { echo "❌ plan-check(v3.6.5): tradfi 有涨跌%无时段词应 FAIL: $(echo "$_P6" | grep 9901 | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P6" | grep -q $'^FAIL\t1000000990[23]\t' && { echo "❌ plan-check(v3.6.5): 带盘中/只有报价的 tradfi 标题不该 FAIL: $(echo "$_P6" | grep -E '990[23]' | cut -c1-100)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P6" | grep -q $'^FAIL\t12921\t' && { echo "❌ plan-check(v3.6.5): crypto 题不查时段词"; fail=$((fail+1)); }
# ── v3.6.7(10-14 用户定):改题摘掉原诱因、新标题落成缺诱因 → FAIL(09-28 Evose 10000003016/3017 复现) ─────
{ printf '【决策表】\n'
  printf '10000009911｜tradfi｜美债收益率走高，KOSPI收跌2.4%%｜改｜KOSPI收跌2.7%%｜改数字-定稿｜原诱因无源摘除\n'
  printf '10000009912｜tradfi｜加息预期升温，黄金盘中跌2.5%%｜改｜特朗普拒绝伊朗停火提议，黄金盘中跌3.2%%｜改归因｜换有源诱因\n'
  printf '10000009913｜tradfi｜KOSPI收跌2.4%%｜改｜KOSPI收跌2.7%%｜改数字-定稿｜原题本就无诱因\n'
  printf '12931｜crypto｜NEAR Intents追回380万美元，NEAR报4.83｜改｜NEAR报4.90｜改数字-定稿｜免诱因：纯行情-A定则\n'
  printf '12932｜crypto｜NEAR Intents追回380万美元，NEAR报4.83｜改｜NEAR报4.90｜改数字-定稿｜更新价格\n'
  printf 'NEW-1｜tradfi｜-｜建｜KOSPI收跌2.7%%｜有诱因-单源待核｜建题不在本闸范围\n'; } > "$PB/a6.txt"
_P7=$(python3 "$D/plan-check.py" "$PB/a6.txt" 2>&1)
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\t10000009911\t.*诱因摘掉' || { echo "❌ plan-check(v3.6.7): 摘掉原诱因成缺诱因应 FAIL: $(echo "$_P7" | grep 9911 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\t10000009912\t' && { echo "❌ plan-check(v3.6.7): 换成有出处的新诱因不该 FAIL: $(echo "$_P7" | grep 9912 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\t10000009913\t' && { echo "❌ plan-check(v3.6.7): 原标题本就缺诱因的照旧 WARN,不升 FAIL"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\t12931\t' && { echo "❌ plan-check(v3.6.7): 判据写明 免诱因：纯行情-A定则 应放行"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\t12932\t.*诱因摘掉' || { echo "❌ plan-check(v3.6.7): crypto 摘掉诱因同样 FAIL: $(echo "$_P7" | grep 12932 | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); echo "$_P7" | grep -q $'^FAIL\tNEW-1\t.*诱因摘掉' && { echo "❌ plan-check(v3.6.7): 本闸只管改题,建题不报「诱因摘掉」"; fail=$((fail+1)); }
rm -rf "$PB"
# ── v3.6.6(10-10 用户批):硬事件词不进 ⑥ 机械撤;价位穿越算价格腿 ─────
_HE=$(cd "$D" && python3 -c 'import lint
for t in ["BLAST宣布停运，用户需迁出资产","Ledger经销商渠道设备失窃","2026年10月9日KAIA上架Upbit","某项目宣布与某链达成合作"]: print(lint.hard_event(t) or "-")' 2>&1)
n=$((n+1)); [ "$(echo "$_HE" | sed -n 1p)" != "-" ] || { echo "❌ ⑥硬事件(v3.6.6): BLAST停运应命中硬事件词"; fail=$((fail+1)); }
n=$((n+1)); [ "$(echo "$_HE" | sed -n 2p)" != "-" ] || { echo "❌ ⑥硬事件(v3.6.6): 失窃应命中硬事件词"; fail=$((fail+1)); }
n=$((n+1)); [ "$(echo "$_HE" | sed -n 3p)" != "-" ] || { echo "❌ ⑥硬事件(v3.6.6): 上架Upbit应命中硬事件词"; fail=$((fail+1)); }
n=$((n+1)); [ "$(echo "$_HE" | sed -n 4p)" = "-" ] || { echo "❌ ⑥硬事件(v3.6.6): 普通合作公告不该命中: $(echo "$_HE" | sed -n 4p)"; fail=$((fail+1)); }

# ── v3.7.0(10-15 用户定「先做 1、2」:修仪表盘 + 机械活收进代码)────────────────
_V=$(mktemp -d)
# ① 建题真实 id:历史「-」行 FIFO 接到其后带「建题后推」的状态修正行;新写法 create 行直接带真实 id;无上线行的「-」不接
printf '%s\n' \
 $'1790000000000\tcreate\t-\t有诱因-多源\t回归:建题A\t-→A题' \
 $'1790000001000\tcreate\t-\t有诱因-多源\t回归:建题B\t-→B题' \
 $'1790000002000\tupdate\t9001\t状态修正\t落此code因=建题后推status=0\t-' \
 $'1790000003000\tupdate\t9002\t状态修正\t落此code因=建题后推status=0\t-' \
 $'1790000004000\tcreate\t9003\t有诱因-多源\t回归:新写法真实id\t-→C题' \
 $'1790000005000\tcreate\t-\t有诱因-多源\t回归:没上线的建题\t-→D题' \
 $'1790099999000\tupdate\t9004\t状态修正\t落此code因=建题后推status=0\t-' > "$_V/a.tsv"
_got=$(ACTIONS="$_V/a.tsv" python3 -c "import sys;sys.path.insert(0,'$D');import ledger;print(','.join(sorted(ledger.created_ids())))")
n=$((n+1)); [ "$_got" = "9001,9002,9003" ] || { echo "❌ ledger(v3.7.0): 建题 id 解析应为 9001,9002,9003(超 2h 的上线行不接),得到 $_got"; fail=$((fail+1)); }
_got=$(python3 -c "import sys;sys.path.insert(0,'$D');import lint;print('-' in lint.created_ids('$_V/a.tsv'))")
n=$((n+1)); [ "$_got" = "False" ] || { echo "❌ lint.created_ids(v3.7.0): 不该再收「-」(b0-audit ⑤ 会把我建的题当系统建)"; fail=$((fail+1)); }
# ② log-action:预检模式不落账;纠错-自纠 必须带标题变更;拒写行带结构列;同动作同 id 其后落账=自动处理;reject-ok 显式处理
_lv(){ ACTIONS="$_V/la.tsv" SNAPSHOTS="$_V/ls.tsv" REJ="$_V/lr.tsv" REJ_OK="$_V/lok.tsv" UNLOGGED="$_V/lu.tsv" B0JSON="$_V/b0.json" "$@" >/dev/null 2>&1; echo $?; }
echo '[{"id":9811,"domain":"tradfi","title":"X收跌7.9%","keywords":"X","status":0,"closed_ts":9999999999999},{"id":9812,"domain":"tradfi","title":"Y收跌5%","keywords":"Y","status":0,"closed_ts":1000}]' > "$_V/b0.json"
n=$((n+1)); [ "$(LA_CHECK=1 _lv "$D/log-action.sh" create - 有诱因-多源 "回归:预检模式不落账" "-→X")" = "0" ] && [ ! -s "$_V/la.tsv" ] || { echo "❌ log-action(v3.7.0): LA_CHECK=1 应只校验不落账"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_lv "$D/log-action.sh" update 9811 纠错-自纠 "回归:纠错缺标题变更" -)" != "0" ] || { echo "❌ log-action(v3.7.0): 纠错-自纠 不带标题变更应拒"; fail=$((fail+1)); }
n=$((n+1)); [ "$(awk -F'\t' 'END{print NF}' "$_V/lr.tsv")" = "5" ] || { echo "❌ log-action(v3.7.0): 拒写行应带 动作/id/rc 三列结构(共5列)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_lv "$D/log-action.sh" update 9811 纠错-自纠 "回归:二次舍入改正" "X收跌7.9%→X收跌7.8%")" = "0" ] || { echo "❌ log-action(v3.7.0): 纠错-自纠 带标题变更应放行"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_lv "$D/log-action.sh" update 9812 纠错-自纠 "回归:过期题纠错应拒" "Y收跌5%→Y收跌6%")" != "0" ] || { echo "❌ log-action(v3.7.0): 过期题 纠错-自纠 应按 v3.6.0 拒(事实错误走撤题)"; fail=$((fail+1)); }
_un=$(ACTIONS="$_V/la.tsv" REJ="$_V/lr.tsv" REJ_OK="$_V/lok.tsv" UNLOGGED="$_V/lu.tsv" python3 "$D/ledger.py" unresolved 0)
n=$((n+1)); [ "$(echo "$_un" | grep -c .)" = "1" ] && echo "$_un" | grep -q 9812 || { echo "❌ ledger(v3.7.0): 9811 拒后已落账应自动处理、只剩 9812 未处理,得到: $_un"; fail=$((fail+1)); }
_rt=$(echo "$_un" | cut -f2)
n=$((n+1)); [ "$(_lv "$D/log-action.sh" reject-ok "$_rt" "回归:过期题改走撤题")" = "0" ] && [ -z "$(ACTIONS="$_V/la.tsv" REJ="$_V/lr.tsv" REJ_OK="$_V/lok.tsv" UNLOGGED="$_V/lu.tsv" python3 "$D/ledger.py" unresolved 0)" ] || { echo "❌ log-action(v3.7.0): reject-ok 后不该再有未处理"; fail=$((fail+1)); }
# ③ pct:只舍入一次;|x|≥10 写整数;方向写反拦
_pc=$(cd "$D" && python3 -c 'import pct
for a,b in [(59.18,64.22),(53.46,37.86),(109.95,100),(100.05,100),(0.9904,1)]: print(pct.fmt(pct.change(a,b)))')
n=$((n+1)); [ "$(echo $_pc)" = "7.8 41 10 0.1 1" ] || { echo "❌ pct(v3.7.0): 标题写法应为 7.8 41 10 0.1 1,得到 $(echo $_pc)"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/pct.py" check "Neutron首飞推迟至2027年，RKLB收跌7.9%" "RKLB=59.18/64.22" >/dev/null && { echo "❌ pct(v3.7.0): 10-15 RKLB 7.9% 应拦(算出 -7.848%)"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/pct.py" check "Neutron首飞推迟至2027年，RKLB收跌7.8%" "RKLB=59.18/64.22" >/dev/null || { echo "❌ pct(v3.7.0): RKLB 7.8% 应放行"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/pct.py" check "巴克莱下调戴尔评级，DELL收涨11%" "DELL=507.93/572.47" >/dev/null && { echo "❌ pct(v3.7.0): 跌写成涨应拦"; fail=$((fail+1)); }
# ④ topic.py(假 console):建题用真实 id 落账+同轮上线行;涨跌幅不符不碰看板;写失败不落账;系统建 tradfi 窗口内改标题拦;撤题备注带撤时标题
_tp(){ CONSOLE_FAKE="$_V/c.json" ACTIONS="$_V/ta.tsv" SNAPSHOTS="$_V/ts.tsv" REJ="$_V/tr.tsv" REJ_OK="$_V/tok.tsv" UNLOGGED="$_V/tu.tsv" B0JSON="$_V/tb0.json" TOPIC_NO_DOWNSTREAM=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
echo '[]' > "$_V/tb0.json"
n=$((n+1)); [ "$(_tp create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.9%' --keywords 'RKLB,Rocket Lab' --rc 有诱因-多源 --note '回归:涨跌幅不符应拦' --pct 'RKLB=59.18/64.22')" != "0" ] && [ ! -s "$_V/ta.tsv" ] && [ ! -s "$_V/c.json" ] || { echo "❌ topic.py(v3.7.0): 涨跌幅不符应在写看板前拦下,台账与看板都不动"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tp create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.8%' --keywords 'RKLB,Rocket Lab' --rc 有诱因-多源 --note '回归:建题落真实id' --pct 'RKLB=59.18/64.22')" = "0" ] \
  && [ "$(awk -F'\t' '$2=="create"{print $3}' "$_V/ta.tsv")" = "10000090001" ] && grep -q '建后自推上线' "$_V/ta.tsv" && [ -z "$(awk -F'\t' '$2=="update" && $4=="状态修正"' "$_V/ta.tsv")" ] \
  || { echo "❌ topic.py(pubfold1105): 建题应落真实 id 10000090001、备注带自推上线标记、不另写状态修正行: $(cut -f2-5 "$_V/ta.tsv" | cut -c1-80 | tr '\n' ' ')"; fail=$((fail+1)); }
# pubfold1105:--no-publish 不带标记;上线调用抛异常→退出 5、create 行已落、unlogged 有行;单行 create 的送审清单计「同轮自推上线」
_n0=$(wc -l < "$_V/ta.tsv")
n=$((n+1)); [ "$(_tp create --domain tradfi --title '台积电10月营收创新高，TSM涨6.1%' --keywords 'TSM' --rc 有诱因-多源 --note '回归:不推上线' --pct 'TSM=106.1/100' --no-publish)" = "0" ] \
  && [ $(wc -l < "$_V/ta.tsv") -eq $((_n0+1)) ] && ! tail -1 "$_V/ta.tsv" | grep -q '建后自推上线' || { echo "❌ topic.py(pubfold1105): --no-publish 不应带自推标记"; fail=$((fail+1)); }
_n0=$(wc -l < "$_V/ta.tsv"); : > "$_V/tu.tsv"
n=$((n+1)); [ "$(CONSOLE_FAKE_RAISE=update _tp create --domain tradfi --title '英伟达财报超预期，NVDA涨6.2%' --keywords 'NVDA' --rc 有诱因-多源 --note '回归:上线抛异常' --pct 'NVDA=106.2/100')" = "5" ] \
  && [ $(wc -l < "$_V/ta.tsv") -eq $((_n0+1)) ] && grep -q '上线调用失败' "$_V/tu.tsv" || { echo "❌ topic.py(pubfold1105): 上线抛异常应退 5、create 行已落、unlogged 有行: $(cat "$_V/tu.tsv" | cut -c1-120)"; fail=$((fail+1)); }
: > "$_V/tu.tsv"
_n0=$(wc -l < "$_V/ta.tsv")
n=$((n+1)); [ "$(CONSOLE_FAKE_FAIL=create _tp create --domain crypto --title 'WAL 24小时涨48%，币安合约成交额7亿美元' --keywords 'WAL' --rc 纯行情-A定则 --note '回归:写失败不落账')" = "3" ] && [ "$(wc -l < "$_V/ta.tsv")" = "$_n0" ] || { echo "❌ topic.py(v3.7.0): 看板写失败应退出 3 且不落账"; fail=$((fail+1)); }
# retro1030:写看板后客户端抛异常(服务端已写)→退出 5、不落台账、actions-unlogged 有行(3377/3378 台账漏行且无回显)
_n0=$(wc -l < "$_V/ta.tsv")
n=$((n+1)); [ "$(CONSOLE_FAKE_RAISE=update _tp update --id 10000090001 --keywords 'RKLB,Rocket Lab' --rc tag修正 --note '回归:写后抛异常')" = "5" ] && [ "$(wc -l < "$_V/ta.tsv")" = "$_n0" ] && grep -q '写看板调用异常' "$_V/tu.tsv" 2>/dev/null || { echo "❌ topic.py(retro1030): 写看板调用抛异常应退出 5、记 actions-unlogged、不落台账"; fail=$((fail+1)); }
: > "$_V/tu.tsv"
# scope1031:建题 >8h 的题用承接更新改标题应拦(13691/13690),纠错-自纠放行
python3 - "$_V/c.json" <<'EOF2'
import json,sys,time
p=sys.argv[1]; st=json.load(open(p))
st['topics'].append({"id":13999001,"domain":"crypto","title":"FOO 24小时涨40%，币安合约成交2亿美元","keywords":"FOO","status":0,"created_at":time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()-20*3600)),"closed_ts":int(time.time()*1000)+4*3600000})
json.dump(st,open(p,'w'),ensure_ascii=False)
EOF2
n=$((n+1)); [ "$(_tp update --id 13999001 --rc 承接更新 --title 'FOO 24小时涨45%，币安合约成交2亿美元' --note '回归:射程外改写应拦')" != "0" ] && tail -1 "$_V/tr.tsv" | grep -q '已出 8h 射程' || { echo "❌ topic.py(scope1031): 建题20h的题用承接更新改标题应被射程闸拦"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tp update --id 13999001 --rc 纠错-自纠 --title 'FOO 24小时涨41%，币安合约成交2亿美元' --note '回归:纠错放行')" = "0" ] || { echo "❌ topic.py(scope1031): 纠错-自纠 不受射程闸限制,应放行"; fail=$((fail+1)); }
python3 - "$_V/c.json" <<'EOF'
import json,sys,time
p=sys.argv[1]; st=json.load(open(p))
st['topics'].append({"id":10000099999,"domain":"tradfi","title":"Samsung Electronics跌8.9%","keywords":"005930.KS","status":0,"created_at":time.strftime('%Y-%m-%d %H:%M:%S'),"closed_ts":int(time.time()*1000)+3600000})
json.dump(st,open(p,'w'),ensure_ascii=False)
EOF
n=$((n+1)); [ "$(_tp update --id 10000099999 --rc 改样式-命名 --title '三星电子跌8.9%' --note '回归:系统建窗口内改标题应拦')" != "0" ] || { echo "❌ topic.py(v3.7.0): 系统建 tradfi 窗口内改标题应拦(会被刷回)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tp cull --id 10000090001 --rc 反转错向 --note '回归:撤题备注带撤时标题')" = "0" ] && awk -F'\t' '$2=="cull"{print $5}' "$_V/ta.tsv" | grep -q '^『Neutron首飞推迟至2027年，RKLB收跌7.8%』' || { echo "❌ topic.py(v3.7.0): 撤题备注应以『撤时标题』开头"; fail=$((fail+1)); }
# ⑤ downstream:挂到本题之外的符号=错标(退出 2);同名代币化股票只记录
printf '%s' '[{"title":"Neutron delayed; RKLB closed down 7.8%.","asset_type":"tradfi","asset_types":["NTRN"],"content":"RKLB收跌7.8%"},{"title":"TSMC reports at 2 PM today; options price 4%.","asset_type":"tradfi","asset_types":["TSM"],"content":"TSM是Robinhood Chain上的台积电代币化股票,期权押注4%"}]' > "$_V/feed.json"
printf '%s' '[{"id":1,"domain":"tradfi","status":0,"title":"Neutron首飞推迟至2027年，RKLB收跌7.8%","title_en":"Neutron delayed; RKLB closed down 7.8%.","keywords":"RKLB,Rocket Lab,Neutron"},{"id":2,"domain":"tradfi","status":0,"title":"台积电今日14时发布三季报","title_en":"TSMC reports at 2 PM today; options price 4%.","keywords":"TSM,台积电"}]' > "$_V/tps.json"
_ds=$(DOWNSTREAM_FEED="$_V/feed.json" DOWNSTREAM_TOPICS="$_V/tps.json" DOWNSTREAM_LOG="$_V/ds.log" python3 "$D/downstream.py" --ids 1,2); _dsrc=$?
n=$((n+1)); [ "$_dsrc" = "2" ] && echo "$_ds" | grep -q '1 .*错标: 下游挂到 NTRN' && echo "$_ds" | grep -q '2 .*OK.*等效' && echo "$_ds" | grep -q '错标=1' || { echo "❌ downstream(v3.7.0): RKLB→NTRN 应判错标退出 2、TSM 同名代币化股票判等效(用户 10-15 定): $_ds"; fail=$((fail+1)); }
# ⑥ review-packet:计数从台账算;有撤题没给「留-撤对照」拒出
printf '%s\n' $'1795000000000\tcreate\t9101\t有诱因-多源\t回归:建\t-→甲' $'1795000000000\tupdate\t9101\t状态修正\t落此code因=建题后推status=0\t-' \
  $'1795000001000\tcull\t9102\t反转错向\t『乙』回归:撤\t' $'1795000002000\tupdate\t9103\t改数字-定稿\t回归:改\t丙1→丙2' $'1795000003000\tnote\t-\t留档\t回归:弃建\t' > "$_V/rp.tsv"
n=$((n+1)); ACTIONS="$_V/rp.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 && { echo "❌ review-packet(v3.7.0): 有撤题没给 --keep 应拒出"; fail=$((fail+1)); }
_rp=$(ACTIONS="$_V/rp.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 --keep '9104|丁|同型留')
n=$((n+1)); echo "$_rp" | grep -q '建 1(其中 1 条同轮自推上线)/ 撤 1 / 改 1 / note 1(共 5 行)' && echo "$_rp" | grep -q '9102「乙」' || { echo "❌ review-packet(v3.7.0): 计数/撤时标题不对: $(echo "$_rp" | sed -n 3p)"; fail=$((fail+1)); }
printf '%s\n' $'1795000000000\tcreate\t9105\t有诱因-多源\t回归:建｜建后自推上线(发布三问已核)\t-→戊' $'1795000001000\tnote\t-\t留档\t回归:弃建\t' > "$_V/rp2.tsv"
_rp2=$(ACTIONS="$_V/rp2.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000)
n=$((n+1)); echo "$_rp2" | grep -q '建 1(其中 1 条同轮自推上线)/ 撤 0 / 改 0 / note 1(共 2 行)' || { echo "❌ review-packet(pubfold1105): 单行 create 带标记应计同轮自推上线: $(echo "$_rp2" | sed -n 3p)"; fail=$((fail+1)); }
# retro1101b:送审前复读本轮币题标题,与币安现读差≥10pp 拒出(13763 ESPORTS 70%→59%)
printf '%s\n' $'1795000000000\tcreate\t9201\t纯行情-A定则\t回归:建\t-→ESPORTS 24小时涨70%，币安合约成交1.4亿美元' > "$_V/rpd.tsv"
printf '%s' '{"ESPORTS": 59.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpd.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 || { echo "❌ review-packet(1103hold): 纯行情币题70%对现读59%同向过线应放行(用户定不动)"; fail=$((fail+1)); }
printf '%s' '{"ESPORTS": 25.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpd.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 && { echo "❌ review-packet(1103hold): 纯行情币题现读25%跌破30%线应拒出"; fail=$((fail+1)); }
printf '%s' '{"ESPORTS": -40.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpd.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 && { echo "❌ review-packet(1103hold): 纯行情币题方向反转应拒出"; fail=$((fail+1)); }
printf '%s\n' $'1795000000000\tcreate\t9202\t有诱因-多源\t回归:建\t-→XPL闪崩致HLP金库亏损56万美元，24小时跌13%' > "$_V/rpx.tsv"
printf '%s' '{"XPL": -1.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpx.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 && { echo "❌ review-packet(1103hold): 有诱因币题差12pp仍应拒出"; fail=$((fail+1)); }
printf '%s' '{"ESPORTS": 59.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpd.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 --ack-drift '回归' >/dev/null 2>&1 || { echo "❌ review-packet(retro1101b): --ack-drift 应放行"; fail=$((fail+1)); }
printf '%s' '{"ESPORTS": 66.0}' > "$_V/bnf.json"
n=$((n+1)); PCT_BN_FAKE="$_V/bnf.json" ACTIONS="$_V/rpd.tsv" CHECKLOG=/dev/null B0JSON="$_V/tb0.json" python3 "$D/review-packet.py" 1795000000000 >/dev/null 2>&1 || { echo "❌ review-packet(retro1101b): 差4pp<10 不应拦"; fail=$((fail+1)); }
rm -rf "$_V"

# ── v3.7.1(10-15 用户定:资格线四条/漏建对账/盘中自动挂复查/规则查询计数)──────────────
_Q=$(mktemp -d)
_now=$(python3 -c 'import time;print(int(time.time()*1000))')
# ① 资格线:没盲审=✗;盲审 18/20 + 其余三条干净 = 本周 ✓
_qa(){ BLIND_AUDIT="$_Q/b.tsv" DOWNSTREAM_LOG="$_Q/d.tsv" UNLOGGED="$_Q/u.tsv" CHECKLOG="$_Q/c.tsv" CHECKLIST_CUR="$_Q/cur.tsv" LARK_LOG="$_Q/l.tsv" ACTIONS="$_Q/a.tsv" python3 -c "import sys;sys.path.insert(0,'$D');import qualify;r=qualify.check(int(sys.argv[1])-3600000,int(sys.argv[1])+1);print(' '.join(('1' if x[1] else '0') for x in r))" "$_now"; }
touch "$_Q/a.tsv"
n=$((n+1)); [ "$(_qa)" = "0 1 1 1" ] || { echo "❌ qualify(v3.7.1): 当周没盲审应判 ✗(没测≠达标),得 $(_qa)"; fail=$((fail+1)); }
for k in $(seq 1 20); do printf '%s\tw\t%s\t留\t留\t%s\n' "$_now" "$k" "$([ $k -le 18 ] && echo 1 || echo 0)" >> "$_Q/b.tsv"; done
n=$((n+1)); [ "$(_qa)" = "1 1 1 1" ] || { echo "❌ qualify(v3.7.1): 盲审 18/20=90% 且其余干净应四条全过,得 $(_qa)"; fail=$((fail+1)); }
printf '%s\t\t9001\t错标\tx\n' "$_now" > "$_Q/d.tsv"
printf '%s\tupdate\t9002\t纠错-自纠\t回归\tA→B\n' "$_now" >> "$_Q/a.tsv"
n=$((n+1)); [ "$(_qa)" = "1 0 0 1" ] || { echo "❌ qualify(v3.7.1): 下游错标/纠错-自纠 应各判 ✗,得 $(_qa)"; fail=$((fail+1)); }
# retro1114:推送 run_ts 比清单开跑早 13 秒仍算同轮已推送;10 分钟外无推送仍判 ✗
_qs=$((_now-7200000)); printf '# mode=刷新 ts=%s src=x\n' "$_qs" > "$_Q/c.tsv"; printf '%s\t%s\tround\t0\t0\toc\tom_x\tok\t-\n' "$_now" "$((_qs-13000))" > "$_Q/l.tsv"
_q4=$(BLIND_AUDIT="$_Q/b.tsv" DOWNSTREAM_LOG=/dev/null UNLOGGED=/dev/null CHECKLOG="$_Q/c.tsv" CHECKLIST_CUR=/dev/null LARK_LOG="$_Q/l.tsv" ACTIONS=/dev/null python3 -c "import sys;sys.path.insert(0,'$D');import qualify;r=qualify.check(int(sys.argv[1])-10800000,int(sys.argv[1])+1);print([('1' if x[1] else '0') for x in r if x[0]=='跑挂没消息'][0])" "$_now")
n=$((n+1)); [ "$_q4" = "1" ] || { echo "❌ qualify(retro1114): 推送 run_ts 早于开跑 13 秒应算已推送,得 $_q4"; fail=$((fail+1)); }
printf '%s\t%s\tround\t0\t0\toc\tom_x\tok\t-\n' "$_now" "$((_qs-1800000))" > "$_Q/l.tsv"
_q4=$(BLIND_AUDIT="$_Q/b.tsv" DOWNSTREAM_LOG=/dev/null UNLOGGED=/dev/null CHECKLOG="$_Q/c.tsv" CHECKLIST_CUR=/dev/null LARK_LOG="$_Q/l.tsv" ACTIONS=/dev/null python3 -c "import sys;sys.path.insert(0,'$D');import qualify;r=qualify.check(int(sys.argv[1])-10800000,int(sys.argv[1])+1);print([('1' if x[1] else '0') for x in r if x[0]=='跑挂没消息'][0])" "$_now")
n=$((n+1)); [ "$_q4" = "0" ] || { echo "❌ qualify(retro1114): 30 分钟外才有推送应判无推送,得 $_q4"; fail=$((fail+1)); }
: > "$_Q/c.tsv"; : > "$_Q/l.tsv"
# ② 漏建对账:过线且无题无弃建=漏;有题/弃建按名字或 ticker 对上
_ct=$(python3 -c 'import time;print(time.strftime("%Y-%m-%d %H:%M:%S"))')
printf '%s' "[{\"id\":1,\"domain\":\"tradfi\",\"status\":0,\"created_at\":\"$_ct\",\"title\":\"巴克莱下调戴尔评级，DELL收跌11%\",\"keywords\":\"DELL,戴尔\"},{\"id\":2,\"domain\":\"tradfi\",\"status\":3,\"created_at\":\"$_ct\",\"title\":\"遭遇诉讼，AST SpaceMobile Inc.跌10%\",\"keywords\":\"ASTS,AST SpaceMobile Inc.\"},{\"id\":3,\"domain\":\"tradfi\",\"status\":3,\"created_at\":\"$_ct\",\"title\":\"x\",\"keywords\":\"NBIS\"}]" > "$_Q/b0.json"
printf '%s' '{"DELL":[507.93,572.47,"EQUITY"],"ASTS":[42.14,47.065,"EQUITY"],"NBIS":[186.01,206.86,"EQUITY"],"NVDA":[221.3,228.52,"EQUITY"]}' > "$_Q/q.json"
printf '%s' '[{"symbol":"ZEREBROUSDT","priceChangePercent":"45","quoteVolume":"150000000"},{"symbol":"DUSTUSDT","priceChangePercent":"60","quoteVolume":"1000"}]' > "$_Q/bn.json"
printf '%s\tnote\t-\t留档\t弃建|NBIS|跟随CRWV同跌,并入CRWV题|2026-10-15\t\n' "$_now" > "$_Q/ca.tsv"
printf '{"channels":[{"key":"板块矩阵6批","call":"B1[NVDA]"}]}' > "$_Q/ch.json"
_cv=$(B0JSON="$_Q/b0.json" COVERAGE_QUOTES="$_Q/q.json" COVERAGE_BN="$_Q/bn.json" ACTIONS="$_Q/ca.tsv" CHANNELS="$_Q/ch.json" COVERAGE_LOG="$_Q/cv.log" python3 "$D/coverage.py"); _cvrc=$?
n=$((n+1)); [ "$_cvrc" = "2" ] && echo "$_cv" | grep -q 'COVERAGE: 过线=4 有题=1 弃建=1 漏=2' && echo "$_cv" | grep -q '🚨 股 ASTS' && echo "$_cv" | grep -q '🚨 币 ZEREBRO' || { echo "❌ coverage(v3.7.1): 应 过线4(DELL有题/NBIS弃建/ASTS漏/ZEREBRO漏,DUST成交额不足不算),得: $(echo "$_cv" | tail -1)"; fail=$((fail+1)); }
# ②n 突发对账(11-10 用户定):news-alert 强关联(linkage=3)入选事件要么有题、要么有弃建;宽标的(指数/大宗/利率/汇率/BTC/ETH)不认有题
n=$((n+1)); echo "$_cv" | grep -q '突发' && { echo "❌ coverage-news(11-10): 没注入 NEWS_ALERT_DB 不得读生产突发库"; fail=$((fail+1)); }
python3 - "$_Q" <<'EOF2'
import sqlite3, sys, json, time, datetime as dt
q = sys.argv[1]; now = time.time()
iso = lambda h: dt.datetime.fromtimestamp(now - h * 3600, dt.timezone.utc).isoformat()
loc = lambda h: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now - h * 3600))
c = sqlite3.connect(f'{q}/news.db')
c.execute("CREATE TABLE items(uid TEXT, src TEXT, ts TEXT, text TEXT, keep INT, keep_ops INT, linkage INT, assets TEXT, event_key TEXT)")
c.execute("CREATE TABLE events(event_key TEXT, headline TEXT)"); c.execute("CREATE TABLE state(k TEXT, v TEXT)")
A = lambda *xs: json.dumps([{"symbol": s, "market": m, "mainstream": True} for s, m in xs])
for uid, h, k, ko, lk, a, ek in [('1', 1, 1, 0, 3, A(('NVDA', 'us_equity')), 'nvda-probe'), ('2', 1, 0, 1, 3, A(('SPX', 'index')), 'tariff-x'),
        ('3', 1, 1, 1, 3, A(('WTI', 'commodity')), 'oil-y'), ('4', 1, 1, 0, 3, A(('KKR', 'us_equity')), 'kkr-z'),
        ('5', 1, 1, 1, 2, A(('TSLA', 'us_equity')), 'low-l2'), ('6', 40, 1, 1, 3, A(('META', 'us_equity')), 'old-e'),
        ('7', 1, 1, 0, 3, A(('AMD', 'us_equity')), 'amd-ev')]:
    c.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?)", (uid, 'jin10', iso(h), f'正文{uid}', k, ko, lk, a, ek))
c.execute("INSERT INTO events VALUES('kkr-z','KKR三季度EPS超预期')"); c.execute("INSERT INTO state VALUES('jin10_last_ts',?)", (iso(2),)); c.commit()
json.dump([{"id": 11, "domain": "tradfi", "status": 0, "created_at": loc(0), "title": "黄仁勋承认婚外情，NVDA跌4%", "keywords": "NVDA,英伟达"},
           {"id": 12, "domain": "tradfi", "status": 0, "created_at": loc(0), "title": "美股三大指数大涨，标普涨2%", "keywords": "SPX,标普"},
           {"id": 13, "domain": "tradfi", "status": 0, "created_at": loc(10), "title": "x", "keywords": "AMD"}], open(f'{q}/b0n.json', 'w'), ensure_ascii=False)
open(f'{q}/can.tsv', 'w').write(f"{int(now * 1000)}\tnote\t-\t留档\t弃建|CL=F|美油跌3.9%未过5%线|2026-11-10\t\n")
open(f'{q}/qn.json', 'w').write('{}'); open(f'{q}/bnn.json', 'w').write('[]')
EOF2
_cvn=$(B0JSON="$_Q/b0n.json" COVERAGE_QUOTES="$_Q/qn.json" COVERAGE_BN="$_Q/bnn.json" ACTIONS="$_Q/can.tsv" CHANNELS="$_Q/ch.json" COVERAGE_LOG="$_Q/cvn.log" NEWS_ALERT_DB="$_Q/news.db" python3 "$D/coverage.py" 2>&1); _cvnrc=$?
n=$((n+1)); [ "$_cvnrc" = "2" ] && echo "$_cvn" | grep -q 'COVERAGE: 过线=5 有题=1 弃建=1 漏=3' && echo "$_cvn" | grep -q '✔ 突发 nvda-probe → 有题 11' \
  && echo "$_cvn" | grep -q '🚨 突发 tariff-x → 漏' && echo "$_cvn" | grep -q '✔ 突发 oil-y → 弃建' && echo "$_cvn" | grep -q '🚨 突发 kkr-z → 漏 「KKR三季度EPS超预期」' \
  && echo "$_cvn" | grep -q '🚨 突发 amd-ev → 漏' && ! echo "$_cvn" | grep -qE 'low-l2|old-e' && echo "$_cvn" | grep -q '突发库已 1[12][0-9] 分钟没更新' \
  || { echo "❌ coverage-news(11-10): 应 nvda有题/指数宽匹配不算(tariff漏)/油认CL=F弃建/KKR漏/3h前旧题不算(amd漏)/L2与出窗不列/库停更提示,得: $(echo "$_cvn" | grep -E '突发|COVERAGE|Traceback')"; fail=$((fail+1)); }
# ②a retro1030:指数/板块 ETF 按各自的线对账(SOXX-7.4% 有「费半」题=有题,QQQ-3% 无题=漏,SPY-1.4% 未过 2% 线不列)
printf '%s' "[{\"id\":7,\"domain\":\"tradfi\",\"status\":0,\"created_at\":\"$_ct\",\"title\":\"英特尔亚马逊财报引发AI担忧，费半ETF盘中跌7.4%\",\"keywords\":\"费城半导体,半导体\"}]" > "$_Q/b0i.json"
printf '%s' '{"SOXX":[475.92,513.86,"ETF"],"QQQ":[694.25,715.34,"ETF"],"SPY":[758.34,769.36,"ETF"]}' > "$_Q/qi.json"
_cvi=$(B0JSON="$_Q/b0i.json" COVERAGE_QUOTES="$_Q/qi.json" COVERAGE_BN="$_Q/bn.json" ACTIONS="$_Q/ca.tsv" CHANNELS="$_Q/ch.json" COVERAGE_LOG="$_Q/cvi.log" python3 "$D/coverage.py")
n=$((n+1)); echo "$_cvi" | grep -q '✔ 指数 SOXX -7.4% → 有题 7' && echo "$_cvi" | grep -q '🚨 指数 QQQ' && ! echo "$_cvi" | grep -q '指数 SPY' || { echo "❌ coverage(retro1030): 指数层应 SOXX有题(费半)/QQQ漏/SPY不过线,得: $(echo "$_cvi" | grep -E '指数|COVERAGE')"; fail=$((fail+1)); }
# ②c scope1031:旧弃建按当时幅度写,幅度又扩大≥3pp不再算已处置(SNDK 盘后-8.9%弃建盖住收盘-13.5%);QCOM 进对账池
printf '%s' '{"SNDK":[1150.89,1330.05,"EQUITY"],"QCOM":[164.79,185.41,"EQUITY"]}' > "$_Q/qs.json"
printf '%s\tnote\t-\t留档\t弃建|SNDK|盘后跌8.9%%,毛利率不及预期,<10%%|2026-10-30\t\n' "$_now" > "$_Q/cs.tsv"
_cvs=$(B0JSON="$_Q/b0i.json" COVERAGE_QUOTES="$_Q/qs.json" COVERAGE_BN="$_Q/bn.json" ACTIONS="$_Q/cs.tsv" CHANNELS="$_Q/ch.json" COVERAGE_LOG="$_Q/cvs.log" python3 "$D/coverage.py")
n=$((n+1)); echo "$_cvs" | grep -q '🚨 股 SNDK' && echo "$_cvs" | grep -q '🚨 股 QCOM' || { echo "❌ coverage(scope1031): 旧弃建幅度差≥3pp应重报漏、QCOM应进池,得: $(echo "$_cvs" | grep -E 'SNDK|QCOM|COVERAGE')"; fail=$((fail+1)); }
# ②d retro1101:周末对账股票窗口延到最近一次美股收盘前 26h(周日 12:00 SGT 看周五收盘题不报漏)
n=$((n+1)); python3 - <<'EOF' || { echo "❌ coverage.stock_hours(retro1101): 周日应放宽到覆盖周五盘前/收盘题,工作日盘中不短于36h"; fail=$((fail+1)); }
import os,sys,importlib.util,datetime; sys.stdout=open(os.devnull,'w')
s=importlib.util.spec_from_file_location('cv',os.path.expanduser('~/.trend-scout/coverage.py')); C=importlib.util.module_from_spec(s); s.loader.exec_module(C)
ts=lambda y,mo,d,h: datetime.datetime(y,mo,d,h,tzinfo=datetime.timezone.utc).timestamp()
h=C.stock_hours(36, ts(2026,11,1,4))          # 周日 12:00 SGT
assert 55 <= h <= 60, h                        # 周五 20:00 UTC 收盘前 26h = 周四 18:00 UTC,距今 58h
assert C.stock_hours(36, ts(2026,10,29,4)) == 36   # 周四 12:00 SGT:前一收盘周三 20:00 UTC 前26h=34h<36 → 36
EOF
# ②b 10-21:下架结算的永续行情冻结(EPICUSDT SETTLING,closeTime 停在 10-20 17:11)不算过线;新鲜的照算
printf '%s' '[{"symbol":"ZEREBROUSDT","priceChangePercent":"45","quoteVolume":"150000000","closeTime":1792500000000},{"symbol":"EPICUSDT","priceChangePercent":"-33.7","quoteVolume":"35000000","closeTime":1792491060000}]' > "$_Q/bn2.json"
_cv2=$(COVERAGE_NOW_MS=1792500600000 B0JSON="$_Q/b0.json" COVERAGE_QUOTES="$_Q/q.json" COVERAGE_BN="$_Q/bn2.json" ACTIONS="$_Q/ca.tsv" CHANNELS="$_Q/ch.json" COVERAGE_LOG="$_Q/cv2.log" python3 "$D/coverage.py")
n=$((n+1)); echo "$_cv2" | grep -q '🚨 币 ZEREBRO' && ! echo "$_cv2" | grep -q '币 EPIC' && echo "$_cv2" | grep -q '⏸ 冻结合约不算过线.*EPIC(-33.7% 已 159 分钟没更新)' || { echo "❌ coverage(10-21): 冻结合约 EPIC 不该算过线、应单列 ⏸,新鲜的 ZEREBRO 照算: $(echo "$_cv2" | grep -E 'EPIC|ZEREBRO|COVERAGE')"; fail=$((fail+1)); }
n=$((n+1)); [ "$(cd "$D" && python3 -c 'import pct;print(pct.stale_min({"closeTime":1792491060000},1792500600000), pct.stale_min({"closeTime":1792500000000},1792500600000), pct.stale_min({},1792500600000))')" = "159 None None" ] || { echo "❌ pct.stale_min(10-21): 应 159 / None(10 分钟内新鲜) / None(没有 closeTime)"; fail=$((fail+1)); }
# ③ 盘中题自动挂复查时点:韩股当日 14:40;美股晚间→次日 09:40;美股凌晨(未收盘)→当日 09:40;欧股→次日 09:40
_rv=$(cd "$D" && python3 -c 'import datetime as d,topic
for t,k,n in [("KOSPI盘中跌7.8%","KOSPI",d.datetime(2026,10,15,9,45)),("BAC盘中跌8.1%","BAC",d.datetime(2026,10,14,22,16)),("X盘中涨5%","X",d.datetime(2026,10,15,1,30)),("ASML盘中涨2.8%","ASML,阿斯麦",d.datetime(2026,10,14,16,10))]: print(topic.review_slot(t,k,n).strftime("%d-%H:%M"))')
n=$((n+1)); [ "$(echo $_rv)" = "15-14:40 15-09:40 15-09:40 15-09:40" ] || { echo "❌ topic.review_slot(v3.7.1): 得 $(echo $_rv)"; fail=$((fail+1)); }
# ④ gate.sh 查询计数落盘
GATE_USAGE="$_Q/gu.tsv" "$D/gate.sh" 时段 >/dev/null 2>&1
n=$((n+1)); grep -q $'\tgate\t时段$' "$_Q/gu.tsv" 2>/dev/null || { echo "❌ gate.sh(v3.7.1): 查闸应记一行 gate-usage"; fail=$((fail+1)); }
rm -rf "$_Q"

# ── v3.7.1 要你定异步化 / 每周盲审 ───────────────────────────────────────
_K=$(mktemp -d)
_ak(){ ASKS="$_K/a.tsv" ASK_NO_SEND=1 ASK_FAKE_MSGS="$_K/m.json" python3 "$D/ask.py" "$@" 2>&1; }
_ak open --q "回归问题一" --default "不做" --deadline "2099-01-01 09:40" >/dev/null
_ak open --q "回归问题二" --default "按默认撤" --deadline "2099-01-01 10:00" >/dev/null
sed -i.bak $'s/\tQ2\topen\t回归问题二\t按默认撤\t[0-9]*/\tQ2\topen\t回归问题二\t按默认撤\t1000/' "$_K/a.tsv"
echo '[["10-15 13:00","群主","Q1 做"],["10-15 13:01","张三","Q2 不同意"]]' > "$_K/m.json"
_as=$(_ak sync)
n=$((n+1)); echo "$_as" | grep -q 'Q1 .*按你的回复「做」' && echo "$_as" | grep -q 'Q2 .*到期没回,按默认「按默认撤」' && echo "$_as" | grep -q '张三.*非群主' \
  || { echo "❌ ask.py(v3.7.1): 群主回复算答复、到期按默认、非群主只作参考: $_as"; fail=$((fail+1)); }
printf '%s' "[{\"id\":1,\"domain\":\"crypto\",\"status\":0,\"title\":\"甲\"},{\"id\":2,\"domain\":\"crypto\",\"status\":3,\"title\":\"乙\"},{\"id\":3,\"domain\":\"crypto\",\"status\":3,\"title\":\"丙(后台隐藏)\"}]" > "$_K/pool.json"
printf '1\tcull\t2\t重复-同标的\tx\t-\n' > "$_K/bact.tsv"
_bl(){ BLIND_ACTIONS="$_K/bact.tsv" BLIND_DIR="$_K/b" BLIND_AUDIT="$_K/ba.tsv" BLIND_DISAGREE="$_K/bd.tsv" BLIND_B0="$_K/pool.json" ASK_NO_SEND=1 ASK_FAKE_MSGS="$_K/bm.json" python3 "$D/blind-audit.py" "$@" 2>&1; }
_bl sample --week 2099-W01 >/dev/null
# v3.7.18:后台隐藏的 3 不进样本;我撤的 2 带「重复」背景
n=$((n+1)); python3 -c "import json;d=json.load(open('$_K/b/2099-W01.json'));ids=[x['id'] for x in d['items']];c=[x['context'] for x in d['items'] if x['id']=='2'];assert '3' not in ids and c and '重复' in c[0]" || { echo "❌ blind-audit(v3.7.18): 后台隐藏题不应入样,重复撤题应附背景"; fail=$((fail+1)); }
_w=$(python3 -c "import json;d=json.load(open('$_K/b/2099-W01.json'));print([x['n'] for x in d['items'] if x['prod']=='留'][0])")
echo "[[\"10-15 13:00\",\"群主\",\"盲审 2099-W01 撤 $_w\"]]" > "$_K/bm.json"
_bs=$(_bl sync)
n=$((n+1)); echo "$_bs" | grep -q '一致 0/2' && [ "$(wc -l < "$_K/bd.tsv" | tr -d ' ')" = "2" ] || { echo "❌ blind-audit(v3.7.1): 把留判撤、撤没列(=留)应 0/2 且写 2 条不一致: $_bs"; fail=$((fail+1)); }
n=$((n+1)); echo "$(_bl sync)" | grep -q '已录过' || { echo "❌ blind-audit(v3.7.1): 同一周重复回复应忽略"; fail=$((fail+1)); }
rm -rf "$_K"

# ── v3.7.2 学习闭环 retro.py:收错 → 分类 → 重犯/已修/修后又犯 → 次日 brief ──────────────
_R=$(mktemp -d)
_rt(){ ACTIONS="$_R/a.tsv" REJ="$_R/r.tsv" UNLOGGED="$_R/u.tsv" DOWNSTREAM_LOG="$_R/d.tsv" COVERAGE_LOG="$_R/c.tsv" ERRORS="$_R/e.tsv" FIXES="$_R/f.tsv" RETRO_DIR="$_R/rd" python3 "$D/retro.py" "$@" 2>&1; }
_d1=$(python3 -c 'import time;print(int((time.time()-3*86400)*1000))'); _d2=$(python3 -c 'import time;print(int(time.time()*1000)-60000)')
_today=$(date '+%Y-%m-%d')
printf '%s\tnote\t9001\t复审员挑战\t复审员挑战成立(仅rc):撤因码不贴,应记 缺诱因-未达线\t\n' "$_d1" > "$_R/a.tsv"
printf '%s\tnote\t9002\t复审员挑战\t复审员挑战成立:撤因码贴错,应记 归因-借源造因\t\n' "$_d2" >> "$_R/a.tsv"
printf '%s\tnote\t9003\t复审员挑战\t复审员挑战不成立(维持):理由「已核实数字为7.8」\t\n' "$_d2" >> "$_R/a.tsv"
printf '%s\t涨跌幅不符:「RKLB」标题写 7.9%%\tcreate\t-\t有诱因-多源\n' "$_d2" > "$_R/r.tsv"
printf '%s\t股\tASTS\t-10.5\t漏\t\n' "$_d2" > "$_R/c.tsv"
_rd=$(_rt day "$_today")
n=$((n+1)); echo "$_rd" | grep -q '复审挑战·撤因码 ×1  🟠 重犯(此前 1 次' && echo "$_rd" | grep -q '工具拦截·涨跌幅不符 ×1  🟡 首次出现' && echo "$_rd" | grep -q '漏建 ×1' && ! echo "$_rd" | grep -q '9003' \
  || { echo "❌ retro(v3.7.2): 应识别撤因码重犯、工具拦截首次、漏建,且「不成立」不算错: $(echo "$_rd" | grep '^## ' | tr '\n' ' ')"; fail=$((fail+1)); }
_rt fix "漏建" 脚本 "回归:coverage.py" >/dev/null
n=$((n+1)); _rt day "$_today" | grep -q '漏建 ×1  🟢 当天已修' || { echo "❌ retro(v3.7.2): 登记修复后应显示当天已修"; fail=$((fail+1)); }
printf '%s\t股\tNBIS\t-10.1\t漏\t\n' "$(python3 -c 'import time;print(int(time.time()*1000)+1000)')" >> "$_R/c.tsv"
sleep 1
n=$((n+1)); _rt day "$_today" | grep -q '漏建 ×2  🔴 修过' || { echo "❌ retro(v3.7.2): 修复之后又出现同类错应标 🔴 修过仍重犯"; fail=$((fail+1)); }
n=$((n+1)); _rt brief | grep -q '复审挑战·撤因码' || { echo "❌ retro(v3.7.2): brief 应读出未修错类"; fail=$((fail+1)); }
rm -rf "$_R"

# ── v3.7.3 每晚复盘 10-15 首次实跑:脚本层五处修复,各配一条拦同类错的用例 ──────────────
_W=$(mktemp -d)
# ① 承接更新的新标题没价格腿 → 拦;备注写「豁免价格腿:」放行(复审挑战·价格腿 重犯 5 次,病例 3138)
python3 - "$_W" <<'EOF'
import json,sys,time
d=sys.argv[1]; now=int(time.time()*1000)
json.dump({"topics":[{"id":10000088888,"domain":"tradfi","title":"台积电今日14时发布三季报","keywords":"TSM","status":0,"created_at":time.strftime('%Y-%m-%d %H:%M:%S'),"closed_ts":now+3600000}]},open(d+'/c.json','w'),ensure_ascii=False)
open(d+'/ta.tsv','w').write(f"{now-60000}\tcreate\t10000088888\t预告题\t回归\t-→台积电今日14时发布三季报\n")
EOF
echo '[]' > "$_W/tb0.json"
_tw(){ CONSOLE_FAKE="$_W/c.json" ACTIONS="$_W/ta.tsv" SNAPSHOTS="$_W/ts.tsv" REJ="$_W/tr.tsv" REJ_OK="$_W/tok.tsv" UNLOGGED="$_W/tu.tsv" B0JSON="$_W/tb0.json" TOPIC_NO_DOWNSTREAM=1 TOPIC_NO_REVIEW=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
n=$((n+1)); [ "$(_tw update --id 10000088888 --rc 承接更新 --title '台积电三季营收与四季度指引均超预期' --note '回归:承接缺价格腿应拦')" != "0" ] || { echo "❌ topic.py(v3.7.3): 承接更新的新标题没有价格腿应拦(3138 型)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tw update --id 10000088888 --rc 承接更新 --title '台积电三季营收与四季度指引均超预期' --note '豁免价格腿:回归放行')" = "0" ] || { echo "❌ topic.py(v3.7.3): 备注写「豁免价格腿:」应放行"; fail=$((fail+1)); }
# ② 盘中题自动挂收盘复查:时点已过的待关事件不算「已有复查」;未来的才算
n=$((n+1)); python3 - "$_W" <<'EOF' || { echo "❌ topic.py(v3.7.3): 盘中题挂收盘复查——时点已过的同题待关事件不应挡住,未来的应挡"; fail=$((fail+1)); }
import os,sys,datetime as dt
d=sys.argv[1]; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); os.environ['EVENT_WATCH']=d+'/ev.tsv'
import topic
sys.stdout=open(os.devnull,'w')   # 10-16 retro:测试输出别混进收尾日志
calls=[]; topic.subprocess.run=lambda *a,**k: (calls.append(a), type('R',(),{'stdout':'ok','stderr':''})())[1]
past=dt.datetime.now()-dt.timedelta(minutes=5); fut=dt.datetime.now()+dt.timedelta(hours=3)
def ev(t): open(d+'/ev.tsv','w').write(f"{t:%Y-%m-%d}\treview\t补价格腿\t{t:%H:%M}\t—\t777\tpending\tx\n")
ev(past); topic.auto_review(777,'台积电财报及指引超预期，TSM盘中仍跌4.3%','TSM','tradfi'); assert len(calls)==1, calls
ev(fut);  topic.auto_review(777,'台积电财报及指引超预期，TSM盘中仍跌4.3%','TSM','tradfi'); assert len(calls)==1, calls
EOF
# ③ coverage:对账池含矿企/算力托管;港股代码补零与否都认弃建
n=$((n+1)); (cd "$D" && python3 -c '
import coverage as c
u=c.universe([],36); assert {"IREN","CIFR","WULF","NBIS"}<=set(u), sorted(u)[:5]
assert c.covered("0992.HK",set(),[],["弃建|992.HK|港股AI同口径|2026-10-15"])[0]=="弃建"
assert c.covered("0992.HK",set(),[],["弃建|0992.HK|x|2026-10-15"])[0]=="弃建"
assert c.covered("AAPL",set(),[],["弃建|992.HK|x"])[0] is None') >/dev/null 2>&1 || { echo "❌ coverage(v3.7.3): 对账池应含 IREN/CIFR/WULF/NBIS,0992.HK 应认 992.HK 的弃建"; fail=$((fail+1)); }
# ④ lark-push send 前现拉看板:待审>0 拒推(16:30 13258、22:00 13269)
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lark-push(v3.7.3): 推送前待审计数解析不对"; fail=$((fail+1)); }
import importlib.util,os
D=os.path.expanduser('~/.trend-scout')
sp=importlib.util.spec_from_file_location('lp',os.path.join(D,'lark-push.py')); lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
os.environ['B0_AUDIT_CMD']="echo 'AUDIT: 在线=36 ≤8h=11 待审=1(s2=1,s1=0) 窗口题=0'"; assert lp._pending_b0()==1
os.environ['B0_AUDIT_CMD']="echo 'AUDIT: 在线=36 待审=0(s2=0,s1=0)'"; assert lp._pending_b0()==0
os.environ['B0_AUDIT_CMD']="false"; assert lp._pending_b0() is None
EOF
# ⑤ 大公司/机构合作=硬事件,机审⑥不给机械撤命令(13265 Stripe×Plasma);无名合作仍算灌水
_he=$(cd "$D" && python3 -c 'import lint
for t in ["PLASMA联手Stripe推出多币种加密卡","某项目宣布与某链达成合作"]: print(lint.hard_event(t) or "-")')
n=$((n+1)); [ "$(echo $_he)" = "Stripe·联手 -" ] || { echo "❌ lint(v3.7.3): 大公司合作应判硬事件、无名合作不判,得到 $(echo $_he)"; fail=$((fail+1)); }
# ⑥ retro:例行「自审七查」留痕不算错误
printf '%s\n' $'1795000000000\tnote\t-\t自审发现\t自审七查(22:00):①横向矛盾0 ④价格腿:无新建\t' $'1795000001000\tnote\t-\t自审发现\t漏建(首扫):矿企板块\t' > "$_W/ra.tsv"
_rg=$(cd "$D" && ACTIONS="$_W/ra.tsv" REJ=/dev/null UNLOGGED=/dev/null DOWNSTREAM_LOG=/dev/null COVERAGE_LOG=/dev/null python3 -c 'import retro; print(len(retro.gather()))' 2>/dev/null)
n=$((n+1)); [ "$_rg" = "1" ] || { echo "❌ retro(v3.7.3): 「自审七查」例行留痕不应计入错误,应只剩 1 条,得到 $_rg"; fail=$((fail+1)); }
rm -rf "$_W"

# ── v3.7.4 每晚复盘 10-16:推送门槛/限流重试/问号标题/收盘复查截止,各配一条用例 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lark-push(v3.7.4): 清单终验门槛或限流重试行为不符"; fail=$((fail+1)); }
import importlib.util,os,tempfile
D=os.path.expanduser('~/.trend-scout')
sp=importlib.util.spec_from_file_location('lp',os.path.join(D,'lark-push.py')); lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
T=tempfile.mkdtemp(); lp.REAL=T
assert lp._ck_passed(123)==False
open(os.path.join(T,'checklists.log.tsv'),'w').write("# mode=刷新 ts=123 src=channels.json\nB0\t✅(1)\n")
assert lp._ck_passed(123)==True and lp._ck_passed(123+16000)==True and lp._ck_passed(123+601000)==False   # 10-19:±10分钟容差
seq=[(1,{},'"type": "rate_limit", "code": 429'),(0,{'ok':1},'')]; calls=[]
lp._cli=lambda a,**k:(calls.append(a),seq[len(calls)-1])[1]
os.environ['LARK_RETRY_SCALE']='0'
rc,d,e=lp._cli_retry(['x']); assert rc==0 and len(calls)==2, (rc,len(calls))
EOF
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.4): 盘中题收盘复查事件应写明有效期截止"; fail=$((fail+1)); }
import os,sys,tempfile
sys.path.insert(0,os.path.expanduser('~/.trend-scout')); os.environ['EVENT_WATCH']=tempfile.mktemp()
import topic
sys.stdout=open(os.devnull,'w')
got=[]; topic.subprocess.run=lambda a,**k:(got.append(a),type('R',(),{'stdout':'ok','stderr':''})())[1]
topic.auto_review(888,'X盘中涨5%','X','tradfi',closed_ms=1792115143000)
assert got and '有效期截止' in got[0][-1], got
EOF

# ── v3.7.6 周度规则通读 10-17(用户批 1→5):过期题闸合并 / 撤因码补废 ──────────────
n=$((n+1)); GG="$HOME/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic/references/gates.md"
{ grep -q '^## 闸:过期题' "$GG" && ! grep -q '^## 闸:窗口题' "$GG" && ! grep -q '改成当下事实或撤' "$GG" && "$D/gate.sh" 过期题 | grep -q '过期题处置表'; } \
  || { echo "❌ v3.7.6 闸:过期题: 应有处置表且窗口题「改成当下事实」死分支已删"; fail=$((fail+1)); }
n=$((n+1)); LT="/tmp/la376.$$"; mkdir -p "$LT"
printf '[{"id":99990106,"domain":"crypto","title":"X 本周将发布Y","keywords":"X","status":0}]' > "$LT/b0.json"
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990106 预告题-准入不过 '预告题准入③影响面不足' >/dev/null 2>&1
[ "$?" = "0" ] || { echo "❌ v3.7.6 撤因码: 预告题-准入不过 应可落账"; fail=$((fail+1)); }
ACTIONS="$LT/a.tsv" SNAPSHOTS="$LT/s.tsv" REJ="$LT/rej.tsv" B0JSON="$LT/b0.json" "$D/log-action.sh" cull 99990106 灌水-悬念疑问 'x' >/dev/null 2>&1
[ "$?" = "1" ] || { echo "❌ v3.7.6 撤因码: 灌水-悬念疑问 已废,应拒写(问号题统一记 疑问句-悬念)"; fail=$((fail+1)); }
B0JSON="$LT/b0.json" "$D/b0-cull.py" --rc 灌水-悬念疑问 --note x --dry 99990106 >/dev/null 2>&1 \
  && { echo "❌ v3.7.6 撤因码: b0-cull 不应再接受 灌水-悬念疑问"; fail=$((fail+1)); }
rm -rf "$LT"
n=$((n+1)); { grep -q '定稿死线＝该题 `closed_ts`' "$GG" && grep -q '`overnight` 块＝\*\*正股夜盘价' "$GG"; } \
  || { echo "❌ v3.7.6 闸:时段/排班: 盘中题定稿死线按 closed_ts、长桥 overnight 为夜盘主通道 两句缺失"; fail=$((fail+1)); }


# ── v3.7.7 每晚复盘 10-17:撤前复测 / 漏建回落粘滞 / 当轮拦下分类 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.7): 读数在准入线±3pp内未写复测应拦,写了复测或离线远应放行"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
assert topic.near_line('缺诱因-未达线','crypto','四查:幅度✗ 24h +28.6% 成交额✗')
assert not topic.near_line('缺诱因-未达线','crypto','四查:幅度✗ 复测:+28.6%/+28.1% 成交额✗')
assert not topic.near_line('缺诱因-未达线','crypto','四查:幅度✗ 24h +12% 成交额✗')
assert topic.near_line('已证伪','tradfi','收跌9.1%')
assert not topic.near_line('灌水-KOL观点','crypto','24h +29%')
assert not topic.near_line('缺诱因-未达线','tradfi','SNDK +5.8%,未过tradfi±10%')   # 10-19 误拦:阈值写法不是读数
assert not topic.near_line('缺诱因-未达线','tradfi','MU 盘中+1.06%,远低于 tradfi 10%,标题3.3%偏差')   # 10-26 影子跑 3270:门槛写法不是读数
assert topic.near_line('缺诱因-未达线','tradfi','盘中 -9.2% 低于 tradfi 10%')   # 读数照拦
EOF
n=$((n+1)); python3 - <<'EOF' || { echo "❌ coverage.py(v3.7.7): 今日早前报漏、现回落线内未处置的标的应继续算漏"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout'))
import importlib.util; s=importlib.util.spec_from_file_location('cov',os.path.expanduser('~/.trend-scout/coverage.py')); c=importlib.util.module_from_spec(s); s.loader.exec_module(c)
rows=[['1000','币','ZEREBRO','-30.0','漏',''],['1001','币','Q','+42','漏',''],['1002','币','Q','+42','有题','13325'],['500','币','OLD','-40','漏','']]
got=c.sticky_misses(rows,900,{('币','BTW')})
assert [g[1] for g in got]==['ZEREBRO'], got
assert c.sticky_misses(rows,900,{('币','ZEREBRO')})==[]
EOF
n=$((n+1)); python3 - <<'EOF' || { echo "❌ retro.py(v3.7.7): 对账报漏后同日补建/弃建应归「漏建·当轮拦下」"; fail=$((fail+1)); }
import os,sys,tempfile; d=tempfile.mkdtemp()
open(d+'/cov.tsv','w').write('1792240618898\t币\tEPIC\t+32.4\t漏\t\n1792240671282\t币\tEPIC\t+33.8\t有题\t13320\n1792240531000\t币\tZERO\t-30.0\t漏\t\n')
open(d+'/err.tsv','w').write('1792240618898\tx1\t漏建\tEPIC\tt\t漏建对账\t2026-10-17\n1792240531000\tx2\t漏建\tZERO\tt\t漏建对账\t2026-10-17\n')
os.environ['COVERAGE_LOG']=d+'/cov.tsv'; os.environ['ERRORS']=d+'/err.tsv'
sys.path.insert(0,os.path.expanduser('~/.trend-scout'))
import importlib.util; s=importlib.util.spec_from_file_location('retro',os.path.expanduser('~/.trend-scout/retro.py')); r=importlib.util.module_from_spec(s); s.loader.exec_module(r)
e=r.load_errors(); assert e['x1']['cls']=='漏建·当轮拦下' and e['x2']['cls']=='漏建', e
EOF


# ── v3.7.8 每晚复盘 10-19:被拦后的 publish / 线程回复限流重试 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.8): 同题10分钟内被拦应挡 publish,超窗或别的题不挡"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
rows=[['1000000','标题闸FAIL(标题长度)','update','13349','改口径-时段']]
assert topic.recent_block(13349,rows,1000000+60000)
assert not topic.recent_block(13349,rows,1000000+700000)
assert not topic.recent_block(13350,rows,1000000+60000)
assert topic.meme_rc('缺价格腿','四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ ——x') and not topic.meme_rc('缺诱因-未达线','四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗') and not topic.meme_rc('缺价格腿','无价格反应')   # 10-19 TRUMP 撤因码
assert topic.meme_rc_fix('缺价格腿','四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ ——x')[0]=='缺诱因-未达线' and topic.meme_rc_fix('缺价格腿','无价格反应')==('缺价格腿',None) and topic.meme_rc_fix('缺诱因-未达线','四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗')==('缺诱因-未达线',None)   # 11-04 复盘 13833 LIT:四查全空自动改码
EOF
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lark-push(v3.7.8): 线程回复遇429应重试"; fail=$((fail+1)); }
import importlib.util,os
D=os.path.expanduser('~/.trend-scout')
sp=importlib.util.spec_from_file_location('lp',os.path.join(D,'lark-push.py')); lp=importlib.util.module_from_spec(sp); sp.loader.exec_module(lp)
os.environ['LARK_RETRY_SCALE']='0'; calls=[]
def fake(a,**k):
    calls.append(a)
    if '+messages-send' in a: return 0,{'data':{'message_id':'om_x'}},''
    return (1,{},'"code": 429 rate_limit') if len([c for c in calls if '+messages-reply' in c])==1 else (0,{},'')
lp._cli=fake; lp._msg_id=lambda d:'om_x'
ok,mid,partial=lp.send_payload({'main':'m','threads':['r1'],'attach':[],'run_ts':1,'kind':'test','force':True},{'chat_id':'c'})
assert ok and partial=='', (ok,partial,len(calls))
EOF

# ── v3.7.9 每晚复盘 10-20:改样式-命名误用 / --pct 标签自带百分数 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.9): 改样式-命名新增数字/价格腿应拦,纯措辞与「仅措辞」放行"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
R='改样式-命名'
assert topic.style_rc(R,'AXISROBOTICS入选路线图，Alpha空投将至','AXIS将于10月21日登陆币安Alpha与OKX永续','crypto','')        # 13403 新增日期事实
assert topic.style_rc(R,'Sophon 正式确定主网将于 11 月 30 日关停，用户需在 11 月 25 日前提取资产','Sophon宣布11月30日关停主网，SOPH跌11%','crypto','')  # 13384 补价格腿
assert not topic.style_rc(R,'分析师下调目标价，Cerebras Systems Inc.跌5.1%','分析师下调目标价，CBRS收跌5.1%','tradfi','')   # 法人全名换 ticker
assert not topic.style_rc(R,'上调营收指引，Vicor Corporation涨9.9%','Vicor上调营收指引，VICR盘中涨10%','tradfi','仅措辞:四舍五入')
assert not topic.style_rc('改数字-定稿','PEARL列入Coinbase路线图，正式上市仍待观察','PEARL列入Coinbase上币路线图，现报1.96美元','crypto','')
EOF
n=$((n+1)); python3 - <<'EOF' || { echo "❌ pct.py(v3.7.9): --pct 标签自带百分数应按标签本身核对"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout'))
import pct
t='AI数据中心商Elice韩国上市首日收跌32%'
assert pct.check(t,['跌32%=61500/90500'])[0][0]=='OK'
assert pct.check(t,['收跌=61500/90500'])[0][0]=='OK'
assert pct.check('X报1美元，涨32%',['涨32%=61500/90500'])[0][0]=='FAIL'   # 方向反了
EOF

# ── v3.7.9 用户定 10-21:纯行情币成交额 <1 亿默认弃建 / 币安限流不崩 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.9): 纯行情币成交 <1 亿应拦,≥1 亿/有诱因/豁免放行"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
A='纯行情-A定则'
assert topic.lowvol(A,'crypto','ARIA 24小时涨64%，币安合约成交0.7亿美元','')            # 10-21 ARIA 0.7 亿
assert topic.lowvol(A,'crypto','BIRB 24小时涨31%，资金费率-1.9%','成交0.5亿美元')        # 数字只在备注
assert topic.lowvol(A,'crypto','EPIC 24小时跌34%','成交3550万美元')
assert not topic.lowvol(A,'crypto','JCT 24小时涨125%，币安合约成交4.1亿美元','')
assert not topic.lowvol('有诱因-多源','crypto','X上线Upbit，成交0.3亿美元','')
assert not topic.lowvol(A,'crypto','Y 24小时涨40%，成交0.5亿美元','豁免成交额:上所首日')
assert not topic.lowvol(A,'tradfi','Z收涨12%，成交0.5亿美元','')
EOF
_Q9=$(mktemp -d); printf "[]" > "$_Q9/b0.json"; printf "{}" > "$_Q9/q.json"; : > "$_Q9/ca.tsv"; printf '{"channels":[]}' > "$_Q9/ch.json"
printf '%s' '[{"symbol":"LOWVUSDT","priceChangePercent":"40","quoteVolume":"50000000"},{"symbol":"HIVUSDT","priceChangePercent":"-35","quoteVolume":"150000000"}]' > "$_Q9/bn3.json"
_cv3=$(B0JSON="$_Q9/b0.json" COVERAGE_QUOTES="$_Q9/q.json" COVERAGE_BN="$_Q9/bn3.json" ACTIONS="$_Q9/ca.tsv" CHANNELS="$_Q9/ch.json" COVERAGE_LOG="$_Q9/cv3.log" python3 "$D/coverage.py")
n=$((n+1)); echo "$_cv3" | grep -q '✔ 币 LOWV +40.0% → 低量弃建' && echo "$_cv3" | grep -q '🚨 币 HIV' || { echo "❌ coverage(v3.7.9): 成交 <1 亿的 LOWV 应记低量弃建、1.5 亿的 HIV 仍算漏: $(echo "$_cv3" | grep -E 'LOWV|HIV')"; fail=$((fail+1)); }
printf '%s' '{"code":-1003,"msg":"Way too many requests"}' > "$_Q9/bn4.json"
_cv4=$(B0JSON="$_Q9/b0.json" COVERAGE_QUOTES="$_Q9/q.json" COVERAGE_BN="$_Q9/bn4.json" ACTIONS="$_Q9/ca.tsv" CHANNELS="$_Q9/ch.json" COVERAGE_LOG="$_Q9/cv4.log" python3 "$D/coverage.py" 2>&1)
n=$((n+1)); echo "$_cv4" | grep -q '半盲=币' && ! echo "$_cv4" | grep -q Traceback || { echo "❌ coverage(10-21): 币安限流返回字典应标半盲=币、不得崩: $(echo "$_cv4" | tail -2)"; fail=$((fail+1)); }
rm -rf "$_Q9"

# ── v3.7.10 用户定 10-21:明确利好/利空公告要写涨跌和因果 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.10): 只写现价却藏着≥5%涨跌应拦,写了涨跌/标方向不明确/<5% 放行"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic as T
assert T.price_only('PEARL列入Coinbase上币路线图，现报1.96美元','CoinGecko 1.96美元 24h+5.8%')        # 10-20 13387:路线图属明确利好,该写涨6%
assert T.price_only('Arkham全量查询转企业专属，ARKM报0.128美元','ARKM币安永续0.1283 24h+10.3%')
assert not T.price_only('Arkham全量查询转企业专属，ARKM报0.128美元','方向不明确:商业模式调整;24h+10.3%')
assert not T.price_only('Coinbase将PEARL列入路线图，PEARL涨6%','24h +5.8%')
assert not T.price_only('X上线测试网，X报1美元','24h +3.1%')
EOF

# ── v3.7.11 每晚复盘 10-21:重复撤因须有在线留存题 / 恢复跨日题须同向 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py(v3.7.11): 重复对象已撤应拦、恢复方向相反的跨日题应拦"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic as T
db={10000003186:{'status':3},13427:{'status':0}}; g=db.get
assert T.dup_target('重复-同标的','与10000003186同日同一NBIS盘后行情的重复题',10000003190,g)    # 10-21 3190:留存题已撤
assert not T.dup_target('重复-同标的','与13427同AGT',13357,g)
assert T.dup_target('重复-同标的','同日重复',1,g)                                              # 没写留存题 id
assert not T.dup_target('重复-同标的','与13001重复',1,g)                                        # 查不到不拦
assert not T.dup_target('缺诱因-未达线','与10000003186',1,g)
e={'id':10000003181,'title':'AI数据中心商Elice韩国上市首日收跌32%','keywords':'Elice,엘리스,AI数据中心,韩国IPO'}
tops=[{'id':10000003196,'status':0,'title':'韩国Elice上市次日收涨30%至涨停','keywords':'Elice,엘리스,AI数据中心,韩国IPO'}]
assert T.opposite_live(e,tops,'')                                                               # 10-21 3181:跨日反向
assert not T.opposite_live(e,tops,'方向相反仍恢复:测试')
assert not T.opposite_live({'id':13357,'title':'AGT 24小时跌32%','keywords':'AGT'},[{'id':13427,'status':0,'title':'AGT 24小时跌35%','keywords':'AGT'}],'')
assert not T.opposite_live({'id':1,'title':'半导体走高，X涨5%','keywords':'半导体'},[{'id':2,'status':0,'title':'半导体下挫，Y跌5%','keywords':'半导体'}],'')   # 泛中文词不算同标的
EOF

# ── 10-22 复盘(13357/13358 两天被撤两次):跨交易日同向不算重复 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.py cross_day_dup(10-22): 留存题隔天同向应拦,同一天/反向/查不到/盘前对收盘不拦"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic as T
me={'id':13357,'title':'AGT 24小时跌32%','created_at':'2026-10-19 10:53:39'}
db={13427:{'status':0,'title':'AGT 24小时跌35%','created_at':'2026-10-21 14:20:00'},
    13500:{'status':0,'title':'AGT 24小时跌33%','created_at':'2026-10-19 16:00:00'},
    13501:{'status':0,'title':'AGT 24小时涨40%','created_at':'2026-10-21 14:20:00'},
    13502:{'status':3,'title':'AGT 24小时跌30%','created_at':'2026-10-21 14:20:00'}}; g=db.get
assert T.cross_day_dup('重复-同标的','闸:聚簇：与 13427 同 AGT，是超集；撤旧题',me,g)              # 10-21/10-22 原样
assert not T.cross_day_dup('重复-同标的','与13500同日同AGT',me,g)                                  # 同一天(相隔5小时)
assert not T.cross_day_dup('重复-同标的','与13501同AGT',me,g)                                      # 方向相反:过期题表要撤老题
assert not T.cross_day_dup('重复-同标的','与13427、13500重复',me,g)                                # 有一条同一天就算真重复
assert not T.cross_day_dup('重复-同标的','与13001重复',me,g)                                        # 查不到不拦
assert not T.cross_day_dup('重复-同标的','与13502重复',me,g)                                        # 不在线的交给 dup_target
assert not T.cross_day_dup('缺诱因-未达线','与13427',me,g)
pre={'id':10000003300,'title':'X盘前涨5%','created_at':'2026-10-21 16:00:00'}
assert not T.cross_day_dup('重复-同标的','被10000003301覆盖',pre,{10000003301:{'status':0,'title':'X收涨6%','created_at':'2026-10-22 04:05:00'}}.get)   # 盘前对同一时段收盘
assert not T.cross_day_dup('重复-同标的','与13427',{'id':1,'title':'AGT报0.04美元','created_at':'2026-10-19 10:00:00'},g)                               # 看不出方向不拦
EOF

# ── v3.7.12 10-22:coverage 前收在 Yahoo 缺当日 K 线时不得取到前天 ──────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ coverage.prev_close(10-22 CRCL): 缺当日K线时最后一根即前收"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import coverage as C
m={'gmtoffset':-14400,'regularMarketTime':1792612800}                       # 10-21 16:00 ET
rows=[(1792330200,82.22),(1792416600,81.37),(1792503000,85.87)]             # 最后一根=10-20
assert C.prev_close(rows,m)==85.87                                           # 原逻辑取 81.37 → CRCL 误报 +10.2%
assert C.prev_close(rows+[(1792589400,89.71)],m)==85.87                      # 含 10-21 K 线时取倒数第二根
EOF

# ── 10-22 复盘:coverage 匹配在线题要比方向,反向旧题不算「有题」────────────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ coverage.covered(10-22 AGT): 当日 +34% 不该被 10-21『AGT 24小时跌35%』算有题"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import coverage as C
old=[{'id':13427,'keywords':'AGT','title':'AGT 24小时跌35%，现报0.0434美元'}]
assert C.covered('AGT',set(),old,[],33.6)[0] is None                         # 反向:漏建不得被盖住
assert C.covered('AGT',set(),old,[],-40.0)==('有题','13427')                 # 同向照算
assert C.covered('AGT',set(),old,[])==('有题','13427')                       # 不给涨跌幅时行为不变
mix=[{'id':1,'keywords':'SVRN','title':'加密财库股收涨，SVRN涨41%、SDEV跌3%'}]
assert C.covered('SVRN',set(),mix,[],-20.0)==('有题','1')                    # 涨跌都含的标题不判方向
EOF

# ── 10-22 复盘:推送 summary 手写计数与标题行不符要在 send 前拦(同类第 3 次)────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lark-push.summary_count_mismatch(10-22): 手写『改1撤8』而台账改3撤12 应判不符"; fail=$((fail+1)); }
import os,sys,importlib.util; sys.stdout=open(os.devnull,'w')
s=importlib.util.spec_from_file_location('lp',os.path.expanduser('~/.trend-scout/lark-push.py')); L=importlib.util.module_from_spec(s); s.loader.exec_module(L)
class R:
    def __init__(s,sm): s.summary=sm
    def counts(s): return {'create':4,'update':3,'cull':12}
assert len(L.summary_count_mismatch(R('14:40刷新：建4改1撤8。韩日收盘定稿')))==2
assert L.summary_count_mismatch(R('韩日收盘定稿,布油涨2.5%'))==[]            # 不写计数不拦
assert L.summary_count_mismatch(R('建4改3撤12'))==[]
EOF

# ── 10-23 复盘:非美股盘中题的收盘复查被挂到次日(Zip .AX / 宇树 .SH / 沃尔沃 .ST)────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ topic.review_slot(10-23): .AX/.SH/.ST 后缀未识别,复查挂错日"; fail=$((fail+1)); }
import os,sys,importlib.util,datetime as d; sys.stdout=open(os.devnull,'w')
s=importlib.util.spec_from_file_location('tp',os.path.expanduser('~/.trend-scout/topic.py')); T=importlib.util.module_from_spec(s); s.loader.exec_module(T)
f=lambda t,k,n: T.review_slot(t,k,n).strftime('%d-%H:%M')
assert f('Zip披露美国欺诈事件损失，盘中跌30%','ZIP.AX,Zip Co',d.datetime(2026,10,23,10,1))=='23-14:40'
assert f('人形机器人股走强，宇树科技盘中涨20%','宇树科技,688836.SH',d.datetime(2026,10,23,14,43))=='23-17:30'          # 11-07 用户定 A/港轮改 17:30
assert f('沃尔沃汽车盘中跌27%','VOLCAR-B.ST,沃尔沃汽车',d.datetime(2026,10,23,16,36))=='24-09:40'
assert f('LKQ盘中跌19%','LKQ',d.datetime(2026,10,23,22,9))=='24-09:40'           # 美股不变
EOF

# ── 10-23 复盘:coverage 前收取错(Yahoo 日线缺中间一天)+ 弃建记录不比方向(AKE)────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ coverage.prev_close/_note_dir(10-23): 缺天应返回 None、反向弃建不得算覆盖"; fail=$((fail+1)); }
import os,sys,importlib.util; sys.stdout=open(os.devnull,'w')
s=importlib.util.spec_from_file_location('cv',os.path.expanduser('~/.trend-scout/coverage.py')); C=importlib.util.module_from_spec(s); s.loader.exec_module(C)
rmt=1792713600+3600; m={'gmtoffset':-14400,'regularMarketTime':rmt}
assert C.prev_close([(1792540800,262.93),(1792713600,229.73)],m) is None          # 10-20、10-22 两根,缺 10-21 → 不许拿前天收
assert C.prev_close([(1792627200,273.05),(1792713600,229.73)],m)==273.05          # 10-21、10-22 相邻 → 正常
assert C._weekday_gap('2026-10-23','2026-10-26')==1                               # 周五→周一不算缺
note=['弃建|AKE|币安永续三次读数-30.63%/-30.04%/-29.98%跨线,成交1.02亿;无诱因|2026-10-22']
assert C.covered('AKE',set(),[],note,40.8)==(None,None)                          # 反向弃建不盖漏建
assert C.covered('AKE',set(),[],note,-35.0)[0]=='弃建'                            # 同向照算
assert C.covered('AKE',set(),[],['弃建|AKE|无诱因|x'],40.8)[0]=='弃建'             # 备注无方向不判
EOF

# ── 10-23 复盘:前收以官方 chartPreviousClose 为准(日线缺天/小时线不含收盘竞价,KER.PA 215.10 vs 213.50)────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ pct.pick_prev(10-23): 日线前收与官方前收不一致时应以官方为准"; fail=$((fail+1)); }
import os,sys,importlib.util; sys.stdout=open(os.devnull,'w')
s=importlib.util.spec_from_file_location('pc',os.path.expanduser('~/.trend-scout/pct.py')); P=importlib.util.module_from_spec(s); s.loader.exec_module(P)
assert P.pick_prev(215.10,213.50)[0]==213.50 and P.pick_prev(215.10,213.50)[1]       # 不一致 → 官方 + 提示
assert P.pick_prev(14.27,14.115)[0]==14.115                                          # 日线缺 10-22,拿到的是 10-21
assert P.pick_prev(217.77,217.77)==(217.77,None)                                     # 一致不提示
assert P.pick_prev(217.77,None)==(217.77,None)                                       # 取不到官方前收保持原值
EOF

# ── 10-23 复盘:预告形态的题被记成「灌水-产品公告」(13473/13495,同日两次)────────
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lint.preview_misfiled(10-23): 预告形态+产品公告码应判错码"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import lint
assert lint.preview_misfiled('灌水-产品公告','ARBITRUM DAO支持1亿ARB计划，本月将进行链上表决')
assert lint.preview_misfiled('灌水-产品公告','PTAH十枚NFT合成矿机，挖矿规则待揭晓')
assert not lint.preview_misfiled('灌水-产品公告','JUPITER接入Decrypt，阅读页可直接交易')   # 已发生的产品接入照常
assert not lint.preview_misfiled('预告题-准入不过','PTAH十枚NFT合成矿机，挖矿规则待揭晓')
EOF

# retro1031:🔔 盘中进行时只列美股收盘题(亚股收盘题美股盘中拉不到价)
n=$((n+1)); python3 - <<'EOF' || { echo "❌ lint.us_close(retro1031): KOSPI/创业板/日股/.T 关键词应排除,美股照列"; fail=$((fail+1)); }
import os,sys;sys.path.insert(0,os.path.expanduser('~/.trend-scout'));import lint
assert not lint.us_close({'title':'谷歌财报重挫拖累芯片股，KOSPI收跌3.5%','keywords':'KOSPI'})
assert not lint.us_close({'title':'全球AI股抛售拖累科技股，创业板指收跌4.1%','keywords':'创业板'})
assert not lint.us_close({'title':'售价下滑且警惕客户提前下单，村田制作所收跌7.7%','keywords':'6981,村田制作所,Murata'})
assert not lint.us_close({'title':'村田收跌7.7%','keywords':'6981.T'})
assert lint.us_close({'title':'财报后遭抛售，闪迪SNDK收跌13%','keywords':'SNDK,Sandisk,闪迪'})
EOF

# retro1031:crypto「24小时涨跌X%」标题与币安现读差>1pp 拦(13732 写41%、现读-42.18%)
n=$((n+1)); python3 - <<'EOF' || { echo "❌ pct.bn_title_mismatch(retro1031): 差>1pp应拦、≤1pp放行、无代码不判"; fail=$((fail+1)); }
import os,sys,json,tempfile;sys.path.insert(0,os.path.expanduser('~/.trend-scout'));import pct
f=tempfile.mktemp(); json.dump({"Q":-42.178,"AKE":-37.93},open(f,'w')); os.environ['PCT_BN_FAKE']=f
assert pct.bn_title_mismatch('Quack AI 24小时跌41%，币安合约成交1.9亿美元',['Quack AI','Q'])
assert pct.bn_title_mismatch('Quack AI 24小时跌42%，币安合约成交1.9亿美元',['Quack AI','Q']) is None
assert pct.bn_title_mismatch('AKE 24小时跌38%，币安合约成交1.5亿美元',['AKE']) is None
assert pct.bn_title_mismatch('AKE 24小时涨38%，币安合约成交1.5亿美元',['AKE'])
assert pct.bn_title_mismatch('Aave解除全网市场冻结，AAVE报124美元',['AAVE']) is None
EOF

# ── 10-24 复盘:checklist 未 verify 就写了 refresh(18:07 轮)────────
n=$((n+1)); _T=$(mktemp -d); : > "$_T/cl.tsv"; : > "$_T/rf.txt"
# scope1031:set -u 下 REFRESH_FORCE 未设时应打印「本轮清单未 verify」而不是「unbound variable」(10-31 首扫收尾实测)
n=$((n+1)); CHECKLIST_FILE="$_T/cl.tsv" REFRESH_FILE="$_T/rf.txt" "$HOME/.trend-scout/log-snapshot.sh" refresh 2>&1 | grep -q '本轮清单未 verify' || { echo "❌ log-snapshot refresh(scope1031): 未设 REFRESH_FORCE 时应给出拒写说明,不是 unbound variable"; fail=$((fail+1)); }
if CHECKLIST_FILE="$_T/cl.tsv" REFRESH_FILE="$_T/rf.txt" "$HOME/.trend-scout/log-snapshot.sh" refresh >/dev/null 2>&1 || [ -s "$_T/rf.txt" ]; then echo "❌ log-snapshot refresh(10-24): 清单未归档时应拒写"; fail=$((fail+1))
else rm -f "$_T/cl.tsv"; CHECKLIST_FILE="$_T/cl.tsv" REFRESH_FILE="$_T/rf.txt" "$HOME/.trend-scout/log-snapshot.sh" refresh >/dev/null 2>&1 && [ -s "$_T/rf.txt" ] || { echo "❌ log-snapshot refresh(10-24): 清单已归档时应放行"; fail=$((fail+1)); }; fi; rm -rf "$_T"

# ── v3.7.18(10-26 用户定):豁免②只剩成交额时须 24h≥±15%(盲审 W42 BAT 11%、IN 2.2%、CAP 15%)────────
n=$((n+1)); python3 - <<'PYV' || { echo "❌ topic.vol_only_exempt(v3.7.18): 成交额单项豁免须配 24h≥±15%"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
assert topic.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗|pct.py bn INUSDT 24h +2.216% 合约2.1亿')
assert topic.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗|bn BATUSDT 24h +10.71% 额1.53亿')
assert topic.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗|无读数')
assert not topic.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗|pct.py bn CAPUSDT 24h +15.036% 合约2.9亿')
assert not topic.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✓|24h +3%')
assert not topic.vol_only_exempt('改数字,无四查行')
PYV

# ── 10-26 复盘:-T 备注漏读 / 同品种族反向题 / note 枚举提示 ────────────────────────────
n=$((n+1)); python3 - <<'PYR' || { echo "❌ topic(10-26 复盘): note_of 须读 -T;同品种族反向题须列出"; fail=$((fail+1)); }
import os,sys,argparse; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import topic
NS=argparse.Namespace
assert topic.note_of(NS(T='判据|留存10000003263|因', note=None)).startswith('判据|留存')
assert topic.note_of(NS(T=None, note='x')) == 'x'
src=open(os.path.expanduser('~/.trend-scout/topic.py'),encoding='utf-8').read()
assert src.count("getattr(a, 'note', '') or ''") == 1, '检查处须走 note_of'
assert topic.dup_target('重复-同标的', topic.note_of(NS(T='判据|留存题10000003263同切面|因', note=None)), 1, lambda i: None) is None
old=[{'id':3262,'status':0,'title':'伊朗局势升温，布油收涨3.3%','keywords':'Brent,布油,原油'},
     {'id':3,'status':3,'title':'布油收涨','keywords':'Brent'},
     {'id':4,'status':0,'title':'油价走低','keywords':'OIL'},
     {'id':5,'status':0,'title':'黄金收涨2%','keywords':'XAUT,黄金'}]
r=[o['id'] for o in topic.opposite_after_create({'title':'特朗普称暂不打击伊朗，WTI盘中跌1.7%','keywords':'WTI,CL,原油'},old)]
assert r==[3262], r
assert [o['id'] for o in topic.opposite_after_create({'title':'WTI盘中涨2%','keywords':'WTI'},old)]==[4]
assert topic.opposite_after_create({'title':'CL概念股跌5%','keywords':'CL'},old)==[]
# 11-12 用户令修:中文关键词的指数题认不出同标的(3767 台股收跌 vs 3739 台股加权指数收涨)
tw=[{'id':3739,'status':0,'title':'台股加权指数收涨3.6%，台积电涨4.8%','keywords':'台股,台湾加权指数,台积电,TSMC'},
    {'id':3746,'status':0,'title':'光通信股大涨，剑桥科技港股收涨23%、中际旭创A股涨15%','keywords':'光通信,剑桥科技'},
    {'id':9,'status':0,'title':'KOSPI收涨3.1%','keywords':'韩国综合指数'}]
r=[o['id'] for o in topic.opposite_after_create({'title':'英伟达高层风波冲击供应链，台股收跌2.6%、纬颖跌6.5%','keywords':'台股,台湾加权指数,6669.TW,2382.TW'},tw)]
assert r==[3739], r
assert [o['id'] for o in topic.opposite_after_create({'title':'恒指收跌3%','keywords':'恒生指数'},tw)]==[], '港股个股题不得算恒指同标的'
assert [o['id'] for o in topic.opposite_after_create({'title':'韩股收跌3%，三星跌5%','keywords':'^KS11,三星电子'},tw)]==[9]
PYR
n=$((n+1)); _o=$(ACTIONS="$(mktemp)" SNAPSHOTS=/dev/null REJ="$(mktemp)" "$D/log-action.sh" note - 系统建放行 '判据=x；实测=y；落此code因=z' 2>&1); echo "$_o" | grep -q 'note 可用: .*留档' || { echo "❌ log-action(10-26 复盘): note rc 非枚举须列出可用码"; fail=$((fail+1)); }

# ── 10-27 复盘:报道前缀冒号题不判 KOL 观点 / 四查成交额格按题面判 ──────────────────────
n=$((n+1)); python3 - <<'PYQ' || { echo "❌ lint(10-27 复盘): 报道前缀不判KOL观点;成交额格须题面主张"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import lint
r=lint.junk_class('10/26报道：XRP Ledger增1.5亿美元基金份额'); assert not r or r[0]!='灌水-KOL观点', r
assert lint.junk_class('Ansem：转向看空比特币和以太坊')[0]=='灌水-KOL观点'
assert lint.vol_claim_unsupported('BTW一小时跌12.2%，未平仓量反增17.3%','四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗')
assert not lint.vol_claim_unsupported('JCT 24小时涨31%，币安合约成交2.8亿美元','四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗')
assert not lint.vol_claim_unsupported('BTW一小时跌12.2%','四查:幅度✗ 成交额✓;来源主张成交额:Odaily')
assert not lint.vol_claim_unsupported('BTW一小时跌12.2%','四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗')
PYQ
_VT=$(mktemp -d); printf '%s' '{"topics":[{"id":99990777,"status":0,"title":"BTW一小时跌12.2%，未平仓量反增17.3%"}]}' > "$_VT/b0.json"
n=$((n+1)); ACTIONS="$_VT/a.tsv" SNAPSHOTS="$_VT/s.tsv" REJ="$_VT/r.tsv" B0JSON="$_VT/b0.json" "$D/log-action.sh" note 99990777 留档 '系统建放行|判据=meme豁免②；实测=合约2.8亿；四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗' >/dev/null 2>&1 && { echo "❌ log-action(10-27 复盘): 题面未主张成交额却记成交额✓,应拦"; fail=$((fail+1)); }

# ── 10-28 复盘:涨跌幅核对跳过非涨跌百分数 / 跨午夜时间词 / 待审提示 / tradfi 关键词撞现货代币 ──────────
n=$((n+1)); python3 - <<'PYS' || { echo "❌ retro1028: pct 跳净利增幅/跨午夜词/待审提示/现货同名"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import pct, lint, topic
r=pct.check('恒瑞医药三季度净利增89%，港股收涨11%',['恒瑞医药=49.56/44.72']); assert r[0][0]=='OK', r
r=pct.check('恒瑞医药三季度净利增89%，港股收涨15%',['恒瑞医药=49.56/44.72']); assert r[0][0]=='FAIL', r
r=pct.check('恒瑞医药三季度净利增89%，港股收跌11%',['恒瑞医药=49.56/44.72']); assert r[0][0]=='FAIL', r
assert lint.cross_midnight_word('美联储今晨2点将公布利率决议',22)
assert lint.cross_midnight_word('美联储今晨2点将公布利率决议',9) is None
assert lint.cross_midnight_word('美联储明晨2点将公布利率决议',22) is None
assert topic.pending_hint(2,'13624') and 'publish' in topic.pending_hint(2,'13624')
assert topic.pending_hint(0,'13624') is None
assert topic.spot_clash(['ULBI','Ultralife','ENS','EnerSys'],{'ENS','BTC'})==['ENS']
assert topic.spot_clash(['VRT','Vertiv'],{'ENS'})==[]
PYS

# ── 10-29 复盘:票数冒号写法 / 四查市值关口判据 ──────────
n=$((n+1)); python3 - <<'PYT' || { echo "❌ retro1029: 票数冒号写法/市值关口判据"; fail=$((fail+1)); }
import os,sys; sys.path.insert(0,os.path.expanduser('~/.trend-scout')); sys.stdout=open(os.devnull,'w')
import lint
assert lint.ratio_like_time('美联储10:2维持利率不变，BTC报8.06万美元')
assert lint.ratio_like_time('美国今晚20:30将公布三季度GDP，预期增3.2%') is None
assert lint.ratio_like_time('美联储维持利率不变、两票主张加息，BTC报8.01万美元') is None
assert lint.mcap_gate_misjudged('四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗(+25%<30%;182万美元;现1440万已回1500万下;转发非事件)')
assert lint.mcap_gate_misjudged('四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗(30天高点1320万,未触及1500万)') is None
assert lint.mcap_gate_misjudged('四查:幅度✗ 成交额✗ 市值关口✓ 硬事件✗') is None
PYT
_VT=$(mktemp -d); printf '%s' '{"topics":[{"id":99990779,"status":0,"title":"Robinhood转发，PRIORS市值越过1500万美元"}]}' > "$_VT/b0.json"
n=$((n+1)); ACTIONS="$_VT/a.tsv" SNAPSHOTS="$_VT/s.tsv" REJ="$_VT/r.tsv" B0JSON="$_VT/b0.json" "$D/log-action.sh" cull 99990779 缺诱因-未达线 '判据=meme四查;实测=dex mcap 1440万;四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗(现1440万已回1500万下)' >/dev/null 2>&1 && { echo "❌ log-action(10-29 复盘): 市值关口以已跌回记✗应拦"; fail=$((fail+1)); }

# retro1102:周一早上现拉看板起始日须覆盖股票窗口(周五建的题),不能只拉近2天
_bs=$(cd "$D" && python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);import calendar,time;print(c.b0_start(calendar.timegm((2026,11,2,1,55,0))))")
n=$((n+1)); [ "$_bs" \< "2026-10-31" ] || { echo "❌ coverage(retro1102): 周一 01:55 UTC 现拉看板起始日应早于 10-31(覆盖周五),得 $_bs"; fail=$((fail+1)); }
_bs2=$(cd "$D" && python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);import calendar;print(c.b0_start(calendar.timegm((2026,11,4,3,0,0))))")
n=$((n+1)); [ "$_bs2" = "2026-11-02" ] || { echo "❌ coverage(retro1102): 周三起始日应为今天-2天 2026-11-02,得 $_bs2"; fail=$((fail+1)); }

# 1102tier1:tradfi 单名有诱因门槛 5%(用户 11-02 定)
_tf=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
print(bool(t.tradfi_floor('tradfi','F5新品发布，FFIV盘中涨3.2%','x')), bool(t.tradfi_floor('tradfi','Marvell洽谈收购Lumentum，LITE盘前涨5.1%','x')),
      bool(t.tradfi_floor('tradfi','韩国明年AI预算拟增近一倍，KOSPI收涨2.2%','x')), bool(t.tradfi_floor('tradfi','美联储维持利率不变，BTC报8.01万美元','x')),
      bool(t.tradfi_floor('tradfi','F5新品发布，FFIV盘中涨3.2%','低于5%仍建:回归')), bool(t.tradfi_floor('crypto','X 24小时涨3%','x')))")
n=$((n+1)); [ "$_tf" = "True False False False False False" ] || { echo "❌ topic.py(1102tier1): tradfi 单名<5%应拦、≥5%/指数/无百分数/例外/币题放行,得 $_tf"; fail=$((fail+1)); }

# mkt1105:对账池补全市场榜——EQUITY、市值≥10亿、|涨跌|≥10% 才进;ETF/小票/幅度不够剔掉;亚洲指数进 IDX
_YH=$(mktemp); printf '%s' '[["DJT",-24.5,1.2e9,"EQUITY"],["XYZQ",-30,5e8,"EQUITY"],["SOXL",-19,9e9,"ETF"],["AAPL",5.3,3e12,"EQUITY"],["DOX",-30.1,4.5e9,"EQUITY"],["CVS",-12.5,1.02e11,"EQUITY"]]' > "$_YH"
_ymd=$(cd "$D" && COVERAGE_YH="$_YH" python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
print(','.join(c.yh_movers()))")
n=$((n+1)); [ "$_ymd" = "CVS" ] || { echo "❌ coverage(mkt1105): 默认门槛 200 亿美元应只留 CVS,得 $_ymd"; fail=$((fail+1)); }
_ym=$(cd "$D" && COVERAGE_YH_MINCAP=1e9 COVERAGE_YH="$_YH" python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
print(','.join(c.yh_movers()), '^KS11' in c.IDX, '7203.T' in c.EXTRA)"); rm -f "$_YH"
n=$((n+1)); [ "$_ym" = "DJT,DOX,CVS True True" ] || { echo "❌ coverage(mkt1105): 门槛 10 亿时应为 DJT,DOX,CVS 且亚洲指数/大票入池,得 $_ym"; fail=$((fail+1)); }
# twii1109:台股加权进指数对账(±3%),台股题标题能认作有题、crypto 题不算
_tw=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
thr,nm=c.IDX['^TWII']
live=[{'id':10000003677,'domain':'tradfi','title':'台股加权指数收涨4.9%，单日涨近2000点','keywords':'台股,台湾加权指数,台积电'}]
cr=[{'id':1,'domain':'crypto','title':'台股代币化上线','keywords':''}]
print(thr, c.covered('^TWII',nm,live,[],4.94,thr,idx=True)[0], c.covered('^TWII',nm,cr,[],4.94,thr,idx=True)[0])" 2>&1)
n=$((n+1)); [ "$_tw" = "3.0 有题 None" ] || { echo "❌ coverage(twii1109): ^TWII 应为 ±3% 线、台股题算有题、crypto 题不算,得 $_tw"; fail=$((fail+1)); }

# cov1105b:弃建前缀误配(P≠PWR)、建题备注样本算有题(仅股票)
_cvb=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
live=[{'id':1,'keywords':'SNDK,AMD','title':'AI芯片股盘中暴跌，SNDK跌17%'},{'id':2,'keywords':'DoorDash','title':'DoorDash盘中跌13%'}]
cn={'1':'样本 ALAB 188.36/223.27=-15.6%','2':'实测长桥DASH 172.4/198.6'}
print(c.covered('P',set(),[],['弃建|PWR|11-04收-11.7%'],-14.8,10)[0], c.covered('ALAB',set(),live,[],-15.6,10,cn)[0], c.covered('DASH',set(),live,[],-13.2,10,cn)[0], c.covered('ALAB',set(),live,[],-15.6,10)[0])")
n=$((n+1)); [ "$_cvb" = "None 有题 有题 None" ] || { echo "❌ coverage(cov1105b): 应为 None 有题 有题 None,得 $_cvb"; fail=$((fail+1)); }
# idx1106:指数弃建在行情明显扩大后不再算已处置(SPY 盘中-2.7%弃建被收盘-4.4%沿用);个股不受影响;DIA 进指数表
_cvi=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
nt=['弃建|SPY|标普500盘中-2.7%,由纳指题承载|2026-11-05']
print(c.covered('SPY',{'标普'},[],nt,-4.4,2.0,idx=True)[0], c.covered('SPY',{'标普'},[],nt,-3.1,2.0,idx=True)[0], c.covered('SPY',{'标普'},[],nt,-4.4,2.0)[0], 'DIA' in c.IDX)")
n=$((n+1)); [ "$_cvi" = "None 弃建 弃建 True" ] || { echo "❌ coverage(idx1106): 应为 None 弃建 弃建 True,得 $_cvi"; fail=$((fail+1)); }
# retro1106:指数对账只认 tradfi 题(QQQ 曾被 crypto 题「纳斯达克批准INJ质押ETF」算有题),中文名后接数字也要认(「纳指100」)
_rc6=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
inj={'id':1,'domain':'crypto','title':'纳斯达克批准INJ质押ETF上市，INJ报8.02美元','keywords':'INJ'}
ndx={'id':2,'domain':'tradfi','title':'芯片股重挫后反弹，费半ETF盘中涨6%、纳指100涨2.4%','keywords':'SOXX'}
nm=c.IDX['QQQ'][1]
print(c.covered('QQQ',nm,[inj],[],2.6,2.5,idx=True)[0], c.covered('QQQ',nm,[inj,ndx],[],2.6,2.5,idx=True)[1])")
n=$((n+1)); [ "$_rc6" = "None 2" ] || { echo "❌ coverage(retro1106): 应为 None 2,得 $_rc6"; fail=$((fail+1)); }
# retro1106b:keywords 传合法 JSON 数组自动转逗号串;一个 --pct 塞两组按「,标签=」拆开;rc 非枚举时列出该 action 合法码
_rk6=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
import re
a=t.norm_kw('[\"非农\",\"美联储\"]'); b=t.norm_kw('[非农'); c=t.norm_kw('非农,美联储')
p=['费半ETF=139.765/131.9,纳指100=27281.698/26629.809']
q=[x.strip() for p0 in p for x in re.split(r'[,，](?=[^,，=]+=)', p0) if x.strip()]
import pct
r=pct.check('芯片股反弹，费半ETF盘中涨6%、纳指100涨2.4%',q)
print(a, b, c==a, len(q), all(lv!='FAIL' for lv,_ in r), 'cull 可用' in open('log-action.sh').read())")
n=$((n+1)); [ "$_rk6" = "['非农', '美联储'] False True 2 True True" ] || { echo "❌ retro1106b: 得 $_rk6"; fail=$((fail+1)); }
# fix1107(用户 11-07 点名修三项):①指数按 IDX 线判幅度不套个股 10% ②5% 门槛不再被「指引/指控」里的「指」放行 ③监管/执法动作算硬事件、不进⑥机械撤
_f7=$(cd "$D" && python3 -W ignore -c "
import sys;sys.path.insert(0,'.');import lint,importlib.util as u
s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
g=lambda x:[gg for lv,gg,_,_ in lint.lint_title(x,'tradfi') if gg.startswith('双要素')]
a=g('纳指收跌2.6%'); b=g('标普收跌1.2%'); c=g('RKLB收涨8%')
d=bool(t.tradfi_floor('tradfi','AAPL上调业绩指引，盘后涨2.6%','')); e=bool(t.tradfi_floor('tradfi','司法部指控XX，跌2%','')); f=t.tradfi_floor('tradfi','AI股抛售拖累美股，标普500收跌1.4%','') is None
h=bool(lint.hard_event('FinCEN切断MEXC美国金融接入，指其涉160亿美元交易')); i=bool(lint.hard_event('美国财政部宣布制裁伊朗加密交易所BitBank')); j=lint.hard_event('OKX Boost联动KNTQ，百万枚奖励进行中') is None
print(a,b,c,d,e,f,h,i,j)")
n=$((n+1)); [ "$_f7" = "['双要素-指数过线'] ['双要素-缺诱因'] ['双要素-缺诱因'] True True True True True True" ] || { echo "❌ fix1107: 得 $_f7"; fail=$((fail+1)); }
# q1107(用户 11-07 拍板 Q11/Q12/Q13/Q15):隔夜补射程、A/港复查 17:30+美股冬令时收盘、meme 幅度路径要成交额≥1亿、建题前须有本轮 B0
_q7=$(cd "$D" && env -u TS_NO_B0CHECK python3 -W ignore -c "
import importlib.util as u,datetime as d,json,tempfile
s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
m=d.datetime(2026,11,7,9,45).timestamp()*1000
a=t.out_of_scope({'id':1,'created_at':'2026-11-06 23:02:00'},'改归因','',m) is None
b=t.out_of_scope({'id':2,'created_at':'2026-11-06 21:00:00'},'改归因','',m) is not None
c=t.us_close_cst(d.datetime(2026,11,9))=='05:00' and t.us_close_cst(d.datetime(2026,7,9))=='04:00'
e=t.lowvol('meme豁免','crypto','X 24小时涨60%','币安合约成交0.5亿美元') is not None and t.lowvol('meme豁免','crypto','X上线币安','硬事件✓') is None
D=tempfile.mkdtemp(); json.dump({'fetched_at':'2026-11-07T10:09:45'},open(D+'/b0-latest.json','w'))
f=t.b0_stale('',d.datetime(2026,11,7,13,0),D) is not None and t.b0_stale('',d.datetime(2026,11,7,11,0),D) is None
print(a,b,c,e,f)")
n=$((n+1)); [ "$_q7" = "True True True True True" ] || { echo "❌ q1107: 得 $_q7"; fail=$((fail+1)); }
# line50-1106:用户定 crypto 纯行情/meme 豁免①幅度线 30→50(默认值,不设 TS_CRYPTO_LINE)
_l50=$(cd "$D" && env -u TS_CRYPTO_LINE python3 -W ignore -c "
import importlib.util as u
def L(n,f):
    s=u.spec_from_file_location(n,f);m=u.module_from_spec(s);s.loader.exec_module(m);return m
t=L('t','topic.py');c=L('c','coverage.py');l=L('l','lint.py')
a=t.crypto_amp('纯行情-A定则','crypto','AIN 24小时跌35%，币安合约成交3亿美元','')
b=t.crypto_amp('纯行情-A定则','crypto','AIN 24小时跌51%，币安合约成交3亿美元','')
d=t.crypto_amp('有诱因-多源','crypto','X上线币安，24小时涨35%','')
print(bool(a), b is None, d is None, t.CRYPTO_LINE, c.COIN_LINE, l.CRYPTO_LINE)")
n=$((n+1)); [ "$_l50" = "True True True 50.0 50.0 50.0" ] || { echo "❌ line50-1106: 应为 True True True 50.0 50.0 50.0,得 $_l50"; fail=$((fail+1)); }
# volamp1106:用户定豁免②(成交额>2亿)单独成立所需幅度 15→50;JCT -47% 成交4亿不再算豁免
_va=$(cd "$D" && env -u TS_VOL_AMP -u TS_CRYPTO_LINE python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
import sys;sys.path.insert(0,'.');import lint;lint.meme_scope=lambda *a,**k:True
r=lambda sym:(-47.3,4.0,'币安永续')
a=t.sicha_auto({'title':'JCT 24小时跌34%，币安合约成交3.7亿美元','keywords':'JCT'},'缺诱因-未达线','硬事件✗',reader=r)
b=t.vol_only_exempt('四查:幅度✗ 成交额✓ 市值关口✗ 硬事件✗ 24h -47%')
print(a[0], bool(b), t.VOL_EXEMPT_AMP)")
n=$((n+1)); [ "$_va" = "fill True 50.0" ] || { echo "❌ volamp1106: 应为 fill True 50.0,得 $_va"; fail=$((fail+1)); }

# retro1105:主网上线/TGE 算硬事件不进机械撤;亚洲业绩题配收盘涨跌须写公告时间、晚于收盘拦
_r5=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u
def L(n):
    s=u.spec_from_file_location(n,n+'.py');m=u.module_from_spec(s);s.loader.exec_module(m);return m
li,t=L('lint'),L('topic')
print(bool(li.hard_event('ELYSIUM主网11月9日上线，生态能否起势？')), bool(li.hard_event('硅谷大佬态度变了：AI发展还能只靠特朗普吗？')),
  bool(t.asia_earn_time('tradfi','索尼二季度利润增45%超预期，股价收涨7.1%','x',['6758.T'])),
  bool(t.asia_earn_time('tradfi','丰田上调全年利润预期，股价收涨17%','公告时间:13:30 JST,早于收盘',['7203.T'])),
  bool(t.asia_earn_time('tradfi','索尼二季度利润增45%超预期，股价收涨7.1%','公告时间:15:37 JST,晚于收盘',['6758.T'])),
  bool(t.asia_earn_time('tradfi','日本芯片股重挫，爱德万收跌15%','x',['6857.T'])), bool(t.asia_earn_time('tradfi','苹果财报超预期，AAPL收涨5%','x',['AAPL'])))")
n=$((n+1)); [ "$_r5" = "True False True False True False False" ] || { echo "❌ retro1105: 应为 True False True False True False False,得 $_r5"; fail=$((fail+1)); }

# tokexist1105:dex 判据——成交额单独成立;市值须配日成交≥1 万(BLAST polygon 死池 mcap 149 万/日成交 0.5 美元误判是代币)
_te=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','token_exist.py');t=u.module_from_spec(s);s.loader.exec_module(t)
print(t._dex_ok([{'chain':'polygon','vol24h':0.5,'mcap':1489939}])[0], t._dex_ok([{'chain':'bsc','vol24h':150000,'mcap':0}])[0],
      t._dex_ok([{'chain':'bsc','vol24h':20000,'mcap':3e6}])[0], t._dex_ok([{'chain':'bsc','vol24h':5000,'mcap':3e6}])[0], t._dex_ok([])[0])")
n=$((n+1)); [ "$_te" = "False True True False False" ] || { echo "❌ token_exist(tokexist1105): 应为 False True True False False,得 $_te"; fail=$((fail+1)); }
# spotclash1105:tradfi 建题关键词与现货代币同名改成拦,备注「同名代币已核」放行
_S=$(mktemp -d); : > "$_S/ta.tsv"; echo '[]' > "$_S/tb0.json"
_tps(){ CONSOLE_FAKE="$_S/c.json" ACTIONS="$_S/ta.tsv" SNAPSHOTS="$_S/ts.tsv" REJ="$_S/tr.tsv" REJ_OK="$_S/tok.tsv" UNLOGGED="$_S/tu.tsv" B0JSON="$_S/tb0.json" TOPIC_NO_DOWNSTREAM=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
n=$((n+1)); [ "$(_tps create --domain tradfi --title '希捷财报超预期，STX收涨8.1%' --keywords 'STX,Seagate' --rc 有诱因-多源 --note '回归:同名代币应拦' --pct 'STX=108.1/100')" != "0" ] \
  && [ "$(_tps create --domain tradfi --title '希捷财报超预期，STX收涨8.1%' --keywords 'STX,Seagate' --rc 有诱因-多源 --note '回归:放行;同名代币已核:公司名在关键词' --pct 'STX=108.1/100')" = "0" ] \
  || { echo "❌ topic.py(spotclash1105): STX 同名代币应拦、备注核过放行"; fail=$((fail+1)); }
rm -rf "$_S"

# sicha1105:撤 meme 题四查前三格工具算,硬事件人判(11-05 用户定「交给工具」)
_sc=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
T=lambda ti:{'domain':'crypto','title':ti,'keywords':'AKE'}
R=lambda x,qv=None:(lambda sym:(x,qv,'注入'))
a=lambda r:r[0]
print(a(t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','',R(-12))),
      a(t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','硬事件✗',R(-12))),
      t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','硬事件✗',R(-12))[1].startswith('四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗'),
      a(t.sicha_auto(T('AKE 24小时涨45%'),'缺价格腿','硬事件✗',R(45))),
      a(t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','与3820重复',R(-12))),
      a(t.sicha_auto({'domain':'tradfi','title':'X跌12%','keywords':'X'},'缺价格腿','',R(-12))),
      a(t.sicha_auto(T('AKE 24小时跌16%，币安合约成交3亿美元'),'缺价格腿','硬事件✗',R(-16,3.2))),
      a(t.sicha_auto(T('AKE 24小时跌10%，币安合约成交3亿美元'),'缺价格腿','硬事件✗',R(-10,3.2))),
      a(t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','硬事件✓',R(-12))),
      a(t.sicha_auto(T('AKE 24小时跌12%'),'缺价格腿','硬事件✗',lambda s:None)))")
n=$((n+1)); [ "$_sc" = "block fill True block skip skip block fill block block" ] || { echo "❌ topic.py(sicha1105): 四查自动算应为 block fill True block skip skip block fill block block,得 $_sc"; fail=$((fail+1)); }

# retro1104:跌幅收窄至X%算价格腿;--pct 标签去时段前缀再找;crypto 关键词首词是他币拦;拦截错类去题号/数字
_r4=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u
def L(n):
    s=u.spec_from_file_location(n,n+'.py');m=u.module_from_spec(s);s.loader.exec_module(m);return m
li,pc,t,r=L('lint'),L('pct'),L('topic'),L('retro')
g=lambda x:[g for _,g,_,_ in li.lint_title(x,'tradfi')]
print('双要素-缺价格' in g('民主党横扫国会两院，纳指期货跌幅收窄至0.2%'), '双要素-缺价格' in g('民主党横扫国会两院，纳指期货'),
      [lv for lv,_ in pc.check('日股盘中重挫，日经225跌3.1%、铠侠跌13%',['盘中跌=61123.98/63081.86'])][0],
      [lv for lv,_ in pc.check('日股盘中重挫，日经225跌3.1%',['盘前涨=1/2'])][0],
      t.token_word_clash(['CLANKER','Clanker','Mask Network'],{'MASK','CLANKER'}), t.token_word_clash(['NEAR','NEAR Intents'],{'NEAR'}),
      r._kind('13827 10 分钟内有写操作被拦:x')==r._kind('13776 10 分钟内有写操作被拦:y'), r._kind('tradfi 单名涨跌 4.8% < 5%')==r._kind('tradfi 单名涨跌 3.2% < 5%'))")
n=$((n+1)); [ "$_r4" = "False True OK FAIL ['Mask Network'] [] True True" ] || { echo "❌ retro1104: 价格腿/标签前缀/他币关键词/错类归一应为 False True OK FAIL ['Mask Network'] [] True True,得 $_r4"; fail=$((fail+1)); }

# retro1103c:板块聚合题首句须是板块播报或价格句(3450 选举概率+太阳能股);纠错缺标题变更提示改用留档
_sl=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
print(bool(t.sector_lead('板块聚合','民主党胜选概率走高，太阳能股NXT收涨15%、RUN涨10%')), bool(t.sector_lead('板块聚合','太阳能股普涨，NXT收涨15%、RUN涨10%')),
      bool(t.sector_lead('板块聚合','比特币一度跌破8.05万美元，NEAR、ZEC跌超10%')), bool(t.sector_lead('板块聚合','费半八连跌创2008年来最长，累计收跌16%')),
      bool(t.sector_lead('有诱因-多源','民主党胜选概率走高，太阳能股NXT收涨15%')))")
n=$((n+1)); [ "$_sl" = "True False False False False" ] || { echo "❌ topic.py(retro1103c): 板块聚合首句事件句应拦、板块/价格/指数首句与非板块rc放行,得 $_sl"; fail=$((fail+1)); }
n=$((n+1)); grep -q '用 note <id> 留档' "$D/log-action.sh" || { echo "❌ log-action.sh(retro1103c): 纠错缺标题变更提示应指向 note 留档"; fail=$((fail+1)); }

# retro1102b:收盘前写「收盘」拦(3432 A股盘中价当收盘);改数字-回落入枚举
_ce=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u,calendar;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
T=lambda *a:calendar.timegm(a)
print(bool(t.close_too_early('央行研究稳市工具，沪深300报4013点','11-02收盘4013.02',['000300.SH'],T(2026,11,2,6,50,0))),
      bool(t.close_too_early('央行研究稳市工具，沪深300报4017点','11-02收盘4016.92',['000300.SH'],T(2026,11,2,7,20,0))),
      bool(t.close_too_early('苹果财报超预期，AAPL收涨3%','x',['AAPL'],T(2026,11,2,15,0,0))),
      bool(t.close_too_early('苹果财报超预期，AAPL收涨3%','x',['AAPL'],T(2026,11,2,21,30,0))),
      bool(t.close_too_early('铠侠利润指引低于预期，收跌16%','x',['285A.T'],T(2026,11,2,6,10,0))),
      bool(t.close_too_early('苹果财报超预期，AAPL收涨3%','非当日收盘',['AAPL'],T(2026,11,2,15,0,0))))")
n=$((n+1)); [ "$_ce" = "True False True False True False" ] || { echo "❌ topic.py(retro1102b): 收盘前写收盘应拦、收盘后/例外放行,得 $_ce"; fail=$((fail+1)); }
n=$((n+1)); grep -q '改数字-回落' "$D/log-action.sh" || { echo "❌ log-action.sh(retro1102b): 枚举缺 改数字-回落"; fail=$((fail+1)); }
# retro1114b:b0-fetch 翻页上限由 21 页提到可配(默认60),存量全审 09-01 起 3184 条曾只拉到 2100
n=$((n+1)); grep -q "MAX_PAGES=int(os.environ.get('B0_MAX_PAGES','60'))" "$D/b0-fetch.py" && ! grep -q "pages>20" "$D/b0-fetch.py" || { echo "❌ b0-fetch(retro1114b): 翻页上限仍是 21 页"; fail=$((fail+1)); }
# retro1113:伪诱因无撤因码,系统题「板块集体下挫」作诱因被迫借「缺诱因-未达线」(3778 复审挑战成立,撤因码重犯22次)
n=$((n+1)); grep -q '归因-伪诱因' "$D/log-action.sh" || { echo "❌ log-action.sh(retro1113): 撤因枚举缺 归因-伪诱因"; fail=$((fail+1)); }
n=$((n+1)); python3 -c "import sys;sys.path.insert(0,'$D');import importlib.util as u;s=u.spec_from_file_location('lp','$D/lark-push.py');m=u.module_from_spec(s);s.loader.exec_module(m);assert '归因-伪诱因' in m.enum_rcs() and '归因-伪诱因' in m.RC_HUMAN" 2>/dev/null || { echo "❌ lark-push.py(retro1113): 归因-伪诱因 未解析进枚举或缺人话映射"; fail=$((fail+1)); }

# v3.7.22 检查计数 + 减法候选(用户 11-03 定):拦截/豁免都要记得上检查名,retro 才能列退役候选
_K=$(mktemp -d); echo '[]' > "$_K/b0.json"
_tk(){ CONSOLE_FAKE="$_K/c.json" ACTIONS="$_K/a.tsv" SNAPSHOTS="$_K/s.tsv" REJ="$_K/r.tsv" REJ_OK="$_K/ok.tsv" UNLOGGED="$_K/u.tsv" B0JSON="$_K/b0.json" CHECK_HITS="$_K/h.tsv" TOPIC_NO_DOWNSTREAM=1 TOPIC_NO_REVIEW=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
n=$((n+1)); [ "$(_tk create --domain crypto --title 'WAL 24小时涨48%，币安合约成交额7亿美元，现货与永续同步放量创三个月新高' --keywords 'WAL' --rc 纯行情-A定则 --note '回归:超长标题')" = "1" ] \
  && grep -qF $'\tlint:标题长度\t拦\tcreate\t' "$_K/h.tsv" || { echo "❌ topic.py(v3.7.22): 标题闸 FAIL 应记 check-hits「lint:标题长度 拦」: $(cat "$_K/h.tsv" 2>/dev/null)"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tk create --domain tradfi --title 'F5新品发布，FFIV盘中涨3.2%' --keywords 'FFIV' --rc 有诱因-多源 --note '低于5%仍建:回归')" = "0" ] \
  && grep -qF $'\ttradfi_floor\t豁免\tcreate\t10000090001\t' "$_K/h.tsv" || { echo "❌ topic.py(v3.7.22): 写入成功且备注用了「低于5%仍建」应记 tradfi_floor 豁免: $(cat "$_K/h.tsv" 2>/dev/null)"; fail=$((fail+1)); }
CHECK_HITS="$_K/h.tsv" ACTIONS="$_K/a.tsv" SNAPSHOTS="$_K/s.tsv" REJ="$_K/r.tsv" B0JSON="$_K/b0.json" "$D/log-action.sh" note 99990001 不存在的码 '回归' >/dev/null 2>&1
n=$((n+1)); grep -qF $'\tlog-action:rc非枚举\t拦\tnote\t99990001\t' "$_K/h.tsv" || { echo "❌ log-action.sh(v3.7.22): 拒写应同时记 check-hits「log-action:rc非枚举 拦」"; fail=$((fail+1)); }
n=$((n+1)); python3 - "$_K" <<'EOF' || { echo "❌ retro.py(v3.7.22): 减法候选四类判据不对(见上)"; fail=$((fail+1)); }
import os,sys,time,importlib.util
d=sys.argv[1]; now=time.time(); ms=lambda dd:int((now-dd*86400)*1000)
os.environ.update(CHECK_HITS=d+'/kh.tsv', GATE_USAGE=d+'/gu.tsv', GATES=d+'/nogates')
open(d+'/kh.tsv','w').write(f"{ms(40)}\tprice_only\t拦\tcreate\t-\tx\n{ms(2)}\tprice_only\t拦\tcreate\t-\tx\n{ms(2)}\ttradfi_floor\t拦\tcreate\t-\tx\n"
                            + ''.join(f"{ms(1)}\ttradfi_floor\t豁免\tcreate\t1\tx\n" for _ in range(3)))
s=importlib.util.spec_from_file_location('retro',os.path.expanduser('~/.trend-scout/retro.py')); r=importlib.util.module_from_spec(s); s.loader.exec_module(r)
E=lambda c,dd,i:{'ts':ms(dd),'eid':f'{c}{i}','cls':c,'tid':'-','text':'','src':'','day':''}
errs={f'a{i}':E('工具拦截·标题闸FAIL(标题长度)',1,i) for i in range(5)}
errs.update({f'b{i}':E('工具拦截·涨跌幅不符',1,i) for i in range(5)})
errs.update({'c0':E('复审挑战·其他',0.5,0)})
fixes={'工具拦截·涨跌幅不符':[{'ts':ms(3),'layer':'脚本','desc':''}],'复审挑战·其他':[{'ts':ms(5-i),'layer':'脚本','desc':''} for i in range(3)]}
out='\n'.join(r.prune(errs=errs,fixes=fixes,now=now))
ok=[('① 零拦截检查' in out and 'lint:疑问句' in out.split('① 零拦截检查')[1].split('\n')[0] and 'price_only' not in out.split('① 零拦截检查')[1].split('\n')[0]),
    '② tradfi_floor:拦 1 次、靠豁免过 3 次' in out, '③ 工具拦截·标题闸FAIL(标题长度):近 30 天拦 5 次' in out,
    '工具拦截·涨跌幅不符' not in out, '④ 复审挑战·其他:修了 3 次' in out]
open(d+'/kh.tsv','w').write(f"{ms(2)}\tprice_only\t拦\tcreate\t-\tx\n")
out2='\n'.join(r.prune(errs={},fixes={},now=now))
ok+=['① 检查计数第 2 天' in out2 and '零拦截检查' not in out2, '本晚无达标候选' in out2]
if not all(ok): print(ok); print(out); print(out2); sys.exit(1)
EOF

# scope1103:scatter 概念零命中=指纹失效,须判失败(此前报 ✅,主流标的白名单指纹失效无人发现)
_SW=$(mktemp); python3 -c "
import json,sys;d=json.load(open('$D/scatter-watch.json'))
[c.update(fingerprint='NEVER_MATCHES_XYZ') for c in d['concepts'] if c['name']=='主流标的白名单'];json.dump(d,open(sys.argv[1],'w'),ensure_ascii=False)" "$_SW"
n=$((n+1)); SCATTER_WATCH="$_SW" python3 "$D/scatter.py" >/dev/null 2>&1 && { echo "❌ scatter.py(scope1103): 概念零命中(指纹失效)应退出 1"; fail=$((fail+1)); }
n=$((n+1)); python3 "$D/scatter.py" | grep -q '主流标的白名单: 1 处定义' || { echo "❌ scatter.py(scope1103): 白名单指纹应命中 majors.json 一处"; fail=$((fail+1)); }

# retro1103b:币安 TradFi 股票永续(MVLL)不进币侧对账
_cb=$(mktemp); printf '%s' '[{"symbol":"MVLLUSDT","priceChangePercent":"-30.4","quoteVolume":"126000000","closeTime":9999999999999},{"symbol":"AKEUSDT","priceChangePercent":"-36.5","quoteVolume":"170000000","closeTime":9999999999999}]' > "$_cb"
_bm=$(cd "$D" && COVERAGE_BN="$_cb" COVERAGE_BN_EQUITY=MVLLUSDT python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);print(','.join(x[0] for x in c.bn_movers()))")
n=$((n+1)); [ "$_bm" = "AKE" ] || { echo "❌ coverage(retro1103b): 股票永续 MVLL 应剔除、AKE 保留,得 $_bm"; fail=$((fail+1)); }
rm -f "$_cb"

# retro1107:①下游「$HUT」带美元号不算错标(Hut 8 股票永续=等效) ②撤题闸拦截进 actions-rejected ③>7 天老题按台账建题日找得到 ④宏观定价读数算价格腿 ⑤TG 0 条不许 ✅
_R7=$(mktemp -d)
n=$((n+1)); _d7=$(cd "$D" && python3 -c "
import downstream as d
t={'domain':'tradfi','keywords':'比特币矿企,CIFR,HUT','original_title':'比特币矿企股反弹，CIFR收涨18%、HUT涨15%'}
print(d.judge(t,{'asset_type':'tradfi','asset_types':['\$HUT','CIFR'],'content':''})[0][0], d.judge(t,{'asset_type':'tradfi','asset_types':['\$MASK'],'content':''})[0][0])")
[ "$_d7" = "OK 错标" ] || { echo "❌ retro1107①: \$HUT 应 OK、\$MASK 应错标,得 $_d7"; fail=$((fail+1)); }
python3 - "$_R7" <<'EOF'
import json,sys,time,datetime as D
d=sys.argv[1]; now=D.datetime.now()
f=lambda h:(now-D.timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
json.dump({"next_crypto":90001,"next_tradfi":10000090003,"topics":[
 {"id":10000090001,"domain":"tradfi","title":"Expedia四季度指引偏弱，EXPE盘后跌8.2%","keywords":"EXPE","status":0,"created_at":f(48),"closed_ts":0},
 {"id":10000090002,"domain":"tradfi","title":"Expedia四季度指引偏弱，EXPE收跌14%","keywords":"EXPE","status":0,"created_at":f(24),"closed_ts":0},
 {"id":10000090009,"domain":"tradfi","title":"老题十天前","keywords":"OLD","status":0,"created_at":f(240),"closed_ts":0}]},open(d+'/c.json','w'),ensure_ascii=False)
open(d+'/ta.tsv','w').write(f"{int((time.time()-240*3600)*1000)}\tcreate\t10000090009\t有诱因-多源\tx\t-\n")
json.dump([],open(d+'/tb0.json','w'))
EOF
_t7(){ CONSOLE_FAKE="$_R7/c.json" ACTIONS="$_R7/ta.tsv" SNAPSHOTS="$_R7/ts.tsv" REJ="$_R7/tr.tsv" REJ_OK="$_R7/tok.tsv" UNLOGGED="$_R7/tu.tsv" B0JSON="$_R7/tb0.json" CHECK_HITS="$_R7/kh.tsv" TOPIC_NO_DOWNSTREAM=1 TOPIC_NO_REVIEW=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
n=$((n+1)); [ "$(_t7 cull --id 10000090001 --rc 重复-同标的 --note '回归:与10000090002同EXPE重复')" = "1" ] && grep -q 'cull	10000090001' "$_R7/tr.tsv" \
  || { echo "❌ retro1107②: 跨交易日同向撤题应拦且进 actions-rejected: $(cat "$_R7/tr.tsv" 2>/dev/null | cut -c1-120)"; fail=$((fail+1)); }
n=$((n+1)); _o7=$(cd "$D" && CONSOLE_FAKE="$_R7/c.json" ACTIONS="$_R7/ta.tsv" B0JSON="$_R7/tb0.json" python3 -c "
import console;c=console.Console();t=c.get(10000090009);print(t and t['id'])")
[ "$_o7" = "10000090009" ] || { echo "❌ retro1107③: 10 天前的题按台账 create 行应找得到,得 $_o7"; fail=$((fail+1)); }
n=$((n+1)); _m7=$(cd "$D" && python3 -c "
import lint
f=lambda t:[x[1] for x in lint.lint_title(t,'tradfi')]
print('双要素-缺价格' not in f('10月非农新增16.5万远超预期，12月加息概率升至近八成'), '双要素-缺价格' not in f('10年期美债收益率升至4.8%'), '双要素-缺价格' in f('日本央行加息至1%，日元走强'))")
[ "$_m7" = "True True True" ] || { echo "❌ retro1107④: 宏观定价腿判定得 $_m7"; fail=$((fail+1)); }
_C7=$(mktemp); printf '# mode=刷新\nTG探针或兜底\tTODO\n' > "$_C7"
n=$((n+1)); { CHECKLIST="$_C7" "$D/checklist.sh" mark TG探针或兜底 "✅(0:全源 news 无 TG 条目)" >/dev/null 2>&1 && grep -q '✅(0' "$_C7"; } && { echo "❌ retro1107⑤: TG 0 条记 ✅ 应拒"; fail=$((fail+1)); }
n=$((n+1)); { CHECKLIST="$_C7" "$D/checklist.sh" mark TG探针或兜底 "⚠️(0:全源 news 无 TG 条目)" >/dev/null 2>&1 && grep -q '⚠️(0' "$_C7"; } || { echo "❌ retro1107⑤b: TG 0 条记 ⚠️ 应写进注入的清单(CHECKLIST)"; fail=$((fail+1)); }
rm -rf "$_R7" "$_C7"
_W7=$(mktemp -d); mkdir -p "$_W7/references"; : > "$_W7/references/gates.md"; : > "$_W7/references/review-agent.md"; : > "$_W7/references/x.md.bak-1"
printf '## ① 用户点名\n## ② 团队打回率\n## ③ 撤题\n## ④ 复审员挑战\n## ⑤ 返工率\n## 规则体积\n## 规则卫生\n## ① 过期\n## ② 矛盾\n## ③ 被实践推翻\n## ④ 冗余\n## 行数体检\n- 散点总数 0\n排序建议\n' > "$_W7/w.md"
n=$((n+1)); RULES_DIR="$_W7" ACTIONS=/dev/null "$D/weekly-verify.sh" "$_W7/w.md" >/dev/null 2>&1 && { echo "❌ retro1107⑦: 周报缺「通读完成:」行应拦"; fail=$((fail+1)); }
echo '> 通读完成: SKILL.md 98 行｜gates.md 458｜review-agent.md 60｜channels.json 167' >> "$_W7/w.md"
n=$((n+1)); RULES_DIR="$_W7" ACTIONS=/dev/null "$D/weekly-verify.sh" "$_W7/w.md" >/dev/null 2>&1 || { echo "❌ retro1107⑦b: 通读行列全(.bak 不算)应放行: $(RULES_DIR="$_W7" ACTIONS=/dev/null "$D/weekly-verify.sh" "$_W7/w.md" | head -3)"; fail=$((fail+1)); }
rm -rf "$_W7"
n=$((n+1)); python3 - <<'EOF' || { echo "❌ retro1107⑥: 漏建·当轮拦下(🟢)不应进减法④"; fail=$((fail+1)); }
import importlib.util as u,os,time
s=u.spec_from_file_location('retro',os.path.expanduser('~/.trend-scout/retro.py'));r=u.module_from_spec(s);s.loader.exec_module(r)
now=time.time()*1000;ms=lambda d:int(now-d*86400000)
E=lambda c,dd,i:{'ts':ms(dd),'eid':f'{c}{i}','cls':c,'tid':'-','text':'','src':'','day':''}
errs={f'a{i}':E('漏建·当轮拦下',0.5,i) for i in range(4)}; errs.update({f'b{i}':E('下游错标',0.5,i) for i in range(2)})
fx=lambda c:[{'ts':ms(5-i),'layer':'脚本','desc':''} for i in range(3)]
out='\n'.join(r.prune(errs=errs,fixes={'漏建·当轮拦下':fx(1),'下游错标':fx(2)},now=now))
assert '④ 漏建·当轮拦下' not in out and '④ 下游错标' in out, out
EOF

# megacap1109(用户 11-09 定):市值前10超大盘股有诱因门槛 3%,其余单名仍 5%;名单读不到时全按 5%
_mc=$(cd "$D" && python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
f=lambda ti,k='':bool(t.tradfi_floor('tradfi',ti,'x',k))
print(f('黄仁勋承认婚外情、董事会启动独立调查，NVDA夜盘跌3.2%','NVDA,英伟达'), f('苹果下调指引，盘后跌2.6%','AAPL'), f('台积电10月营收创新高，TSM涨3.4%','TSM'),
      f('F5新品发布，FFIV盘中涨3.2%','FFIV'), f('Meta Platforms裁员，盘前跌4%','META'), f('AMD新品发布，盘中涨4.5%','AMD'))")
n=$((n+1)); [ "$_mc" = "False True False True False True" ] || { echo "❌ megacap1109: 超大盘≥3%放行/<3%拦、非超大盘<5%拦,得 $_mc"; fail=$((fail+1)); }
_mc2=$(cd "$D" && MEGACAP_JSON=/nonexistent python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
print(bool(t.tradfi_floor('tradfi','NVDA夜盘跌3.2%','x','NVDA')))")
n=$((n+1)); [ "$_mc2" = "True" ] || { echo "❌ megacap1109b: megacap.json 读不到时应回落 5% 线,得 $_mc2"; fail=$((fail+1)); }

# major1109(用户 11-09 定):BTC/ETH 纯行情不走 50% 线——24h BTC±5%/ETH±7%,或关口+阶段新高低(备注须「阶段高低已核」);对账按同线与 60 天新高低
_mj=$(cd "$D" && env -u TS_CRYPTO_LINE python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
import lint
f=lambda ti,n='x',k='':t.crypto_amp('纯行情-A定则','crypto',ti,n,k) is None
print(f('BTC 24小时跌6%，币安合约成交90亿美元'), f('BTC 24小时跌3%','x'), f('ETH 24小时跌6%','x'), f('ETH 24小时跌7.5%','x'),
      f('BTC凌晨一度跌破7.4万，创8月下旬以来新低','阶段高低已核:币安日线'), f('BTC凌晨一度跌破7.4万，创8月下旬以来新低','x'),
      f('ONE 24小时涨37%','x'), f('ONE 24小时涨61%','x'),
      [g for _,g,_,_ in lint.lint_title('BTC凌晨一度跌破7.4万，创8月下旬以来新低','crypto') if g.startswith('双要素')],
      [g for _,g,_,_ in lint.lint_title('某项目注册用户突破100万','crypto') if g.startswith('双要素')])")
n=$((n+1)); [ "$_mj" = "True False False True True False False True ['双要素-关口价格腿'] ['双要素-缺价格']" ] || { echo "❌ major1109: 主流币线判定得 $_mj"; fail=$((fail+1)); }
_KL=$(mktemp); python3 - "$_KL" <<'EOF'
import json,sys
def k(n,lo_last):
    rows=[[1790000000000+i*86400000,'0','80000','76000','78000'] for i in range(n)]
    rows[-1][3]=str(lo_last); return rows
json.dump({'BTC':k(62,73333),'ETH':k(62,76500)},open(sys.argv[1],'w'))
EOF
_mm=$(cd "$D" && COVERAGE_KLINES="$_KL" python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
print([(a,b) for a,b,_,_ in c.major_milestones()])")
n=$((n+1)); [ "$_mm" = "[('BTC', '新低')]" ] || { echo "❌ major1109b: BTC 跌破 60 天低点应报新低、ETH 未破不报,得 $_mm"; fail=$((fail+1)); }
_cb7=$(mktemp); printf '%s' '[{"symbol":"BTCUSDT","priceChangePercent":"-5.6","quoteVolume":"9000000000","closeTime":9999999999999},{"symbol":"ETHUSDT","priceChangePercent":"-6.0","quoteVolume":"5000000000","closeTime":9999999999999}]' > "$_cb7"
_bm7=$(cd "$D" && COVERAGE_BN="$_cb7" COVERAGE_BN_EQUITY=X python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);print(','.join(x[0] for x in c.bn_movers()))")
n=$((n+1)); [ "$_bm7" = "BTC" ] || { echo "❌ major1109c: BTC -5.6% 应进对账、ETH -6% 未过 7% 不进,得 $_bm7"; fail=$((fail+1)); }
rm -f "$_KL" "$_cb7"

# hot1111(用户 11-11 定「ZEC这种热点主流币大跌，可以留」):币安合约 24h 成交 ≥10 亿美元的加密币纯行情线 ±10%;非 COIN 永续(韩股/商品)不进币侧对账
_ht=$(cd "$D" && env -u TS_CRYPTO_LINE python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
f=lambda ti,n='x':t.crypto_amp('纯行情-A定则','crypto',ti,n) is None
print(f('ZEC 24小时跌14.8%','币安合约成交30亿美元,市值165亿美元'), f('ZEC 24小时跌14.8%','币安合约成交30亿美元'), f('ZEC 24小时跌8%','币安合约成交30亿美元,市值165亿美元'), f('XYZ 24小时跌15%','币安合约成交5亿美元,市值20亿美元'), f('INIT 24小时涨16%','币安合约成交15亿美元,市值0.5亿美元'))")
n=$((n+1)); [ "$_ht" = "True False False False False" ] || { echo "❌ hot1111a: 热点主流币线判定得 $_ht"; fail=$((fail+1)); }
_cbh=$(mktemp); printf '%s' '[{"symbol":"ZECUSDT","priceChangePercent":"-14.9","quoteVolume":"3000000000","closeTime":9999999999999},{"symbol":"SOLUSDT","priceChangePercent":"-9.0","quoteVolume":"1800000000","closeTime":9999999999999},{"symbol":"XYZUSDT","priceChangePercent":"-15.0","quoteVolume":"500000000","closeTime":9999999999999},{"symbol":"SKHYNIXUSDT","priceChangePercent":"12.0","quoteVolume":"1400000000","closeTime":9999999999999},{"symbol":"INITUSDT","priceChangePercent":"16.2","quoteVolume":"1500000000","closeTime":9999999999999}]' > "$_cbh"
_mch=$(mktemp); printf '%s' '{"ZEC":16500000000,"INIT":54000000}' > "$_mch"
_bmh=$(cd "$D" && COVERAGE_BN="$_cbh" COVERAGE_MCAP="$_mch" COVERAGE_BN_EQUITY=SKHYNIXUSDT python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);print(','.join(x[0] for x in c.bn_movers()), c.HOT_VOL, c.HOT_LINE, c.HOT_MCAP)")
n=$((n+1)); [ "$_bmh" = "ZEC 1000000000.0 10.0 1000000000.0" ] || { echo "❌ hot1111b: ZEC(成交30亿 -14.9% 市值165亿)应进对账,SOL(-9%)/XYZ(成交5亿)/SKHYNIX(非币)/INIT(市值0.5亿)不进,得 $_bmh"; fail=$((fail+1)); }
_bmu=$(cd "$D" && COVERAGE_BN="$_cbh" COVERAGE_BN_EQUITY=SKHYNIXUSDT python3 -W ignore -c "import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c);r=','.join(x[0] for x in c.bn_movers());print(r, any('市值取不到' in b for b in c.BLIND))")
n=$((n+1)); [ "$_bmu" = "ZEC,INIT True" ] || { echo "❌ hot1111c: 市值取不到时热点币应按过线报并记半盲,得 $_bmu"; fail=$((fail+1)); }
rm -f "$_cbh" "$_mch"

# retro1111:①亚洲指数弃建只认备注日期=今天(台股 11-10 弃建备注引了错读数 +7.6%,盖住 11-11 收涨 3.6%)②restore 可用「用户点名」
_r11=$(cd "$D" && COVERAGE_NOW_MS=1794379446000 python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
old='弃建|台股加权|Yahoo ^TWII 显示+7.6%系前收取错;按11-09收算今收=+2.5%,未过±3%线|2026-11-10'
new='弃建|台股加权|今收+3.3%,测试|2026-11-11'
print(c.covered('^TWII',{'台股'},[],[old],pct=3.6,line=3.0,idx=True)[0], c.covered('^TWII',{'台股'},[],[new],pct=3.6,line=3.0,idx=True)[0], c.covered('SPY',{'标普'},[],['弃建|SPY|盘中-2.5%|2026-11-10'],pct=-2.6,line=2.0,idx=True)[0])")
n=$((n+1)); [ "$_r11" = "None 弃建 弃建" ] || { echo "❌ retro1111①: 亚洲指数弃建应只认当天备注(美股不受影响),得 $_r11"; fail=$((fail+1)); }
_R11=$(mktemp -d)
ACTIONS="$_R11/a.tsv" SNAPSHOTS="$_R11/s.tsv" REJ="$_R11/r.tsv" bash "$D/log-action.sh" restore 99990001 用户点名 "测试:用户点名恢复,回归用例" >/dev/null 2>&1
n=$((n+1)); grep -q '用户点名' "$_R11/a.tsv" 2>/dev/null || { echo "❌ retro1111②: restore+用户点名 应放行"; fail=$((fail+1)); }
rm -rf "$_R11"

# weight1112(用户 11-12 批):①判档三修——DIA 词边界/点名公司认发行价与估值金额/加密域认美股代码 ②系统建美股题窗口短且属 A/B 档→机审⑤提示自建承接
_w12=$(cd "$D" && python3 -W ignore -c "
import sys;sys.path.insert(0,'.');import weight as W
c=lambda d,t,k='':W.classify(d,t,k)[0]
print(c('tradfi','MEDIA板块走强，PARA涨8%'),c('tradfi','印度Sensex收跌3%，INDIA ETF跌2.8%'),c('tradfi','董事会据报准备罢免黄仁勋，NVIDIA Corporation盘后跌7.3%','NVDA'),c('tradfi','美股三大指数收涨，SPY涨1.3%、QQQ涨2.3%'),c('crypto','MSCI将Strategy剔出指数，MSTR夜盘跌2.2%'),c('crypto','Coinbase永续新增GRAM、GRASS、QNT、ZRO','GRAM'),c('tradfi','FT称Anthropic拟上调发行价，估值或超1.5万亿美元'),c('tradfi','Anthropic发布新模型，估值传闻不改'))")
n=$((n+1)); [ "$_w12" = "B C A A B C A C" ] || { echo "❌ weight1112①: 判档得 $_w12"; fail=$((fail+1)); }
_s12=$(cd "$D" && python3 -W ignore -c "
import sys;sys.path.insert(0,'.');import lint
N=1794448000000
a=lint.short_window({'domain':'tradfi','created_at':'2026-11-12 08:02:36','closed_ts':1794441922537,'title':'董事会据报准备罢免黄仁勋，NVIDIA Corporation盘后跌7.3%','keywords':'NVDA'},N) or ''
b=lint.short_window({'domain':'tradfi','created_at':'2026-11-12 08:02:36','closed_ts':1794441922537,'title':'拟通过优质贷款融资，CoreWeave Inc.盘后跌6.8%','keywords':'CRWV'},N) or ''
d=lint.short_window({'domain':'tradfi','created_at':'2026-11-12 09:48:20','closed_ts':1794534500000,'title':'CoreWeave重燃AI交易，费半收涨5.7%'},N)
print('自建' in a, '不必承接' in b, d is None)")
n=$((n+1)); [ "$_s12" = "True True True" ] || { echo "❌ weight1112②: 窗口短提示得 $_s12"; fail=$((fail+1)); }

# retro1112(11-12 每晚复盘):①大宗/宏观资产不进 tradfi 单名 5% 门槛(金价两次靠例外放行) ②--pct 写成 bn:/yahoo: 时提示先跑 pct.py 拿数字
_r12=$(cd "$D" && python3 -W ignore -c "
import sys;sys.path.insert(0,'.');import topic,pct
a=topic.tradfi_floor('tradfi','美联储加息押注升温，COMEX金价跌2.8%失守3900美元','x')
b=topic.tradfi_floor('tradfi','订单不及预期，ABCD跌2.8%','x')
c=pct.check('JCT 24小时跌50%',['JCT=bn:JCTUSDT'])
print(a is None, b is not None, 'pct.py bn' in c[0][1])")
n=$((n+1)); [ "$_r12" = "True True True" ] || { echo "❌ retro1112: 大宗豁免/--pct 提示得 $_r12"; fail=$((fail+1)); }

# monday1109(用户 11-09 定):美股期货进指数对账线(ES 2%/NQ 2.5%/YM 2%);首扫通道含期货夜盘与周一前瞻
_fq=$(mktemp); printf '%s' '{"ES=F":[7200,7402,"FUTURE"],"NQ=F":[27000,27085,"FUTURE"]}' > "$_fq"
_fu=$(cd "$D" && COVERAGE_QUOTES="$_fq" python3 -W ignore -c "
import importlib.util as u;s=u.spec_from_file_location('c','coverage.py');c=u.module_from_spec(s);s.loader.exec_module(c)
print(sorted(k for k in ('ES=F','NQ=F','YM=F') if k in c.IDX), c.IDX['ES=F'][0], c.IDX['NQ=F'][0])")
n=$((n+1)); [ "$_fu" = "['ES=F', 'NQ=F', 'YM=F'] 2.0 2.5" ] || { echo "❌ monday1109: 期货应进 IDX,得 $_fu"; fail=$((fail+1)); }
n=$((n+1)); python3 -c "
import json;d=json.load(open('$D/channels.json'));k={c['key']:c['mode'] for c in d['channels']}
assert k.get('美股期货+夜盘')=='首扫' and k.get('本周前瞻(周一)')=='首扫'" || { echo "❌ monday1109b: channels.json 缺首扫通道 美股期货+夜盘/本周前瞻(周一)"; fail=$((fail+1)); }
rm -f "$_fq"

# weight1109(用户 11-09 定 v3.7.30,当日 review 修订):四档全部非负(score≤0 会从榜上消失);A 美股宏观大事件/B 核心池·板块·宏观资产/C 主流币·亚股·其余美股/D 小币
_wc=$(cd "$D" && python3 -c "
import weight
for d,t,k,n in [('tradfi','美国10月CPI将于周二21:30公布，前值3.7%','美国CPI',''),('tradfi','AI监管担忧拖累美股，标普500收跌4.4%、道指跌3.4%','',''),
  ('tradfi','黄仁勋承认婚外情、董事会启动独立调查，NVDA夜盘跌3.2%','NVDA',''),('tradfi','Wayfair第三季度增长创疫情后最强，CPNG涨12%、W涨11%','零售,CPNG,W,AMZN',''),
  ('tradfi','电池股重挫，三星SDI收跌11.3%、LG新能源跌5.8%','三星SDI',''),('tradfi','Anthropic本周将启动IPO路演，拟下周上市','Anthropic',''),
  ('crypto','BTC凌晨一度跌破7.4万，创8月下旬以来新低','BTC',''),('crypto','JCT 24小时涨254%，币安合约成交19亿美元','JCT',''),
  ('crypto','FinCEN切断MEXC美国金融接入，指其涉160亿美元交易','MEXC',''),('crypto','纳斯达克批准INJ质押ETF上市，INJ报8.02美元','INJ',''),
  ('crypto','b14g称5至7天内启动偿还被盗CORE，CORE跌2.3%','CORE','')]:
    print(weight.classify(d,t,k,n)[0],end='')")
n=$((n+1)); [ "$_wc" = "AAABCACDCCD" ] || { echo "❌ weight1109: 判档应为 AAABCACDCCD(CPI/标普/NVDA→A,Wayfair 多股→B,三星→C,Anthropic IPO→A,BTC→C,JCT→D,FinCEN/ETF→C,被盗<1亿→D),得 $_wc"; fail=$((fail+1)); }
# review 修订用例:杂股归 C、政策次切面 B、主切面 A、建题备注带 .T 判亚股、核心池 B、宏观资产 B、央行决议 A、中国 CPI 不算美国宏观、英文逗号公司名、「每股2美元」不算宏观资产、前 20 币与头部机构 C、币安合约成交额与币安上线不算头部机构
_wc2=$(cd "$D" && python3 -c "
import weight
for d,t,k,n in [('tradfi','Black Rifle Coffee收跌23%','BRCC',''),('tradfi','民主党拿下国会，DJT收跌25%','DJT',''),
  ('tradfi','民主党横扫国会压低美元，金价重回4000美元、白银涨4.8%','黄金',''),('tradfi','激进基金Farallon入股，雅玛多收涨11.5%','雅玛多','Yahoo 9064.T 收盘'),
  ('tradfi','美国商业收入未达高预期，PLTR盘前跌8.1%','PLTR',''),('tradfi','金价创历史新高，报4200美元','黄金',''),
  ('tradfi','日本央行加息25基点，日经跌2%','日本央行',''),('tradfi','国家统计局公布10月CPI同比0.7%，沪深300跌1%','CPI',''),
  ('tradfi','InP激光器产能售罄且客户订单延至远期，Coherent, Inc.涨12%','COHR',''),('tradfi','LS Power据报提议每股2美元收购，EVGO收涨47%','EVGO',''),
  ('crypto','SUI 24小时涨55%，币安合约成交3亿美元','SUI',''),('crypto','参议员索要TETHER调查材料，合作期限至2027年1月4日','TETHER',''),
  ('crypto','币安Alpha上线XYZ，24小时涨80%','XYZ',''),('tradfi','特朗普将于周三公布对华关税新政','关税',''),
  ('tradfi','日本央行干预汇市，日元急涨2%','日元',''),('tradfi','欧元兑美元跌破1.05，创两年新低','欧元',''),('tradfi','韩国国会通过加密法案，KOSPI涨1%','KOSPI','')]:
    print(weight.classify(d,t,k,n)[0],end='')")
n=$((n+1)); [ "$_wc2" = "CBACBBACBCCCDAABC" ] || { echo "❌ weight1109e: review 修订判档应为 CBACBBACBCCCDAABC(末四条:无价格腿的政策预告→A、日本央行干预→A、汇率→B、韩国政策题→C),得 $_wc2"; fail=$((fail+1)); }
_wneg=$(cd "$D" && python3 -c "import weight;print(min(weight.tier_weight(x) for x in 'ABCD')>0)")
n=$((n+1)); [ "$_wneg" = "True" ] || { echo "❌ weight1109g: 四档权重必须全部>0(实测 score≤0 的题会从榜上消失)"; fail=$((fail+1)); }
_W9=$(mktemp -d); echo '[]' > "$_W9/tb0.json"
_tw9(){ CONSOLE_FAKE="$_W9/c.json" ACTIONS="$_W9/ta.tsv" SNAPSHOTS="$_W9/ts.tsv" REJ="$_W9/tr.tsv" REJ_OK="$_W9/tok.tsv" UNLOGGED="$_W9/tu.tsv" B0JSON="$_W9/tb0.json" WEIGHTS_TIER="$_W9/wt.tsv" TOPIC_NO_DOWNSTREAM=1 TOPIC_NO_REVIEW=1 python3 "$D/topic.py" "$@" >/dev/null 2>&1; echo $?; }
_wA=$(cd "$D" && python3 -c "import weight;print(format(weight.tier_weight('A'),'g'))")
n=$((n+1)); [ "$(_tw9 create --domain tradfi --title '美国10月CPI将于周二21:30公布，前值3.7%' --keywords '美国CPI,通胀' --rc 预告题 --note '回归:建题带权重')" = "0" ] \
  && python3 -c "import json,sys;t=json.load(open('$_W9/c.json'))['topics'][-1];sys.exit(0 if t.get('score_weight')==$_wA else 1)" && grep -q "权重:A+$_wA" "$_W9/ta.tsv" \
  && awk -F'\t' -v id="$(python3 -c "import json;print(json.load(open('$_W9/c.json'))['topics'][-1]['id'])")" '$2==id && $3=="A" && $4=="auto"' "$_W9/wt.tsv" | grep -q . \
  || { echo "❌ weight1109b: CPI 预告题建题应传 score_weight=A 档值、台账备注带「权重:A+$_wA」、weights-tier.tsv 记 auto 档"; fail=$((fail+1)); }
n=$((n+1)); [ "$(_tw9 create --domain crypto --title 'JCT 24小时涨254%，币安合约成交19亿美元' --keywords 'JCT' --rc 纯行情-A定则 --note '回归:人工档无理由' --tier A)" != "0" ] \
  || { echo "❌ weight1109c: --tier 不带 --tier-why 应拦"; fail=$((fail+1)); }
_now9=$(python3 -c 'import time;print(int(time.time()*1000))')
cat > "$_W9/sb0.json" <<EOF9
{"fetched_at":"$(date '+%Y-%m-%dT%H:%M:%S')","topics":[
 {"id":1,"domain":"crypto","status":0,"title":"JCT 24小时涨254%","keywords":"JCT","score":250,"score_weight":1,"closed_ts":$((_now9+3600000))},
 {"id":2,"domain":"tradfi","status":0,"title":"SHOP收跌8.7%","keywords":"SHOP","score":700,"score_weight":200,"closed_ts":$((_now9-3600000))},
 {"id":3,"domain":"crypto","status":0,"title":"AKE 24小时涨89%","keywords":"AKE","score":100,"score_weight":1,"closed_ts":$((_now9+3600000))},
 {"id":4,"domain":"crypto","status":3,"title":"VLX资格查询开放","keywords":"VLX","score":1,"score_weight":1,"closed_ts":$((_now9+3600000))},
 {"id":5,"domain":"tradfi","status":0,"title":"存储芯片股普跌，KIOXIA收跌16%、SANKEN跌9%","keywords":"x","score":90,"score_weight":1,"closed_ts":$((_now9+3600000))}]}
EOF9
printf '%s\t3\tA\tmanual\t回归:大热点\n%s\t5\tC\tauto\t亚股(建题备注9064.T)\n' "$_now9" "$_now9" > "$_W9/wt.tsv"
_ws=$(cd "$D" && B0JSON="$_W9/sb0.json" WEIGHTS_TIER="$_W9/wt.tsv" python3 -c "
import importlib.util as u;s=u.spec_from_file_location('w','weight-sync.py');m=u.module_from_spec(s);s.loader.exec_module(m)
print(' '.join(f'{t[\"id\"]}:{tier}:{k}' for t,w,tier,_,k in m.plan(m._load_b0(refetch=False))))")
n=$((n+1)); [ "$_ws" = "1:D:now 3:A:manual 5:C:auto" ] || { echo "❌ weight1109d: 同步计划应为 只管在期上线题(过期/隐藏不管)、记过档的以记档为准(人工 A、建题时亚股 C)、没记过的现判,得 $_ws"; fail=$((fail+1)); }
rm -rf "$_W9"

# retro1109(11-09 复盘):②c 开盘后把盘前/夜盘口径换盘中/收盘不受 8h 射程闸拦;换成别的事件或超 24h 仍拦
_oc=$(cd "$D" && python3 -c "
import importlib.util as u,time;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
m=time.mktime(time.strptime('2026-11-09 23:00:00','%Y-%m-%d %H:%M:%S'))*1000
o={'id':1,'created_at':'2026-11-09 10:38:36','title':'黄仁勋承认婚外情、董事会启动独立调查，NVDA盘前跌4.5%'}
a=t.out_of_scope(o,'改口径-时段','',m,new_title='黄仁勋承认婚外情、董事会启动独立调查，NVDA盘中跌5%') is None
b=t.out_of_scope(o,'改归因','',m,new_title='英伟达发布新品，NVDA盘中跌5%') is not None
c=t.out_of_scope(dict(o,created_at='2026-11-08 10:38:36'),'改口径-时段','',m,new_title='黄仁勋…，NVDA盘中跌5%') is not None
d=t.out_of_scope(o,'改口径-时段','',m,new_title='黄仁勋…，NVDA夜盘跌5%') is not None
print(a,b,c,d)")
n=$((n+1)); [ "$_oc" = "True True True True" ] || { echo "❌ retro1109: ②c 盘前→盘中改口径应放行,改归因/超24h/仍是夜盘应拦,得 $_oc"; fail=$((fail+1)); }

# ── arch1110(11-10 架构 review,用户「做」):回归不污染查闸计数 / 下游错标误报 / 撞名表 / 批量预检 / 最接近撤因码 ──────────────
_A=$(mktemp -d)
# ① 标题里紧贴中文的代码要能抽出来(VRT涨9.6%);AI/ETF 这类缩写不当标的
printf '%s' '[{"title":"AI power stocks surge","asset_type":"tradfi","asset_types":["VRT"],"content":"x"},{"title":"AI sector up","asset_type":"tradfi","asset_types":["AI"],"content":"x"},{"title":"Crypto stocks fall","asset_type":"tradfi","asset_types":["ROBINHOOD"],"content":"x"}]' > "$_A/feed.json"
printf '%s' '[{"id":1,"domain":"tradfi","status":0,"title":"AI电力设备股大涨，BE收涨12%、VRT涨9.6%","title_en":"AI power stocks surge","keywords":"GE,Vertiv,电力设备"},{"id":2,"domain":"tradfi","status":0,"title":"AI板块走强，XYZ收涨12%","title_en":"AI sector up","keywords":"XYZ"},{"id":3,"domain":"tradfi","status":0,"title":"加密概念股收跌，HOOD跌10%","title_en":"Crypto stocks fall","keywords":"加密概念股"}]' > "$_A/tps.json"
_dsa(){ DOWNSTREAM_FEED="$_A/feed.json" DOWNSTREAM_TOPICS="$_A/tps.json" DOWNSTREAM_LOG="$_A/ds.log" DS_CLASH="$_A/clash.tsv" DS_NAMES="$_A/names.json" python3 "$D/downstream.py" "$@" 2>&1; }
echo '{}' > "$_A/names.json"
_d1=$(_dsa --ids 1,2,3)
n=$((n+1)); echo "$_d1" | grep -q '^✔ 1 ' || { echo "❌ arch1110[错标误报]: 标题明写 VRT(紧贴中文)、下游挂 VRT 应判 OK(10000003686 误报): $_d1"; fail=$((fail+1)); }
n=$((n+1)); echo "$_d1" | grep -q '2 .*错标: 下游挂到 AI' || { echo "❌ arch1110[缩写]: 标题里的 AI 不是标的,下游挂到 AI 仍应报错标"; fail=$((fail+1)); }
n=$((n+1)); echo "$_d1" | grep -q '3 .*错标: 下游挂到 ROBINHOOD' || { echo "❌ arch1110[等效]: 没登记等效时 ROBINHOOD 应报错标"; fail=$((fail+1)); }
_dsa equiv ROBINHOOD HOOD "回归:代币化股票等效" >/dev/null
n=$((n+1)); _dsa --ids 3 | grep -q '^✔ 3 ' || { echo "❌ arch1110[等效]: 登记 ROBINHOOD=HOOD 后应判 OK"; fail=$((fail+1)); }
# ② 撞名表:错标时自动定位触发词(整词 Lab→LAB、前缀 FERG→FER);建题前关键词命中拦、只在标题里出现不拦、撞名已核放行、题本身说的就是该符号不拦
printf '%s' '[{"title":"Rocket Lab Q3 loss","asset_type":"tradfi","asset_types":["LAB"],"content":"x"},{"title":"Ferguson beats","asset_type":"tradfi","asset_types":["FER"],"content":"x"}]' > "$_A/feed.json"
printf '%s' '[{"id":11,"domain":"tradfi","status":0,"title":"Rocket Lab三季度亏损超预期，RKLB夜盘跌7%","title_en":"Rocket Lab Q3 loss","keywords":"RKLB,Rocket Lab"},{"id":12,"domain":"tradfi","status":0,"title":"弗格森三季报强劲，FERG收涨11%","title_en":"Ferguson beats","keywords":"FERG,弗格森"}]' > "$_A/tps.json"
_dsa --ids 11,12 >/dev/null
n=$((n+1)); { grep -q $'\tLAB\tLAB\t整词' "$_A/clash.tsv" && grep -q $'\tFERG\tFER\t前缀' "$_A/clash.tsv"; } || { echo "❌ arch1110[撞名表]: 错标后应自动登记 LAB→LAB(整词)、FERG→FER(前缀): $(cat "$_A/clash.tsv" 2>/dev/null)"; fail=$((fail+1)); }
_dc=$(cd "$D" && DS_CLASH="$_A/clash.tsv" python3 -c "
import importlib.util as u;s=u.spec_from_file_location('t','topic.py');t=u.module_from_spec(s);s.loader.exec_module(t)
T='Rocket Lab三季度亏损超预期，RKLB夜盘跌7%'
print(t.ds_clash(T,['RKLB','Rocket Lab']) is not None, t.ds_clash(T,['RKLB','火箭实验室']) is None,
      t.ds_clash(T,['RKLB','Rocket Lab'],'撞名已核:回归') is None, t.ds_clash('LAB 24小时涨60%',['LAB']) is None,
      t.ds_clash('弗格森三季报强劲',['FERG','弗格森']) is not None)" 2>/dev/null | tail -1)
n=$((n+1)); [ "$_dc" = "True True True True True" ] || { echo "❌ arch1110[撞名表]: 关键词命中应拦/仅标题不拦/撞名已核放行/本题即该符号不拦/前缀词应拦,得 $_dc"; fail=$((fail+1)); }
echo '[]' > "$_A/tb0.json"
_tpa(){ CONSOLE_FAKE="$_A/c.json" ACTIONS="$_A/ta.tsv" SNAPSHOTS="$_A/ts.tsv" REJ="$_A/tr.tsv" REJ_OK="$_A/tok.tsv" UNLOGGED="$_A/tu.tsv" B0JSON="$_A/tb0.json" CHECK_HITS="$_A/kh.tsv" DS_CLASH="$_A/clash.tsv" TS_NO_B0CHECK=1 TOPIC_NO_DOWNSTREAM=1 python3 "$D/topic.py" "$@" 2>&1; }
_tpa create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.8%' --keywords 'RKLB,Rocket Lab' --rc 有诱因-多源 --note '回归:撞名表应在写看板前拦' --pct 'RKLB=59.18/64.22' >/dev/null
n=$((n+1)); { [ ! -s "$_A/ta.tsv" ] && [ ! -s "$_A/c.json" ] && grep -q $'\tds_clash\t拦' "$_A/kh.tsv"; } || { echo "❌ arch1110[撞名表]: 关键词含 Rocket Lab(曾挂到 LAB)建题应被拦,看板与台账不动"; fail=$((fail+1)); }
# ③ 误报更正:登记后该题此前的错标行不计入资格线与每晚复盘;更正之后又错标照算
_n1=$(python3 -c 'import time;print(int(time.time()*1000))')
printf '%s\t\t9001\t错标\tx\n%s\t\t9001\t误报更正\t回归\n%s\t\t9002\t错标\ty\n' "$((_n1-3000))" "$((_n1-2000))" "$((_n1-1000))" > "$_A/d.tsv"
_qf=$(BLIND_AUDIT=/dev/null DOWNSTREAM_LOG="$_A/d.tsv" UNLOGGED=/dev/null CHECKLOG=/dev/null CHECKLIST_CUR=/dev/null LARK_LOG=/dev/null ACTIONS=/dev/null python3 -c "import sys;sys.path.insert(0,'$D');import qualify;r=qualify.check(int(sys.argv[1])-3600000,int(sys.argv[1])+1);print([x[2] for x in r if x[0]=='下游错标'][0])" "$_n1" 2>/dev/null)
n=$((n+1)); echo "$_qf" | grep -q '^1 题(9002)' || { echo "❌ arch1110[误报更正]: 资格线应只剩 9002 一题,得 $_qf"; fail=$((fail+1)); }
_rf=$(cd "$D" && ACTIONS=/dev/null REJ=/dev/null UNLOGGED=/dev/null DOWNSTREAM_LOG="$_A/d.tsv" COVERAGE_LOG=/dev/null python3 -c 'import retro; print(",".join(e[3] for e in retro.gather() if e[2]=="下游错标"))' 2>/dev/null)
n=$((n+1)); [ "$_rf" = "9002" ] || { echo "❌ arch1110[误报更正]: 每晚复盘的下游错标应只剩 9002,得 $_rf"; fail=$((fail+1)); }
# ④ 批量预检:一条命令的多处拦截一次列全;不写看板、不落账、不进拒写留痕;检查计数带「预检:」
rm -f "$_A/kh.tsv" "$_A/tr.tsv"; : > "$_A/empty.tsv"
cat > "$_A/plan.txt" <<'PLANEOF'
# 注释行跳过
create --domain tradfi --title 'Neutron首飞推迟至2027年并且之后再度延期到更晚的时间，RKLB收跌7.9%' --keywords 'RKLB,火箭实验室' --rc 有诱因-多源 --note '回归:批量预检两处都该列出' --pct 'RKLB=59.18/64.22'
topic.py create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.8%' --keywords 'RKLB,火箭实验室' --rc 有诱因-多源 --note '回归:批量预检这条应通过' --pct 'RKLB=59.18/64.22'
PLANEOF
_ck=$(DS_CLASH="$_A/empty.tsv" _tpa check "$_A/plan.txt"); _ckrc=$?
n=$((n+1)); { echo "$_ck" | grep -q '标题闸FAIL' && echo "$_ck" | grep -q '涨跌幅不符' && echo "$_ck" | grep -q '^✔ #2 ' && echo "$_ck" | grep -q 'CHECK: 条数=2 通过=1 被拦=1'; } \
  || { echo "❌ arch1110[批量预检]: 第 1 条应同时列出标题闸与涨跌幅两处、第 2 条通过: $_ck"; fail=$((fail+1)); }
n=$((n+1)); { [ ! -s "$_A/ta.tsv" ] && [ ! -s "$_A/c.json" ] && [ ! -s "$_A/tr.tsv" ] && grep -q $'\t预检:create\t' "$_A/kh.tsv"; } \
  || { echo "❌ arch1110[批量预检]: 预检不得写看板/台账/拒写留痕,检查计数应带「预检:」"; fail=$((fail+1)); }
# ⑤ 撤因码写错时给最接近的合法码
echo '[{"id":9811,"domain":"tradfi","title":"X收跌7.9%","keywords":"X","status":0,"closed_ts":9999999999999}]' > "$_A/b0.json"
_nr=$(ACTIONS="$_A/la.tsv" SNAPSHOTS="$_A/ls.tsv" REJ="$_A/lr.tsv" REJ_OK="$_A/lok.tsv" UNLOGGED="$_A/lu.tsv" B0JSON="$_A/b0.json" "$D/log-action.sh" cull 9811 双要素-缺价格 "回归:撤因码写错应给最接近的" 2>&1)
n=$((n+1)); echo "$_nr" | grep -q '最接近的合法码: .*缺价格腿' || { echo "❌ arch1110[最接近码]: 「双要素-缺价格」应提示 缺价格腿"; fail=$((fail+1)); }
rm -rf "$_A"
# ⑥ 守卫:整套回归跑完,生产 gate-usage.tsv 不得多出回归自己的查询(回归固定会搜一次「价格」)
n=$((n+1)); _GU1=$(grep -c $'\tgrep\t价格$' "$_GU_PROD" 2>/dev/null); [ "${_GU1:-0}" = "$_GUG0" ] || { echo "❌ arch1110[查闸计数]: 回归往生产 gate-usage.tsv 写了查询(退役判据会失真)——GATE_USAGE 必须指向临时文件"; fail=$((fail+1)); }

# ── mirror1110(11-10 用户「先做3、4」):脚本/用例/配置镜像进规则仓库 repo-sync.py ──────────────
#   沙箱里没有这个脚本(只在本机用),不存在就整段跳过、不计数。
if [ -f "$D/repo-sync.py" ]; then
_M=$(mktemp -d); mkdir -p "$_M/ts/tests/sub" "$_M/ts/__pycache__"
echo 'print(1)' > "$_M/ts/a.py"; echo 'echo hi' > "$_M/ts/b.sh"; ln -s a.py "$_M/ts/a_link.py"
echo '{}' > "$_M/ts/majors.json"; echo '{"chat":"x"}' > "$_M/ts/lark.json"; echo 'x' > "$_M/ts/run-auto.sh"
echo 'old' > "$_M/ts/a.py.bak-pre-x"; printf '1\t2\n' > "$_M/ts/actions.tsv"; echo '{}' > "$_M/ts/b0-latest.json"
echo 'case' > "$_M/ts/tests/sub/c.tsv"; echo 'old' > "$_M/ts/tests/c.tsv.bak-1"; echo x > "$_M/ts/__pycache__/a.pyc"
_rs(){ TS_DIR="$_M/ts" TS_MIRROR="$_M/mir" python3 "$D/repo-sync.py" "$@"; }
_s1=$(_rs snapshot 2>&1); _ls=$(cd "$_M/mir" 2>/dev/null && find . \( -type f -o -type l \) | sort | tr '\n' ' ')
n=$((n+1)); [ "$_ls" = "./a.py ./a_link.py ./b.sh ./majors.json ./tests/sub/c.tsv " ] || { echo "❌ mirror1110①: 只该镜像 代码+用例+登记的配置;台账/缓存/.bak/飞书配置/run-auto 不进: [$_ls] $_s1"; fail=$((fail+1)); }
n=$((n+1)); [ -L "$_M/mir/a_link.py" ] && [ "$(readlink "$_M/mir/a_link.py")" = "a.py" ] || { echo "❌ mirror1110②: 软链应原样保留为软链"; fail=$((fail+1)); }
n=$((n+1)); _rs status | grep -q '^MIRROR: 文件=5 一致=5 改动未入库=0 新文件未入库=0 仓库多出=0' || { echo "❌ mirror1110③: 刚 snapshot 完应全一致且退出 0: $(_rs status | head -1)"; fail=$((fail+1)); }
echo 'print(2)' > "$_M/ts/a.py"; echo 'n' > "$_M/ts/new.py"; rm "$_M/ts/b.sh"; echo '# 说明' > "$_M/mir/README.md"
_s2=$(_rs status); _r2=$?
n=$((n+1)); [ "$_r2" -eq 1 ] && echo "$_s2" | grep -q '改动未入库=1 新文件未入库=1 仓库多出=1' && echo "$_s2" | grep -q $'改动\ta.py' || { echo "❌ mirror1110④: 改一个/加一个/删一个应各报 1 且退出 1(README 不算多出): $_s2"; fail=$((fail+1)); }
_rs snapshot >/dev/null 2>&1
n=$((n+1)); [ ! -e "$_M/mir/b.sh" ] && [ -f "$_M/mir/README.md" ] && [ "$(cat "$_M/mir/a.py")" = 'print(2)' ] && _rs status >/dev/null || { echo "❌ mirror1110⑤: 再 snapshot 应带上改动、删掉本机已无的、保留 README"; fail=$((fail+1)); }
# 仓库是公开的:含飞书 id 的文件一个都不拷(id 运行时拼出来,免得本文件自己被拦)
_FID="oc""_$(printf '0123456789abcdef01234567')"; echo "chat=$_FID" > "$_M/ts/leak.py"
_s3=$(_rs snapshot 2>&1); _r3=$?
n=$((n+1)); [ "$_r3" -eq 2 ] && echo "$_s3" | grep -q $'leak.py\t飞书' && [ ! -e "$_M/mir/leak.py" ] && ! echo "$_s3" | grep -q "$_FID" || { echo "❌ mirror1110⑥: 含飞书 id 应退出 2、不拷、不打印内容"; fail=$((fail+1)); }
rm "$_M/ts/leak.py"; echo 'broken' > "$_M/ts/a.py"; rm "$_M/ts/majors.json"
_rs restore --missing >/dev/null 2>&1
n=$((n+1)); [ -f "$_M/ts/majors.json" ] && [ "$(cat "$_M/ts/a.py")" = 'broken' ] || { echo "❌ mirror1110⑦: restore --missing 只补缺的,已有的(哪怕不同)不覆盖"; fail=$((fail+1)); }
_rs restore a.py >/dev/null 2>&1
n=$((n+1)); [ "$(cat "$_M/ts/a.py")" = 'print(2)' ] && ! _rs restore nosuch.py >/dev/null 2>&1 || { echo "❌ mirror1110⑧: restore 点名文件应还原;镜像里没有的应退出非 0"; fail=$((fail+1)); }
rm -rf "$_M"
# 不计入用例:本机脚本与仓库镜像是否一致(改脚本过程中不一致是常态,只提示)
_MS=$(python3 "$D/repo-sync.py" status 2>/dev/null | head -1); [ -n "$_MS" ] && echo "📦 ${_MS/MIRROR: /脚本镜像 } $(echo "$_MS" | grep -q '改动未入库=0 新文件未入库=0 仓库多出=0' || echo '→ repo-sync.py snapshot')"
fi

# ── cards1110(11-10 用户「先拿5道闸试一周」):判据卡 card.py + references/cards.md ──────────────
if [ -f "$D/card.py" ]; then
_CD=$(mktemp -d); _cd(){ CARD_USAGE="$_CD/u.tsv" CARD_SEEN="$_CD/s.json" CARDS="${_CARDS:-$G/references/cards.md}" env -u CARD_QUIET python3 "$D/card.py" "$@" 2>&1; }
# ① 体积与卡名:只试 5 张,每张 ≤2KB、全文件 ≤8KB,每张有自检句
_cl=$(_cd list); _cs=$(wc -c < "$G/references/cards.md" 2>/dev/null | tr -d ' ')
n=$((n+1)); [ "$(echo "$_cl" | awk '{print $1}' | tr '\n' ' ')" = "时效 时段 双要素 归因 过期题 " ] || { echo "❌ cards1110①: 试跑卡应正好 时效/时段/双要素/归因/过期题 五张: $_cl"; fail=$((fail+1)); }
n=$((n+1)); { [ "${_cs:-99999}" -le 8192 ] && echo "$_cl" | awk '$2+0>2048{bad=1} END{exit bad}'; } || { echo "❌ cards1110①b: 每张 ≤2KB、全文件 ≤8KB(现 ${_cs}B): $_cl"; fail=$((fail+1)); }
n=$((n+1)); [ "$(CARDS="$G/references/cards.md" python3 -c "import sys;sys.path.insert(0,'$D');import card;print(sum('自检' in b for b in card.load().values()))")" = 5 ] || { echo "❌ cards1110①c: 每张卡都要有一句自检"; fail=$((fail+1)); }
# ② 挑卡:建题四张(tradfi 带价才有时段)、只改关键词不出卡、过期题改/撤出过期题卡、时间词出时效
_pk=$(python3 -c "
import sys;sys.path.insert(0,'$D');import card
N=card._now()
print(card.pick('create','币安被盗后COIN盘中跌12%','tradfi'))
print(card.pick('create','BTC跌破7.4万美元','crypto'))
print(card.pick('update','x','crypto',closed_ms=N+3600000,new_title=False))
print(card.pick('update','x','crypto',closed_ms=N-1,new_title=False))
print(card.pick('cull','x','tradfi',closed_ms=N-1))
print(card.pick('update','美联储明日公布决议','tradfi',closed_ms=N+3600000,new_title=False))")
n=$((n+1)); [ "$_pk" = "['双要素', '归因', '时效', '时段']
['双要素', '归因', '时效']
[]
['过期题']
['过期题']
['时效']" ] || { echo "❌ cards1110②: 挑卡规则不对: $_pk"; fail=$((fail+1)); }
# ③ 60 分钟去重:第一次打印、59 分钟内跳过、61 分钟后再打;show 不去重;都记 usage
_o1=$(CARD_NOW_MS=1800000000000 _cd route 0 30); _o2=$(CARD_NOW_MS=1800003540000 _cd route 0 30); _o3=$(CARD_NOW_MS=1800003660000 _cd route 0 30)
n=$((n+1)); { echo "$_o1" | grep -q '📇 判据卡·过期题' && [ -z "$_o2" ] && echo "$_o3" | grep -q '📇 判据卡·过期题' && [ "$(cut -f4 "$_CD/u.tsv" | tr '\n' ' ')" = "打印 去重 打印 " ]; } || { echo "❌ cards1110③: 同卡 60 分钟去重/记账不对: [$_o2] $(cat "$_CD/u.tsv" 2>/dev/null)"; fail=$((fail+1)); }
n=$((n+1)); { _cd show 时段 | grep -q '📇 判据卡·时段' && CARD_NOW_MS=1800003660001 _cd show 过期题 | grep -q '判据卡·过期题'; } || { echo "❌ cards1110③b: show 应不受去重"; fail=$((fail+1)); }
# ④ 卡片文件不在(沙箱/旧规则包)→ 一律静默、退出 0,不得影响写题
_o4=$(_CARDS="$_CD/nosuch.md" _cd route 0 30; echo "rc=$?")
n=$((n+1)); [ "$_o4" = "rc=0" ] || { echo "❌ cards1110④: 没有 cards.md 应静默: $_o4"; fail=$((fail+1)); }
# ⑤ route.sh 路由后接着出卡(0>8h→过期题;0≤8h→时段)
_o5=$(CARD_USAGE="$_CD/u5.tsv" CARD_SEEN="$_CD/s5.json" CARDS="$G/references/cards.md" env -u CARD_QUIET "$D/route.sh" 0 30; echo "rc=$?")
_o6=$(CARD_USAGE="$_CD/u5.tsv" CARD_SEEN="$_CD/s5.json" CARDS="$G/references/cards.md" env -u CARD_QUIET "$D/route.sh" 0 3 12)
n=$((n+1)); { echo "$_o5" | grep -q '破闸例外' && echo "$_o5" | grep -q '📇 判据卡·过期题' && echo "$_o5" | grep -q 'rc=0' && echo "$_o6" | grep -q '升温update' && echo "$_o6" | grep -q '📇 判据卡·时段'; } || { echo "❌ cards1110⑤: route.sh 应先给路由再出对应判据卡: $_o5 / $_o6"; fail=$((fail+1)); }
# ⑥ 批量预检:各条命中的卡汇总后在逐条结果前只打一次
cat > "$_CD/plan.txt" <<'PLANEOF'
create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.8%' --keywords 'RKLB,火箭实验室' --rc 有诱因-多源 --note '回归:卡片汇总' --pct 'RKLB=59.18/64.22'
create --domain crypto --title 'Upbit上线XYZ现货，XYZ涨60%' --keywords 'XYZ' --rc 有诱因-多源 --note '回归:卡片汇总'
PLANEOF
_ck6=$(CARD_USAGE="$_CD/u6.tsv" CARD_SEEN="$_CD/s6.json" CARDS="$G/references/cards.md" CONSOLE_FAKE="$_CD/c.json" ACTIONS="$_CD/a.tsv" SNAPSHOTS="$_CD/ts.tsv" REJ="$_CD/r.tsv" REJ_OK="$_CD/ok.tsv" UNLOGGED="$_CD/un.tsv" B0JSON="$_CD/b0.json" CHECK_HITS="$_CD/k.tsv" DS_CLASH="$_CD/e.tsv" TOPIC_NO_DOWNSTREAM=1 env -u CARD_QUIET python3 "$D/topic.py" check "$_CD/plan.txt" 2>&1)
_c1=$(echo "$_ck6" | grep -n '📇 判据卡·' | head -1 | cut -d: -f1); _r1=$(echo "$_ck6" | grep -n -E '^(✔|🚨) #1 ' | cut -d: -f1)
n=$((n+1)); { [ "$(echo "$_ck6" | grep -c '📇 判据卡·')" = 4 ] && [ "$(echo "$_ck6" | grep -c '📇 判据卡·双要素')" = 1 ] && [ -n "$_c1" ] && [ -n "$_r1" ] && [ "$_c1" -lt "$_r1" ]; } \
  || { echo "❌ cards1110⑥: 预检应在逐条结果前把 4 张卡各打一次: $(echo "$_ck6" | grep -E '📇|^(✔|🚨) #|CHECK')"; fail=$((fail+1)); }
n=$((n+1)); { [ ! -s "$_CD/a.tsv" ] && [ ! -s "$_CD/r.tsv" ] && [ ! -s "$_CD/c.json" ]; } || { echo "❌ cards1110⑥b: 带卡片的预检仍不得写看板/台账/拒写留痕"; fail=$((fail+1)); }
# ⑦ 逐条判(11-10 用户「按逐条判的口径来」):打卡记触发题;建题成功后记「题号|标题」关联;结算能按题号找回建题前出现过的卡
_CW="$_CD/w"; mkdir -p "$_CW"
_cw(){ CARD_USAGE="$_CD/u7.tsv" CARD_SEEN="$_CD/s7.json" CARDS="$G/references/cards.md" CONSOLE_FAKE="$_CW/c.json" ACTIONS="$_CW/ta.tsv" SNAPSHOTS="$_CW/ts.tsv" REJ="$_CW/tr.tsv" REJ_OK="$_CW/tok.tsv" UNLOGGED="$_CW/tu.tsv" B0JSON="$_CW/tb0.json" WEIGHTS_TIER="$_CW/wt.tsv" TOPIC_NO_DOWNSTREAM=1 TOPIC_NO_REVIEW=1 env -u CARD_QUIET python3 "$D/topic.py" "$@" 2>&1; }
_c7=$(_cw create --domain tradfi --title '美国10月CPI将于周二21:30公布，前值3.7%' --keywords '美国CPI,通胀' --rc 预告题 --note '回归:卡片逐条判')
_t7=$(echo "$_c7" | grep -o '✔ 建 [0-9]*' | grep -o '[0-9]*$')
n=$((n+1)); { [ -n "$_t7" ] && grep -q $'\t双要素\tcreate\t打印\t美国10月CPI将于周二21:30公布，前值3.7%$' "$_CD/u7.tsv" && grep -q $'\t-\tcreate\t关联\t'"$_t7"'|美国10月CPI' "$_CD/u7.tsv"; } || { echo "❌ cards1110⑦: 建题前打卡应记标题、建成后应记「题号|标题」关联: $(cut -f2-5 "$_CD/u7.tsv" 2>/dev/null) / $(echo "$_c7" | tail -2)"; fail=$((fail+1)); }
_ev=$(CARD_USAGE="$_CD/u7.tsv" python3 -c "import sys,time;sys.path.insert(0,'$D');import card;print(sorted({n for n,s,_ in card.evidence('$_t7', int(time.time()*1000)+1)}))")
n=$((n+1)); [ "$_ev" = "['双要素', '归因', '时效', '时段']" ] || { echo "❌ cards1110⑦b: 按题号 $_t7 应找回建题前的 4 张卡,得 $_ev"; fail=$((fail+1)); }
# ⑧ judge 只收三类、能管的两类必须写卡名、理由不能空、错误 id 必须在 errors.tsv 里
printf '1794000000000\te1\t纠错·归因\t10000000001\t无源归因\n' > "$_CD/err.tsv"
_jg(){ ERRORS="$_CD/err.tsv" CARD_JUDGED="$_CD/j.tsv" CARDS="$G/references/cards.md" python3 "$D/card.py" judge "$@" >/dev/null 2>&1; echo -n "$? "; }
_j8="$(_jg e1 看着像 归因 x)$(_jg e1 该打没打 - x)$(_jg e9 管不到 - x)$(_jg e1 该打没打 归因 '')$(_jg e1 该打没打 归因 '归因卡该在改标题时出')"
n=$((n+1)); { [ "$_j8" = "1 1 1 1 0 " ] && [ "$(wc -l < "$_CD/j.tsv" | tr -d ' ')" = 1 ]; } || { echo "❌ cards1110⑧: judge 校验不对(期望 1 1 1 1 0): $_j8"; fail=$((fail+1)); }
# ⑨ 结算:基线 3 条能管;上线后 1 条能管+1 条管不到 → 到期判「通过」;有待判不下结论;未到期只作参考;工具拦截类不算判断错误
_S=1794000000000; _W=$((7*86400000))
printf '%s\n' "$((_S-3000))	b1	纠错·归因	10000000011	x" "$((_S-2000))	b2	纠错·归因	10000000012	x" "$((_S-1000))	b3	复审挑战·时效口径	10000000013	x" \
  "$((_S+1000))	p1	纠错·归因	10000000021	x" "$((_S+2000))	p2	纠错·其他	10000000022	x" "$((_S+3000))	t1	工具拦截·标题长度	-	不算判断类" > "$_CD/err9.tsv"
printf '%s\n' "$((_S+500))	归因	update	打印	10000000021" > "$_CD/u9.tsv"
printf '%s\n' "1	b1	该打没打	归因	r" "1	b2	该打没打	归因	r" "1	b3	该打没打	时段	r" "1	p1	卡打了照犯	归因	r" > "$_CD/j9.tsv"
_tr(){ ERRORS="$_CD/err9.tsv" CARD_USAGE="$_CD/u9.tsv" CARD_JUDGED="$_CD/j9.tsv" CHECK_HITS=/dev/null ACTIONS=/dev/null CHECKLOG=/dev/null python3 -c "import sys;sys.path.insert(0,'$D');import card;l,v=card.trial(start=$_S,now=$1);print(v);print(chr(10).join(l))"; }
_v1=$(_tr $((_S+_W+1)))
printf '1\tp2\t管不到\t-\t措辞\n' >> "$_CD/j9.tsv"; _v2=$(_tr $((_S+_W+1))); _v3=$(_tr $((_S+_W-1)))
n=$((n+1)); { echo "$_v1" | head -1 | grep -q '^待判:还有 1 条' && echo "$_v2" | head -1 | grep -q '^通过:能管的错误 3→1' && echo "$_v3" | head -1 | grep -q '^未到期' \
  && echo "$_v2" | grep -q '\[卡打了照犯·归因\] p1 .*卡:归因(打印)' && ! echo "$_v2" | grep -q '\] t1 '; } \
  || { echo "❌ cards1110⑨: 逐条判结算不对: $(echo "$_v1" | head -1) / $(echo "$_v2" | head -1) / $(echo "$_v3" | head -1)"; fail=$((fail+1)); }
printf '%s\n' "$((_S+4000))	p3	自审发现·时效口径	10000000023	x" "$((_S+5000))	p4	纠错·归因	10000000024	x" "$((_S+6000))	p5	纠错·归因	10000000025	x" >> "$_CD/err9.tsv"
printf '%s\n' "1	p2	该打没打	时效	改判" "1	p3	该打没打	时效	r" "1	p4	该打没打	归因	r" "1	p5	管不到	-	r" >> "$_CD/j9.tsv"
_v4=$(_tr $((_S+_W+1)) | head -1)
n=$((n+1)); echo "$_v4" | grep -q '^失败:能管的错误 4 条 >3' || { echo "❌ cards1110⑨b: 能管的错误 >3 应判失败(同一 id 判多次以最后一次为准): $_v4"; fail=$((fail+1)); }
rm -rf "$_CD"
fi
n=$((n+1)); _WT1=$(wc -l < "$_WT_PROD" 2>/dev/null | tr -d ' '); [ "${_WT1:-0}" = "$_WT0" ] || { echo "❌ 权重档案守卫(11-10): 回归往生产 weights-tier.tsv 写了 $((_WT1-_WT0)) 行——WEIGHTS_TIER 必须指向临时文件"; fail=$((fail+1)); }
# ── retro1110(11-10 每晚复盘):批量预检并发偶发「退出码非 0 且无输出」→ 串行重跑一次,不当被拦 ──────────────
_FL=$(mktemp -d); touch "$_FL/flake"
cat > "$_FL/p.txt" <<'PLANEOF'
create --domain tradfi --title 'Neutron首飞推迟至2027年，RKLB收跌7.8%' --keywords 'RKLB,火箭实验室' --rc 有诱因-多源 --note '回归:并发无输出重跑' --pct 'RKLB=59.18/64.22'
PLANEOF
_fo=$(TOPIC_CHECK_FLAKE="$_FL/flake" CONSOLE_FAKE="$_FL/c.json" ACTIONS="$_FL/a.tsv" SNAPSHOTS="$_FL/s.tsv" REJ="$_FL/r.tsv" REJ_OK="$_FL/ok.tsv" UNLOGGED="$_FL/u.tsv" B0JSON="$_FL/b0.json" CHECK_HITS="$_FL/k.tsv" DS_CLASH="$_FL/e.tsv" TOPIC_NO_DOWNSTREAM=1 python3 "$D/topic.py" check "$_FL/p.txt" 2>&1)
n=$((n+1)); { echo "$_fo" | grep -q '^✔ #1 ' && echo "$_fo" | grep -q '串行重跑' && [ ! -e "$_FL/flake" ]; } || { echo "❌ retro1110[预检重跑]: 并发下无输出失败应串行重跑一次并注明,不得判被拦: $(echo "$_fo" | grep -E '#1|重跑|无输出')"; fail=$((fail+1)); }
rm -rf "$_FL"
# 守卫:整套回归跑完,生产 card-usage.tsv 不得多出行(试跑结算靠它)
n=$((n+1)); _CU1=$({ wc -l < "$_CU_PROD"; } 2>/dev/null | tr -d ' '); [ "${_CU1:-0}" = "$_CU0" ] || { echo "❌ cards1110[守卫]: 回归往生产 card-usage.tsv 写了记录——CARD_USAGE 必须指向临时文件"; fail=$((fail+1)); }

[ "$fail" -eq 0 ] && {

if [ "$skip" -gt 0 ]; then
  echo "✅ 回归 $((n-skip))/$n 用例通过，跳过 $skip 条（${skipmsg}）｜散点 ${sc:-?}｜gates $((gs/1024))/128KB｜SKILL $sl 行"
  echo "   ⚠️ 跳过的不算通过:上面那几条本轮**没测成**,换到能连通的环境要补跑"
else
  echo "✅ 回归 $n 用例全过｜散点 ${sc:-?}｜gates $((gs/1024))/128KB｜SKILL $sl 行"
fi
exit 0; }
echo "🚨 回归失败 $fail 项——规则退化,先修再出报告"; exit 1
