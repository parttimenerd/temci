"""
Tests related to the typecheck code
"""
from temci.utils.typecheck import verbose_isinstance, Int, Dict


def test_dict_missing_key_error_msg():
    assert "key 'a' " in verbose_isinstance({}, Dict({"a": Int()})).msg.lower()


def test_dict_wrong_type_error_msg():
    assert verbose_isinstance({"a": "s"}, Dict({"a": Int()})).msg.lower().startswith("'s'")
