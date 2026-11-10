#!/bin/bash
# v2.9.70 通道齐备清单——先列全清单再打勾;verify 不过不得出报告(对偶 log-snapshot.sh)
DIR="$HOME/.trend-scout"; F="${CHECKLIST:-$DIR/current-checklist.tsv}"; LOG="$DIR/checklists.log.tsv"
case "$1" in
start)
  # v2.9.76:模板从 channels.json 生成——通道清单单一事实源,改通道只改 json
  MODE="$2"; CH="$DIR/channels.json"
  { [ "$MODE" = "首扫" ] || [ "$MODE" = "刷新" ]; } || { echo "用法: checklist.sh start 首扫|刷新"; exit 1; }
  [ -f "$CH" ] || { echo "🚨 无 channels.json——单一事实源缺失,不得开跑"; exit 1; }
  { echo "# mode=$MODE ts=$(date +%s)000 src=channels.json"
    python3 - "$CH" "$MODE" <<'PYEOF'
import json,sys
d=json.load(open(sys.argv[1])); mode=sys.argv[2]
for c in d['channels']:
    if c['mode']=='both' or c['mode']==mode:
        print(c['key']+'\tTODO')
PYEOF
  } > "$F"
  N=$(grep -vc '^#' "$F")
  [ "$N" -ge 10 ] || { echo "🚨 生成仅 $N 项,channels.json 疑似损坏"; rm -f "$F"; exit 1; }
  echo "清单已落 $F ($MODE $N 项,全部 TODO,源=channels.json)";;
channels)
  python3 - "$DIR/channels.json" <<'PYEOF'
import json,sys
d=json.load(open(sys.argv[1]))
print("channels.json %s | 共%d通道" % (d['_meta']['version'], len(d['channels'])))
for c in d['channels']:
    tag='[首扫]' if c['mode']=='首扫' else '[both]'
    print("  %s %s: %s" % (tag, c['key'], c['call']))
    if c.get('guard'): print("         ⚠️ "+c['guard'])
    if c.get('fallback'): print("         🛟 "+c['fallback'])
PYEOF
  ;;
mark)
  KEY="$2"; VAL="$3"
  [ -f "$F" ] || { echo "❌ 无 current-checklist.tsv,先 start"; exit 1; }
  case "$VAL" in ✅*|❌*|⚠️*) ;; *) echo "❌ 状态必须以 ✅/❌/⚠️ 开头(✅须带计数,❌须带兜底)"; exit 1;; esac
  # 11-07 复盘(Q14=A 落脚本):TG 通道从全源 news 抽 TG 条目,0 条只能记 ⚠️——本周 6 轮未单拉却记 ✅
  case "$KEY" in TG*) case "$VAL" in "✅(0"*|"✅(0:"*|"✅(0,"*|"✅(0)"*) echo "❌ TG 条目 0 条只能记 ⚠️ 半盲(11-07 Q14),不得 ✅"; exit 1;; esac;; esac
  awk -F'\t' -v k="$KEY" -v v="$VAL" 'BEGIN{OFS="\t"; n=0} !/^#/ && index($1,k)>0 {$2=v; n++} {print} END{exit (n==0)}' "$F" > "$F.tmp"
  if [ $? -eq 0 ]; then mv "$F.tmp" "$F"; echo "✔ $KEY ← $VAL"
  else rm -f "$F.tmp"; echo "❌ 未匹配到通道: $KEY (checklist.sh show 查行名)"; exit 1; fi;;
verify)
  [ -f "$F" ] || { echo "🚨 无清单文件——本轮没跑 start,不得出报告"; exit 1; }
  BAD=$(awk -F'\t' '
    /^#/ {next}
    $2=="TODO" {print "未填: "$1; next}
    $2 ~ /^✅/ && $2 !~ /[0-9]/ {print "✅无计数证据(v2.9.19 虚报视同❌): "$1; next}
    $2 ~ /^❌/ && length($2)<6 {print "❌无兜底/半盲说明: "$1; next}
  ' "$F")
  # v2.9.82: log-action 拒写留痕(actions-rejected.tsv)晚于本轮开跑 → 台账可能缺行,不得出报告
  # v3.7.0: 不再要求删行(删了周报就数不出工具拦了几次)。同动作同 id 其后已落账=自动算已处理;
  #   改判不写/换了 id 的用 `log-action.sh reject-ok <ts> <说明>` 显式标。topic.py 写成功但落账失败的进 actions-unlogged.tsv,同一判据。
  RUNTS=$(head -1 "$F" | grep -oE 'ts=[0-9]+' | cut -d= -f2)
  if [ -n "$RUNTS" ]; then
    RJ=$(python3 "$DIR/ledger.py" unresolved "$RUNTS" 2>&1)
    [ -n "$RJ" ] && BAD="$BAD"$'\n'"拒写/未落账未处理(其后同动作同 id 落账即自动处理;否则 log-action.sh reject-ok <ts> <说明>): "$'\n'"$RJ"
  fi
  if [ -n "$BAD" ]; then echo "🚨 verify 不通过,不得出报告:"; echo "$BAD"; exit 1; fi
  # v3.6.2(09-29 Evose 第 46 轮):沙箱里整套回归要 11 分钟(本机 19 秒),而 Evose 脚本每轮都是同一个发布包。
  #   evose-round.py close 核过「沙箱脚本与打包时本机跑过回归的那一份逐个一致」才设 CHECKLIST_SKIP_TESTS;本机从不设。
  if [ -n "$CHECKLIST_SKIP_TESTS" ]; then echo "⏭ 回归跳过:$CHECKLIST_SKIP_TESTS"
  else "$DIR/run-tests.sh" || { echo "🚨 规则回归失败——先修 lint/枚举再出报告(v2.9.83)"; exit 1; }; fi
  cat "$F" >> "$LOG"; echo "---" >> "$LOG"; rm -f "$F"
  echo "✅ 清单齐备,已归档 $LOG";;
show) cat "$F" 2>/dev/null || echo "(无进行中清单)";;
*) echo "用法: checklist.sh start 首扫|刷新 | channels | mark <通道关键字> '✅(计数)/❌兜底/⚠️半盲' | verify | show";;
esac
