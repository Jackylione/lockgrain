# 选题：lockgrain — uv.lock 字段差异阅读

核查日期：2026-10-12（Asia/Shanghai）。有效窗口：2026-07-12 至 2026-10-12。
原帖日期以下均按 GitHub 的 UTC `created_at` / `createdAt` 记录，不用更新时间冒充发布时间。
只做一个工具：读取两份本地 `uv.lock`，过滤已知无序集合的排列噪声，逐字段显示真正变化。

## 三个候选的比较

| 候选 | 公开线索 | 可用性及取舍 |
| --- | --- | --- |
| 文件监听额度/泄漏排查 | [ZefengWang，2026-07-23，vscode #327108](https://github.com/microsoft/vscode/issues/327108)：`when i close the workspace， it still keep 50000+ watchers`；近期检索还出现 [#332860](https://github.com/microsoft/vscode/issues/332860)、[#334248](https://github.com/microsoft/vscode/issues/334248) | 不选。进程计数只能辅助定位，不能修复监听器生命周期；用户要求的一条本地命令不能替上游修复泄漏。作者于 [2026-07-24 更正](https://github.com/microsoft/vscode/issues/327108#issuecomment-5065550529)：`the leak was happened on cursor not vscode`。后两条只核到检索元数据，不计入独立原话门槛。当前 VS Code [1.141.0](https://github.com/microsoft/vscode/releases/tag/1.141.0)，2026-10-07 发布，不能把旧版本报告直接当作当前版本结论。 |
| pnpm 锁文件冲突合并 | [oblador，2026-09-14，#14880](https://github.com/pnpm/pnpm/issues/14880)：`pnpm 12 attempts to parse the raw conflict marker as YAML. After parsing fails, it warns that the lockfile is broken, discards the entire wanted lockfile, and resolves again from package.json.` | 不选。只核实到一位作者的直接合并痛点；其他搜索结果不是同一问题。原帖已有 pnpm 11.24.0 自动合并的对照；当前 [12.11.2](https://github.com/pnpm/pnpm/releases/tag/v12.11.2)，2026-10-09 发布，不能以 12.4.1 的回归报告断言当前仍未修复。离线重建依赖图也超出小工具范围。 |
| uv.lock 字段差异阅读 | 下文三位独立作者的近期原话 | **入选**。有可重复的纯本地输入；不求解依赖、不访问包索引，也无需平台改动。现有摘要器丢弃部分字段，通用文本差异保留排列噪声。 |

检索限定于以上三个方向。检索入口包括：
[VS Code inotify](https://github.com/microsoft/vscode/issues?q=is%3Aissue+created%3A%3E%3D2026-07-12+inotify)、
[pnpm lockfile conflict](https://github.com/pnpm/pnpm/issues?q=is%3Aissue+created%3A%3E%3D2026-07-12+lockfile+conflict)、
[uv lock diff](https://github.com/astral-sh/uv/issues?q=is%3Aissue+created%3A%3E%3D2026-07-12+lock+diff)、
[uv lock order](https://github.com/astral-sh/uv/issues?q=is%3Aissue+created%3A%3E%3D2026-07-12+lock+order)。

## 入选的三条独立原话

uv 是高星开发者项目：[astral-sh/uv](https://github.com/astral-sh/uv)，核查时公开仓库元数据为 90,624 stars。

### 1. ashrub-holvi — 2026-07-30 08:35:50 UTC

原始链接：[Diff friendly uv.lock formatting for wheels list，#20814](https://github.com/astral-sh/uv/issues/20814)。
原帖中的连续原话及代码（保留原有拼写）：

> Hi,
> not really sure, but have a feeling that

```toml
wheels = [
    { url = "https://pypi.org/billiard/4.2.4/billiard-4.2.4-py3-none-any.whl", hash = "sha256:525b42bdec68d2b983347ac312f892db930858495db601b5836ac24e6477cde5" },
```

> would be better as

```toml
wheels = [
    {
        url = "https://pypi.org/billiard/4.2.4/billiard-4.2.4-py3-none-any.whl",
        hash = "sha256:525b42bdec68d2b983347ac312f892db930858495db601b5836ac24e6477cde5"
    },
```

> for checking the diff

痛点：单行混合 URL、哈希等字段，难看出哪个字段变化。工具把字段分行显示。
同一作者 2026-08-05 的补充不另计人数。

### 2. pjonsson — 2026-09-28 12:02:37 UTC

原始链接：[Varying order of resolution-markers from the same pyproject.toml，#22040](https://github.com/astral-sh/uv/issues/22040)。

> For the linked pull requests that are made only a few hours apart, the consequence is that the difference for the package update is just a re-shuffling of the resolution markers without changing the version in uv.lock.

痛点：marker 排列变化制造无实际值变化的差异。工具只忽略已知 marker 列表的顺序，保留 marker 字符串的任何实际修改；不采用作者转述的 LLM 原因推测。

### 3. gorewilliams — 2026-09-26 12:35:51 UTC

原始链接：[#17549 的独立用户评论](https://github.com/astral-sh/uv/issues/17549#issuecomment-5846318339)。

> I encountered a similar case with the ordering of extras in package.metadata.requires-dist:
>
> 1. In commit A, pyproject-fmt changed pkg1[c,b,a] to pkg1[a,b,c] in pyproject.toml. Running uv lock left uv.lock unchanged.
> 2. In commit B, I upgraded an unrelated dependency, pkg2. This also changed pkg1’s extras in uv.lock from ["c", "b", "a"] to ["a", "b", "c"].
>
> The lockfile remains semantically valid throughout, but the formatting change ends up in an unrelated commit.

痛点：extras 的无意义顺序变化混入其他依赖更新。工具在这个已知位置排序 extras。
**原 issue 创建于 2026-01-17，不计入门槛；计入的是上面这条 9 月新评论。**
三条证据来自三个不同账号，无转载，没有把同一人的补充重复计算。

## 上游现状及现有方案核查

所有版本在 2026-10-12 核查。下面是官方发行页、README 和源码审阅，未宣称运行过这些竞争工具。

| 工具及当前核查版本 | 已能解决什么 | 剩余成本/本工具的具体区别 |
| --- | --- | --- |
| [uv 0.13.0](https://github.com/astral-sh/uv/releases/tag/0.13.0)，2026-10-09 发布 | 锁定、同步、导出、依赖树；[CLI reference](https://docs.astral.sh/uv/reference/cli/) 没有两文件字段 diff 命令 | [官方文档](https://github.com/astral-sh/uv/blob/0.13.0/docs/concepts/projects/layout.md#the-lockfile) 明确 uv.lock 由 uv 管理，不应手改。通过重写锁文件获得可读差异会改变输入。本工具只读两份文件，不调用 uv。 |
| [lockdiff 0.1.0](https://github.com/Nithinfgs/lockdiff/blob/be04abebb8fc93b57b6733d2e08745ae8aab69bb/package.json)，commit `be04abebb8fc93b57b6733d2e08745ae8aab69bb` | 已有离线多生态包版本/来源/哈希摘要，不能声称此类工具不存在 | [uv parser](https://github.com/Nithinfgs/lockdiff/blob/be04abebb8fc93b57b6733d2e08745ae8aab69bb/src/parsers/python.ts) 投影为 name/version/integrity/source/installScript，并跳过 editable/virtual/path 包。依赖 marker、项目 metadata、顶层设置等不在投影中。本工具显示这些字段，未知字段也保留。 |
| [lockreview 0.1.0](https://github.com/agentscope-ai-java/lockreview/blob/70c1cc1bfa8616c830643eba6240e063f36b5aeb/pyproject.toml)，commit `70c1cc1bfa8616c830643eba6240e063f36b5aeb` | Python 锁文件的供应链信号；零运行依赖、离线、支持两文件比较 | [README](https://github.com/agentscope-ai-java/lockreview/blob/70c1cc1bfa8616c830643eba6240e063f36b5aeb/README.md) 明确未命中信号的更新只计数，不逐项输出。目标是风险摘要，而此次是字段完整的差异阅读；不复刻其风险规则。 |
| [action-uv-lock-diff-viewer 0.0.3](https://github.com/trim21/action-uv-lock-diff-viewer/blob/61bee4931adb577a98838e7324d5fdef8d5bf7e8/package.json)，commit `61bee4931adb577a98838e7324d5fdef8d5bf7e8` | GitHub Action 的锁文件变更展示 | [README](https://github.com/trim21/action-uv-lock-diff-viewer/blob/61bee4931adb577a98838e7324d5fdef8d5bf7e8/README.md) 要求工作流和 PR 写权限。不是本地无账号的一条命令。 |
| [Difftastic 0.71.0](https://github.com/Wilfred/difftastic/releases/tag/0.71.0) | [官方介绍](https://difftastic.wilfred.me.uk/)：按语法比较，能忽略格式变化 | 是有效替代方案，但其通用语法比较没有本工具针对 uv 字段的无序集合规则和每行包/字段路径；需要用户进一步识别列表排列噪声。 |

必须保留的反证：gorewilliams 在 [2026-10-01](https://github.com/astral-sh/uv/issues/17549#issuecomment-5929103878) 认为新预览功能已解决其场景；原作者随后表示开启 `--preview` 后原问题消失，但整个 `package.metadata` 也不见了，无法确认所有问题都消失。因此不声称 extras 序列化问题在所有当前配置中依然存在。已有历史文件、未启用该行为的锁文件和 marker/wheel 阅读问题仍适合只读比较。三条 issue 在核查时仍为 open，这只是状态记录，不是证明未修复的充分条件。

另核查过 [Otto-AA 的 #21484，2026-09-05](https://github.com/astral-sh/uv/issues/21484)：作者在后续确认 `uv lock --check --refresh --no-build` 满足校验需求。**不把它算作本工具的第三条证据，也不把字段 diff 宣称为锁文件真实性校验。**

## 最终范围

命令：`python3 lockgrain.py BEFORE AFTER`，Python 3.11+ 标准库，无运行依赖。
两份输入可用任何文件名；工具只读取显式传入的普通文件。
输出包含每个变化的字段路径和前后值；忽略 TOML 格式、映射键顺序，以及明确列出的 uv 无序列表顺序。
保留未知字段和未知列表的顺序；不改写输入、不运行项目代码、不登录、不调用服务 API。

只支持 `uv.lock` format version 1；包的多个版本/来源不能被按名称覆盖。
不求解 PEP 508/PEP 440 等价关系，不做漏洞/真实性判断，不合并锁文件，不加 GitHub 或 CI 功能。
这与 shebanglf 的换行修复、ignoretrail 的排除规则解释、treeport 的 Git 文件名诊断不同；也不实现 prgate 式 PR 门禁。

研究过程只读公开原始网页；github.com 后续连接超时时，以 GitHub 官方匿名只读 REST 接口核对帖子正文、作者、发布时间和版本。研究联网与最终 CLI 的完全离线运行相互独立。未创建远程仓库、推送、提交 PR、评论或发消息。
