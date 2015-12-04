import unittest, os, yaml
from temci.run.run_processor import RunProcessor
from temci.utils.settings import Settings
from temci.tester.report_processor import ReportProcessor
import time, humanfriendly

def path(name):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), name))

class Test(unittest.TestCase):

    def test_console(self):
        Settings()["run/driver"] = "exec"
        Settings()["run/exec_misc/runner"] = "perf_stat"
        Settings()["run/out"] = path("run_output2.yaml")
        Settings()["run/in"] = path("console_run.exec.yaml")
        Settings()["report/in"] = path("run_output2.yaml")
        Settings()["run/min_runs"] = 100
        Settings()["run/max_runs"] = 100
        Settings()["stats/properties"] = ["ov-time", "cache-misses", "cycles",
                                          "task-clock", "instructions", "branch-misses", "cache-references"]
        Settings()["run/cpuset/active"] = True
        Settings()["run/cpuset/parallel"] = 1
        Settings()["run/exec_plugins/exec_active"] = ["stop_start"]#["nice", "env_randomize", "other_nice", "stop_start"]
        Settings()["run/exec_plugins/nice_misc"] = {
            "nice": -15,
            "io_nice": 1,
        }
        Settings()["run/exec_plugins/other_nice_misc"] = {
            "nice": 19
        }
        processor = RunProcessor()
        t = time.time()
        processor.benchmark()
        print(humanfriendly.format_timespan(time.time() - t))
        #processor.teardown()

        rprocessor = ReportProcessor()
        rprocessor.report()

"""
        Settings()["run/out"] = path("run_output3.yaml")
        Settings()["run/in"] = path("console_run.yaml")
        Settings()["report/in"] = path("run_output3.yaml")
        Settings()["run/cpuset/active"] = False
        #processor = RunProcessor()
        #processor.benchmark()
        #processor.store_and_teardown()

        rprocessor = ReportProcessor()
        #rprocessor.report()
"""