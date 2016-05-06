"""
Benchmarks game inspired comparison of different implementations for a given language.

It doesn't really belong directly to the temci tool, but uses big parts of it.
It's currently in a pre alpha state as it's a part of the evaluation for my bachelor thesis
that I'm currently doing,
"""

import temci.utils.util as util

if __name__ == "__main__":
    util.allow_all_imports = True

import logging, time
import typing as t
import inspect

import multiprocessing

import zlib
from collections import defaultdict
from enum import Enum

from temci.report.testers import Tester, TTester, TesterRegistry

START_TIME = time.time()

import subprocess

import itertools

from temci.report.rundata import RunData

from temci.report.stats import SingleProperty, Single, SinglesProperty
from temci.utils.typecheck import *
import os, shutil, copy
from pprint import pprint
from temci.report import report
import scipy as sp
import  scipy.stats as stats

from temci.utils.util import InsertionTimeOrderedDict, geom_std

itod_from_list = InsertionTimeOrderedDict.from_list

if util.can_import("scipy"):
    import scipy.stats as stats
    #import ruamel.yaml as yaml
try:
    import yaml
except ImportError:
    import pureyaml as yaml

from temci.report.report import HTMLReporter2, html_escape_property
from temci.utils.settings import Settings
Settings().load_files()

USABLE_WITH_SERVER = True
FIG_WIDTH = 15
FIG_HEIGHT_PER_ELEMENT = 1.5

class Mode(Enum):
    geom_mean_rel_to_best = 1
    """ calculate all mean scores as "mean / best mean" and use the geometric mean for summaries"""
    mean_rel_to_first = 2
    """ calculate all mean scores as "mean / mean of first" and use the arithmetic mean for summaries"""
    mean_rel_to_one = 3
    """ calculate all mean scores as "mean / 1" and use the arithmetic mean for summaries"""

CALC_MODE = Mode.geom_mean_rel_to_best # type: Mode


def amean_std(values: t.List[float]) -> float:
    """
    Calculates the arithmetic mean.
    """
    return sp.std(values)


def used_summarize_mean(values: t.List[float]) -> float:
    if CALC_MODE in [Mode.geom_mean_rel_to_best, Mode.mean_rel_to_one]:
        return stats.gmean(values)
    elif CALC_MODE in [Mode.mean_rel_to_first]:
        return sp.mean(values)
    assert False


def used_summarize_mean_std(values: t.List[float]) -> float:
    if CALC_MODE in [Mode.geom_mean_rel_to_best, Mode.mean_rel_to_one]:
        return geom_std(values)
    elif CALC_MODE in [Mode.mean_rel_to_first]:
        return amean_std(values)
    assert False


StatProperty = t.Callable[[SingleProperty, t.List[float], t.List[SingleProperty], int], float]
""" Gets passed a SingleProperty object, the list of means (containing the object's mean),
 the list of all SingleProperty objects and the index of the first in it and returns a float. """
ReduceFunc = t.Callable[[t.List[float]], Any]
""" Gets passed a list of values and returns a single value, e.g. stats.gmean """

def first(values: t.List[float]) -> float:
    return values[0]

def rel_mean_property(single: SingleProperty, means: t.List[float], *args) -> float:
    """
    A property function that returns the relative mean (the mean of the single / minimum of means)
    """
    return single.mean() / min(means)

def rel_std_property(single: SingleProperty, means: t.List[float], *args) -> float:
    """
    A property function that returns the relative standard deviation (relative to single's mean)
    """
    return single.std_dev_per_mean()


def used_rel_mean_property(single: SingleProperty, means: t.List[float], *args) -> float:
    if CALC_MODE == Mode.geom_mean_rel_to_best:
        return single.mean() / min(means)
    elif CALC_MODE == Mode.mean_rel_to_first:
        return single.mean() / means[0]
    elif CALC_MODE == Mode.mean_rel_to_one:
        return single.mean()
    assert False


def used_std_property(single: SingleProperty, means: t.List[float], *args) -> float:
    if CALC_MODE in [Mode.geom_mean_rel_to_best, Mode.mean_rel_to_first, Mode.mean_rel_to_one]:
        return single.std_dev_per_mean()
    assert False

alpha = 0.05
tester = TesterRegistry.get_for_name("t", [alpha, 2 * alpha])

def ttest_rel_to_first_property(single: SingleProperty, _, all_singles: t.List[SingleProperty], index: int) -> float:
    if index == 0:
        return float("nan")
    return tester.test(single.data, all_singles[0].data)

def ttest_summarize(values: t.List[float]) -> float:
    not_nans = [val for val in values if val == val]
    if len(not_nans) == 0:
        return float("nan")
    return sum(val < alpha for val in not_nans) / len(not_nans)

class BOTableColumn:
    """ Column for BaseObject table_html_for_vals_per_impl  """

    def __init__(self, title: str, format_str: str, property: StatProperty, reduce: ReduceFunc):
        self.title = title
        self.format_str = format_str
        self.property = property
        self.reduce = reduce

mean_score_column = lambda: BOTableColumn({
    Mode.geom_mean_rel_to_best: "mean score (gmean(mean / best mean))",
    Mode.mean_rel_to_first: "mean score (gmean(mean / mean of first impl))",
    Mode.mean_rel_to_one: "mean score (mean(mean / 1))"
}[CALC_MODE], "{:5.1%}", used_rel_mean_property, used_summarize_mean)
mean_score_std_column = lambda: BOTableColumn({
    Mode.geom_mean_rel_to_best: "mean score std (gmean std(mean / best mean))",
    Mode.mean_rel_to_first: "mean score std (gmean std(mean / mean of first impl))",
    Mode.mean_rel_to_one: "mean score std (std(mean / 1))"
}[CALC_MODE], "{:5.1%}", used_rel_mean_property, used_summarize_mean_std)
mean_rel_std = lambda: BOTableColumn({
    Mode.geom_mean_rel_to_best: "mean rel std (gmean(std / mean))",
    Mode.mean_rel_to_first: "mean rel std (gmean(std / mean))",
    Mode.mean_rel_to_one: "mean rel std (mean(std / mean))"
}[CALC_MODE], "{:5.1%}", used_std_property, used_summarize_mean)
ttest_to_first = lambda: BOTableColumn("t test: this != first", "{:5.1%}", ttest_rel_to_first_property, ttest_summarize)

common_columns = [mean_score_column, mean_score_std_column, mean_rel_std, ttest_to_first]

#MeanBOTableColumn = BOTableColumn("")



class BaseObject:
    """
    A base class for all other classes that provides helper methods.
    """

    def __init__(self, name: str, children: t.Union[t.Dict[str, 'BaseObject'], InsertionTimeOrderedDict] = None):
        self.name = name
        self.children = children or InsertionTimeOrderedDict()  # type: t.Dict[str, 'BaseObject']

    def _create_dir(self, dir: str):
        """
        ... and delete all contents if the directory all ready exists.
        """
        if os.path.exists(dir):
            shutil.rmtree(dir)
        os.mkdir(dir)

    def _create_own_dir(self, base_dir: str) -> str:
        dir = os.path.realpath(os.path.join(base_dir, self.name))
        self._create_dir(dir)
        return dir

    def _process_build_obj(self, arg: t.Tuple[str, 'BaseObject']):
        path, obj = arg
        tmp = obj.build(path)
        if isinstance(tmp, list):
            return tmp
        else:
            return [tmp]

    def _buildup_dict(self, path: str,
                      base_objs: t.Dict[str, 'BaseObject'],
                      multiprocess: bool = False) -> t.List[dict]:
        objs = []
        for key in base_objs:
            objs.append((path, base_objs[key]))
        map_func = map
        if multiprocess:
            pool = multiprocessing.Pool()
            map_func = pool.map
        ret_fts = map_func(self._process_build_obj, objs)
        ret = []
        for elem in ret_fts:
            ret.extend(elem)
        return ret

    def build(self, base_dir: str) -> t.List[dict]:
        pass

    @classmethod
    def from_config_dict(cls, *args) -> 'BaseObject':
        pass

    def boxplot_html(self, base_file_name: str, singles: t.List[SingleProperty]) -> str:
        sp = SinglesProperty(singles, self.name)
        sp.boxplot(FIG_WIDTH, max(len(singles) * FIG_HEIGHT_PER_ELEMENT, 6))
        d = sp.store_figure(base_file_name, fig_width=FIG_WIDTH, fig_height=max(len(singles) * FIG_HEIGHT_PER_ELEMENT, 4),
                            pdf=False)
        html = """
        <center>
        <img src="{}{}"/>
        </center>
        <p>
        """.format("" if USABLE_WITH_SERVER else "file:", d["img"].split("/")[-1])
        for format in sorted(d):
            html += """
            <a href="{}{}">{}</a>
            """.format("" if USABLE_WITH_SERVER else "file:", d[format].split("/")[-1], format)
        return html + "</p>"

    def boxplot_html_for_data(self, name: str, base_file_name: str, data: t.Dict[str, t.List[float]]):
        singles = []
        for var in data:
            run_data = RunData({name: data[var]}, {"description": str(var)})
            singles.append(SingleProperty(Single(run_data), run_data, name))
        return self.boxplot_html(base_file_name, singles)

    def get_x_per_impl(self, property: StatProperty) -> t.Dict[str, t.List[float]]:
        """
        Returns a list of [property] for each implementation.

        :param property: property function that gets a SingleProperty object and a list of all means and returns a float
        """
        assert len(self.children) != 0
        means = InsertionTimeOrderedDict()  # type: t.Dict[str, t.List[float]]
        for c in self.children:
            child = self.children[c]  # type: BaseObject
            child_means = child.get_x_per_impl(property)
            for impl in child_means:
                if impl not in means:
                    means[impl] = []
                means[impl].extend(child_means[impl])
        typecheck(means._dict, Dict(key_type=Str(), value_type=List(Float()|Int()), all_keys=False))
        return means

    def get_reduced_x_per_impl(self, property: StatProperty, reduce: ReduceFunc,
                               x_per_impl_func: t.Callable[[StatProperty], t.Dict[str, t.List[float]]] = None) \
            -> t.Dict[str, float]:
        """
        Returns the reduced [property] for each implementation. To reduce the list of [property] it uses
        the passed reduce function.
        The returned implementations doesn't depend on one of the parameters.
        """
        ret = InsertionTimeOrderedDict()
        x_per_impl_func = x_per_impl_func or self.get_x_per_impl
        rel_means = x_per_impl_func(property)
        for impl in rel_means:
            ret[impl] = reduce(rel_means[impl])
        typecheck(ret._dict, Dict(key_type=Str(), value_type=Int()|Float(), all_keys=False))
        return ret

    def get_gsd_for_x_per_impl(self, property: StatProperty) -> t.Dict[str, float]:
        """
        Calculates the geometric standard deviation for the property for each implementation.
        """
        return self.get_reduced_x_per_impl(property, geom_std)

    def get_geom_over_rel_means(self) -> t.Dict[str, float]:
        return self.get_reduced_x_per_impl(used_rel_mean_property, stats.gmean)

    def get_geom_std_over_rel_means(self) -> t.Dict[str, float]:
        return self.get_gsd_for_x_per_impl(used_rel_mean_property)

    def get_geom_over_rel_stds(self) -> t.Dict[str, float]:
        return self.get_reduced_x_per_impl(rel_std_property, stats.gmean)

    def table_html_for_vals_per_impl(self, columns: t.List[t.Union[BOTableColumn, t.Callable[[], BOTableColumn]]],
                                     base_file_name: str,
                                     x_per_impl_func: t.Callable[[StatProperty], t.Dict[str, t.List[float]]] = None) \
            -> str:
        """
        Returns the html for a table that has a row for each implementation and several columns (the first is the
        implementation column).
        """
        columns = [col() if not isinstance(col, BOTableColumn) else col for col in columns]
        tex = """
        \\begin{{tabular}}{{l{cs}}}\\toprule
           & {header} \\\\ \\midrule
        """.format(cs="".join("r" * len(columns)), header=" & ".join(col.title for col in columns))
        html = """
        <table class="table">
            <tr><th></th>{header}</tr>
        """.format(header="".join("<th>{}</th>".format(col.title) for col in columns))
        cells = [["", ]]
        for col in columns:
            cells[0].append(col.title)
        values = InsertionTimeOrderedDict() # t.Dict[t.List[str]]
        for (i, col) in enumerate(columns):
            xes = self.get_reduced_x_per_impl(col.property, col.reduce, x_per_impl_func)
            for (j, impl) in enumerate(xes):
                if impl not in values:
                    values[impl] = []
                values[impl].append(col.format_str.format(xes[impl]))
                if j + 1 >= len(cells):
                    cells.append([repr(impl)])
                cells[j + 1].append(repr(col.format_str.format(xes[impl])))
        for impl in values:
            html += """
                <tr><td scope="row">{}</td>{}</tr>
            """.format(impl, "".join("<td>{}</td>".format(val) for val in values[impl]))
            tex += """
                {} & {} \\\\
            """.format(impl, " & ".join(str(val).replace("%", "\\%") for val in values[impl]))
        html += """
        </table>
        """
        tex += """
                \\bottomrule
            \\end{tabular}
                """
        with open(base_file_name + ".csv", "w") as f:
            f.write("\n".join(",".join(val for val in row) for row in cells))
        with open(base_file_name + ".tex", "w") as f:
            f.write(tex)
        html += """
            <a href="{base}{csv}.csv">csv</a><a href="{base}{csv}.tex">tex</a><br/>
        """.format(base="" if USABLE_WITH_SERVER else "file:", csv=base_file_name.split("/")[-1])

        return html


