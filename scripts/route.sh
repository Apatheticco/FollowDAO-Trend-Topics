#!/bin/bash
# v2.9.79 处置路由判定器——status×age→适用规则,单一事实源(SKILL §2 表已指针化)
# 用法: route.sh <status 0|1|2|3> <age_hours> [abs_deviation_pct]
S="$1"; AGE="$2"; DEV="$3"
[ -n "$AGE" ] || { echo "用法: route.sh <status> <age_hours> [deviation_pct]"; [ "$S" ] || exit 1; }
A=${AGE%%.*}
case "$S" in
0)
  if [ "$A" -le 8 ] 2>/dev/null; then
    echo "▶ status=0 ≤8h(轮内射程):"
    if [ -n "$DEV" ]; then
      D=$(echo "$DEV" | tr -d '%+-')
      B=$(awk -v d="$D" 'BEGIN{ if(d>=50)print "强撤(>50%反向=退场复查)"; else if(d>25)print "撤(>25%)"; else if(d>=10)print "升温update(≥10%)"; else print "容差内不动(<10%)" }')
      echo "  ↳ 偏差 ${DEV}% → $B"
    else
      echo "  偏差档:≥10%升温update ｜ >25%撤 ｜ >50%反向强撤"
    fi
    echo "  🟢 例外(11-03 用户定 Q9):纯行情币题(rc 纯行情-A定则)同方向且现读仍过 A 定则线(24h≥±50%且成交≥1亿;11-06 用户定由30%上调)→偏差多大都不动(不改不撤);跌破线→已证伪撤;方向反转→建反向新题并撤旧题"
    echo "  ⚠️ 三档只管数字——关系型修饰词(N连涨/新高/首次)失效不走百分比,单独验(v2.9.40)"
    echo "  A≤1灌水已上线直接撤(v2.9.2;meme豁免见A闸;带明确未来日期的预告可留)"
  else
    echo "▶ status=0 >8h: 🚫默认不管,当前行情→新建。破闸例外仅7项(v2.9.8集中):"
    echo "  ①事实错误(v2.9.4硬数字/定义词,客观可证) ②盘中反转错向(v2.9.6)"
    echo "  ③碎片/重复卫生(去重树) ④tag卫生(v2.9.5) ⑤命名样式(v2.9.43 ticker化)"
    echo "  ⑥过期题(gate.sh 过期题:数字不改,只按单条撤因撤) ⑦同标的聚簇≥2(v2.9.63留超集)"
  fi;;
1|2)
  if [ "$A" -le 24 ] 2>/dev/null; then
    echo "▶ status=2/1 ≤24h: 质量复审(v2.7.7)+0a.5预过滤(含灌水形态闸六型) → ✅发/🟠改/🚨撤/🟡待核"
    echo "  不合格四类:①A≤1 ②链上红线(匿名对赌/托管流水) ③事实红线 ④灌水(meme豁免三选一优先判)"
    echo "  🟡最多跨1轮(v2.9.78),下轮必须走上或撤;status=2只有上和撤两条路(v2.9.47)"
  else
    echo "▶ status=2/1 >24h: 时效闸快判(三问②:动作不在扫描窗内)→status=3"
    echo "  客观闸非懒判,无需逐条重新核价;不催团队上线旧题(v2.9.18仅此一义)"
  fi;;
3) echo "▶ status=3: 不重建、不分析";;
*) echo "用法: route.sh <status 0|1|2|3> <age_hours> [deviation_pct]";;
esac
# v3.7.33 判据卡试跑:路由定了,接着把这一步要用的判据打出来(0≤8h→时段;0>8h→过期题;1/2→双要素/归因/时效)。card.py 不在则静默
[ -f "$(dirname "$0")/card.py" ] && [ -n "$AGE" ] && python3 "$(dirname "$0")/card.py" route "$S" "$AGE" 2>/dev/null
exit 0
