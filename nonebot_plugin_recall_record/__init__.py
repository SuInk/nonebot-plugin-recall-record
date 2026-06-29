from __future__ import annotations

import time
from collections import defaultdict, deque

from nonebot import get_driver, logger, on_message, on_notice
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    Message,
    MessageSegment,
)
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, to_me

from .config import Config
from .render import (
    CachedMessage,
    RecallRecord,
    build_empty_query_message,
    build_forward_fallback,
    build_recall_forward_content,
    build_recall_notice,
    plain_text_from_message,
    sender_name_from_event,
)

__version__ = "0.1.0"

__plugin_meta__ = PluginMetadata(
    name="撤回记录",
    description="NoneBot2 / OneBot v11 撤回记录插件，默认 @ 机器人查询最近撤回消息。",
    usage="@机器人 最近撤回消息，即可合并转发最近 24 小时的群撤回记录。",
    type="application",
    homepage="https://github.com/suink/nonebot-plugin-recall-record",
    config=Config,
    supported_adapters={"~onebot.v11"},
)

driver = get_driver()
plugin_config = Config.from_driver_config(driver.config)

_message_cache: defaultdict[int, dict[int, CachedMessage]] = defaultdict(dict)
_message_order: defaultdict[int, deque[int]] = defaultdict(deque)
_recall_records: defaultdict[int, deque[RecallRecord]] = defaultdict(
    lambda: deque(maxlen=plugin_config.recall_record_recall_cache_size)
)
_recent_recalls: deque[tuple[int, int, int]] = deque(maxlen=2048)


async def _is_group_message(event: Event) -> bool:
    return isinstance(event, GroupMessageEvent)


async def _is_group_recall(event: Event) -> bool:
    return isinstance(event, GroupRecallNoticeEvent)


async def _is_recall_query(event: Event) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if not plugin_config.recall_record_enabled or not _group_enabled(int(event.group_id)):
        return False
    text = _event_plain_text(event).lower()
    return any(keyword.lower() in text for keyword in plugin_config.recall_record_query_keywords)


message_cache = on_message(rule=Rule(_is_group_message), priority=1, block=False)
recall_query = on_message(rule=to_me() & Rule(_is_recall_query), priority=5, block=True)
group_recall = on_notice(rule=Rule(_is_group_recall), priority=10, block=False)


@message_cache.handle()
async def handle_group_message(event: GroupMessageEvent) -> None:
    if not plugin_config.recall_record_enabled:
        return
    group_id = int(event.group_id)
    user_id = int(event.user_id)
    if not _group_enabled(group_id) or user_id in plugin_config.recall_record_exclude_users:
        return

    message_id = int(event.message_id)
    message = _safe_message_copy(event.message)
    record = CachedMessage(
        group_id=group_id,
        message_id=message_id,
        user_id=user_id,
        sender_name=sender_name_from_event(event),
        message=message,
        raw_message=str(event.raw_message or ""),
        plain_text=plain_text_from_message(message),
        time=int(getattr(event, "time", time.time()) or time.time()),
    )
    _message_cache[group_id][message_id] = record
    _message_order[group_id].append(message_id)
    _trim_group_cache(group_id)


@group_recall.handle()
async def handle_group_recall(bot: Bot, event: GroupRecallNoticeEvent) -> None:
    if not plugin_config.recall_record_enabled:
        return

    group_id = int(event.group_id)
    message_id = int(event.message_id)
    user_id = int(event.user_id)
    operator_id = int(event.operator_id)
    if not _group_enabled(group_id) or user_id in plugin_config.recall_record_exclude_users:
        return

    recall_time = int(getattr(event, "time", time.time()) or time.time())
    recall_key = (group_id, message_id, recall_time)
    if recall_key in _recent_recalls:
        return
    _recent_recalls.append(recall_key)

    cached = _message_cache.get(group_id, {}).get(message_id)
    record = RecallRecord(
        group_id=group_id,
        message_id=message_id,
        user_id=user_id,
        operator_id=operator_id,
        recall_time=recall_time,
        cached=cached,
    )
    _recall_records[group_id].append(record)
    _trim_recall_records(group_id)

    if plugin_config.recall_record_mode in {"auto", "both"}:
        await _send_auto_notice(bot, record)

    logger.info(
        "Recall record cached: "
        f"group={group_id} message_id={message_id} user={user_id} operator={operator_id}"
    )


@recall_query.handle()
async def handle_recall_query(bot: Bot, event: GroupMessageEvent) -> None:
    group_id = int(event.group_id)
    records = _recent_group_recalls(group_id)
    if plugin_config.recall_record_forward_limit > 0:
        records = records[-plugin_config.recall_record_forward_limit :]

    if not records:
        await bot.send_group_msg(
            group_id=group_id,
            message=build_empty_query_message(plugin_config.recall_record_query_window_seconds),
        )
        return

    nodes = [
        _build_forward_node(record, index)
        for index, record in enumerate(records, start=1)
    ]
    try:
        await bot.call_api("send_group_forward_msg", group_id=group_id, messages=nodes)
    except Exception as exc:
        logger.warning(
            "Recall record forward query failed, retrying as text: "
            f"group={group_id} error={type(exc).__name__}: {exc}"
        )
        await bot.send_group_msg(
            group_id=group_id,
            message=build_forward_fallback(
                records,
                window_seconds=plugin_config.recall_record_query_window_seconds,
            ),
        )