class Implementation(BaseObject):
    """
    Represents an implementation of a program.
    """

    def __init__(self, parent: 'ProgramWithInput', name: str, run_cmd: str,
                 build_cmd: str = None, run_data: t.List[t.Union[int, float]] = None):
        super().__init__(name)
        typecheck_locals(parent=T(ProgramWithInput))
        self.parent = parent
        self.run_cmd = run_cmd
        self.build_cmd = build_cmd
        self.run_data = run_data # t.List[float]

    def get_single_property(self) -> SingleProperty:
        assert self.run_data is not None
        data = RunData({self.name: self.run_data})
        return SingleProperty(Single(RunData({self.name: self.run_data})), data, self.name)

    @classmethod
    def from_config_dict(cls, parent: 'ProgramWithInput', config: dict) -> 'Implementation':
        typecheck(config, Dict({
            "name": Str(),
            "run_cmd": Str(),
            "build_cmd": Str() | NonExistent()
        }))
        return cls(parent, **config)

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        d = {
            "input": self.parent.input,
            "file": self.parent.parent.file,
            "bfile": os.path.basename(self.parent.parent.file),
            "program": self.parent.parent.name,
            "impl": self.name,
            "impl_escaped": html_escape_property(self.name),
            "category": self.parent.parent.parent.name
        }
        run_cmd = self.run_cmd.format(**d)
        if self.parent.parent.file is not None:
            shutil.copy(self.parent.parent.file, os.path.join(path, os.path.basename(self.parent.parent.file)))
        for copied_file in self.parent.parent.copied_files:
            p = os.path.join(path, copied_file)
            if os.path.isdir(copied_file):
                shutil.copytree(copied_file, p)
            else:
                shutil.copy(copied_file, p)
        if self.build_cmd:
            build_cmd = self.build_cmd.format(**d)
            #pprint(build_cmd)
            proc = subprocess.Popen(["/bin/sh", "-c", build_cmd], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        cwd=path)
            out, err = proc.communicate()
            logging.info(out)
            if proc.poll() > 0:
                logging.error("Error while executing {}: {}".format(build_cmd, err))
                exit(1)
        prog_in = self.parent
        prog = prog_in.parent
        category = prog.parent
        lang = category.parent
        logging.info(path)
        return {
            "attributes": {
                "language": lang.name,
                "category": category.name,
                "program": prog.name,
                "impl": self.name,
                "input": str(prog_in.input)
            },
            "run_config": {
                "run_cmd": run_cmd,
                "cwd": path
            }
        }

    def get_x_per_impl(self, property: StatProperty):
        raise NotImplementedError()

    def mean(self) -> float:
        return sp.mean(self.run_data)

class Input:
    """
    Input with a variable numeric part.
    """

    def __init__(self, prefix: str = None, number: t.Union[int, float] = None, appendix: str = None):
        self.prefix = prefix or ""
        self.number = number
        self.appendix = appendix or ""

    def __mul__(self, other: t.Union[int, float]) -> 'Input':
        typecheck_locals(other=Int() | Float())
        return Input(self.prefix, None if self.number is None else self.number * other, self.appendix)

    def __floordiv__(self, other: t.Union[int, float]) -> 'Input':
        typecheck_locals(other=Int() | Float())
        return Input(self.prefix, None if self.number is None else self.number * other, self.appendix)

    def __str__(self):
        return self.prefix + str(self.number or "") + self.appendix

    def __repr__(self):
        return repr(str(self))

    def replace(self, search: str, replacement: str) -> 'Input':
        """
        Returns an input object in which the search string is replaced in the prefix and the appendix.
        """
        return Input(self.prefix.replace(search, replacement), self.number, self.appendix.replace(search, replacement))

    @classmethod
    def from_config_dict(cls, config: dict) -> 'Input':
        typecheck_locals(config=Dict({
            "prefix": Str() | NonExistent(),
            "number": Int() | Float() | NonExistent(),
            "appendix": Str() | NonExistent()
        }))
        return Input(**config)

    @classmethod
    def list_from_numbers(cls, *numbers: t.List[t.Union[int, float]]) -> t.List['Input']:
        return [Input(number=number) for number in numbers]

    def to_dict(self) -> dict:
        ret = {}
        if self.prefix != "":
            ret["prefix"] = self.prefix
        if self.number is not None:
            ret["number"] = self.number
        if self.appendix != "":
            ret["appendix"] = self.appendix
        return ret

    def __hash__(self, *args, **kwargs):
        return str(self).__hash__(*args, **kwargs)


StatisticalPropertyFunc = t.Callable[[SingleProperty], float]
""" Get's passed the SingleProperty object to process and min mean """

rel_mean_func = lambda x, min: x.mean() / min

def rel_std_dev_func(x: SingleProperty, min: float) -> float:
    return x.std_dev_per_mean()

def rel_std_dev_to_min_func(x: SingleProperty, min: float) -> float:
    return x.std_dev() / min


