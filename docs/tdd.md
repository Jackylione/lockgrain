# TDD 记录

用户已指定 CLI、严格逐条 TDD 和主要/边界/失败路径测试。
采用这一已授权的公共边界：用独立进程执行 `python3 lockgrain.py BEFORE AFTER`，检查标准输出、标准错误、退出码及输入文件不被改写。
测试输入和临时目录全部位于本项目。测试不导入内部函数、不 mock 内部实现，不运行外部项目。

退出码约定：0 表示无字段变化，1 表示存在变化，2 表示输入或用法错误。
每次只新增一个行为测试，实际观察失败，再实现使其通过；每次通过时运行已有全部测试。
下方将记录实际执行的红/绿循环，不预填验证结果。

每轮命令：`python3 -B -m unittest discover -s tests -v`。
“绿”列为该次真实执行时的累计测试数；参数化 subtest 不另计测试数。

| 轮次 | 新增行为 | 实际红灯 | 绿 |
| --- | --- | --- | --- |
| 1 | 相同输入 | CLI 文件不存在，退出 2 | 1 OK |
| 2 | 版本字段变化 | 仍报告无变化 | 2 OK |
| 3 | 顶层/包 marker 排序 | 报告了纯排列差异 | 3 OK |
| 4 | extras 重排和真实升级共存 | 多报 extras 差异 | 4 OK |
| 5 | wheel 重排中的哈希变化 | 整个列表混在一行 | 5 OK |
| 6 | 依赖重排中的 marker 变化 | 没有逐字段定位 | 6 OK |
| 7 | 同名多版本/来源 | 路径缺乏分叉身份 | 7 OK |
| 8 | 重复依赖名 | 错把 2.0 报为原版本，记录覆盖 | 8 OK |
| 9 | 坏 TOML | 未捕获异常，退出 1 | 9 OK |
| 10 | 不支持/缺失格式版本 | 五个 subtest 都误按可比较文件处理 | 10 OK |
| 11 | 坏记录结构 | 13 个 subtest 失败，含异常及误报相同 | 11 OK |
| 12 | 重复包/wheel 身份 | 两个 subtest 都静默覆盖 | 12 OK |
| 13 | 未知列表和空表 | 空表变化丢失 | 13 OK |
| 14 | 引号键、点号键和控制字符 | 字段路径碰撞且输出原始控制字符 | 14 OK |
| 15 | 空包集合及增删 | 丢失显式空数组字段 | 15 OK |
| 16 | 非 UTF-8 | 未捕获解码异常，退出 1 | 16 OK |
| 17 | 缺失文件、目录、FIFO | 前两项错误退出 1；FIFO 子进程 3 秒超时，被测试框架终止 | 17 OK |
| 18 | 帮助和参数数量 | 四个 subtest 失败，无正确用法提示 | 18 OK |
| 19 | 16 MiB 文件边界 | 超限文件仍被读取比较 | 19 OK |
| 20 | optional/dev/metadata 依赖列表 | 四种集合的纯重排都被报告 | 20 OK |
| 21 | TOML 日期/时间类型 | JSON 编码器不支持日期，产生 traceback | 21 OK |
| 22 | 过深嵌套 | 未捕获递归错误，退出 1 | 22 OK |

第 16 轮新增测试时曾插入到前一测试中间；在实现前修正测试布局并重跑，确认仍只因 UTF-8 错误路径失败，然后才修改实现。

## 上游文件抽查

上游 [uv 0.13.0 自带的 uv.lock](https://github.com/astral-sh/uv/blob/0.13.0/uv.lock)
为 347,478 字节、96 个包，SHA-256：
`beaca1f1a9db7356bcf8d943d03081f31370169b0fed373f1997ade312d035c1`。
下载仅是测试准备，CLI 本身全程离线。首个 raw 下载请求超时，后续官方匿名只读 contents 接口下载成功。

在 `.test-tmp/upstream-smoke/` 内保存原文件及两个变体，实际执行：

```sh
python3 -B lockgrain.py .test-tmp/upstream-smoke/uv-0.13.0.lock .test-tmp/upstream-smoke/uv-0.13.0.lock
python3 -B lockgrain.py .test-tmp/upstream-smoke/uv-0.13.0.lock .test-tmp/upstream-smoke/reordered.lock
python3 -B lockgrain.py .test-tmp/upstream-smoke/uv-0.13.0.lock .test-tmp/upstream-smoke/modified.lock
```

实际使用 `/usr/bin/python3` 和文件绝对路径，完整 argv/输出见 [upstream-smoke.json](upstream-smoke.json)。
结果依次为：退出 0，无变化；退出 0，无变化；退出 1，仅 `lock.requires-python` 的前后两行。
第二个变体颠倒 96 个包的顺序、加入注释并改为 CRLF；第三个只把 `>=3.8` 改为 `>=3.11`。
三个结果均以独立已知期望值断言通过，stderr 为空。

## 最终验收

完成代码和文档后实际运行 `/usr/bin/python3 -B -m unittest discover -s tests -v`：
`Ran 22 tests in 3.638s`，`OK`，退出 0，无跳过。
README 示例实际运行退出 1，仅显示预期的哈希前后两行；`./lockgrain.py --help` 退出 0。
完整命令及原始输出保存在 [validation.json](validation.json)。
`git diff --check` 退出 0，但项目文件尚未跟踪，该项不作为代码正确性的证据。
执行环境为 Linux、Python 3.14.4；未执行其他平台/解释器。
