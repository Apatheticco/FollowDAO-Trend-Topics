#!/bin/bash
# v3.4.4(周报提案 P0-1) 入口固定 C locale:本脚本全部字符串操作(-T 的 ${x%%|*} 切段、备注长度、枚举 grep)按字节语义写成,
#   生产 shell 一直是 C。macOS /bin/bash 3.2 在 UTF-8 locale 下对含中文的 ${var%%pattern} 会切坏多字节字符——
#   实测 en_US.UTF-8 下 `-T '判据|实测|因'` 落进台账成「判据=��实测=��」(静默写坏,不报错),
#   metrics.py 经 python subprocess 跑回归时继承 UTF-8,于是周报连报 7 项「回归未通过」。
export LC_ALL=C
# v2.9.71 结构化写操作日志——归因可聚合(对偶 log-snapshot.sh / checklist.sh)
# v2.9.73 补:cull 自动补写快照(治误撤率算不出) + cull-batch 逐条落账(治批量撤合并致归因失真)
# v3.3.4 备注模板化(-T)+改题批量(update-batch)——治「备注膨胀」:09-08 22:00 轮实测,
#   写操作 32 条、输出 54553 token(优化前一轮 48 条写操作只用 33532),**每写操作成本涨 60%**,
#   主因是每条 log-action 备注 200~1000 字。三要素(判据/实测/落此code因)必须留,但不必每条重写判据。
# 用法: log-action.sh <action> <id> <reason_code> <备注> [旧标题→新标题]
#       log-action.sh <action> <id> <reason_code> -T "<判据>|<实测>|<落此code因>" [旧标题→新标题]
#            ↑ 三段模板,展开成标准备注;机械改题(改数字族/改样式)默认走这条,省 60~80% 字数。
#              需要讲清事故/教训/分歧的(cull/改归因/note/rulefix)仍用长备注,不要模板化。
#       log-action.sh update-batch <rc> <判据> <落此code因> "<id>|<旧→新>|<该条实测>" ...
#            ↑ 判据与 why 写一次,实测每条一句;逐条调用 update,**所有闸照常生效**(同 cull-batch)
#       log-action.sh codes            列出枚举
#       log-action.sh stats [天数]     归因分布统计
#       log-action.sh reject-ok <拒写行ts> <怎么处理的>   v3.7.0 拒写标记已处理(不再删行)
#       LA_CHECK=1 log-action.sh <同上参数>   v3.7.0 只跑全部闸不落账(topic.py 写看板前预检用;被拒照样留痕)
DIR="$HOME/.trend-scout"
# v3.1.3 三个写入路径全部可注入——回归测试必须能把写操作导到临时文件。
#   09-06 实录:回归用例传了 ACTIONS=<tmp> 但本文件的 F 是硬编码,3 条假 id(9101/9102)被写进真台账与真快照,
#   直到复审员把它们当本轮处置报进 LEDGER 才发现。**测试用例污染生产数据,比没有测试更危险**。
F="${ACTIONS:-$DIR/actions.tsv}"
REJ="${REJ:-$DIR/actions-rejected.tsv}"  # v2.9.82 拒写留痕,checklist.sh verify 据此拦报告
REJ_OK="${REJ_OK:-$DIR/actions-rejected-resolved.tsv}"
# v3.7.0 拒写行加三列结构(动作/id/rc):ledger.py 据此自动判「其后已同动作同 id 落账=已处理」,
#   旧版只有一句话,只能靠删行放行——工具拦下的错误证据被清空,周报数不出「被拦了几次」(10-12~10-14 ≥4 次,文件 0 条)。
# 拒写行 ts 用真毫秒:同一秒内连拒两条(cull-batch 常见)时「$(date +%s)000」会撞 ts,reject-ok 按 ts 标记就会一次标掉两条。
# v3.7.22 检查计数:拒写同时记一行 check-hits.tsv(检查名=log-action:<拒写原文冒号前一段,≤12 字>),retro.py 减法候选读它。
CHECK_HITS="${CHECK_HITS:-$DIR/check-hits.tsv}"
reject(){ local _ts; _ts="$(python3 -c 'import time;print(int(time.time()*1000))' 2>/dev/null || echo "$(date +%s)000")"
  printf "%s\t%s\t%s\t%s\t%s\n" "$_ts" "$*" "${ACT:-}" "${ID:-}" "${RC:-}" >> "$REJ"
  printf "%s\tlog-action:%s\t拦\t%s\t%s\t%s\n" "$_ts" "$(printf '%s' "$*" | python3 -c 'import sys,re;print(re.split("[:：]",sys.stdin.read(),maxsplit=1)[0].strip()[:12])' 2>/dev/null)" "${ACT:-}" "${ID:-}" "${RC:-}" >> "$CHECK_HITS" 2>/dev/null
  exit 1; }

