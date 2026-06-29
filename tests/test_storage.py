import time
from importlib import import_module

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

from nonebot.adapters.onebot.v11 import Message, MessageSegment

render = import_module("nonebot_plugin_recall_record.render")
storage_module = import_module("nonebot_plugin_recall_record.storage")

CachedMessage = render.CachedMessage
RecallRecord = render.RecallRecord
RecallRecordStorage = storage_module.RecallRecordStorage
message_from_json = storage_module.message_from_json
message_to_json = storage_module.message_to_json


def test_message_json_roundtrip() -> None:
    message = Message(
        [
            MessageSegment.text("hello"),
            MessageSegment(type="image", data={"file": "a.png", "summary": "[图片]"}),
            MessageSegment(type="mface", data={"summary": "[动画表情]", "url": "u"}),
        ]
    )

    restored = message_from_json(message_to_json(message))

    assert [(segment.type, dict(segment.data)) for segment in restored] == [
        ("text", {"text": "hello"}),
        ("image", {"file": "a.png", "summary": "[图片]"}),
        ("mface", {"summary": "[动画表情]", "url": "u"}),
    ]


def test_storage_survives_reopen(tmp_path) -> None:
    db_path = tmp_path / "recall.sqlite3"
    now = int(time.time())
    cached = CachedMessage(
        group_id=100,
        message_id=200,
        user_id=300,
        sender_name="Winter",
        message=Message([MessageSegment.text("hello")]),
        raw_message="hello",
        plain_text="hello",
        time=now,
    )
    record = RecallRecord(
        group_id=100,
        message_id=200,
        user_id=300,
        operator_id=300,
        recall_time=now,
        cached=cached,
    )

    storage = RecallRecordStorage(
        db_path,
        storage_ttl_seconds=86400,
        max_messages=500,
        max_recalls=500,
    )
    storage.setup()
    storage.save_message(cached)
    storage.save_recall(record)
    storage.close()

    reopened = RecallRecordStorage(
        db_path,
        storage_ttl_seconds=86400,
        max_messages=500,
        max_recalls=500,
    )
    reopened.setup()
    records = reopened.load_recent_recalls(100, since=0)

    assert len(records) == 1
    assert records[0].sender_name == "Winter"
    assert records[0].cached is not None
    assert records[0].cached.message.extract_plain_text() == "hello"
    reopened.close()


def test_storage_prune_by_ttl_and_group_limit(tmp_path) -> None:
    storage = RecallRecordStorage(
        tmp_path / "recall.sqlite3",
        storage_ttl_seconds=100,
        max_messages=1,
        max_recalls=1,
    )
    storage.setup()
    for message_id, timestamp in ((1, 900), (2, 990), (3, 995)):
        cached = CachedMessage(
            group_id=100,
            message_id=message_id,
            user_id=300,
            sender_name="Winter",
            message=Message([MessageSegment.text(str(message_id))]),
            raw_message=str(message_id),
            plain_text=str(message_id),
            time=timestamp,
        )
        storage.save_message(cached)
        storage.save_recall(
            RecallRecord(
                group_id=100,
                message_id=message_id,
                user_id=300,
                operator_id=300,
                recall_time=timestamp,
                cached=cached,
            )
        )

    storage.prune(now=1000)

    records = storage.load_recent_recalls(100, since=0)
    assert [record.message_id for record in records] == [3]
    assert storage.get_message(100, 1) is None
    assert storage.get_message(100, 3) is not None
    storage.close()
