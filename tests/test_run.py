"""
Tests for runners and related code
"""
import pytest

from temci.scripts.cli import ErrorCode
from tests.utils import run_temci, run_temci_proc


def test_parse_output_option():
    out = run_temci("short exec 'echo foo: 3' --runner time --parse_output").out
    assert "time " in out
    assert "foo " in out


def test_build_before_exec():
    run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "./test", "tags": []},
                "build_config": {"cmd": "echo 'echo 3' > test; chmod +x test"}
            }
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


def test_check_tag_attribute():
    with pytest.raises(TypeError):
        assert run_temci("exec bla.yaml --runs 1", files={
            "bla.yaml": [
                {
                    "run_config": {"cmd": "echo 1"},
                    "attributes": {"tags": "slow"}
                }
            ]
        }).ret_code != 0


def test_included_blocks():
    out = run_temci("short exec echo ls --included_blocks ls --runs 1").out
    assert "ls" in out and "echo" not in out


def test_discard_blocks_on_error():
    assert run_temci("short exec 'exit 1' --discard_all_data_for_block_on_error", expect_success=False).ret_code == ErrorCode.PROGRAM_ERROR.value