class ProgramWithInput(BaseObject):
    """
    This represents the program with a specific input. It has several program implementations.
    """

    def __init__(self, parent: 'Program', input: Input, impls: t.List[Implementation], id: int):
        super().__init__(str(id), itod_from_list(impls, lambda x: x.name))
        self.parent = parent
        self.input = input
        self.impls = self.children # type: t.Dict[str, Implementation]

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.impls)

    def __getitem__(self, name: str) -> Implementation:
        return self.impls[name]

    def __setitem__(self, key: str, value: Implementation):
        self.impls[key] = value
        self.children[key] = value

    def get_single(self):
        data = InsertionTimeOrderedDict()
        for impl in self.impls:
            data[impl] = self.impls[impl]
        return Single(RunData(data))

    def get_single_properties(self) -> t.List[t.Tuple[str, SingleProperty]]:
        return [(impl, self.impls[impl].get_single_property()) for impl in self.impls]

    def get_means_rel_to_best(self) -> t.Dict[str, float]:
        return self.get_statistical_properties_for_each(rel_mean_func)

    def get_statistical_properties_for_each(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        sps = self.get_single_properties()
        means = [sp.mean() for (impl, sp) in sps]
        d = InsertionTimeOrderedDict()
        for (impl, sp) in sps:
            d[impl] = func(sp, means)
        return d

    def get_box_plot_html(self, base_file_name: str) -> str:
        singles = []
        for impl in self.impls:
            impl_val = self.impls[impl]
            data = RunData({self.name: impl_val.run_data}, {"description": "{!r}|{}".format(self.input, impl)})
            singles.append(SingleProperty(Single(data), data, self.name))
        return self.boxplot_html(base_file_name, singles)

    def get_html2(self, base_file_name: str, h_level: int) -> str:
        return self.get_html(base_file_name, h_level)

    def get_html(self, base_file_name: str, h_level: int) -> str:
        sp = None # type: SingleProperty
        columns = [
            BOTableColumn("n", "{:5d}", lambda sp, _: sp.observations(), first),
            BOTableColumn("mean", "{:10.5f}", lambda sp, _: sp.mean(), first),
            BOTableColumn("mean / best mean", "{:5.5%}", lambda sp, means: sp.mean() / min(means), first),
            BOTableColumn("mean / mean of first impl", "{:5.5%}", lambda sp, means: sp.mean() / means[0], first),
            BOTableColumn("std / mean", "{:5.5%}", lambda sp, _: sp.std_dev_per_mean(), first),
            BOTableColumn("std / best mean", "{:5.5%}", lambda sp, means: sp.std_dev() / min(means), first),
            BOTableColumn("std / mean of first impl", "{:5.5%}", lambda sp, means: sp.std_dev() / means[0], first),
            BOTableColumn("median", "{:5.5f}", lambda sp, _: sp.median(), first)
        ]
        html = """
        <h{h}>Input: {input}</h{h}>
        The following plot shows the actual distribution of the measurements for each implementation.
        {box_plot}
        """.format(h=h_level, input=repr(self.input), box_plot=self.get_box_plot_html(base_file_name))
        html += self.table_html_for_vals_per_impl(columns, base_file_name)
        return html

    def get_x_per_impl(self, property: StatProperty) -> t.Dict[str, t.List[float]]:
        """
        Returns a list of [property] for each implementation.

        :param property: property function that gets a SingleProperty object and a list of all means and returns a float
        """
        means = [x.mean() for x in self.impls.values()]  # type: t.List[float]
        singles = [x.get_single_property() for x in self.impls.values()]
        ret = InsertionTimeOrderedDict() # t.Dict[str, t.List[float]]
        property_arg_number = min(len(inspect.signature(property).parameters), 4)
        for (i, impl) in enumerate(self.impls):
            args = [singles[i], means, singles, i]
            ret[impl] = [property(*args[:property_arg_number])]
        #pprint(ret._dict)
        typecheck(ret._dict, Dict(key_type=Str(), value_type=List(Float()|Int()), all_keys=False))
        return ret


class Program(BaseObject):
    """
    A program with several different inputs.
    """

    def __init__(self, parent: 'ProgramCategory', name: str, file: str,
                 prog_inputs: t.List[ProgramWithInput] = None, copied_files: t.List[str] = None):
        super().__init__(name, itod_from_list(prog_inputs, lambda x: x.name))
        self.parent = parent
        self.file = file
        self.prog_inputs = copy.copy(self.children) # type: t.Dict[str, ProgramWithInput]
        self.copied_files = copied_files or [] # type: t.List[str]
        self.line_number = file_lines(self.file)
        self.entropy = file_entropy(self.file)
        """ Entropy of the implementation """

    @classmethod
    def from_config_dict(cls, parent: 'ProgramCategory', config: dict) -> 'Implementation':
        typecheck(config, Dict({
            "program": Str(),
            "file": FileName(allow_non_existent=False),
            "inputs": List(Dict({
                    "prefix": Str() | NonExistent(),
                    "number": Int() | Float() | NonExistent(),
                    "appendix": Str() | NonExistent()
                })) | NonExistent(),
            "copied_files": List(Str()) | NonExistent(),
            "impls": List(Dict(all_keys=False)) | NonExistent()
        }))
        program = cls(parent, name=config["program"], file=config["file"],
                       copied_files=config["copied_files"] if "copied_files" in config else [])
        inputs = config["inputs"] if "inputs" in config else [""]
        for (i, input) in enumerate(inputs):
            input = Input.from_config_dict(input)
            prog_input = ProgramWithInput(program, input, [], i)
            program.prog_inputs[str(input)] = prog_input
            impls = config["impls"] if "impls" in config else []
            prog_input.impls = InsertionTimeOrderedDict()
            for impl_conf in impls:
                impl = Implementation.from_config_dict(prog_input, impl_conf)
                prog_input.impls[impl.name] = impl
        return program

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.prog_inputs)

    def __getitem__(self, input: str) -> ProgramWithInput:
        return self.prog_inputs[input]

    def get_box_plot_html(self, base_file_name: str) -> str:
        return self.boxplot_html_for_data("mean score", base_file_name + "_program" + html_escape_property(self.name),
                                          self.get_statistical_property_scores(rel_mean_func))

    def get_box_plot_per_input_per_impl_html(self, base_file_name: str, input: str) -> str:
        """
        A box plot for each input that shows the execution times for each implementation.
        """
        return self.prog_inputs[input].get_box_plot_html(base_file_name + "__input_"
                                                         + str(list(self.prog_inputs.keys()).index(input)))

    def get_statistical_property_scores_per_input_per_impl(self, func: StatisticalPropertyFunc,
                                                           input: str) -> t.Dict[str, float]:
        return self.prog_inputs[input].get_statistical_properties_for_each(func)

    def get_html2(self, base_file_name: str, h_level: int):
        base_file_name += "__program_" + html_escape_property(self.name)
        html = """
            <h{}>Program: {!r}</h{}>
            The following plot shows the rel means (means / min means) per input distribution for every implementation.
        """.format(h_level, self.name, h_level)
        html += self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(used_rel_mean_property))
        html += self.table_html_for_vals_per_impl(common_columns, base_file_name)
        for (i, input) in enumerate(self.prog_inputs.keys()):
            app = html_escape_property(input)
            if len(app) > 20:
                app = str(i)
            html += self.prog_inputs[input].get_html2(base_file_name + "_" + app, h_level + 1)
        return html

    def get_html(self, base_file_name: str, h_level: int) -> str:
        html = """
            <h{}>Program: {!r} ({} lines, {} entropy)</h{}>
            The following plot shows the mean score per input distribution for every implementation.
        """.format(h_level, self.name, self.line_number, self.entropy, h_level)
        html += self.get_box_plot_html(base_file_name)
        scores = self.get_impl_mean_scores()
        std_devs = self.get_statistical_property_scores(rel_std_dev_func)
        html += """
            <table class="table">
                <tr><th>implementation</th><th>geom mean over means relative to best (per input) aka mean score</th>
                    <th>... std dev rel. to the best mean</th>
                </tr>
        """
        for impl in scores.keys():
            html += """
                <tr><td>{}</td><td>{:5.2%}</td><td>{:5.2%}</td></tr>
            """.format(impl, stats.gmean(scores[impl]), stats.gmean(std_devs[impl]))
        html += "</table>"
        impl_names = list(scores.keys())
        for (i, input) in enumerate(self.prog_inputs.keys()):
            app = html_escape_property(input)
            if len(app) > 20:
                app = str(i)
            html += self.prog_inputs[input].get_html(base_file_name + "_" + app, h_level + 1)
        return html

    def get_impl_mean_scores(self) -> t.Dict[str, t.List[float]]:
        """
        Geometric mean over the means relative to best per implementation (per input).
        """
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc) -> t.Dict[str, t.List[float]]:
        d = InsertionTimeOrderedDict()  # type: t.Dict[str, t.List[float]]
        for input in self.prog_inputs:
            rel_vals = self.prog_inputs[input].get_statistical_properties_for_each(func)
            for impl in rel_vals:
                if impl not in d:
                    d[impl] = []
                d[impl].append(rel_vals[impl])
        return d

    def _get_inputs_that_contain_impl(self, impl: str) -> t.List[ProgramWithInput]:
        return list(filter(lambda x: impl in x.impls, self.prog_inputs.values()))


ProgramFilterFunc = t.Callable[[int, t.List[Program]], bool]
"""
    A function that get's the current program index in the also passed list of all other programs
    and returns True if the program is okay and False otherwise.
"""


def id_program_filter(_1, _2):
        return True


def property_filter_half(cur_index: int, all: t.List[Program], property_func: t.Callable[[Program], float],
                          remove_upper_half: bool) -> bool:
    """
    Note: if the number of programs is uneven, then one program will belong to the upper and the lower half.
    """
    vals = [property_func(p) for p in all]
    cur_val = vals[cur_index]
    median = sp.median(vals)
    if (remove_upper_half and cur_val > median) or (not remove_upper_half and cur_val < median):
        return False
    return True


