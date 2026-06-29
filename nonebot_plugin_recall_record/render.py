from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment

MEDIA_SIZE_KEYS = ("size", "file_size", "filesize", "fileSize")
EMOJI_SEGMENT_TYPES = {"face", "mface", "marketface", "dice", "rps"}
DEFAULT_MAX_MEDIA_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class ReplayOptions:
    resend_images: bool = True
    resend_faces: bool = True
    resend_records: bool = True
    resend_videos: bool = True
    resend_files: bool = True
    max_media_bytes: int = DEFAULT_MAX_MEDIA_BYTES
    resend_unknown_size_media: bool = False


@dataclass
class CachedMessage:
    group_id: int
    message_id: int
    user_id: int
    sender_name: str
    message: Message
    raw_message: str
    plain_text: str
    time: int


@dataclass
class RecallRecord:
    group_id: int
    message_id: int
    user_id: int
    operator_id: int
    recall_time: int
    cached: CachedMessage | None = None

    @property
    def sender_name(self) -> str:
        if self.cached is not None and self.cached.sender_name:
            return self.cached.sender_name
        return str(self.user_id)


def sender_name_from_event(event: Any) -> str:
    sender = getattr(event, "sender", None)
    for attr in ("card", "nickname"):
        value = str(getattr(sender, attr, "") or "").strip()
        if value:
            return value
    return str(getattr(event, "user_id", ""))


def plain_text_from_message(message: Message) -> str:
    text = message.extract_plain_text().strip()
    if text:
        return text
    return render_message_as_text(message).strip()


def render_message_as_text(message: Message) -> str:
    parts: list[str] = []
    for segment in message:
        segment_type = segment.type
        data = dict(segment.data)
        if segment_type == "text":
            parts.append(str(data.get("text") or ""))
        elif segment_type == "at":
            qq = str(data.get("qq") or "").strip()
            parts.append(f"[@{qq}]" if qq else "[@]")
        else:
            parts.append(_segment_fallback_text(segment_type, data))
    return "".join(parts)


def build_recall_notice(
    cached: CachedMessage | None,
    *,
    group_id: int,
    message_id: int,
    user_id: int,
    operator_id: int,
    recall_time: int | None,
    show_message_id: bool,
    mention_operator: bool,
    resend_media: bool | None = None,
    replay_options: ReplayOptions | None = None,
) -> Message:
    return _build_recall_message(
        title="检测到群消息撤回",
        cached=cached,
        group_id=group_id,
        message_id=message_id,
        user_id=user_id,
        operator_id=operator_id,
        recall_time=recall_time,
        show_message_id=show_message_id,
        mention_operator=mention_operator,
        resend_media=resend_media,
        replay_options=replay_options,
    )


def build_recall_forward_content(
    record: RecallRecord,
    *,
    index: int,
    show_message_id: bool,
    resend_media: bool | None = None,
    replay_options: ReplayOptions | None = None,
) -> Message:
    return _build_recall_message(
        title=f"第 {index} 条撤回记录",
        cached=record.cached,
        group_id=record.group_id,
        message_id=record.message_id,
        user_id=record.user_id,
        operator_id=record.operator_id,
        recall_time=record.recall_time,
        show_message_id=show_message_id,
        mention_operator=False,
        resend_media=resend_media,
        replay_options=replay_options,
    )