# v3.3.4 **改名 ACTIONS→ACT_ENUM(潜伏 bug 修复)**:注入用的环境变量也叫 ACTIONS,而它是命令前缀设的
#   (等同 export),脚本在这里重新赋值会**连带修改被导出的那个**,于是 cull-batch/update-batch
#   的子调用 `"$0" ...` 继承到的 ACTIONS 变成了 "create cull update..." 这串枚举,
#   子进程的 F=${ACTIONS:-默认} 就把台账写进了一个名叫「create cull update merge restore publish rulefix note」的文件。
#   **生产路径一直是好的**(不注入时 ACTIONS 非 export、子进程取默认值),所以从 v2.9.73 潜伏至今;
#   坏的只有注入路径——也就是**回归用例里所有 cull-batch 断言,测的都不是它们声称的那条路径**。
#   一个「通过」但测错路径的用例,比没有用例更危险。
ACT_ENUM="create cull update merge restore publish rulefix note"

# reason_code 枚举:从 1210 行历史归纳,分三组
R_CREATE="有诱因-多源 有诱因-单源待核 纯行情-A定则 meme豁免 预告题 承接兑现 板块聚合 补跑捞回"
R_CULL="灌水-KOL观点 灌水-产品公告 灌水-vanity指标 灌水-融资无标的 灌水-立法程序 预告题-准入不过 重复-同标的 重复-碎片合并 反转错向 事实错误-数字 事实错误-定义 归因-借源造因 归因-反向 缺价格腿 缺诱因-未达线 疑问句-悬念 已证伪 过期-窗口题 用户点名 链上红线-托管流水/多空对赌"
# v2.9.79:「A闸不过-灌水」宽桶已废——占撤题41%的一个桶=零分析价值,且宽到能装下任何想撤的meme(11815/11859两次误撤的藏身处)
# v3.7.6(10-17 用户批周度 review ③-3/④-1):废「灌水-悬念疑问」(与「疑问句-悬念」重复,历史 3 次,Q2=A 后问号题统一记后者);
#   补「预告题-准入不过」(13182/13211 两条该撤的预告题此前无码可落,被迫借灌水码)。
R_UPDATE="改数字-定稿 改数字-升温 改数字-回落 改归因 改口径-时段 改样式-命名 tag修正 状态修正 承接更新 纠错-自纠"
# v3.7.0「纠错-自纠」=改正我自己写错的内容(算错的数字/事实)。此前没有这个码,10-15 RKLB 二次舍入(7.848%写成7.9%)
#   的修正只能记「改数字-定稿」,而周报⑤返工率口径恰好把定稿当正常代谢排除——自己犯的错在统计里隐身。
#   约束:必须带标题变更;过期题照 v3.6.0 不许改(事实错误按撤题走)。
R_OTHER="规则演进 通道故障 自审发现 复审员挑战 留档 跳过-待人裁 上游诱发"
# v2.9.81:「上游诱发」=错误/返工由系统侧缺陷引起(编辑回滚/碎片/切词/无过期),周报把点名与返工拆成「我错的」vs「上游诱发」两份
ALL_R="$R_CREATE $R_CULL $R_UPDATE $R_OTHER"

case "$1" in
codes)
  echo "action 枚举: $ACT_ENUM"; echo ""
  echo "reason_code —— 建题:"; for r in $R_CREATE; do echo "  $r"; done
  echo "reason_code —— 撤题:"; for r in $R_CULL; do echo "  $r"; done
  echo "reason_code —— 改题:"; for r in $R_UPDATE; do echo "  $r"; done
  echo "reason_code —— 其他:"; for r in $R_OTHER; do echo "  $r"; done
  exit 0;;
reject-ok)
  # v3.7.0 拒写标记已处理——替代旧版「补记后 rm 该行」。行留着,周报才数得出工具拦了几次。
  #   多数拒写不需要这条:其后同动作同 id 落账即自动判已处理(ledger.py);只有改判不写/换了 id 的才要显式标。
  _RT="$2"; _RN="$3"
  [ -n "$_RT" ] && [ -n "$_RN" ] || { echo "用法: log-action.sh reject-ok <拒写行ts(第1列)> <怎么处理的>"; exit 1; }
  _UL="${UNLOGGED:-$DIR/actions-unlogged.tsv}"; _FS=""
  for _f in "$REJ" "$_UL"; do [ -f "$_f" ] && _FS="$_FS $_f"; done
  [ -n "$_FS" ] && awk -F'\t' -v t="$_RT" '$1==t{f=1} END{exit !f}' $_FS || {
    echo "🚨 拒写/未落账文件里没有 ts=$_RT 的行(第1列13位毫秒)"; exit 1; }
  printf "%s\t%s\t%s\n" "$(date +%s)000" "$_RT" "$(printf '%s' "$_RN" | tr '\t\n' '  ')" >> "$REJ_OK" || { echo "🚨 $REJ_OK 不可写"; exit 3; }
  echo "✔ 拒写 $_RT 已标记处理"
  exit 0;;
