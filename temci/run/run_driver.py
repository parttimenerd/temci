"""
This modules contains the base run driver, needed helper classes and registries.
"""
import os

import datetime
import re
import shutil
import pytimeparse, numpy, math

from temci.utils.settings import Settings
from temci.utils.typecheck import NoInfo
from temci.utils.vcs import VCSDriver
from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register
from .cpuset import CPUSet
from copy import deepcopy
import logging, time, random, subprocess
from collections import namedtuple
import shlex, gc
from fn import _
import typing as t

class RunDriverRegistry(AbstractRegistry):
    """
    The registry for run drivers.
    """

    settings_key_path = "run"
    use_key = "driver"
    use_list = False
    default = "exec"
    registry = {}


class RunProgramBlock:
    """
    An object that contains every needed information of a program block.
    """

    def __init__(self, id: int, data, attributes: dict, run_driver: type = None):
        """

        :param data:
        :param attributes:
        :param type_scheme:
        :return:
        """
        if run_driver is not None:
            self.run_driver_class = run_driver
        else:
            self.run_driver_class = RunDriverRegistry.get_class(RunDriverRegistry.get_used())
        self.type_scheme = self.run_driver_class.block_type_scheme
        self.data = self.run_driver_class.block_default
        self.data.update(data)
        self.attributes = attributes
        self.is_enqueued = False
        self.id = id
        """Is this program block enqueued in a run worker pool queue?"""

    def __getitem__(self, key: str):
        """
        Returns the value associated with the given key.
        """
        return self.data[key]

    def __setitem__(self, key: str, value):
        """
        Sets the value associated with the passed key to the new value.
        :param key: passed key
        :param value: new value
        :raises TypeError if the value hasn't the expected type
        """
        value_name = "run programm block[{}]".format(key)
        typecheck(self.type_scheme, Dict)
        typecheck(value, self.type_scheme[key], value_name=value_name)
        self.data[key] = value

    def __contains__(self, item) -> bool:
        return item in self.data

    def __repr__(self):
        return "RunDataBlock({}, {})".format(self.data, self.attributes)

    def copy(self):
        """
        Copy this run program block.
        Deep copies the data and uses the same type scheme and attributes.
        :return:
        """
        return RunProgramBlock(self.id, deepcopy(self.data), self.attributes, self.run_driver_class)

    def __len__(self):
        return min(map(len, self.data.values())) if len(self.data) > 0 else 0

    @classmethod
    def from_dict(cls, id: int, data, run_driver: type = None):
        """
        Structure of data::

             {
                "attributes": {"attr1": ..., ...},
                "run_config": {"prop1": ..., ...}
             }

        :param id: id of the block (only used to track them later)
        :param data: used data
        :param run_driver: used RunDriver subclass
        :return: new RunProgramBlock
        """
        typecheck(data, Dict({
            "attributes": Dict(all_keys=False, key_type=Str()),
            "run_config": Dict(all_keys=False)
        }))
        return RunProgramBlock(id, data["run_config"], data["attributes"], run_driver)

    def to_dict(self):
        return {
            "attributes": self.attributes,
            "run_config": self.data
        }

class BenchmarkingResultBlock:

    def __init__(self, properties: list, data: dict = None):
        typecheck(properties, List(Str()))
        self.properties = properties
        self.data = data if data is not None else {}
        for prop in properties:
            self.data[prop] = []

    def add_run_data(self, data: dict):
        typecheck(data, Dict(all_keys=False, key_type=Str(), value_type=Int()|Float()))
        for prop in self.properties:
            self.data[prop].append(data[prop])

    def to_dict(self):
        return {
            "properties": self.properties,
            "data": self.data
        }

    @classmethod
    def from_dict(cls, source: dict):
        typecheck(source, Dict({
            "properties": List(Str()),
            "data": Dict(all_keys=False, key_type=Str(), value_type=Int()|Float())
        }))
        return BenchmarkingResultBlock(source["properties"], source["data"])


