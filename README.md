# nonebot-plugin-recall-record

NoneBot2 撤回记录插件，适配 OneBot v11，兼容 NapCat、Lagrange、LLOneBot 等常见 QQ 机器人实现。关键词：NoneBot 防撤回、QQ 防撤回、群撤回记录、撤回消息查询、OneBot v11 防撤回、合并转发撤回消息。

插件默认是 **触发式撤回记录查询**：平时会缓存并落盘保存群聊消息元数据和撤回事件，不会在有人撤回时立刻刷屏。群里 `@机器人 最近撤回消息`、`@机器人 查撤回` 或 `@机器人 防撤回` 时，机器人会把最近 24 小时记录到的所有撤回消息通过合并转发发出来。

默认会尽量在合并转发里还原图片、QQ 表情和动画表情；语音、视频、文件只有在 OneBot 消息段能确认小于 10MB 时才尝试重发，过大或无法确认大小会降级为 `[视频]`、`[语音]`、`[文件:name]` 等文本摘要。插件会把聊天记录元数据写入 SQLite，重启后仍可查询；但不会下载媒体、不保存图片/视频/文件二进制内容，只保存 OneBot 消息段元数据。

## 特性

- 默认触发式查询，不主动公开每一条撤回。
- 支持 `@机器人` 查询最近 24 小时撤回消息。
- 使用 OneBot `send_group_forward_msg` 合并转发撤回记录。
- 支持文字、@、表情、图片、语音、视频、文件等常见消息段的缓存和降级展示。
- 默认尽量还原图片、QQ 表情、动画表情；小于 10MB 的语音、视频、文件会尝试重发。
- 默认使用 SQLite 持久化消息段元数据和撤回记录，机器人重启后也能查询。
- 不下载文件，不保存媒体二进制；落盘数据按数量上限和 TTL 在正常事件触发时清理。
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
| `RECALL_RECORD_CACHE_TTL_SECONDS` | `86400` | 原消息缓存保留秒数；过期数据会在新消息、撤回、查询时清理 |
| `RECALL_RECORD_QUERY_WINDOW_SECONDS` | `86400` | 查询最近多少秒的撤回记录，默认 24 小时 |
| `RECALL_RECORD_PERSIST` | `true` | 是否启用 SQLite 持久化，启用后重启不丢撤回记录 |
| `RECALL_RECORD_STORAGE_PATH` | `data/nonebot_plugin_recall_record/recall_record.sqlite3` | SQLite 数据库路径 |
| `RECALL_RECORD_STORAGE_TTL_SECONDS` | `604800` | 落盘记录最长保留秒数，默认 7 天 |
| `RECALL_RECORD_QUERY_KEYWORDS` | `撤回,防撤回,查撤回,最近撤回,撤回消息,撤回记录,recall,anti-recall` | @ 机器人时触发查询的关键词 |
| `RECALL_RECORD_FORWARD_LIMIT` | `0` | 合并转发最大记录数；`0` 表示不限制 |
| `RECALL_RECORD_MAX_FIELD_CHARS` | `4096` | 单个消息段字段最多保留多少字符，防止异常大字段占用内存 |
| `RECALL_RECORD_GROUPS` | 空 | 仅在这些群启用，空表示不限制 |
| `RECALL_RECORD_EXCLUDE_GROUPS` | 空 | 排除这些群 |
| `RECALL_RECORD_EXCLUDE_USERS` | 空 | 排除这些 QQ 号的撤回消息 |
| `RECALL_RECORD_REPORT_TO` | `group` | 自动模式通知目标：`group` / `private` / `both` / `none` |
| `RECALL_RECORD_PRIVATE_TARGETS` | 空 | 自动模式私聊通知目标 QQ；为空时使用 NoneBot `SUPERUSERS` |
| `RECALL_RECORD_RESEND_MEDIA` | `true` | 媒体/表情重放总开关；设为 `false` 时全部降级为文本摘要 |
| `RECALL_RECORD_RESEND_IMAGES` | `true` | 是否尝试在合并转发里还原图片 |
| `RECALL_RECORD_RESEND_FACES` | `true` | 是否尝试还原 QQ 表情、动画表情、骰子、猜拳等表情类消息段 |
| `RECALL_RECORD_RESEND_RECORDS` | `true` | 是否尝试重发语音；仍受大小限制 |
| `RECALL_RECORD_RESEND_VIDEOS` | `true` | 是否尝试重发视频；仍受大小限制 |
| `RECALL_RECORD_RESEND_FILES` | `true` | 是否尝试保留文件消息段；仍受大小限制，实际效果取决于 OneBot 实现 |
| `RECALL_RECORD_MAX_MEDIA_BYTES` | `10485760` | 语音、视频、文件重放大小上限，默认 10 MiB；支持写 `10MB` |
| `RECALL_RECORD_RESEND_UNKNOWN_SIZE_MEDIA` | `false` | 语音、视频、文件没有大小字段时是否仍尝试重发；默认保守降级 |
| `RECALL_RECORD_MENTION_OPERATOR` | `false` | 自动补发到群时是否 @ 撤回操作者 |
| `RECALL_RECORD_SHOW_MESSAGE_ID` | `false` | 通知中是否展示群号和消息 ID |

