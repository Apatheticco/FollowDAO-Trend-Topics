# scripts/ — 执行脚本的镜像

规则文字在 `skills/create-trending-topic/`，把规则落成硬检查的脚本在本机 `~/.trend-scout/`。
这个目录是那批脚本的**镜像**：让「哪一版规则配哪一版脚本」能在同一次提交里对上，改坏了能回滚。

**运行目录仍是 `~/.trend-scout/`，不要直接改这里的文件**——改本机的，回归全过后同步过来。

## 里面有什么

| 进仓库 | 不进仓库 |
|---|---|
| 顶层 `*.py` `*.sh` `*.awk`（含 3 个软链） | 流水台账（`actions.tsv`、`snapshots.tsv` 等） |
| `tests/` 全部用例与样本 | 缓存（`b0-latest.json`、`quotes-cache.json` 等） |
| 人手维护的配置：`channels.json` `contracts.json` `majors.json` `megacap.json` `weights.json` `scatter-watch.json` | `lark.json`（飞书群号与人员 id，本仓库是公开的） |
| | `run-auto.sh`（休眠的本机定时启动器，写死本机路径） |

清单规则写在 `repo-sync.py` 顶部（`CONFIGS` / `NOT_MIRRORED`），新增不进仓库的文件要在那里登记原因。

## 怎么用

```bash
~/.trend-scout/repo-sync.py status            # 对账：本机与镜像是否一致
~/.trend-scout/repo-sync.py snapshot          # 本机 → 镜像（先查敏感内容，命中就停）
~/.trend-scout/repo-sync.py restore topic.py  # 镜像 → 本机，只还原点名的文件
~/.trend-scout/repo-sync.py restore --missing # 新机器：只补本机没有的文件
```

- 回归 `run-tests.sh` 跑完会打印一行「📦 脚本镜像 …」，有未同步的改动会提示。
- `snapshot` 不执行 git；提交仍然单独做。
- 回到更早的版本：`git checkout <提交> -- scripts/<文件>`，再 `restore <文件>`。
- 新机器还需要自己补 `lark.json`，以及 `~/.claude.json` 里的 MCP 凭证（脚本运行时读取，不落盘）。

## 为什么是镜像，不是把脚本搬进来再软链回去

2026-11-10 实测：软链之后 Python 会把导入路径解析到仓库目录，而各脚本是按「自己所在的目录」找台账的。
被别的脚本导入时，它们会到仓库目录里找台账，找不到就当空表处理、不报错——撞名表、下游回读这类检查会悄悄放行。
回归用例全靠注入临时路径，测不到这条默认路径。另外仓库一旦切分支，正在跑的轮次用的脚本会当场变。
