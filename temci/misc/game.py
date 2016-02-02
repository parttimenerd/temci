"""
Benchmarks game inspired comparison of different implementations for a given language.

It doesn't really belong directly to the temci tool, but uses big parts of it.
It's currently in a pre alpha state as it's a part of the evaluation for my bachelor thesis
that I'm currently doing,
"""

import logging, time
import typing as t

import multiprocessing

START_TIME = time.time()

import subprocess

import itertools

import temci.utils.util as util

if __name__ == "__main__":
    util.allow_all_imports = True

from temci.tester.rundata import RunData

from temci.tester.stats import SingleProperty, Single, SinglesProperty
from temci.utils.typecheck import *
import os, shutil, copy
from pprint import pprint
from temci.tester import report
import scipy as sp

from temci.utils.util import InsertionTimeOrderedDict

itod_from_list = InsertionTimeOrderedDict.from_list

if util.can_import("scipy"):
    import scipy.stats as stats
    import ruamel.yaml as yaml

from temci.tester.report import HTMLReporter2, html_escape_property

FIG_WIDTH = 15
FIG_HEIGHT_PER_ELEMENT = 1.5


def geom_std(values: t.List[float]) -> float:
    """
    Calculates the geometric standard deviation for the values.
    Source: https://en.wikipedia.org/wiki/Geometric_standard_deviation
    """
    gmean = stats.gmean(values)
    return sp.exp(sp.sqrt(sp.sum([sp.log(x / gmean) ** 2 for x in values]) / len(values)))


StatProperty = t.Callable[[SingleProperty, t.List[float]], float]
""" Gets passed a SingleProperty object and the list of means (containing the object's mean) and returns a float. """
ReduceFunc = t.Callable[[t.List[float]], Any]
""" Gets passed a list of values and returns a single value, e.g. stats.gmean """

def first(values: t.List[float]) -> float:
    return values[0]

def rel_mean_property(single: SingleProperty, means: t.List[float]) -> float:
    """
    A property function that returns the relative mean (the mean of the single / minimum of means)
    """
    return single.mean() / min(means)

def rel_std_property(single: SingleProperty, means: t.List[float]) -> float:
    """
    A property function that returns the relative standard deviation (relative to single's mean)
    """
    return single.std_dev_per_mean()


class BOTableColumn:
    """ Column for BaseObject table_html_for_vals_per_impl  """

    def __init__(self, title: str, format_str: str, property: StatProperty, reduce: ReduceFunc):
        self.title = title
        self.format_str = format_str
        self.property = property
        self.reduce = reduce

mean_score_column = BOTableColumn("mean score (gmean(mean / best mean))", "{:5.5%}", rel_mean_property, stats.gmean)
mean_score_std_column = BOTableColumn("mean score std (gmean std(mean / best mean))", "{:5.5%}", rel_mean_property, geom_std)
mean_rel_std = BOTableColumn("mean rel std (gmean(std / mean))", "{:5.5%}", rel_std_property, stats.gmean)

