# nonebot-plugin-recall-record

NoneBot2 撤回记录插件，适配 OneBot v11，兼容 NapCat、Lagrange、LLOneBot 等常见 QQ 机器人实现。关键词：NoneBot 防撤回、QQ 防撤回、群撤回记录、撤回消息查询、OneBot v11 防撤回、合并转发撤回消息。

插件默认是 **触发式撤回记录查询**：平时只缓存群聊消息和撤回事件，不会在有人撤回时立刻刷屏。群里 `@机器人 最近撤回消息`、`@机器人 查撤回` 或 `@机器人 防撤回` 时，机器人会把最近 24 小时记录到的所有撤回消息通过合并转发发出来。

默认不会重发图片、语音、视频或文件，只展示文本摘要，例如 `[图片]`、`[视频]`、`[文件:name]`。插件不下载媒体、不落盘、不缓存二进制内容；如果手动开启媒体重发，会尽量使用 OneBot 消息段里的 `url` / `file` 重新发送图片、语音、视频，失败时降级为文本描述。文件消息始终只做文本展示。

## 特性

- 默认触发式查询，不主动公开每一条撤回。
- 支持 `@机器人` 查询最近 24 小时撤回消息。
- 使用 OneBot `send_group_forward_msg` 合并转发撤回记录。
- 支持文字、@、表情、图片、语音、视频、文件等常见消息段的缓存和降级展示。
- 默认不重发媒体，不下载文件，不写入磁盘，避免大文件占用空间。
- 支持群白名单、群黑名单、用户排除名单。
- 可切换为自动补发模式，或同时启用自动补发和触发式查询。

## 安装

```bash
pip install nonebot-plugin-recall-record
```

在 NoneBot 项目的 `pyproject.toml` 中加载：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_recall_record"]
```

也可以在入口文件中手动加载：

```python
nonebot.load_plugin("nonebot_plugin_recall_record")
```

## 使用

默认配置下，在群里 @ 机器人并询问撤回即可：

```text
@机器人 最近撤回消息
@机器人 查撤回
@机器人 防撤回
@机器人 recall
```

机器人会合并转发当前群最近 24 小时内记录到的撤回消息。

如果最近没有撤回记录，会回复一条普通文本提示。

## 配置

所有配置都可写在 `.env` / `.env.prod` 中。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `RECALL_RECORD_ENABLED` | `true` | 是否启用插件 |
| `RECALL_RECORD_MODE` | `query` | 工作模式：`query` 仅触发查询，`auto` 自动补发，`both` 两者都启用 |
| `RECALL_RECORD_CACHE_SIZE` | `500` | 每个群缓存的原消息数量 |
| `RECALL_RECORD_RECALL_CACHE_SIZE` | `500` | 每个群缓存的撤回记录数量 |
| `RECALL_RECORD_CACHE_TTL_SECONDS` | `86400` | 原消息缓存保留秒数 |
| `RECALL_RECORD_QUERY_WINDOW_SECONDS` | `86400` | 查询最近多少秒的撤回记录，默认 24 小时 |
| `RECALL_RECORD_QUERY_KEYWORDS` | `撤回,防撤回,查撤回,最近撤回,撤回消息,撤回记录,recall,anti-recall` | @ 机器人时触发查询的关键词 |
| `RECALL_RECORD_FORWARD_LIMIT` | `0` | 合并转发最大记录数；`0` 表示不限制 |
| `RECALL_RECORD_MAX_FIELD_CHARS` | `4096` | 单个消息段字段最多保留多少字符，防止异常大字段占用内存 |
| `RECALL_RECORD_GROUPS` | 空 | 仅在这些群启用，空表示不限制 |
| `RECALL_RECORD_EXCLUDE_GROUPS` | 空 | 排除这些群 |
| `RECALL_RECORD_EXCLUDE_USERS` | 空 | 排除这些 QQ 号的撤回消息 |
| `RECALL_RECORD_REPORT_TO` | `group` | 自动模式通知目标：`group` / `private` / `both` / `none` |
| `RECALL_RECORD_PRIVATE_TARGETS` | 空 | 自动模式私聊通知目标 QQ；为空时使用 NoneBot `SUPERUSERS` |
| `RECALL_RECORD_RESEND_MEDIA` | `false` | 是否尝试重发图片、语音、视频；文件始终只做文本展示 |
| `RECALL_RECORD_MENTION_OPERATOR` | `false` | 自动补发到群时是否 @ 撤回操作者 |
| `RECALL_RECORD_SHOW_MESSAGE_ID` | `false` | 通知中是否展示群号和消息 ID |

列表配置支持逗号、空格、换行混写，例如：

```dotenv
RECALL_RECORD_MODE=query
RECALL_RECORD_GROUPS=123456, 234567
RECALL_RECORD_EXCLUDE_USERS=10000 10001
RECALL_RECORD_QUERY_WINDOW_SECONDS=86400
RECALL_RECORD_QUERY_KEYWORDS=撤回,查撤回,最近撤回,recall
```

如果你想要传统“有人撤回就立刻发出来”的防撤回，可以这样配置：

```dotenv
RECALL_RECORD_MODE=auto
RECALL_RECORD_REPORT_TO=group
```

如果既要自动补发，又要支持 @ 查询最近撤回记录：

```dotenv
RECALL_RECORD_MODE=both
```

仓库里也提供了 `.env.example`，可以直接复制后修改。

旧版本草稿里的 `GROUP_ANTIRECALL_*` 配置前缀仍可读取，但新项目推荐统一使用 `RECALL_RECORD_*`。

## 媒体与空间占用

插件没有媒体下载逻辑，也没有本地文件缓存目录。撤回记录保存在进程内存里，内容是消息 ID、发送者、撤回时间和 OneBot 消息段元数据。为了避免异常大的消息段字段占用内存，单个字段默认最多保留 4096 字符，可通过 `RECALL_RECORD_MAX_FIELD_CHARS` 调整。

默认配置下：

- 图片显示为 `[图片]` 或 OneBot 提供的摘要。
- 语音显示为 `[语音]`。
- 视频显示为 `[视频]`。
- 文件显示为 `[文件:name]` 或 `[文件]`。

如果设置 `RECALL_RECORD_RESEND_MEDIA=true`，插件会尝试把图片、语音、视频消息段放回合并转发节点里，但仍然不会主动下载到本地。大视频是否能发出、是否耗时较长，取决于 NapCat / Lagrange / LLOneBot 等 OneBot 实现。


## 行为说明

- 插件只处理群聊撤回事件，不处理私聊撤回。
- 插件只能展示启动后缓存到的撤回消息；机器人重启前的消息无法恢复。
- 默认只响应 `@机器人` 的查询，避免误触发和刷屏。
- 插件只在内存里保存 OneBot 消息段元数据，不下载、不落盘、不保存图片/视频/文件二进制内容。
- 默认不重发媒体；开启 `RECALL_RECORD_RESEND_MEDIA=true` 后，图片、语音、视频能否重发取决于 OneBot 实现提供的消息段字段以及资源是否仍可访问，可能消耗额外带宽和发送时间。
- 文件消息不会重发，只显示文件名或 `[文件]` 摘要。
- 如果机器人没有收到原消息事件，合并转发里会显示“未缓存到原消息内容”。
- 请在遵守群规则、平台规则和当地法律的前提下使用。

## 发布

```bash
python -m build
python -m twine upload dist/*
```

