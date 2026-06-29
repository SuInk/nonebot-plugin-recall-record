from importlib import import_module

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

config = import_module("nonebot_plugin_recall_record.config")
Config = config.Config
parse_bool = config.parse_bool
parse_byte_size = config.parse_byte_size
parse_int_set = config.parse_int_set
parse_str_tuple = config.parse_str_tuple


def test_parse_int_set_from_mixed_string() -> None:
    assert parse_int_set("123, 456\n789") == {123, 456, 789}


def test_parse_int_set_from_sequence() -> None:
    assert parse_int_set(["123 456", 789]) == {123, 456, 789}


def test_parse_bool() -> None:
    assert parse_bool("yes") is True
    assert parse_bool("0", default=True) is False
    assert parse_bool("", default=True) is True


def test_parse_byte_size() -> None:
    assert parse_byte_size("10MB", default=1) == 10 * 1024 * 1024
    assert parse_byte_size("2kb", default=1) == 2 * 1024
    assert parse_byte_size("bad", default=123) == 123


def test_parse_str_tuple() -> None:
    assert parse_str_tuple("撤回, 查撤回 recall") == ("撤回", "查撤回", "recall")


def test_parse_str_tuple_default() -> None:
    assert parse_str_tuple("", default=("撤回",)) == ("撤回",)


def test_resend_media_switch_disables_replay_flags() -> None:
    parsed = Config.from_driver_config({"recall_record_resend_media": "false"})

    assert parsed.recall_record_resend_images is False
    assert parsed.recall_record_resend_faces is False
    assert parsed.recall_record_resend_records is False
    assert parsed.recall_record_resend_videos is False
    assert parsed.recall_record_resend_files is False


def test_resend_media_switch_allows_specific_override() -> None:
    parsed = Config.from_driver_config(
        {
            "recall_record_resend_media": "false",
            "recall_record_resend_images": "true",
        }
    )

    assert parsed.recall_record_resend_images is True
    assert parsed.recall_record_resend_faces is False
