"""
Test the loading of plugin file
"""
from tests.utils import run_temci_proc


def test_basic():
    assert run_temci_proc("", files={
        "bla.py": "print(42)"
    }, misc_env={"TEMCI_PLUGIN_PATH": "bla.py"}).out.startswith("42")