common_columns = [mean_score_column, mean_score_std_column, mean_rel_std]

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
        <img src="file:{}"/>
        </center>
        <p>
        """.format(d["img"])
        for format in sorted(d):
            html += """
            <a href="file:{}">{}</a>
            """.format(d[format], format)
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
        return self.get_reduced_x_per_impl(rel_mean_property, stats.gmean)

    def get_geom_std_over_rel_means(self) -> t.Dict[str, float]:
        return self.get_gsd_for_x_per_impl(rel_mean_property)

    def get_geom_over_rel_stds(self) -> t.Dict[str, float]:
        return self.get_reduced_x_per_impl(rel_std_property, stats.gmean)

    def table_html_for_vals_per_impl(self, columns: t.List[BOTableColumn],
                                     x_per_impl_func: t.Callable[[StatProperty], t.Dict[str, t.List[float]]] = None) \
            -> str:
        """
        Returns the html for a table that has a row for each implementation and several columns (the first is the
        implementation column).
        """
        html = """
        <table class="table">
            <tr><th></th>{header}</tr>
        """.format(header="".join("<th>{}</th>".format(col.title) for col in columns))
        values = InsertionTimeOrderedDict() # t.Dict[t.List[str]]
        for col in columns:
            xes = self.get_reduced_x_per_impl(col.property, col.reduce, x_per_impl_func)
            for impl in xes:
                if impl not in values:
                    values[impl] = []
                values[impl].append(col.format_str.format(xes[impl]))
        for impl in values:
            html += """
                <tr><td scope="row">{}</td>{}</tr>
            """.format(impl, "".join("<td>{}</td>".format(val) for val in values[impl]))
        html += """
        </table>
        """
        return html


class Implementation(BaseObject):
    """
    Represents an implementation of a program.
    """

    def __init__(self, parent: 'ProgramWithInput', name: str, run_cmd: str, build_cmd: str = None,
                 run_data: t.List[t.Union[int, float]] = None):
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
            "impl_escaped": html_escape_property(self.name)
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
        best_mean = min(sp.mean() for (impl, sp) in sps)
        d = InsertionTimeOrderedDict()
        for (impl, sp) in sps:
            d[impl] = func(sp, best_mean)
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
        scores = self.get_means_rel_to_best()
        columns = [
            BOTableColumn("n", "{:5d}", lambda sp, _: sp.observations(), first),
            BOTableColumn("mean", "{:10.5f}", lambda sp, _: sp.mean(), first),
            BOTableColumn("mean / best mean", "{:5.5%}", lambda sp, means: sp.mean() / min(means), first),
            BOTableColumn("std / mean", "{:5.5%}", lambda sp, _: sp.std_dev_per_mean(), first),
            BOTableColumn("std / best mean", "{:5.5%}", lambda sp, means: sp.std_dev() / min(means), first),
            BOTableColumn("median", "{:5.5f}", lambda sp, _: sp.median(), first)
        ]
        html = """
        <h{h}>Input: {input}</h{h}>
        The following plot shows the actual distribution of the measurements for each implementation.
        {box_plot}
        """.format(h=h_level, input=repr(self.input), box_plot=self.get_box_plot_html(base_file_name))
        html += self.table_html_for_vals_per_impl(columns)
        return html

    def get_x_per_impl(self, property: StatProperty) -> t.Dict[str, t.List[float]]:
        """
        Returns a list of [property] for each implementation.
        :param property: property function that gets a SingleProperty object and a list of all means and returns a float
        """
        means = [x.mean() for x in self.impls.values()]  # type: t.List[float]
        ret = InsertionTimeOrderedDict() # t.Dict[str, t.List[float]]
        for impl in self.impls:
            ret[impl] = [property(self.impls[impl].get_single_property(), means)]
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
        self.prog_inputs = self.children # type: t.Dict[str, ProgramWithInput]
        self.copied_files = copied_files or [] # type: t.List[str]

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
        html += self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(rel_mean_property))
        html += self.table_html_for_vals_per_impl(common_columns)
        for (i, input) in enumerate(self.prog_inputs.keys()):
            app = html_escape_property(input)
            if len(app) > 20:
                app = str(i)
            html += self.prog_inputs[input].get_html2(base_file_name + "_" + app, h_level + 1)
        return html

    def get_html(self, base_file_name: str, h_level: int) -> str:
        html = """
            <h{}>Program: {!r}</h{}>
            The following plot shows the mean score per input distribution for every implementation.
        """.format(h_level, self.name, h_level)
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


class ProgramCategory(BaseObject):
    """
    Represents a specific abstract program that gives the specification for several implementations (aka "program"s).
    """

    def __init__(self, parent: 'Language', name: str, programs: t.List[Program]):
        super().__init__(name, itod_from_list(programs, lambda x: x.name))
        self.parent = parent
        self.programs = self.children # type: t.Dict[str, Program]

    @classmethod
    def from_config_dict(cls, parent: 'Language', config: dict) -> 'ProgramCategory':
        typecheck(config, Dict({
            "category": Str(),
            "programs": List(Dict(all_keys=False))
        }))
        cat = cls(parent, config["category"], [])
        cat.programs = InsertionTimeOrderedDict()
        for prog_conf in config["programs"]:
            prog = Program.from_config_dict(cat, prog_conf)
            cat.programs[prog.name] = prog
            cat.children[prog.name] = prog
        return cat

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.programs)

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
        base_file_name += "__program_category_" + html_escape_property(self.name)
        html = """
            <h{}>{}</h{}>
        """.format(h_level, self.name, h_level)
        if len(self.children) > 1:
            html += self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(rel_mean_property))
            html += self.table_html_for_vals_per_impl(common_columns)
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
                    html += self.boxplot_html_for_data("mean score", base_file_name + "__input_"
                                                       + html_escape_property(input),
                                          self.get_x_per_impl_and_input(rel_mean_property, input))
                    html += self.table_html_for_vals_per_impl(common_columns,
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
                                p_in_val.impls[name] = Implementation.from_config_dict(p_in_val, impl_conf)
        return lang

    def __getitem__(self, name: str) -> ProgramCategory:
        return self.categories[name]

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

    def process_result_file(self, file: str, property: str = "task-clock"):
        with open(file, "r") as f:
            self.set_run_data_from_result_dict(yaml.load(f), property)

    def build(self, base_dir: str, multiprocess: bool = True) -> t.List[dict]:
        #path = self._create_own_dir(base_dir)
        return self._buildup_dict(base_dir, self.categories, multiprocess=True)

    def create_temci_run_file(self, base_build_dir: str, file: str):
        run_config = self.build(base_build_dir)
        with open(file, "w") as f:
            print(yaml.dump(run_config, Dumper=yaml.RoundTripDumper), file=f)

    def get_box_plot_html(self, base_file_name: str) -> str: # a box plot over the mean scores per category
        scores_per_impl = self.get_scores_per_impl()
        singles = []
        for impl in scores_per_impl:
            scores = scores_per_impl[impl]
            name = "mean score"
            data = RunData({name: scores}, {"description": impl})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name, singles)

    def get_html2(self, base_file_name: str, h_level: int, with_header: bool = True, multiprocess: bool = False):
        base_file_name += "__program_category_" + html_escape_property(self.name)
        html = ""
        if with_header:
            html += """
            <h{}>Language: {}</h{}>
            """.format(h_level, self.name, h_level)
        else:
            h_level -= 1
        if len(self.children) > 1:
            html += self.boxplot_html_for_data("mean score", base_file_name, self.get_x_per_impl(rel_mean_property))
            html += self.table_html_for_vals_per_impl(common_columns)
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
                html += self.boxplot_html_for_data("mean score", base_file_name + "__input_" + str(n),
                                          self.get_x_per_impl_and_input(rel_mean_property, n))
                html += self.table_html_for_vals_per_impl(common_columns,
                                                          lambda property: self.get_x_per_impl_and_input(property, n))

        objs = []
        for (i, cat) in enumerate(self.categories):
            objs.append((i, cat, base_file_name + "_" + html_escape_property(cat), h_level + 1))
        map_func = map
        if multiprocess: # doesn't work (fix warning issue of seaborn)
            pool = multiprocessing.Pool(2)
            map_func = pool.map
        html += "\n".join(map_func(self._get_html2_for_category, objs))
        return html

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
        <link rel="stylesheet" href="file:resources/style.css">
        <script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery-ui-1.9.1.custom.min.js"></script>
        <script src="http://gregfranko.com/jquery.tocify.js/js/jquery.tocify.js"></script>
        <script type="text/javascript" src="https://cdn.mathjax.org/mathjax/latest/MathJax.js?config=TeX-AMS-MML_SVG"></script>
        <script src="file:resources/script.js"></script>
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
            f.write(self.get_full_html(os.path.join(base_dir), html_func))

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

AV_GHC_VERSIONS = ["7.0.1", "7.2.1", "7.4.1", "7.6.1", "7.8.1", "7.10.1", "8.0.1"]
""" These are (currently) the versions installable via the ppa on https://launchpad.net/~hvr/+archive/ubuntu/ghc
Older versions can't be installed due to version conflicts and missing libraries """


