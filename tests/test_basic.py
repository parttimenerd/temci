"""
Basic command line tool tests
"""
from tests.utils import run_temci


def test_max_runs_per_block():
    assert "3 single bench" in run_temci("exec bla.yaml", files={"bla.yaml": [{
        "run_config":
            {
                "cmd": "ls",
                "max_runs": 3
            }
    }]}).out


def test_config_default_values():
    assert "11 single bench" in run_temci("short exec ls --log_level debug --config temci.yaml", files={"temci.yaml": {
        "run": {
            "runs": 11
        }
    }}).out