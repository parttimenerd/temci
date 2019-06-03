"""
Statistical helper classes for tested pairs and single blocks.
"""

import logging
import os
from collections import defaultdict
from enum import Enum

import itertools

import math
from temci.report.rundata import RunData
from temci.report.testers import Tester, TesterRegistry
from temci.utils.settings import Settings
import typing as t
import temci.utils.util as util
from temci.utils.sudo_utils import chown

if util.can_import("scipy"):
    import numpy as np
    import scipy as sp
    import scipy.stats as st
    import pandas as pd
    import matplotlib as mpl
    mpl.use("agg")
from temci.utils.typecheck import *


Number = t.Union[float, int]
""" Numeric value type """


class StatMessageType(Enum):
    """
    Types of StatMessages.
    """
    ERROR = 10
    """ Error type that signals a possible error or mistake """
    WARNING = 5
    """ Warning type that signals a possible but not servere mistake """


class StatMessageValueFormat:
    """
    Format strings for ints, floats and percentage values used in the StatMessages.
    """

    INT = "{}"  # type: str
    """ Format string for int values """
    FLOAT = "{:5.3f}"  # type: str
    """ Format string for float values that aren't shown as percentages """
    PERCENT = "{:5.3%}"  # type: str
    """ Format string for float values that are shown as percentages """


