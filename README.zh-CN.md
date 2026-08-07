# Zotero Librarian

Zotero Librarian 是一个 release-ready 的 Python CLI 和 companion Agent skill，用于安全审计、整理和维护本地 Zotero Desktop 文库。它在 MIT 许可的 [`zotero-agent`](https://github.com/alex-roc/zotero-agent) 后端之上提供类似 lark-cli 的 Agent 命令层：高层命令、稳定 JSON、默认 dry-run、内嵌 skill、备份和撤销规则。

[English](README.md)

## 为什么做这个项目

`zotero-agent` 已经解决底层问题：从运行中的 Zotero 本地读取，并通过认证 bridge 在 Zotero 进程内写入。本项目不重复实现 bridge，而是把这些原子能力组织成可复用的 Agent 工作流：

- 审计集合、标签、缺失元数据、重复项和附件；
- 生成可审查 JSONL 修改计划并做策略校验；
- 用用户自己的 taxonomy 分类文献；
- 只在来源身份可验证时修复元数据；
- 维护阅读队列，写入有依据的阅读笔记；
- 先备份，再将条目移入回收站，并在可用时支持 undo。

## 环境要求

- 本地运行的 Zotero Desktop 7-9
- Python 3.9+
- `zotero-agent` CLI 和 bridge XPI
- `uv`、`pipx` 或 `pip`

先安装并验证底层：

```bash
uv tool install zotero-agent
zot init
zot ping
```

bridge XPI 需要从上游 `zotero-agent` Release 获取，并先阅读其安全说明。

## 安装

从仓库本地安装 release-ready CLI：

```bash
git clone https://github.com/HY-LiYihan/zotero-librarian.git
cd zotero-librarian
python3 -m pip install -e .
zotero-librarian --json doctor --offline
```

正式发布 PyPI 后，预期入口是：

```bash
uvx zotero-librarian --help
```

从同一 CLI 构建安装内嵌 Agent skill：

```bash
zotero-librarian skills install --codex
zotero-librarian skills install --claude
```

只想复制 skill 的用户仍可使用旧安装脚本：

```bash
./install.sh --codex
```

## Agent 快速开始

```bash
zotero-librarian --json doctor
zotero-librarian --json library export --out library.json
zotero-librarian --json library status library.json --expect-items 229
zotero-librarian --json library audit library.json --strict
```

处理身份冲突：

```bash
zotero-librarian --json identity audit library.json --only-conflicts --workers 4 --output identity.json
zotero-librarian identity report library.json identity.json --output conflicts.md
zotero-librarian identity decision library.json identity.json --expect-items 229 --output decision.md
zotero-librarian --json identity plan library.json identity.json --output source-plan.jsonl --report source-plan.json
zotero-librarian --json plan preview source-plan.jsonl --extended
```

执行已审查写入：

```bash
zotero-librarian --json plan validate edits.jsonl --taxonomy taxonomy.example.toml
zotero-librarian --json plan preview edits.jsonl
zotero-librarian --json plan sample edits.jsonl --out sample.jsonl --count 2
zotero-librarian --json plan apply edits.jsonl --yes
```

`plan apply` 会先执行 `zot backup`。作者或 item type 修复使用 `--extended`，对应原先的 `librarian_apply.py` 受限写入器。

## 命令地图

- `doctor`：检查 package、config、内嵌 skill、`zot` 和 bridge 状态。
- `schema plan|audit|status`：输出 Agent 可依赖的 JSON 结构。
- `skills list|read|install`：查看和安装内嵌 companion skill。
- `library export|audit|status`：导出文库并运行完成度闸门。
- `identity audit|report|decision|plan`：检测身份冲突并生成受保护修复计划。
- `metadata enrich`：生成摘要或 DOI 补全计划，不直接写入 Zotero。
- `plan validate|preview|sample|apply`：校验、dry-run、抽样和应用 JSONL 计划。
- `item get|pdf|notes`：读取精确条目、PDF 路径或 child notes。
- `raw zot -- ...`：底层逃生口；已知写命令必须 `--allow-write`，`zot exec` 永远拒绝。

## JSON 契约

Agent 解析输出时使用 `--json`。JSON 命令只向 stdout 输出 JSON；诊断信息和 subprocess 失败进入 stderr 或脱敏后的错误 envelope：

```json
{"ok":false,"error":{"code":"confirmation_required","message":"refusing to write without --yes; run plan preview first","details":{}}}
```

命令不得打印 bridge token、Zotero API key、WebDAV 凭据、private env、无关 live export 或完整私有配置内容。

## 完成闸门

CLI 封装了原先 `library_audit.py` 和 `goal_status.py` 提供的检查：

```bash
zotero-librarian --json library status library.json --expect-items <BASELINE>
```

状态报告区分：

- `automationComplete`：没有剩余可自动处理的缺标签、缺元数据、PDF 队列问题或父条目数量漂移。
- `fullComplete`：没有任何已记录元数据冲突或仍需人工复核的条目。

如果 `automationComplete` 为 true 但 `fullComplete` 为 false，Agent 必须停止并要求用户做文献身份选择。使用 `identity audit`、`identity report`、`identity decision`，并且只在用户批准后使用 `identity plan`。这替代了直接调用 `source_identity_plan.py` 的流程，但保留脚本兼容性。

## 安全边界

- 不需要或保存 Zotero Web API key。
- 不直接修改 `zotero.sqlite`。
- 不永久删除或清空回收站。
- 本项目不增加任意 JavaScript 执行入口。
- 批量操作必须先 dry-run、备份、必要时抽样、验证，并在后端支持时可 undo。
- PDF 默认本地导入为 Zotero stored attachment，由 Zotero Desktop 使用现有 WebDAV 或存储设置同步。
- v1 不发布 MCP server。

更多信息见 [SECURITY.md](SECURITY.md)。

## 开发

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/zotero-librarian
python3 -m build
```

发布前从其他目录 smoke-test：

```bash
cd /tmp
zotero-librarian --help
zotero-librarian --json doctor --offline
zotero-librarian --json schema plan
```

默认 CI 只跑离线测试，不访问真实 Zotero 文库。真实文库前向测试见 [docs/live-testing.md](docs/live-testing.md)，发布流程见 [docs/release.md](docs/release.md)。

## 许可证与归因

MIT。本项目依赖但不隶属于同为 MIT 许可的 `alex-roc/zotero-agent`。Zotero 是 Corporation for Digital Scholarship 的商标；本项目未获 Zotero 官方隶属或背书。
