"""
Statistical helper classes for tested pairs and single blocks.
"""
import copy
import functools
import logging
from enum import Enum

import itertools

import path

from temci.tester.rundata import RunData
from temci.tester.testers import Tester, TesterRegistry
from temci.utils.settings import Settings
import typing as t
import numpy as np
import scipy as sp
import scipy.stats as st
from temci.utils.typecheck import *
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib
from matplotlib2tikz import save as tikz_save
import seaborn as sns


class StatMessageType(Enum):

    ERROR = 10
    WARNING = 5


class StatMessage:
    """
    A statistical message that gives a hint to
    """

    message = "{props}: {b_val}"
    hint = ""
    type = None # type: StatMessageType
    border_value = 0

    def __init__(self, parent, properties: t.Union[t.List[str], str], values):
        self.parent = parent
        if not isinstance(properties, list):
            properties = [properties]
        if not isinstance(values, list):
            values = [values]
        typecheck(properties, List() // (lambda x: len(x) > 0))
        typecheck(values, List() // (lambda x: len(x) == len(properties)))
        self.properties = sorted(properties)
        self.values = values

    def __add__(self, other: 'StatMessage') -> 'StatMessage':
        typecheck(other, T(type(self)))
        typecheck(other.parent, E(self.parent))
        return StatMessage(self.parent, self.properties + other.properties, self.values + other.values)

    @classmethod
    def combine(cls, *messages: t.List['StatMessage', None]) -> t.List['StatMessage']:
        """
        Combines all message of the same type and with the same parent in the passed list.
        Ignores None entries.
        :param messages: passed list of messages
        :return: new reduced list
        """
        bins = {}
        for msg in messages:
            if msg is None:
                continue
            if msg.parent not in bins:
                bins[msg.parent][type(msg)] = msg
            elif type(msg) not in bins[msg.parent]:
                bins[msg.parent][type(msg)] = msg
            else:
                bins[msg.parent][type(msg)] += msg
        return [x for l in bins.values() for x in l]

    @classmethod
    def _val_to_str(cls, value) -> str:
        return "({!r))".format(value)

    @classmethod
    def check_value(cls, value) -> bool:
        """
        If this fails with the passed value, than the warning is appropriate.
        """
        pass

    @classmethod
    def create_if_valid(cls, value, parent, properties = None, **kwargs) -> t.Union['StatMessage', None]:
        if cls.check_value(value):
            return None
        if properties is not None:
            return cls(parent, properties, value, **kwargs)
        kwargs["values"] = value
        return cls(parent, **kwargs)

    def generate_msg_text(self, show_parent: bool) -> str:
        """
        Generates the text of this message object.
        :param show_parent: Is the parent shown in after the properties? E.g. "blub of bla parent: …"
        :return: message text
        """
        val_strs = map(self._val_to_str, self.properties)
        prop_strs = ["{} {}".format(prop, val) for (prop, val) in zip(self.properties, val_strs)]
        props = " and ".join([", ".join(prop_strs[0:-1]), prop_strs[-1]])
        if show_parent:
            props += " of {}".format(self.parent)
        return self.message.format(b_val=self.border_value, **locals())


class StatWarning(StatMessage):

    type = StatMessageType.WARNING


class StatError(StatMessage):

    type = StatMessageType.ERROR


class StdDeviationToHighWarning(StatWarning):

    message = "The standard deviation of {{props}} is to high it should be <= {b_val:%}."
    border_value = 0.01

    @classmethod
    def check_value(cls, value) -> bool:
        return value <= cls.border_value


class StdDeviationToHighError(StdDeviationToHighWarning, StatError):

    border_value = 0.5


class NotEnoughObservationsWarning(StatWarning):

    message = "The number of observations of {{props}} is less than {b_val:%}."
    border_value = 30

    @classmethod
    def check_value(cls, value) -> bool:
        return value >= cls.border_value


class NotEnoughObservationsError(StdDeviationToHighWarning, StatError):

    border_value = 15


def cached(func, _incr = [0]):
    """
    Caches the results of the passed function.
    :param func: function without any parameters other than self, that returns numeric value.
    :return: wrapped function
    """
    _incr[0] += 1
    prop_name = "___{}".format(_incr[0])

    def ret_func(self):
        if not hasattr(self, prop_name):
            setattr(self, prop_name, func(self))
        return getattr(self, prop_name)
    return functools.update_wrapper(ret_func, func)


class BaseStatObject:
    """
    Class that gives helper methods for the extending stat object classes.
    """

    _filename_counter = 0

    @cached
    def get_stat_messages(self) -> t.List[StatMessage]:
        raise NotImplementedError()

    @cached
    def warnings(self) -> t.List[StatMessage]:
        return [x for x in self.get_stat_messages() if x.type is StatMessageType.WARNING]

    @cached
    def errors(self) -> t.List[StatMessage]:
        return [x for x in self.get_stat_messages() if x.type is StatMessageType.ERROR]

    def get_data_frame(self, **kwargs) -> pd.DataFrame:
        """
        Get the data frame that is associated with this stat object.
        """
        raise NotImplementedError()

    def _height_for_width(self, width: float) -> float:
        golden_mean = (np.sqrt(5) - 1.0) / 2.0    # Aesthetic ratio
        return width * golden_mean

    def _latexify(self, fig_width: float, fig_height: float = None):
        """Set up matplotlib's RC params for LaTeX plotting.
        Call this before plotting a figure.

        Adapted from http://nipunbatra.github.io/2014/08/latexify/

        Parameters
        ----------
        fig_width : float, optional, inches
        fig_height : float,  optional, inches
        """

        # code adapted from http://www.scipy.org/Cookbook/Matplotlib/LaTeX_Examples

        #MAX_HEIGHT_INCHES = 8.0
        #if fig_height > MAX_HEIGHT_INCHES:
        #    print("WARNING: fig_height too large:" + fig_height +
        #          "so will reduce to" + MAX_HEIGHT_INCHES + "inches.")
        #    fig_height = MAX_HEIGHT_INCHES

        params = {'backend': 'ps',
                  'text.latex.preamble': ['\\usepackage{gensymb}'],
                  'axes.labelsize': 8, # fontsize for x and y labels (was 10)
                  'axes.titlesize': 8,
                  'text.fontsize': 8, # was 10
                  'legend.fontsize': 8, # was 10
                  'xtick.labelsize': 8,
                  'ytick.labelsize': 8,
                  'text.usetex': True,
                  'figure.figsize': list(self._fig_size_cm_to_inch(fig_width,fig_height)),
                  'font.family': 'serif'
        }

        matplotlib.rcParams.update(params)

    def _format_axes(self, ax):
        """
        Adapted from http://nipunbatra.github.io/2014/08/latexify/
        """
        SPINE_COLOR = 'gray'
        for spine in ['top', 'right']:
            ax.spines[spine].set_visible(False)

        for spine in ['left', 'bottom']:
            ax.spines[spine].set_color(SPINE_COLOR)
            ax.spines[spine].set_linewidth(0.5)

        ax.xaxis.set_ticks_position('bottom')
        ax.yaxis.set_ticks_position('left')

        for axis in [ax.xaxis, ax.yaxis]:
            axis.set_tick_params(direction='out', color=SPINE_COLOR)

        return ax

    def _get_new_file_name(self, dir: str) -> str:
        self._filename_counter += 1
        return path.join(path.abspath(dir), str(self._filename_counter))

    def _fig_size_cm_to_inch(self, fig_width: float, fig_height: float) -> t.Tuple[float, float]:
        return fig_width * 0.39370079, fig_height * 0.39370079

    def store_figure(self, dir: str, fig_width: float, fig_height: float = None,
                     pdf: bool = True, tex: bool = True, img: bool = True) -> t.Dict[str, str]:
        """
        Stores the current figure in different formats and returns a dict, that maps
        each used format (pdf, tex or img) to the resulting files name.
        :param dir: base directory that the files are placed into
        :param fig_width: width of the resulting figure (in cm)
        :param fig_height: height of the resulting figure (in cm) or calculated via the golden ratio from fig_width
        :param pdf: store as pdf optimized for publishing
        :param tex: store as tex with pgfplots
        :param img: store as png image
        :return: dictionary mapping each used format to the resulting files name
        """
        if fig_height is None:
            fig_height = self._height_for_width(fig_width)
        filename = self._get_new_file_name(dir)
        ret_dict = {}
        if img:
            ret_dict["img"] = self._store_as_image(filename, fig_width, fig_height)
        if tex:
            ret_dict["tex"] = self._store_as_latex(filename, fig_width, fig_height)
        if pdf:
            ret_dict["pdf"] = self._store_as_pdf(filename, fig_width, fig_height)
        return ret_dict

    def _store_as_pdf(self, filename: str, fig_width: float, fig_height: float) -> str:
        """
        Stores the current figure in a pdf file.
        :warning modifies the current figure
        """
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        rc = copy.deepcopy(matplotlib.rcParams)
        self._latexify(fig_width, fig_height)
        plt.tight_layout()
        self._format_axes(plt.gca())
        plt.savefig(filename)
        matplotlib.rcParams = rc
        return filename

    def _store_as_latex(self, filename: str, fig_width: float, fig_height: float) -> str:
        """
        Stores the current figure as latex in a tex file. Needs pgfplots in latex.
        :see https://github.com/nschloe/matplotlib2tikz
        """
        if not filename.endswith(".tex"):
            filename += ".tex"
        tikz_save(filename, figurewidth="{}cm".format(fig_width), figureheight="{}cm".format(fig_height))
        return filename

    def _store_as_image(self, filename: str, fig_width: float, fig_height: float) -> str:
        """
        Stores the current figure as an png image.
        """
        if not filename.endswith(".png"):
            filename += ".png"
        rc = copy.deepcopy(matplotlib.rcParams)
        matplotlib.rcParams.update['figure.figsize'] = list(self._fig_size_cm_to_inch(fig_width,fig_height))
        plt.savefig(filename)
        matplotlib.rcParams = rc
        return filename

    def _freedman_diaconis_bins(*arrays: t.List[np.array]) -> int:
        """
        Calculate number of hist bins using Freedman-Diaconis rule.
        If more than one array is passed, the maximum number of bins calculated for each
        array is used.
        Adapted from seaborns source code
        """
        # From http://stats.stackexchange.com/questions/798/
        def freedman_diaconis(array: np.array):
            h = 2 * sns.utils.iqr(array) / (len(array) ** (1 / 3))
            # fall back to sqrt(a) bins if iqr is 0
            if h == 0:
                return int(np.sqrt(len(array)))
            else:
                return int(np.ceil((max(array) - min(array)) / h))
        return max(map(freedman_diaconis, arrays))

    @cached
    def is_single_valued(self) -> bool:
        """
        Does the data consist only of one unique value?
        """
        raise NotImplementedError()

    def histogram(self, x_ticks: list = None, y_ticks: list = None,
                  show_legend: bool = None, type: str = None,
                  align: str = 'mid', x_label: str = None,
                  y_label: str = None, **kwargs):
        """
        Plots a histogram as the current figure.
        Don't forget to close it via fig.close()
        :param x_ticks: None: use default ticks, list: use the given ticks
        :param y_ticks: None: use default ticks, list: use the given ticks
        :param show_legend: show a legend in the plot? If None only show one if there are more than one sub histograms
        :param type: histogram type (either 'bar', 'barstacked', 'step', 'stepfilled' or None for auto)
        :param align: controls where each bar centered ('left', 'mid' or 'right')
        :param x_label: if not None, shows the given x label
        :param y_lable: if not None: shows the given y label
        :param kwargs: optional arguments passed to the get_data_frame method
        """
        plt.figure()
        if self.is_single_valued():
            logging.error("Can't plot histogram for {} as it's only single valued.".format(self))
            return
        df = self.get_data_frame(**kwargs)
        df_t = df.T
        min_xval = min(map(min, df_t.values))
        max_xval = max(map(max, df_t.values))
        plt.xlim(min_xval, max_xval)
        if type is None:
            type = 'bar' if len(df_t) == 1 else 'step'
        bins = np.linspace(min_xval, max_xval, self._freedman_diaconis_bins(*df_t.values))
        plt.hist(df_t.values, bins=self._freedman_diaconis_bins(*df_t.values),
                 range=(min_xval, max_xval), type=type, align=align,
                 labels=list(df.keys()))
        if x_ticks is not None:
            plt.xticks(x_ticks)
        if y_ticks is not None:
            plt.yticks(y_ticks)
        if show_legend or (show_legend is None and len(df_t) > 1):
            plt.legend()
        if len(df_t) == 1:
            plt.xlabel(df.keys()[0])
        if x_label is not None:
            plt.xlabel(x_label)
        if y_label is not None:
            plt.xlabel(y_label)


class Single(BaseStatObject):
    """
    A statistical wrapper around a single run data object.
    """

    def __init__(self, data: t.Union[RunData, 'Single']):
        self.data = data if isinstance(data, RunData) else data.data
        self.properties = {} # type: t.Dict[str, SingleProperty]
        """ SingleProperty objects for each property """
        for prop in data.properties:
            self.properties[prop] = SingleProperty(data[prop], prop)

    @cached
    def get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited SingleProperty objects (for each property),
        :return: simplified list of all messages
        """
        msgs = [x for prop in self.properties for x in self.properties[prop].get_stat_messages()]
        return StatMessage.combine(*msgs)

    def get_data_frame(self) -> pd.DataFrame:
        series_dict = {}
        for prop in self.properties:
            series_dict[prop] = pd.Series(self.properties[prop].data, name=prop)
        frame = pd.DataFrame(series_dict, columns=sorted(self.properties.keys()))
        return frame


class SingleProperty(BaseStatObject):
    """
    A statistical wrapper around a single run data block for a specific measured property.
    """

    def __init__(self, data: t.Union[RunData, 'SingleProperty'], property: str):
        self.data = data[property] if isinstance(data, RunData) else data.data[property]
        self.array = np.array(self.data)
        self.property = property

    @cached
    def get_stat_messages(self) -> t.List[StatMessage]:
        return StatMessage.combine(
            StdDeviationToHighWarning.create_if_valid(self, self.std_dev_per_mean(), self.property),
            StdDeviationToHighError.create_if_valid(self, self.std_dev_per_mean(), self.property),
            NotEnoughObservationsWarning.create_if_valid(self, self.observations(), self.property),
            NotEnoughObservationsError.create_if_valid(self, self.observations(), self.property)
        )

    @cached
    def mean(self) -> float:
        return np.mean(self.array)

    @cached
    def median(self) -> float:
        return np.median(self.array)

    @cached
    def min(self) -> float:
        return np.min(self.array)

    @cached
    def max(self) -> float:
        return np.max(self.array)

    @cached
    def std_dev(self) -> float:
        """
        Returns the standard deviation.
        """
        return np.std(self.array)

    @cached
    def std_devs(self) -> t.Tuple[float, float]:
        """
        Calculates the standard deviation of elements <= mean and of the elements > mean.
        :return: (lower, upper)
        """
        mean = self.mean()

        def std_dev(elements: list) -> float:
            return np.sqrt(sum(np.power(x - mean, 2) for x in elements) / (len(elements) - 1))

        lower = [x for x in self.array if x <= mean]
        upper = [x for x in self.array if x > mean]
        return std_dev(lower), std_dev(upper)

    @cached
    def std_dev_per_mean(self) -> float:
        return self.std_dev() / self.mean()

    @cached
    def variance(self) -> float:
        return np.var(self.array)

    @cached
    def observations(self) -> int:
        return len(self.data)

    @cached
    def __len__(self) -> int:
        return len(self.data)

    @cached
    def sem(self) -> float:
        """
        Returns the standard error of the mean (standard deviation / sqrt(observations)).
        """
        return st.sem(self.array)

    @cached
    def std_error_mean(self) -> float:
        return st.sem(self.array)

    def mean_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the population mean lies with the given probability.
        Assumes normal distribution.
        :param alpha: given probability
        :return: lower, upper bound
        :see http://stackoverflow.com/a/15034143
        """
        h = self.std_error_mean() * st.t._ppf((1+alpha)/2.0, self.observations() - 1)
        return self.mean() - h, self.mean() + h

    def std_dev_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the standard deviation lies with the given probability.
        Assumes normal distribution.
        :param alpha: given probability
        :return: lower, upper bound
        :see http://www.stat.purdue.edu/~tlzhang/stat511/chapter7_4.pdf
        """
        var = self.variance() * (self.observations() - 1)
        upper = np.sqrt(var / st.t._ppf(alpha/2.0, self.observations() - 1))
        lower = np.sqrt(var / st.t._ppf(1-alpha/2.0, self.observations() - 1))
        return lower, upper

    @cached
    def is_single_valued(self) -> bool:
        """
        Does the data consist only of one unique value?
        """
        return len(set(self.data)) == 1

    @cached
    def __str__(self) -> str:
        return self.data.description()

    @cached
    def get_data_frame(self) -> pd.DataFrame:
        series_dict = {self.property: pd.Series(self.data, name=self.property)}
        frame = pd.DataFrame(series_dict, columns=[self.property])
        return frame


class TestedPair(BaseStatObject):
    """
    A statistical wrapper around two run data objects that are compared via a tester.
    """

    def __init__(self, first: t.Union[RunData, Single], second: t.Union[RunData, Single], tester: Tester = None):
        self.first = Single(first)
        self.second = Single(second)
        self.tester = tester or TesterRegistry.get_for_name(TesterRegistry.get_used(),
                                                            Settings()["stats/tester"],
                                                            Settings()["stats/uncertainty_range"])
        self.properties = {} # type: t.Dict[str, TestedPairProperty]
        """ TestedPairProperty objects for each shared property of the inherited Single objects """
        for prop in set(self.first.properties.keys()).intersection(self.second.properties.keys()):
            self.properties[prop] = TestedPairProperty(first, second, prop, tester)

    @cached
    def get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited TestedPairProperty objects (for each property),
        :return: simplified list of all messages
        """
        msgs = [x for prop in self.properties for x in self.properties[prop].get_stat_messages()]
        return StatMessage.combine(*msgs)

    def rel_difference(self) -> float:
        """
        Calculates the geometric mean of the relative mean differences (first - second) / first.
        :see http://www.cse.unsw.edu.au/~cs9242/15/papers/Fleming_Wallace_86.pdf
        """
        return np.power(sum(x.mean_diff_per_mean() for x in self.properties.values()), 1 / len(self.properties))


class EffectToSmallWarning(StatWarning):

    message = "The mean difference per standard deviation of {{props}} is less than {b_val:%}."
    border_value = 2

    @classmethod
    def check_value(cls, value) -> bool:
        return value >= cls.border_value


class EffectToSmallError(StdDeviationToHighWarning, StatError):

    border_value = 1


class TestedPairProperty(BaseStatObject):
    """
    Statistic helper for a compared pair of run data blocks for a specific measured property.
    """

    def __init__(self, first: t.Union[RunData, SingleProperty],
                 second: t.Union[RunData, SingleProperty], property: str, tester: Tester = None):
        self.first = SingleProperty(first, property)
        self.second = SingleProperty(second, property)
        self.tester = tester or TesterRegistry.get_for_name(TesterRegistry.get_used(),
                                                            Settings()["stats/tester"],
                                                            Settings()["stats/uncertainty_range"])
        self.property = property

    @cached
    def get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited TestedPairProperty objects (for each property),
        :return: simplified list of all messages
        """
        msgs = self.first.get_stat_messages() + self.second.get_stat_messages()
        msgs += [
            EffectToSmallWarning.create_if_valid(self, self.mean_diff_per_dev(), self.property),
            EffectToSmallError.create_if_valid(self, self.mean_diff_per_dev(), self.property)
        ]
        return StatMessage.combine(*msgs)

    @cached
    def mean_diff(self) -> float:
        return self.first.mean() - self.second.mean()

    def mean_diff_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the mean difference lies with the given probability.
        Assumes normal distribution.
        :param alpha: given probability
        :return: lower, upper bound
        :see http://www.kean.edu/~fosborne/bstat/06b2means.html
        """
        d = self.mean_diff()
        t =  st.t.ppf(1-alpha/2.0) * np.sqrt(self.first.variance() / self.first.observations() -
                                             self.second.variance() / self.second.observations())
        return d - t, d + t

    @cached
    def mean_diff_per_mean(self) -> float:
        """
        :return: (mean(A) - mean(B)) / mean(A)
        """
        return self.mean_diff() / self.first.mean()

    @cached
    def mean_diff_per_dev(self) -> float:
        """
        Calculates the mean difference per standard deviation (maximum of first and second).
        """
        return self.mean_diff() / self.max_std_dev()

    @cached
    def equal_prob(self) -> float:
        """
        Probability of the nullhypothesis being not not correct (three way logic!!!).
        :return: p value between 0 and 1
        """
        return self.tester.test(self.first.data, self.second.data)

    @cached
    def is_equal(self) -> t.Union[None, bool]:
        """
        Checks the nullhypthosesis.
        :return: True or False if the p val isn't in the uncertainty range of the tester, None else
        """
        if self.tester.is_uncertain(self.first.data, self.second.data):
            return None
        return self.tester.is_equal(self.first.data, self.second.data)

    @cached
    def mean_std_dev(self) -> float:
        return (self.first.mean() + self.second.mean()) / 2

    @cached
    def max_std_dev(self) -> float:
        return max(self.first.mean(), self.second.mean())

    def get_data_frame(self, show_property = True) -> pd.DataFrame:
        columns = []
        if show_property:
            columns = ["{}: {}".format(self.first, self.property),
                             "{}: {}".format(self.second, self.property)]
        else:
            columns = [str(self.first), str(self.second)]
        series_dict = {
            columns[0]: pd.Series(self.first.data, name=columns[0]),
            columns[1]: pd.Series(self.first.data, name=columns[1])
        }
        frame = pd.DataFrame(series_dict, columns=columns)
        return frame

    @cached
    def is_single_valued(self) -> bool:
        return self.first.is_single_valued() and self.second.is_single_valued()