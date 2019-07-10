"""
Tests related to temci's init commands
"""
from tests.utils import run_temci


def test_temci_init_build_config():
    run_temci("build a.yaml", files={
        "a.yaml": run_temci("init build_config").file_contents["build_config.yaml"]
    })


def test_temci_init_run_config():
    run_temci("exec a.yaml", files={
        "a.yaml": run_temci("init run_config").yaml_contents["run_config.yaml"]
    })
