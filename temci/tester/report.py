import logging

import math
import queue
import shlex
import shutil
import threading
import warnings
from collections import namedtuple

import multiprocessing

from temci.tester.testers import TesterRegistry
from temci.tester.rundata import RunDataStatsHelper, RunData
from temci.utils.typecheck import *
from temci.utils.registry import AbstractRegistry, register
import click, yaml, numpy, os, matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from temci.utils.settings import Settings
from multiprocessing import Queue, Pool

class ReporterRegistry(AbstractRegistry):

    settings_key_path = "report"
    use_key = "reporter"
    use_list = False
    default = "html"
    registry = {}

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
    "plot_size": PositiveInt() // Default(6) // Description("Width of the plots in centimeters"),
    "compared_props": (ListOrTuple(Str())) // Default(["all"])
                      // Description("Properties to include in comparison table"),
    "compare_against": NaturalNumber() // Default(0)
                       // Description("Run to to use as base run for relative values in comparison table")
}))
class HTMLReporter(AbstractReporter):
    """
    Reporter that produces a HTML bsaed report with lot's of graphics.
    """

    counter = 0
    """ Just a counter to allow collision free figure saving. """

    PlotTuple = namedtuple("PlotTuple", ["func", "args", "kwargs", "filename"])

    def report(self):
        if os.path.exists(self.misc["out"]):
            shutil.rmtree(self.misc["out"])
        resources_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "report_resources"))
        shutil.copytree(resources_path, self.misc["out"])
        runs = self.stats_helper.runs
        html = """
<html>
    <head>
        <title>Benchmarking report</title>
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.ui.all.css">
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.tocify.css">
        <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="file://{resources_path}/style.css">
        <script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js" integrity="sha512-K1qjQ+NcF2TYO/eI3M6v8EiNYZfA95pQumfvcVrTHtwQVDG+aHRqLi/ETn2uB+1JqwYqVG3LIvdm9lj6imS/pQ==" crossorigin="anonymous"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery-ui-1.9.1.custom.min.js"></script>
        <script src="file://{resources_path}/script.js"></script>
    </head>
    <body style="font-family: sans-serif;">
        <div id="toc"></div>
        <div class="container">
          <div class="row">
             <div class="col-sm-3">
                <div id="toc"></div>
            </div>
             <!-- sidebar, which will move to the top on a small screen -->
             <!-- main content area -->
             <div class="col-sm-9">
                <div class="page-header">
                    <h1>Benchmarking report</h1>
                    <p class="lead">A benchmarking report comparing {comparing_str}</p>
                  </div>
                {inner_html}
                <footer class="footer">Generated by temci</footer>
             </div>
          </div>
        </div>
    </body>
</html>
        """
        descriptions = [run.description() for run in self.stats_helper.runs]
        comparing_str = ""
        if len(descriptions) == 1:
            comparing_str = descriptions[0]
        elif len(descriptions) > 1:
            comparing_str = " and ".join([", ".join(descriptions[0:-1]), descriptions[-1]])
        inner_html = ""
        self.big_size = self.misc["plot_size"]
        self.small_size = max(2, math.floor(self.big_size * 2 / len(runs[0].properties)))
        if len(self.stats_helper.runs) > 1:
            logging.info("Generate comparison tables")
            inner_html += "<h2>Comparison tables</h2>" + self._comparison_tables()
            self._write(html.format(**locals()))
            for i in range(0, len(runs)):
                for j in range(0, i):
                    logging.info("Plot pair summary ({}, {})".format(i, j))
                    inner_html += self._pair_summary(runs[i], runs[j], heading_no=2)
                self._write(html.format(**locals()))
        for i in range(0, len(runs)):
            logging.info("Plot program block {}".format(i))
            inner_html += self._report_single(runs[i])
            self._write(html.format(**locals()))
        if len(self.stats_helper.runs) > 1:
            for i in range(0, len(runs)):
                for j in range(0, i):
                    logging.info("Plot pair ({}, {})".format(i, j))
                    inner_html += self._report_pair(runs[i], runs[j])
                self._write(html.format(**locals()))

    def _write(self, html_string: str):
        """
        Store the html string in the appropriate file and append "</center></body></html>"
        """
        with open(os.path.join(self.misc["out"], self.misc["html_filename"]), "w") as f:
            f.write(html_string)

    def _set_fig_size(self, size: int):
        plt.rcParams['figure.figsize'] = (size, size)
        self.current_size = size

    def _report_single(self, data: RunData):
        ret_str = """
        <h2>{}</h2><small>{} benchmarkings<br/></small>
        """.format(data.description(), len(data[data.properties[0]]))
        ret_str += """
            <table class="table"><tr>
        """
        for prop in sorted(self.stats_helper.properties):
            x = pd.Series(data[prop], name=prop)
            self._set_fig_size(self.small_size)
            ax = sns.distplot(x)
            if self.small_size == self.current_size:
                plt.xticks([])
                plt.yticks([])
            filename = self._get_new_figure_filename()
            plt.xlim(0, max(data[prop]))
            plt.xlabel(prop)
            plt.savefig(filename)
            plt.title(prop)
            plt.close()
            ret_str += """
                <td><img src="file://{filename}" class="img-rounded"></td>
            """.format(filename=filename, sm=self.small_size)
        ret_str += """
            </tr>
            </table>
        """
        for prop in sorted(self.stats_helper.properties):
            ret_str += """
            <h3>{prop}</h3><small>{benchs} benchmarkings<br/></small>
            """.format(prop=prop, benchs=len(data[prop]))
            x = pd.Series(data[prop], name=prop)
            self._set_fig_size(self.big_size)
            ax = sns.distplot(x, kde=False)
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
            <table class="table table-condensed table-striped">
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

        ret_str += self._pair_summary(first, second, heading_no=3)

        for prop in sorted(self.stats_helper.properties):
            length = min(len(first[prop]), len(second[prop]))
            first_prop = first[prop][0:length]
            second_prop = second[prop][0:length]
            ret_str += """
                <h3>{prop}</h3><small>{benchs} benchmarkings<br/></small><br/>
                <table class="table">
                    <tr>
                        <td><img src="file://{filename}"/></td>
                        <td><img src="file://{filename2}"/></td>
                    </tr>
                </table>
                <h4>Probability of the null hypothesis</h4>
                I.e. the probability that the data sets of both program block of the property {prop}
                come from the same population.
                <table class="table table-condensed">
                    <tr><th>Tester</th><th>probability</th><th>Tester description</th></tr>
            """.format(filename=self._jointplot(first, second, prop, size=self.big_size), prop=prop,
                       filename2=self._barplot(first, second, prop, size=self.big_size), benchs=length)
            for tester_name in sorted(TesterRegistry.registry.keys()):
                tester = TesterRegistry.get_for_name(tester_name, Settings()["stats/uncertainty_range"])
                p_val = tester.test(first[prop], second[prop])
                row_class = self._p_val_to_row_class(p_val)
                tester_descr = tester.__description__
                ret_str += """
                    <tr class="{row_class}"><td>{tester_name}</td><td align="right">{p_val:5.5%}</td>
                        <td>{tester_descr}</td></tr>
                """.format(**locals())
            ret_str += """
                </table>
            """
            vals = {
                "mean": (np.mean(first_prop), np.mean(second_prop)),
                "median": (np.median(first_prop), np.median(second_prop)),
            }
            ret_str += """
                <table class="table table-condensed">
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

    def _pair_summary(self, first: RunData, second: RunData, heading_no: int):
        html = """
                <h{no}>Summary of {descr} <=> {descr2}</h{no}>
                {{inner_html}}
        """.format(descr=first.description(), descr2=second.description(), no=heading_no)

        inner_html = """
            <table class="table table-bordered">
                <tr>
        """
        for prop in sorted(self.stats_helper.properties):
            inner_html += """
                    <td><img src="file://{filename}"/></td>
            """.format(filename=self._jointplot(first, second, prop, size=self.small_size, show_ticks=False))
        inner_html += "</tr><tr>"
        for prop in sorted(self.stats_helper.properties):
            inner_html += """
                    <td><img src="file://{filename}"/></td>
            """.format(filename=self._barplot(first, second, prop, size=self.small_size, show_ticks=False))
        inner_html += "</tr><tr>"
        for prop in sorted(self.stats_helper.properties):
            length = min(len(first[prop]), len(second[prop]))
            first_prop = first[prop][0:length]
            second_prop = second[prop][0:length]
            inner_html += """
                <td><table class="table">
                    <tr><th>tester</th><th>p val</th></tr>
            """
            for tester_name in sorted(TesterRegistry.registry.keys()):
                tester = TesterRegistry.get_for_name(tester_name, Settings()["stats/uncertainty_range"])
                p_val = tester.test(first_prop, second_prop)
                row_class = self._p_val_to_row_class(p_val)
                inner_html += """
                        <tr class="{row_class}">
                        <td>{tester_name}</td><td>{p_val:3.5%}</td></tr>
                """.format(**locals())
            inner_html += "</table></td>"
        inner_html += """
                </tr>
            </table>
        """
        return html.format(**locals())

    def _p_val_to_row_class(self, p_val: float) -> str:
        row_class = ""
        if self.stats_helper.is_equal(p_val):
            row_class = "danger"
        elif self.stats_helper.is_unequal(p_val):
            row_class = "success"
        return row_class

    def _comparison_tables(self, runs: list = None, properties: list = None, compare_against: int = None,
                           heading_no: int = 3) -> str:
        runs = runs or self.stats_helper.runs
        properties = list(properties or self.misc["compared_props"])
        compare_against = compare_against or self.misc["compare_against"]
        typecheck(properties, List(Str()))
        typecheck(runs, List(T(RunData)) // (lambda l: len(l) > 0))
        typecheck(compare_against, Int(range=range(len(runs))))
        if "all" in properties:
            properties = self.stats_helper.properties
        stat_funcs = {
            "mean": np.mean,
            "median": np.median,
            "min": np.min,
            "max": np.max,
            "standard deviation / mean": lambda l: np.std(l) / np.mean(l),
            "standard deviation / median": lambda l: np.std(l) / np.median(l)
        }
        ret_str = ""
        for stat_prop in sorted(stat_funcs.keys()):
            stat_func = stat_funcs[stat_prop]
            ret_str += """
                <h{n}>{prop}</h{n}>
            """.format(n=heading_no, prop=stat_prop)
            ret_str += self._comparison_table(stat_func, runs, properties, compare_against)
        return ret_str

    def _comparison_table(self, stat_func, runs: list, properties: list, compare_against: int) -> str:
        """
        :param stat_func: function that gets a data series (list) and returns a scalar (e.g. mean or median)
        :param runs: RunData objects to compare
        :param properties: used properties
        :param compare_against: use this run as the base run (for relative values)
        :return: html string
        """
        values = []
        for run in runs:
            values_for_run = {}
            for property in sorted(properties):
                values_for_run[property] = stat_func(run[property])
            values.append(values_for_run)
        ret_str = """
            <table class="table table-condensed table-striped">
                <tr><th></th>{}</tr>
        """.format("".join("<th>{}</th><td></td>".format(run.description(), compare_against) for run in runs))
        for property in sorted(properties):
            ret_str += """
                <tr>
                    <th>{}</th>
            """.format(property)
            for i, run in enumerate(runs):
                ret_str += """
                    <td align="right">{abs:15.5}</td><td align="right">{rel:3.3}</td>
                """.format(
                    abs=values[i][property],
                    rel=values[i][property] / values[compare_against][property]
                )
            ret_str += """
                </tr>
            """
        ret_str += """
                <tr>
                    <th>geometric mean</th>
        """
        # why? see https://dl.acm.org/citation.cfm?id=5673
        mult_compare_against = numpy.prod(list(values[compare_against].values()))
        for (i, run) in enumerate(runs):
            mult = numpy.prod(list(values[i].values()))
            ret_str += """
                <td align="right"></td><td align="right">{rel:3.3}</td>
            """.format(
                abs=numpy.power(mult, 1 / len(values[i])),
                rel=numpy.power(mult / mult_compare_against, 1 / len(values[i]))
            )
        ret_str += """
                    </tr>
                </table>
        """
        return ret_str

    def _jointplot(self, first: RunData, second: RunData, property: str, size: int, filename: str = None,
                   show_ticks: bool = True):
        filename = filename or self._get_new_figure_filename()
        length = min(len(first[property]), len(second[property]))
        first_prop = first[property][0:length]
        second_prop = second[property][0:length]
        lim = (0, max(max(first_prop), max(second_prop)))
        self._set_fig_size(size)
        x1 = pd.Series(first_prop, name="{descr}: {prop}".format(descr=first.description(), prop=property))
        x2 = pd.Series(second_prop, name="{descr}: {prop}".format(descr=second.description(), prop=property))
        plt.xlim(lim)
        g = sns.jointplot(x1, x2, kind=self.misc["pair_kind"], size=size, space=0,
                          stat_func=self.stats_helper.tester.test, xlim=lim, ylim=lim)
        if not show_ticks:
            g.ax_joint.set_xticklabels([])
            g.ax_joint.set_yticklabels([])
        g.savefig(filename)
        plt.close()
        return filename

    def _barplot(self, first: RunData, second: RunData, property: str, size: int,
                 filename: str = None, show_ticks: bool = True) -> str:
        filename = filename or self._get_new_figure_filename()
        self._set_fig_size(size)
        length = min(len(first[property]), len(second[property]))
        first_prop = first[property][0:length]
        second_prop = second[property][0:length]
        min_xval = min(first_prop + second_prop)
        max_xval = max(first_prop + second_prop)
        bins = np.linspace(min_xval, max_xval, math.floor(math.sqrt(length) * size))
        sns.distplot(first_prop, bins=bins,label=first.description(), kde=False)
        sns.distplot(second_prop, bins=bins,label=second.description(), kde=False)
        if not show_ticks:
            plt.xticks([])
            plt.yticks([])
        plt.xlim(min_xval, max_xval)
        plt.legend()
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
