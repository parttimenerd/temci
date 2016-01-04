import csv
import logging

import math
import queue
import re
import shlex
import shutil
import threading
import warnings
from collections import namedtuple

import multiprocessing

import time

import sys

import itertools

import humanfriendly

from temci.tester.stats import TestedPairsAndSingles, BaseStatObject, TestedPair, TestedPairProperty, StatMessage, \
    StatMessageType, Single, SingleProperty
from temci.tester.testers import TesterRegistry, Tester
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
from temci.utils.util import join_strs
import typing as t


class ReporterRegistry(AbstractRegistry):

    settings_key_path = "report"
    use_key = "reporter"
    use_list = False
    default = "html2"
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
        self.stats = TestedPairsAndSingles(self.stats_helper.runs)

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


@register(ReporterRegistry, "html2", Dict({
    "out": DirName() // Default("report") // Description("Output directory"),
    "html_filename": Str() // Default("report.html") // Description("Name of the HTML file"),
    "fig_width_small": Float() // Default(10.0) // Description("Width of all small plotted figures"),
    "fig_width_big": Float() // Default(20.0) // Description("Width of all big plotted figures"),
    "alpha": Float() // Default(0.05) // Description("Alpha value for confidence intervals"),
    "gen_tex": Bool() // Default(True) // Description("Generate simple latex versions of the plotted figures?"),
    "gen_pdf": Bool() // Default(True) // Description("Generate pdf versions of the plotted figures?")
}))
class HTMLReporter2(AbstractReporter):
    """
    Reporter that produces a HTML bsaed report with lot's of graphics.
    A rewite of the original HTMLReporter
    """

    counter = 0
    """ Just a counter to allow collision free figure saving. """

    def report(self):
        if os.path.exists(self.misc["out"]):
            shutil.rmtree(self.misc["out"])
        resources_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "report_resources"))
        shutil.copytree(resources_path, self.misc["out"])
        runs = self.stats_helper.runs
        self.app_html = ""
        html = """<html lang="en">
    <head>
        <title>Benchmarking report</title>
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.ui.all.css">
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.tocify.css">
        <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="file://{resources_path}/style.css">
        <script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js" integrity="sha512-K1qjQ+NcF2TYO/eI3M6v8EiNYZfA95pQumfvcVrTHtwQVDG+aHRqLi/ETn2uB+1JqwYqVG3LIvdm9lj6imS/pQ==" crossorigin="anonymous"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery-ui-1.9.1.custom.min.js"></script>
        <script type="text/javascript" src="https://cdn.mathjax.org/mathjax/latest/MathJax.js?config=TeX-AMS-MML_SVG"></script>
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
        {self.app_html}
        <script>
            $(function () {{
                $('[data-toggle="popover"]').popover()
                $('[data-toggle="popover"]').on('inserted.bs.popover', function () {{
                    MathJax.Hub.Queue(["Typeset",MathJax.Hub]);
                }})
            }})
        </script>
    </body>
</html>
        """
        comparing_str = join_strs([single.description() for single in self.stats.singles])
        inner_html = """
            <h2>Summary</h2>
        """
        inner_html += self._format_errors_and_warnings(self.stats)
        inner_html += """
            <h3>Overall summary</h3>
        """
        inner_html += self._full_single_property_comp_table().html()
        for prop in self.stats.properties():
            inner_html += """
                <h3>Summary regarding {prop}</h3>
            """.format(**locals())
            inner_html += self._full_single_property_comp_table(prop).html()
        for single in self.stats.singles:
            inner_html += """<div class="block">"""
            inner_html += self._extended_summary(single, with_title=True, title_level=2,
                                                 title_class="page-header") + """</div>"""
        for pair in self.stats.pairs:
            inner_html += """<div class="block">"""
            inner_html += self._extended_summary(pair, with_title=True, title_level=2,
                                                 title_class="page-header") + """</div>"""
        pool = multiprocessing.Pool(4)
        self._write(html.format(**locals()))
        logging.info("Finished generating html")
        logging.info("Generate images...")
        pool_res = [pool.apply_async(self._process_hist_cache_entry, args=(entry,))
                for entry in self._hist_async_img_cache.values()]
        for res in pool_res:
            res.get()
        self._write(html.format(**locals()))
        if self.misc["gen_pdf"] or self.misc["gen_tex"]:
            logging.info("Generate other figure formats...")
            pool_res = [pool.apply_async(self._process_hist_cache_entry, args=(entry,))
                        for entry in self._hist_async_misc_cache.values()]
            for (i, res) in enumerate(pool_res):
                res.get()

    def _write(self, html_string: str):
        """
        Store the html string in the appropriate file and append "</center></body></html>"
        """
        with open(os.path.join(self.misc["out"], self.misc["html_filename"]), "w") as f:
            f.write(html_string)

    def _full_single_property_comp_table(self, property: str = None) -> 'Table':
        header_cells = []
        for single in self.stats.singles:
            _single = SingleProperty(single, single.rundata, property) if property is not None else single
            modal_id = self._short_summary_modal(_single)
            header_cells.append(Cell(content=self._obj_description(single), color_class_obj=single,
                                     modal_id=modal_id))
        table = Table(self, header_cells, header_cells, Cell("vs."))

        for i in range(self.stats.number_of_singles()):
            for j in range(self.stats.number_of_singles()):
                popover = Popover("Explanation", content="")
                cell = None
                pair = self.stats.get_pair(i, j)
                rel_diff = None
                if property is None:
                    popover.content = """
                        Geometric mean of the mean differences relative to the means of the left:
                        \\[\\sqrt[\|properties\|]{
                        \\prod_{p \in \\text{properties}}
                        \\frac{\\overline{\\text{left[p]}} - \\overline{\\text{right[p]}}}{
                            \\overline{\\text{left[p]}}}}\]
                        <p>Using the more widely known would be like
                        <a href='http://ece.uprm.edu/~nayda/Courses/Icom6115F06/Papers/paper4.pdf?origin=publication_detail'>
                        lying</a></p>.
                    """
                    rel_diff = pair.rel_difference()
                    popover.trigger = "hover click"
                else:
                    pair = pair[property]
                    popover.content="""Difference relative to the mean of the left:
                    \\begin{align}
                        & \\frac{\\overline{\\text{left[%s]}} - \\overline{\\text{right[%s]}}}{\\overline{\\text{left[%s]}}} \\\\
                        &= \\frac{%5.4f - %5.4f}{%5.4f}
                    \\end{align}
                    """ % (property, property, property, pair.first.mean(), pair.second.mean(), pair.first.mean())
                    rel_diff = pair.mean_diff_per_mean()

                cell = Cell(content=str(rel_diff), popover=popover, color_class_obj=pair, show_click_on_info=True)
                cell.modal_id = self._short_summary_modal(pair)
                table[i, j] = cell
        return table

    def _extended_summary(self, obj: BaseStatObject, with_title: bool = True, title_level: int = 3,
                          title_class: str = "") -> str:
        html = ""
        if with_title:
            html += """<h{level} id='{id}' class="{tc}">
                            {title}</h{level}>""".format(level=title_level, tc=title_class,
                                                         title=self._obj_description(obj),
                                                         id=self._html_id_for_object("misc", obj))
        if isinstance(obj, Single):
            html += self._extended_summary_of_single(obj, title_level)
        if isinstance(obj, SingleProperty):
            html += self._extended_summary_of_single_property(obj, title_level)
        if isinstance(obj, TestedPair):
            html += self._extended_summary_of_tested_pair(obj, title_level)
        if isinstance(obj, TestedPairProperty):
            html += self._extended_summary_of_tested_pair_property(obj, title_level)
        return html

    def _extended_summary_of_single(self, obj: Single, title_level: int) -> str:
        html = self._short_summary(obj, use_modals=True, extended=False, title_level=title_level + 1)
        for prop in sorted(obj.properties.keys()):
            html += """<div class="sub-block"><h{level} class="page-header">{prop}</h{level}>""".format(
                level=title_level + 1, prop=prop
            )
            html += self._extended_summary(obj.properties[prop], with_title=False,
                                           title_level=title_level + 1, title_class="page-header")
            html += """</div>"""
        return html

    def _extended_summary_of_single_property(self, obj: SingleProperty, title_level: int) -> str:
        html = self._short_summary(obj, use_modals=True, extended=True, title_level=title_level + 1)
        return html

    def _extended_summary_of_tested_pair(self, obj: TestedPair, title_level: int) -> str:
        html = self._short_summary(obj, use_modals=True, extended=True, title_level=title_level + 1)
        for prop in sorted(obj.properties.keys()):
            html += """<div class="sub-block"><h{level} class="page-header">{prop}</h{level}>""".format(
                level=title_level + 1, prop=prop
            )
            html += self._extended_summary(obj.properties[prop], with_title=False,
                                           title_level=title_level + 1, title_class="page-header")
            html += """</div>"""
        return html


    def _extended_summary_of_tested_pair_property(self, obj: TestedPairProperty, title_level: int) -> str:
        html = self._short_summary(obj, use_modals=True, extended=True, title_level=title_level + 1)
        return html

    def _short_summary(self, obj: BaseStatObject, with_title: bool = False, title_level: int = 4,
                       use_modals: bool = False, extended: bool = False) -> str:
        html = ""
        if with_title:
            html += "<h{level}>{title}</h{level}>".format(level=title_level, title=self._obj_description(obj))
        html += self._format_errors_and_warnings(obj)
        if isinstance(obj, SingleProperty):
            html += self._short_summary_of_single_property(obj, use_modals, extended)
        if isinstance(obj, TestedPairProperty):
            html += self._short_summary_of_tested_pair_property(obj, use_modals, extended)
        if isinstance(obj, TestedPair):
            html += self._short_summary_of_tested_pair(obj, use_modals, extended)
        if isinstance(obj, Single):
            html += self._short_summary_of_single(obj, use_modals, extended)
        return html

    def _short_summary_of_single(self, obj: Single, use_modal: bool = False, extended: bool = False):
        obj_descrs = sorted(obj.properties.keys())
        objs = [obj.properties[val] for val in obj_descrs]
        return self._short_summary_table_for_single_property(objs=objs, objs_in_cols=False,
                                                             obj_descrs=obj_descrs, use_modal=use_modal,
                                                             extended=extended)

    def _short_summary_of_single_property(self, obj: SingleProperty, use_modals: bool = False, extended: bool = False):
        filenames = self._histogram(obj, big=extended, zoom_in=True)
        html = self._filenames_to_img_html(filenames)
        if extended:
            html += self._filenames_to_img_html(self._histogram(obj, big=extended, zoom_in=False))
        html += self._short_summary_table_for_single_property([obj], objs_in_cols=True, use_modal=use_modals,
                                                              extended=extended)
        return html

    def _short_summary_of_tested_pair_property(self, obj: TestedPairProperty, extended: bool = False,
                                               use_modals: bool = False):
        filenames = self._histogram(obj, big=extended, zoom_in=True)
        html = self._filenames_to_img_html(filenames)
        if extended:
            filenames = self._histogram(obj, big=extended, zoom_in=False)
            html += self._filenames_to_img_html(filenames)
        ci_popover = Popover("Confidence interval", """
                        The chance is \\[ 1 - \\alpha = {p} \\] that the mean difference
                        \\[ \\text{{{first}}}[{prop}] - \\text{{{second}}}[{prop}] \\\\ = {diff} \\]
                        lies in the interval $$({ci[0]}, {ci[1]})$$ (assuming the data is normal
                        distributed to a certain degree).
                        """.format(p=1-self.misc["alpha"], first=str(obj.first.parent),
                                   second=obj.second.parent, prop=obj.property,
                                   diff=obj.mean_diff(), ci=obj.mean_diff_ci(self.misc["alpha"])))
        tested_per_prop = [
            {
                "title": "Mean difference",
                "popover": Popover("Explanation", """
                    Difference between the mean of the first and the mean of the second.
                    It's the absolute difference and is often less important that the relative differences.
                """),
                "func": lambda x: x.mean_diff(),
                "format": "{:5.5f}"
            }, {
                "title": "... per mean",
                "func": lambda x: x.mean_diff_per_mean(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """The mean difference relative to the first mean
                \\begin{align}
                    & \\frac{ \\overline{\\text{%s}} - \\overline{\\text{%s}}}{ \\overline{\\text{%s}} } \\\\
                    &= \\frac{ %f }{ %f}
                \\end{align}
                gives a number that helps to talk about the practical significance of the mean difference.
                A tiny difference might be cool, but irrelevant (as caching effects are probably higher, use the
                <pre>temci build</pre> if you're curious about this).
                """ % (str(obj.first.parent), str(obj.second.parent), str(obj.first.parent), float(obj.mean_diff()),
                       float(obj.first.mean())))
            }, {
                "title": "... per std dev",
                "func": lambda x: x.mean_diff_per_dev(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """
                    The mean difference relative to the maximum standard deviation:
                    \\begin{{align}}
                        &\\frac{{
                            \\overline{{
                                \\text{{{first}}}
                                }}
                             - \\overline{{\\text{{{second}}}}}}}{{
                     \\text{{max}}(\\sigma_\\text{{{first}}}, \\sigma_\\text{{{second}}}) }} \\\\
                        = &  \\frac{{{md}}}{{{std}}}  \\end{{align}}

                    It's important, because as <a href='http://www.cse.unsw.edu.au/~cs9242/15/lectures/05-perfx4.pdf'>
                    Gernot Heiser</a> points out:
                    <ul>
                        <li>Don't believe any effect that is less than a standard deviation</li>
                        <li>Be highly suspicious if it is less than two standard deviations</li>
                    </ul>
                """.format(first=str(obj.first.parent), second=obj.second.parent,
                           md=obj.mean_diff(), std=obj.max_std_dev()), trigger="hover click")
            }, {
                "title": "... ci (lower bound)",
                "func": lambda x: x.mean_diff_ci(self.misc["alpha"])[0],
                "format": "{:5.5f}",
                "extended": True,
                "popover": ci_popover
            } ,{
                "title": "... ci (upper bound)",
                "func": lambda x: x.mean_diff_ci(self.misc["alpha"])[1],
                "format": "{:5.5f}",
                "extended": True,
                "popover": ci_popover
            }, {
                "title": obj.tester.name,
                "func": lambda x: x.equal_prob(),
                "format": "{:5.5%}",
                "popover": self._popover_for_tester(obj.tester)
            }
        ]
        if not extended:
            l = []
            for elem in tested_per_prop:
                if not ("extended" in elem and elem["extended"]):
                    l.append(elem)
            tested_per_prop = l

        def content_func(row_header: str, col_header: str, row: int, col: int):
            return tested_per_prop[row]["format"].format(tested_per_prop[row]["func"](obj))

        def header_popover_func(elem, index: int, is_header_row: bool):
            if not is_header_row and "popover" in tested_per_prop[index]:
                return tested_per_prop[index]["popover"]

        table = Table.from_content_func(self, cols=[obj],
                                        rows=list(map(lambda d: d["title"], tested_per_prop)),
                                        content_func=content_func, anchor_cell=Cell(),
                                        header_popover_func=header_popover_func)
        html += str(table)
        html += self._short_summary_table_for_single_property(objs=[obj.first, obj.second],
                                                              obj_descrs=[obj.first.description(),
                                                                          obj.second.description()],
                                                              objs_in_cols=False,
                                                              use_modal=use_modals)
        return html

    def _short_summary_of_tested_pair(self, obj: TestedPair, extended: bool = False, use_modals: bool = False) -> str:
        tested_per_prop = [
            {
                "title": "Mean difference",
                "popover": Popover("Explanation", """
                    Difference between the mean of the first and the mean of the second.
                    It's the absolute difference and is often less important that the relative differences.
                """),
                "func": lambda x: x.mean_diff(),
                "format": "{:5.5f}"
            }, {
                "title": "... per mean",
                "func": lambda x: x.mean_diff_per_mean(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """The mean difference relative to the first mean
                gives a number that helps to talk about the practical significance of the mean difference.
                A tiny difference might be cool, but irrelevant (as caching effects are probably higher, use the
                \\verb|temci build| if you're curious about this).
                """)
            }, {
                "title": "... per std dev",
                "func": lambda x: x.mean_diff_per_dev(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """
                The mean difference relative to the maximum standard deviation is important,
                because as <a href='http://www.cse.unsw.edu.au/~cs9242/15/lectures/05-perfx4.pdf'>
                    Gernot Heiser</a> points out:
                    <ul>
                        <li>Don't believe any effect that is less than a standard deviation</li>
                        <li>Be highly suspicious if it is less than two standard deviations</li>
                    </ul>
                """, trigger="hover click")
            }, {
                "title": "... ci",
                "func": lambda x: x.mean_diff_ci(self.misc["alpha"])[0],
                "format": "{:5.5f}",
                "extended": True,
                "popover": Popover("Confidence interval", """
                        The chance is \\[ 1 - \\alpha = {p} \\] that the mean difference
                        lies in the interval of which the lower and the upper bound are given
                        (assuming the data is normal distributed to a certain degree).
                                                """.format(p=1-self.misc["alpha"]))
            } ,{
                "title": "",
                "func": lambda x: x.mean_diff_ci(self.misc["alpha"])[1],
                "format": "{:5.5f}",
                "extended": True,
                "popover": Popover("Confidence interval", """
                        The chance is \\[ 1 - \\alpha = {p} \\] that the mean difference
                        lies in the interval of which the lower and the upper bound are given.
                                                """.format(p=1-self.misc["alpha"]))
            }, {
                "title": obj.tester.name,
                "func": lambda x: x.equal_prob(),
                "format": "{:5.5%}",
                "popover": self._popover_for_tester(obj.tester)
            }
        ]
        if not extended:
            l = []
            for elem in tested_per_prop:
                if not ("extended" in elem and elem["extended"]):
                    l.append(elem)
            tested_per_prop = l

        def header_link_func(elem: str, index: int, is_header_row: bool):
            if not is_header_row and not use_modals:
                return "#" + self._html_id_for_object("misc", obj.properties[elem])

        def header_modal_func(elem: str, index: int, is_header_row: bool):
            if not is_header_row and use_modals:
                return self._short_summary_modal(obj.properties[elem])

        def content_func(row_header: str, col_header: str, row: int, col: int):
            d = tested_per_prop[col]
            res = d["func"](obj.properties[row_header])
            return d["format"].format(res)

        def header_color_obj(elem, index: int, is_header_row: bool):
            if not is_header_row:
                return obj[elem]

        def header_popover_func(elem, index: int, is_header_row: bool):
            if is_header_row and "popover" in tested_per_prop[index]:
                return tested_per_prop[index]["popover"]

        table = Table.from_content_func(self, rows=sorted(list(obj.properties.keys())),
                                        cols=list(map(lambda d: d["title"], tested_per_prop)),
                                        header_link_func=header_link_func,
                                        content_func=content_func, anchor_cell=Cell(),
                                        header_color_obj_func=header_color_obj,
                                        header_modal_func=header_modal_func,
                                        header_popover_func=header_popover_func)
        html = str(table)
        html += """
            <p {po}>The <b>relative difference</b> between {first} and {second} is <b>{rel_diff}</d>
        """.format(po=Popover("Explanation", """
                        Geometric mean of the mean differences relative to the means of the first:
                        \\[\\sqrt[\|properties\|]{
                        \\prod_{p \in \\text{properties}}
                        \\frac{\\overline{\\text{first[p]}} - \\overline{\\text{second[p]}}}{
                            \\overline{\\text{first[p]}}}}\]
                        Using the more widely known would be like
                        <a href='http://ece.uprm.edu/~nayda/Courses/Icom6115F06/Papers/paper4.pdf?origin=publication_detail'>
                        lying</a>.
                 """, trigger="hover click"), first=obj.first, second=obj.second, rel_diff=obj.rel_difference())
        return html

    def _short_summary_table_for_single_property(self, objs: t.List[SingleProperty], use_modal: bool,
                                                 objs_in_cols: bool, obj_descrs: t.List[str] = None,
                                                 extended: bool = False) -> str:
        """
        :param objs: objects to look on
        :param use_modal: use modals for meta information, not simple links?
        :param objs_in_cols: show the different objects in own columns, not rows
        :param extended: more infos
        :return:
        """
        obj_descrs = obj_descrs or [self._obj_description(obj) for obj in objs]

        #objs[0]..std_dev_per_mean()
        mean_ci_popover = Popover("Mean confidence interval", """
                The chance is \\[ 1 - \\alpha = {p} \\] that the mean lies in the given interval
                (assuming the data is normal distributed to a certain degree).
                """.format(p=1-self.misc["alpha"]))
        std_dev_ci_popover = Popover("Standard deviation confidence interval", """
                The chance is \\[ 1 - \\alpha = {p} \\] that the standard deviation lies in the given interval
                (assuming the data is normal distributed to a certain degree).
                """.format(p=1-self.misc["alpha"]))
        tested_per_prop = [
            {
                "title": "mean",
                "func": lambda x: x.mean(),
                "format": "{:5.5f}",
                "popover": Popover("Explanation", """The simple arithmetical mean
                    \\[ \\frac{1}{n}\\sum_{i=1}^{n} a_i. \\]
                """)
            }, {
                "title": "std dev",
                "popover": Popover("Explanation", """
                    The sample standard deviation
                    \\[ \\sigma_N = \\sqrt{\\frac{1}{N} \\sum_{i=1}^N (x_i - \\overline{x})^2} \\]
                    In statistics, the standard deviation is a measure that is used to quantify the amount of
                    variation or dispersion of a set of data values. A standard deviation close to 0
                    indicates that the data points tend to be very close to the mean (also called the
                    expected value) of the set, while a high standard deviation indicates that the data
                    points are spread out over a wider range of values.
                    (<a href='https://en.wikipedia.org/wiki/Standard_deviation'>wikipedia</a>)
                """, trigger="hover click"),
                "func": lambda x: x.std_dev(),
                "format": "{:5.5f}"
            }, {
                "title": "... per mean",
                "func": lambda x: x.std_dev_per_mean(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """
                    The standard deviation relative to the mean is a measure of how big the relative variation
                    of data is. A small value is considered neccessary for a benchmark to be useful.
                    Or to quote <a href='https://www.cse.unsw.edu.au/~gernot/benchmarking-crimes.html'>
                    Gernot Heiser</a>:
                    <p>Always do several runs, and check the standard deviation. Watch out for abnormal variance.
                    In the sort of measurements we do, standard deviations are normally
                    expected to be less than 0.1%. If you see >1% this should ring alarm bells.</p>
                """, trigger="hover click")
            }, {
                "title": "sem",
                "popover": Popover("Explanation", """Standard error mean:
                    \\[ \\sigma(\\overline{X}) = \\frac{\\sigma}{\\sqrt{n}} \\]
                    <p>Put simply, the standard error of the sample is an estimate of how far the sample mean is
                    likely to be from the population mean, whereas the standard deviation of the sample is the
                    degree to which individuals within the sample differ from the sample mean.
                    (<a href='https://en.wikipedia.org/wiki/Standard_error'>wikipedia</a>)</p>""",
                                   trigger="hover focus"),
                "func": lambda x: x.sem(),
                "format": "{:5.5f}",
                "extended": False
            }, {
                "title": "median",
                "func": lambda x: x.median(),
                "format": "{:5.5f}",
                "popover": Popover("Explanation", """
                    The median is the value that seperates that data into two equal sizes subsets
                    (with the &lt; and the &gt; relation respectively).
                    As the mean and the standard deviation are already given here, the median isn't important.
                """),
                "extended": True
            }, {
                "title": "min",
                "func": lambda x: x.min(),
                "format": "{:5.5f}",
                "popover": Popover("Explanation", """The minimum value. It's a bad sign if the maximum
                                                  is far lower than the mean and you can't explain it.
                                                  """),
                "extended": True
            }, {
                "title": "max",
                "func": lambda x: x.min(),
                "format": "{:5.5f}",
                "popover": Popover("Explanation", """The maximum value. It's a bad sign if the maximum
                                                  is far higher than the mean and you can't explain it.
                                                  """),
                "extended": True
            }, {
                "title": "n",
                "func": lambda x: x.observations(),
                "format": "{}",
                "popover": Popover("Explanation", """The number of valid runs
                or statistically spoken: the sample size."""),
                "extended": True
            }, {
                "title": "mean ci (lower bound)",
                "func": lambda x: x.mean_ci(self.misc["alpha"])[0],
                "format": "{:5.5f}",
                "extended": True,
                "popover": mean_ci_popover
            } ,{
                "title": "mean ci (upper bound)",
                "func": lambda x: x.mean_ci(self.misc["alpha"])[1],
                "format": "{:5.5f}",
                "extended": True,
                "popover": mean_ci_popover
            }, {
                "title": "std dev ci (lower bound)",
                "func": lambda x: x.std_dev_ci(self.misc["alpha"])[0],
                "format": "{:5.5f}",
                "extended": True,
                "popover": mean_ci_popover
            } ,{
                "title": "std dev ci (upper bound)",
                "func": lambda x: x.std_dev_ci(self.misc["alpha"])[1],
                "format": "{:5.5f}",
                "extended": True,
                "popover": mean_ci_popover
            }, {
                "title": "normality probability",
                "func": lambda x: x.normality(),
                "format": "{:5.5%}",
                "popover": Popover("Explanation", """
                    Quoting the
                    <a href='http://blog.minitab.com/blog/michelle-paret/using-the-mean-its-not-always-a-slam-dunk'>
                    minitab blog</a>:
                    <p>If process knowledge tells you that your data should follow a normal distribution,
                    then run a normality test to be sure. If your Anderson-Darling Normality
                    Test p-value is larger than, say, an alpha level of 0.05 (here {alpha}), then you can conclude
                    that your data follow a normal distribution and, therefore, the mean is an adequate
                    measure of central tendency.</p>
                    The T test is robust against non normality, but that's not the case fpr statistical properties like
                    the given confidence intervals.
                """.format(alpha=self.misc["alpha"])),
                "extended": True
            }
        ]

        if not extended:
            l = []
            for elem in tested_per_prop:
                if not ("extended" in elem and elem["extended"]):
                    l.append(elem)
            tested_per_prop = l

        def header_link_func(elem: SingleProperty, index: int, is_header_row: bool):
            if objs_in_cols == is_header_row and not use_modal:
                return "#" + self._html_id_for_object("misc", elem)

        def header_modal_func(elem: SingleProperty, index: int, is_header_row: bool):
            if objs_in_cols == is_header_row and use_modal:
                return self._short_summary_modal(elem)

        def header_popover_func(elem, index: int, is_header_row: bool):
            if objs_in_cols != is_header_row and "popover" in tested_per_prop[index]:
                return tested_per_prop[index]["popover"]

        def content_func(row_header: t.Union[SingleProperty, str], col_header: t.Union[SingleProperty, str],
                         row: int, col: int):
            d = {}
            obj = None # type: SingleProperty
            if objs_in_cols:
                d = tested_per_prop[row]
                obj = col_header
            else:
                d = tested_per_prop[col]
                obj = row_header
            return d["format"].format(d["func"](obj))

        def header_color_obj(elem, index: int, is_header_row: bool):
            if objs_in_cols == is_header_row:
                return elem

        def header_content_func(elem, index: int, is_header_row: bool) -> str:
            if objs_in_cols == is_header_row:
                return obj_descrs[index]
            return tested_per_prop[index]["title"]

        func_titles = list(map(lambda d: d["title"], tested_per_prop))
        rows = []
        cols = []
        if objs_in_cols:
            cols = objs
            rows = func_titles
        else:
            cols = func_titles
            rows = objs
        table = Table.from_content_func(self, rows=rows,
                                        cols=cols,
                                        header_link_func=header_link_func,
                                        content_func=content_func, anchor_cell=Cell(),
                                        header_color_obj_func=header_color_obj,
                                        header_content_func=header_content_func,
                                        header_modal_func=header_modal_func,
                                        header_popover_func=header_popover_func)
        return str(table)

    def _filenames_to_img_html(self, filenames: t.Dict[str, str]):
        return """
            <center>
                <div {popover}>
                    <img width="100%" src="file://{img}" class="img"></img>
                </div>
            </center>
        """.format(popover=self._img_filenames_popover(filenames), **filenames)

    def _img_filenames_popover(self, filenames: t.Dict[str, str]) -> 'Popover':
        html = """
            <div class='list-group'>
        """
        if "img" in filenames:
            html += """
                  <a href='file://{img}' class='list-group-item'>
                    The current image
                  </a>
            """.format(**filenames)
        if "pdf" in filenames:
            html += """
                  <a href='file://{pdf}' class='list-group-item'>
                    PDF (generated by matplotlib)
                  </a>
            """.format(**filenames)
        if "tex" in filenames:
            html += """
                  <a href='file://{tex}' class='list-group-item'>
                    TeX (requiring the package pgfplots)
                  </a>
                  <a href='file://{tex_standalone}' class='list-group-item'>
                    Standalone TeX
                  </a>
            """.format(**filenames)
        html += """
            </div>
        """.format(**filenames)
        return Popover("Get this image in your favorite format", content=html,
                       trigger="hover click")

    _hist_cache = {} # type: t.Dict[str, t.Dict[str, str]]
    _hist_async_img_cache = {}
    _hist_async_misc_cache = {}

    def _histogram(self, obj: BaseStatObject, fig_width: int = None, zoom_in: bool = True,
                   big: bool = False) -> t.Dict[str, str]:
        if fig_width is None:
            fig_width = self.misc["fig_width_big"] if big else self.misc["fig_width_small"]
        filename = self._get_fig_filename(obj) + "___{}___{}".format(fig_width, zoom_in)
        if filename not in self._hist_cache:
            d = {
                "img": filename + ".svg"
            }
            if self.misc["gen_tex"]:
                d["tex"] = filename + ".tex"
                d["tex_standalone"] = filename + "____standalone.tex"
            if self.misc["gen_pdf"]:
                d["pdf"] = filename + ".pdf"
            self._hist_cache[filename] = d
            self._hist_async_img_cache[filename] = {
                "filename": filename,
                "obj": obj,
                "fig_width": fig_width,
                "zoom_in": zoom_in,
                "img": True,
                "tex": False,
                "pdf": False,
                "tex_sa": False
            }
            if self.misc["gen_pdf"] or self.misc["gen_tex"]:
                self._hist_async_misc_cache[filename] = {
                    "filename": filename,
                    "obj": obj,
                    "fig_width": fig_width,
                    "zoom_in": zoom_in,
                    "img": False,
                    "tex": self.misc["gen_tex"],
                    "pdf": self.misc["gen_pdf"],
                    "tex_sa": self.misc["gen_tex"]
                }
        return self._hist_cache[filename]


    def _process_hist_cache_entry(self, entry: t.Dict[str, str]):
        entry["obj"].histogram(zoom_in=entry["zoom_in"], fig_width=entry["fig_width"])
        entry["obj"].store_figure(entry["filename"], fig_width=entry["fig_width"], img=entry["img"], tex=entry["tex"],
                              pdf=entry["pdf"], tex_standalone=entry["tex_sa"])
        logging.debug("Plotted {}, zoom_in={}, fig_width={}cm, img={}, tex={}, pdf={}"
                     .format(entry["obj"], entry["zoom_in"], entry["fig_width"],
                     entry["img"], entry["tex"], entry["pdf"]))

    def _popover_for_tester(self, tester: Tester):
        return Popover(tester.name.capitalize(), """
                    Probability that the null hypothesis is not incorrect. It's the probability that the measured
                    values (for a given property) come out of the same population for both benchmarked programs.
                    Or short: That the programs have the same characteristics for a given property. <br/>
                    <b>Important note</b>: Statistical tests can only given an probability of the null hypothesis being incorrect.
                    But this okay, if you're aim is to see whether a specific program is better (different) than another
                    program in some respect. <br/>
               """)

    def _short_summary_modal(self, obj: BaseStatObject) -> str:
        """

        :param obj:
        :return: id
        """
        if not hasattr(self, "_modal_cache"):
            self._modal_cache = [] # type: t.List[str]
        modal_id = self._html_id_for_object("short_summary_modal", obj)
        if modal_id in self._modal_cache:
            return modal_id
        modal_title = self._obj_description(obj)
        modal_body = self._short_summary(obj, with_title=False)
        html_id = self._html_id_for_object("misc", obj)
        html = """
            <div class="modal fade" id="{modal_id}" tabindex="-10" role="dialog">
              <div class="modal-dialog" role="document">
                <div class="modal-content">
                  <div class="modal-header">
                    <button type="button" class="close" data-dismiss="modal"><span>&times;</span></button>
                    <h4 class="modal-title" id="{modal_id}_label"><a href="#{html_id}">{modal_title}</a></h4>
                  </div>
                  <div class="modal-body">
                    {modal_body}
                  </div>
                  <div class="modal-footer">
                    <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" data-dismiss="modal"
                        onclick="window.location='#{html_id}'">More informations</button>
                  </div>
                </div>
              </div>
            </div>
        """.format(**locals())
        self.app_html += html
        return modal_id

    def _obj_description(self, obj: BaseStatObject) -> str:
        if isinstance(obj, Single):
            return obj.description()
        if isinstance(obj, TestedPair):
            return "{} vs. {}".format(self._obj_description(obj.first), self._obj_description(obj.second))
        if isinstance(obj, SingleProperty) or isinstance(obj, TestedPairProperty):
            obj_base = ""
            if isinstance(obj, SingleProperty):
                obj_base = obj.rundata.description()
            else:
                obj_base = self._obj_description(obj.parent)
            return obj_base + " (regarding {})".format(obj.property)

    def _html_id_for_object(self, scope: str, obj: BaseStatObject) -> str:
        return "{}___{}".format(scope, self._get_obj_id(obj))

    def _get_obj_id(self, obj: BaseStatObject) -> str:
        if isinstance(obj, Single):
            return str(self.stats.singles.index(obj))
        if isinstance(obj, TestedPair):
            return self._get_obj_id(obj.first) + "_" + self._get_obj_id(obj.second)
        if isinstance(obj, SingleProperty) or isinstance(obj, TestedPairProperty):
            return self._get_obj_id(obj.parent) + "__" + self._html_escape_property(obj.property)
        assert False # you shouldn't reach this point

    def _html_escape_property(self, property: str) -> str:
        return re.sub(r"([^a-zA-Z0-9]+)", "000000", property)

    def _format_errors_and_warnings(self, obj: BaseStatObject, show_parent: bool = True) -> str:

        def format_msg(msg: StatMessage):
            message = msg.generate_msg_text(show_parent)
            msg_class = "div_danger" if msg.type == StatMessageType.ERROR else "div_warning"
            html = """
                <div class="panel-body {msg_class}">
                    {message}
                </div>
            """.format(**locals())
            if msg.hint != "" and msg.hint is not None:
                html = """
                    <div tabindex="0" class="panel-body {msg_class}" data-content="{msg.hint}"
                        data-trigger="hover" data-toggle="popover" data-placement="auto top" data-title="Hint">
                        {message}
                    </div>
                """.format(**locals())
            return html

        def collapsible(title: str, msgs: t.List[StatMessage]):
            collapse_id = self._random_html_id()
            heading_id = self._random_html_id()
            inner = "\n".join(map(format_msg, msgs))
            return """
                <div class="panel-group" role="tablist">
                <div class="panel panel-default">
                    <div class="panel-heading" role="tab" id="{heading_id}">
                      <h4 class="panel-title">
                        <a role="button" data-toggle="collapse" href="#{collapse_id}" style="display: block">
                            {title}
                        </a>
                      </h4>
                    </div>
                    <div id="{collapse_id}" class="panel-collapse collapse" role="tabpanel">
                        {inner}
                    </div>
                  </div>
                </div>
            """.format(**locals())
        html = ""
        if obj.has_errors():
            html += collapsible('Errors <span class="badge">{}</span>'.format(len(obj.errors())), obj.errors())
        if obj.has_warnings():
            html += collapsible('Warnings <span class="badge">{}</span>'.format(len(obj.warnings())), obj.warnings())
        return html

    _time = time.time()

    def _get_fig_filename(self, obj: BaseStatObject) -> str:
        """ Without any extension. """
        return os.path.realpath(os.path.join(os.path.abspath(self.misc["out"]),
                                             self._html_id_for_object("fig{}".format(self._time), obj)))

    _id_counter = 1000

    def _random_html_id(self) -> str:
        self._id_counter += 1
        return "id" + str(self._id_counter)


