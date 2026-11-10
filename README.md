# FollowDAO Trend Topics

Claude Code skills for managing FollowDAO / Followin TrendingTopic — 热点风向标端到端管线。

## skills/

- **create-trending-topic** — 从原始素材或主动扫描热点（加密 + 跨市场宏观 / 美股 / 港股 / 大宗）创建 Followin TrendingTopic：采集 → 去重 → 双轴评分 → 字段提取 + 标题优化 → 预览 → 创建 → tag 校验 → 数据核实 → 发布。

## scripts/

把规则落成硬检查的脚本、回归用例和人手维护的配置，是本机 `~/.trend-scout/` 的镜像（运行目录仍在本机）。同步方法与清单见 [scripts/README.md](scripts/README.md)。
