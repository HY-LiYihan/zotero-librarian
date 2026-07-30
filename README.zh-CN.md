# Zotero Librarian

Zotero Librarian 是一个安全优先的跨 Agent 文献馆员 skill，用于整理和维护本地 Zotero 文库。它基于 [`zotero-agent`](https://github.com/alex-roc/zotero-agent) 的本地读写能力，增加分类体系、文库审计、可审查的 JSONL 变更计划、PDF 阅读流程以及备份/撤销约束。

[English](README.md)

## 为什么做这个项目

`zotero-agent` 已经解决最困难的底层问题：从正在运行的 Zotero 快速读取，并通过认证插件在 Zotero 进程内写入。本项目不重复实现插件，而是把这些原子能力组织成可靠的文献维护流程：

- 审计集合、标签、缺失元数据、重复项和附件；
- 使用用户自己维护的 taxonomy 分类；
- 批量修改前生成、校验和预览 JSONL 计划；
- 维护阅读队列，阅读 PDF 并写入有页码依据的笔记；
- 将 PDF 作为 stored attachment 本地导入，由 Zotero Desktop/WebDAV 同步；
- 先备份、再预览，将条目移入回收站，并在可用时支持 undo。

## 环境要求

- 本地运行的 Zotero Desktop 7-9
- Python 3.9+
- [`zotero-agent`](https://github.com/alex-roc/zotero-agent) CLI 与 bridge XPI
- Python 3.9-3.10 使用校验脚本时需要 `tomli`

先安装并验证底层：

```bash
uv tool install zotero-agent
zot init
zot ping
```

bridge XPI 必须从上游 `zotero-agent` Release 下载。安装前应阅读其安全文档。

## 安装 skill

```bash
git clone https://github.com/HY-LiYihan/zotero-librarian.git
cd zotero-librarian
./install.sh --codex
```

Claude Code 使用 `./install.sh --claude`；两个参数可以同时使用。唯一规范源保存在 `skills/zotero-librarian/`。

## 使用示例

调用 `$zotero-librarian`，例如：

- “审计我的 Inbox，提出 taxonomy，但不要修改文库。”
- “按 taxonomy 分类这个集合，只生成 dry-run 计划并等待确认。”
- “查找重复论文，给出可以合并的证据。”
- “总结这篇 PDF，保留页码，并草拟 Zotero 子笔记。”
- “备份并预览后，把这些精确 item key 移入回收站。”

校验示例 taxonomy 和计划：

```bash
python3 skills/zotero-librarian/scripts/librarian_guard.py taxonomy taxonomy.example.toml
python3 skills/zotero-librarian/scripts/librarian_guard.py plan \
  examples/edits.example.jsonl --taxonomy taxonomy.example.toml
```

校验器只检查规则和格式。科学分类必须由 Agent 根据元数据、摘要或 PDF 证据完成。

## 完成闸门

审计或整理完成后，用 `goal_status.py` 作为全库最终检查：

```bash
zot search '' --all --json > library.json
python3 skills/zotero-librarian/scripts/goal_status.py library.json --expect-items <BASELINE>
```

状态报告会区分两个结果：

- `automationComplete`：没有剩余可自动处理的缺标签、缺元数据、PDF 队列问题或父条目数量漂移。
- `fullComplete`：更严格的完成状态，没有任何已记录元数据冲突或仍需人工复核的条目。

如果 `automationComplete` 为 true 但 `fullComplete` 为 false，Agent 必须停止并要求用户明确选择文献身份。此时可以用 `identity_audit.py`、`conflict_report.py`，并且只在用户批准后用 `source_identity_plan.py` 准备 dry-run 修复计划。不能把已记录冲突自动转换成写入。

## 安全边界

- 不需要或保存 Zotero Web API key。
- 不直接修改 `zotero.sqlite`。
- 不永久删除或清空回收站。
- 本项目不增加任意 JavaScript 执行入口。
- 批量操作必须先 dry-run、备份、小样本验证，再执行并复核。
- PDF 默认本地导入为 Zotero stored attachment，由 Zotero Desktop 使用现有 WebDAV 或存储设置同步。

更多信息见 [SECURITY.md](SECURITY.md)。

## 开发

```bash
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py skills/zotero-librarian
```

自动测试不会访问真实 Zotero 文库；实时前向测试必须使用一次性测试库。

## 许可证与归因

MIT。本项目依赖但不隶属于同为 MIT 许可的 `alex-roc/zotero-agent`。Zotero 是 Corporation for Digital Scholarship 的商标；本项目未获 Zotero 官方隶属或背书。