def haskel_config(inputs_per_category: InputsPerCategory, optimisation: str, ghc_versions: t.List[str] = None) \
        -> ConfigDict:
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
    
    
    def ghc_impl(version: str) -> t.Dict[str, str]:
        return {
            "name": "ghc-" + version,
            "build_cmd": "cp {{file}} {{bfile}}.{{impl}}.hs; PATH={impl_dir}:$PATH ghc {O} -XBangPatterns "
                         "{{bfile}}.{{impl}}.hs -XCPP -XGeneralizedNewtypeDeriving -XTypeSynonymInstances "
                         "-XFlexibleContexts -XUnboxedTuples -funbox-strict-fields -XScopedTypeVariables "
                         "-XFlexibleInstances -funfolding-use-threshold=32 -XMagicHash -threaded"
                .format(O=optimisation, impl_dir=ghc_impl_dir(version)),
            "run_cmd": "./{{bfile}}.{{impl}} {{input}} > /dev/null".format(ghc_impl_dir(version))
        }
    
        
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
            ghc_impl(version) for version in AV_GHC_VERSIONS
        ]
    }

    return config


def process(config: ConfigDict, name: str = None, build_dir: str = None, build: bool = True, benchmark: bool = True,
            report: bool = True, temci_runs: int = 15, temci_options: str = "--discarded_blocks 1",
            temci_stop_start: bool = True, report_dir: str = None, property: str = "task-clock"):
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
    report_dir = report_dir or name + "_report"
    os.system("mkdir -p {} {}".format(build_dir, report_dir))
    if build:
        lang.create_temci_run_file(build_dir, temci_run_file)
    if benchmark:
        stop_start_str = "--stop_start" if temci_stop_start else ""
        cmd = "temci exec {temci_run_file} --runs {temci_runs} {temci_options} {stop_start_str} --out {temci_result_file}"\
            .format(**locals())
        #print(cmd)
        os.system(cmd)
    if report:
        lang.process_result_file(temci_result_file, property)
        lang.store_html(report_dir, clear_dir=True, html_func=lang.get_html2)


MODE = "haskell_full"


if MODE == "haskell_full":

    for opti in ["", "-O", "-O2", "-Odph"]:
        try:
            config = replace_run_with_build_cmd(haskel_config(empty_inputs(INPUTS_PER_CATEGORY), opti))
            process(config, "compile_time_haskell_" + opti, temci_runs=30, build=False, benchmark=False)
            #shutil.rmtree("/tmp/compile_time_haskell_" + opti)
        except OSError as ex:
            logging.error(ex)
            pass
        os.sync()
        #time.sleep(60)

    for opti in  reversed(["", "-O", "-O2", "-Odph", "-Odph"]):
        try:
            config = haskel_config(INPUTS_PER_CATEGORY, opti)
            process(config, "haskell" + opti, temci_options=" --discarded_blocks 1 --nice --other_nice", build=False, benchmark=False, property="task-clock")
            logging.info("processed")
            shutil.rmtree("/tmp/haskell" + opti)
        except BaseException as ex:
            logging.exception(ex)
            pass
        os.sync()
        #time.sleep(60)