from importlib import import_module

import nonebot

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init(driver="~none")

config = import_module("nonebot_plugin_recall_record.config")
parse_bool = config.parse_bool
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


def test_parse_str_tuple() -> None:
    assert parse_str_tuple("撤回, 查撤回 recall") == ("撤回", "查撤回", "recall")


def test_parse_str_tuple_default() -> None:
    assert parse_str_tuple("", default=("撤回",)) == ("撤回",)