cull-batch)
  # v2.9.73:批量撤逐条落账,禁止合并成一行 note(否则归因分布绝对数失真)
  RC="$2"; NOTE="$3"; shift 3
  [ -n "$RC" ] && [ -n "$NOTE" ] && [ $# -gt 0 ] || { echo "用法: log-action.sh cull-batch <reason_code> <共同备注> <id1> <id2> ..."; exit 1; }
echo "$ALL_R" | tr ' ' '\n' | grep -qx "$RC" || { echo "🚨 reason_code 不在枚举内: $RC"; exit 1; }
  n=0
  for id in "$@"; do "$0" cull "$id" "$RC" "$NOTE" >/dev/null && n=$((n+1)); done
  echo "✔ cull-batch 逐条落账 $n 条 [$RC]"
  exit 0;;
update-batch)
  # v3.3.4:改题批量。与 cull-batch 同构——**逐条调用 $0 update,不合并成一行**,
  #   否则归因分布绝对数失真(v2.9.73 的教训),且每条的 action×rc / 备注长度 / 标题变更闸都会被跳过。
  RC="$2"; JUDGE="$3"; WHY="$4"; shift 4
  [ -n "$RC" ] && [ -n "$JUDGE" ] && [ -n "$WHY" ] && [ $# -gt 0 ] || {
    echo "用法: log-action.sh update-batch <rc> <判据> <落此code因> \"<id>|<旧→新>|<该条实测>\" ..."; exit 1; }
  echo "$R_UPDATE $R_OTHER" | tr ' ' '\n' | grep -qx "$RC" || {
    echo "🚨 update-batch 的 rc 必须是改题族: $R_UPDATE"; echo "   或通用族: $R_OTHER"; exit 1; }
  n=0; bad=0
  for spec in "$@"; do
    _id="${spec%%|*}"; _rest="${spec#*|}"; _delta="${_rest%%|*}"; _meas="${_rest#*|}"
    if [ "$_id" = "$spec" ] || [ "$_delta" = "$_rest" ] || [ -z "$_meas" ]; then
      echo "🚨 spec 需三段「id|旧→新|实测」,收到: $spec"; bad=$((bad+1)); continue
    fi
    if "$0" update "$_id" "$RC" -T "$JUDGE|$_meas|$WHY" "$_delta" >/dev/null; then n=$((n+1)); else bad=$((bad+1)); fi
  done
  echo "✔ update-batch 逐条落账 $n 条 [$RC]${bad:+ ｜⚠️ 失败 $bad 条}"
  [ "$bad" -eq 0 ] || exit 1
  exit 0;;
stats)
  DAYS="${2:-7}"; CUT=$(( ($(date +%s) - DAYS*86400) * 1000 ))
  echo "=== 近 ${DAYS} 天归因分布(仅 6 列结构化行)==="
  awk -F'\t' -v c="$CUT" 'NF>=5 && $1+0>=c {print $2"\t"$4}' "$F" \
    | sort | uniq -c | sort -rn \
    | awk '{printf "%4d  %-10s %s\n",$1,$2,$3}'
  echo ""
  echo "=== 标题变更流水 ==="
  awk -F'\t' -v c="$CUT" 'NF>=6 && $1+0>=c && $6!="" {print "  ["$3"] "$6}' "$F"
  exit 0;;
esac

ACT="$1"; ID="$2"; RC="$3"; NOTE="$4"; DELTA="$5"

# v3.5.0(09-20 自审发现) 备注里的换行会把一行 TSV 撑成多行物理行,后续所有 awk -F'\t' 消费者
#   (metrics.py / weekly-verify / log-action stats / review-verify) 只认首列是13位时间戳的行,
#   续行全部变成看不见的孤儿——**内容还在文件里,但对所有统计都不存在**。
#   实证:09-20 我给 v3.4.8 写的三层落地说明有 5 行掉成孤儿,于是 weekly-verify 从台账抽版本号时
#   抽不到 v3.4.8,一条当天固化的规则就这样绕过了「本周每条 rulefix 都必须回看」的门禁;
#   全库体检 3128 行里有 168 行是这种孤儿。改成写入前把换行压成「 ⏎ 」保形不丢内容。
NOTE=$(printf '%s' "$NOTE" | awk 'NR>1{printf " ⏎ "}{printf "%s",$0}')
DELTA=$(printf '%s' "$DELTA" | awk 'NR>1{printf " ⏎ "}{printf "%s",$0}')

