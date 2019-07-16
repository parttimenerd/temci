"""
Basic command line tool tests
"""
from tests.utils import run_temci


def test_max_runs_per_block():
    assert " 1 single bench" in run_temci("exec bla.yaml", settings={
            "run": {
                "max_runs": 4,
                "min_runs": 2
            }
        },
        files={"bla.yaml": [{
          "run_config":
              {
                  "cmd": "ls",
                  "max_runs": 1
              }
          }, {
          "run_config":
              {
                  "cmd": "ls .",
                  "max_runs": 3
              }
          }]}).out


def test_config_default_values():
    assert "11 single bench" in run_temci("short exec ls --log_level debug", settings={
        "run": {
            "runs": 11
        }
    }).out


def test_format():
    assert run_temci("format 1.001 0.05").out == "1.0(01)"