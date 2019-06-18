"""
Tests related to the processing of settings
"""
from tests.utils import run_temci


def test_config_not_ignored():
    """
    Issue "Config now seems to be ignored completely after type checking #62"
    """
    assert "11 single benchmarks" in run_temci("short exec ls", settings={"run": {"runs": 11}}).out


def test_settings_set_config_option_not_to_itself():
    assert run_temci("init settings").yaml_contents["temci.yaml"]["settings"] != "temci.yaml"