# v3.3.4 -T 三段模板:把「判据|实测|落此code因」展开成标准备注。
#   三要素是规则要求(备注三要素),模板只压缩**写法**不压缩**内容**;缺任一段直接拒,
#   免得模板化变成「少写一要素」的后门。
if [ "$NOTE" = "-T" ]; then
  _TSEG="$5"; DELTA="$6"
  _J="${_TSEG%%|*}"; _R="${_TSEG#*|}"; _M="${_R%%|*}"; _W="${_R#*|}"
  if [ "$_J" = "$_TSEG" ] || [ "$_M" = "$_R" ] || [ -z "$_J" ] || [ -z "$_M" ] || [ -z "$_W" ]; then
    echo "🚨 -T 需三段「判据|实测|落此code因」,收到: 「$_TSEG」"
    echo "   例: -T 'v2.9.62窗口题72h|binance 0.1537→0.1412=-9.7%|价格腿刷新,诱因不变'"
    reject "-T三段不全:$ID $ACT/$RC"
  fi
  NOTE="判据=$_J；实测=$_M；落此code因=$_W"
fi
[ -n "$NOTE" ] || { echo "用法: log-action.sh <action> <id> <reason_code> <备注> [旧标题→新标题]"; echo "      log-action.sh codes | stats [天数] | cull-batch <rc> <备注> <id...>"; exit 1; }

echo "$ACT_ENUM" | tr ' ' '\n' | grep -qx "$ACT" || {
  echo "🚨 action 不在枚举内: $ACT"; echo "   合法值: $ACT_ENUM"
  echo "   (历史上 action 列长出过 203 种自造标签,导致归因无法聚合——这道闸就是防这个)"; reject "action非枚举:$ACT $ID"; }

echo "$ALL_R" | tr ' ' '\n' | grep -qx "$RC" || {
  echo "🚨 reason_code 不在枚举内: $RC"; echo "   跑 log-action.sh codes 看全表"
  # 11-10 架构 review(rc非枚举近 14 天 7 次):直接给最接近的合法码,不用在一长串里找
  _near=$(python3 -c 'import sys,difflib;print("、".join(difflib.get_close_matches(sys.argv[1],sys.argv[2].split(),n=3,cutoff=0.4)))' "$RC" "$ALL_R" 2>/dev/null)
  [ -n "$_near" ] && echo "   最接近的合法码: $_near"
  # 11-06 复盘(rc非枚举又犯 3 次:撤题写成「双要素-缺价格」):当场列出本 action 的合法码,不用再跑 codes
  case "$ACT" in cull) echo "   cull 可用: $R_CULL";; create) echo "   create 可用: $R_CREATE";; update) echo "   update 可用: $R_UPDATE";; esac
  # 10-26 复盘(rc非枚举第 3 次:note 写成「系统建放行」):note 只收 R_OTHER,当场列出来,放行说明写进「留档」备注
  [ "$ACT" = note ] && echo "   note 可用: $R_OTHER(系统建放行/弃建等写 留档 + 备注首段)"
  echo "   确需新类型 → 先在本脚本加枚举并在报告里说明,禁止塞自由文本"; reject "rc非枚举:$ACT $ID $RC"; }

# v3.2.0 备注实质性:备注三要素(判据引用＋实测证据＋为何落此 code)本就要求实质内容,
#   一个 'x' 或 'test' 显然不合格。**这条闸防的不是别人,是我自己在生产台账上敲验证命令**——
#   09-07 一天内犯两次:下午手工验 v3.1.9 时用 id=99999 污染 actions/snapshots(v3.1.3 的泄漏哨兵
#   只盯回归用的固定 id 段,防不了手工命令);傍晚又用 `cull 12094 用户点名 x` 测 rc 校验,再污染一条。
#   **任何验证都该用 ACTIONS=/tmp/... 注入,不要在生产台账上试**;这道闸是最后一层兜底。
# v3.4.4(周报提案 P0-1) 计数改为字节且显式 LC_ALL=C:原 `wc -m` 随 locale 变——C 下数字节、UTF-8 下数字符,
#   同一条「同标的在线重复」C 下 21 通过、en_US.UTF-8 下 7 被拒。生产 shell 一直是 C(实际判据=字节),
#   而 metrics.py 经 python subprocess 跑回归时继承 UTF-8 → 周报「回归未通过」7 项假失败连报。判据不变,只去掉 locale 依赖。
_NLEN=$(printf '%s' "$NOTE" | LC_ALL=C wc -c | tr -d ' ')
if [ "$_NLEN" -lt 12 ] && [ "$ACT" != "note" ]; then
  echo "🚨 备注过短($_NLEN 字节,要求 ≥12 字节≈4 个汉字): 备注三要素=判据引用＋实测证据＋为何落此 reason_code"
  echo "   收到的是: 「$NOTE」"
  echo "   如果你在测试:用 ACTIONS=/tmp/t.tsv SNAPSHOTS=/tmp/s.tsv REJ=/tmp/r.tsv 注入,别写生产台账"
  reject "备注过短:$ID $ACT/$RC"
