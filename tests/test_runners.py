"""
Tests for runners and related code
"""
from tests.utils import run_temci


def test_parse_output_option():
    out = run_temci("short exec 'echo foo: 3' --runner time --parse_output").out
    assert "time " in out
    assert "foo " in out