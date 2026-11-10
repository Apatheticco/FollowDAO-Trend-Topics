#!/bin/bash
# v2.9.76 通道熔断状态文件化——治「会话级状态 cron 一来就丢」
# 状态存 append-only 日志(留审计链),get 取每通道末行为当前态
DIR="$HOME/.trend-scout"; F="$DIR/circuit-log.tsv"
now=$(date +%s)
# v3.4.3 跨平台:BSD `date -r <秒>` 在 Linux 是「取文件 mtime」,Evose 沙箱里时间列会变空;统一走 python
fmt_ts(){ python3 -c 'import sys,time
try: print(time.strftime("%m-%d %H:%M",time.localtime(int(sys.argv[1]))))
except Exception: pass' "$1" 2>/dev/null; }
case "$1" in
set)
  # circuit.sh set <通道> <ok|degraded|fused> <重探时点> <证据备注>
  # 重探时点: 小时数(如 4=4小时后) | next-firstscan(下次首扫重探) | -(无需重探)
  CH="$2"; ST="$3"; RT="$4"; NOTE="$5"
  [ -n "$NOTE" ] || { echo "用法: circuit.sh set <通道> <ok|degraded|fused> <小时数|next-firstscan|-> <证据备注>"; exit 1; }
  case "$ST" in ok|degraded|fused) ;; *) echo "🚨 状态枚举: ok|degraded|fused"; exit 1;; esac
  case "$RT" in
    next-firstscan|-) RTS="$RT";;
    *[!0-9]*) echo "🚨 重探时点须为小时数/next-firstscan/-"; exit 1;;
    *) RTS=$(( (now + RT*3600) * 1000 ));;
  esac
  [ "$ST" = "ok" ] && [ "$RTS" != "-" ] && RTS="-"
  printf '%s\t%s\t%s\t%s\t%s\n' "${now}000" "$CH" "$ST" "$RTS" "$NOTE" >> "$F"
  echo "✔ $CH ← $ST (重探=$RTS)";;
get)
  # 开跑必读:列每通道当前态;到重探时点/首扫重探的标 🔔
  MODE="${2:-}"  # 传"首扫"则 next-firstscan 的也标🔔
  [ -f "$F" ] || { echo "(无熔断记录,全通道视为 ok)"; exit 0; }
  awk -F'\t' '{last[$2]=$0} END{for(k in last) print last[k]}' "$F" | sort | \
  while IFS=$'\t' read ts ch st rt note; do
    [ "$st" = "ok" ] && continue
    flag=""
    if [ "$rt" = "next-firstscan" ]; then
      [ "$MODE" = "首扫" ] && flag="🔔本轮重探"
    elif [ "$rt" != "-" ] && [ "${rt%000}" -le "$now" ] 2>/dev/null; then
      flag="🔔已到重探时点"
    fi
    d=$(fmt_ts "${ts%000}")
    echo "⛔ $ch=$st [自$d] $flag | $note"
  done
  # 全 ok 时上面无输出,给个明确信号
  n=$(awk -F'\t' '{last[$2]=$3} END{c=0; for(k in last) if(last[k]!="ok") c++; print c}' "$F")
  [ "$n" -eq 0 ] && echo "✅ 全通道 ok"
  exit 0;;
history)
  CH="$2"; [ -n "$CH" ] || { echo "用法: circuit.sh history <通道>"; exit 1; }
  awk -F'\t' -v c="$CH" '$2==c' "$F" | while IFS=$'\t' read ts ch st rt note; do
    echo "$(fmt_ts "${ts%000}") $st (重探=$rt) $note"
  done;;
*) echo "用法: circuit.sh set <通道> <ok|degraded|fused> <小时|next-firstscan|-> <备注> | get [首扫] | history <通道>";;
esac
