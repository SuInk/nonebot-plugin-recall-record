from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment


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
        elif segment_type == "face":
            face_id = str(data.get("id") or "").strip()
            parts.append(f"[表情:{face_id}]" if face_id else "[表情]")
        elif segment_type == "image":
            summary = str(data.get("summary") or "").strip()
            parts.append(summary or "[图片]")
        elif segment_type == "record":
            parts.append("[语音]")
        elif segment_type == "video":
            parts.append("[视频]")
        elif segment_type == "file":
            name = str(data.get("name") or data.get("file") or "").strip()
            parts.append(f"[文件:{name}]" if name else "[文件]")
        elif segment_type == "reply":
            reply_id = str(data.get("id") or "").strip()
            parts.append(f"[回复:{reply_id}]" if reply_id else "[回复]")
        else:
            parts.append(f"[{segment_type}]")
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
    resend_media: bool,
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
    )


def build_recall_forward_content(
    record: RecallRecord,
    *,
    index: int,
    show_message_id: bool,
    resend_media: bool,
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


def build_replay_message(message: Message, *, resend_media: bool) -> Message:
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
        if segment_type == "face":
            face_id = str(data.get("id") or "").strip()
            text_buffer.append(f"[表情:{face_id}]" if face_id else "[表情]")
            continue

        media_segment = _media_segment(segment_type, data) if resend_media else None
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
    resend_media: bool,
) -> Message:
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

    replay = build_replay_message(cached.message, resend_media=resend_media)
    if replay:
        return prefix + replay

    fallback = cached.plain_text or render_message_as_text(cached.message) or "(空消息)"
    prefix.append(MessageSegment.text(fallback))
    return prefix


def _media_segment(segment_type: str, data: dict[str, Any]) -> MessageSegment | None:
    file_ref = str(data.get("url") or data.get("file") or "").strip()
    if not file_ref:
        return None
    if segment_type == "image":
        return MessageSegment.image(file_ref)
    if segment_type == "record":
        return MessageSegment.record(file_ref)
    if segment_type == "video":
        return MessageSegment.video(file_ref)
    return None


def _segment_fallback_text(segment_type: str, data: dict[str, Any]) -> str:
    if segment_type == "image":
        return str(data.get("summary") or "[图片]")
    if segment_type == "record":
        return "[语音]"
    if segment_type == "video":
        return "[视频]"
    if segment_type == "file":
        name = str(data.get("name") or data.get("file") or "").strip()
        return f"[文件:{name}]" if name else "[文件]"
    return f"[{segment_type}]"


def _format_time(timestamp: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
