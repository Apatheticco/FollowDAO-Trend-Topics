#!/bin/bash
# v2.9.81 标题机械闸——写任何标题前跑;FAIL 则 exit 1。规则在 lint.py(单一事实源)
# 用法: lint-title.sh "<标题>" [tradfi|crypto]
[ -n "$1" ] || { echo "用法: lint-title.sh \"<标题>\" [tradfi|crypto]"; exit 2; }
exec python3 "$HOME/.trend-scout/lint.py" title "$1" "${2:-crypto}"