fi

# v3.1.9 action × rc 组合合法性:rc 在全集内还不够,还得属于这个 action 的那一组。
#   09-05 我用 `restore + 复审员挑战` 时就记过「本脚本不校验组合」是个可加的闸,当时没加;
#   09-07 复审员抓到我用 `update + 反转错向`——反转错向是撤题枚举,改题该用「改归因」。
#   **同一个缺口两天内踩两次,第二次是复审员替我抓的**,所以这次补上。
#   note/rulefix/merge/publish 不限制(它们本就跨组用 rc)。
case "$ACT" in
  create)          _OK="$R_CREATE $R_OTHER" ;;
  cull)            _OK="$R_CULL $R_OTHER" ;;
  update|restore)  _OK="$R_UPDATE $R_OTHER" ;;
  *)               _OK="$ALL_R" ;;
esac
printf '%s' "$_OK" | tr ' ' '\n' | grep -qx "$RC" || {
  echo "🚨 action×rc 组合非法(v3.1.9): action=$ACT 不能用 reason_code「$RC」"
  case "$ACT" in
    create) echo "   建题可用: $R_CREATE" ;;
    cull)   echo "   撤题可用: $R_CULL" ;;
    update|restore) echo "   改题可用: $R_UPDATE" ;;
  esac
  echo "   任何 action 都能用的: $R_OTHER"
  echo "   提示:方向反转导致的**改题**用「改归因」,「反转错向」是撤题专用"
  reject "action×rc组合非法:$ID $ACT/$RC"
}

[ "$ACT" = "update" ] && [ -z "$DELTA" ] && {
  echo "⚠️ update 未带标题变更(第5参数)。若本次只改 status/tag 不改标题,传 '-' 显式声明"; reject "update缺标题变更:$ID $RC"; }

[ "$RC" = "纠错-自纠" ] && { [ -z "$DELTA" ] || [ "$DELTA" = "-" ] || ! printf '%s' "$DELTA" | grep -q '→'; } && {
  echo "🚨 纠错-自纠(v3.7.0)必须带「旧标题→新标题」——改的是我写错的内容,标题没变就不是纠错(改 tag 用 tag修正;只更正备注里的事实、标题不动,用 note <id> 留档)"
  reject "纠错缺标题变更:$ID"; }

# v3.5.0(09-20 用户点名「都做」) 复审员挑战行必须能判出裁决,否则第0层④算不出成立数。
#   09-13~09-20 实证:4 条成立里有 2 条被漏数,因为我写成「**复审员挑战成立,我错了…」,
#   旧匹配只认行首 ^成立: 够不着。metrics.py 已改全文匹配,这里再加一道**提醒**(不拒写):
#   拒写会误伤正当的轮次小结(实测 9 条里有 2 条成立案就写在小结里),把我逼去堆关键词前缀;
#   写不出裁决词的行仍然落账,只是 metrics 会在 ④ 段用 ⚠️ 单列出来,不静默漏掉。
[ "$RC" = "复审员挑战" ] && ! printf '%s' "$NOTE" | grep -qE '挑战成立|成立[:：]|不成立|据此改判|改判为撤|我错了|接受并改判' && {
  echo "⚠️ 复审员挑战行里没有裁决词(成立/不成立/改判…),第0层④会把它单列为「模糊」不计入分子——本行已落账,建议补一句裁决"; }

