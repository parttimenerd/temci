import logging

import math
import warnings

from temci.tester.testers import TesterRegistry
from .rundata import RunDataStatsHelper, RunData
from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register
import click, yaml, numpy, os, matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from ..utils.settings import Settings

class ReporterRegistry(AbstractRegistry):

    settings_key_path = "report"
    use_key = "reporter"
    use_list = False
    default = "html"
    _register = {}

class AbstractReporter:

    def __init__(self, misc_settings: dict = None, stats_helper: RunDataStatsHelper = None):
        self.misc = misc_settings
        if stats_helper is None:
            runs = []
            typecheck(Settings()["report/in"], ValidYamlFileName())
            with open(Settings()["report/in"], "r") as f:
                runs = yaml.load(f)
            self.stats_helper = RunDataStatsHelper.init_from_dicts(Settings()["stats"], runs)
        else:
            self.stats_helper = stats_helper

    def report(self):
        raise NotImplementedError()

@register(ReporterRegistry, "console", Dict({
    "out": FileNameOrStdOut() // Default("-") // Description("Output file name or stdard out (-)")
}))
class ConsoleReporter(AbstractReporter):
    """
    Simple reporter that outputs just text.
    """

    def report(self):
        with click.open_file(self.misc["out"], mode='w') as f:
            for block in self.stats_helper.runs:
                assert isinstance(block, RunData)
                print("{descr:<20} ({num:>5} single benchmarkings)"
                      .format(descr=block.description(), num=len(block.data[block.properties[0]])), file=f)
                for prop in sorted(block.properties):
                    mean = numpy.mean(block[prop])
                    stdev = numpy.std(block[prop])
                    print("\t {prop:<18} mean = {mean:>15.5f}, "
                          "deviation = {dev_perc:>10.5%} ({dev:>15.5f})".format(
                        prop=prop, mean=mean,
                        dev=stdev, dev_perc=stdev/mean
                    ))

            self._report_list("Equal program blocks",
                              self.stats_helper.get_evaluation(with_equal=True,
                                                               with_uncertain=False,
                                                               with_unequal=False), f)
            self._report_list("Unequal program blocks",
                              self.stats_helper.get_evaluation(with_equal=False,
                                                               with_uncertain=False,
                                                               with_unequal=True), f)
            self._report_list("Uncertain program blocks",
                              self.stats_helper.get_evaluation(with_equal=True,
                                                               with_uncertain=True,
                                                               with_unequal=True), f)

    def _report_list(self, title: str, list, file):
        if len(list) != 0:
            print(title, file=file)
            print("####################", file=file)
        for item in list:
            print("\t {} ⟷ {}".format(item["data"][0].description(),
                                       item["data"][1].description()), file=file)
            for prop in sorted(item["properties"]):
                prop_data = item["properties"][prop]
                perc = prop_data["p_val"]
                if prop_data["unequal"]:
                    perc = 1 - perc
                print("\t\t {descr:<18} probability = {perc:>10.5%}, speed up = {speed_up:>10.5%}"
                      .format(descr=prop_data["description"], perc=perc,
                              speed_up=prop_data["speed_up"]), file=file)