class StatMessage:
    """
    A message that warns of possible mistakes and gives hints.
    It's related to a statistical property.
    """

    message = "{props}: {b_val}"  # type: str
    """
    Format string for the message, ``{b_val}`` is replaced by the border value
    and ``{props}`` by the list of properties and program block names that
    have this problem.
    """
    hint = ""  # type: str
    """ Text that should give a hint about what to do to prevent the possible mistake """
    type = None  # type: StatMessageType
    """ Type of this StatMessage, warning or error """
    border_value = 0  # type: Number
    value_format = StatMessageValueFormat.FLOAT  # type: str
    """ Format string used to format the border and the actual value """

    def __init__(self, parent: 'BaseStatObject', properties: t.Union[t.List[str], str],
                 values: t.Union[t.List[Number], Number]):
        """
        Create a new instance.

        :param parent: parent stat object
        :param properties: properties of the stat object for which this message is relevant
        :param values: a value of the related statistical property for each relevant property
        """
        self.parent = parent  # type: BaseStatObject
        """ Parent stat object """
        if not isinstance(properties, list):
            properties = [properties]
        if not isinstance(values, list):
            values = [values]
        typecheck(properties, List() // (lambda x: len(x) > 0))
        typecheck(values, List() // (lambda x: len(x) == len(properties)))
        self.properties = sorted(properties)  # type: t.List[str]
        """ Properties of the stat object for which this message is relevant """
        self.values = values  # type: t.List[Number]
        """ a value of the related statistical property for each relevant property """

    def __add__(self, other: 'StatMessage') -> 'StatMessage':
        typecheck(other, T(type(self)))
        assert self.parent.eq_except_property(other.parent)
        return type(self)(self.parent, self.properties + other.properties, self.values + other.values)

    @staticmethod
    def combine(*messages: t.Tuple[t.Optional['StatMessage']]) -> t.List['StatMessage']:
        """
        Combines all message of the same type and with the same parent in the passed list.
        Ignores None entries.

        :param messages: passed list of messages
        :return: new reduced list
        """
        msgs = set([msg for msg in messages if msg is not None]) # t.Set['StatMessage']
        something_changed = True
        while something_changed:
            something_changed = False
            merged_pair = None # type: t.Tuple['StatMessage', 'StatMessage']
            for (msg, msg2) in itertools.product(msgs, msgs):
                if msg is not msg2:
                    if msg.parent.eq_except_property(msg2.parent) and type(msg) == type(msg2):
                        merged_pair = (msg, msg2)
                        something_changed = True
                        break
            if something_changed:
                msg, msg2 = merged_pair
                msgs.remove(msg)
                msgs.remove(msg2)
                msgs.add(msg + msg2)
        return list(msgs)

    @classmethod
    def _val_to_str(cls, value: Number) -> str:
        """ Formats the passed value """
        format = cls.value_format if isinstance(cls.value_format, str) else cls.value_format.value
        return format.format(value)

    @classmethod
    def check_value(cls, value: Number) -> bool:
        """ Is this type of message inappropriate for the passed value of the related statistical property? """
        raise NotImplementedError()

    @classmethod
    def create_if_valid(cls, parent: 'BaseStatObject', property: str, value: Number, **kwargs) \
            -> t.Optional['StatMessage']:
        """
        Returns a message object if this type of message is appropriate for the passed value of the related statistical
        property or None otherwise.

        :param parent: parent stat object
        :param property: property of the stat object for which this message is might by relevant and the value is given
        :param value: a value of the related statistical property
        :param kwargs: additional arguments for the constructor of this message type class
        """
        assert isinstance(value, Int()|Float())
        if cls.check_value(value):
            return None
        ret = None
        if property is not None:
            ret = cls(parent, property, value, **kwargs)
        else:
            ret = cls(parent, property, value, **kwargs)
        return ret

    def generate_msg_text(self, show_parent: bool) -> str:
        """
        Generates the text of this message object.

        :param show_parent: Is the parent shown in after the properties? E.g. "blub of bla parent: …"
        :return: message text
        """
        val_strs = list(map(self._val_to_str, self.values))
        prop_strs = ["{} ({})".format(prop, val) for (prop, val) in zip(self.properties, val_strs)]
        props = util.join_strs(prop_strs)
        if show_parent:
            props += " of {}".format(self.parent.description())
        return self.message.format(b_val=self._val_to_str(self.border_value), props=props)


class StatWarning(StatMessage):
    """ A message that signals a possible warning that isn't severe """

    type = StatMessageType.WARNING


class StatError(StatWarning, StatMessage):
    """ A message that signals a possible warning that is probably severe """

    type = StatMessageType.ERROR


class StdDeviationToHighWarning(StatWarning):
    """ A warning about a too high standard deviation. """

    message = "The standard deviation per mean of {props} is too high it should be <= {b_val}."
    hint = "With the exec run driver you can probably use the stop_start plugin, preheat and sleep plugins. " \
           "Also consider to increase the number of measured runs."
    border_value = 0.01
    value_format = StatMessageValueFormat.PERCENT

    @classmethod
    def check_value(cls, value) -> bool:
        return value <= cls.border_value


class StdDeviationToHighError(StdDeviationToHighWarning):
    """ Error message regarding a far too high standard deviation. """

    type = StatMessageType.ERROR
    border_value = 0.05


class NotEnoughObservationsWarning(StatWarning):
    """ Warning regarding too few observations or measurements. """

    message = "The number of observations of {props} is less than {b_val}."
    hint = "Increase the number of measured runs."
    border_value = 30
    value_format = StatMessageValueFormat.INT

    @classmethod
    def check_value(cls, value) -> bool:
        return value >= cls.border_value


class NotEnoughObservationsError(NotEnoughObservationsWarning):
    """ Error message regarding too few observations or measurements. """

    type = StatMessageType.ERROR
    border_value = 15


class BaseStatObject:
    """
    Class that gives helper methods for the extending stat object classes.
    """

    _filename_counter = 0  # type: int
    """ Counter to produce unique file names """
    img_filename_ending = ".svg"  # type: str
    """ File ending for image file (and therefore their format) """

    def __init__(self):
        self._stat_messages = None  # type: t.Optional[t.List[StatMessage]]
        """ List of statistical warnings an errors. Use ``get_stat_messages`` to access this property properly. """
        self._fig = None  # type: t.Optional[matplotlib.figure.Figure]
        self._hist_data = {}

    def get_stat_messages(self) -> t.List[StatMessage]:
        """ Returns a list of all (merged) statistical warnings and errors for this stat object. """
        if not self._stat_messages:
            self._stat_messages = StatMessage.combine(*self._get_stat_messages())
        return self._stat_messages

    def _get_stat_messages(self) -> t.List[StatMessage]:
        """
        Returns a list of all (not merged) statistical warnings and errors for this stat object.

        Implemented by sub classes of BaseStatObject.
        """
        raise NotImplementedError()

    def warnings(self) -> t.List[StatMessage]:
        """ Returns a list of all (merged) statistical warnings for this stat object. """
        return [x for x in self.get_stat_messages() if x.type is StatMessageType.WARNING]

    def errors(self) -> t.List[StatMessage]:
        """ Returns a list of all (merged) statistical errors for this stat object. """
        return [x for x in self.get_stat_messages() if x.type is StatMessageType.ERROR]

    def has_errors(self) -> bool:
        """ Does this stat object has any statistical errors? """
        return any([x.type == StatMessageType.ERROR for x in self.get_stat_messages()])

    def has_warnings(self) -> bool:
        """ Does this stat object has any statistical errors? """
        return any([x.type == StatMessageType.WARNING for x in self.get_stat_messages()])

    def get_data_frame(self, **kwargs):
        """
        Get the data frame that is associated with this stat object.

        Implemented by sub classes of BaseStatObject.
        :return pd.DataFrame instance
        """
        raise NotImplementedError()

    def eq_except_property(self, other) -> bool:
        """
        Is this stat object equal to the passed stat object (without regarding the actual property)?

        Implemented by sub classes of BaseStatObject.
        """
        raise NotImplementedError()

    def _height_for_width(self, width: float) -> float:
        """ Calculates a possible height for an image with the given width using the aesthetic ratio. """
        golden_mean = (np.sqrt(5) - 1.0) / 2.0    # Aesthetic ratio
        return width * golden_mean

    def _latexify(self, fig_width: float, fig_height: float = None):
        """
        Set up matplotlib's RC params for LaTeX plotting.
        Call this before plotting a figure.

        Adapted from http://nipunbatra.github.io/2014/08/latexify/

        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        """

        # code adapted from http://www.scipy.org/Cookbook/Matplotlib/LaTeX_Examples

        params = {'backend': 'ps',
                  'text.latex.preamble': ['\\usepackage{gensymb}'],
                  'axes.labelsize': 8, # fontsize for x and y labels (was 10)
                  'axes.titlesize': 8,
                  'font.size': 8, # was 10
                  'legend.fontsize': 8, # was 10
                  'xtick.labelsize': 8,
                  'ytick.labelsize': 8,
                  'text.usetex': True,
                  'figure.figsize': self._fig_size_cm_to_inch(fig_width,fig_height),
                  'font.family': 'serif'
        }
        import matplotlib
        matplotlib.rcParams.update(params)

    def _format_axes(self, ax: 'matplotlib.axis.Axis') -> 'matplotlib.axis.Axis':
        """
        Set up the parameters of the passed matplotlib axis for LaTeX plotting.

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
        """ Returns a new unique file name (without extension) in the given directory. """
        self._filename_counter += 1
        return os.path.join(os.path.abspath(dir), str(self._filename_counter))

    def _fig_size_cm_to_inch(self, fig_width: float, fig_height: float) -> t.Tuple[float, float]:
        """
        Converts the passed cm values into inch values.

        :param fig_width: width of a figure in cm
        :param fig_height: height of a figure in cm
        :return: (fig_width, fig_height) in inches
        """
        return fig_width * 0.39370079, fig_height * 0.39370079

    def store_figure(self, filename: str, fig_width: float, fig_height: float = None,
                     pdf: bool = True, tex: bool = True, tex_standalone: bool = True,
                     img: bool = True) -> t.Dict[str, str]:
        import matplotlib.pyplot as plt
        """
        Stores the current figure in different formats and returns a dict, that maps
        each used format (pdf, tex or img) to the resulting files name.

        :param filename: base filename that is prepended with the appropriate extensions
        :param fig_width: width of the resulting figure (in cm)
        :param fig_height: height of the resulting figure (in cm) or calculated via the golden ratio from fig_width
        :param pdf: store as pdf optimized for publishing
        :param tex: store as tex with pgfplots
        :param img: store as png image
        :return: dictionary mapping each used format to the resulting files name
        """
        if fig_height is None:
            fig_height = self._height_for_width(fig_width)
        #filename = # self._get_new_file_name(dir)
        ret_dict = {}
        if img:
            ret_dict["img"] = self._store_as_image(filename + self.img_filename_ending, fig_width, fig_height)
        if tex:
            ret_dict["tex"] = self._store_as_tex(filename + ".tex", fig_width, fig_height, standalone=False)
        if pdf:
            if util.has_pdflatex():
                ret_dict["pdf"] = self._store_as_pdf(filename + ".pdf", fig_width, fig_height)
            else:
                util.warn_for_pdflatex_non_existence_once()
        if tex_standalone:
            ret_dict["tex_standalone"] = self._store_as_tex(filename + "____standalone.tex", fig_width,
                                                            fig_height, standalone=True)
        if self._fig is not None:
            plt.close('all')
        return ret_dict

    def _store_as_pdf(self, filename: str, fig_width: float, fig_height: float) -> str:
        """
        Stores the current figure in a pdf file.

        :param filename: name of the pdf file
        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        :warning: modifies the current figure
        """
        import matplotlib.pyplot as plt
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        self.reset_plt()
        self._latexify(fig_width, fig_height)
        try:
            plt.tight_layout()
        except ValueError:
            pass
        self._format_axes(plt.gca())
        plt.savefig(filename)
        self.reset_plt()
        return os.path.realpath(filename)

    def _store_as_tex(self, filename: str, fig_width: float, fig_height: float, standalone: bool) -> str:
        """
        Stores the current figure as a latex histrogram plot in a tex file. Needs pgfplots in latex.
        Works independently of matplotlib.

        :param filename: name of the tex file
        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        :param standalone: surround the tex code with an standalone document environment
        """
        if not filename.endswith(".tex"):
            filename += ".tex"
        if "min_xval" not in self._hist_data:
            return
        x_range = (self._hist_data["min_xval"], self._hist_data["max_xval"])
        x_bin_width = (self._hist_data["min_xval"] - self._hist_data["max_xval"]) / self._hist_data["bin_count"]
        plot_tex = ""
        ymax = 0
        for value in self._hist_data["values"]:
            hist, bin_edges = np.histogram(value, bins=self._hist_data["bin_count"],
                                           range=x_range)
            #bin_edges = map(_ + (x_bin_width / 2), bin_edges)
            plot_tex += """
            \\addplot coordinates {{ {} ({}, 0) }};
            """.format(" ".join(map(lambda d: "({}, {})".format(*d), zip(bin_edges, hist))), bin_edges[-1])
            ymax = max(ymax, max(hist))

        tex = """
\\pgfplotsset{{width={width}cm, height={height}cm, compat=1.10}}
\\begin{{tikzpicture}}
    \\begin{{axis}}[
    ymin=0,
    ymax={ymax},
    bar shift=0pt,
    enlarge x limits=0.10,
    cycle list name=auto,
    every axis plot/.append style={{ybar interval, opacity={opacity},fill,draw=none,no markers}},
    ylabel= ,
    xlabel={xlabel}""".format(width=fig_width, height=fig_height, xlabel=self._hist_data["xlabel"],
                              ymax=ymax * 1.2, opacity= 1 if len(self._hist_data["values"]) == 1 else 0.75)
        if self._hist_data["legend"]:
            legend = "\\\\".join(self._hist_data["legend"]) + "\\\\"
            tex += """,
    legend entries={{{}}}""".format(legend)
        tex += """
        ]
        """
        tex += plot_tex
        tex += """
    \end{axis}
\end{tikzpicture}
        """
        if standalone:
            tex = """
\\documentclass[margin=10pt]{standalone}
\\usepackage{pgfplots}
\\begin{document}
                  """ + tex + """
\\end{document}
"""
        with open(filename, "w") as f:
            f.write(tex)
            chown(f)
        return os.path.realpath(filename)

    def _store_as_image(self, filename: str, fig_width: float, fig_height: float) -> str:
        """
        Stores the current figure as an image.

        :param filename: name of the image file that defines the file format of the image with its ending
        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        """
        import matplotlib.pyplot as plt
        if not filename.endswith(self.img_filename_ending):
            filename += self.img_filename_ending
        self.reset_plt()
        plt.savefig(filename)
        self.reset_plt()
        return os.path.realpath(filename)

    def _freedman_diaconis_bins(self, *arrays: t.Tuple[t.List[Number]]) -> int:
        """
        Calculate number of hist bins using Freedman-Diaconis rule.
        If more than one array is passed, the maximum number of bins calculated for each
        array is used.

        Adapted from seaborns source code (adapted originally from http://stats.stackexchange.com/questions/798/).
        """
        import seaborn as sns
        def freedman_diaconis(array: np.array):
            array = [a for a in array if not math.isnan(a)]
            h = 2 * sns.utils.iqr(array) / (len(array) ** (1 / 3))
            # fall back to sqrt(a) bins if iqr is 0
            if h == 0:
                return int(np.sqrt(len(array)))
            else:
                return int(np.ceil((max(array) - min(array)) / h))
        return max(map(freedman_diaconis, arrays))

    
    def is_single_valued(self) -> bool:
        """ Does the data consist only of one unique value? """
        return False

    def histogram(self, fig_width: Number, fig_height: Number = None,
                  x_ticks: t.List[Number] = None, y_ticks: t.List[Number] = None,
                  show_legend: bool = None, type: str = None,
                  align: str = 'mid', x_label: str = None,
                  y_label: str = None, zoom_in: bool = True,
                  other_objs: t.List['BaseStatObject'] = None,
                  other_obj_names: t.List[str] = None,
                  own_name: str = None, **kwargs):
        """
        Plots a histogram as the current figure.
        Don't forget to close it via fig.close()

        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        :param x_ticks: None: use default ticks, list: use the given ticks
        :param y_ticks: None: use default ticks, list: use the given ticks
        :param show_legend: show a legend in the plot? If None only show one if there are more than one sub histograms
        :param type: histogram type (either 'bar', 'barstacked', 'step', 'stepfilled' or None for auto)
        :param align: controls where each bar centered ('left', 'mid' or 'right')
        :param x_label: if not None, shows the given x label
        :param y_label: if not None: shows the given y label
        :param zoom_in: does the x axis start at the minimum x value?
        :param kwargs: optional arguments passed to the get_data_frame method
        :param other_objs: addional objects to plot on the same histogram (only SingleProperty objects allowed)
        :param other_obj_names: names of the additional objects
        :param own_name: used with other_objs option
        """
        self.reset_plt()
        self._hist_data = {}
        import matplotlib.pyplot as plt
        import seaborn as sns
        if fig_height is None:
            fig_height = self._height_for_width(fig_width)
        if self.is_single_valued():
            descr = self.description()
            if isinstance(self, SingleProperty):
                descr += " [" + self.property + "]"
            logging.error("Can't plot histogram for {} as it's only single valued.".format(self))
            return
        df = self.get_data_frame(**kwargs)
        if other_objs:
            typecheck(self, SingleProperty)
            for obj in other_objs:
                if obj.is_single_valued() or not isinstance(obj, SingleProperty):
                    logging.error("Can't additionally plot histogram for {} as it's only single valued.".format(self))
                    return
            series_dict = {}
            for (i, name) in enumerate(other_obj_names):
                series_dict[name] = pd.Series(other_objs[i].data, name=name)
            series_dict[own_name] = self.data
            df = pd.DataFrame(series_dict, columns=sorted(list(series_dict.keys())))
        df_t = df.T
        show_legend = show_legend or (show_legend is None and len(df_t) > 1)
        min_xval = min(map(min, df_t.values)) if zoom_in else 0
        max_xval = max(map(max, df_t.values))
        if type is None:
            type = 'bar' if len(df_t) == 1 else 'stepfilled'
        bin_count = self._freedman_diaconis_bins(*df_t.values)
        bins = np.linspace(min_xval, max_xval, bin_count)
        self.reset_plt()
        ymax = 0
        for value in df_t.values:
            hist, bin_edges = np.histogram(value, bins=bin_count, range=(min_xval, max_xval))
            ymax = max(ymax, max(hist))

        self._fig = plt.figure(figsize=self._fig_size_cm_to_inch(fig_width, fig_height))
        plt.xlim(min_xval, max_xval)
        plt.ylim(0, ymax * (1.2 if show_legend else 1.05))
        plt.hist(df.values, bins=bin_count,
                 range=(min_xval, max_xval), histtype=type, align=align,
                 label=list(reversed(df.keys())), alpha= 0.75 if len(df_t) > 1 else 1)
        #sns.distplot(df, bins=bin_count, color=["red", "blue", "yellow"][0:len(df_t)])
        if x_ticks is not None:
            plt.xticks(x_ticks)
        if y_ticks is not None:
            plt.yticks(y_ticks)
        legend = None
        if show_legend:
            legend = list(df.keys())
            plt.legend(labels=list(reversed(legend)))
        if len(df_t) == 1:
            plt.xlabel(df.keys()[0])
        if x_label is not None:
            plt.xlabel(x_label)
        if y_label is not None:
            plt.xlabel(y_label)
        self._hist_data = {
            "xlabel": x_label or ("" if len(df_t) > 1 else df.keys()[0]),
            "legend": None if legend is None else list(reversed(legend)),
            "min_xval": min_xval,
            "max_xval": max_xval,
            "values": list(reversed(df_t.values)),
            "bin_count": bin_count
        }

    def description(self) -> str:
        """
        Returns the description of this stat object.

        Should be implemented by sub classes of BaseStatObject.
        """
        return str(self)

    def __str__(self) -> str:
        """ Returns the description of this stat object. """
        return self.description()

    def reset_plt(self):
        """ Reset the current matplotlib plot style. """
        import matplotlib.pyplot as plt
        plt.gcf().subplots_adjust(bottom=0.15)
        if Settings()["report/xkcd_like_plots"]:
            import seaborn as sns
            sns.reset_defaults()
            mpl.use("agg")
            plt.xkcd()
        else:
            import seaborn as sns
            sns.reset_defaults()
            sns.set_style("darkgrid")
            sns.set_palette(sns.color_palette("muted"))
            mpl.use("agg")


class Single(BaseStatObject):
    """
    A statistical wrapper around a single run data object.
    """

    def __init__(self, data: t.Union[RunData, 'Single']):
        """
        Create an instance.

        :param data: run data wrapped by this instance or another instance of which the run data is used
        """
        super().__init__()
        self.rundata = None  # type: RunData
        """ Run data wrapped by this instance """
        if isinstance(data, RunData):
            self.rundata = data
        else:
            self.rundata = data.rundata
        self.attributes = self.rundata.attributes  # type: t.Dict[str, str]
        """ Attributes for this instance """
        self.properties = {}  # type: t.Dict[str, SingleProperty]
        """ SingleProperty objects for each property """
        for prop in data.properties:
            self.properties[prop] = SingleProperty(self, self.rundata, prop)

    def _get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited SingleProperty objects (for each property),

        :return: list of all messages
        """
        msgs = [x for prop in self.properties for x in self.properties[prop].get_stat_messages()]
        return msgs

    def get_data_frame(self):
        series_dict = {}
        for prop in self.properties:
            series_dict[prop] = pd.Series(self.properties[prop].data, name=prop)
        frame = pd.DataFrame(series_dict, columns=sorted(self.properties.keys()))
        return frame

    def description(self) -> str:
        return self.rundata.description()

    def eq_except_property(self, other) -> bool:
        return isinstance(other, type(self)) and self.rundata == other.rundata

    def __eq__(self, other):
        return self.eq_except_property(other)

class SingleProperty(BaseStatObject):
    """
    A statistical wrapper around a single run data block for a specific measured property.
    """

    def __init__(self, parent: Single, data: t.Union[RunData, 'SingleProperty'], property: str):
        """
        Creates an instance.

        :param parent: parent single object that contains this instance
        :param data: measured data for all properties or another single property instance of which the data is used
        :param property: actually measured property
        """
        super().__init__()
        self.parent = parent
        """ Parent single object that contains this instance """
        self.rundata = None  # type: RunData
        """ RunData object that contains the measurements for all properties """
        self.data = None  # type: t.List[Number]
        """ Measured data for the specific property """
        if isinstance(data, RunData):
            self.rundata = data
            self.data = data[property]
        else:
            self.rundata = data.rundata # type: RunData
            self.data = data.data
        self.array = np.array(self.data)  # type: np.array
        """
        NumPy array version of the measured data for the specific property. Using this in NumPy contexts might
        speed up the calculations.
        """
        self.property = property  # type: str
        """ Actually measured property """

    def _get_stat_messages(self) -> t.List[StatMessage]:
        msgs = [
            StdDeviationToHighWarning.create_if_valid(self, self.property, self.std_dev_per_mean()),
            StdDeviationToHighError.create_if_valid(self, self.property, self.std_dev_per_mean()),
            NotEnoughObservationsWarning.create_if_valid(self, self.property, self.observations()),
            NotEnoughObservationsError.create_if_valid(self, self.property, self.observations())
        ]
        return msgs

    def mean(self) -> float:
        """ Mean value of the measurements """
        return np.mean(self.array)

    def median(self) -> float:
        """ Median of the measurements """
        return np.median(self.array)

    def min(self) -> float:
        """ Minimum value of the measurements """
        return np.min(self.array)

    def max(self) -> float:
        """ Maximum value of the measurements """
        return np.max(self.array)

    def std_dev(self) -> float:
        """ Standard deviation of the measurements """
        return np.std(self.array)

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

    def std_dev_per_mean(self) -> float:
        """ Standard deviation per mean of the measurements (also known as variation coefficient) """
        return self.std_dev() / self.mean()
    
    def variance(self) -> float:
        """ Variance of the measurements """
        return np.var(self.array)
    
    def observations(self) -> int:
        """ Number of measurements or observations """
        return len(self.data)
    
    def __len__(self) -> int:
        """ Number of measurements """
        return len(self.data)

    def eq_except_property(self, other) -> bool:
        return isinstance(other, SingleProperty) and self.rundata == other.rundata

    def __eq__(self, other):
        return self.eq_except_property(other) and self.property == other.property
    
    def sem(self) -> float:
        """ Standard error of the mean (standard deviation / sqrt(observations)) """
        return st.sem(self.array)
    
    def std_error_mean(self) -> float:
        """ Standard error of the mean (standard deviation / sqrt(observations)) """
        return st.sem(self.array)

    def mean_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the population mean lies with the given probability.
        Assumes normal distribution.

        Adopted from http://stackoverflow.com/a/15034143

        :param alpha: given probability
        :return: lower, upper bound
        """
        h = self.std_error_mean() * st.t._ppf((1+alpha)/2.0, self.observations() - 1)
        return self.mean() - h, self.mean() + h

    def std_dev_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the standard deviation lies with the given probability.
        Assumes normal distribution.

        Adopted from http://www.stat.purdue.edu/~tlzhang/stat511/chapter7_4.pdf

        :param alpha: given probability
        :return: lower, upper bound
        """
        var = self.variance() * (self.observations() - 1)
        upper = np.sqrt(var / st.t._ppf(alpha/2.0, self.observations() - 1))
        lower = np.sqrt(var / st.t._ppf(1-alpha/2.0, self.observations() - 1))
        return lower, upper

    def is_single_valued(self) -> bool:
        """ Does the data consist only of one unique value?  """
        return len(set(self.data)) == 1

    def description(self) -> str:
        return self.rundata.description()

    def get_data_frame(self):
        series_dict = {self.property: pd.Series(self.data, name=self.property)}
        frame = pd.DataFrame(series_dict, columns=[self.property])
        return frame

    def skewedness(self) -> float:
        """
        Calculates the skewedness of the data.

        :warning: return NaN if the number of observations is less than 8
        """
        return sp.stats.skew(self.data, axis=0, bias=True) if len(self.data) >= 8 else float("nan")

    def normality(self) -> float:
        """
        Calculates the probability of the data being normal distributed.

        :warning: return NaN if the number of observations is less than 8
        """
        return sp.stats.normaltest(self.data)[1] if len(self.data) >= 8 else float("nan")

    def percentile(self, q: int) -> float:
        """
        Calculates the q th percentile. q must be between 0 and 100 inclusive.
        """
        return np.percentile(self.data, q)

    def quartiles(self) -> t.Tuple[float, float, float]:
        """
        Calculates the 3 quartiles (1, 2 and 3)
        """
        return self.percentile(25), self.percentile(50), self.percentile(75)

    def iqr(self) -> float:
        """
        Calculates the interquartile range.
        """
        return np.subtract(*np.percentile(self.data, [75, 25]))

    def whiskers(self, whis: float = 1.5) -> t.Tuple[float, float]:
        """
        Calculates the upper and the lower whisker for a boxplot.
        I.e. the minimum and the maximum value of the data set
        the lie in the range (Q1 - whis * IQR, Q3 + whis * IQR).
        IQR being the interquartil distance, Q1 the lower and Q2 the upper quartile.

        Adapted from http://stackoverflow.com/a/20096945
        """
        q1, q2, q3 = self.quartiles()
        iqr = self.iqr()
        hi_val = q1 + whis * self.iqr()
        whisk_hi = np.compress(self.array <= hi_val, self.array)
        if len(whisk_hi) == 0 or np.max(whisk_hi) < q3:
            whisk_hi = q3
        else:
            whisk_hi = max(whisk_hi)

        # get low extreme
        lo_val = q1 - whis * iqr
        whisk_lo = np.compress(self.array >= lo_val, self.array)
        if len(whisk_lo) == 0 or np.min(whisk_lo) > q1:
            whisk_lo = q1
        else:
            whisk_lo = min(whisk_lo)
        return whisk_lo, whisk_hi

    def outliers(self, whis: float = 1.5) -> t.List[float]:
        """
        Returns the values that don't lie in the in the range fenced by the whiskers.
        """
        whiskers = self.whiskers(whis)
        return [x for x in self.data if x < whiskers[0] or x > whiskers[1]]


class TestedPair(BaseStatObject):
    """
    A statistical wrapper around two run data objects that are compared via a tester.
    """

    def __init__(self, first: t.Union[RunData, Single], second: t.Union[RunData, Single], tester: Tester = None):
        """
        Creates an instance.

        :param first: first of the two compared run data or single objects
        :param second: second of the two compared run data or single objects
        :param tester: used statistical tester, if None the default tester is used (configured in the settings)
        """
        super().__init__()
        self.first = Single(first)  # type: Single
        """ First of the two compared single objects """
        self.second = Single(second)  # type: Single
        """ Second of the two compared single objects """
        self.tester = tester or TesterRegistry.get_for_name(TesterRegistry.get_used(),  # type: Tester
                                                            Settings()["stats/tester"],
                                                            Settings()["stats/uncertainty_range"])
        """ Used statistical tester for the comparisons """
        self.properties = {} # type: t.Dict[str, TestedPairProperty]
        """ TestedPairProperty objects for each shared property of the inherited Single objects """
        for prop in set(self.first.properties.keys()).intersection(self.second.properties.keys()):
            self.properties[prop] = TestedPairProperty(self, self.first, self.second, prop, tester)
    
    def _get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited TestedPairProperty objects (for each property),

        :return: simplified list of all messages
        """
        msgs = [x for prop in self.properties for x in self.properties[prop].get_stat_messages()]
        return msgs

    def first_rel_to_second(self) -> float:
        """
        Calculates the geometric mean of the first means relative to the second means.

        See http://www.cse.unsw.edu.au/~cs9242/15/papers/Fleming_Wallace_86.pdf
        """
        return st.gmean([x.first_rel_to_second() for x in self.properties.values()])

    def first_rel_to_second_std(self) -> float:
        """
        Calculates the geometric standard deviation for the first_rel_to_second method.
        """
        return util.geom_std([x.first_rel_to_second() for x in self.properties.values()])

    def swap(self) -> 'TestedPair':
        """
        Creates a new pair with the elements swapped.

        :return: new pair object
        """
        return TestedPair(self.second, self.first, self.tester)

    def __getitem__(self, property: str) -> 'TestedPairProperty':
        return self.properties[property]

    def eq_except_property(self, other) -> bool:
        return isinstance(other, type(self)) and self.first == other.first and self.second == other.second \
               and self.tester == other.tester

    def __eq__(self, other) -> bool:
        return self.eq_except_property(other)

    def description(self) -> str:
        return "{} vs. {}".format(self.first, self.second)


class TestedPairsAndSingles(BaseStatObject):
    """
    A wrapper around a list of tested pairs and singles.
    """

    def __init__(self, singles: t.List[t.Union[RunData, Single]], pairs: t.List[TestedPair] = None):
        """
        Creates an instance.

        :param singles: compared single objects or run data objects that are turned into single object
        :param pairs: compared pairs of single objects, if None they created out of the passed single objects
        """
        super().__init__()
        self.singles = list(map(Single, singles))  # type: t.List[Single]
        """ Compared single objects """
        self._pairs = pairs or []  # type: t.List[TestedPair]
        """ Compared tested pair objects """
        self.singles_properties = {}  # type: t.Dict[str, SinglesProperty]
        """ Singles property object for every measured property """
        for prop in self.properties():
            self.singles_properties[prop] = SinglesProperty(self.singles, prop)

    @property
    def pairs(self) -> t.List[TestedPair]:
        if not hasattr(self, "_pairs") or not self._pairs:
            self._pairs = []
            if len(self.singles) > 1:
                for i in range(0, len(self.singles) - 1):
                    for j in range(i + 1, len(self.singles)):
                        self._pairs.append(self.get_pair(i, j))
        return self._pairs

    def number_of_singles(self) -> int:
        """ Number of compared single objects """
        return len(self.singles)

    def get_pair(self, first_id: int, second_id: int) -> TestedPair:
        """
        Get the tested pair consisting of the two single objects with the passed ids.
        The id of a single objects is its index (starting at zero) in the internal single list.

        :param first_id: id of the first single object
        :param second_id: id of the second single object
        :return: created tested pair object comparing the two single objects
        """
        l = self.number_of_singles()
        assert 0 <= first_id < l and 0 <= second_id < l
        return TestedPair(self.singles[first_id], self.singles[second_id])

    def properties(self) -> t.List[str]:
        """
        Returns the properties that are shared among all single run data objects.
        """
        if not self.singles:
            return []
        props = set(self.singles[0].properties.keys())
        for single in self.singles[1:]:
            props.intersection_update(single.properties.keys())
        return sorted(props)

    def get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited TestedPair and Single objects,

        :return: simplified list of all messages
        """
        msgs = []
        for pair in self.pairs:
            msgs.extend(pair.get_stat_messages())
        return msgs

    def __getitem__(self, id: int) -> Single:
        """
        Get the single object with the given id.

        The id of a single objects is its index (starting at zero) in the internal single list.

        :param id: given id
        """
        assert 0 <= id < self.number_of_singles()
        return self.singles[id]


class EffectToSmallWarning(StatWarning):
    """ Warning regarding a not really significant mean difference regarding the standard deviation. """

    message = "The mean difference per standard deviation of {props} is less than {b_val}."
    hint = "Try to reduce the standard deviation if you think that the measured difference is significant: " \
           "If you use the exec run driver, consider using the stop_start plugin, preheat and sleep plugins. " \
           "Also consider increasing the number of measured runs."
    border_value = 2
    value_format = StatMessageValueFormat.FLOAT

    @classmethod
    def check_value(cls, value) -> bool:
        return abs(value) >= cls.border_value


class EffectToSmallError(EffectToSmallWarning):
    """ Error message regarding an only insignificant mean difference regarding the standard deviation. """

    type = StatMessageType.ERROR
    border_value = 1


class SignificanceTooLowWarning(StatWarning):
    """
    Warning regarding an only insignificant difference regarding a statistical test.
    The probability of the null hypothesis lies in the configured uncertainty range.
    """

    message = """The used statistical significance test showed that the significance of the
    difference with {props} is too low."""
    hint = """Increase the number of benchmarking runs."""

    @classmethod
    def check_value(cls, value) -> bool:
        r = Settings()["stats/uncertainty_range"]
        return r[0] <= value <= r[1]


class SignificanceTooLowError(SignificanceTooLowWarning):
    """
    Error message regarding an only insignificant difference regarding a statistical test.
    The probability of the null hypothesis is lower than the lower end of the configured uncertainty range.
    """

    type = StatMessageType.ERROR

    @classmethod
    def check_value(cls, value) -> bool:
        r = Settings()["stats/uncertainty_range"]
        return r[1] < value


class TestedPairProperty(BaseStatObject):
    """
    Statistical helper for comparing a pair of run data blocks for a specific measured property.
    """

    def __init__(self, parent: TestedPair, first: Single, second: Single, property: str, tester: Tester = None):
        """
        Creates an instance.

        :param parent: parent tested pair object
        :param first: first of the two compared single objects
        :param second: second of the two compared single objects
        :param property: regarded property
        :param tester: used statistical tester, if None the default tester is used (configured in the settings)
        :return:
        """
        super().__init__()
        self.parent = parent  # type: TestedPair
        """ Parent tested pair object """
        self.first = SingleProperty(first, first.rundata, property)  # type: SingleProperty
        """ First of the two compared single property objects """
        self.second = SingleProperty(second, second.rundata, property)
        """ Second of the two compared single property objects """
        self.tester = tester or TesterRegistry.get_for_name(TesterRegistry.get_used(),  # type: Tester
                                                            Settings()["stats/tester"],
                                                            Settings()["stats/uncertainty_range"])
        """ Used statistical tester for the comparisons """
        self.property = property
        """ Regarded specific property """

    def _get_stat_messages(self) -> t.List[StatMessage]:
        """
        Combines the messages for all inherited TestedPairProperty objects (for each property).

        :return: simplified list of all messages
        """
        msgs = self.first.get_stat_messages() + self.second.get_stat_messages()
        #if self.is_equal() == False:
        sign_val = self.tester.test(self.first.data, self.second.data)
        msgs += [
            EffectToSmallWarning.create_if_valid(self, self.property, self.mean_diff_per_dev()),
            EffectToSmallError.create_if_valid(self, self.property, self.mean_diff_per_dev()),
            SignificanceTooLowWarning.create_if_valid(self, self.property, sign_val),
            SignificanceTooLowError.create_if_valid(self, self.property, sign_val),
        ]

        return msgs
    
    def mean_diff(self) -> float:
        """
        Calculates the difference of the means between the first and the second single property object
        (mean(first) - mean(second)).
        """
        return self.first.mean() - self.second.mean()

    def mean_diff_ci(self, alpha: float) -> t.Tuple[float, float]:
        """
        Calculates the confidence interval in which the mean difference lies with the given probability.
        Assumes normal distribution.

        Adopted from http://www.kean.edu/~fosborne/bstat/06b2means.html

        :param alpha: given probability
        :return: lower, upper bound
        """
        d = self.mean_diff()
        t = sp.stats.norm.sf(1-alpha/2.0) * np.sqrt(self.first.variance() / self.first.observations() -
                                             self.second.variance() / self.second.observations())
        return d - t, d + t
    
    def mean_diff_per_mean(self) -> float:
        """
        Calculates the mean difference relative to the mean of the first
        ((mean(first) - mean(second)) / mean(first)).
        """
        return self.mean_diff() / self.first.mean()

    def first_rel_to_second(self) -> float:
        """
        Calculates the mean of the first relative to the mean of the second (mean(first) / mean(second)).
        """
        return self.first.mean() / self.second.mean()
    
    def mean_diff_per_dev(self) -> float:
        """
        Calculates the mean difference per standard deviation (maximum of the first's and the second's deviation).
        """
        return self.mean_diff() / self.max_std_dev()
    
    def equal_prob(self) -> float:
        """
        Probability of the null hypothesis being not not correct (tertiary logic).

        :return: p value between 0 and 1
        """
        return self.tester.test(self.first.data, self.second.data)
    
    def is_equal(self) -> t.Optional[bool]:
        """
        Checks the null hypothesis.

        :return: True or False if the p val isn't in the uncertainty range of the tester, None else
        """
        if self.tester.is_uncertain(self.first.data, self.second.data):
            return None
        return self.tester.is_equal(self.first.data, self.second.data)

    def mean_std_dev(self) -> float:
        """ Calculates the mean of the standard deviations of the first and the second. """
        return (self.first.mean() + self.second.mean()) / 2

    def max_std_dev(self) -> float:
        """ Calculates the maximum of the standard deviations of the first and the second. """
        return max(self.first.std_dev(), self.second.std_dev())

    def get_data_frame(self, show_property = True):
        columns = []
        if show_property:
            columns = ["{}: {}".format(self.first, self.property),
                             "{}: {}".format(self.second, self.property)]
        else:
            columns = [str(self.first), str(self.second)]
        series_dict = {
            columns[0]: pd.Series(self.first.data, name=columns[0]),
            columns[1]: pd.Series(self.second.data, name=columns[1])
        }
        frame = pd.DataFrame(series_dict, columns=list(reversed(columns)))
        return frame

    def is_single_valued(self) -> bool:
        return self.first.is_single_valued() and self.second.is_single_valued()

    def eq_except_property(self, other) -> bool:
        return isinstance(other, type(self)) and self.first.eq_except_property(self.second) \
               and self.tester == other.tester

    def __eq__(self, other) -> bool:
        return self.eq_except_property(other) and self.property == other.property

    def min_observations(self) -> int:
        """ Returns the minimum number of observations of the first and the second """
        return min(self.first.observations(), self.second.observations())

    def description(self) -> str:
        return "{} vs. {}".format(self.first, self.second)

    def swap(self) -> 'TestedPairProperty':
        """
        Swap the first and the second single object.

        :return: new instance
        """
        return TestedPairProperty(self.parent, self.parent.first, self.parent.second,
                                  self.property, self.tester)

    def max_rel_std_dev(self) -> float:
        return max(self.first.std_dev_per_mean(), self.second.std_dev_per_mean())


class SinglesProperty(BaseStatObject):

    def __init__(self, singles: t.List[t.Union[Single, SingleProperty]], property: str):
        """
        Creates an instance.

        :param singles: compared single property objects or single objects that are turned into one
        :param property: regarded measured property
        """
        super().__init__()
        self.singles = singles # type: t.List[SingleProperty]
        """ Compared single property objects """
        if isinstance(singles, List(T(Single))):
            self.singles = [single.properties[property] for single in singles]
        self.property = property
        """ Regarded measured property """

    def __str__(self) -> str:
        return "SinglesProperty(property={prop})".format(prop=self.property)

    def get_data_frame(self, **kwargs):
        columns = []
        data = {}
        min_len = min(len(single.data) for single in self.singles)
        for single in self.singles:
            name = str(single.parent)
            columns.append(name)
            data[name] = single.data[0:min_len]
        return pd.DataFrame(data, columns=columns)

    def boxplot(self, fig_width: Number, fig_height: Number = None):
        """
        Creates a (horizontal) box plot comparing all single object for a given property.

        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm, if None it is calculated from the figure width using the
                           aesthetic ratio
        """
        import seaborn as sns
        import matplotlib.pyplot as plt
        self.reset_plt()
        if fig_height is None:
            fig_height = self._height_for_width(fig_width)
        self._fig = plt.figure(figsize=self._fig_size_cm_to_inch(fig_width, fig_height))
        df = self.get_data_frame()
        sns.boxplot(data=df, orient="h")

    def _store_as_tex(self, filename: str, fig_width: Number, fig_height: Number, standalone: bool):
        """
        Stores the current figure as latex in a tex file.
        Works independently of matplotlib.

        Needs following code in the document preamble::

            \\usepackage{pgfplots}
            \\usepgfplotslibrary{statistics}

        Useful demo at http://tex.stackexchange.com/questions/115210/boxplot-in-latex

        :param filename: name of the tex file
        :param fig_width: width of the figure in cm
        :param fig_height: height of the figure in cm
        :param standalone: surround the tex code with an standalone document environment
        """
        if not filename.endswith(".tex"):
            filename += ".tex"
        descrs = [str(single.parent) for single in self.singles]
        tex = """
\\pgfplotsset{{width={width}cm, height={height}cm, compat=1.8}}
\\begin{{tikzpicture}}
    \\begin{{axis}}[
    cycle list name=auto,
    xlabel={xlabel},
    ytick={{{yticks}}},
    yticklabels={{{yticklabels}}},
    max space between ticks=50pt
    ]""".format(
            width=fig_width, height=fig_height, xlabel=self.property,
            yticklabels="\\\\".join(reversed(descrs)) + "\\\\",
            yticks=",".join(map(str, range(1, len(descrs) + 1)))
        )
        for single in reversed(self.singles):
            q1, q2, q3 = single.quartiles()
            wh_lower, wh_upper = single.whiskers()
            outliers = " ".join("(0, {})".format(x) for x in single.outliers())
            tex += """
        \\addplot+[
        boxplot prepared={{
            median={median},
            upper quartile={q3},
            lower quartile={q1},
            upper whisker={wh_upper},
            lower whisker={wh_lower}
        }},
        ] coordinates {{{outliers}}};
        """.format(median=single.median(), **locals())
        tex += """
    \end{axis}
\end{tikzpicture}
        """
        if standalone:
            tex = """
\\documentclass[margin=10pt]{standalone}
\\usepackage{pgfplots}
\\usepgfplotslibrary{statistics}
\\begin{document}
                  """ + tex + """
\\end{document}
"""
        with open(filename, "w") as f:
            f.write(tex)
            chown(f)
        return os.path.realpath(filename)

    def max(self) -> float:
        """ Calculates the maximum value of all compared single property objects. """
        return max(single.max() for single in self.singles)