# v3.5.6(09-21 Evose 第二十三轮实证):「不成立」必须逐条带证据,且不许一句理由批量驳回。
# v3.5.7(09-22 第二十四轮):证据不能只引审核员决策表(被审对象自证),须引原始出处。本机 14 条历史「不成立」回测 0 误伤。
#   复审员对 4 题判「处置有误」,Lead 全判「不成立」、理由统一为「时点差」;其中一条异议(诱因查无出处)
#   与时点无关也被一起驳回。手册第 11b 步要求「不成立」附出处原文或实测数字——之前只写在手册里,没有闸。
#   证据判据(机器能查的最低线):理由里有数字,或有 ≥6 字的引文(「」『』“”"")。
#   本机 14 条历史「不成立」按此回测全部通过(09-21)。
if [ "$RC" = "复审员挑战" ] && printf '%s' "$NOTE" | grep -qE '^[[:space:]*]*不成立'; then
  _CH=$(python3 - "$F" "$ID" "$NOTE" <<'CHEOF' 2>/dev/null
import sys,re,time
f,tid,note=sys.argv[1],sys.argv[2],sys.argv[3]
def reason(n): return re.sub(r'^[\s*]*不成立[:：]?\s*(演练·未实调console｜)?\s*','',n).strip()
r=reason(note)
if not re.search(r'\d|「[^」]{6,}」|『[^』]{6,}』|“[^”]{6,}”|"[^"]{6,}"',r): print('NOEVI'); raise SystemExit
# v3.5.7 被审对象不能自证:只引审核员决策表、不引任何原始出处(取价原件/扫描员产出/工具返回)的,不算证据
if re.search(r'auditor|决策表|审核员产出',r) and not re.search(r'lead-[\w-]*(okx|b0)|scanner-|扫描员|工具返回',r): print('SELF'); raise SystemExit
now=int(time.time()*1000)
try: rows=[l.rstrip('\n').split('\t') for l in open(f,encoding='utf-8') if not l.startswith('#')]
except Exception: rows=[]
for x in rows:
    if len(x)>=5 and x[3]=='复审员挑战' and x[2]!=tid and x[0].isdigit() and now-int(x[0])<12*3600*1000 \
       and re.match(r'^[\s*]*不成立',x[4]) and reason(x[4])==r:
        print('DUP '+x[2]); raise SystemExit
print('OK')
CHEOF
)
  case "$_CH" in
    NOEVI) echo "🚨 「不成立」没有证据(v3.5.6):理由里须有实测数字,或 ≥6 字的出处原文引文(「」『』“”)——手册第 11b 步"
           echo "   驳回复审员要拿得出东西;拿不出就是「成立」或「待人裁」,不是「不成立」"
           reject "不成立缺证据:$ID" ;;
    SELF)  echo "🚨 「不成立」只引了审核员决策表(v3.5.7):复审员质疑的正是决策表里的数,拿它自己的话证明它不算证据"
           echo "   证据要来自原始出处——取价原件 lead-*-okx/b0、扫描员产出(取价记录)、工具返回原文;引不到就改判「成立」或「跳过-待人裁」"
           echo "   09-22 第二十四轮 10000002963 盘前274.05、12489 HYPE 94.68 两条都只引了 auditor 文件"
           reject "不成立自证:$ID" ;;
    DUP*)  echo "🚨 「不成立」理由与 ${_CH#DUP } 那条逐字相同(v3.5.6):每条异议要逐条回应,不许一句话批量驳回"
           echo "   09-21 第二十三轮 4 条异议被同一句「时点差」驳回,其中一条与时点无关"
           reject "不成立一刀切:$ID" ;;
  esac
fi

# v3.6.0 过期题不改价(2026-09-26 用户定「过期的题不用再继续改价」):
#   console 每条题有 closed_ts(crypto=建题+24h),09-24 实测在线 36 条里 24 条已过期,而每轮给这些题改价约占写操作四成。
#   只拦「改数字-*」;事实错误/反转等撤题、改归因不受影响。读不到快照或找不到该题=放行(无从判断)。
if [ "$ACT" = "update" ] && printf '%s' "$RC" | grep -qE '^(改数字|纠错-自纠$)'; then
  _EXP=$(python3 - "$ID" <<'PYEOF' 2>/dev/null
import sys,os,json,time
tid=sys.argv[1]
_snap=os.environ.get('B0JSON') or os.path.expanduser('~/.trend-scout/b0-latest.json')
try: rows=json.load(open(_snap))
except Exception: print("0"); raise SystemExit
rows=rows if isinstance(rows,list) else (rows.get('topics') or rows.get('data') or [])
t=next((x for x in rows if str(x.get('id'))==tid), None)
ct=(t or {}).get('closed_ts')
now=float(os.environ.get('NOW_MS') or time.time()*1000)
print("1" if ct and float(ct) < now else "0")
PYEOF
)
  if [ "$_EXP" = "1" ]; then
    echo "🚨 v3.6.0 过期题不改价(09-26 用户定):$ID 已过 closed_ts,不再做「$RC」。确有事实错误/方向反转要处理 → 按撤题走"
    reject "过期题改价:$ID $RC"
  fi
fi