@register(ReporterRegistry, "html", Dict({
    "out": DirName() // Default("report") // Description("Output directory"),
    "html_filename": Str() // Default("report.html") // Description("Name of the HTML file"),
    "pair_kind": ExactEither("scatter", "reg", "resid", "kde", "hex") // Default("kde")
                 // Description("Kind of plot to draw for pair plots (see searborn.joinplot)"),
    "plot_size": PositiveInt() // Default(7) // Description("Width of the plots in centimeters")
}))
class HTMLReporter(AbstractReporter):
    """
    Reporter that produces a HTML bsaed report with lot's of graphics.
    """

    counter = 0
    """ Just a counter to allow collision free figure saving. """

    small_size = 3
    """ Width an height of small diagrams in cm """
    big_size = 7
    """ Width an height of small diagrams in cm """

    def report(self):
        if os.path.exists(self.misc["out"]):
            for file in os.listdir(self.misc["out"]):
                file_path = os.path.join(self.misc["out"], file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except:
                    pass
        else:
            os.mkdir(self.misc["out"])
        runs = self.stats_helper.runs
        ret_str = """
<html>
    <head>
        <title>Benchmarking report</title>
    </head>
    <body style="font-family: sans-serif;">
        <center>
        <h1>Benchmarking report</h1>
        """

        self.big_size = self.misc["plot_size"]
        self.small_size = math.floor(self.big_size * 2 / len(runs[0].properties))
        self.current_size = self.big_size
        for i in range(0, len(runs)):
            for j in range(0, i):
                ret_str += """
                    <h2>Summary of {descr} <=> {descr2}</h2>
                """.format(descr=runs[i].description(), descr2=runs[j].description())
                logging.info("Plot pair summary ({}, {})".format(i, j))
                ret_str += self._pair_summary(runs[i], runs[j])
            self._write(ret_str)
        for i in range(0, len(runs)):
            logging.info("Plot program block {}".format(i))
            ret_str += self._report_single(runs[i])
            self._write(ret_str)
        for i in range(0, len(runs)):
            for j in range(0, i):
                logging.info("Plot pair ({}, {})".format(i, j))
                ret_str += self._report_pair(runs[i], runs[j])
            self._write(ret_str)

    def _write(self, html_string: str):
        """
        Store the html string in the appropriate file and append "</center></body></html>"
        """
        with open(os.path.join(self.misc["out"], self.misc["html_filename"]), "w") as f:
            f.write(html_string + "</center></body></html>")

    def _use_big_size(self):
        plt.rcParams['figure.figsize'] = self.big_size, self.big_size
        self.current_size = self.big_size

    def _use_small_size(self):
        plt.rcParams['figure.figsize'] = self.small_size, self.small_size
        self.current_size = self.small_size

    def _report_single(self, data: RunData):
        ret_str = """
        <h2>{} ({} benchmarkings)</h2>
        """.format(data.description(), len(data[data.properties[0]]))
        ret_str += """
            <table><tr>
        """
        for (prop, descr) in self.stats_helper.properties:
            x = pd.Series(data[prop], name=descr)
            self._use_small_size()
            ax = sns.distplot(x)
            if self.small_size == self.current_size:
                plt.xticks([])
                plt.yticks([])
            filename = self._get_new_figure_filename()
            plt.xlim(0, max(data[prop]))
            plt.xlabel(descr)
            plt.savefig(filename)
            plt.title(descr)
            plt.close()
            ret_str += """
                <td><img src="file://{filename}"</td>
            """.format(filename=filename, sm=self.small_size)
        ret_str += """
            </tr>
            </table>
        """
        for (prop, descr) in self.stats_helper.properties:
            ret_str += """
            <h3>{prop} ({benchs} benchmarkings)</h3>
            """.format(prop=descr, benchs=len(data[prop]))
            x = pd.Series(data[prop], name=descr)
            self._use_big_size()
            ax = sns.distplot(x)
            filename = self._get_new_figure_filename()
            plt.xlim(min(data[prop]), max(data[prop]))
            plt.savefig(filename)
            plt.close()
            ret_str += """
                <img src="file://{filename}"/>
            """.format(filename=filename)
            prop_data = data[prop]
            vals = {
                "mean": np.mean(prop_data),
                "median": np.median(prop_data),
                "min": np.min(prop_data),
                "max": np.max(prop_data),
                "standard deviation": np.std(prop_data)
            }
            ret_str += """
            <table>
                <tr><th>statistical property</th><th>absolute value</th>
                    <th>relative to mean</th><th>relative to median</th></tr>
            """
            for name in sorted(vals.keys()):
                ret_str += """
                <tr><td>{name}</td>
                    <td align="right">{absolute}</td>
                    <td align="right">{rel_mean:15.5%}</td>
                    <td align="right">{rel_median:15.5%}</td>
                </tr>
                """.format(name=name, absolute=vals[name],
                           rel_mean=vals[name] / vals["mean"],
                           rel_median=vals[name] / vals["median"])
            ret_str += """
            </table>
            """
        return ret_str

    def _report_pair(self, first: RunData, second: RunData):



        ret_str = """
            <h2>{descr1} &lt;=&gt; {descr2}</h2>
        """.format(descr1=first.description(), descr2=second.description())

        ret_str += self._pair_summary(first, second)

        for (prop, descr) in self.stats_helper.properties:
            length = min(len(first[prop]), len(second[prop]))
            first_prop = first[prop][0:length]
            second_prop = second[prop][0:length]
            self._use_big_size()
            ret_str += """
                <h3>{prop} ({benchs} benchmarkings)</h3>
                <table>
                    <tr>
                        <td><img src="file://{filename}"/></td>
                        <td><img src="file://{filename2}"/></td>
                    </tr>
                </table>
                <h4>Probability of the null hypothesis</h4>
                I.e. the probability that the data sets of both program block of the property {prop}
                come from the same population.
                <table>
                    <tr><th>Tester</th><th>probability</th><th>Tester description</th></tr>
            """.format(filename=self._jointplot(first, second, prop), prop=prop,
                       filename2=self._barplot(first, second, prop), benchs=length)
            for tester_name in sorted(TesterRegistry._register.keys()):
                tester = TesterRegistry.get_for_name(tester_name, Settings()["stats/uncertainty_range"])
                ret_str += """
                    <tr><td>{tester}</td><td align="right">{prop:5.5%}</td><td>{tester_descr}</td></tr>
                """.format(tester=tester_name,
                           tester_descr=tester.__description__,
                           prop=tester.test(first[prop], second[prop])
                           )
            ret_str += """
                </table>
            """
            vals = {
                "mean": (np.mean(first_prop), np.mean(second_prop)),
                "median": (np.median(first_prop), np.median(second_prop)),
            }
            ret_str += """
                <table>
                    <tr><th>Diferrence in property</th>
                        <th>absolute difference</th>
                        <th>difference rel. to first</th>
                    </tr>
            """
            for descr in sorted(vals.keys()):
                first_val, second_val = vals[descr]
                ret_str += """
                    <tr><td>{descr}</td><td align="right">{diff:15.5}</td><td align="right">{rel_diff:3.5%}</td></tr>
                """.format(descr=descr, diff=first_val - second_val, rel_diff=(first_val - second_val) / first_val)
            ret_str += """
                </table>
            """
        return ret_str

    def _pair_summary(self, first: RunData, second: RunData):
        ret_str = """
            <table>
                <tr>
        """
        for (prop, descr) in self.stats_helper.properties:
            self._use_small_size()
            ret_str += """
                    <td><img src="file://{filename}"/></td>
            """.format(filename=self._jointplot(first, second, prop))
        ret_str += "</tr><tr>"
        for (prop, descr) in self.stats_helper.properties:
            self._use_small_size()
            ret_str += """
                    <td><img src="file://{filename}"/></td>
            """.format(filename=self._barplot(first, second, prop))
        ret_str += "</tr><tr>"
        for (prop, descr) in self.stats_helper.properties:
            length = min(len(first[prop]), len(second[prop]))
            first_prop = first[prop][0:length]
            second_prop = second[prop][0:length]
            ret_str += """
                <td><table>
                    <tr><th>tester</th><th>p val</th></tr>
            """
            for tester_name in sorted(TesterRegistry._register.keys()):
                tester = TesterRegistry.get_for_name(tester_name, Settings()["stats/uncertainty_range"])
                p_val = tester.test(first_prop, second_prop)
                text_color = "black"
                background_color = "white"
                if tester.is_equal(first_prop, second_prop):
                    text_color = "white"
                    background_color = "black"
                elif tester.is_unequal(first_prop, second_prop):
                    text_color = "white"
                    background_color = "green"
                ret_str += """
                        <tr style="color: {text_color}; background: {background_color};">
                        <td>{tester_name}</td><td>{p_val:3.5%}</td></tr>
                """.format(**locals())
            ret_str += "</table></td>"
        ret_str += """
                </tr>
            </table>
        """
        return ret_str

    def _jointplot(self, first: RunData, second: RunData, property: str) -> str:
        length = min(len(first[property]), len(second[property]))
        first_prop = first[property][0:length]
        second_prop = second[property][0:length]
        lim = (0, max(max(first_prop), max(second_prop)))
        x1 = pd.Series(first_prop, name="{descr}: {prop}".format(descr=first.description(), prop=property))
        x2 = pd.Series(second_prop, name="{descr}: {prop}".format(descr=second.description(), prop=property))
        plt.xlim(lim)
        g = sns.jointplot(x1, x2, kind=self.misc["pair_kind"], size=self.current_size, space=0,
                          stat_func=self.stats_helper.tester.test, xlim=lim, ylim=lim)
        if self.small_size == self.current_size:
            g.ax_joint.set_xticklabels([])
            g.ax_joint.set_yticklabels([])
        #g.ax_marg_x.set_xlim(*lim)
        #g.ax_marg_y.set_ylim(*lim)
        filename = self._save_figure(g)
        plt.close()
        return filename

    def _barplot(self, first: RunData, second: RunData, property: str) -> str:
        length = min(len(first[property]), len(second[property]))
        first_prop = first[property][0:length]
        second_prop = second[property][0:length]
        min_xval = min(first_prop + second_prop)
        max_xval = max(first_prop + second_prop)
        bins = np.linspace(min_xval, max_xval, math.floor(math.sqrt(length) * 3))
        sns.distplot(first_prop,bins=bins,label=first.description())
        sns.distplot(second_prop,bins=bins,label=second.description())
        if self.small_size == self.current_size:
            plt.xticks([])
            plt.yticks([])
        plt.xlim(min_xval, max_xval)
        plt.legend()
        filename = self._get_new_figure_filename()
        plt.savefig(filename)
        plt.close()
        return filename

    def _save_figure(self, figure: sns.JointGrid) -> str:
        filename = self._get_new_figure_filename()
        figure.savefig(filename)
        return filename

    def _get_new_figure_filename(self) -> str:
        self.counter += 1
        return os.path.join(os.path.abspath(self.misc["out"]), "figure.{}.svg".format(self.counter))