class Popover:

    def __init__(self, title: str, content: str, trigger: str = "hover"):
        self.title = title
        self.content = content
        self.trigger = trigger

    def __str__(self) -> str:
        content = """<div class='hyphenate'>""" + self.content + """</div>"""
        focus = 'tabindex="0" role="button"' if self.trigger == "focus" else ""
        return '{focus} data-content="{content}" data-trigger="{trigger}" data-toggle="popover" data-html="true"' \
           'data-placement="auto" data-title="{title}" data-container="body"'\
            .format(content=content, trigger=self.trigger, title=self.title, focus=focus)


def color_class(obj: BaseStatObject) -> str:
    if obj.has_errors():
        return "danger"
    if obj.has_warnings():
        return "warning"
    if isinstance(obj, TestedPairProperty):
        if obj.is_equal() is not None:
            return "sucess" if obj.is_equal() == False and obj.mean_diff_per_mean() < 1 else "active"
    return None


def color_explanation(obj: BaseStatObject) -> str:
    _color_class = "div_" + color_class(obj)
    msg = ""
    if obj.has_errors():
        msg = "This color means that the corresponding data set is erroneous " \
              "(with {} errors and {} warnings).".format(len(obj.errors()), len(obj.warnings()))
    elif obj.has_warnings():
        msg = "This color means that the corresponding data set could be erroneous " \
              "(with {} warnings).".format(len(obj.warnings()))
    elif isinstance(obj, TestedPairProperty) and obj.is_equal() is not None:
        msg = "This color means that everything is probably okay with the corresponding data" \
              " and that the tester could make a decision."
    if msg != "":
        return """
            <p class='{_color_class}'>
                {msg}
            </p>
        """.format(**locals())


