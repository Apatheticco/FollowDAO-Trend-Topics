#!/bin/bash
# weekly-verify.sh — 周报完整性门禁(v3.0.4)。lark-push.py weekly 调用;任一缺项 exit 1 不得推送。
# 治的病:weekly-review.md 第 4/5 步(规则卫生+四问梳理)是散文,09-04 周报整体漏跑——第 0 层能跑是因为它是 metrics.py 一条命令。
# 用法: weekly-verify.sh <周报文件> [天数=7]     环境: ACTIONS=<actions.tsv 路径> 可覆盖(测试用)
F="$1"; DAYS="${2:-7}"; A="${ACTIONS:-$HOME/.trend-scout/actions.tsv}"
[ -f "$F" ] || { echo "用法: weekly-verify.sh <reports/weekly-*.md> [天数]"; exit 1; }
miss=0
need(){ grep -qE "$1" "$F" || { echo "❌ 缺:$2"; miss=$((miss+1)); }; }
# 第 0 层(metrics.py 六段)
need '^## ① 用户点名' '第0层① 用户点名'
need '^## ② 团队打回率' '第0层② 团队打回率'
need '^## ③ 撤题' '第0层③ 撤因TOP'
need '^## ④ 复审员挑战' '第0层④ 复审员挑战'
need '^## ⑤ 返工率' '第0层⑤ 返工率'
need '^## 规则体积' '第0层 规则体积'
# 第 4 步 规则卫生
need '^## 规则卫生' '第4步 规则卫生(反例护栏满30天沉降清单,无则写「本周无」)'
# 第 5 步 四问——四个段名必须都在,每段可写「本周无」但不能没有段
need '^## ① 过期' '第5步 四问① 过期'
need '^## ② 矛盾' '第5步 四问② 矛盾'
need '^## ③ 被实践推翻' '第5步 四问③ 被实践推翻'
need '^## ④ 冗余' '第5步 四问④ 冗余'
need '^## 行数体检' '第5步 行数体检'
grep -qE '^## 行数体检' "$F" && { grep -A6 '^## 行数体检' "$F" | grep -qE '散点[^0-9]{0,8}[0-9]+' || { echo "❌ 行数体检没有散点数(scatter.py 真量,不是写「正常」;v3.4.4 体积口径二选一=散点,gates.md KB 只作提示)"; miss=$((miss+1)); }; }
need '(排序建议|规则集本周无梳理项)' '第5步 产出=梳理提案排序 或 明写「规则集本周无梳理项」'
# 本周每条 rulefix 都必须被回看:从台账抽版本号,逐个在周报里找
cut=$(( ($(date +%s) - DAYS*86400) * 1000 ))
vers=$(awk -F'\t' -v c="$cut" '$1+0>=c && $2=="rulefix" {print $5}' "$A" 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+[a-z]?' | awk '!s[$0]++')
nv=0; for v in $vers; do nv=$((nv+1)); grep -q "$v" "$F" || { echo "❌ 本周 rulefix $v 未在周报里回看(台账有这版,周报一字未提)"; miss=$((miss+1)); }; done
# 11-07 复盘(第5步四问只按本周证据倒推、没逐条通读,本脚本照样放行):周报须有「通读完成:」行,且列到 SKILL/gates/channels.json 与 references 下每个 .md
RD="${RULES_DIR:-$HOME/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic}"
rl=$(grep -m1 '通读完成:' "$F")
if [ -z "$rl" ]; then echo "❌ 缺:第5步 规则全量通读的「通读完成: 文件:行数」行(只按证据倒推不算通读,11-07)"; miss=$((miss+1))
else for nm in SKILL.md gates.md channels.json $(ls "$RD/references" 2>/dev/null | grep -E '\.md$' | grep -v '^gates\.md$'); do
  case "$rl" in *"$nm"*) ;; *) echo "❌ 通读完成行未列 $nm"; miss=$((miss+1));; esac; done; fi
if [ "$miss" -gt 0 ]; then echo "🚨 周报不完整($miss 项)——补齐再推,与 checklist verify 拦报告同级"; exit 1; fi
echo "✅ 周报完整｜第0层六段｜规则卫生｜四问四段+行数体检｜本周 rulefix $nv 版全部回看"