class AbstractRunDriver(AbstractRegistry):
    """
    A run driver
    """

    settings_key_path = "run/plugins"
    use_key = "active"
    use_list = True
    default = []
    block_type_scheme = Dict()
    block_default = {}
    registry = {}

    def __init__(self, misc_settings: dict = None):
        """
        Also calls the setup methods on all registered plugins.
        It calls the setup() method.
        :param misc_settings: further settings
        :return:
        """
        self.misc_settings = misc_settings
        self.used_plugins = [self.get_for_name(name) for name in self.get_used()]
        self.setup()

    def setup(self):
        """
        Call the setup() method on all used plugins for this driver.
        """
        for plugin in self.used_plugins:
            plugin.setup()

    def teardown(self):
        """
        Call the teardown() method on all used plugins for this driver.
        """
        for plugin in self.used_plugins:
            plugin.teardown()

    def _setup_block(self, block: RunProgramBlock):
        """
        Call the setup_block() method on all used plugins for this driver.
        """
        for plugin in self.used_plugins:
            plugin.setup_block(block)

    def _setup_block_run(self, block: RunProgramBlock):
        """
        Call the setup_block_run() method on all used plugins for this driver.
        """
        for plugin in self.used_plugins:
            plugin.setup_block_run(block)

    def _teardown_block(self, block: RunProgramBlock):
        """
        Call the teardown_block() method on all used plugins for this driver.
        """
        for plugin in self.used_plugins:
            plugin.teardown_block(block)

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        """
        Benchmark the passed program block "runs" times and return the benchmarking results.
        :param block: run program block to benchmark
        :param runs: number of benchmarking runs
        :return: object that contains a dictionary of properties with associated raw run data
        :raises BenchmarkingError if the benchmarking of the passed block fails
        """
        raise NotImplementedError()


