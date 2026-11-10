BEGIN{FS=OFS="\t"}
NF>=5 {print $1,$2,$3,$4,"[已结构化]"; next}   # 新格式行直接过
{
  a=$2; n=$4; act=""; rc=""
  # ---- action 归一 ----
  if (a ~ /^(cull|hide|撤)$/ || a ~ /撤|hide/) act="cull"
  else if (a ~ /^(create|建题|补建|create\+publish|建题材料)$/) act="create"
  else if (a ~ /^(update|改题|改数字|factfix|定稿|承接|factcheck\+update|tag-fix)$/ || a ~ /定稿|承接|改数字|改题/) act="update"
  else if (a ~ /^(merge|合并|归并|并单|并入|聚簇)$/) act="merge"
  else if (a ~ /^(restore|误撤\+回滚)$/) act="restore"
  else if (a ~ /^(publish|上线)$/) act="publish"
  else if (a ~ /^(rulefix|规则|铁律|判据|规则强化|规则映射|候选规则)$/) act="rulefix"
  else act="note"
  if (a ~ /merge-hide/) act="merge"
  # ---- reason_code:最具体优先 ----
  if (a ~ /用户点名/ || n ~ /用户点名|用户问|用户说/) rc="用户点名"
  else if (act=="cull") {
    if (n ~ /失实|数字错|数字不|硬数字|量级/) rc="事实错误-数字"
    else if (n ~ /事实错误|定义词|硬定义/) rc="事实错误-定义"
    else if (n ~ /反转|翻绿|翻红|错向/) rc="反转错向"
    else if (n ~ /借源造因|伪因果|未证实.*传导/) rc="归因-借源造因"
    else if (n ~ /归因反向|因果反|超预期.*跌|方向.*矛盾/) rc="归因-反向"
    else if (n ~ /同标的|留超集|重复/) rc="重复-同标的"
    else if (n ~ /碎片|聚簇|合并/) rc="重复-碎片合并"
    else if (n ~ /疑问句|悬念|修辞/) rc="疑问句-悬念"
    else if (n ~ /无价格|价格腿|零反应/) rc="缺价格腿"
    else if (n ~ /证伪/) rc="已证伪"
    else if (n ~ /过期|保质期|窗口题/) rc="过期-窗口题"
    else if (n ~ /A闸|灌水|观点|vanity|流水|产品公告|路线图/) rc="A闸不过-灌水"
    else rc="未分类"
  }
  else if (act=="create") {
    if (n ~ /预告/) rc="预告题"
    else if (n ~ /承接/) rc="承接兑现"
    else if (n ~ /meme|放量|市值里程碑/) rc="meme豁免"
    else if (n ~ /纯行情|A定则|无诱因|未给诱因/) rc="纯行情-A定则"
    else if (n ~ /补跑|捞回|backfill/) rc="补跑捞回"
    else if (n ~ /板块|矩阵/) rc="板块聚合"
    else if (n ~ /多源|双源|交叉/) rc="有诱因-多源"
    else if (n ~ /单源|待核/) rc="有诱因-单源待核"
    else rc="未分类"
  }
  else if (act=="update") {
    if (n ~ /定稿|收盘/) rc="改数字-定稿"
    else if (n ~ /升温|偏差/) rc="改数字-升温"
    else if (n ~ /归因/) rc="改归因"
    else if (n ~ /口径|盘前|盘后|时段/) rc="改口径-时段"
    else if (n ~ /命名|样式|ticker|全名/) rc="改样式-命名"
    else if (n ~ /tag/) rc="tag修正"
    else if (n ~ /承接/) rc="承接更新"
    else if (n ~ /status|状态/) rc="状态修正"
    else rc="未分类"
  }
  else if (act=="rulefix") rc="规则演进"
  else {
    if (n ~ /自审|六查/ || a ~ /自审/) rc="自审发现"
    else if (n ~ /复审员/) rc="复审员挑战"
    else if (n ~ /熔断|degraded|通道|挂了|卡死/) rc="通道故障"
    else if (n ~ /跳过|待人|待裁/) rc="跳过-待人裁"
    else rc="留档"
  }
  print $1,act,$3,rc,"[回填·原标签="a"]"
}
