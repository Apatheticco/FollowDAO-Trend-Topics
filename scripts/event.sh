#!/bin/bash
# v2.9.79 event-watch 工具化——治「到期项靠眼扫89行,漏一项报告就少一项」(08-31 Anthropic漏办实证)
# 文件仍 append-only;同主题多行取末行为当前态(与 circuit.sh 同模式)
DIR="${EV_DIR:-$HOME/.trend-scout}"; F="$DIR/event-watch.tsv"
today=$(date '+%Y-%m-%d')
case "$1" in
add)
  # event.sh add <date_et> <type> <主题> <时点> <关联id|—> <备注>
  D="$2"; T="$3"; K="$4"; W="$5"; R="$6"; N="$7"
  [ -n "$N" ] || { echo "用法: event.sh add <YYYY-MM-DD> <type> <主题> <时点> <关联id|—> <备注>"; exit 1; }
  echo "$D" | grep -qE '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' || { echo "🚨 日期格式 YYYY-MM-DD"; exit 1; }
  case "$T" in earnings|macro|policy|listing|unlock|review) ;; *) echo "🚨 type 枚举: earnings|macro|policy|listing|unlock|review"; exit 1;; esac
  printf '%s\t%s\t%s\t%s\t—\t%s\tpending\t%s\n' "$D" "$T" "$K" "$W" "$R" "$N" >> "$F"
  echo "✔ 入册: $D [$T] $K";;
due)
  # 到期清单:同主题末行为准,状态∈pending/review/tbd 且 date<=今天;末行输出机器可读 DUE=N
  # v3.7.20(11-02):due --since <run_ts_ms>——末行带「延后@<ms>」且 ms≥run_ts 的(本轮已 defer)不计入 DUE,另报 DEFERRED=
  S=""; [ "$2" = "--since" ] && S="$3"
  [ -f "$F" ] || { echo "DUE=0 (无文件)"; exit 0; }
  awk -F'\t' '!/^#/ && NF>=7 {last[$3]=$0} END{for(k in last) print last[k]}' "$F" | \
  awk -F'\t' -v today="$today" '$7=="pending"||$7=="review"||$7=="tbd"{ if($1<=today) print }' | sort > /tmp/ev_due.$$
  n=0; dn=0
  while IFS=$'\t' read -r d t k w v r st note; do
    dt=$(printf '%s' "$note" | grep -o '延后@[0-9]*' | tail -1 | grep -o '[0-9]*$')   # 不用 cut -c:UTF-8 区域下按字符切会错位
    if [ -n "$S" ] && [ -n "$dt" ] && [ "$dt" -ge "$S" ]; then dn=$((dn+1)); printf ' 延后. [%s|%s] %s ｜时点=%s\n' "$d" "$t" "$k" "$w"; continue; fi
    n=$((n+1))
    printf '%2d. [%s|%s] %s ｜时点=%s ｜关联=%s\n    %s\n' "$n" "$d" "$t" "$k" "$w" "$r" "${note:0:120}"
  done < /tmp/ev_due.$$
  rm -f /tmp/ev_due.$$
  echo "DUE=$n"
  [ -n "$S" ] && echo "DEFERRED=$dn"
  echo "⚠️ 每一项必须处置(建/update/close),checklist 的 event-watch 行填「DUE=$n,处置N项」——数字对不上=漏办";;
upcoming)
  # 未到期的 pending(前瞻视野)
  awk -F'\t' '!/^#/ && NF>=7 {last[$3]=$0} END{for(k in last) print last[k]}' "$F" | \
  awk -F'\t' -v today="$today" '($7=="pending"||$7=="tbd") && $1>today' | sort | \
  awk -F'\t' '{printf "   [%s|%s] %s ｜%s\n",$1,$2,$3,$4}';;
close)
  # event.sh close <主题子串> <done|missed> <备注> —— 取末行复制改状态追加
  K="$2"; ST="$3"; N="$4"
  [ -n "$N" ] || { echo "用法: event.sh close <主题子串> <done|missed> <备注>"; exit 1; }
  case "$ST" in done|missed) ;; *) echo "🚨 状态枚举: done|missed"; exit 1;; esac
  # 精确键优先,无精确匹配才子串(v2.9.79b:close "IREN" 曾误关同名长键行)
  M=$(awk -F'\t' -v k="$K" '!/^#/ && $3==k {last=$0} END{print last}' "$F")
  [ -n "$M" ] || M=$(awk -F'\t' -v k="$K" '!/^#/ && index($3,k)>0 {last=$0} END{print last}' "$F")
  [ -n "$M" ] || { echo "🚨 未匹配到主题: $K"; exit 1; }
  echo "$M" | awk -F'\t' -v st="$ST" -v n="$N" 'BEGIN{OFS="\t"} {$7=st; $8=$8"|关闭:"n; print}' >> "$F"
  echo "✔ 关闭[$ST]: $(echo "$M" | cut -f3)";;
defer)
  # v3.7.20(11-02 用户定):event.sh defer <主题> <备注> —— 到期但没到时点(如 23:00 数据、22:30 美股开盘)的延后:
  #   状态不变(仍是待办,下一轮 due 照列),末行备注追加「|延后@<毫秒>:备注」。治 Evose 为过收尾闸把未到时点的关成 missed(11-02 演练 5 项)
  K="$2"; N="$3"
  [ -n "$N" ] || { echo "用法: event.sh defer <主题子串> <备注>"; exit 1; }
  M=$(awk -F'\t' -v k="$K" '!/^#/ && $3==k {last=$0} END{print last}' "$F")
  [ -n "$M" ] || M=$(awk -F'\t' -v k="$K" '!/^#/ && index($3,k)>0 {last=$0} END{print last}' "$F")
  [ -n "$M" ] || { echo "🚨 未匹配到主题: $K"; exit 1; }
  echo "$M" | awk -F'\t' -v n="$N" -v t="$(date +%s)000" 'BEGIN{OFS="\t"} {$8=$8"|延后@"t":"n; print}' >> "$F"
  echo "✔ 延后: $(echo "$M" | cut -f3)";;
*) echo "用法: event.sh add <date> <type> <主题> <时点> <关联|—> <备注> | due [--since <run_ts>] | upcoming | close <主题> <done|missed> <备注> | defer <主题> <备注>";;
esac