列表配置支持逗号、空格、换行混写，例如：

```dotenv
RECALL_RECORD_MODE=query
RECALL_RECORD_GROUPS=123456, 234567
RECALL_RECORD_EXCLUDE_USERS=10000 10001
RECALL_RECORD_QUERY_WINDOW_SECONDS=86400
RECALL_RECORD_STORAGE_TTL_SECONDS=604800
RECALL_RECORD_QUERY_KEYWORDS=撤回,查撤回,最近撤回,recall
RECALL_RECORD_MAX_MEDIA_BYTES=10MB
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

插件没有媒体下载逻辑，也没有本地文件缓存目录。撤回记录默认写入 SQLite，内容是消息 ID、发送者、撤回时间、文本和 OneBot 消息段元数据；图片、视频、语音、文件只保存 OneBot 提供的 `url` / `file` / `summary` / `size` 等字段，不保存二进制内容。为了避免异常大的消息段字段占用内存和磁盘，单个字段默认最多保留 4096 字符，可通过 `RECALL_RECORD_MAX_FIELD_CHARS` 调整。

默认配置下：

- 图片、QQ 表情、动画表情会尽量放回合并转发节点里；动画表情会优先使用消息段里的 `url` / `file` 转成普通图片段发送。如果 OneBot 实现不支持、资源已失效，或原消息段没有可用媒体引用，会降级为 `[图片]`、`[表情]`、`[动画表情]`。
- 语音、视频、文件只有在消息段里带有 `size` / `file_size` / `filesize` / `fileSize` 且不超过 `RECALL_RECORD_MAX_MEDIA_BYTES` 时才尝试重发。
- 无法确认大小的语音、视频、文件默认降级为文本摘要，避免误拉取大文件；如果你愿意承担带宽和耗时，可以设置 `RECALL_RECORD_RESEND_UNKNOWN_SIZE_MEDIA=true`。
- 文件消息能否在合并转发里原样显示取决于 NapCat / Lagrange / LLOneBot 等 OneBot 实现；失败时仍会保留文件名和大小摘要。

缓存和落盘数据不会无限增长：插件按 `RECALL_RECORD_CACHE_SIZE` 限制每个群缓存/落盘的原消息数量，按 `RECALL_RECORD_RECALL_CACHE_SIZE` 限制每个群缓存/落盘的撤回记录数量，并按 `RECALL_RECORD_CACHE_TTL_SECONDS` / `RECALL_RECORD_QUERY_WINDOW_SECONDS` / `RECALL_RECORD_STORAGE_TTL_SECONDS` 在收到新消息、撤回事件或查询时清理过期数据。插件不会启动额外的定时清理任务。


## 行为说明

- 插件只处理群聊撤回事件，不处理私聊撤回。
- 插件默认会把启动后收到的消息段元数据和撤回记录写入 SQLite；机器人重启后仍可查询未过期的撤回记录。
- 默认只响应 `@机器人` 的查询，避免误触发和刷屏。
- 插件只保存 OneBot 消息段元数据，不下载、不保存图片/视频/文件二进制内容。
- 图片、表情、语音、视频、文件能否原样重放取决于 OneBot 实现提供的消息段字段以及资源是否仍可访问，可能消耗额外带宽和发送时间。
- 语音、视频、文件默认必须能确认小于 10 MiB 才会尝试重放；过大或未知大小会降级为摘要。
- 如果机器人没有收到原消息事件，合并转发里会显示“未缓存到原消息内容”。
- 请在遵守群规则、平台规则和当地法律的前提下使用。

## 发布

```bash
python -m build
python -m twine upload dist/*
```

