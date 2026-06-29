from importlib import import_module

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

from nonebot.adapters.onebot.v11 import Message, MessageSegment

render = import_module("nonebot_plugin_recall_record.render")
ReplayOptions = render.ReplayOptions
build_replay_message = render.build_replay_message
render_message_as_text = render.render_message_as_text


def test_render_message_as_text() -> None:
    message = Message(
        [
            MessageSegment.text("hello"),
            MessageSegment.at(123),
            MessageSegment.image("https://example.com/a.png"),
        ]
    )
    assert render_message_as_text(message) == "hello[@123][图片]"


def test_build_replay_message_avoids_reply_and_at_ping() -> None:
    message = Message(
        [
            MessageSegment.reply(100),
            MessageSegment.text("hi "),
            MessageSegment.at(123),
        ]
    )
    replay = build_replay_message(message, resend_media=True)
    assert replay.extract_plain_text() == "hi [@123]"


def test_build_replay_message_preserves_image_and_face_by_default() -> None:
    message = Message(
        [
            MessageSegment.image("https://example.com/a.png"),
            MessageSegment(type="face", data={"id": "14"}),
            MessageSegment(type="mface", data={"summary": "[动画表情]", "url": "u"}),
        ]
    )

    replay = build_replay_message(message)

    assert [segment.type for segment in replay] == ["image", "face", "mface"]


def test_build_replay_message_respects_media_size_limit() -> None:
    message = Message(
        [
            MessageSegment(type="record", data={"file": "small.amr", "size": 1024}),
            MessageSegment(type="video", data={"file": "large.mp4", "size": 11 * 1024 * 1024}),
            MessageSegment(
                type="file",
                data={"file": "large.zip", "name": "large.zip", "size": "11MB"},
            ),
        ]
    )

    replay = build_replay_message(message)

    segments = list(replay)
    assert segments[0].type == "record"
    assert replay.extract_plain_text() == "[视频 11.0MB][文件:large.zip 11.0MB]"


def test_build_replay_message_skips_unknown_size_heavy_media() -> None:
    message = Message(
        [
            MessageSegment(type="video", data={"file": "unknown.mp4"}),
            MessageSegment(type="file", data={"file": "unknown.zip", "name": "unknown.zip"}),
        ]
    )

    replay = build_replay_message(message)

    assert [segment.type for segment in replay] == ["text"]
    assert replay.extract_plain_text() == "[视频][文件:unknown.zip]"


def test_build_replay_message_allows_unknown_size_when_enabled() -> None:
    message = Message([MessageSegment(type="video", data={"file": "unknown.mp4"})])

    replay = build_replay_message(
        message,
        replay_options=ReplayOptions(resend_unknown_size_media=True),
    )

    assert [segment.type for segment in replay] == ["video"]


def test_build_replay_message_respects_resend_media_switch() -> None:
    message = Message(
        [
            MessageSegment.image("https://example.com/a.png"),
            MessageSegment(type="face", data={"id": "14"}),
        ]
    )

    replay = build_replay_message(message, resend_media=False)

    assert [segment.type for segment in replay] == ["text"]
    assert replay.extract_plain_text() == "[图片][表情:14]"
