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

def test_build_before_exec_abort():
    run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "./test", "tags": []},
                "build_config": {"cmd": "exit(1)"}
            }
        ]
    }, expect_success=False, raise_exc=False)


def test_build_before_exec_do_not_arbort():
    assert "3333" in run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "./test", "tags": []},
                "build_config": {"cmd": "exit(1)"}
            },
            {
                "attributes": {"description": "3333"},
                "run_config": {"cmd": "./test", "tags": []},
                "build_config": {"cmd": "echo 'echo 3333' > test; chmod +x test"}
            }
        ]
    }, settings={
        "run": {
            "abort_after_build_error": False
        }
    }, expect_success=False, raise_exc=False).out


def test_build_before_exec_only_build():
    assert "3333" not in run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "attributes": {"description": "3333"},
                "run_config": {"cmd": "./test", "tags": []},
                "build_config": {"cmd": "echo 'echo 3333' > test; chmod +x test"}
            }
        ]
    }, settings={
        "run": {
            "only_build": True
        }
    }, expect_success=False, raise_exc=False).out


def test_successful_run_errors():
    d = run_temci("short exec true").yaml_contents["run_output.yaml"][0]
    assert "internal_error" not in d
    assert "error" not in d


def test_errorneous_run():
    d = run_temci("short exec 'exit 1'", expect_success=False).yaml_contents["run_output.yaml"][0]
    assert "error" in d
    e = d["error"]
    assert e["return_code"] == 1


def test_check_tag_attribute():
    assert run_temci("exec bla.yaml --runs 1", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "echo 1"},
                "attributes": {"tags": "slow"}
            }
        ]
    }, expect_success=False).ret_code != 0


def test_included_blocks():
    out = run_temci("short exec echo ls --included_blocks ls --runs 1").out
    assert "ls" in out and "echo" not in out


def test_discard_blocks_on_error():
    assert run_temci("short exec 'exit 1' --discard_all_data_for_block_on_error", expect_success=False).ret_code == ErrorCode.PROGRAM_ERROR.value


def test_temci_short_shell():
    assert "42" in run_temci_proc("short shell echo 42").out


def test_temci_short_shell_file_creation():
    assert "run_output.yaml" not in run_temci_proc("short shell echo 42").file_contents


def test_pass_arguments():
    assert run_temci("short exec exit --argument 1", expect_success=False).ret_code == ErrorCode.PROGRAM_ERROR.value


def test_included_blocks_single_issue99():
    r = run_temci("exec --in in.yaml --included_blocks b --runs 0", files={
        "in.yaml":
            [
                {
                    "attributes": {
                        "description": "a"
                    },
                    "run_config": {
                        "cmd": "true"
                    }
                },
                {
                    "attributes": {
                        "description": "b"
                    },
                    "run_config": {
                        "cmd": "true"
                    },
                    "build_config": {
                        "cmd": "false"
                    }
                }
            ]
    }, expect_success=False)
    assert r.ret_code != 0


def test_per_block_runs_issue_113():
    assert len(run_temci("exec bla.yaml", files={
        "bla.yaml": [
            {
                "run_config": {"cmd": "echo nooo", "runs": 1}
            }
        ]
    }).yaml_contents["run_output.yaml"][0]["data"]["stime"]) == 1


def test_envinfo_in_result():
    assert any("env_info" in v for v in run_temci("short exec ls").yaml_contents["run_output.yaml"])
