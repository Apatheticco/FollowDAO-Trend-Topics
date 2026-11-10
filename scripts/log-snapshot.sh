#!/bin/bash
# log-snapshot.sh — trend-scout 双留档辅助 (v2.9.31 配套)
# 目的: 消灭两个已发生过的静默退化——手拍时间戳漂移(~74min)、逐题行退化成单行摘要(08-04~08-05 六轮报废)
#
# 用法:
#   1) 逐题快照 (stdin 每行: id domain status [note], 空格分隔):
#        echo "11237 crypto 0
#        10000002524 tradfi 2 新建" | ~/.trend-scout/log-snapshot.sh snap
#   2) JSON 直灌 (list_trending_topics 原始返回存成文件后):
#        ~/.trend-scout/log-snapshot.sh json /path/to/b0.json
#   3) 收尾打点 last-refresh:
#        ~/.trend-scout/log-snapshot.sh refresh
#
# 特性: 时间戳统一取当前 $(date +%s000) 不许手拍; 格式不合规的行**大声拒绝**并非零退出, 防静默降级。

set -u
DIR="$HOME/.trend-scout"
SNAP="$DIR/snapshots.tsv"
REFRESH="${REFRESH_FILE:-$DIR/last-refresh.txt}"
CHECKLIST="${CHECKLIST_FILE:-$DIR/current-checklist.tsv}"
TS=$(date +%s000)

case "${1:-}" in
  snap)
    ok=0; bad=0
    while IFS= read -r line; do
      [ -z "$(echo "$line" | tr -d '[:space:]')" ] && continue
      id=$(echo "$line" | awk '{print $1}')
      domain=$(echo "$line" | awk '{print $2}')
      status=$(echo "$line" | awk '{print $3}')
      note=$(echo "$line" | awk '{$1=$2=$3=""; sub(/^ +/,""); print}')
      [ -z "$note" ] && note="-"
      if ! echo "$id" | grep -qE '^[0-9]+$'; then echo "REJECT(id非数字): $line" >&2; bad=$((bad+1)); continue; fi
      if ! echo "$domain" | grep -qE '^(crypto|tradfi)$'; then echo "REJECT(domain须crypto/tradfi): $line" >&2; bad=$((bad+1)); continue; fi
      if ! echo "$status" | grep -qE '^[0-3]$'; then echo "REJECT(status须0-3): $line" >&2; bad=$((bad+1)); continue; fi
      printf '%s\t%s\t%s\t%s\t%s\n' "$TS" "$id" "$domain" "$status" "$note" >> "$SNAP"
      ok=$((ok+1))
    done
    echo "snapshots: +${ok} 行 @ ${TS}$([ $bad -gt 0 ] && echo " | ⚠️ 拒绝 ${bad} 行(见 stderr)")"
    [ $bad -gt 0 ] && exit 1 || exit 0
    ;;
  json)
    f="${2:?用法: log-snapshot.sh json <b0.json>}"
    # v2.9.81: note 列存 keywords(周报叙事聚类用);无 keywords 填 "-"
    # v3.4.3 去掉 jq 依赖(Evose 沙箱装不上 jq,09-10 首轮 Lead 只能手工仿写 148 行快照)。python3 逐字节复刻原表达式:
    #   jq -r --arg ts "$TS" '.topics[] | [$ts, (.id|tostring), .domain, (.status|tostring), ((.keywords // "-") | if .=="" then "-" else . end)] | @tsv'
    n=$(python3 -c 'import sys,json
def tostr(v): return v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,separators=(",",":"))
def cell(v):
    if v is None: return ""
    if isinstance(v,bool): return "true" if v else "false"
    if isinstance(v,(int,float)): return json.dumps(v)
    if isinstance(v,str): return v.replace("\\","\\\\").replace("\t","\\t").replace("\n","\\n").replace("\r","\\r")
    sys.stdout.flush(); sys.exit("log-snapshot: %s 不能写进 tsv 单元格" % type(v).__name__)
out=sys.stdout.buffer
for t in json.load(open(sys.argv[2],encoding="utf-8"))["topics"]:
    k=t.get("keywords")
    if k is None or k is False or k=="": k="-"
    out.write(("\t".join(cell(x) for x in [sys.argv[1],tostr(t.get("id")),t.get("domain"),tostr(t.get("status")),k])+"\n").encode("utf-8"))' "$TS" "$f" | tee -a "$SNAP" | wc -l | tr -d ' ')
    echo "snapshots: +${n} 行 @ ${TS} (json 直灌)"
    ;;
  refresh)
    # 10-24 复盘:18:07 轮在 checklist verify 不通过时先写了 refresh,下一轮判模式/增量过滤就以未收尾的轮次为准。
    #   current-checklist.tsv 还在=本轮没 verify 归档 → 拒写;确需写(放弃本轮)用 REFRESH_FORCE=1。
    if [ -f "$CHECKLIST" ] && [ -z "${REFRESH_FORCE:-}" ]; then
      echo "🚨 本轮清单未 verify(仍在 $CHECKLIST)——先 checklist.sh verify 通过再写 refresh;放弃本轮用 REFRESH_FORCE=1" >&2; exit 1
    fi
    echo "$TS" >> "$REFRESH"
    echo "last-refresh: ${TS} ($(date '+%Y-%m-%d %H:%M:%S'))"
    ;;
  *)
    echo "用法: log-snapshot.sh snap|json <file>|refresh" >&2; exit 1
    ;;
esac
