from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.tester.rundata import RunData, RunDataStatsHelper
from temci.tester.report import ConsoleReporter
from copy import deepcopy
import unittest


class RunDataTester(unittest.TestCase):

    def test_to_dict_and_init(self):
        with self.assertRaises(ValueError):
            data = RunData(["a"])
        data = RunData(["a", "ov-time"], attributes={"abc": 3})
        self.assertEqual(data.to_dict(), {
            "attributes": {"abc": 3},
            "data": {"a": [], "ov-time": []}
        })

    def test_add_data_block(self):
        data = RunData(["ov-time"])
        with self.assertRaises(ValueError):
            data.add_data_block({})
        data = RunData(["ov-time", "a"])
        with self.assertRaises(ValueError):
            data.add_data_block({"a": []})
        with self.assertRaises(ValueError):
            data.add_data_block({"a": [3], "ov-time": [4, 5]})
        data.add_data_block({"a": [3], "ov-time": [4]})
        self.assertEqual(data.to_dict(), {
            "attributes": {},
            "data": {"a": [3], "ov-time": [4]}
        })


class RunDataStatsHelperTest(unittest.TestCase):

    def setUp(self):
        valid = {
            "stats": {
                "tester": "t",
                "t_misc": {},
                "properties": ["ov-time"],
                "uncertainty_range": (0.1, 0.3)
            },
            "runs": [
                {
                    "attributes": {"nr": 0},
                    "data": {"ov-time": [1, 2]}
                },
                {
                    "attributes": {"nr": 1},
                    "data": {"ov-time": [1.0, 2.2]}
                }
            ]
        }
        self.helper = RunDataStatsHelper.init_from_dicts(valid["stats"], valid["runs"])

    def test_init_from_dict(self):
        valid = {
            "stats": {
                "tester": "t",
                "t_misc": {},
                "properties": ["ov-time"],
                "uncertainty_range": (0.1, 0.3)
            },
            "runs": [
                {
                    "attributes": {"nr": 0},
                    "data": {"ov-time": [1, 2]}
                }
            ]
        }
        RunDataStatsHelper.init_from_dicts(valid["stats"], valid["runs"])
        with self.assertRaises(ValueError):
            tmp = deepcopy(valid)
            tmp["stats"].update({"properties": "t"})
            RunDataStatsHelper.init_from_dicts(tmp, valid["runs"])
        with self.assertRaises(TypeError):
            RunDataStatsHelper.init_from_dicts(valid["stats"], [{
                    "attributes": {"nr": 0},
                    "data": {"ov-time": [1, "4"]}
                }])
        def test_properties(props_list: list, expected_result: list):
            tmp = deepcopy(valid)
            tmp["stats"].update({"properties": props_list})
            helper = RunDataStatsHelper.init_from_dicts(tmp["stats"], valid["runs"])
            self.assertListEqual(helper.properties, expected_result)

        test_properties(["ov-time"], [("ov-time", "ov-time")])
        test_properties([("ov-time", "description")], [("ov-time", "description")])

    def test_small_methods(self):
        #self.helper.estimate_time()
        #self.helper.estimate_time_for_next_round()
        self.helper.get_program_ids_to_bench()

    def test_add_data_block(self):
        self.helper.add_data_block(1, {"ov-time": [3, 4]})
        self.assertEqual(len(self.helper.runs[1]["ov-time"]), 4)
        with self.assertRaises(ValueError):
            self.helper.add_data_block(2, {"ov-time": [3, 4]})

    def test_add_run_data(self):
        ConsoleReporter(self.helper).report()
        self.helper.add_run_data()
        self.helper.add_data_block(2, {"ov-time": [3, 4]})
        self.assertEqual(len(self.helper.runs[2]["ov-time"]), 2)

    def test_get_evaluation(self):
        pass