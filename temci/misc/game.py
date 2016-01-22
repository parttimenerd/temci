"""
Benchmarks game inspired comparison of different implementations for a given language.
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

if util.can_import("scipy"):
    import scipy.stats as stats
    import ruamel.yaml as yaml

from temci.tester.report import HTMLReporter2, html_escape_property

FIG_WIDTH = 15
FIG_HEIGHT_PER_ELEMENT = 1.5

class BaseObject:

    def __init__(self, name: str):
        self.name = name

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

    def _buildup_dict(self, path: str, base_objs: t.Union[t.List['BaseObject'], t.Dict[str, 'BaseObject']],
                      multiprocess: bool = False) -> t.List[dict]:
        objs = sorted(base_objs)
        if isinstance(base_objs, dict):
            objs = []
            for key in sorted(base_objs):
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
        d = sp.store_figure(base_file_name, fig_width=FIG_WIDTH, fig_height=max(len(singles) * FIG_HEIGHT_PER_ELEMENT, 4))
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

class Implementation(BaseObject):

    def __init__(self, parent: 'ProgramWithInput', name: str, run_cmd: str, build_cmd: str = None,
                 run_data: t.List[t.Union[int, float]] = None):
        super().__init__(name)
        typecheck_locals(parent=T(ProgramWithInput))
        self.parent = parent
        self.run_cmd = run_cmd
        self.build_cmd = build_cmd
        self.run_data = run_data

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
            pprint(build_cmd)
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
                "input": prog_in.input
            },
            "run_config": {
                "run_cmd": run_cmd,
                "cwd": path
            }
        }


StatisticalPropertyFunc = t.Callable[[SingleProperty], float]
""" Get's passed the SingleProperty object to process and min mean """
rel_mean_func = lambda x, min: x.mean() / min
rel_std_dev_func = lambda x, min: x.std_dev() / min