class Cell:
    """
    Cell of a html table
    """

    def __init__(self, content: str = "", cell_class: str = "", popover: Popover = None,
                 modal_id: str = None, color_class_obj: BaseStatObject = None,
                 is_header_cell: bool = False, cell_scope: str = None,
                 show_click_on_info: bool = None, link: str = None):
        """
        :param content: displayed text of the cell
        :param cell_class: CSS class of the table cellr
        :param modal_id: id of the modal linked to this cell
        :param color_class_obj: object used to get the color class. Adds also an explanation to the popover
        :param is_header_cell: is the cell a header cell?
        """
        self.content = content
        self.cell_class = cell_class
        self.popover = popover
        self.modal_id = modal_id
        self.link = link
        assert link is None or modal_id is None
        if color_class_obj is not None:
            if self.popover is None:
                self.popover = Popover("Explanation", color_explanation(color_class_obj))
            else:
                self.popover.content += color_explanation(color_class_obj)
            self.cell_class += " " + color_class(color_class_obj)
        if (modal_id is not None and show_click_on_info != False) or (show_click_on_info is True and not link):
            msg = "<p>Click on the cell to get more information.</p>"
            if self.popover is None:
                self.popover = Popover("Explanation", msg)
            else:
                self.popover.content += msg
        self.is_header_cell = is_header_cell
        self.cell_scope = cell_scope

    def __str__(self):
        cell_tag = "th" if self.is_header_cell else "td"
        scope = 'scope="{}"'.format(self.cell_scope) if self.cell_scope else ""
        html = """<{} class="{}" {}>""".format(cell_tag, self.cell_class, scope)
        html_end = "</{}>".format(cell_tag)
        if self.popover:
            html += """<div style="width: 100%" {}>""".format(self.popover)
            html_end = "</div>" + html_end
        if self.modal_id:
            html += """<a data-toggle="modal" data-target="#{id}" style="width:100%;">""".format(id=self.modal_id)
            html_end = "</a>" + html_end
        if self.link:
            html += """<a href="{link}" data-dismiss="modal" style="width:100%;">""".format(link=self.link)
            html_end = "</a>" + html_end
        return html + self.content + html_end