class ProgramCategory(BaseObject):
    """
    Represents a specific abstract program that gives the specification for several implementations (aka "program"s).
    """

    def __init__(self, parent: 'Language', name: str, programs: t.List[Program]):
        super().__init__(name, itod_from_list(programs, lambda x: x.name))
        self.parent = parent
        self.programs = self.children # type: t.Dict[str, Program]
        self._programs = copy.copy(self.children) # type: t.Dict[str, Program]

    @classmethod
    def from_config_dict(cls, parent: 'Language', config: dict) -> 'ProgramCategory':
        typecheck(config, Dict({
            "category": Str(),
            "programs": List(Dict(all_keys=False))
        }))
        cat = cls(parent, config["category"], [])
        cat.programs = InsertionTimeOrderedDict()
        cat._programs = InsertionTimeOrderedDict()
        for prog_conf in config["programs"]:
            prog = Program.from_config_dict(cat, prog_conf)
            cat.programs[prog.name] = prog
            cat.children[prog.name] = prog
            cat._programs[prog.name] = prog
        return cat

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.programs)

    def apply_program_filter(self, filter: ProgramFilterFunc = id_program_filter):
        """
        Filters the programs that make up self.children and self.programs.
        It stores the original set of programs else where.

        :param filter: the used filter, the id filter resets the original state
        """
        self.children = InsertionTimeOrderedDict()
        prog_list = self._programs.values()
        for (i, prog) in enumerate(self._programs):
            if filter(i, prog_list):
                self.children[prog] = self._programs[prog]
        self.programs = self.children

    def __getitem__(self, name: str) -> Program:
        return self.programs[name]

    def get_box_plot_html(self, base_file_name: str) -> str: # a box plot over the mean scores per sub program
        scores_per_impl = self.get_scores_per_impl()
        singles = []
        for impl in scores_per_impl:
            scores = scores_per_impl[impl]
            name = "mean score"
            data = RunData({name: scores}, {"description": impl})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name, singles)

    def get_html2(self, base_file_name: str, h_level: int):
        base_file_name += "__cat_" + html_escape_property(self.name)
        html = """
            <h{}>{}</h{}>
        """.format(h_level, self.name, h_level)
        if len(self.children) > 1:
            html += self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(used_rel_mean_property))
            html += self.table_html_for_vals_per_impl(common_columns, base_file_name)
            if len(self.get_input_strs()) > 1:
                html += """
                <h{h}> Mean scores per input</h{h}>
                """.format(h=h_level + 1)
                for input in self.get_input_strs():
                    html += """
                        <h{h}>Mean scores for input {!r}</h{h}>
                        The plot shows the distribution of mean scores per program for each implementation.
                        <p>
                    """.format(input, h=h_level + 2)
                    file_name = base_file_name + "__input_" + html_escape_property(input)
                    html += self.boxplot_html_for_data("mean score", file_name,
                                          self.get_x_per_impl_and_input(used_rel_mean_property, input))
                    html += self.table_html_for_vals_per_impl(common_columns, file_name,
                                                              lambda property: self.get_x_per_impl_and_input(property,                                                                                       input))
        for (i, prog) in enumerate(self.programs):
            html += self.programs[prog].get_html2(base_file_name + "_" + html_escape_property(prog), h_level + 1)
        return html

    def get_html(self, base_file_name: str, h_level: int) -> str:
        html = """
            <h{}>{}</h{}>
        """.format(h_level, self.name, h_level)
        scores = self.get_impl_mean_scores()
        std_devs = self.get_statistical_property_scores(rel_std_dev_func)
        if len(self.programs) > 1:
            html += """
                Mean scores per implementation for this program category
                <p>
            """
            html += self.get_box_plot_html(base_file_name)
            html += """
                </p>
                <table class="table">
                    <tr><th>implementation</th><th>geom mean over means relative to best (per input and program) aka mean score</th>
                    <th>... std devs relative to the best means </th>
                    </tr>
            """
            for impl in scores.keys():
                html += """
                    <tr><td>{}</td><td>{:5.2%}</td><td>{:5.2%}</td></tr>
                """.format(impl, scores[impl], std_devs[impl])
            html += "</table>"
            if len(self.get_input_strs()) > 1:
                html += """
                <h{h}> Mean scores per input</h{h}>
                """.format(h=h_level + 1)
                for input in self.get_input_strs():
                    mean_scores = self.get_statistical_property_scores_per_input_per_impl(rel_mean_func, input)
                    std_scores = self.get_statistical_property_scores_per_input_per_impl(rel_std_dev_func, input)
                    html += """
                        <h{h}>Mean scores for input {!r}</h{h}>
                        The plot shows the distribution of mean scores per program for each implementation.
                        <p>
                    """.format(input, h=h_level + 2)
                    html += self.get_box_plot_per_input_per_impl_html(base_file_name, input)
                    html += """
                        </p>
                        <table class="table">
                            <tr><th>impl</th><th>geom mean over means relative to best (per program) aka mean score</th>
                            <th>... std devs relative to the best means </th>
                            </tr>
                    """
                    for impl in mean_scores.keys():
                        html += """
                            <tr><td>{}</td><td>{:5.2%}</td><td>{:5.2%}</td></tr>
                        """.format(impl, stats.gmean(mean_scores[impl]), stats.gmean(std_scores[impl]))
                    html += "</table>"
        impl_names = list(scores.keys())
        for (i, prog) in enumerate(self.programs):
            html += self.programs[prog].get_html(base_file_name + "_" + html_escape_property(prog), h_level + 1)
        return html

    def get_scores_per_impl(self) -> t.Dict[str, t.List[float]]:
        return self.get_statistical_property_scores_per_impl(rel_mean_func)

    def get_statistical_property_scores_per_impl(self, func: StatisticalPropertyFunc,
                                                 reduce: ReduceFunc = stats.gmean) -> t.Dict[str, float]:
        impl_scores = InsertionTimeOrderedDict()
        for prog in self.programs:
            scores = self.programs[prog].get_statistical_property_scores(func)
            for impl in scores:
                if impl not in impl_scores:
                    impl_scores[impl] = []
                impl_scores[impl].append(reduce(scores[impl]))
        return impl_scores

    def get_impl_mean_scores(self) -> t.Dict[str, float]:
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc,
                                        reduce: ReduceFunc = stats.gmean) -> t.Dict[str, float]:
        ret = InsertionTimeOrderedDict()
        scores_per_impl = self.get_statistical_property_scores_per_impl(func)
        for impl in scores_per_impl:
            ret[impl] = reduce(scores_per_impl[impl])
        return ret

    def get_box_plot_per_input_per_impl_html(self, base_file_name: str, input: str) -> str:
        """
        A box plot for each input that shows the mean scores (over all programs) for each implementation.
        """
        return self.boxplot_html_for_data("mean score", base_file_name + "__input_" + html_escape_property(input),
                                          self.get_statistical_property_scores_per_input_per_impl(rel_mean_func, input))

    def get_statistical_property_scores_per_input_per_impl(self, func: StatisticalPropertyFunc, input: str)\
            -> t.Dict[str, t.List[float]]:
        scores_per_impl = InsertionTimeOrderedDict()
        for prog in self.programs:
            prog_val = self.programs[prog]
            scores = prog_val.get_statistical_property_scores_per_input_per_impl(func, input)
            for impl in scores:
                if impl not in scores_per_impl:
                    scores_per_impl[impl] = []
                scores_per_impl[impl].append(scores[impl])
        return scores_per_impl

    def get_x_per_impl_and_input(self, property: StatProperty, input: str) -> t.Dict[str, t.List[float]]:
        scores_per_impl = InsertionTimeOrderedDict()
        for prog in self.programs:
            prog_val = self.programs[prog]
            scores = prog_val.prog_inputs[input].get_x_per_impl(property)
            #pprint(scores._dict)
            for impl in scores:
                if impl not in scores_per_impl:
                    scores_per_impl[impl] = []
                scores_per_impl[impl].extend(scores[impl])
        typecheck(scores_per_impl._dict, Dict(key_type=Str(), value_type=List(Float()|Int()), all_keys=False))
        return scores_per_impl

    def get_input_strs(self) -> t.List[str]:
        return list(self.programs.values())[0].prog_inputs.keys()


