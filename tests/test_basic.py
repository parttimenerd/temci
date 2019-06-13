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