#!/bin/bash
# v2.9.81 池子机器审计——输出待办清单(待审/48h窗口题/聚簇/标题闸/系统新建)
# 用法: b0-audit.sh --fetch [start end] [--since ms]   经 b0-fetch.py 直接拉 B0(默认昨天~今天,全状态,自动翻页)再审 ← 每轮默认路径
#       b0-audit.sh <b0.json> [--since ms]             审一份已存的 JSON
#       since 默认取 last-refresh.txt 末行(=上轮打点)
DIR="$HOME/.trend-scout"
if [ "$1" = "--fetch" ]; then
  shift; DATES=()
  while [ $# -gt 0 ] && [ "$1" != "--since" ]; do DATES+=("$1"); shift; done
  python3 "$DIR/b0-fetch.py" "${DATES[@]}" --out "$DIR/b0-latest.json" || exit 1
  F="$DIR/b0-latest.json"
else
  F="$1"; shift
fi
[ -f "$F" ] || { echo "用法: b0-audit.sh --fetch [start end] [--since ms] | b0-audit.sh <b0.json> [--since ms]"; exit 2; }
if [ "$1" != "--since" ]; then S=$(tail -1 "$DIR/last-refresh.txt" 2>/dev/null); set -- --since "${S:-0}"; fi
exec python3 "$DIR/lint.py" b0 "$F" "$@"
