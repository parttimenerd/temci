"""
Contains the tester base class and several simple implementations.
"""

import temci.utils.util as util
import temci.utils.util as util
if util.can_import("scipy"):
    import scipy as np
    import scipy.stats as st
    import scipy.optimize as opti
from temci.utils.typecheck import *
from temci.utils.registry import AbstractRegistry, register
import logging, warnings


class TesterRegistry(AbstractRegistry):

    settings_key_path = "stats"
    use_key = "tester"
    use_list = False
    default = "t"
    registry = {}


class Tester(object, metaclass=util.Singleton):
    """
    A tester tests the probability of the nullhypothesis of two same length list of observations.

    This is a base class that shouldn't be instantiated.
    """

    scipy_stat_method = ""
    name = ""

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
        """
        res = 0
        min_len = min(len(data1), len(data2))
        with warnings.catch_warnings(record=True) as w:
            res = self._test_impl(data1[0:min_len], data2[0: min_len])
        return res

    def _test_impl(self, data1: list, data2: list) -> float:
        return getattr(st, self.scipy_stat_method)(data1, data2)[-1]

    def is_uncertain(self, data1: list, data2: list) -> bool:
        return min(len(data1), len(data2)) == 0 or \
               self.uncertainty_range[0] <= self.test(data1, data2) <= self.uncertainty_range[1]

    def is_equal(self, data1: list, data2: list):
        return self.test(data1, data2) > max(*self.uncertainty_range)

    def is_unequal(self, data1: list, data2: list):
        return self.test(data1, data2) < min(*self.uncertainty_range)

    def estimate_needed_runs(self, data1: list, data2: list,
                             run_bin_size: int, min_runs: int,
                             max_runs: int) -> int:
        """
        Calculate a approximation of the needed length of both observations that is needed for the
        p value to lie outside the uncertainty range.

        It uses the simple observation that the graph of the p value plotted against
        the size of the sets has a exponential, logarithmic or root shape.

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

    def __eq__(self, other):
        return isinstance(other, type(self))


@register(TesterRegistry, name="t", misc_type=Dict())
class TTester(Tester):
    """
    Implementation of the Tester base class for the student's t test.
    """

    scipy_stat_method = "ttest_ind"
    name = "t"


@register(TesterRegistry, name="ks", misc_type=Dict())
class KSTester(Tester):
    """
    Uses the Kolmogorov-Smirnov statistic on 2 samples.
    """

    scipy_stat_method = "ks_2samp"
    name = "kolmogorov smirnov"


@register(TesterRegistry, name="anderson", misc_type=Dict())
class AndersonTester(Tester):
    """
    Uses the Anderson statistic on 2 samples.
    """

    scipy_stat_method = "anderson_ksamp"

    def _test_impl(self, data1: list, data2: list) -> float:
        return max(st.anderson_ksamp([data1, data2])[-1], 1)

    name = "anderson"