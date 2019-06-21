"""
Tests for reporters
"""
from tests.utils import run_temci


def test_console_reporter_auto_mode():
    out = run_temci("report in.yaml --console_mode auto",
                    files={
                        "in.yaml": [
                            {
                                "attributes": {"description": "XYZ"},
                                "data": {"p": [1]}
                            },
                            {
                                "attributes": {"description": "XYZ"},
                                "data": {"p": [1]}
                            },
                            {
                                "attributes": {"description": "XYZ"},
                                "data": {"p": [1]}
                            },
                            {
                                "attributes": {"description": "XYZW"},
                                "data": {"p": [1]}
                            },
                            {
                                "attributes": {"description": "XYZX"},
                                "data": {"p": [1]}
                            }
                        ]
                    }).out
    assert "Report for XYZ" in out
    assert any("XYZ [1]" in l and "XYZ [2]" in l for l in out.split("\n"))
    assert "XYZX" in out
