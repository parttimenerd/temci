from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.tester.testers import Tester, TTester
import unittest

class TesterMock(Tester):

    x = 0.1

    def _test_impl(self, data1: list, data2: list) -> float:
        return self.x

class TesterTester(unittest.TestCase):

    def test_test(self):
        tester = TesterMock({}, (0.1, 0.3))
        with self.assertRaises(ValueError):
            tester.test([2], [3, 4])
        data = [[4], [5]]
        self.assertEqual(tester.test(*data), 0.1)
        self.assertTrue(tester.is_uncertain(*data))
        self.assertFalse(tester.is_equal(*data))
        tester.x = 0.22
        self.assertTrue(tester.is_equal(*data))
        #tester.estimate_needed_runs(*data)