async def _send_auto_notice(bot: Bot, record: RecallRecord) -> None:
    notice_kwargs = {
        "group_id": record.group_id,
        "message_id": record.message_id,
        "user_id": record.user_id,
        "operator_id": record.operator_id,
        "recall_time": record.recall_time,
        "show_message_id": plugin_config.recall_record_show_message_id,
        "mention_operator": plugin_config.recall_record_mention_operator,
    }
    notice = build_recall_notice(
        record.cached,
        resend_media=plugin_config.recall_record_resend_media,
        **notice_kwargs,
    )
    fallback_notice = build_recall_notice(record.cached, resend_media=False, **notice_kwargs)

    target = plugin_config.recall_record_report_to
    if target in {"group", "both"}:
        await _send_group_notice(bot, record.group_id, notice, fallback_notice)
    if target in {"private", "both"}:
        for target_user in _private_targets():
            await _send_private_notice(bot, target_user, notice, fallback_notice)


async def _send_group_notice(bot: Bot, group_id: int, notice, fallback_notice) -> None:
    try:
        await bot.send_group_msg(group_id=group_id, message=notice)
    except Exception as exc:
        logger.warning(
            "Recall record notice failed, retrying as text: "
            f"group={group_id} error={type(exc).__name__}: {exc}"
        )
        await bot.send_group_msg(group_id=group_id, message=fallback_notice)


async def _send_private_notice(bot: Bot, user_id: int, notice, fallback_notice) -> None:
    try:
        await bot.send_private_msg(user_id=user_id, message=notice)
    except Exception as exc:
        logger.warning(
            "Recall record private notice failed, retrying as text: "
            f"user={user_id} error={type(exc).__name__}: {exc}"
        )
        await bot.send_private_msg(user_id=user_id, message=fallback_notice)


def _build_forward_node(record: RecallRecord, index: int):
    content = build_recall_forward_content(
        record,
        index=index,
        show_message_id=plugin_config.recall_record_show_message_id,
        resend_media=plugin_config.recall_record_resend_media,
    )
    return MessageSegment.node_custom(
        user_id=record.user_id,
        nickname=record.sender_name,
        content=content,
    )


def _recent_group_recalls(group_id: int) -> list[RecallRecord]:
    _trim_recall_records(group_id)
    now = time.time()
    window = plugin_config.recall_record_query_window_seconds
    return [
        record
        for record in _recall_records.get(group_id, ())
        if now - record.recall_time <= window
    ]


def _group_enabled(group_id: int) -> bool:
    if group_id in plugin_config.recall_record_exclude_groups:
        return False
    include_groups = plugin_config.recall_record_groups
    return not include_groups or group_id in include_groups


def _private_targets() -> set[int]:
    if plugin_config.recall_record_private_targets:
        return set(plugin_config.recall_record_private_targets)
    return {int(user_id) for user_id in driver.config.superusers if str(user_id).isdigit()}


def _event_plain_text(event: GroupMessageEvent) -> str:
    try:
        return event.get_plaintext().strip()
    except Exception:
        return event.message.extract_plain_text().strip()


def _safe_message_copy(message: Message) -> Message:
    copied = Message()
    max_chars = plugin_config.recall_record_max_field_chars
    for segment in message:
        data = {}
        for key, value in dict(segment.data).items():
            if isinstance(value, str):
                data[key] = value[:max_chars]
            else:
                data[key] = value
        copied.append(MessageSegment(type=segment.type, data=data))
    return copied


def _trim_group_cache(group_id: int) -> None:
    now = time.time()
    cache = _message_cache[group_id]
    order = _message_order[group_id]

    while order:
        message_id = order[0]
        record = cache.get(message_id)
        if record is None:
            order.popleft()
            continue
        if len(cache) <= plugin_config.recall_record_cache_size:
            break
        cache.pop(order.popleft(), None)

    ttl = plugin_config.recall_record_cache_ttl_seconds
    while order:
        message_id = order[0]
        record = cache.get(message_id)
        if record is None:
            order.popleft()
            continue
        if now - record.time <= ttl:
            break
        cache.pop(order.popleft(), None)


def _trim_recall_records(group_id: int) -> None:
    now = time.time()
    window = max(
        plugin_config.recall_record_query_window_seconds,
        plugin_config.recall_record_cache_ttl_seconds,
    )
    records = _recall_records[group_id]
    while records and now - records[0].recall_time > window:
        records.popleft()