# meme 硬闸:v2.9.7 铁律工具层执行。
# v3.1.2 判据从「备注文本」改为「题目本身」——原实现靠 `NOTE` 里有没有出现 meme/小市值/微型 触发,
#   是个自证式的闸:不提就不查、一提就拦。09-06 一轮内发作两次——
#   ① 机械撤的备注是固定模板永不含该词 → 整条机械撤路径 100% 绕过(09-05 12041);
#   ② 我在备注里写「LTC 是主流标的(不走 meme 闸)」「不在 meme 豁免保护内」来解释为何不适用,
#      **解释这个行为本身触发了闸**,7 条已在前台撤掉的题落账被拒,台账与前台静默不一致。
#   现改为与 b0-cull.py 同一套判据:读 b0-latest.json 的 domain+标的,crypto 且非主流白名单=按小市值处理;
#   且只对可能误杀真实价格动作的 rc 启用(疑问句/缺价格腿/vanity/悬念疑问),形态明确的撤因不走此闸。
if [ "$ACT" = "cull" ]; then
  _MEME=$(python3 - "$ID" "$RC" "$(cd "$(dirname "$0")" && pwd)" <<'PYEOF' 2>/dev/null
import sys,os,json,re
tid,rc=sys.argv[1],sys.argv[2]
GUARD={'缺价格腿','缺诱因-未达线','灌水-vanity指标','灌水-悬念疑问'}   # v3.6.1 移出「疑问句-悬念」;v3.6.2 加「缺诱因-未达线」,放行条件改为四查全否
if rc not in GUARD: print("0"); raise SystemExit
_mp=os.environ.get('MAJORS_JSON') or os.path.expanduser('~/.trend-scout/majors.json')
try: MAJORS=set(json.load(open(_mp))['majors'])   # v3.1.4(提案5-3) 单一事实源,不再内嵌副本
except Exception: MAJORS=set()                    # 读不到=全按小币处理(保守方向)
_snap=os.environ.get('B0JSON') or os.path.expanduser('~/.trend-scout/b0-latest.json')  # v3.1.2 可注入,便于回归
try: rows=json.load(open(_snap))
except Exception: print("1"); raise SystemExit          # 快照读不到 → 保守当 meme,宁可拦
rows=rows if isinstance(rows,list) else (rows.get('topics') or rows.get('data') or [])
t=next((x for x in rows if str(x.get('id'))==tid), None)
if t is None: print("1"); raise SystemExit
# v3.4.4(P0-2) 作用域判定收归 lint.meme_scope(与 b0-cull.py 同一实现):只有能指认出小市值代币的题才受铁律保护
sys.path.insert(0, sys.argv[3] if len(sys.argv)>3 else os.path.expanduser('~/.trend-scout'))
import lint
try:
    import token_exist; _ex = token_exist.exists     # v3.6.0 方案B:认代币要有交易证据
except Exception:
    _ex = None                                          # 模块坏了=退回旧判据(保守方向)
print("1" if lint.meme_scope(t, _ex) else "0")
PYEOF
)
  # v3.6.2(09-30 用户定收紧 meme 铁律):不达豁免线且无硬事件的 meme 题可撤,但备注必须带「四查」行且四项全否——
  #   四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗ (24h±50%且币安合约成交≥1亿(11-06)｜24h全市场成交额>2亿美元只作佐证、不单独构成豁免(11-07 Q13)｜市值本轮首次突破整数关口｜硬事件);任一为 ✓ 即应留。
  if [ "$_MEME" = "1" ] && ! printf '%s' "$NOTE" | grep -qE '重复|证伪|事实错误' \
     && ! printf '%s' "$NOTE" | grep -qE '四查(:|：) *幅度✗ *成交额✗ *市值关口✗ *硬事件✗'; then
    echo "🚨 meme铁律(v3.6.2):crypto 小市值/meme 题用「$RC」撤,备注须带四查行且四项全否——四查:幅度✗ 成交额✗ 市值关口✗ 硬事件✗"
    echo "   (24h±50%且币安合约成交≥1亿(11-06)｜24h全市场成交额>2亿美元只作佐证、不单独构成豁免(11-07 Q13)｜市值本轮首次突破整数关口｜硬事件;任一为 ✓ 即应留);或撤因落 同标的重复/已证伪/事实错误"
    echo "   禁用撤因:核不了/市值小/纯投机/无叙事锚"; reject "meme撤因非法:$ID $RC"
  fi
fi

# 10-23 复盘:预告形态的题用「灌水-产品公告」撤(13473/13495 两次被复审员挑出)→ 拦,提示改「预告题-准入不过」;确非预告写「非预告:<理由>」
#   b0-cull 机械撤在写看板前已自查(_preview_guard),落账时不再重拦,免得看板已撤、台账被拒
if [ "$ACT" = "cull" ] && [ "$RC" = "灌水-产品公告" ] && ! printf '%s' "$NOTE" | grep -qE '非预告(:|：)|b0-cull机械撤'; then
  _PV=$(python3 -c '
import sys,os,json
sys.path.insert(0, sys.argv[2]); import lint
try: d=json.load(open(os.environ.get("B0JSON") or os.path.expanduser("~/.trend-scout/b0-latest.json")))
except Exception: print("0"); raise SystemExit
rows=d if isinstance(d,list) else (d.get("topics") or [])
t=next((x for x in rows if str(x.get("id"))==sys.argv[1]), None)
print("1" if t and lint.preview_misfiled("灌水-产品公告", t.get("title") or t.get("original_title")) else "0")
' "$ID" "$(cd "$(dirname "$0")" && pwd)" 2>/dev/null)
  if [ "$_PV" = "1" ]; then
    echo "🚨 预告形态(将于/本月将/待揭晓…)的题不该记「灌水-产品公告」——按预告题准入三档判,不过用「预告题-准入不过」;确非预告在备注写「非预告:<理由>」"
    reject "预告题错码:$ID $RC"
  fi
fi

# 10-29 复盘(13658):四查③市值关口按「本轮首次突破」判,「已跌回关口下」不是 ✗ 的理由
if printf '%s' "$NOTE" | grep -q '市值关口✗'; then
  _MG=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[2]); import lint; r=lint.mcap_gate_misjudged(sys.argv[1]); print(r or "")' "$NOTE" "$(cd "$(dirname "$0")" && pwd)" 2>/dev/null)
  if [ -n "$_MG" ]; then
    echo "🚨 $_MG"
    reject "市值关口判据用错:$ID $RC"
  fi