class Language(BaseObject):

    def __init__(self, name: str, categories: t.List[ProgramCategory]):
        super().__init__(name, itod_from_list(categories, lambda x: x.name))
        self.categories = self.children  # type: t.Dict[str, ProgramCategory]

    @classmethod
    def from_config_dict(cls, config: dict) -> 'Language':
        typecheck(config, Dict({
            "language": Str(),
            "categories": List(Dict(all_keys=False)),
            "impls": List(Dict({"name": Str()}, all_keys=False)) | NonExistent()
        }))
        lang = cls(config["language"], [])
        lang.categories = InsertionTimeOrderedDict()
        for cat_conf in config["categories"]:
            cat = ProgramCategory.from_config_dict(lang, cat_conf)
            lang.categories[cat.name] = cat
            lang.children[cat.name] = cat
        if "impls" in config:
            for cat in lang.categories:
                cat_val = lang.categories[cat]
                for prog in cat_val.programs:
                    prog_val = cat_val.programs[prog]
                    for p_in in prog_val.prog_inputs:
                        p_in_val = prog_val.prog_inputs[p_in]
                        for impl_conf in config["impls"]:
                            name = impl_conf["name"]
                            if name not in p_in_val.impls:
                                p_in_val[name] = Implementation.from_config_dict(p_in_val, impl_conf)
        return lang

    def set_run_data_from_result_dict(self, run_datas: t.List[t.Dict[str, t.Any]], property: str = "task-clock"):
        for run_data in run_datas:
            attrs = run_data["attributes"]
            typecheck(attrs, Dict({
                "language": E(self.name),
                "category": Str(),
                "program": Str(),
                "impl": Str(),
                "input": Str()
            }))
            try:
                self[attrs["category"]][attrs["program"]][attrs["input"]][attrs["impl"]].run_data = run_data["data"][property]
            except KeyError as err:
                #logging.warning(err)
                pass

    @classmethod
    def merge_different_versions_of_the_same(cls, configs: t.List[dict], config_impl_apps: t.List[str],
                                             group_by_app: bool):
        assert len(configs) == len(config_impl_apps)
        configs = copy.deepcopy(configs)
        typecheck(configs, List(Dict({
            "language": Str(),
            "categories": List(Dict(all_keys=False)),
            "impls": List(Dict({"name": Str()}, all_keys=False)) | NonExistent()
        })))
        first_config = configs[0]
        typecheck(configs, List(Dict({
            "language": E(first_config["language"]),
            "categories": E(first_config["categories"]),
        }, all_keys=False)))
        lang = cls(first_config["language"], [])
        lang.categories = InsertionTimeOrderedDict()
        for cat_conf in first_config["categories"]:
            cat = ProgramCategory.from_config_dict(lang, cat_conf)
            lang.categories[cat.name] = cat
            lang.children[cat.name] = cat
        impl_confs = []  # type: t.List[t.Tuple[str, dict]]
        if not group_by_app:
            for (i, config) in enumerate(configs):
                for impl_conf in config["impls"]:
                    impl_confs.append((config_impl_apps[i], impl_conf))
        else:
            d = defaultdict(lambda: [])
            for (i, config) in enumerate(configs):
                for (j, impl_conf) in enumerate(config["impls"]):
                    d[j].append((config_impl_apps[i], impl_conf))
            impl_confs = []
            for i in range(len(first_config["impls"])):
                impl_confs.extend(d[i])
        if "impls" in first_config:
            for cat in lang.categories:
                cat_val = lang.categories[cat]
                for prog in cat_val.programs:
                    prog_val = cat_val.programs[prog]
                    for p_in in prog_val.prog_inputs:
                        p_in_val = prog_val.prog_inputs[p_in]
                        for (app, impl_conf) in impl_confs:
                                conf = copy.deepcopy(impl_conf)
                                conf["name"] += app
                                name = conf["name"]
                                if name not in p_in_val.impls:
                                    p_in_val[name] = Implementation.from_config_dict(p_in_val, conf)
        return lang

    def set_merged_run_data_from_result_dict(self, run_datas: t.List[t.List[t.Dict[str, t.Any]]],
                                             impl_apps: t.List[str], property: str = "task-clock"):
        assert len(run_datas) == len(impl_apps)
        for (i, run_data_list) in enumerate(run_datas):
            for run_data in run_data_list:
                attrs = run_data["attributes"]
                typecheck(attrs, Dict({
                    "language": E(self.name),
                    "category": Str(),
                    "program": Str(),
                    "impl": Str(),
                    "input": Str()
                }))
                try:
                    self[attrs["category"]][attrs["program"]][attrs["input"]][attrs["impl"] + impl_apps[i]].run_data \
                        = run_data["data"][property]
                except KeyError as err:
                    logging.warning(err)
                    pass

    def set_difference_from_two_result_dicts(self, run_datas: t.Tuple[t.List[t.Dict[str, t.Any]]], app: str,
                                             property: str = "task-clock"):
        """
        First - Second for each measured value
        """
        assert len(run_datas) == 2
        first_run_data_list = run_datas[0]
        for (i, run_data) in enumerate(first_run_data_list):
            sec_run_data = run_datas[1][i]
            attrs = run_data["attributes"]
            typecheck([attrs, sec_run_data["attributes"]], List(Dict({
                "language": E(self.name),
                "category": Str(),
                "program": Str(),
                "impl": Str(),
                "input": Str()
            })))
            data = [f - s for (f, s) in zip(run_data["data"][property], sec_run_data["data"][property])]
            try:
                self[attrs["category"]][attrs["program"]][attrs["input"]][attrs["impl"]].run_data \
                    = data
            except KeyError as err:
                logging.warning(err)
                pass

    def __getitem__(self, name: str) -> ProgramCategory:
        return self.categories[name]

    def process_result_file(self, file: str, property: str = "task-clock"):
        with open(file, "r") as f:
            self.set_run_data_from_result_dict(yaml.load(f), property)

    def build(self, base_dir: str, multiprocess: bool = True) -> t.List[dict]:
        #path = self._create_own_dir(base_dir)
        return self._buildup_dict(base_dir, self.categories, multiprocess=True)

    def create_temci_run_file(self, base_build_dir: str, file: str):
        run_config = self.build(base_build_dir)
        with open(file, "w") as f:
            print(yaml.dump(run_config), file=f)

    def get_box_plot_html(self, base_file_name: str) -> str: # a box plot over the mean scores per category
        scores_per_impl = self.get_scores_per_impl()
        singles = []
        for impl in scores_per_impl:
            scores = scores_per_impl[impl]
            name = "mean score"
            data = RunData({name: scores}, {"description": impl})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name, singles)

    def get_html2(self, base_file_name: str, h_level: int, with_header: bool = True,
                  multiprocess: bool = False, show_entropy_distinction: bool = True):
        base_file_name += "_" + html_escape_property(self.name)
        html = ""
        if with_header:
            html += """
            <h{}>Language: {}</h{}>
            """.format(h_level, self.name, h_level)
        else:
            h_level -= 1

        def summary(h_level: int, base_file_name: str):
            html = self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(used_rel_mean_property))
            html += self.table_html_for_vals_per_impl(common_columns, base_file_name)
            if self.get_max_input_num() > 1:
                for n in range(0, self.get_max_input_num()):
                    mean_scores = self.get_statistical_property_scores_per_input_per_impl(used_rel_mean_property, n)
                    std_scores = self.get_statistical_property_scores_per_input_per_impl(used_std_property, n)
                    html += """
                        <h{h}>Summary for input no. {n} </h{h}>
                        Mean score per implementation. Excludes all categories with less than {m} inputs.
                        The plot shows the distribution of mean scores per category per implementation for
                        input no. {n}.
                        <p>
                    """.format(h=h_level + 1, n=n, m=self.get_max_input_num())
                    html += self.boxplot_html_for_data("mean score", base_file_name + "__input_" + str(n),
                                              self.get_x_per_impl_and_input(used_rel_mean_property, n))
                    html += self.table_html_for_vals_per_impl(common_columns, base_file_name + "__input_" + str(n),
                                                              lambda property: self.get_x_per_impl_and_input(property, n))
            return html

        html += summary(h_level, base_file_name)
        if show_entropy_distinction:
            html += """
                <h{h}>Seperated by entropy</h{h}>
                The following shows the summary including only the lower or the upper half of programs
                (per category),
                regarding the entropy of their files. This entropy is measured by taking the length of the
                gnu zipped program code length. Programs with lower entropy should be simpler than programs
                with higher entropy.
                If the number of programs is uneven in a category, then one program belongs to the upper and
                the lower half.
            """.format(h=h_level + 1)
            for (b, title) in [(True, "Programs with lower entropies"), (False, "Programs with higher entropies")]:
                def func(cur_index: int, all: t.List[Program]):
                    return property_filter_half(cur_index, all, lambda x: x.entropy, b)
                self.apply_program_filter(func)
                html += summary(h_level + 1, base_file_name + "__entropy_lower_half_" + str(b))
            self.apply_program_filter(id_program_filter)
        objs = []
        for (i, cat) in enumerate(self.categories):
            objs.append((i, cat, base_file_name + "_" + html_escape_property(cat), h_level + 1))
        map_func = map
        if multiprocess: # doesn't work (fix warning issue of seaborn)
            pool = multiprocessing.Pool(2)
            map_func = pool.map
        html += "\n".join(map_func(self._get_html2_for_category, objs))
        return html

    def apply_program_filter(self, filter: ProgramFilterFunc = id_program_filter):
        for cat in self.categories.values():
            cat.apply_program_filter(filter)

    def get_html(self, base_file_name: str, h_level: int, with_header: bool = True, multiprocess: bool = False) -> str:
        html = ""
        if with_header:
            html += """
            <h{}>Language: {}</h{}>
            """.format(h_level, self.name, h_level)
        else:
            h_level -= 1
        html += """
        <h{h}>Summary</h{h}>
        Mean score per implementation
        <p>
        """.format(h=h_level + 1)
        html += self.get_box_plot_html(base_file_name)
        scores = self.get_impl_mean_scores()
        std_devs = self.get_statistical_property_scores(rel_std_dev_func)
        html += """
            </p>
            <table class="table">
                <tr><th>implementation</th><th>geom mean over means relative to best
                (per input, program and category) aka mean score</th>
                <th> ... std devs per best means</th>
                </tr>
        """
        for impl in scores:
            html += """
                <tr><td>{}</td><td>{:5.2%}</td><td>{:5.2%}</td></tr>
            """.format(impl, scores[impl], std_devs[impl])
        html += "</table>"
        if self.get_max_input_num() > 1:
            for n in range(0, self.get_max_input_num()):
                mean_scores = self.get_statistical_property_scores_per_input_per_impl(rel_mean_func, n)
                std_scores = self.get_statistical_property_scores_per_input_per_impl(rel_std_dev_func, n)
                html += """
                    <h{h}>Summary for input no. {n} </h{h}>
                    Mean score per implementation. Excludes all categories with less than {m} inputs.
                    The plot shows the distribution of mean scores per category per implementation for
                    input no. {n}.
                    <p>
                """.format(h=h_level + 1, n=n, m=self.get_max_input_num())
                html += self.get_box_plot_per_input_per_impl_html(base_file_name, n)
                html += """
                    </p>
                    <table class="table">
                        <tr><th>impl</th><th>geom mean over means relative to best (per input and program) aka mean score</th>
                        <th>... std devs relative to the best means </th><th>std devs over the categories mean scores</th>
                        </tr>
                """
                for impl in mean_scores.keys():
                    html += """
                        <tr><td>{}</td><td>{:5.2%}</td><td>{:5.2%}</td><td>{:5.2%}</td></tr>
                    """.format(impl, stats.gmean(mean_scores[impl]), stats.gmean(std_scores[impl]), stats.nanstd(mean_scores[impl]))
                html += "</table>"
        objs = []
        for (i, cat) in enumerate(self.categories):
            objs.append((i, cat, base_file_name + "_" + html_escape_property(cat), h_level + 1))
        map_func = map
        if multiprocess: # doesn't work (fix warning issue of seaborn)
            pool = multiprocessing.Pool(2)
            map_func = pool.map
        html += "\n".join(map_func(self._get_html_for_category, objs))
        return html

    def _get_html_for_category(self, arg: t.Tuple[int, str, str, int]) -> str:
        i, cat, base_name, h_level = arg
        return self.categories[cat].get_html(base_name, h_level)

    def _get_html2_for_category(self, arg: t.Tuple[int, str, str, int]) -> str:
        i, cat, base_name, h_level = arg
        return self.categories[cat].get_html2(base_name, h_level)

    def get_full_html(self, base_dir: str, html_func: t.Callable[[str, int, bool], str] = None) -> str:
        resources_path = os.path.abspath(os.path.join(os.path.dirname(report.__file__), "report_resources"))
        shutil.copytree(resources_path, os.path.join(base_dir, "resources"))
        html = """<html lang="en">
    <head>
        <title>Implementation comparison for {lang}</title>
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.ui.all.css">
        <link rel="stylesheet" src="http://gregfranko.com/jquery.tocify.js/css/jquery.tocify.css">
        <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="{srv}resources/style.css">
        <script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery-ui-1.9.1.custom.min.js"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery.tocify.js"></script>
        <script type="text/javascript" src="https://cdn.mathjax.org/mathjax/latest/MathJax.js?config=TeX-AMS-MML_SVG"></script>
        <script src="{srv}resources/script.js"></script>
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
                    <h1>Implementation comparison for {lang}</h1>
                    <p class="lead">A comparison of {comparing_str}</p>
                  </div>
                {inner_html}
                <footer class="footer">
                    Generated by <a href="https://github.com/parttimenerd/temci">temci</a>'s game.py in {timespan}<br/>
                    The benchmarked algorithms and their inputs come from the
                    <a href="http://benchmarksgame.alioth.debian.org/">benchmarksgame</a>
                </footer>
             </div>
          </div>
        </div>
    </body>
</html>
        """
        lang = self.name
        comparing_str = util.join_strs(self.get_scores_per_impl().keys())
        html_func = html_func or self.get_html
        inner_html = html_func(base_dir + "/fig", 2, with_header=False)
        import humanfriendly
        timespan = humanfriendly.format_timespan(time.time() - START_TIME)
        srv = "" if USABLE_WITH_SERVER else "file:"
        return html.format(**locals())

    def store_html(self, base_dir: str, clear_dir: bool = True, html_func: t.Callable[[str, int, bool], str] = None):
        typecheck_locals(base_dir=DirName())
        if not os.path.exists(base_dir):
            os.mkdir(base_dir)
        if clear_dir:
            shutil.rmtree(base_dir)
            self.store_html(base_dir, clear_dir=False, html_func=html_func)
            return
        with open(os.path.join(base_dir, "report.html"), "w") as f:
            #print(self.get_full_html(os.path.join(base_dir)))
            f.write(self.get_full_html(base_dir, html_func))

    def get_scores_per_impl(self) -> t.Dict[str, t.List[float]]:
        return self.get_statistical_property_scores_per_impl(rel_mean_func)

    def get_statistical_property_scores_per_impl(self, func: StatisticalPropertyFunc) -> t.Dict[str, t.List[float]]:
        impl_scores = InsertionTimeOrderedDict()
        for cat in self.categories:
            scores = self.categories[cat].get_statistical_property_scores(func)
            for impl in scores:
                if impl not in impl_scores:
                    impl_scores[impl] = []
                impl_scores[impl].append(scores[impl])
        return impl_scores

    def get_impl_mean_scores(self) -> t.Dict[str, float]:
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc,
                                        reduce: ReduceFunc = stats.gmean) -> t.Dict[str, float]:
        ret = InsertionTimeOrderedDict()
        scores_per_impl = self.get_statistical_property_scores_per_impl(func)
        for impl in scores_per_impl:
            ret[impl] = reduce(scores_per_impl[impl])
        return ret

    def get_max_input_num(self) -> int:
        return max(len(cat.get_input_strs()) for cat in self.categories.values())

    def _get_categories_for_number_of_inputs(self, number_of_inputs: int) -> t.List[ProgramCategory]:
        return [cat for cat in self.categories.values() if len(cat.get_input_strs()) == number_of_inputs]

    def get_statistical_property_scores_per_input_per_impl(self, func: StatisticalPropertyFunc, input_num: int,
                                                           reduce: ReduceFunc = stats.gmean) -> t.Dict[str, t.List[float]]:
        """
        Assumptions:
            - Most programs have the same number of input (known as max input number)
            - The input number n takes roughly the same amount of time for every program category
        """
        cats = self._get_categories_for_number_of_inputs(self.get_max_input_num())
        scores_per_impl = InsertionTimeOrderedDict()
        for cat in cats:
            scores = cat.get_statistical_property_scores_per_input_per_impl(func, cat.get_input_strs()[input_num])
            for impl in scores:
                if impl not in scores_per_impl:
                    scores_per_impl[impl] = []
                scores_per_impl[impl].append(reduce(scores[impl]))
        return scores_per_impl

    def get_box_plot_per_input_per_impl_html(self, base_file_name: str, input_num: int) -> str:
        """
        A box plot for each input that shows the mean scores (over all programs) for each implementation.
        """
        return self.boxplot_html_for_data("mean score", base_file_name + "__input_" + str(input_num),
                                          self.get_statistical_property_scores_per_input_per_impl(rel_mean_func, input_num))

    def get_x_per_impl_and_input(self, property: StatProperty, input_num: int) -> t.Dict[str, t.List[float]]:
        means = InsertionTimeOrderedDict()  # type: t.Dict[str, t.List[float]]
        for child in self.categories.values():
            inputs = child.get_input_strs()
            if len(inputs) <= input_num:
                continue
            child_means = child.get_x_per_impl_and_input(property, inputs[input_num])
            for impl in child_means:
                if impl not in means:
                    means[impl] = []
                means[impl].extend(child_means[impl])
        typecheck(means._dict, Dict(key_type=Str(), value_type=List(Float()|Int()), all_keys=False))
        return means


