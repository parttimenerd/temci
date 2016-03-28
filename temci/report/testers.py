"""
Contains the tester base class and several simple implementations
that simplify the work with statistical hypothesis tests.
"""

import warnings
import temci.utils.util as util
import typing as t
if util.can_import("scipy"):
    import scipy.stats as st
    import scipy.optimize as opti
    import numpy as np
from temci.utils.typecheck import *
from temci.utils.registry import AbstractRegistry, register
import logging

Number = t.Union[int, float]

class TesterRegistry(AbstractRegistry):

    settings_key_path = "stats"
    use_key = "tester"
    use_list = False
    default = "t"
    registry = {}
    plugin_synonym = ("tester", "testers")


class Tester(object, metaclass=util.Singleton):
    """
    A tester tests the probability of the nullh ypothesis of two same length list of observations.

    This is a base class that shouldn't be instantiated.
    """

    scipy_stat_method = None  # type: t.Optional[str]
    """ Used method of the scipy.stats module if the _test_impl isn't reimplemented """
    name = ""
    """ Name of the implemented statistical test """

    def __init__(self, misc_settings: dict, uncertainty_range: t.Tuple[float, float]):
        """
        Creates a new instance.
        :param misc_settings: Additional settings
        :param uncertainty_range: (start, end) probability tuple that gives range in which the tester doesn't give
             a definitive result on the nullhypothesis check
        """
        self.uncertainty_range = uncertainty_range
        """
        (start, end) probability tuple that gives range in which the tester doesn't give
             a definitive result on the nullhypothesis check
        """
        assert isinstance(uncertainty_range, Tuple(Float(), Float()))
        self.misc_settings = misc_settings
        """ Additional settings """

    def test(self, data1: t.List[Number], data2: t.List[Number]) -> float:
        """
        Calculates the probability of the null hypotheses for two samples.
        """
        res = 0
        min_len = min(len(data1), len(data2))
        with warnings.catch_warnings(record=True) as w:
            res = self._test_impl(data1[0:min_len], data2[0: min_len])
        return res

    def _test_impl(self, data1: t.List[Number], data2: t.List[Number]) -> float:
        """
        Calculates the probability of the null hypotheses for two equal sized samples.
        """
        assert self.scipy_stat_method
        return getattr(st, self.scipy_stat_method)(data1, data2)[-1]

    def is_uncertain(self, data1: t.List[Number], data2: t.List[Number]) -> bool:
        """ Does the probability of the null hypothesis for two samples lie in the uncertainty range? """
        val = self.test(data1, data2)
        return min(len(data1), len(data2)) == 0 or \
               self.uncertainty_range[0] <= val <= self.uncertainty_range[1] or \
               val != val

    def is_equal(self, data1: t.List[Number], data2: t.List[Number]) -> bool:
        """ Are the two samples not significantly unequal regarding the probability of the null hypothesis? """
        return self.test(data1, data2) > max(*self.uncertainty_range)

    def is_unequal(self, data1: t.List[Number], data2: t.List[Number]) -> bool:
        """ Are the two samples significantly unequal regarding the probability of the null hypothesis? """
        return self.test(data1, data2) < min(*self.uncertainty_range)

    def estimate_needed_runs(self, data1: list, data2: list,
                             run_bin_size: int, min_runs: int,
                             max_runs: int) -> int:
        """
        Calculate a approximation of the needed length of both observations that is needed for the
        p value to lie outside the uncertainty range.

        It uses the simple observation that the graph of the p value plotted against
        the size of the sets has a exponential, logarithmic or root shape.

        :warning: Doesn't work well.

        :param data1: list of observations
        :param data2: list of observations
        :param run_bin_size: granularity of the observation (> 0)
        :param min_runs: minimum number of allowed runs
        :param max_runs: maximum number of allowed runs
        :return: approximation of needed runs or float("inf")
        """
        #print("###", max_runs)
        if data1 == data2:
            #logging.error("equal")
            return min_runs
        min_len = min(len(data1), len(data2))
        #print("##", max_runs)
        if min_len <= 5:
            return max_runs
        x_space = np.linspace(0, min_len - 2, min_len - 2)
        yn = [self.test(data1[0:i], data2[0:i]) for i in range(2, min_len)]

        def interpolate(func, name: str):
            try:
                popt, pcov = opti.curve_fit(func, x_space, yn, maxfev=10000)
                for i in range(min_len, max_runs + 1, run_bin_size):
                    ith = func(i, *popt)
                    if ith > max(self.uncertainty_range) or ith < min(self.uncertainty_range):
                        #print("i = ", i)
                        return i
                return max_runs
            except (TypeError, RuntimeWarning, RuntimeError) as err:
                logging.info("Interpolating {} with {} data points gave "
                              "following error: {}".format(name, min_len, str(err)))
                return float("inf")

        funcs = [
            (lambda x, a, b, c: a * np.exp(-b * x) + c, "exponential function")
        ]
        res = 0
        with warnings.catch_warnings(record=True) as w:
            res = min(interpolate(*f) for f in funcs)
        return res

    def __eq__(self, other) -> bool:
        return isinstance(other, type(self))


@register(TesterRegistry, name="t", misc_type=Dict())
class TTester(Tester):
    """
    Tester that uses the student's t test.
    """

    scipy_stat_method = "ttest_ind"
    name = "t"


@register(TesterRegistry, name="ks", misc_type=Dict())
class KSTester(Tester):
    """
    Tester that uses the Kolmogorov-Smirnov statistic on 2 samples.
    """

    scipy_stat_method = "ks_2samp"
    name = "kolmogorov smirnov"


@register(TesterRegistry, name="anderson", misc_type=Dict())
class AndersonTester(Tester):
    """
    Tester that uses the Anderson statistic on 2 samples.
    """

    scipy_stat_method = "anderson_ksamp"
    name = "anderson"

    def _test_impl(self, data1: t.List[Number], data2: t.List[Number]) -> float:
        return max(st.anderson_ksamp([data1, data2])[-1], 1)
