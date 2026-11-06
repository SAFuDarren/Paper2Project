# Paper2Project

Connect papers, concepts, and ideas to build your research.

A lightweight agent skill for Markdown and Obsidian: existing knowledge in **Library**, potential directions and your increment in **Projects**, with one home per project. Research Map shows the branches; Full Network includes papers and concepts.

[![Tests](https://github.com/SAFuDarren/Paper2Project/actions/workflows/tests.yml/badge.svg)](https://github.com/SAFuDarren/Paper2Project/actions/workflows/tests.yml)

## Use

Copy this folder to your host’s skill directory and invoke `$paper2project`, or ask a compatible agent to read [SKILL.md](SKILL.md). Python 3.10+ standard library only. A download does not launch setup; the first invocation reads relevant context and asks only for missing consequential choices.

The host LLM can use memory/context it actually has. It proposes normalized preferences; the program resolves, validates and saves them. No universal memory API, home-folder crawl, raw-memory storage or external service is required.

**Current explicit choice → saved workspace → supplied memory → conversation inference → fallback.** Response, note and filename languages are separate. A temporary request affects only the current task; an enduring change updates the same profile with backup/hash/readback. Existing notes are not translated or moved automatically.

```sh
python scripts/p2p.py --help
python scripts/p2p.py locales
python scripts/p2p.py preferences --root /chosen/Academic --signals /chosen/signals.json
python scripts/p2p.py init --root /chosen/Academic --profile /chosen/profile.json --non-interactive --apply
python scripts/p2p.py check --root /chosen/Academic
python scripts/p2p.py export --root /chosen/Academic --output /chosen/notes.jsonl
```

See [first use and updates](references/onboarding.md), [source-grounded note cards](references/workflow.md), and [entry/task handoff](references/preferences-and-handoff.md). Example signals/cards are in [examples](examples/).

## Languages and customization

Built-in label packs: English, simplified/traditional Chinese, Spanish, French, German, Japanese, Arabic. Ordered single/multilingual notes use the same six semantic templates and locale-aware checker. Additional languages use a complete `locale_overrides` pack prepared by the host LLM (`locales --template <tag>`); missing labels/content are rejected rather than substituted with English. Actual prose must be supplied and reviewed in every chosen language.

Customize language/order, filename/detail/navigation preferences, folder-role display names and five role colors. Preserve recognized academic names, source identity, one project home, explained connections and evidence scope. The optional [English/Chinese preset](assets/profiles/bilingual-research.json) is a choice, not a requirement for every user. Legacy en/en-zh workspaces remain readable.

`render` previews or exclusively creates new notes; `preferences` previews by default and changes only the selected profile when explicitly applied. `check` covers local structure/labels/IDs/links, not translation quality, source support or scientific truth. Native Obsidian appearance requires actual app review when changed. No embedding/RAG/agent/store provider is enabled; [extension contracts](references/extensions.md) leave that choice to users.

## Tests

```sh
python -m unittest discover -s tests -v
```

GitHub Actions tests Linux, macOS and Windows with multiple Python versions, including Unicode/space paths, precedence, transient/persistent changes, old-note preservation, all templates/locales, custom packs and guarded writes. A CI pass is a bounded software check, not proof of a model’s scientific judgment. See actual runs above.

MIT license. This repository contains only the general public skill; personal vaults, memory, absolute paths and private profiles are excluded.

---

# Paper2Project

将论文、概念和想法连接到可以发展的研究。Library保存已有知识；Projects保存潜在方向和你的增量，每个项目只有一个入口。Research Map展示枝干，Full Network展开论文与概念。

调用`$paper2project`或让兼容agent读取[SKILL.md](SKILL.md)。首次调用利用实际可得的context/memory，只问关键缺项。偏好优先级为：本次明确要求→工作区保存设置→宿主提供的相关记忆→对话推断→默认值。回复、笔记和文件名语言分别设置；临时要求不改长期配置，持久更新带哈希核对、备份与读回，不自动改写旧笔记。

内置八种语言标签包，其他语言可由LLM补全并保存自定义包；程序和六类模板共同适配，不把缺失语言替换成英文。LLM负责有来源的正文与判断，程序负责设置、生成格式、查重和检查。命名、详细度、目录显示及配色可调整，知识/增量分工、唯一入口、来源与证据范围保持一致。

安装和命令见上文；[首次使用与偏好调整](references/onboarding.md)、[笔记输入](references/workflow.md)、[稳定接手](references/preferences-and-handoff.md)按需读取。Linux/macOS/Windows与多Python版本由GitHub Actions测试；结构通过不等于科学内容或翻译已获认证。embedding、RAG等仅保留关闭的接口，由使用者后续选择。
