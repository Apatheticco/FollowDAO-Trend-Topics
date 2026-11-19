# HANDOFF — 会话交接

新会话接管时按这个顺序读：

1. `skills/create-trending-topic/SKILL.md`：每轮跑什么、什么顺序、调哪个脚本。
2. `skills/create-trending-topic/references/gates.md`：判定规则，用 `gate.sh <闸名>` 按需查，不整篇加载。
3. 本机 `~/.trend-scout/`：运行目录和台账（不入库）。开跑先跑 `retro.py brief` 读最近一次每晚复盘的「今天注意」，再跑 `ask.py sync` 看待定事项。

看板上题目的状态以 `list_trending_topics` 实查为准，不以任何文档为准。

未决事项不记在本文件：要用户定的走 `ask.py`，每晚复盘的结论写在 `~/.trend-scout/retro/`，周六周报汇总。历史事故与版本演进见 `skills/create-trending-topic/LESSONS.md`。
