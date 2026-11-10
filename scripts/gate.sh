#!/bin/bash
# v2.9.81 判例库查表器——references/gates.md 是单一事实源,本脚本只做分节打印(route.sh 同模式)
# 用法: gate.sh list | gate.sh <闸名子串> | gate.sh grep <词> | gate.sh usage [天数]
G="${GATES:-$HOME/Desktop/FollowDAO-Trend-Topics/skills/create-trending-topic/references/gates.md}"
# v3.5.1:GATES 在 run-tests.sh/scatter.py 里是**目录**、在本脚本里是 gates.md **全路径**,
#   同名不同义。平时没人设 GATES、默认值各自正确所以一直没暴露,一旦要把脚本包装进
#   隔离环境跑回归就必炸。两种都认:传目录就自己补上 references/gates.md。
[ -d "$G" ] && G="$G/references/gates.md"
[ -f "$G" ] || { echo "🚨 无 gates.md: $G"; exit 1; }
USAGE="${GATE_USAGE:-$HOME/.trend-scout/gate-usage.tsv}"
# v3.7.1 查询计数:规则退役要有依据——「30 天没被查过」的闸才进退役候选。此前本脚本什么都不记(10-15 实测),退役无从谈起。
#   注意:被脚本强制的闸(lint/topic.py/log-action)不经本脚本也在起作用,零查询≠没用,只是「该复核要不要留」的信号。
logq(){ printf '%s\t%s\t%s\n' "$(date +%s)000" "$1" "$2" >> "$USAGE" 2>/dev/null; }
case "$1" in
usage)
  python3 - "$G" "$USAGE" "${2:-30}" <<'GUEOF'
import sys,time,collections
g,u,days=sys.argv[1],sys.argv[2],float(sys.argv[3])
names=[l[len('## 闸:'):].strip() for l in open(g,encoding='utf-8') if l.startswith('## 闸:')]
cut=(time.time()-days*86400)*1000; c=collections.Counter(); first=None
try:
    for l in open(u,encoding='utf-8'):
        x=l.rstrip('\n').split('\t')
        if len(x)>=3 and x[0].isdigit():
            first=first or int(x[0])
            if int(x[0])>=cut and x[1]=='gate': c[x[2]]+=1
except FileNotFoundError: pass
span=(time.time()*1000-first)/86400e3 if first else 0
print(f"近 {days:g} 天查询计数(记录始于 {span:.1f} 天前;记满 {days:g} 天前零查询只作参考):")
for n in sorted(names,key=lambda n:-c[n]): print(f"  {c[n]:4d}  {n}")
z=[n for n in names if c[n]==0]
print(f"零查询 {len(z)}/{len(names)}:{'、'.join(z) or '无'}")
GUEOF
  ;;
list)
  # v3.4.5 截断改按字符(python):原 awk substr/cut -c 按字节切,中文被切成半个字——实测 C 下 list 18/40 行、grep 19/51 行非法 UTF-8
  python3 - "$G" <<'PYEOF'
import sys
L=open(sys.argv[1],encoding='utf-8').read().split('\n'); out=[]
for i,x in enumerate(L):
    if not x.startswith('## 闸:'): continue
    k=x[len('## 闸:'):]; nxt=next((y for y in L[i+1:] if y.strip()),'').replace('**','')
    out.append(f"  {k:<8} {nxt[:80]}")
sys.stdout.buffer.write(('\n'.join(out)+'\n').encode('utf-8'))
PYEOF
  ;;
grep)
  [ -n "$2" ] || { echo "用法: gate.sh grep <词>"; exit 1; }
  logq grep "$2"
  grep -n -- "$2" "$G" | python3 -c 'import sys;sys.stdout.buffer.write("".join(l[:220]+"\n" for l in sys.stdin.buffer.read().decode("utf-8","replace").splitlines()).encode("utf-8"))';;
"") echo "用法: gate.sh list | gate.sh <闸名> | gate.sh grep <词>"; exit 1;;
*)
  n=$(grep -c "^## 闸:.*$1" "$G")
  [ "$n" -gt 0 ] || { echo "❌ 无此闸: $1 (gate.sh list 查)"; exit 1; }
  [ "$n" -gt 1 ] && echo "⚠️ 匹配 $n 个闸,全部打印:" && grep "^## 闸:.*$1" "$G"
  grep "^## 闸:.*$1" "$G" | sed 's/^## 闸://' | while IFS= read -r _g; do logq gate "$_g"; done
  awk -v k="$1" '/^## 闸:/{p=(index($0,k)>0)} p' "$G";;
esac