def build_empty_query_message(window_seconds: int) -> Message:
    hours = max(1, int(window_seconds // 3600))
    return Message(f"最近 {hours} 小时没有记录到撤回消息。")


def build_forward_fallback(records: list[RecallRecord], *, window_seconds: int) -> Message:
    hours = max(1, int(window_seconds // 3600))
    lines = [f"最近 {hours} 小时撤回消息记录（合并转发发送失败，已降级为文本）："]
    for index, record in enumerate(records, start=1):
        text = "(未缓存到原消息内容)"
        if record.cached is not None:
            text = (
                record.cached.plain_text
                or render_message_as_text(record.cached.message)
                or "(空消息)"
            )
        lines.append(
            f"{index}. {record.sender_name}({record.user_id}) "
            f"在 {_format_time(record.recall_time)} 撤回：{text}"
        )
    return Message("\n".join(lines))


def build_replay_message(
    message: Message,
    *,
    resend_media: bool | None = None,
    replay_options: ReplayOptions | None = None,
) -> Message:
    options = _coerce_replay_options(replay_options, resend_media=resend_media)
    result = Message()
    text_buffer: list[str] = []

    def flush_text() -> None:
        if text_buffer:
            result.append(MessageSegment.text("".join(text_buffer)))
            text_buffer.clear()

    for segment in message:
        segment_type = segment.type
        data = dict(segment.data)
        if segment_type == "reply":
            continue
        if segment_type == "text":
            text_buffer.append(str(data.get("text") or ""))
            continue
        if segment_type == "at":
            qq = str(data.get("qq") or "").strip()
            text_buffer.append(f"[@{qq}]" if qq else "[@]")
            continue
        if segment_type in EMOJI_SEGMENT_TYPES:
            if options.resend_faces:
                flush_text()
                result.append(_clone_segment(segment_type, data))
            else:
                text_buffer.append(_segment_fallback_text(segment_type, data))
            continue

        media_segment = _replay_media_segment(segment_type, data, options)
        if media_segment is not None:
            flush_text()
            result.append(media_segment)
            continue
        text_buffer.append(_segment_fallback_text(segment_type, data))

    flush_text()
    return result


def _build_recall_message(
    *,
    title: str,
    cached: CachedMessage | None,
    group_id: int,
    message_id: int,
    user_id: int,
    operator_id: int,
    recall_time: int | None,
    show_message_id: bool,
    mention_operator: bool,
    resend_media: bool | None,
    replay_options: ReplayOptions | None,
) -> Message:
    options = _coerce_replay_options(replay_options, resend_media=resend_media)
    lines = [title]
    sender_name = cached.sender_name if cached else str(user_id)
    lines.append(f"发送者：{sender_name} ({user_id})")
    if operator_id != user_id:
        lines.append(f"操作者：{operator_id}")
    if show_message_id:
        lines.append(f"群号：{group_id}")
        lines.append(f"消息ID：{message_id}")
    if recall_time:
        lines.append(f"撤回时间：{_format_time(recall_time)}")

    prefix = Message()
    if mention_operator:
        prefix.append(MessageSegment.at(operator_id))
        prefix.append(MessageSegment.text("\n"))
    prefix.append(MessageSegment.text("\n".join(lines) + "\n原消息：\n"))

    if cached is None:
        prefix.append(MessageSegment.text("(未缓存到原消息内容)"))
        return prefix

    replay = build_replay_message(cached.message, replay_options=options)
    if replay:
        return prefix + replay

    fallback = cached.plain_text or render_message_as_text(cached.message) or "(空消息)"
    prefix.append(MessageSegment.text(fallback))
    return prefix


def _coerce_replay_options(
    replay_options: ReplayOptions | None,
    *,
    resend_media: bool | None,
) -> ReplayOptions:
    if replay_options is not None:
        return replay_options
    if resend_media is None:
        return ReplayOptions()
    return ReplayOptions(
        resend_images=resend_media,
        resend_faces=resend_media,
        resend_records=resend_media,
        resend_videos=resend_media,
        resend_files=resend_media,
        resend_unknown_size_media=resend_media,
    )


def _replay_media_segment(
    segment_type: str,
    data: dict[str, Any],
    options: ReplayOptions,
) -> MessageSegment | None:
    if segment_type == "image":
        if not options.resend_images:
            return None
        return _media_segment(segment_type, data, options, allow_unknown_size=True)
    if segment_type == "record":
        if not options.resend_records:
            return None
        return _media_segment(segment_type, data, options)
    if segment_type == "video":
        if not options.resend_videos:
            return None
        return _media_segment(segment_type, data, options)
    if segment_type == "file":
        if not options.resend_files:
            return None
        return _media_segment(segment_type, data, options)
    return None


def _media_segment(
    segment_type: str,
    data: dict[str, Any],
    options: ReplayOptions,
    *,
    allow_unknown_size: bool = False,
) -> MessageSegment | None:
    if not _within_media_limit(data, options, allow_unknown_size=allow_unknown_size):
        return None
    file_ref = _file_reference(data)
    if not file_ref:
        return None
    if segment_type in {"image", "record", "video", "file"}:
        if data.get("file"):
            return _clone_segment(segment_type, data)
        return MessageSegment(type=segment_type, data={"file": file_ref})
    return None


def _within_media_limit(
    data: dict[str, Any],
    options: ReplayOptions,
    *,
    allow_unknown_size: bool = False,
) -> bool:
    size = _media_size(data)
    if size is None:
        return allow_unknown_size or options.resend_unknown_size_media
    return size <= options.max_media_bytes


def _file_reference(data: dict[str, Any]) -> str:
    return str(
        data.get("url")
        or data.get("file")
        or data.get("path")
        or data.get("file_id")
        or data.get("id")
        or ""
    ).strip()


def _clone_segment(segment_type: str, data: dict[str, Any]) -> MessageSegment:
    return MessageSegment(type=segment_type, data=dict(data))


def _segment_fallback_text(segment_type: str, data: dict[str, Any]) -> str:
    if segment_type == "face":
        face_id = str(data.get("id") or "").strip()
        return f"[表情:{face_id}]" if face_id else "[表情]"
    if segment_type in {"mface", "marketface"}:
        return _segment_summary(data) or "[动画表情]"
    if segment_type == "dice":
        return "[骰子]"
    if segment_type == "rps":
        return "[猜拳]"
    if segment_type == "image":
        return _segment_summary(data) or "[图片]"
    if segment_type == "record":
        return _media_fallback_text("语音", data)
    if segment_type == "video":
        return _media_fallback_text("视频", data)
    if segment_type == "file":
        name = str(data.get("name") or data.get("file") or "").strip()
        size_text = _media_size_text(data)
        if name and size_text:
            return f"[文件:{name} {size_text}]"
        if name:
            return f"[文件:{name}]"
        return f"[文件 {size_text}]" if size_text else "[文件]"
    if segment_type == "reply":
        reply_id = str(data.get("id") or "").strip()
        return f"[回复:{reply_id}]" if reply_id else "[回复]"
    return f"[{segment_type}]"


def _media_fallback_text(label: str, data: dict[str, Any]) -> str:
    size_text = _media_size_text(data)
    return f"[{label} {size_text}]" if size_text else f"[{label}]"


def _segment_summary(data: dict[str, Any]) -> str:
    for key in ("summary", "name", "text", "title"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _media_size_text(data: dict[str, Any]) -> str:
    size = _media_size(data)
    return _format_bytes(size) if size is not None else ""


def _media_size(data: dict[str, Any]) -> int | None:
    for key in MEDIA_SIZE_KEYS:
        size = _parse_size(data.get(key))
        if size is not None:
            return size
    return None


def _parse_size(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    text = str(value).strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgt]?i?b?|字节)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    multiplier = 1
    if unit in {"g", "gb", "gib"}:
        multiplier = 1024 * 1024 * 1024
    elif unit in {"m", "mb", "mib"}:
        multiplier = 1024 * 1024
    elif unit in {"k", "kb", "kib"}:
        multiplier = 1024
    return int(number * multiplier)


def _format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


def _format_time(timestamp: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
