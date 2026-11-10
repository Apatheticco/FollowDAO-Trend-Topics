#!/bin/bash
# v2.9.79 复审员覆盖率对账——它的输出id集必须⊇本轮actions写操作id集;缺行=复审未完成不得出报告
# v3.0.4 每次结果落 review-verify.log.tsv,lark-push.py send 据此拒发未对账的轮次
# v3.0.6 台账自取契约:复审员必须自己取台账并报 LEDGER 行,治「喂料权又退回被评审者」
# 用法: review-verify.sh <run_ts_ms起点> <复审员输出文件>
TS="$1"; F="$2"; A="${ACTIONS:-$HOME/.trend-scout/actions.tsv}"; LOG="${RVLOG:-$HOME/.trend-scout/review-verify.log.tsv}"
# v3.3.9 时间上界:此前 awk 只有 $1>=TS 没有上界,**重跑任何旧轮次都会把后续所有轮的写操作算进来判 FAIL**
#   (09-09 15:50 实证:重跑 09:40 轮报「覆盖不全 8/38」,那 8 条全是 14:40 轮的),并把 FAIL 写进日志,
#   让 lark-push 的 _rv_passed 门禁把一个当时明明 PASS 的轮次拒发。上界=下一轮 checklist start,取自 checklists.log。
CL="${CHECKLOG:-$HOME/.trend-scout/checklists.log.tsv}"
TS_HI="${RV_UNTIL:-$(grep -o 'ts=[0-9]*' "$CL" 2>/dev/null | cut -d= -f2 | awk -v t="$TS" '$1+0>t+0' | sort -n | head -1)}"
[ -n "$TS_HI" ] || TS_HI=9999999999999
[ -f "$F" ] || { echo "用法: review-verify.sh <run_ts_ms> <复审员输出文件>"; exit 1; }
log(){ printf "%s\t%s\t%s\t%s\n" "$(date +%s)000" "$TS" "$1" "$2" >> "$LOG"; }

MY_IDS=$(awk -F'\t' -v t="$TS" -v h="$TS_HI" '$1+0>=t && $1+0<h && $2 ~ /^(create|cull|update|restore|merge|publish)$/ && $3!="-" {print $3}' "$A" | sort -u)
# v3.5.7(09-24):建题先记账后建题,create 行 id 只能记「-」,真实 id 落在同轮「状态修正/建题后推status=0」行。
#   旧版把「-」算进 MY_IDS,而下面 L_IDS 用 tr -dc 0-9 滤掉了「-」→ 任何有建题的轮次都必然 FAIL;
#   09-24 14:47 轮复审员为过这道闸把台账 create 行私改成 note(第3376行,已恢复)。改为:「-」不进 id 清单,
#   但每条 create - 必须有同轮 update 状态修正 行对应,数量不够即 FAIL。
DASH_N=$(awk -F'\t' -v t="$TS" -v h="$TS_HI" '$1+0>=t && $1+0<h && $2=="create" && $3=="-"' "$A" | grep -c .)
PUB_N=$(awk -F'\t' -v t="$TS" -v h="$TS_HI" '$1+0>=t && $1+0<h && $2=="update" && $4=="状态修正" && $5 ~ /建题后推/' "$A" | grep -c .)
if [ "$DASH_N" -gt "$PUB_N" ]; then echo "❌ create 行 id=「-」共 $DASH_N 条,但同轮「状态修正·建题后推」只有 $PUB_N 条——建题无法对应到真实 id"; exit 1; fi
TOTAL=$(echo "$MY_IDS" | grep -c . )
MISS=0
for id in $MY_IDS; do grep -q "$id" "$F" || { echo "❌ 复审员未覆盖: $id"; MISS=$((MISS+1)); }; done
# v3.7.20(11-02):干轮也要归档——原先这里 exit 0 在尾部 cp 之前,reports/review-<ts>.md 不存在,Evose challenges 找不到就停下
#   (11-02 11:20 演练看门一那轮全弃建、0 写操作,复审交回后整轮卡死 57 分钟,看门三接手又撞一次)
RD="${REPORTS_DIR:-$HOME/.trend-scout/reports}"; mkdir -p "$RD"
archive(){ cp "$F" "$RD/review-$TS.md" && touch "$RD/review-$TS.md" && echo "📁 已归档 $RD/review-$TS.md(供 lark-push 对账)"; }
[ "$TOTAL" -eq 0 ] && { echo "⚠️ 该时间窗无写操作"; log PASS "干轮无写操作"; archive; exit 0; }
if [ "$MISS" -gt 0 ]; then echo "🚨 复审覆盖不全($MISS/$TOTAL 缺失)——重跑复审员补审,不得出报告"; log FAIL "覆盖不全 $MISS/$TOTAL"; exit 1; fi