T1 = t.TypeVar('T1', BaseStatObject, str, int, float, bool)
T2 = t.TypeVar('T2', BaseStatObject, str, int, float, bool)


class Table:
    """
    A html table consisting of Cell objects.
    Idea: Abstract the creation of html tables to a degree that allows automatic generation of latex and csv.
    """

    def __init__(self, parent: HTMLReporter2, header_row: t.List['Cell'], header_col: t.List['Cell'],
                 anchor_cell: 'Cell' = None, content_cells: t.List[t.List['Cell']] = None):
        """
        The resulting table has len(header_row) + rows and len(header_col) + 1 columns.
        :param header_row: list of cells of the bold top header row
        :param header_col: list of cells of the bold left header collumn
        :param anchor_cell: the cell in the top left corner of the table
        :param content_cells: a list of content rows
        :return resulting html
        """
        self.parent = parent
        self.header_row = header_row
        self.header_col = header_col
        for cell in itertools.chain(self.header_row, self.header_col):
            cell.is_header_cell = True
        for cell in self.header_col:
            cell.cell_scope = "row"
        assert len(header_row) > 0
        self.orig_anchor_cell = Cell("") if anchor_cell is None else Cell(anchor_cell.content)
        self.anchor_cell = anchor_cell or Cell("&#9047; ")
        self.anchor_cell.content += "  	&#9047;"
        self.anchor_cell.cell_class += " anchor_cell "
        self.height = len(header_col)
        """ Number of content (non header) rows """
        self.width = len(header_row)
        """ Number of content (non header) columns """
        if content_cells:
            assert len(content_cells) == self.height and len(content_cells[0]) == self.width \
                                        and all(len(content_cells[0]) == len(row) for row in content_cells)
            self.content_cells = content_cells
        else:
            self.content_cells = [[Cell() for i in range(self.width)] for j in range(self.height)]

    def __str__(self) -> str:
        html = """
        <table class="table">
            <thead>
        """
        html += " ".join(str(cell) for cell in [self.format_anchor_cell()] + self.header_row)
        html += """
            </thead>
            <tbody>
        """
        for (hcell, row) in zip(self.header_col, self.content_cells):
            html += "\t\t\t<tr>{}</tr>\n".format(" ".join(str(cell) for cell in [hcell] + row))
        html += """
            </tbody>
        </table>
        """
        return html

    def html(self):
        return str(self)

    def format_anchor_cell(self) -> 'Cell':
        formats = [{
            "ending": ".tex",
            "mime": "application/x-latex",
            "descr": "Latex table",
            "code": self.latex()
         }, {
            "ending": ".tex",
            "mime": "application/x-latex",
            "descr": "Latex table with surrounding article environment",
            "code": self.latex(True)
         }, {
            "ending": ".csv",
            "mime": "text/csv",
            "descr": "CSV table",
            "code": self.csv()
        }]
        html = """
            <div class='list-group'>
        """
        for d in formats:
            id = self.parent._random_html_id()

            self.parent.app_html += """
                <pre id="{}" style="display: none;">
                    {}
                </pre>
            """.format(id, d["code"])
            html += """
                  <div onclick='download(this)' code_id='{id}' mime='{mime}'
                        filename='{filename}'class='list-group-item'
                        style='cursor: pointer'>
                    {descr}
                  </div>
            """.format(descr=d["descr"], id=id, filename="table" + d["ending"], mime=d["mime"])
        html += """
            </div>
        """
        self.anchor_cell.popover = Popover("Get this table in your favorite format", content=html,
                                           trigger="hover click")
        return self.anchor_cell

    def latex(self, with_env: bool = False) -> str:
        tex = ""
        tex_end = ""
        if with_env:
            tex = """
\\documentclass[10pt,a4paper]{article}
\\begin{document}
            """
            tex_end = """
\\end{document}
"""
        tex += """
    \\begin{{tabular}}{{l|{cs}}}
        """.format(cs="".join("r" * self.width))
        tex_end = """
    \\end{tabular}
        """ + tex_end
        tex += " & ".join(cell.content for cell in [self.orig_anchor_cell] + self.header_row) + "\\\\ \n \\hline "
        for (hcell, row) in zip(self.header_col, self.content_cells):
            tex += " & ".join(cell.content.replace("%", "\\%") for cell in [hcell] + row) + "\\\\ \n"
        return tex + tex_end

    def csv(self) -> str:
        rows = []
        rows.append(",".join(repr(cell.content) for cell in [self.orig_anchor_cell] + self.header_row))

        def convert_content(text: str) -> str:
            if text.endswith("%"):
                return str(float(text[:-1]) / 100)
            try:
                float(text)
                return text
            except:
                return repr(text)

        for (hcell, row) in zip(self.header_col, self.content_cells):
            rows.append(",".join(convert_content(cell.content) for cell in [hcell] + row))
        return "\n".join(rows)

    def __getitem__(self, cell_pos: t.Tuple[int, int]) -> 'Cell':
        return self.content_cells[cell_pos[0]][cell_pos[1]]

    def __setitem__(self, cell_pos: t.Tuple[int, int], new_val: 'Cell'):
        self.content_cells[cell_pos[0]][cell_pos[1]] = new_val

    def append(self, header: 'Cell', content_row: t.List['Cell']):
        assert len(content_row) == self.width
        self.content_cells.append(content_row)
        self.header_col.append(header)

    @classmethod
    def from_content_func(cls, parent: HTMLReporter2, rows: t.List[T1], cols: t.List[T2], anchor_cell: 'Cell',
                          content_func: t.Callable[[T1, T2], Any],
                          content_modal_func: t.Callable[[T1, T2, int, int], str] = None,
                          header_modal_func: t.Callable[[t.Union[T1, T2], int, bool], str] = None,
                          content_popover_func: t.Callable[[T1, T2, int, int], t.Optional[Popover]] = None,
                          header_popover_func: t.Callable[[t.Union[T1, T2], int, bool], t.Optional[Popover]] = None,
                          content_link_func: t.Callable[[T1, T2, int, int], t.Optional[str]] = None,
                          header_link_func: t.Callable[[t.Union[T1, T2], int, bool], t.Optional[str]] = None,
                          content_color_obj_func: t.Callable[[T1, T2, int, int], t.Optional[BaseStatObject]] = None,
                          header_color_obj_func: t.Callable[[t.Union[T1, T2], int, bool],
                                                            t.Optional[BaseStatObject]] = None,
                          header_content_func: t.Callable[[t.Union[T1, T2], int, bool], str] = None):
        """
        Idea: Table that populates itself with a passed content function.
        """
        def convert_hc(elem: t.Union[T1, T2], index: int, header_row: bool) -> Cell:
            def call(func: t.Optional[t.Callable[[t.Union[T1, T2], int, bool], t.T]]) -> t.T:
                if func:
                    return func(elem, index, header_row)
                return None
            content = ""
            color_obj = None
            if header_content_func:
                content = str(header_content_func(elem, index, header_row))
            elif isinstance(elem, str) or isinstance(elem, int) or isinstance(elem, float):
                content = str(elem)
            elif isinstance(elem, BaseStatObject):
                content = parent._obj_description(elem)
            else:
                assert False
            if isinstance(elem, BaseStatObject):
                color_obj = elem
            if header_color_obj_func:
                color_obj = header_color_obj_func(elem, index, header_row)
            modal_id = call(header_modal_func)
            popover = call(header_popover_func)
            link = None
            if header_link_func and header_link_func(elem, index, header_row):
                assert not modal_id # modal and link can't be used together in the same cell
                link = header_link_func(elem, index, header_row)
            return Cell(content, popover=popover, modal_id=modal_id, color_class_obj=color_obj, is_header_cell=True,
                        cell_scope="row" if header_row else None, link=link)
        header_row = []
        for (i, elem) in enumerate(cols):
            header_row.append(convert_hc(elem, i, header_row=True))
        header_col = []
        for (i, elem) in enumerate(rows):
            header_col.append(convert_hc(elem, i, header_row=False))

        def convert_cc(row_header: T1, col_header: T2, row: int, col: int) -> Cell:
            def call(func: t.Optional[t.Callable[[T1, T2, int, int], t.T]]) -> t.T:
                if func:
                    return func(row_header, col_header, row, col)
                return None

            content = str(content_func(row_header, col_header, row, col))
            color_obj = call(content_color_obj_func)
            modal_id = call(content_modal_func)
            popover = call(content_popover_func)
            link = call(content_link_func)
            assert None in [link, modal_id]
            return Cell(content, popover=popover, modal_id=modal_id, color_class_obj=color_obj, link=link)
        content_cells = []
        for (row, row_header) in enumerate(rows):
            a = []
            for (col, col_header) in enumerate(cols):
                a.append(convert_cc(row_header, col_header, row, col))
            content_cells.append(a)
        return Table(parent, header_row, header_col, anchor_cell, content_cells)

