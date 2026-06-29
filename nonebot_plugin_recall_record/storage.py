from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from .render import CachedMessage, RecallRecord


class RecallRecordStorage:
    def __init__(
        self,
        path: str | Path,
        *,
        storage_ttl_seconds: int,
        max_messages: int,
        max_recalls: int,
    ) -> None:
        self.path = Path(path).expanduser()
        self.storage_ttl_seconds = storage_ttl_seconds
        self.max_messages = max_messages
        self.max_recalls = max_recalls
        self._connection: sqlite3.Connection | None = None

    def setup(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cached_messages (
                group_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                sender_name TEXT NOT NULL,
                message_json TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                plain_text TEXT NOT NULL,
                time INTEGER NOT NULL,
                PRIMARY KEY (group_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_cached_messages_group_time
                ON cached_messages (group_id, time);

            CREATE TABLE IF NOT EXISTS recall_records (
                group_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                operator_id INTEGER NOT NULL,
                recall_time INTEGER NOT NULL,
                PRIMARY KEY (group_id, message_id, recall_time)
            );
            CREATE INDEX IF NOT EXISTS idx_recall_records_group_time
                ON recall_records (group_id, recall_time);
            """
        )
        connection.commit()
        self.prune()

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    def save_message(self, cached: CachedMessage) -> None:
        connection = self._connect()
        connection.execute(
            """
            INSERT OR REPLACE INTO cached_messages (
                group_id, message_id, user_id, sender_name,
                message_json, raw_message, plain_text, time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cached.group_id,
                cached.message_id,
                cached.user_id,
                cached.sender_name,
                message_to_json(cached.message),
                cached.raw_message,
                cached.plain_text,
                cached.time,
            ),
        )
        connection.commit()

    def save_recall(self, record: RecallRecord) -> None:
        connection = self._connect()
        connection.execute(
            """
            INSERT OR IGNORE INTO recall_records (
                group_id, message_id, user_id, operator_id, recall_time
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.group_id,
                record.message_id,
                record.user_id,
                record.operator_id,
                record.recall_time,
            ),
        )
        if record.cached is not None:
            self.save_message(record.cached)
        else:
            connection.commit()

    def get_message(self, group_id: int, message_id: int) -> CachedMessage | None:
        row = self._connect().execute(
            """
            SELECT group_id, message_id, user_id, sender_name,
                   message_json, raw_message, plain_text, time
            FROM cached_messages
            WHERE group_id = ? AND message_id = ?
            """,
            (group_id, message_id),
        ).fetchone()
        if row is None:
            return None
        return _cached_from_row(row)

    def load_recent_recalls(self, group_id: int, *, since: int) -> list[RecallRecord]:
        rows = self._connect().execute(
            """
            SELECT
                r.group_id, r.message_id, r.user_id, r.operator_id, r.recall_time,
                m.user_id, m.sender_name, m.message_json, m.raw_message, m.plain_text, m.time
            FROM recall_records AS r
            LEFT JOIN cached_messages AS m
                ON m.group_id = r.group_id AND m.message_id = r.message_id
            WHERE r.group_id = ? AND r.recall_time >= ?
            ORDER BY r.recall_time ASC
            """,
            (group_id, since),
        ).fetchall()
        return [_recall_from_row(row) for row in rows]

    def prune(self, *, now: int | None = None) -> None:
        current = int(now or time.time())
        connection = self._connect()
        if self.storage_ttl_seconds > 0:
            cutoff = current - self.storage_ttl_seconds
            connection.execute("DELETE FROM cached_messages WHERE time < ?", (cutoff,))
            connection.execute("DELETE FROM recall_records WHERE recall_time < ?", (cutoff,))
        self._prune_group_limit(
            table="cached_messages",
            max_items=self.max_messages,
            order_columns=("time", "message_id"),
        )
        self._prune_group_limit(
            table="recall_records",
            max_items=self.max_recalls,
            order_columns=("recall_time", "message_id"),
        )
        connection.commit()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self.path))
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
        return self._connection

    def _prune_group_limit(
        self,
        *,
        table: str,
        max_items: int,
        order_columns: tuple[str, str],
    ) -> None:
        if max_items <= 0:
            return
        connection = self._connect()
        groups = connection.execute(
            f"SELECT group_id FROM {table} GROUP BY group_id HAVING COUNT(*) > ?",
            (max_items,),
        ).fetchall()
        order_sql = ", ".join(f"{column} DESC" for column in order_columns)
        for (group_id,) in groups:
            rows = connection.execute(
                f"""
                SELECT rowid FROM {table}
                WHERE group_id = ?
                ORDER BY {order_sql}
                LIMIT -1 OFFSET ?
                """,
                (group_id, max_items),
            ).fetchall()
            row_ids = [row[0] for row in rows]
            if not row_ids:
                continue
            placeholders = ",".join("?" for _ in row_ids)
            connection.execute(
                f"DELETE FROM {table} WHERE rowid IN ({placeholders})",
                row_ids,
            )


def message_to_json(message: Message) -> str:
    payload = [
        {"type": segment.type, "data": _json_safe(dict(segment.data))}
        for segment in message
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def message_from_json(raw: str) -> Message:
    message = Message()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return message
    if not isinstance(payload, list):
        return message
    for item in payload:
        if not isinstance(item, dict):
            continue
        segment_type = str(item.get("type") or "").strip()
        data = item.get("data")
        if not segment_type or not isinstance(data, dict):
            continue
        message.append(MessageSegment(type=segment_type, data=data))
    return message


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _cached_from_row(row: sqlite3.Row | tuple[Any, ...]) -> CachedMessage:
    return CachedMessage(
        group_id=int(row[0]),
        message_id=int(row[1]),
        user_id=int(row[2]),
        sender_name=str(row[3] or ""),
        message=message_from_json(str(row[4] or "[]")),
        raw_message=str(row[5] or ""),
        plain_text=str(row[6] or ""),
        time=int(row[7] or 0),
    )


def _recall_from_row(row: sqlite3.Row | tuple[Any, ...]) -> RecallRecord:
    cached = None
    if row[5] is not None:
        cached = CachedMessage(
            group_id=int(row[0]),
            message_id=int(row[1]),
            user_id=int(row[5]),
            sender_name=str(row[6] or ""),
            message=message_from_json(str(row[7] or "[]")),
            raw_message=str(row[8] or ""),
            plain_text=str(row[9] or ""),
            time=int(row[10] or 0),
        )
    return RecallRecord(
        group_id=int(row[0]),
        message_id=int(row[1]),
        user_id=int(row[2]),
        operator_id=int(row[3]),
        recall_time=int(row[4]),
        cached=cached,
    )