def ref(name: str, value = None, _store={}):
    """
    A simple YAML like reference utility.
    It to easily store a value under a given key and return it.

    :param name: name of the reference
    :param value: new value of the reference (if value isn't None)
    :param _store: dict to store everything in
    :return: the value of the reference
    """
    if value is not None:
        _store[name] = value
    return _store[name]


def file_entropy(file: str) -> int:
    """ Calculates the entropy of given file by taking the length of its gzip compressed content  """
    with open(file, "r") as f:
        return len(zlib.compress(f.read().encode("utf-8")))


def file_lines(file: str) -> int:
    """ Number of non empty lines in the file  """
    with open(file, "r") as f:
        return sum(1 for line in f if line.strip() != "")


def bench_file(category: str, ending: str, number: int = 1) -> str:
    base = BENCH_PATH + "/{c}/{c}".format(c=category)
    if number == 1:
        return base + "." + ending
    return base + ".{ending}-{number}.{ending}".format(**locals())


def bench_program(category: str, ending: str, inputs: t.List[Input], number: int = 1) -> dict:
    return {
        "program": str(number),
        "file": bench_file(category, ending, number),
        "inputs": [input.replace("$INPUT", BENCH_PATH + "/../bencher/input").to_dict() for input in inputs]
    }


def bench_category(category: str, ending: str, inputs: t.List[Input], numbers: t.List[int] = None) -> dict:
    if numbers is None:
        numbers = []
        for i in range(1, 10):
            if os.path.exists(bench_file(category, ending, i)):
                numbers.append(i)
    #numbers = [numbers[0]]
    programs = [bench_program(category, ending, inputs, number) for number in numbers]
    return {
        "category": category,
        "programs": programs
    }


InputsPerCategory = t.Dict[str, t.List[Input]]


def bench_categories(ending: str, inputs: InputsPerCategory) -> t.List[dict]:
    categories = []
    for cat in inputs:
        if os.path.exists(bench_file(cat, ending)):
            categories.append(bench_category(cat, ending, inputs[cat]))
    return categories


def first_inputs(inputs_per_category: InputsPerCategory) -> InputsPerCategory:
    ret = InsertionTimeOrderedDict()
    for key in inputs_per_category:
        if len(inputs_per_category[key]) > 0:
            ret[key] = [inputs_per_category[key][0]]
    return ret


def empty_inputs(inputs_per_category: InputsPerCategory) -> InputsPerCategory:
    ret = InsertionTimeOrderedDict()
    for key in inputs_per_category:
        if len(inputs_per_category[key]) > 0:
            ret[key] = [Input()]
    return ret


def last_inputs(inputs_per_category: InputsPerCategory) -> t.Dict[str, t.List[Input]]:
    ret = InsertionTimeOrderedDict()
    for key in inputs_per_category:
        if len(inputs_per_category[key]) > 0:
            ret[key] = [inputs_per_category[key][-1]]
    return ret


