"""
Tests for runners and related code
"""
from tests.utils import run_temci


def test_parse_output_option():
    out = run_temci("short exec 'echo foo: 3' --runner time --parse_output").out
    assert "time " in out
    assert "foo " in out


def test_build_before_exec():
    run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "./test"},
                "build_config": {"cmd": "echo 'echo 3' > test; chmod +x test"}
            },
        ]
    })