class ProgramWithInput(BaseObject):

    def __init__(self, parent: 'Program', input: str, impls: t.List[Implementation], id: int):
        super().__init__(str(id))
        self.parent = parent
        self.input = input
        self.impls = {} # type: t.Dict[str, Implementation]
        for impl in impls:
            self.impls[impl.name] = impl

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.impls)

    def __getitem__(self, name: str) -> Implementation:
        return self.impls[name]

    def get_single(self):
        data = {}
        for impl in self.impls:
            data[impl] = self.impls[impl]
        return Single(RunData(data))

    def get_single_properties(self) -> t.List[t.Tuple[str, SingleProperty]]:
        return [(impl, self.impls[impl].get_single_property()) for impl in sorted(self.impls)]

    def get_means_rel_to_best(self) -> t.Dict[str, float]:
        return self.get_statistical_properties_for_each(rel_mean_func)

    def get_statistical_properties_for_each(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        sps = self.get_single_properties()
        best_mean = min(sp.mean() for (impl, sp) in sps)
        d = {}
        for (impl, sp) in sps:
            d[impl] = func(sp, best_mean)
        return d

    def get_box_plot_html(self, base_file_name: str) -> str:
        singles = []
        for impl in sorted(self.impls.keys()):
            impl_val = self.impls[impl]
            data = RunData({self.name: impl_val.run_data}, {"description": "{!r}|{}".format(self.input, impl)})
            singles.append(SingleProperty(Single(data), data, self.name))
        return self.boxplot_html(base_file_name, singles)

    def get_html(self, base_file_name: str, h_level: int) -> str:
        sp = None # type: SingleProperty
        scores = self.get_means_rel_to_best()
        columns = [
            {
                "name": "implementation",
                "func": lambda x, sp: x.name,
                "format": "{}"
            }, {
                "name": "n",
                "func": lambda x, sp: sp.observations(),
                "format": "{:5d}"
            }, {
                "name": "mean",
                "func": lambda x, sp: sp.mean(),
                "format": "{:5.5f}"
            }, {
                "name": "mean / best mean",
                "func": lambda x, sp: scores[x.name],
                "format": "{:5.5f}"
            }, {
                "name": "std / mean",
                "func": lambda x, sp: sp.std_dev_per_mean(),
                "format": "{:5.2%}"
            }, {
                "name": "median",
                "func": lambda x, sp: sp.median(),
                "format": "{:5.5f}"
            }
        ]
        html = """
        <h{h}>Input: {input}</h{h}>
        {box_plot}
        <table class="table">
            <tr>{header}</tr>
        """.format(h=h_level, input=repr(self.input), box_plot=self.get_box_plot_html(base_file_name),
                   header="".join("<th>{}</th>".format(elem["name"]) for elem in columns))
        for impl in sorted(self.impls.keys()):
            impl_val = self.impls[impl]
            sp = impl_val.get_single_property()
            col_vals = []
            for elem in columns:
                col_vals.append(elem["format"].format(elem["func"](impl_val, sp)))
            html += """
                <tr>{}</tr>
            """.format("".join("<td>{}</td>".format(col_val) for col_val in col_vals))
        return html + "</table>"


class Program(BaseObject):

    def __init__(self, parent: 'ProgramCategory', name: str, file: str,
                 prog_inputs: t.Dict[str, ProgramWithInput] = None, copied_files: t.List[str] = None):
        super().__init__(name)
        self.parent = parent
        self.file = file
        self.prog_inputs = prog_inputs or {} # type: t.Dict[str, ProgramWithInput]
        self.copied_files = copied_files or [] # type: t.List[str]

    @classmethod
    def from_config_dict(cls, parent: 'ProgramCategory', config: dict) -> 'Implementation':
        typecheck(config, Dict({
            "program": Str(),
            "file": FileName(allow_non_existent=False),
            "inputs": List(Str()) | NonExistent(),
            "copied_files": List(Str()) | NonExistent(),
            "impls": List(Dict(all_keys=False)) | NonExistent()
        }))
        program = cls(parent, name=config["program"], file=config["file"],
                       copied_files=config["copied_files"] if "copied_files" in config else [])
        inputs = config["inputs"] if "inputs" in config else [""]
        program.prog_inputs = {}
        for (i, input) in enumerate(inputs):
            prog_input = ProgramWithInput(program, input, [], i)
            program.prog_inputs[input] = prog_input
            impls = config["impls"] if "impls" in config else []
            prog_input.impls = {}
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
        singles = []
        for input in sorted(self.prog_inputs.keys()):
            prog_in = self.prog_inputs[input]
            for impl in sorted(prog_in.impls):
                impl_val = prog_in.impls[impl]
                data = RunData({self.name: impl_val.run_data}, {"description": "{!r}|{}".format(input, impl)})
                singles.append(SingleProperty(Single(data), data, self.name))
        return self.boxplot_html(base_file_name, singles)

    def get_box_plot_score_per_input_html(self, base_file_name: str) -> str:
        singles = []
        for input in sorted(self.prog_inputs.keys()):
            prog_in = self.prog_inputs[input]
            vals = list(prog_in.get_means_rel_to_best().values())
            data = RunData({prog_in.name: vals}, {"description": prog_in.name})
            singles.append(SingleProperty(Single(data), data, prog_in.name))
        return self.boxplot_html(base_file_name + "__per_input_", singles)

    def get_html(self, base_file_name: str, h_level: int) -> str:
        html = """
            <h{}>Program: {!r}</h{}>
        """.format(h_level, self.name, h_level)
        html += """
            Measured values per implementation and input
            <p>
        """
        html += self.get_box_plot_html(base_file_name)
        scores = self.get_impl_mean_scores()
        std_devs = self.get_statistical_property_scores(rel_std_dev_func)
        html += """
            </p>
            <table class="table">
                <tr><th>implementation</th><th>geom mean over means relative to best (per input) aka mean score</th>
                    <th>... std dev rel. to the best mean</th>
                </tr>
        """
        for impl in sorted(scores.keys()):
            html += """
                <tr><td>{}</td><td>{}</td><td>{}</td></tr>
            """.format(impl, scores[impl], std_devs[impl])
        html += "</table>"
        scores_per_input = self.get_statistical_property_scores_per_input(rel_mean_func)
        std_devs_per_input = self.get_statistical_property_scores_per_input(rel_std_dev_func)
        if len(scores_per_input) > 1:
            html += "<p>"
            html += self.get_box_plot_score_per_input_html(base_file_name)
            html += """
                </p>
                <table class="table">
                    <tr><th>input</th><th>geom mean over means relative to best (per impl) aka mean score</th>
                        <th>... std dev rel. to the best mean</th>
                    </tr>
            """
            for input in sorted(scores_per_input.keys()):
                html += """
                    <tr><td>{}</td><td>{}</td><td>{}</td></tr>
                """.format(impl, scores_per_input[input], std_devs_per_input[input])
            html += "</table>"
        impl_names = sorted(list(scores.keys()))
        for (i, input) in enumerate(sorted(self.prog_inputs.keys())):
            app = html_escape_property(input)
            if len(app) > 20:
                app = str(i)
            html += self.prog_inputs[input].get_html(base_file_name + "_" + app, h_level + 1)
        return html

    def get_impl_mean_scores(self) -> t.Dict[str, float]:
        """
        Geometric mean over the means relative to best per implementation (per input).
        """
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        d = {} # type: t.Dict[str, t.List[float]]
        for input in sorted(self.prog_inputs):
            rel_vals = self.prog_inputs[input].get_statistical_properties_for_each(func)
            for impl in rel_vals:
                if impl not in d:
                    d[impl] = []
                d[impl].append(rel_vals[impl])
        scores = {}
        for impl in d:
            scores[impl] = stats.gmean(d[impl])
        return scores

    def get_statistical_property_scores_per_input(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        d = {}
        for input in self.prog_inputs:
            d[input] = stats.gmean(list(self.prog_inputs[input].get_statistical_properties_for_each(func).values()))
        return d

    def _get_inputs_that_contain_impl(self, impl: str) -> t.List[ProgramWithInput]:
        return list(filter(lambda x: impl in x.impls, self.prog_inputs.values()))


class ProgramCategory(BaseObject):
    """
    Represents a specific abstract program that gives the specification for several implementations (aka "program"s).
    """

    def __init__(self, parent: 'Language', name: str, programs: t.List[Program]):
        super().__init__(name)
        self.parent = parent
        self.programs = {} # type: t.Dict[str, Program]
        for prog in programs:
            self.programs[prog.name] = programs

    @classmethod
    def from_config_dict(cls, parent: 'Language', config: dict) -> 'ProgramCategory':
        typecheck(config, Dict({
            "category": Str(),
            "programs": List(Dict(all_keys=False))
        }))
        cat = cls(parent, config["category"], [])
        cat.programs = {}
        for prog_conf in config["programs"]:
            prog = Program.from_config_dict(cat, prog_conf)
            cat.programs[prog.name] = prog
        return cat

    def build(self, base_dir: str) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.programs)

    def __getitem__(self, name: str) -> Program:
        return self.programs[name]

    def get_box_plot_html(self, base_file_name: str) -> str: # a box plot over the mean scores per sub program
        scores_per_impl = self.get_scores_per_impl()
        singles = []
        for impl in sorted(scores_per_impl.keys()):
            scores = scores_per_impl[impl]
            name = "mean score"
            data = RunData({name: scores}, {"description": impl})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name, singles)

    def get_box_plot_html_per_input(self, base_file_name: str) -> str:
        scores_per_input = self.get_statistical_property_scores_per_input(rel_mean_func)
        singles = []
        for input in sorted(scores_per_input.keys()):
            scores = scores_per_input[input]
            name = "mean score"
            descr = list(self.programs.values())[0].prog_inputs[input].name
            data = RunData({name: scores}, {"description": descr})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name + "__per_input_", singles)

    def get_html(self, base_file_name: str, h_level: int) -> str:
        html = """
            <h{}>{}</h{}>
        """.format(h_level, self.name, h_level)
        html += """
            Mean scores per implementation for this program category
            <p>
        """
        html += self.get_box_plot_html(base_file_name)
        scores = self.get_impl_mean_scores()
        std_devs = self.get_statistical_property_scores(rel_std_dev_func)
        html += """
            </p>
            <table class="table">
                <tr><th>implementation</th><th>geom mean over means relative to best (per input and program) aka mean score</th>
                <th>... std devs relative to the best means </th>
                </tr>
        """
        for impl in sorted(scores.keys()):
            html += """
                <tr><td>{}</td><td>{}</td><td>{}</td></tr>
            """.format(impl, scores[impl], std_devs[impl])
        html += "</table>"
        scores_per_input = self.get_statistical_property_score_per_input(rel_mean_func)
        if len(scores_per_input) > 1:
            std_devs_per_input = self.get_statistical_property_score_per_input(rel_std_dev_func)
            html += """
                Mean scores per input for this program category
                <p>
            """
            html += self.get_box_plot_html_per_input(base_file_name)
            html += """
                </p>
                <table class="table">
                    <tr><th>input</th><th>geom mean over means relative to best (per input and program) aka mean score</th>
                    <th>... std devs relative to the best means </th>
                    </tr>
            """
            for input in sorted(scores_per_input.keys()):
                html += """
                    <tr><td>{}</td><td>{}</td><td>{}</td></tr>
                """.format(impl, scores_per_input[input], std_devs_per_input[input])
            html += "</table>"
        impl_names = sorted(list(scores.keys()))
        for (i, prog) in enumerate(sorted(self.programs)):
            html += self.programs[prog].get_html(base_file_name + "_" + html_escape_property(prog), h_level + 1)
        return html

    def get_scores_per_impl(self) -> t.Dict[str, t.List[float]]:
        return self.get_statistical_property_scores_per_impl(rel_mean_func)

    def get_statistical_property_scores_per_impl(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        impl_scores = {}
        for prog in sorted(self.programs):
            scores = self.programs[prog].get_impl_mean_scores()
            for impl in scores:
                if impl not in impl_scores:
                    impl_scores[impl] = []
                impl_scores[impl].append(scores[impl])
        return impl_scores

    def get_statistical_property_scores_per_input(self, func: StatisticalPropertyFunc) -> t.Dict[str, t.List[float]]:
        input_scores = {}
        for prog in sorted(self.programs):
            scores = self.programs[prog].get_statistical_property_scores_per_input(func)
            for impl in scores:
                if impl not in input_scores:
                    input_scores[impl] = []
                input_scores[impl].append(scores[impl])
        return input_scores

    def get_impl_mean_scores(self) -> t.Dict[str, float]:
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        ret = {}
        scores_per_impl = self.get_statistical_property_scores_per_impl(func)
        for impl in scores_per_impl:
            ret[impl] = stats.gmean(scores_per_impl[impl])
        return ret

    def get_statistical_property_score_per_input(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        ret = {}
        scores_per_input = self.get_statistical_property_scores_per_input(func)
        for impl in scores_per_input:
            ret[impl] = stats.gmean(scores_per_input[impl])
        return ret

class Language(BaseObject):

    def __init__(self, name: str, categories: t.List[ProgramCategory]):
        super().__init__(name)
        self.categories = {} # type: t.Dict[str, ProgramCategory]
        for cat in categories:
            self.categories[cat.name] = cat

    @classmethod
    def from_config_dict(cls, config: dict) -> 'Language':
        typecheck(config, Dict({
            "language": Str(),
            "categories": List(Dict(all_keys=False)),
            "impls": List(Dict({"name": Str()}, all_keys=False)) | NonExistent()
        }))
        lang = cls(config["language"], [])
        lang.categories = {}
        for cat_conf in config["categories"]:
            cat = ProgramCategory.from_config_dict(lang, cat_conf)
            lang.categories[cat.name] = cat
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
            except KeyError:
                pass

    def process_result_file(self, file: str, property: str = "task-clock"):
        with open(file, "r") as f:
            self.set_run_data_from_result_dict(yaml.load(f), property)

    def build(self, base_dir: str, multiprocess: bool = True) -> t.List[dict]:
        path = self._create_own_dir(base_dir)
        return self._buildup_dict(path, self.categories, multiprocess=True)

    def create_temci_run_file(self, base_build_dir: str, file: str):
        with open(file, "w") as f:
            print(yaml.dump(self.build(base_build_dir), Dumper=yaml.RoundTripDumper), file=f)

    def get_box_plot_html(self, base_file_name: str) -> str: # a box plot over the mean scores per category
        scores_per_impl = self.get_scores_per_impl()
        singles = []
        for impl in sorted(scores_per_impl.keys()):
            scores = scores_per_impl[impl]
            name = "mean score"
            data = RunData({name: scores}, {"description": impl})
            singles.append(SingleProperty(Single(data), data, name))
        return self.boxplot_html(base_file_name, singles)

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
        for impl in sorted(scores.keys()):
            html += """
                <tr><td>{}</td><td>{}</td><td>{}</td></tr>
            """.format(impl, scores[impl], std_devs[impl])
        html += "</table>"
        objs = []
        for (i, cat) in enumerate(sorted(self.categories)):
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

    def get_full_html(self, base_file_name: str) -> str:
        resources_path = os.path.abspath(os.path.join(os.path.dirname(report.__file__), "report_resources"))
        shutil.copytree(resources_path, os.path.join(os.path.dirname(base_file_name), "resources"))
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
                <footer class="footer">Generated by temci in {timespan}</footer>
             </div>
          </div>
        </div>
    </body>
</html>
        """
        lang = self.name
        comparing_str = util.join_strs(sorted(self.get_scores_per_impl()))
        inner_html = self.get_html(base_file_name, 2, with_header=False)
        import humanfriendly
        timespan = humanfriendly.format_timespan(time.time() - START_TIME)
        return html.format(**locals())

    def store_html(self, base_dir: str, clear_dir: bool = False):
        assert isinstance(base_dir, DirName())
        if not os.path.exists(base_dir):
            os.mkdir(base_dir)
        elif clear_dir:
            shutil.rmtree(base_dir)
            self.store_html(base_dir, clear_dir=False)
            return
        with open(os.path.join(base_dir, "{}_report.html".format(self.name)), "w") as f:
            f.write(self.get_full_html(os.path.join(base_dir, "{}_fig".format(self.name))))

    def get_scores_per_impl(self) -> t.Dict[str, t.List[float]]:
        return self.get_statistical_property_scores_per_impl(rel_mean_func)

    def get_statistical_property_scores_per_impl(self, func: StatisticalPropertyFunc) -> t.Dict[str, t.List[float]]:
        impl_scores = {}
        for cat in self.categories:
            scores = self.categories[cat].get_statistical_property_scores(func)
            for impl in scores:
                if impl not in impl_scores:
                    impl_scores[impl] = []
                impl_scores[impl].append(scores[impl])
        return impl_scores

    def get_impl_mean_scores(self) -> t.Dict[str, float]:
        return self.get_statistical_property_scores(rel_mean_func)

    def get_statistical_property_scores(self, func: StatisticalPropertyFunc) -> t.Dict[str, float]:
        ret = {}
        scores_per_impl = self.get_statistical_property_scores_per_impl(func)
        for impl in scores_per_impl:
            ret[impl] = stats.gmean(scores_per_impl[impl])
        return ret


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


def bench_program(category: str, ending: str, number: int = 1) -> dict:
    return {
        "program": str(number),
        "file": bench_file(category, ending, number),
        "inputs": [input.replace("$INPUT", BENCH_PATH + "/../bencher/input") for input in inputs[category]]
    }


def bench_category(category: str, ending: str, numbers: t.List[int] = None) -> dict:
    if numbers is None:
        numbers = []
        for i in range(1, 10):
            if os.path.exists(bench_file(category, ending, i)):
                numbers.append(i)
    #numbers = [numbers[0]]
    programs = [bench_program(category, ending, number) for number in numbers]
    return {
        "category": category,
        "programs": programs
    }


def bench_categories(ending: str) -> t.List[dict]:
    categories = []
    for cat in sorted(inputs):
        if os.path.exists(bench_file(cat, ending)):
            categories.append(bench_category(cat, ending))
    return categories


def first_inputs(inputs: t.Dict[str, t.List[str]]) -> t.Dict[str, t.List[str]]:
    ret = {}
    for key in inputs:
        if len(inputs[key]) > 0:
            ret[key] = [inputs[key][0]]
    return ret


def last_inputs(inputs: t.Dict[str, t.List[str]]) -> t.Dict[str, t.List[str]]:
    ret = {}
    for key in inputs:
        if len(inputs[key]) > 0:
            ret[key] = [inputs[key][-1]]
    return ret


def prepend(item: str, array: t.List[str]) -> t.List[str]:
    return [item + elem for elem in array]


def replace_run_with_build_cmd(config_dict: t.Dict[str, t.Union[str, t.List[dict]]]):
    config_dict = copy.deepcopy(config_dict)
    for impl_dict in config_dict["impls"]:
        impl_dict["run_cmd"] = impl_dict["build_cmd"] + " &> /dev/null"
        del(impl_dict["build_cmd"])
    return config_dict


BENCH_PATH = "/home/parttimenerd/benchmarksgame/bench"
inputs = { # type: t.Dict[str, t.List[str]]
    "binarytrees": ["12", "16"], # game: [12, 16, 20]
    "chameneosredux": ["60000", "600000", "6000000"], # 60000 600000 6000000
    "fannkuchredux": ["8", "9", "10"], # game: ["10", "11", "12"]
    "fasta": ["25000", "250000", "2500000"], # game: ["250000", "2500000", "25000000"]
    "fastaredux": ["25000", "250000", "2500000"], # 250000 2500000 25000000
    "knucleotide": prepend("$INPUT/knucleotide-input.txt ", ["25000", "250000", "2500000"]), # 250000 2500000 25000000
    "mandelbrot": ["1000", "4000", "16000"],
    "meteor": ["2098"],
    "nbody": ["50000", "500000", "5000000"], # 500000 5000000 50000000
    "pidigits": ["2000", "6000", "10000"],
    "regexdna": prepend("$INPUT/regexdna-input.txt ", ["50", "50000", "500000"]), # 50000 500000 5000000
    "revcomp": prepend("$INPUT/revcomp-input.txt ", ["250000", "2500000", "25000000"]), # 250000 2500000 25000000
    "spectralnorm": ["500", "3000", "5500"],
    "threadring": ["5000", "50000", "500000"] # 500000 5000000 50000000
}

#inputs = first_inputs(inputs)

php_config = {
    "language": "php",
    "categories": [
        bench_category("binarytrees", "php"),
        bench_category("fannkuchredux", "php", [1, 2])#,
        #bench_category("knucleotide", "php", [4])
    ],
    "impls": [
        {
            "name": "php",
            "run_cmd": "php {file} {input}"
        }, {
            "name": "hhvm",
            "run_cmd": "hhvm {file} {input}"
        }
    ]
}

c_config = {
    "language": "c",
    "categories": [
        bench_category("binarytrees", "gcc"),
        bench_category("chameneosredux", "gcc", [2]),
        bench_category("fannkuchredux", "gcc", [1, 5]),
        bench_category("fasta", "gcc", [1, 4, 5]),
        bench_category("fastaredux", "gcc"),
        #bench_category("knucleotide", "gcc", [9]) # doesn't compile
        bench_category("mandelbrot", "gcc", [1, 2, 3, 4, 6, 9]),
        bench_category("meteor", "gcc"),
        bench_category("nbody", "gcc"),
        bench_category("pidigits", "gcc"),
        #bench_category("regexdna", "gcc", [1, 2]),      # runs almost infinitely
        bench_category("revcomp", "gcc", [1]),
        bench_category("spectralnorm", "gcc", [1]),
        bench_category("threadring", "gcc")
    ],
    "impls": [
        {
            "name": "gcc",
            "build_cmd": "cp {file} {bfile}.c; gcc {bfile}.c -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp "
                         "-D_GNU_SOURCE -Doff_t=__off64_t -fopenmp -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 "
                         "-lapr-1 -lgomp -lm -std=c99 -mfpmath=sse -msse3 -I/usr/include/glib-2.0 "
                         "-I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre -o {bfile}",
            "run_cmd": "./{bfile} {input} > /dev/null"
        }, {
            "name": "clang",
            "build_cmd": "cp {file} {bfile}.c; clang-3.7 {bfile}.c -I/usr/include/tcl8.6 -ltcl8.4 -fopenmp=libgomp "
                         "-lglib-2.0 -lgmp -D_GNU_SOURCE -Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 "
                         "-I/usr/include/apr-1.0 -lapr-1  -lm -std=c99 -mfpmath=sse -msse3 -I/usr/include/glib-2.0 "
                         "-I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre -o {bfile}",
            "run_cmd": "./{bfile} {input} > /dev/null"
        }
    ]
}

cparser_config = {
    "language": "c",
    "categories": [
        bench_category("binarytrees", "gcc", [1, 3, 5]),
        bench_category("chameneosredux", "gcc", [2]),
        bench_category("fannkuchredux", "gcc", [1, 5]),
        bench_category("fasta", "gcc", [1, 4, 5]),
        bench_category("fastaredux", "gcc"),
        #bench_category("knucleotide", "gcc", [9]) # doesn't compile
        bench_category("mandelbrot", "gcc", [2, 9]),
        bench_category("meteor", "gcc"),
        bench_category("nbody", "gcc", [1, 2, 3, 6]),
        bench_category("pidigits", "gcc"),
        #bench_category("regexdna", "gcc", [1, 2]),      # runs almost infinitely
        bench_category("revcomp", "gcc", [1]),
        bench_category("spectralnorm", "gcc", [1]),
        bench_category("threadring", "gcc", [1, 2, 3])
    ],
    "impls": [
        {
            "name": "gcc",
            "build_cmd": "cp {file} {bfile}.c; gcc {bfile}.c -w -O3 -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp -D_GNU_SOURCE "
                         "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1 -lgomp -lm -std=c99 "
                         " -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                         " -lpthread -o {bfile}.{impl_escaped}",
            "run_cmd": "./{bfile} {input} > /dev/null"
        }, {
            "name": "clang",
            "build_cmd": "cp {file} {bfile}.c; clang-3.7 {bfile}.c -w -O3 -I/usr/include/tcl8.6 -ltcl8.4 "
                         "-fopenmp=libgomp -lglib-2.0 -lgmp -D_GNU_SOURCE "
                         "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1  -lm -std=c99 "
                         "-I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                         "-lpthread -o {bfile}.{impl_escaped}",
            "run_cmd": "./{bfile}.{impl_escaped} {input} > /dev/null"
        }, {
            "name": "cparser",
            "build_cmd": "cp {file} {bfile}.c; cparser {bfile}.c -w -O3 -I/usr/include/tcl8.6 -ltcl8.4 -lglib-2.0 -lgmp -D_GNU_SOURCE "
                         "-Doff_t=__off64_t -D_FILE_OFFSET_BITS=64 -I/usr/include/apr-1.0 -lapr-1 -lgomp -lm -std=c99 "
                         " -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include -lglib-2.0 -lpcre "
                         " -lpthread -o {bfile}.{impl_escaped}",
            "run_cmd": "./{bfile}.{impl_escaped} {input} > /dev/null"
        }
    ]
}

AV_GHC_VERSIONS = ["7.0.1", "7.2.1", "7.4.1", "7.6.1", "7.8.1", "7.10.1", "8.0.1"]
""" These are (currently) the versions installable via the ppa on https://launchpad.net/~hvr/+archive/ubuntu/ghc
Older versions can't be installed due to version conflicts and missing libraries """

def ghc_impl_dir(version: str = "8.0.1") -> str:
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
            .format(O=GHC_O_APP, impl_dir=ghc_impl_dir(version)),
        "run_cmd": "./{{bfile}}.{{impl}} {{input}} > /dev/null".format(ghc_impl_dir(version))
    }

GHC_O_APP = "-O -Odph " # -fmax-simplifier-iterations=1000 -fsimplifier-phases=20" # ""

# Note to the removed programs:
# These either don't compile with all ghc versions properly or use additional hackage packages
# The latter is bad because installing the package for all ghc's isn't to costly

haskell_config = {
    "language": "haskell",
    "categories": [
        bench_category("binarytrees", "ghc", [1]),
        ###bench_category("chameneosredux", "ghc", [4]),
        bench_category("fannkuchredux", "ghc", [1, 3]),
        bench_category("fasta", "ghc", [1]),
        ###bench_category("knucleotide", "ghc"), # seems to run forever
        bench_category("mandelbrot", "ghc"),
        bench_category("meteor", "ghc"),
        bench_category("nbody", "ghc", [2]),
        bench_category("pidigits", "ghc"),
        ###bench_category("regexdna", "ghc"), # uses package PCRE
        ###bench_category("revcomp", "ghc", [2]), # seems to runs forever
        bench_category("spectralnorm", "ghc", [2]),
        ###bench_category("threadring", "ghc")    # doesn't compile properly
    ],
    "impls": [
        ghc_impl(version) for version in AV_GHC_VERSIONS
    ]
}

#cparser_config = replace_run_with_build_cmd(cparser_config)
#pprint(Language.from_config_dict(haskell_config).build("/tmp/"))
php = Language.from_config_dict(haskell_config)
php.create_temci_run_file("/tmp/", "abc")
logging.info("run temci")
#os.system("temci exec abc --discarded_blocks 1 --stop_start --drop_fs_caches --runs 15 --out haskell.yaml")
php.process_result_file("haskell.yaml")
php.store_html("haskell", clear_dir=True)

php = Language.from_config_dict(cparser_config)
#php.create_temci_run_file("/tmp/", "abc")
logging.info("run temci")
#os.system("temci exec abc --discarded_blocks 1 --stop_start --drop_fs_caches --nice --other_nice --runs 15 --out cparser.yaml")
php.process_result_file("cparser.yaml")
php.store_html("cparser", clear_dir=True)

inputs = first_inputs(inputs)

php = Language.from_config_dict(replace_run_with_build_cmd(haskell_config))
#php.create_temci_run_file("/tmp/", "abc")
#logging.info("run temci")
#os.system("temci exec abc --discarded_blocks 1 --stop_start --drop_fs_caches --nice --other_nice --runs 15 --out haskell_c_time.yaml")
php.process_result_file("haskell_c_time.yaml")
php.store_html("haskell_c_time", clear_dir=True)

php = Language.from_config_dict(replace_run_with_build_cmd(cparser_config))
php.create_temci_run_file("/tmp/", "abc")
#logging.info("run temci")
#os.system("temci exec abc --discarded_blocks 1 --stop_start --drop_fs_caches --nice --other_nice --runs 15 --out cparser_c_time.yaml")
php.process_result_file("cparser_c_time.yaml")
php.store_html("cparser_c_time", clear_dir=True)

#php.process_result_file("cparser.yaml")
#php.store_html("cparser", clear_dir=True)