def divide_inputs(inputs_per_category: InputsPerCategory, divisor: t.Union[int, float]) \
        -> t.Dict[str, t.List[Input]]:
    ret = InsertionTimeOrderedDict()
    for key in inputs_per_category:
        ret[key] = [input // divisor for input in inputs_per_category[key]]
    return ret


def prefix_inputs(prefix: str, inputs: t.List[Input]) -> t.List[Input]:
    return [Input(prefix + input.prefix, input.number, input.appendix) for input in inputs]


ConfigDict = t.Dict[str, t.Union[str, dict]]


def replace_run_with_build_cmd(config_dict: ConfigDict) -> ConfigDict:
    config_dict = copy.deepcopy(config_dict)
    for impl_dict in config_dict["impls"]:
        impl_dict["run_cmd"] = impl_dict["build_cmd"] + " &> /dev/null"
        del(impl_dict["build_cmd"])
    return config_dict


# download the benchmarksgame source code from https://alioth.debian.org/snapshots.php?group_id=100815
BENCH_PATH = "/home/parttimenerd/benchmarksgame/bench"

# Inputs based on the ones used in the benchmarksgame
INPUTS_PER_CATEGORY = { # type: InputsPerCategory
    "binarytrees": Input.list_from_numbers(12, 16, 20),
    "binarytreesredux": Input.list_from_numbers(12, 16, 20),
    "chameneosredux": Input.list_from_numbers(60000, 600000, 6000000),
    "fannkuchredux": Input.list_from_numbers(10, 11, 12),
    "fasta": ref("fasta", Input.list_from_numbers(250000, 2500000, 25000000)),
    "fastaredux": ref("fasta"),
    "knucleotide": prefix_inputs("$INPUT/knucleotide-input.txt ", ref("fasta")),
    "mandelbrot": Input.list_from_numbers(1000, 4000, 16000),
    "meteor": Input.list_from_numbers(2098),
    "nbody": Input.list_from_numbers(500000, 5000000, 50000000),
    "pidigits": Input.list_from_numbers(2000, 6000, 10000),
    "regexdna": prefix_inputs("$INPUT/regexdna-input.txt ", Input.list_from_numbers(50000, 500000, 5000000)),
    "revcomp": prefix_inputs("$INPUT/revcomp-input.txt ", Input.list_from_numbers(250000, 2500000, 25000000)),
    "spectralnorm": Input.list_from_numbers(500, 3000, 5500),
    "threadring": Input.list_from_numbers(500000, 5000000, 50000000)
}


def c_config(inputs_per_category: InputsPerCategory, optimisation: str = "-O2", clang_version = "3.7") -> ConfigDict:
    """
    Generates a game config that compares gcc and clang.
    """

    def cat(category: str, numbers: t.List[int] = None):
        return bench_category(category, "gcc", inputs_per_category[category], numbers)

    config = {
        "language": "c",
        "categories": [
            cat("binarytrees"),
            cat("chameneosredux", [2]),
            cat("fannkuchredux", [1, 5]),
            cat("fasta", [1, 4, 5]),
            cat("fastaredux"),
            #cat("knucleotide", "gcc", [9]) # doesn't compile
            cat("mandelbrot", [1, 2, 3, 4, 6, 9]),
            cat("meteor"),
            cat("nbody"),
            cat("pidigits"),
            #cat("regexdna", "gcc", [1, 2]),      # runs almost infinitely
            cat("revcomp", [1]),
            cat("spectralnorm", [1]),
            cat("threadring")
        ],
        "impls": [
            {
                "name": "gcc", # todo: tcl8.6 vs 8.4???
                "build_cmd": "cp {file} {bfile}.c; gcc {bfile}.c $O -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp "
                             "-D_GNU_SOURCE -Doff_t=__off64_t -fopenmp -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 "
                             "-lapr-1 -lgomp -lm -std=c99 -mfpmath=sse -msse3 -I/usr/include/glib-2.0 "
                             "-I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre -o {bfile}"
                             .replace("$O", optimisation),
                "run_cmd": "./{bfile} {input} > /dev/null"
            }, {
                "name": "clang",
                "build_cmd": "cp {file} {bfile}.c; clang-$CV {bfile}.c $O -I/usr/include/tcl8.6 -ltcl8.4 -fopenmp=libgomp "
                             "-lglib-2.0 -lgmp -D_GNU_SOURCE -Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 "
                             "-I/usr/include/apr-1.0 -lapr-1  -lm -std=c99 -mfpmath=sse -msse3 -I/usr/include/glib-2.0 "
                             "-I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre -o {bfile}"
                            .replace("$CV", clang_version).replace("$O", optimisation),
                "run_cmd": "./{bfile} {input} > /dev/null"
            }
        ]
    }

    return config


def cparser_config(inputs_per_category: InputsPerCategory, optimisation: str = "-O2", clang_version = "3.7") -> ConfigDict:
    """
    Generates a game config that compares gcc, clang and cparser.
    """

    def cat(category: str, numbers: t.List[int] = None):
        return bench_category(category, "gcc", inputs_per_category[category], numbers)

    config = {
        "language": "c",
        "categories": [
            cat("binarytrees", [1, 3, 5]),
            cat("chameneosredux", [2]),
            cat("fannkuchredux", [1, 5]),
            cat("fasta", [1, 4, 5]),
            cat("fastaredux"),
            #cat("knucleotide", "gcc", [9]) # doesn't compile
            cat("mandelbrot", [2, 9]),
            cat("meteor"),
            cat("nbody", [1, 2, 3, 6]),
            cat("pidigits"),
            #cat("regexdna", "gcc", [1, 2]),      # runs almost infinitely
            cat("revcomp", [1]),
            cat("spectralnorm", [1]),
            cat("threadring", [1, 2, 3])
        ],
        "impls": [
            {
                "name": "gcc",
                "build_cmd": "cp {file} {bfile}.c; gcc {bfile}.c -w $O -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp -D_GNU_SOURCE "
                             "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1 -lgomp -lm -std=c99 "
                             " -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                             " -lpthread -o {bfile}.{impl_escaped}".replace("$O", optimisation),
                "run_cmd": "./{bfile} {input} > /dev/null"
            }, {
                "name": "clang",
                "build_cmd": "cp {file} {bfile}.c; clang-$CV {bfile}.c -w $O -I/usr/include/tcl8.6 -ltcl8.4 "
                             "-fopenmp=libgomp -lglib-2.0 -lgmp -D_GNU_SOURCE "
                             "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1  -lm -std=c99 "
                             "-I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                             "-lpthread -o {bfile}.{impl_escaped}".replace("$CV", clang_version).replace("$O", optimisation),
                "run_cmd": "./{bfile}.{impl_escaped} {input} > /dev/null"
            }, {
                "name": "cparser",
                "build_cmd": "cp {file} {bfile}.c; cparser {bfile}.c -w $O -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp -D_GNU_SOURCE "
                             "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1 -lgomp -lm -std=c99 "
                             " -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                             " -lpthread -o {bfile}.{impl_escaped}".replace("$O", optimisation),
                "run_cmd": "./{bfile}.{impl_escaped} {input} > /dev/null"
            }
        ]
    }

    return config


AV_RUST_VERSIONS = ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0", "beta", "nightly"]

def rust_config(inputs_per_category: InputsPerCategory, optimisation: int = 3) -> ConfigDict:
    """
    Generates a game config that compares the different rust versions.
    """

    def cat(category: str, numbers: t.List[int] = None):
        return bench_category(category, "rust", inputs_per_category[category], numbers)

    impls = []
    for version in AV_RUST_VERSIONS:
        impls.append({
            "name": str(version),
            "build_cmd": "cp {file} {category}.rust; multirust run $V rustc {category}.rust -Copt-level=$O -o {category}"
                .replace("$O", str(optimisation)).replace("$V", str(version)),
            "run_cmd": "./{category} {input} > /dev/null"
        })

    config = {
        "language": "rust",
        "categories": [
            #cat("binarytrees")
            cat("chameneosredux"),
            cat("fannkuchredux", [2]),
            cat("fasta", [1]),
            cat("fastaredux"),
            #cat("knucleotide"),
            ###cat("mandelbrot", [1]),
            cat("meteor", [2]),
            cat("nbody"),
            cat("pidigits"),
            #cat("regexdna"),
            #cat("revcomp"),
            cat("spectralnorm"),
            cat("threadring")
        ],
        "impls": impls
    }

    return config


AV_GHC_VERSIONS = ["7.0.1", "7.2.1", "7.4.1", "7.6.1", "7.8.1", "7.10.1", "8.0.1"]
""" These are (currently) the versions installable via the ppa on https://launchpad.net/~hvr/+archive/ubuntu/ghc
Older versions can't be installed due to version conflicts and missing libraries """


def haskel_config(inputs_per_category: InputsPerCategory, optimisation: str, ghc_versions: t.List[str] = None,
                  used_c_compilers: t.List[str] = None) -> ConfigDict:
    """
    Generate a game config comparing all available ghc versions

    :param inputs_per_category: 
    :param optimisation: optimisation flags, e.g. '-Odph' or '-O'
    :param ghc_versions: compared ghc versions, if None, AV_GHC_VERSIONS is used
    """
    ghc_versions = ghc_versions or AV_GHC_VERSIONS

    def cat(category: str, numbers: t.List[int] = None):
        return bench_category(category, "ghc", inputs_per_category[category], numbers)


    def ghc_impl_dir(version) -> str:
        typecheck_locals(version=ExactEither(*AV_GHC_VERSIONS))
        dir = "/opt/ghc/{version}/bin/".format(**locals())
        typecheck_locals(dir=DirName())
        return dir
    
    
    def ghc_impl(version: str, used_c_compiler: str = None) -> t.Dict[str, str]:
        c_comp_str = "-pgmc " + used_c_compiler if used_c_compiler else ""
        return {
            "name": "ghc-" + version + ("-" + used_c_compiler if used_c_compiler else ""),
            "build_cmd": "cp {{file}} {{bfile}}.{{impl}}.hs; PATH={impl_dir}:$PATH ghc {O} -XBangPatterns "
                         "{{bfile}}.{{impl}}.hs -XCPP -XGeneralizedNewtypeDeriving -XTypeSynonymInstances "
                         "-XFlexibleContexts -XUnboxedTuples -funbox-strict-fields -XScopedTypeVariables "
                         "-XFlexibleInstances -funfolding-use-threshold=32 {c_comp} -XMagicHash -threaded"
                .format(O=optimisation, impl_dir=ghc_impl_dir(version), c_comp=c_comp_str),
            "run_cmd": "./{{bfile}}.{{impl}} {{input}} > /dev/null".format(ghc_impl_dir(version))
        }
    

    impls = [ghc_impl(version) for version in ghc_versions]
    if used_c_compilers:
        impls = []
        for c_comp in used_c_compilers:
            impls.extend([ghc_impl(version, c_comp) for version in ghc_versions])

    # Note to the removed programs:
    # These either don't compile with all ghc versions properly or use additional hackage packages
    # The latter is bad because installing the package for all ghc's isn't to costly

    config = {
        "language": "haskell",
        "categories": [
            cat("binarytrees", [1]),
            ###cat("chameneosredux", [4]),
            cat("fannkuchredux", [1, 3]),
            cat("fasta", [1]),
            ###cat("knucleotide"), # seems to run forever
            cat("mandelbrot"),
            cat("meteor"),
            cat("nbody", [2]),
            cat("pidigits"),
            ###cat("regexdna"), # uses package PCRE
            ###cat("revcomp", [2]), # seems to runs forever
            cat("spectralnorm", [2]),
            ###cat("threadring")    # doesn't compile properly
        ],
        "impls": [
            ghc_impl(version) for version in ghc_versions
        ]
    }

    return config


def process(config: ConfigDict, name: str = None, build_dir: str = None, build: bool = True, benchmark: bool = True,
            report: bool = True, temci_runs: int = 15, temci_options: str = "--discarded_blocks 1",
            temci_stop_start: bool = True, report_dir: str = None, property: str = "task-clock",
            report_modes: t.List[Mode] = [Mode.mean_rel_to_first, Mode.geom_mean_rel_to_best]):
    """
    Process a config dict. Simplifies the build, benchmarking and report generating.

    :param config: processed config dict
    :param name: the name of the whole configuration (used to generate the file names), default "{config['language]}"
    :param build_dir: build dir that is used to build the programs, default is "/tmp/{name}"
    :param build: make a new build of all programs? (results in a "{name}.exec.yaml" file for temci)
    :param benchmark: benchmark the "{name}.exec.yaml" file (from a built)? (results in a "{name}.yaml" result file)
    :param report: generate a game report? (results in a report placed into the report_dir)
    :param temci_runs: number of benchmarking runs (if benchmark=True)
    :param temci_options: used options for temci
    :param temci_stop_start: does temci use the StopStart plugin for decreasing the variance while benchmarking?
    :param report_dir: the directory to place the report in, default is "{name}_report"
    :param property: measured property for which the report is generated, default is "task-clock"
    """
    global START_TIME
    START_TIME = time.time()
    lang = Language.from_config_dict(config)
    name = name or config["language"]
    temci_run_file = name + ".exec.yaml"
    temci_result_file = name + ".yaml"
    build_dir = build_dir or "/tmp/" + name
    if not os.path.exists(build_dir):
        os.mkdir(build_dir)
    if build:
        lang.create_temci_run_file(build_dir, temci_run_file)
    if benchmark:
        logging.info("Start benchmarking")
        stop_start_str = "--stop_start" if temci_stop_start else ""
        cmd = "temci exec {temci_run_file} --runner perf_stat --runs {temci_runs} {temci_options} {stop_start_str} --out {temci_result_file}"\
            .format(**locals())
        #print(cmd)
        os.system(cmd)
    if report:
        lang.process_result_file(temci_result_file, property)
        for mode in report_modes:
            global CALC_MODE
            CALC_MODE = mode
            _report_dir = (report_dir or name + "_report") + "_" + str(mode)
            os.system("mkdir -p " + _report_dir)
            lang.store_html(_report_dir, clear_dir=True, html_func=lang.get_html2)


DataBlock = t.Dict[str, t.Union[t.Dict[str, t.List[float]], t.Any]]


def produce_ttest_comparison_table(datas: t.List[t.List[DataBlock]],
                                   impls: t.List[str],
                                   data_descrs: t.List[str],
                                   filename: str,
                                   property: str = "task-clock", alpha: float = 0.05,
                                   tester_name: str = "t",
                                   ratio_format: str = "{:3.0%}"):

    assert len(datas) == len(data_descrs)

    tester = TesterRegistry.get_for_name(tester_name, [alpha, 2 * alpha])

    def not_equal(data_block1: DataBlock, data_block2: DataBlock) -> Bool:

        def extract_list(data_block: DataBlock) -> t.List[float]:
            return data_block["data"][property]

        return tester.test(extract_list(data_block1), extract_list(data_block2)) < alpha

    def get_data_blocks_for_impl(data: t.List[DataBlock], impl: str) -> t.List[DataBlock]:
        return [x for x in data if x["attributes"]["impl"] == impl]

    def not_equal_ratio_for_impl(data1: t.List[DataBlock], data2: t.List[DataBlock], impl: str) -> float:
        bools = [not_equal(f, s) for (f, s) in zip(get_data_blocks_for_impl(data1, impl), get_data_blocks_for_impl(data2, impl))]
        not_equal_num = sum(bools)
        return not_equal_num / len(bools)

    def not_equal_ratios_forall_impls(data1: t.List[DataBlock], data2: t.List[DataBlock]) -> t.List[float]:
        l = [not_equal_ratio_for_impl(data1, data2, impl) for impl in impls]
        l.append(sum(l) / len(l))
        return l

    def get_data_permutation_ratios_per_impl() -> t.List[t.Tuple[str, t.List[float]]]:
        tuples = []
        for (i, (data1, descr1)) in enumerate(zip(data, data_descrs)):
            for (data2, descr2) in list(zip(data, data_descrs))[i + 1:]:
                descr = "{} != {}?".format(descr1, descr2)
                ratios = not_equal_ratios_forall_impls(data1, data2)
                tuples.append((descr, ratios))
        return tuples

    def tuples_to_html(tuples: t.List[t.Tuple[str, t.List[float]]]) -> str:
        html = """
        <html>
            <body>
            <table><tr><th></th>{}</tr>
        """.format("".join("<th>{}</th>".format(descr) for (descr, d) in tuples))
        for (i, impl) in enumerate(impls + ["average"]):
            html += """
            <tr><td>{}</td>{}</tr>
            """.format(impl, "".join("<td>{}</td>".format(ratio_format.format(d[i])) for (_, d) in tuples))
        html += """
            <table>
            </body>
        </html>
        """
        return html

    def tuples_to_tex(tuples: t.List[t.Tuple[str, t.List[float]]]) -> str:
        tex = """
\\documentclass[10pt,a4paper]{article}
\\usepackage{booktabs}
\\begin{document}
            """
        tex_end = """
\\end{document}
"""
        tex += """
    \\begin{{tabular}}{{l{cs}}}\\toprule
        """.format(cs="".join("r" * len(tuples)))
        tex_end = """
        \\bottomrule
    \\end{tabular}
        """ + tex_end
        tex += "&" + " & ".join(descr for (descr, _) in tuples) + "\\\\ \n \\midrule "
        for (i, impl) in enumerate(impls + ["average"]):
            tex += """
            {} & {} \\\\
            """.format(impl, " & ".join(ratio_format.format(d[i]).replace("%", "\\%") for (_, d) in tuples))
        return tex + tex_end

    tuples = get_data_permutation_ratios_per_impl()
    #pprint(tuples)

    with open(filename + ".html", "w") as f:
        f.write(tuples_to_html(tuples))

    with open(filename + ".tex", "w") as f:
        f.write(tuples_to_tex(tuples))

if __name__ == "__main__":

    #MODE = "haskell_full"
    MODE = "rustc" # requires multirust
    #MODE = "haskell_c_compilers"

    if MODE == "rustc":
        optis = [0, 1, 2, 3]
        for opti in reversed(optis):
            try:
                config = replace_run_with_build_cmd(rust_config(empty_inputs(INPUTS_PER_CATEGORY), opti))
                process(config, "compile_time_rust_" + str(opti), temci_runs=30, build=False, benchmark=False,
                        temci_options="--nice --other_nice --send_mail me@mostlynerdless.de", temci_stop_start=True)
                #shutil.rmtree("/tmp/compile_time_haskell_" + opti)
            except BaseException as ex:
                logging.error(ex)
                pass
            os.sync()
            #time.sleep(60)

        for opti in reversed(optis[-1:]):
            try:
                config = rust_config(INPUTS_PER_CATEGORY, opti)
                process(config, "rust_" + str(opti),
                        temci_options="--discarded_blocks 1 --nice --other_nice --send_mail me@mostlynerdless.de ",
                        build=False, benchmark=False, property="task-clock",
                        temci_stop_start=False)
                #shutil.rmtree("/tmp/compile_time_haskell_" + opti)
            except BaseException as ex:

                logging.error(ex)
                pass
            os.sync()
            #time.sleep(60)
        """
        for prop in ["task-clock"]:#["task-clock", "branch-misses", "cache-references", "cache-misses"]:
            config = rust_config(INPUTS_PER_CATEGORY, 3)
            process(config, "rust_3", report_dir="rust_c_" + prop,
                    temci_options="--discarded_blocks 1 --nice --other_nice --send_mail me@mostlynerdless.de ",
                    build=False, benchmark=False, property="task-clock",
                    temci_stop_start=False)
        """

    if MODE == "haskell_full":
        optis = ["", "-O", "-O2", "-Odph"]

        for opti in optis:
            try:
                config = replace_run_with_build_cmd(haskel_config(empty_inputs(INPUTS_PER_CATEGORY), opti))
                process(config, "compile_time_haskell_" + opti, temci_runs=30, build=False, benchmark=False)
                #shutil.rmtree("/tmp/compile_time_haskell_" + opti)
            except OSError as ex:
                logging.error(ex)
                pass
            os.sync()
            #time.sleep(60)
        optis = ["-O", "-O2", "-Odph"]
        for opti in reversed(optis):
            try:
                config = haskel_config(INPUTS_PER_CATEGORY, opti)
                process(config, "haskell" + opti, temci_options=" --discarded_blocks 1 --nice --other_nice", build=False, benchmark=False, property="task-clock")
                logging.info("processed")
                #shutil.rmtree("/tmp/haskell" + opti)
            except BaseException as ex:
                logging.exception(ex)
                pass
        configs = [haskel_config(empty_inputs(INPUTS_PER_CATEGORY), opti) for opti in optis]
        data = [yaml.load(open("compile_time_haskell_" + opti + ".yaml", "r")) for opti in optis]
        for (by_opti, app) in [(True, "_grouped_by_opti"), (False, "_grouped_by_version")]:
            lang = Language.merge_different_versions_of_the_same(configs, optis, by_opti)
            lang.set_merged_run_data_from_result_dict(data, optis)
            for mode in [Mode.geom_mean_rel_to_best, Mode.mean_rel_to_first]:
                CALC_MODE = mode
                _report_dir = "compile_time_haskell_merged_report" + "_" + str(mode) + app
                os.system("mkdir -p " + _report_dir)
                lang.store_html(_report_dir, clear_dir=True, html_func=lang.get_html2)

        optis = ["-O", "-O2", "-Odph"]
        configs = [haskel_config(INPUTS_PER_CATEGORY, opti) for opti in optis]
        data = [yaml.load(open("haskell" + opti + ".yaml", "r")) for opti in optis]

        """
        for (by_opti, app) in [(True, "_grouped_by_opti"), (False, "_grouped_by_version")]:
            lang = Language.merge_different_versions_of_the_same(configs, optis, by_opti)
            lang.set_merged_run_data_from_result_dict(data, optis)
            for mode in [Mode.geom_mean_rel_to_best, Mode.mean_rel_to_first]:
                CALC_MODE = mode
                _report_dir = "haskell_merged_report" + "_" + str(mode) + app
                os.system("mkdir -p " + _report_dir)
                lang.store_html(_report_dir, clear_dir=True, html_func=lang.get_html2)

        for (first_opti, second_opti, app) in [(0, 1, "O-O2"), (1, 2, "O2-Odph")]:
            lang = Language.from_config_dict(configs[first_opti])
            lang.set_difference_from_two_result_dicts((data[first_opti], data[second_opti]), app)
            for mode in [Mode.mean_rel_to_one]:
                CALC_MODE = mode
                _report_dir = "haskell_" + app + "_report" + "_" + str(mode)
                os.system("mkdir -p " + _report_dir)
                lang.store_html(_report_dir, clear_dir=True, html_func=lang.get_html2)
        """

        produce_ttest_comparison_table(data, ["ghc-" + x for x in AV_GHC_VERSIONS], optis, "haskell_comp")



    if MODE == "haskell_c_compilers":
        for opti in ["-Odph"]:
            try:
                config = haskel_config(INPUTS_PER_CATEGORY, opti, ghc_versions=AV_GHC_VERSIONS[-1:], used_c_compilers=[None, "clang", "gcc"])
                process(config, "haskell_c_compilers_" + opti, temci_options=" --discarded_blocks 0 --nice --other_nice", build=True,
                        benchmark=True, property="task-clock", )
                logging.info("processed")
                #shutil.rmtree("/tmp/haskell" + opti)
            except BaseException as ex:
                logging.exception(ex)
                pass
