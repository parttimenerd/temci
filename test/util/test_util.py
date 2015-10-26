import temci.utils.util as util
import unittest

class TestUtilMethods(unittest.TestCase):

    def test_recursive_contains(self):
        self.assertEqual(util.recursive_contains("sd", {"sd": "sd"}), 1)
        self.assertEqual(util.recursive_contains("sd", {"sd": "sd"}, compare_value=True), 2)
        self.assertEqual(util.recursive_contains("sd", {"sd": "sfd"}), 1)
        self.assertEqual(util.recursive_contains("sd", {"sd": ["sds", "sd"]}), 1)
        self.assertEqual(util.recursive_contains("sd", {"sd": ["sds", "sd"]}, compare_value=True), 2)

    def test_recursive_get(self):
        self.assertEqual(util.recursive_get({"ab": 4}, "ab"), 4)
        self.assertEqual(util.recursive_get({"ab": 4}, "a3b"), None)
        self.assertEqual(util.recursive_get({"ab": {"abc": 4}}, "abc"), 4)
        self.assertEqual(util.recursive_get("sd", "ab"), None)

    def test_recursive_find_key(self):
        def expect(key, data, expected_value):
             self.assertEqual(util.recursive_find_key(key, data), expected_value)
        expect("a", {"a": 3}, ["a"])
        expect("b", {"a", 3}, None)
        expect("b", {"a": "b"}, None)
        expect("b", {"a": {"b": 4}}, ["a", "b"])

    def test_recursive_exec_for_leafs(self):
        paths = []
        values = []
        map = {"a": {"b": "3", "c": "4"}, "ds": "3", "z": {"b": "3", "c": {"b": "3", "c": "4"}}}
        exp_paths = [["a", "b"], ["a", "c"], ["ds"], ["z", "b"], ["z", "c", "b"], ["z", "c", "c"]]
        exp_values = ["3", "4", "3", "3", "3", "4"]
        def func(key, path, value):
            paths.append(path)
            values.append(value)
        util.recursive_exec_for_leafs(map, func)
        self.assertTrue(sorted(paths) == sorted(exp_paths))
        self.assertTrue(sorted(values) == sorted(exp_values))