@register(RunDriverRegistry, "exec", Dict({
    "perf_stat_props": ListOrTuple(Str()) // Description("Measured properties")
                              // Default(["task-clock", "branch-misses", "cache-references",
                                          "cache-misses", "cycles", "instructions"]),
    "perf_stat_repeat": PositiveInt() // Description("If runner=perf_stat make measurements of the program"
                                                     "repeated n times. Therefore scale the number of times a program."
                                                     "is benchmarked.") // Default(1),
    "runner": ExactEither("perf_stat") // Description("Used benchmarking runner")
                              // Default("perf_stat")
}, all_keys=False))
class ExecRunDriver(AbstractRunDriver):
    """
    Implements a simple run driver that just executes one of the passed run_cmds
    in each benchmarking run.
    It meausures the time  using the perf stat tool (runner=perf_stat).
    """

    settings_key_path = "run/exec_plugins"
    use_key = "exec_active"
    use_list = True
    default = ["nice"]
    block_type_scheme = Dict({
        "run_cmd": (List(Str()) | Str()) // Description("Commands to benchmark"),
        "env": Dict(all_keys=False, key_type=Str()) // Description("Environment variables"),
        "cmd_prefix": List(Str()) // Description("Command to append before the commands to benchmark"),
        "revision": (Int(_ >= -1) | Str()) // Description("Used revision (or revision number)."
                                                        "-1 is the current revision."),
        "cwd": (List(Str())|Str()) // Description("Execution directories for each command"),
        "runner": ExactEither() // Description("Used runner")
    }, all_keys=False)
    block_default = {
        "run_cmd": "",
        "env": {},
        "cmd_prefix": [],
        "revision": -1,
        "cwd": ".",
        "base_dir": ".",
        "runner": "perf_stat"
    }
    registry = {}

    def __init__(self, misc_settings: dict = None):
        super().__init__(misc_settings)
        self.dirs = {}

    def _setup_block(self, block: RunProgramBlock):
        if isinstance(block["run_cmd"], List(Str())):
            block["run_cmds"] = block["run_cmd"]
        else:
            block["run_cmds"] = [block["run_cmd"]]
        if isinstance(block["cwd"], List(Str())):
            if len(block["cwd"]) != len(block["run_cmds"]):
                raise ValueError("Number of passed working directories is unequal with number of passed run commands")
            block["cwds"] = block["cwd"]
        else:
            block["cwds"] = [block["cwd"]] * len(block["run_cmds"])
        self.uses_vcs = block["revision"] != -1
        self.vcs_driver = None
        self.tmp_dir = ""
        if self.uses_vcs and block.id not in self.dirs:
            self.vcs_driver = VCSDriver.get_suited_vcs(".")
            self.tmp_dir = os.path.join(Settings()["tmp_dir"], datetime.datetime.now().strftime("%s%f"))
            os.mkdir(self.tmp_dir)
            self.dirs[block.id] = os.path.join(self.tmp_dir, str(block.id))
            os.mkdir(self.dirs[block.id])
            self.vcs_driver.copy_revision(block["revision"], ".", self.dirs[block.id])
            block["working_dir"] = self.dirs[block.id]
        super()._setup_block(block)

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        t = time.time()
        block = block.copy()
        self._setup_block(block)
        runner = self.misc_settings["runner"]
        gc.collect()
        gc.disable()
        try:
            res = self._benchmark(block, runs, cpuset, set_id)
        except BaseException:
            self.teardown()
            logging.error("Forced teardown of RunProcessor")
            raise
        finally:
            gc.enable()
        self._teardown_block(block)
        t = time.time() - t
        assert isinstance(res, BenchmarkingResultBlock)
        res.data["ov-time"] = [t / runs] * runs
        #print(res.data)
        return res

    ExecResult = namedtuple("ExecResult", ['time', 'stderr', 'stdout'])
    """ A simple named tuple named ExecResult with to properties: time, stderr and stdout """

    def _benchmark(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None, set_id: int = 0):
        block = block.copy()
        runner = self.get_runner(block)
        runner.setup_block(block, runs, cpuset, set_id)
        results = []
        for i in range(runs):
            self._setup_block_run(block)
            results.append(self._exec_command(block["run_cmds"], block, cpuset, set_id))
        res = None # type: BenchmarkingResultBlock
        for exec_res in results:
            res = runner.parse_result(exec_res, res)
        return res

    def _exec_command(self, cmds: list, block: RunProgramBlock,
                      cpuset: CPUSet = None, set_id: int = 0) -> ExecResult:
        """
        Executes one randomly chosen command of the passed ones.
        And takes additional settings in the passed run program block into account.
        :param cmds: list of commands
        :param block: passed run program block
        :return: time in seconds the execution needed to finish
        """
        typecheck(cmds, List(Str()))
        rand_index = random.randrange(0, len(cmds))
        cmd = cmds[rand_index]
        cwd = block["cwds"][rand_index]
        executed_cmd = block["cmd_prefix"] + [cmd]
        if cpuset is not None:
            executed_cmd.insert(0, "sudo cset proc --move --force --pid $$ {} > /dev/null"\
                .format(cpuset.get_sub_set(set_id)))
        env = block["env"]
        env.update({'LC_NUMERIC': 'en_US.ASCII'})
        t = time.time()
        executed_cmd = "; ".join(executed_cmd)
        proc = subprocess.Popen(["/bin/sh", "-c", executed_cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                                cwd=cwd,
                                env=env)
        out, err = proc.communicate()
        t = time.time() - t
        if proc.poll() > 0:
            msg = "Error executing " + cmd + ": "+ str(err) + " " + str(out)
            logging.error(msg)
            raise BenchmarkingError(msg)
        return self.ExecResult(time=t, stderr=str(err), stdout=str(out))

    def teardown(self):
        super().teardown()
        if hasattr(self, "tmp_dir") and os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    runners = {}

    @classmethod
    def register_runner(cls):

        def dec(klass):
            assert issubclass(klass, ExecRunner)
            cls.runners[klass.name] = klass
            cls.block_type_scheme["runner"] |= E(klass.name)
            cls.block_type_scheme[klass.name] = klass.misc_options
            cls.block_default[klass.name] = klass.misc_options.get_default()
            if klass.__doc__ is not None:
                header = ""# "Description of {} (class {}):\n".format(name, klass.__qualname__)
                lines = str(klass.__doc__.strip()).split("\n")
                lines = map(lambda x: "  " + x.strip(), lines)
                description = Description(header + "\n".join(lines))
                klass.__description__ = description.description
            else:
                klass.__description__ = ""
            return klass

        return dec

    @classmethod
    def get_runner(cls, block: RunProgramBlock) -> 'ExecRunner':
        return cls.runners[block["runner"]](block)


class ExecRunner:
    """
    Base class for runners for the ExecRunDriver.
    """

    name = None # type: str
    misc_options = Dict({})

    def __init__(self, block: RunProgramBlock):
        self.misc = self.misc_options.get_default()
        if self.name in block:
            self.misc.update(block[self.name])
            typecheck(self.misc, self.misc_options)

    def setup_block(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None, set_id: int = 0):
        pass

    def parse_result(self, exec_res: ExecRunDriver.ExecResult, res: BenchmarkingResultBlock = None) -> dict:
        raise NotImplementedError()


def get_av_perf_stat_properties() -> t.List[str]:
    proc = subprocess.Popen(["/bin/sh", "-c", "perf list"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    out, err = proc.communicate()
    if proc.poll() > 0:
        raise EnvironmentError("Error calling 'perf list': {}".format(err))
    lines = out.split("\n")[3:]
    props = []
    for line in lines:
        line = line.strip()
        if line == "" or "=" in line or "<" in line or "NNN" in line:
            continue
        prop = line.split(" ", 1)[0].strip()
        if prop != "":
            props.append(prop)
    return props


class ValidPerfStatPropertyList(Type):
    """
    Checks for the value to be a valid perf stat measurement property list.
    """

    def __init__(self):
        super().__init__()
        av = get_av_perf_stat_properties()
        self.completion_hints = {
            "zsh": "({})".format(" ".join(av)),
            "fish": {
                "hint": list(av)
            }
        }

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not isinstance(value, List(Str())):
            return info.errormsg(self)
        cmd = "perf stat -x ';' -e {props} -- /bin/echo".format(props=",".join(value))
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            return info.errormsg("Not a valid properties list: " + str(err).split("\n")[0].strip())
        return info.wrap(True)

    def __str__(self) -> str:
        return "ValidPerfStatPropertyList()"

    def _eq_impl(self, other):
        return True


@ExecRunDriver.register_runner()
class PerfStatExecRunner(ExecRunner):
    """
    Runner that uses perf stat for measurements.
    """

    name = "perf_stat"
    misc_options = Dict({
        "repeat": NaturalNumber() // Default(1),
        "properties": ValidPerfStatPropertyList() // Default(["cache-misses", "cycles", "task-clock",
                                              "instructions", "branch-misses", "cache-references"])
    })

    def setup_block(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None, set_id: int = 0):
        do_repeat = self.misc["repeat"] > 1

        def modify_cmd(cmd):
            return "perf stat {repeat} -x ';' -e {props} -- {cmd}".format(
                props=",".join(self.misc["properties"]),
                cmd=cmd,
                repeat="--repeat {}".format(self.misc["properties"]) if do_repeat else ""
            )
        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]


    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        res = res or BenchmarkingResultBlock(list(set(list(self.misc["properties"]) + ["ov-time"])))
        m = {"ov-time": exec_res.time}
        for line in exec_res.stderr.strip().split("\n"):
            if ';' in line:
                var, empty, descr = line.split(";")[0:3]
                try:
                    m[descr] = float(var)
                except:
                    pass
        res.add_run_data(m)
        return res


