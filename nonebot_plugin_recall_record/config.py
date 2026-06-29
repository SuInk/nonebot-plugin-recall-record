from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ReportTarget = Literal["group", "private", "both", "none"]
WorkMode = Literal["query", "auto", "both"]
DEFAULT_MAX_MEDIA_BYTES = 10 * 1024 * 1024
DEFAULT_STORAGE_PATH = "data/nonebot_plugin_recall_record/recall_record.sqlite3"


def parse_int_set(value: Any) -> set[int]:
    if value in (None, ""):
        return set()
    if isinstance(value, int):
        return {value}
    if isinstance(value, (set, list, tuple)):
        result: set[int] = set()
        for item in value:
            result.update(parse_int_set(item))
        return result
    return {int(token) for token in re.findall(r"\d+", str(value))}


def parse_bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def parse_byte_size(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgt]?i?b?|字节)?", text)
    if not match:
        return default
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


def parse_str_tuple(value: Any, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        parts = re.split(r"[,，;；\n\r\t ]+", value)
    elif isinstance(value, (set, list, tuple)):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]
    return tuple(part.strip() for part in parts if part and part.strip())


DEFAULT_QUERY_KEYWORDS = (
    "撤回",
    "防撤回",
    "查撤回",
    "最近撤回",
    "撤回消息",
    "撤回记录",
    "recall",
    "anti-recall",
)


class Config(BaseModel):
    recall_record_enabled: bool = True
    recall_record_mode: WorkMode = "query"
    recall_record_cache_size: int = Field(default=500, ge=1)
    recall_record_recall_cache_size: int = Field(default=500, ge=1)
    recall_record_cache_ttl_seconds: int = Field(default=86400, ge=1)
    recall_record_query_window_seconds: int = Field(default=86400, ge=1)
    recall_record_persist: bool = True
    recall_record_storage_path: str = DEFAULT_STORAGE_PATH
    recall_record_storage_ttl_seconds: int = Field(default=7 * 86400, ge=1)
    recall_record_query_keywords: tuple[str, ...] = DEFAULT_QUERY_KEYWORDS
    recall_record_max_field_chars: int = Field(default=4096, ge=128)
    recall_record_forward_limit: int = Field(default=0, ge=0)
    recall_record_groups: set[int] = Field(default_factory=set)
    recall_record_exclude_groups: set[int] = Field(default_factory=set)
    recall_record_exclude_users: set[int] = Field(default_factory=set)
    recall_record_report_to: ReportTarget = "group"
    recall_record_private_targets: set[int] = Field(default_factory=set)
    recall_record_resend_media: bool = True
    recall_record_resend_images: bool = True
    recall_record_resend_faces: bool = True
    recall_record_resend_records: bool = True
    recall_record_resend_videos: bool = True
    recall_record_resend_files: bool = True
    recall_record_max_media_bytes: int = Field(default=DEFAULT_MAX_MEDIA_BYTES, ge=0)
    recall_record_resend_unknown_size_media: bool = False
    recall_record_mention_operator: bool = False
    recall_record_show_message_id: bool = False

    @classmethod
    def from_driver_config(cls, raw_config: Any) -> Config:
        data = _dump_config(raw_config)
        _apply_resend_media_switch(data)
        int_set_fields = {
            "recall_record_groups",
            "recall_record_exclude_groups",
            "recall_record_exclude_users",
            "recall_record_private_targets",
        }
        bool_fields = {
            "recall_record_enabled": True,
            "recall_record_persist": True,
            "recall_record_resend_media": True,
            "recall_record_resend_images": True,
            "recall_record_resend_faces": True,
            "recall_record_resend_records": True,
            "recall_record_resend_videos": True,
            "recall_record_resend_files": True,
            "recall_record_resend_unknown_size_media": False,
            "recall_record_mention_operator": False,
            "recall_record_show_message_id": False,
        }
        for field in int_set_fields:
            data[field] = parse_int_set(data.get(field))
        for field, default in bool_fields.items():
            data[field] = parse_bool(data.get(field), default=default)
        data["recall_record_max_media_bytes"] = parse_byte_size(
            data.get("recall_record_max_media_bytes"),
            default=DEFAULT_MAX_MEDIA_BYTES,
        )
        if data.get("recall_record_storage_path"):
            data["recall_record_storage_path"] = str(Path(data["recall_record_storage_path"]))
        data["recall_record_query_keywords"] = parse_str_tuple(
            data.get("recall_record_query_keywords"),
            default=DEFAULT_QUERY_KEYWORDS,
        )
        for field in ("recall_record_report_to", "recall_record_mode"):
            if data.get(field):
                data[field] = str(data[field]).strip().lower()
        return _model_validate(cls, data)


def _dump_config(raw_config: Any) -> dict[str, Any]:
    if isinstance(raw_config, dict):
        data = dict(raw_config)
    elif hasattr(raw_config, "model_dump"):
        data = dict(raw_config.model_dump())
    elif hasattr(raw_config, "dict"):
        data = dict(raw_config.dict())
    else:
        data = dict(getattr(raw_config, "__dict__", {}))
    return _with_legacy_group_antirecall_keys(data)


def _with_legacy_group_antirecall_keys(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    legacy_prefix = "group_antirecall_"
    current_prefix = "recall_record_"
    for key, value in data.items():
        if not key.startswith(legacy_prefix):
            continue
        current_key = current_prefix + key[len(legacy_prefix) :]
        result.setdefault(current_key, value)
    return result


def _apply_resend_media_switch(data: dict[str, Any]) -> None:
    if "recall_record_resend_media" not in data:
        return
    for field in (
        "recall_record_resend_images",
        "recall_record_resend_faces",
        "recall_record_resend_records",
        "recall_record_resend_videos",
        "recall_record_resend_files",
    ):
        data.setdefault(field, data["recall_record_resend_media"])


def _model_validate(model: type[Config], data: dict[str, Any]) -> Config:
    if hasattr(model, "model_validate"):
        return model.model_validate(data)
    return model.parse_obj(data)