fi

# 10-27 复盘(13585):四查成交额格按题面判——备注写「成交额✓」而题面没主张成交额(标题无「成交」)→ 拦;来源主张的写「来源主张成交额:<出处>」放行
if [ "$ID" != "-" ] && printf '%s' "$NOTE" | grep -q '成交额✓'; then
  _VC=$(python3 -c '
import sys,os,json
sys.path.insert(0, sys.argv[3]); import lint
try: d=json.load(open(os.environ.get("B0JSON") or os.path.expanduser("~/.trend-scout/b0-latest.json")))
except Exception: print("0"); raise SystemExit
rows=d if isinstance(d,list) else (d.get("topics") or [])
t=next((x for x in rows if str(x.get("id"))==sys.argv[1]), None)
print("1" if t and lint.vol_claim_unsupported(t.get("title") or t.get("original_title"), sys.argv[2]) else "0")
' "$ID" "$NOTE" "$(cd "$(dirname "$0")" && pwd)" 2>/dev/null)
  if [ "$_VC" = "1" ]; then
    echo "🚨 四查②按题面判(gates A闸 meme 行):标题没主张成交额,成交额格应记 ✗,不能拿实测成交额补成 ✓;来源确有主张写「来源主张成交额:<出处>」"
    reject "成交额格非题面:$ID $RC"
  fi
fi

# v3.7.0 预检模式:全部闸已过,不落账。topic.py 写看板前先跑这一遍,写成功后再正式落账(届时有真实 id)。
#   顺序从「先记账后写」改为「预检→写→立刻记账」:create 行终于能带真实 id;10-14 那种「记账被拒、看板已改」也不再可能。
if [ -n "$LA_CHECK" ]; then echo "✔ check $ACT $ID [$RC]"; exit 0; fi

# v3.5.1(09-20 Evose 第十七轮机制空跑实证):写入失败必须炸,不许打✔。
#   旧版 printf >> "$F" 失败后无条件执行下一行 echo "✔",于是目录缺失/无权限/磁盘满时
#   stderr 有 "No such file or directory"、stdout 却是「✔ note 0 [留档]」且 EXIT=0——
#   整个跑单的强制力建立在「写操作一律走 log-action.sh」+ 双留档上,这个假成功把强制力直接掏空。
if ! printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date +%s)000" "$ACT" "$ID" "$RC" "$NOTE" "$DELTA" >> "$F" 2>/dev/null; then
  echo "🚨 台账写入失败:$F 不可写(目录缺失/无权限/磁盘满)——本条写操作**未落账**,双留档已断" >&2
  echo "   不要当作已记账:若照旧版的「✔」继续跑,这条操作在台账里永远不存在" >&2
  exit 3
fi
echo "✔ $ACT $ID [$RC]${DELTA:+ | $DELTA}"

# v2.9.73:cull 自动补写快照——不依赖手写,否则 status 变迁链断在撤的那一步、误撤率永远算不出
# (实证:11774 只有 status=0 一条、11711 完全无快照,08-23~29 周报因此 n/a)
if [ "$ACT" = "cull" ] && [ "$ID" -eq "$ID" ] 2>/dev/null; then
  if [ "$ID" -gt 10000000000 ]; then DOM=tradfi; else DOM=crypto; fi
  if ! printf '%s\t%s\t%s\t3\t%s\n' "$(date +%s)000" "$ID" "$DOM" "auto-snap@cull[$RC]" >> "${SNAPSHOTS:-$DIR/snapshots.tsv}" 2>/dev/null; then
    echo "🚨 快照写入失败:${SNAPSHOTS:-$DIR/snapshots.tsv} 不可写——本条 cull 的 status 变迁链已断,误撤率算不出(v2.9.73 立此补写的本意)" >&2
    exit 3
  fi
  echo "  ↳ 已自动补快照 status=3 ($DOM)"
fi