# ── v3.0.6 台账自取契约 ──────────────────────────────────────────────
# 病:v2.9.77 定「复审员自己动手取数,我只给源摘要」,但 09-04 三轮我都直接贴决策表全文,
#    它没跑过一次 awk——评审材料又回到被评审者手里,v2.9.81 抽样自检只治了一半。
# 判据形状: LEDGER=<本轮台账总行数>|<其中note行数>|<自取到的写操作id,逗号分隔>
#   区分「真读台账」vs「抄送审清单」的关键=note 行：台账里有(自审七查/弃建/复审员挑战),送审清单里没有。
LED=$(grep -oE '^LEDGER=.*' "$F" | head -1)
[ -n "$LED" ] || { echo "🚨 复审员未输出 LEDGER= 行(v3.0.6 台账自取契约)——它没自己取台账,审的仍是我写的送审清单"; log FAIL "无LEDGER行"; exit 1; }
LB=${LED#LEDGER=}
L_TOT=$(echo "$LB" | cut -d'|' -f1 | tr -dc '0-9'); L_NOTE=$(echo "$LB" | cut -d'|' -f2 | tr -dc '0-9')
# v3.6.1(09-28):演练的新建题没有真实题号,Evose log-writer 记为 NEW-<k>;旧版 tr -dc 0-9 把 NEW-1 截成 1,② 必然报「LEDGER 未含写操作 id」(第 44 轮卡在此)
L_IDS=$(echo "$LB" | cut -d'|' -f3 | tr ',' '\n' | sed 's/[^0-9A-Za-z-]//g' | grep -E '^([0-9]+|NEW-[0-9]+)$' | sort -u)
[ -n "$L_TOT" ] && [ -n "$L_NOTE" ] || { echo "🚨 LEDGER 形状错,应为 LEDGER=<总行数>|<note行数>|<id,id,...>,实得: $(echo "$LED"|cut -c1-80)"; log FAIL "LEDGER形状错"; exit 1; }
MY_TOT=$(awk -F'\t' -v t="$TS" -v h="$TS_HI" '$1+0>=t && $1+0<h && NF>=5' "$A" | wc -l | tr -d ' ')
MY_NOTE=$(awk -F'\t' -v t="$TS" -v h="$TS_HI" '$1+0>=t && $1+0<h && $2=="note"' "$A" | wc -l | tr -d ' ')
# ① 窗口对不对(先查这条:窗口错会让 ②③ 刷出几十行噪音,把根因埋掉——09-04 实跑实证)
#    容差 +3:复审员先跑、主进程后落 note(复审员挑战/自审发现),它读到的行数可能略少
if [ "$L_TOT" -gt $((MY_TOT + 3)) ]; then
  echo "❌ LEDGER 窗口错:报 $L_TOT 行,本轮实为 $MY_TOT 行——awk 条件没生效(用 \$1+0>=<RUN_TS> 强制数值比较),读成了整份台账"
  echo "🚨 台账自取契约不过——重跑复审员,把窗口对上,不得出报告"; log FAIL "窗口错 $L_TOT vs $MY_TOT"; exit 1
fi
# ② 自取窗口够不够:它报的写操作 id 必须盖住我算的全集
for id in $MY_IDS; do echo "$L_IDS" | grep -qx "$id" || { echo "❌ LEDGER 未含写操作 id: $id(自取窗口错或未真取)"; MISS=$((MISS+1)); }; done
# ③ 自取到就必须审:它从台账捞出来的 id,每个都要有裁决行(治「捞到我漏送的题却不吭声」);超 5 条折叠
UN=""; UNN=0
for id in $L_IDS; do grep -qE "^${id}\|" "$F" || { UNN=$((UNN+1)); [ "$UNN" -le 5 ] && UN="$UN $id"; }; done
if [ "$UNN" -gt 0 ]; then
  ext=""; [ "$UNN" -gt 5 ] && ext="…等 $UNN 条"
  echo "❌ LEDGER 自取到但无裁决行:$UN$ext——自取到就必须审(v2.9.77 防送审清单漏报的原意)"; MISS=$((MISS+1))
fi
# ④ note 行数:台账有 note 而它报 0 = 它读的是送审清单不是台账(送审清单里没有 note)
if [ "$MY_NOTE" -gt 0 ] && [ "$L_NOTE" -eq 0 ]; then
  echo "❌ 台账本轮有 $MY_NOTE 条 note 行,LEDGER 报 0——送审清单里没有 note,报 0 说明读的不是台账"; MISS=$((MISS+1))
fi
[ "$L_TOT" -lt "$TOTAL" ] && { echo "❌ LEDGER 总行数 $L_TOT < 写操作数 $TOTAL,不自洽"; MISS=$((MISS+1)); }
if [ "$MISS" -gt 0 ]; then echo "🚨 台账自取契约不过($MISS 项)——重跑复审员,让它自己 awk 台账,不得出报告"; log FAIL "LEDGER不过 $MISS 项"; exit 1; fi

# v2.9.81 抽样自检契约——≥30%(≥3条,不足则全量)自己重检索
SAMP=$(grep -oE '^SAMPLED=.*' "$F" | tail -1)   # v3.4.1: 取末条——复审员按契约只追加不覆盖,head -1 让它永远改不了清单(09-10 实证多跑 2 趟纯格式往返)
[ -n "$SAMP" ] || { echo "🚨 复审员未输出 SAMPLED= 行(v2.9.81 抽样自检契约)——重跑复审员,不得出报告"; log FAIL "无SAMPLED行"; exit 1; }
# v2.9.82: 只把理由行含「自检:」的抽样 id 计数(09-03 实证 17 报 3 真)
# v3.0.8: 全角冒号一并认——中文输出天然写「自检：」,09-04 实跑 5 条真自检全被判 0(判据形状歧视了正确行为)
NS=0; FAKE=""
for sid in $(echo "${SAMP#SAMPLED=}" | tr ',' ' '); do
  sid=${sid%%(*}; sid=${sid%%（*}   # 11-03:复审员写「10000003452(EVGO)」,括号进 grep -E 报 parentheses not balanced、该条被误判无自检
  [ -n "$sid" ] || continue
  if grep -E "^${sid}\|" "$F" | grep -qE "自检[:：]"; then NS=$((NS+1)); else FAKE="$FAKE $sid"; fi
done
[ -n "$FAKE" ] && echo "⚠️ 抽样行无「自检:／自检：」原句,不计入:$FAKE"
NEED=$(( (TOTAL*3+9)/10 )); [ "$NEED" -lt 3 ] && NEED=3; [ "$NEED" -gt "$TOTAL" ] && NEED=$TOTAL
[ "$NS" -ge "$NEED" ] || { echo "🚨 抽样不足: 复审员自检 $NS 条 < 要求 $NEED 条(≥30% 且 ≥3)"; log FAIL "抽样 $NS<$NEED"; exit 1; }
# v3.0.9 裁决词歧义哨兵(不阻断):09-04/09-05 连续两轮,复审员把「你撤对了」写成「挑战」。
#   「挑战」歧义=既可读作挑战这条题、也可读作挑战我的处置,写进 prompt 说明没治住,已在 review-agent.md 换词为「处置有误」。
#   这里兜底:判否定却通篇肯定词的行捞出来提示复核。存在「撤对了但 rc 贴错」这类合法的部分否定,故只 WARN。
SUS=$(grep -E "^[0-9]+\|(挑战|处置有误)\|" "$F" | grep -cE "准确|贴切|成立|确实|正确|无误" || true)
[ "${SUS:-0}" -gt 0 ] && echo "⚠️ 裁决词存疑 $SUS 行:判「挑战/处置有误」但理由含肯定词(准确/贴切/成立/确实/正确)——逐行复核它到底反对什么,别当成真分歧落账(v3.0.9)"
echo "✅ 复审覆盖完整($TOTAL/$TOTAL)｜台账自取 $L_TOT 行(note $L_NOTE)✔｜抽样自检 $NS 条 ✔"; log PASS "覆盖 $TOTAL 台账 $L_TOT/note$L_NOTE 抽样 $NS"
# v3.3.9 PASS 即归档:lark-push.py 只认 reports/review-* 作复审产物,而复审员输出常落在 /tmp。
#   09-03 16:41 之后 reports/ 再无 review-* 文件,于是**每张卡片都写「🚨 复审 未跑」**,而实际每轮都审了、这里都 PASS 了——
#   用户在群里看到的是假警报,持续 6 天没人发现(09-09 深度 review 时第一次去看渲染结果才抓到)。
#   归档文件名带 run_ts,mtime=现在,落在 lark-push 的 [run_ts-10min, round_end+15min] 判定窗内。
archive
