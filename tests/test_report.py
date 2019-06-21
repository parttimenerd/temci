"""
Tests for reporters
"""
from tests.utils import run_temci


def test_console_reporter_auto_mode():
    d = lambda d: {
        "attributes": {"description": "XYZ" + d},
        "data": {"p": [1]}
    }
    out = run_temci("report in.yaml --console_mode auto",
                    files={
                        "in.yaml": [d(""), d(""), d(""), d("W"), d("X")]
                    }).out
    assert "Report for XYZ" in out
    assert any("XYZ [1]" in l and "XYZ [2]" in l for l in out.split("\n"))
    assert "XYZX" in out


def test_support_multiple_inputs():
    d = lambda: {
        "attributes": {"description": "XYZ"},
        "data": {"p": [1]}
    }
    out = run_temci("report in1.yaml in2.yaml --console_mode auto",
                    files={
                        "in1.yaml": [d()],
                        "in2.yaml": [d(), d()]
                    }).out
    assert any("XYZ [1]" in l and "XYZ [2]" in l for l in out.split("\n"))