@ExecRunDriver.register_runner()
class SpecExecRunner(ExecRunner):
    """
    Runner for SPEC like single benchmarking suites.
    It works with resulting property files, in which the properties are collon
    separated from their values.
    """

    name = "spec"
    misc_options = Dict({
        "file": Str() // Default("") // Description("SPEC result file"),
        "base_path": Str() // Default(""),
        "path_regexp": Str() // Default(".*")
                         // Description("Regexp matching the base property path for each measured property"),
        "code": Str() // Default("get()")
                      // Description("Code that is executed for each matched path. "
                           "The code should evaluate to the actual measured value for the path."
                           "it can use the function get(sub_path: str = '') and the modules "
                           "pytimeparse, numpy, math, random, datetime and time.")
    })

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        if not self.misc["base_path"].endswith(".") and len(self.misc["base_path"]) > 0:
            self.misc["base_path"] += "."
        if not self.misc["path_regexp"].startswith("^"):
            self.misc["path_regexp"] = "^" + self.misc["path_regexp"]
        self.path_regexp = re.compile(self.misc["path_regexp"])

    def setup_block(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None, set_id: int = 0):
        block["run_cmds"] = ["{}; cat {}".format(cmd, self.misc["file"]) for cmd in block["run_cmds"]]

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        props = {}
        for line in exec_res.stdout.split("\n"):
            if ":" not in line:
                continue
            arr = line.split(":")
            if len(arr) != 2 or not arr[0].strip().startswith(self.misc["base_path"]):
                continue
            val = 0
            try:
                val = float(arr[1].strip())
            except ValueError:
                continue
            whole_path = arr[0].strip()[len(self.misc["base_path"]):]
            matches = self.path_regexp.match(whole_path)
            if matches:
                path = matches.group(0)
                if path not in props:
                    props[path] = {}
                sub_path = whole_path[len(path):]
                props[path][sub_path] = val
        data = {}
        for prop in props:
            def get(sub_path: str = ""):
                return props[prop][sub_path]
            data[prop] = eval(self.misc["code"])
        if len(data) == 0:
            logging.error("No properties in the result file matched begin with {!r} "
                          "and match the passed regular expression {!r}"
                          .format(self.misc["base_path"], self.path_regexp))

        res = res or BenchmarkingResultBlock(list(props.keys()))
        res.add_run_data(data)
        return res


class BenchmarkingError(RuntimeError):
    """
    Thrown when the benchmarking of a program block fails.
    """