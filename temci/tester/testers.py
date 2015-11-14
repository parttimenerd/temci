"""
Contains the tester base class and several simple implementations.
"""

import temci.utils.util as util
import numpy as np
import scipy.stats as st
import scipy
from temci.utils.typecheck import *
from temci.utils.settings import Settings
from temci.utils.registry import AbstractRegistry, register


class TesterRegistry(AbstractRegistry):

    def __init__(self):
        super().__init__(["stats"], "tester", use_list=False, default="t")


class Tester(object, metaclass=util.Singleton):
    """
    A tester tests the probability of the nullhypothesis of two same length list of observations.

    This is a base class that shouldn't be instantiated.
    """

    scipy_stat_method = ""

    def __init__(self, misc_settings: dict, uncertainty_range: tuple):
        """
        :param data1: first list of of data points
        :param data2: second list of data points
        :param uncertainty_range: (start, end) probability tuple that gives range in which the tester doesn't give
         a definitive result on the nullhypothesis check
        """
        self.uncertainty_range = uncertainty_range
        assert isinstance(uncertainty_range, Tuple(Float(), Float()))
        self.misc_settings = misc_settings

    def test(self, data1: list, data2: list) -> float:
        """
        Calculates the probability of the null hypotheses.
        :raises ValueError if both lists haven't the same length
        """
        if len(data1) != len(data2):
            raise ValueError("Both data list have not the same length ({} != {})".format(len(data1), len(data2)))
        return self._test_impl(data1, data2)

    def _test_impl(self, data1: list, data2: list) -> float:
        return getattr(st, self.scipy_stat_method)(data1, data2)[1]

    def is_uncertain(self, data1: np.array, data2: np.array) -> bool:
        return self.uncertainty_range[0] <= self.test(data1, data2) <= self.uncertainty_range[1]

    def is_equal(self, data1: np.array, data2: np.array):
        return self.test(data1, data2) > sum(self.uncertainty_range) / 2

    def estimate_needed_runs(self, data1: np.array, data2: np.array, run_bin_size: int = 5, times: int = 10) -> int:
        """
        Calculate a approximation of the needed length of both observations that is needed for the
        p value to lie outside the uncertainty range.
        :param data1: list of observations
        :param data2: list of observations
        :param run_bin_size: granularity of the observation (> 0)
        :return: approximation of needed runs
        """
        # todo test with realworld data

        def add_rand(data, avg, dev):
            return list(data) + [np.random.normal(loc=avg, scale=dev) for i in range(0, run_bin_size)]

        def middlenes(p_val):
            return abs(p_val - (self.uncertainty_range[0] + self.uncertainty_range[1]) / 2)

        (data1_cp, data2_cp) = (np.copy(data1), np.copy(data2))
        while self.is_uncertain(data1_cp, data2_cp):
            (dev1, dev2) = (scipy.std(data1_cp), scipy.std(data2_cp))
            (avg1, avg2) = (scipy.mean(data1_cp), scipy.mean(data2_cp))
            l = []
            for i in range(0, times):
                (tmp1, tmp2) = (add_rand(data1_cp, avg1, dev1), add_rand(data2_cp, avg2, dev2))
                l.append((self.test(tmp1, tmp2), (data1_cp, data2_cp)))
            (p_val, (data1_cp, data2_cp)) = sorted(l, key=lambda t: middlenes(t[0]))[len(l) // 2]
        return len(data1_cp)


@register(TesterRegistry, name="t", misc_type=Dict(), misc_default={})
class TTester(Tester):
    """
    Implementation of the Tester base class for the student's t test.
    """

    scipy_stat_method = "ttest_ind"