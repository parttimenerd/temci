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


def test_successful_run_errors():
    d = run_temci("short exec true").yaml_contents["run_output.yaml"][0]
    assert "internal_error" not in d
    assert "error" not in d


def test_errorneous_run():
    d = run_temci("short exec 'exit 1'", expect_success=False).yaml_contents["run_output.yaml"][0]
    assert "error" in d
    e = d["error"]
    assert e["return_code"] is 1