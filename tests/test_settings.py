"""
Tests related to the processing of settings
"""
from tests.utils import run_temci


def test_config_not_ignored():
    """
    Issue "Config now seems to be ignored completely after type checking #62"
    """
    assert "3 single benchmarks" in run_temci("short exec ls", settings={"run": {"runs": 3}}).out
