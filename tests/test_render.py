from importlib import import_module

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

from nonebot.adapters.onebot.v11 import Message, MessageSegment

render = import_module("nonebot_plugin_recall_record.render")
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
