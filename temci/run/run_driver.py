"""
This modules contains the base run driver, needed helper classes and registries.
"""
import os
import datetime
import re
import shlex
import shutil
import collections
from threading import Timer

import humanfriendly
import yaml

from temci.build.builder import Builder, env_variables_for_rand_conf
from temci.build.build_processor import BuildProcessor
from temci.setup import setup
from temci.utils.settings import Settings
from temci.utils.sudo_utils import get_bench_user, bench_as_different_user, get_env_setting
from temci.utils.typecheck import NoInfo
from temci.utils.util import has_root_privileges, join_strs, does_command_succeed, sphinx_doc, on_apple_os, \
    does_program_exist, document
from temci.utils.vcs import VCSDriver
from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register
from .cpuset import CPUSet
from copy import deepcopy
import logging, time, random, subprocess
from collections import namedtuple
import gc
import typing as t

Number = t.Union[int, float]
""" Numeric value """


class RunDriverRegistry(AbstractRegistry):
    """
    The registry for run drivers.
    """

    settings_key_path = "run"
    use_key = "driver"
    use_list = False
    default = "exec"
    registry = {}
    plugin_synonym = ("run driver", "run drivers")

    @classmethod
    def register(cls, name: str, klass: type, misc_type: Type):
        assert issubclass(klass, AbstractRunDriver)
        super().register(name, klass, misc_type)
        if not sphinx_doc():
            return
        klass.__doc__ += """

    Block configuration format for the run configuration:

    .. code-block:: yaml

        {yaml}

    """.format(yaml="\n        ".join(klass.get_full_block_typescheme().string_representation().split("\n")))


def filter_runs(blocks: t.List[t.Union['RunProgramBlock','RunData']], included: t.List[str]) -> t.List['RunProgramBlock']:
    """
    Filter run blocks (all: include all), identified by their description or tag or their number in the file (starting with 0)
    and run datas (only identified by their description and tag)

    :param blocks: blocks or run datas to filter
    :param included: include query
    :return: filtered list
    """
    list = [block for block in blocks
            if ("description" in block.attributes and block.attributes["description"] in included) or
            (isinstance(block, RunProgramBlock) and str(block.id) in included) or "all" in included or
            ("tags" in block.attributes and any(tag in included for tag in block.attributes["tags"]))]
    for i, x in enumerate(list):
        if isinstance(x, RunProgramBlock):
            x.id = i
    return list


class RunProgramBlock:
    """
    An object that contains every needed information of a program block.
    """

    def __init__(self, id: int, data: t.Dict[str, t.Any], attributes: t.Dict[str, str], run_driver_class: type = None):
        """
        Creates an instance.

        :param data: run driver configuration for this run program block
        :param attributes: attributes of this run program block
        :param run_driver_class: used type of run driver with this instance
        """
        self.run_driver_class = run_driver_class or RunDriverRegistry.get_class(
            RunDriverRegistry.get_used())  # type: type
        """ Used type of run driver """
        self.type_scheme = self.run_driver_class.block_type_scheme  # type: Type
        """ Configuration type scheme of the used run driver """
        self.data = deepcopy(self.run_driver_class.block_type_scheme.get_default())  # type: t.Dict[str, t.Any]
        """ Run driver configuration """
        self.data.update(data)
        self.attributes = attributes  # type: t.Dict[str, str]
        """ Describing attributes of this run program block """
        self.is_enqueued = False  # type: bool
        """ Is this program block enqueued in a run worker pool queue? """
        self.id = id  # type: int
        """ Id of this run program block """
        self.tags = attributes["tags"] if "tags" in self.attributes else None
        from temci.report.rundata import get_for_tags
        self.max_runs = get_for_tags("run/max_runs_per_tag", "run/max_runs", self.tags, min)
        if "max_runs" in self.data and self.data["max_runs"] > -1:
            self.max_runs = min(self.max_runs, self.data["max_runs"])
        self.min_runs = get_for_tags("run/min_runs_per_tag", "run/min_runs", self.tags, max)
        if "min_runs" in self.data and self.data["min_runs"] > -1:
            self.min_runs = max(self.min_runs, self.data["min_runs"])
        self.runs = get_for_tags("run/runs_per_tag", "run/runs", self.tags, max)
        if "runs" in self.data and self.data["min_runs"] > -1:
            self.runs = max(self.runs, self.data["runs"])

    def __getitem__(self, key: str) -> t.Any:
        """
        Returns the value associated with the given key.
        """
        return self.data[key]

    def __setitem__(self, key: str, value):
        """
        Sets the value associated with the passed key to the new value.

        :param key: passed key
        :param value: new value
        :raises TypeError: if the value hasn't the expected type
        """
        value_name = "run programm block[{}]".format(key)
        typecheck(self.type_scheme, Dict)
        typecheck(value, self.type_scheme[key], value_name=value_name)
        self.data[key] = value

    def __contains__(self, key) -> bool:
        """ Does the run driver configuration data contain the passed key? """
        return key in self.data

    def __repr__(self) -> str:
        return "RunDataBlock({}, {})".format(self.data, self.attributes)

    def copy(self) -> 'RunProgramBlock':
        """
        Copy this run program block.
        Deep copies the data and uses the same type scheme and attributes.
        """
        return RunProgramBlock(self.id, deepcopy(self.data), self.attributes, self.run_driver_class)

    @classmethod
    def from_dict(cls, id: int, data: t.Dict, run_driver: type = None):
        """
        Structure of data::

             {
                "attributes": {"attr1": ..., ...},
                "run_config": {"prop1": ..., ...},
                "build_config": {"prop1": ..., ...}
             }

        :param id: id of the block (only used to track them later)
        :param data: used data
        :param run_driver: used RunDriver subclass
        :return: new RunProgramBlock
        """
        typecheck(data, Dict({
            "attributes": Dict(unknown_keys=True, key_type=Str()) // Default({}),
            "run_config": Dict(unknown_keys=True),
            "build_config": BuildProcessor.block_scheme["build_config"],
        }))
        block = RunProgramBlock(id, data["run_config"], data["attributes"] if "attributes" in data else {}, run_driver)
        return block

    def to_dict(self) -> t.Dict:
        """
        Serializes this instance into a data structure that is accepted by the ``from_dict`` method.
        """
        return {
            "attributes": self.attributes,
            "run_config": self.data
        }

    def description(self) -> str:
        if "description" in self.attributes and self.attributes["description"] is not None:
            return self.attributes["description"]
        return ", ".join("{}={}".format(key, self.attributes[key]) for key in self.attributes)


class BenchmarkingResultBlock:
    """
    Result of the benchmarking of one block.
    It includes the error object if an error occurred.
    """

    def __init__(self, data: t.Dict[str, t.List[Number]] = None, error: BaseException = None,
                 recorded_error: 'RecordedError' = None):
        """
        Creates an instance.

        :param data: measured data per measured property
        :param error: exception object if something went wrong during benchmarking
        :return:
        """
        self.data = collections.defaultdict(lambda: [])  # type: t.Dict[str, t.List[Number]]
        """ Measured data per measured property """
        if data:
            self.add_run_data(data)
        self.error = error  # type: t.Optional[BaseException]
        """ Exception object if something went wrong during benchmarking """
        self.recorded_error = recorded_error

    def properties(self) -> t.List[str]:
        """ Get a list of the measured properties """
        return list(self.data.keys())

    def add_run_data(self, data: t.Dict[str, t.Union[Number, t.List[Number]]]):
        """
        Add data.

        :param data: data to be added (measured data per property)
        """
        typecheck(data, Dict(unknown_keys=True, key_type=Str(), value_type=Int() | Float() | List(Int() | Float())))
        for prop in data:
            if isinstance(data[prop], list):
                self.data[prop].extend(data[prop])
            else:
                self.data[prop].append(data[prop])

                # def _to_dict(self):
                #    """
                #    Serializes this instance into a data structure that is accepted by the ``from_dict`` method.
                #    """
                #    return {
                #        "properties": self.properties(),
                #        "data": self.data
                #    }
                #
                # @classmethod
                # def _from_dict(cls, source: dict):
                #    typecheck(source, Dict({
                #        "data": Dict(unknown_keys=True)
                #    }, unknown_keys=True))
                #    return BenchmarkingResultBlock(source["data"])


class AbstractRunDriver(AbstractRegistry):
    """
    A run driver that does the actual benchmarking and supports plugins to modify the benchmarking environment.

    The constructor also calls the setup methods on all registered plugins. It calls the setup() method.
    """

    settings_key_path = "run/plugins"
    use_key = "active"
    use_list = True
    default = []
    registry = {}
    plugin_synonym = ("run driver plugin", "run driver plugins")
    block_type_scheme = Dict()
    """ Type scheme for the program block configuration """
    runs_benchmarks = True

    def __init__(self, misc_settings: dict = None):
        """
        Creates an instance.
        Also calls the setup methods on all registered plugins.
        It calls the setup() method.

        :param misc_settings: further settings
        """
        self.misc_settings = misc_settings
        """ Further settings """
        self.used_plugins = []  # type: t.List[RunDriverPlugin]
        """ Used and active plugins """
        miss_root_plugins = []
        is_root = has_root_privileges()
        for used in self.get_used_plugins():
            klass = self.get_class(used)
            if klass.needs_root_privileges and not is_root:
                miss_root_plugins.append(used)
            else:
                self.used_plugins.append(self.get_for_name(used))
        if miss_root_plugins:
            logging.warning("The following plugins are disabled because they need root privileges (consider using `--sudo`): " +
                            join_strs(miss_root_plugins))
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
        typecheck(block.attributes, self.get_full_block_typescheme()["attributes"],
                  value_name="attributes of {}".format(block))
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
                  cpuset: CPUSet = None, set_id: int = 0,
                  timeout: float = -1) -> BenchmarkingResultBlock:
        """
        Benchmark the passed program block "runs" times and return the benchmarking results.

        :param block: run program block to benchmark
        :param runs: number of benchmarking runs
        :param cpuset: used CPUSet instance
        :param set_id: id of the cpu set the benchmarked block should be executed in
        :param timeout: timeout or -1 if no timeout is given
        :return: object that contains a dictionary of properties with associated raw run data
        """
        raise NotImplementedError()

    def get_property_descriptions(self) -> t.Dict[str, str]:
        """
        Returns a dictionary that maps some properties to their short descriptions.
        """
        return {}

    def get_used_plugins(self) -> t.List[str]:
        return self.get_used()

    @classmethod
    def get_full_block_typescheme(cls) -> Type:
        return Dict({"attributes": Dict({
            "tags": ListOrTuple(Str()) // Default([]) // Description("Tags of this block"),
            "description": Optional(Str()) // Default(None)
        }, unknown_keys=True, key_type=Str(), value_type=Any()) // Default({"tags": []})
                        // Description("Optional attributes that describe the block"),
                     "run_config": cls.block_type_scheme})


class _Err:

    def __init__(self, cmd: str, out: str, err: str, return_code: int):
        self.messages = []
        self.cmd = cmd
        self.out = out
        self.err = err
        self.return_code = return_code

    def append(self, message: str):
        self.messages.append(message)

    def error(self) -> 'BenchmarkingProgramError':
        from temci.report.rundata import RecordedProgramError
        return BenchmarkingProgramError(RecordedProgramError("\n".join(self.messages), self.out, self.err, self.return_code))


@document(config_type_scheme="Configuration:")
class ExecValidator:
    """
    Output validator.
    """

    config_type_scheme = Dict({
        "expected_output": Optional(Str()) // Default(None) // Description(
            "Program output without ignoring line breaks and spaces at the beginning and the end"),
        "expected_output_contains": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that should be present in the program output"),
        "unexpected_output_contains": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that shouldn't be present in the program output"),
        "expected_err_output": Optional(Str()) // Default(None) // Description(
            "Program error output without ignoring line breaks and spaces at the beginning and the end"),
        "expected_err_output_contains": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that should be present in the program error output"),
        "unexpected_err_output_contains": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that shouldn't be present in the program output"),
        "expected_return_code": (List(Int()) | Int()) // Default(0) // Description("Allowed return code(s)"),
    })
    """ Configuration type scheme """

    def __init__(self, config: dict):
        """
        Creates an instance.

        :param config: validator configuration
        """
        self.config = config  # type: t.Dict[str, t.Union[t.List[int], t.List[str], int, str]]
        """ Validator configuration """

    def validate(self, cmd: str, out: str, err: str, return_code: int):
        """
        Validate the passed program output, error output and return code.

        :param cmd: program command for better error messages
        :param out: passed program output
        :param err: passed program error output
        :param return_code: passed program return code
        :raises BenchmarkingError: if the check failed
        """
        error_messages = _Err(cmd, out, err, return_code)
        out = out.strip()
        err = err.strip()
        self._match(error_messages, cmd, "program output", out, self.config["expected_output"], True)
        self._match(error_messages, cmd, "program output", out, self.config["expected_output_contains"], True,
                    contains=True)
        self._match(error_messages, cmd, "program output", out, self.config["unexpected_output_contains"], False,
                    contains=True)
        self._match(error_messages, cmd, "program error output", err, self.config["expected_err_output"], True)
        self._match(error_messages, cmd, "program error output", err, self.config["expected_err_output_contains"], True,
                    contains=True)
        self._match(error_messages, cmd, "program error output", err, self.config["unexpected_err_output_contains"], False,
                    contains=True)
        self._match_return_code(error_messages, cmd, err, self.config["expected_return_code"], return_code)
        if error_messages.messages:
            raise error_messages.error()

    def _match(self, error_messages: _Err, cmd: str, name: str, checked_str: str, checker: List(Str()) | Str(),
               expect_match: bool, contains: bool = False):
        if not isinstance(checker, List()):
            checker = [checker]
        if contains:
            bools = [check in checked_str for check in checker]
            if expect_match and not all(bools):
                raise error_messages.append("{} doesn't contain the string {!r}, it's: {}"
                                            .format(name, checker[bools.index(False)], checked_str))
            if not expect_match and any(bools):
                raise error_messages.append("{} contains the string {!r}, it's: {}"
                                            .format(name, checker[bools.index(True)], checked_str))
        else:
            matches = checked_str == checker[0]
            if expect_match and matches:
                raise error_messages.append("{} isn't the string {!r}, it's: {}"
                                            .format(name, checker[0], checked_str))
            if not expect_match and not matches:
                raise error_messages.append("{} isn't the string {!r}, it's: {}"
                                            .format(name, checker[0], checked_str))

    def _match_return_code(self, error_messages: _Err, cmd: str, err: str, exptected_codes: t.Union[t.List[int], int],
                           return_code: int):
        if isinstance(exptected_codes, int):
            exptected_codes = [exptected_codes]
        if return_code not in exptected_codes:
            error_messages.append("Unexpected return code {}, expected {}"
                                   .format(str(return_code), join_strs(list(map(str, exptected_codes)), "or"), err))


_intel = ",disable_intel_turbo" if does_command_succeed("ls /sys/devices/system/cpu/intel_pstate/no_turbo") else ""

PRESET_PLUGIN_MODES = {
    "none": ("", "enable none by default"),
    "all": ("cpu_governor,disable_swap,sync,stop_start,other_nice,nice,disable_aslr,disable_ht" + _intel,
            "enable all, might freeze your system"),
    "usable": ("cpu_governor,disable_swap,sync,nice,disable_aslr,disable_ht,cpuset" + _intel,
               "like 'all' but doesn't affect other processes")
}


@register(RunDriverRegistry, "exec", Dict({
    "runner": ExactEither("")
              // Description("If not '' overrides the runner setting for each program block")
              // Default(""),
    "random_cmd": Bool() // Default(True)
                  // Description("Pick a random command if more than one run command is passed."),
    "preset": ExactEither(*PRESET_PLUGIN_MODES.keys()) // Default("usable" if has_root_privileges() else "none")
            // Description("Enable other plugins by default: {}".format("; ".join("{} = {} ({})".format(k, *t) for k, t in PRESET_PLUGIN_MODES.items()))),
    "parse_output": Bool() // Default(False) // Description("Parse the program output as a YAML dictionary of "
                                                            "that gives for a specific property a measurement. "
                                                             "Not all runners support it.")
}, unknown_keys=True))
class ExecRunDriver(AbstractRunDriver):
    """
    Implements a simple run driver that just executes one of the passed run_cmds
    in each benchmarking run.
    It measures the time  using the perf stat tool (runner=perf_stat).

    The constructor calls the ``setup`` method.
    """

    settings_key_path = "run/exec_plugins"
    use_key = "exec_active"
    use_list = True
    default = []
    block_type_scheme = Dict({
        "run_cmd": (List(Str()) | Str()) // Default("") // Description("Commands to benchmark"),
        "cmd": Str() // Default("") // Description("Command to benchmark, adds to run_cmd"),
        "env": Dict(unknown_keys=True, key_type=Str()) // Default({}) // Description("Environment variables"),
        "cmd_prefix": List(Str()) // Default([]) // Description("Command to append before the commands to benchmark"),
        "revision": (Int(lambda x: x >= -1) | Str()) // Default(-1) // Description("Used revision (or revision number)."
                                                                                   "-1 is the current revision, checks out "
                                                                                   "the revision"),
        "cwd": (List(Str()) | Str()) // Default(".") // Description("Execution directories for each command"),
        "runner": ExactEither().dont_typecheck_default() // Default("time") // Description("Used runner"),
        "disable_aslr": Bool() // Default(False) // Description("Disable the address space layout randomization"),
        "validator": ExecValidator.config_type_scheme // Description(
            "Configuration for the output and return code validator"),
        "max_runs": Int(lambda x: x >= -1) // Default(-1) // Description("Override all other max run"
                                                                         "specifications if > -1"),
        "min_runs": Int(lambda x: x >= -1) // Default(-1) // Description("Override all other min run"
                                                                         "specifications if > -1"),
        "runs": Int(lambda x: x >= -1) // Default(-1) // Description("Override min run and max run"
                                                                     "specifications if > -1"),
        "parse_output": Bool() // Default(False) // Description("Parse the program output as a YAML dictionary of "
                                                                "that gives for a specific property a measurement. "
                                                                "Not all runners support it.")
    }, unknown_keys=True)

    registry = {}

    def __init__(self, misc_settings: dict = None):
        super().__init__(misc_settings)
        self._dirs = {}
        self.runner = None  # type: t.Optional[ExecRunner]

    def _setup_block(self, block: RunProgramBlock):
        if isinstance(block["run_cmd"], List(Str())):
            block["run_cmds"] = block["run_cmd"] + [block["cmd"]] if block["cmd"] != "" else block["run_cmd"]
        else:
            block["run_cmds"] = [block["run_cmd"] + block["cmd"]]
        block["run_cmds"] = [cmd.replace("&", "&&").replace("$SUDO$", "&SUDO&") for cmd in block["run_cmds"]]
        if isinstance(block["cwd"], List(Str())):
            if len(block["cwd"]) != len(block["run_cmd"]) and not isinstance(block["run_cmd"], str):
                raise ValueError("Number of passed working directories {} "
                                 "is unequal with number of passed run commands {}"
                                 .format(len(block["cwd"]), len(block["run_cmd"])))
            block["cwds"] = block["cwd"]
        else:
            block["cwds"] = [block["cwd"]] * len(block["run_cmds"])
        self.uses_vcs = block["revision"] != -1
        self.vcs_driver = None
        self.tmp_dir = ""
        if self.uses_vcs and block.id not in self._dirs:
            self.vcs_driver = VCSDriver.get_suited_vcs(".")
            self.tmp_dir = os.path.join(Settings()["tmp_dir"], datetime.datetime.now().strftime("%s%f"))
            os.mkdir(self.tmp_dir)
            self._dirs[block.id] = os.path.join(self.tmp_dir, str(block.id))
            os.mkdir(self._dirs[block.id])
            self.vcs_driver.copy_revision(block["revision"], ".", self._dirs[block.id])
            block["working_dir"] = self._dirs[block.id]
        if self.misc_settings["runner"] != "":
            block["runner"] = self.misc_settings["runner"]
        block["parse_output"] |= self.misc_settings["parse_output"]
        super()._setup_block(block)

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0,
                  timeout: float = -1) -> BenchmarkingResultBlock:
        from temci.report.rundata import RecordedInternalError
        block = block.copy()
        try:
            self._setup_block(block)
            gc.collect()
            gc.disable()
        except IOError as err:
            return BenchmarkingResultBlock(error=err, recorded_error=RecordedInternalError.for_exception(err))
        try:
            res = self._benchmark(block, runs, cpuset, set_id, timeout=timeout)
        except BenchmarkingProgramError as ex:
            return BenchmarkingResultBlock(error=ex, recorded_error=ex.recorded_error)
        except BaseException as ex:
            return BenchmarkingResultBlock(error=ex, recorded_error=RecordedInternalError.for_exception(ex))
        finally:
            gc.enable()
        try:
            self._teardown_block(block)
        except BaseException as err:
            return BenchmarkingResultBlock(error=err, recorded_error=RecordedInternalError.for_exception(err))
        return res

    ExecResult = namedtuple("ExecResult", ['time', 'stderr', 'stdout'])
    """ A simple named tuple named ExecResult with to properties: time, stderr and stdout """

    def _benchmark(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None,
                   set_id: int = 0, timeout: float = -1):
        block = block.copy()
        self.runner = self.get_runner(block)
        self.runner.setup_block(block, cpuset, set_id)
        results = []
        for i in range(runs):
            self._setup_block_run(block)
            results.append(self._exec_command(block["run_cmds"], block, cpuset, set_id, timeout=timeout))
        res = None  # type: BenchmarkingResultBlock
        for exec_res in results:
            if not self.runner.supports_parsing_out and block["parse_output"]:
                logging.warn("Runner {} does not support the `parse_output` option")
            res = self.runner.parse_result(exec_res, res, block["parse_output"]
                                           and self.runner.supports_parsing_out)
        return res

    def _exec_command(self, cmds: list, block: RunProgramBlock,
                      cpuset: CPUSet = None, set_id: int = 0, redirect_out: bool = True,
                      timeout: float = -1) -> ExecResult:
        """
        Executes one randomly chosen command of the passed ones.
        And takes additional settings in the passed run program block into account.

        :param cmds: list of commands
        :param block: passed run program block
        :return: time in seconds the execution needed to finish
        """
        typecheck(cmds, List(Str()))
        rand_index = random.randrange(0, len(cmds)) if self.misc_settings["random_cmd"] else 0
        cmd = cmds[rand_index]
        if "$SUDO$" not in cmd:
            cmd = "$SUDO$ " + cmd
        if cmd.count("$SUDO$") == 1:
            cmd += " $SUDO$"
        pre, center, post = cmd.split("$SUDO$")
        if bench_as_different_user():
            cmd = pre + " sudo -u {} -E  PATH={} sh -c {}".format(get_bench_user(),
                                                           shlex.quote(Settings()["env"]["PATH"]),
                                                           shlex.quote(center)) + post
        else:
            cmd = pre + " " + center + " " + post
        cmd = cmd.replace("&SUDO&", "$SUDO$") .replace("&&", "&")
        cwd = block["cwds"][rand_index]
        executed_cmd = block["cmd_prefix"] + [cmd]
        if cpuset is not None and has_root_privileges():
            executed_cmd.insert(0, "cset proc --move --force --pid $$ {} > /dev/null" \
                                .format(cpuset.get_sub_set(set_id)))
        env = get_env_setting() if bench_as_different_user() else os.environ.copy()
        env.update(block["env"])
        env.update({'LC_NUMERIC': 'en_US.UTF-8'})
        # print(env["PATH"])
        executed_cmd = "; ".join(executed_cmd)
        proc = None

        try:
            t = time.time()
            proc = subprocess.Popen(["/bin/sh", "-c", executed_cmd],
                                    stdout=subprocess.PIPE if redirect_out else None,
                                    stderr= subprocess.PIPE if redirect_out else None,
                                    universal_newlines=True,
                                    cwd=cwd,
                                    env=env, )
            # preexec_fn=os.setsid)
            if not redirect_out:
                proc.wait(timeout=timeout if timeout > -1 else None)
            out, err = proc.communicate(timeout=timeout if timeout > -1 else None)
            t = time.time() - t
            if redirect_out:
                ExecValidator(block["validator"]).validate(cmd, out, err, proc.poll())
            # if proc.poll() > 0:
            #    msg = "Error executing " + cmd + ": "+ str(err) + " " + str(out)
            # logging.error(msg)
            #    raise BenchmarkingError(msg)
            return self.ExecResult(time=t, stderr=str(err), stdout=str(out))
        except Exception as ex:
            if proc is not None:
                try:
                    proc.terminate()
                    # os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except BaseException as err:
                    pass
            if isinstance(ex, subprocess.TimeoutExpired):
                raise TimeoutException(executed_cmd, timeout, str(out), str(err), proc.returncode)
            raise

    def teardown(self):
        super().teardown()
        if hasattr(self, "tmp_dir") and os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    runners = {}
    """ Dictionary mapping a runner name to a runner class """

    @classmethod
    def register_runner(cls) -> t.Callable[[type], type]:
        """ Decorator to register a runner (has to be sub class of ``ÈxecRunner``)."""

        def dec(klass):
            assert issubclass(klass, ExecRunner)
            cls.runners[klass.name] = klass
            cls.block_type_scheme["runner"] |= E(klass.name)
            Settings().modify_type_scheme("run/exec_misc/runner", lambda x: x | E(klass.name))
            cls.block_type_scheme[klass.name] = klass.misc_options
            if klass.__doc__ is not None:
                header = ""  # "Description of {} (class {}):\n".format(name, klass.__qualname__)
                lines = str(klass.__doc__.strip()).split("\n")
                lines = map(lambda x: "  " + x.strip(), lines)
                description = Description(header + "\n".join(lines))
                klass.__description__ = description.description
            else:
                klass.__description__ = ""
            # if not sphinx_doc():
            #    return
            klass.__doc__ = (klass.__doc__ or "") + """

    To use this runner with name ``{name}`` either set the ``runner`` property of a run configuration
    or the setting under the key ``run/exec_misc/runner`` to its name.

        """
            if klass.supports_parsing_out:
                klass.__doc__ += """
    This runner supports the ``parse_output`` option.   
             """
            if klass.misc_options not in [Dict(), Dict({}), None]:
                klass.__doc__ += """

    The runner is configured by modifying the ``{name}`` property of a run configuration. This configuration
    has the following structure:

    .. code-block:: yaml

        {yaml}

    """.format(name=klass.name, yaml="\n        ".join(klass.misc_options.string_representation().split("\n")))
            return klass

        return dec

    @classmethod
    def get_runner(cls, block: RunProgramBlock) -> 'ExecRunner':
        """
        Create the suitable runner for the passed run program block.

        :param block: passed run program block
        """
        return cls.runners[block["runner"]](block)

    def get_property_descriptions(self) -> t.Dict[str, str]:
        return self.runner.get_property_descriptions() if self.runner else {}

    def get_used_plugins(self) -> t.List[str]:
        """
        Get the list of name of the used plugins (use_list=True)
        or the names of the used plugin (use_list=False).
        """
        used = super().get_used()
        for plugin in PRESET_PLUGIN_MODES[self.misc_settings["preset"]][0].split(","):
            if plugin not in used and plugin is not "":
                used.append(plugin)
        return used


@register(RunDriverRegistry, "shell", Dict({
    "preset": ExactEither(*PRESET_PLUGIN_MODES.keys()) // Default("none")
            // Description("Enable other plugins by default: {}".format("; ".join("{} = {} ({})".format(k, *t) for k, t in PRESET_PLUGIN_MODES.items())))
}, unknown_keys=True))
class ShellRunDriver(ExecRunDriver):
    """
    Implements a run driver that runs the benched command a single time with redirected in- and output.
    It can be used to run own benchmarking commands inside a sane benchmarking environment

    The constructor calls the ``setup`` method.
    """

    block_type_scheme = Dict({
        "run_cmd": Str() // Default("sh") // Description("Command to run"),
        "env": Dict(unknown_keys=True, key_type=Str()) // Default({}) // Description("Environment variables"),
        "cwd": (List(Str()) | Str()) // Default(".") // Description("Execution directory"),
    }, unknown_keys=True)
    runs_benchmarks = False

    def __init__(self, misc_settings: dict = None):
        super().__init__(misc_settings)
        self.misc_settings["random_cmd"] = False

    def _setup_block(self, block: RunProgramBlock):
        block["cwds"] = [block["cwd"]]
        block["cmd_prefix"] = []
        AbstractRunDriver._setup_block(self, block)

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0,
                  timeout: float = -1) -> BenchmarkingResultBlock:
        block = block.copy()
        try:
            self._setup_block(block)
            gc.collect()
            gc.disable()
        except IOError as err:
            return BenchmarkingResultBlock(error=err)
        try:
            self._exec_command([block["run_cmd"]], block, cpuset, set_id, redirect_out=False, timeout=timeout)
        except BaseException as ex:
            return BenchmarkingResultBlock(error=ex)
        finally:
            gc.enable()
        try:
            self._teardown_block(block)
        except BaseException as err:
            return BenchmarkingResultBlock(error=err)
        return BenchmarkingResultBlock([])

    def teardown(self):
        super().teardown()


class ExecRunner:
    """
    Base class for runners for the ExecRunDriver.
    A runner deals with creating the commands that actually measure a program and parse their outputs.
    """

    name = None  # type: str
    """ Name of the runner """
    misc_options = Dict({})  # type: Type
    """ Type scheme of the options for this type of runner """
    supports_parsing_out = False
    """ Is the captured output on standard out useful for parsing """

    def __init__(self, block: RunProgramBlock):
        """
        Creates an instance.

        :param block: run program block to measure
        :raises KeyboardInterrupt: if the runner can't be used (e.g. if the used tool isn't installed or compiled)
        """
        self.misc = self.misc_options.get_default()
        """ Options for this runner """
        if self.name in block:
            self.misc.update(block[self.name])
            typecheck(self.misc, self.misc_options)

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
        """
        Configure the passed copy of a run program block (e.g. the run command).

        :param block: modified copy of a block
        :param cpuset: used CPUSet instance
        :param set_id: id of the cpu set the benchmarking takes place in
        """
        pass

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None,
                     parse_output: bool = False) -> BenchmarkingResultBlock:
        """
        Parse the output of a program and turn it into benchmarking results.

        :param exec_res: program output
        :param res: benchmarking result to which the extracted results should be added or None if they should be added
        to an empty one
        :param parse_output: parse standard out to get additional properties
        :return: the modified benchmarking result block
        """
        ret = self.parse_result_impl(exec_res, res)
        if parse_output:
            OutputExecRunner.parse_result_impl(None, exec_res, ret)
        return ret


    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        """
        Parse the output of a program and turn it into benchmarking results.

        :param exec_res: program output
        :param res: benchmarking result to which the extracted results should be added or None if they should be added
        to an empty one
        :return: the modified benchmarking result block
        """
        raise NotImplementedError()

    def get_property_descriptions(self) -> t.Dict[str, str]:
        """
        Returns a dictionary that maps some properties to their short descriptions.
        """
        return {}


def is_perf_available() -> bool:
    """
    Is the ``perf`` tool available?
    """
    try:
        subprocess.check_call(["perf"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except BaseException:
        return False
    return True


def get_av_perf_stat_properties() -> t.List[str]:
    """
    Returns the list of properties that are measurable with the used ``perf stat`` tool.
    """
    if not is_perf_available():
        return []
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
    props.append("wall-clock")
    return props


class ValidPerfStatPropertyList(Type):
    """
    Checks for the value to be a valid ``perf stat`` measurement property list or the perf tool to be missing.
    """

    def __init__(self):
        super().__init__()

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not isinstance(value, List(Str())):
            return info.errormsg(self)
        if not is_perf_available():
            return info.wrap(True)
        assert isinstance(value, list)
        if "wall-clock" in value:
            value = value.copy()
            value.remove("wall-clock")
        cmd = "perf stat -x ';' -e {props} -- /bin/echo".format(props=",".join(value))
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            return info.errormsg(self, "Not a valid properties list: " + str(err).split("\n")[0].strip())
        return info.wrap(True)

    def __str__(self) -> str:
        return "ValidPerfStatPropertyList()"

    def _eq_impl(self, other):
        return True


@ExecRunDriver.register_runner()
class PerfStatExecRunner(ExecRunner):
    """
    Runner that uses ``perf stat`` for measurements.
    """

    name = "perf_stat"
    misc_options = Dict({
        "repeat": NaturalNumber() // Default(1) // Description("If runner=perf_stat make measurements of the program "
                                                               "repeated n times. Therefore scale the number of times "
                                                               "a program is benchmarked."),
        "properties": List(Str()) // Default(["wall-clock", "cycles", "cpu-clock", "task-clock",
                                                              "instructions", "branch-misses", "cache-references"])
                      // Description("Measured properties. The number of properties that can be measured at once "
                                     "is limited."),
        "limit_to_cpuset": Bool() // Default(True)
                      // Description("Limit measurements to CPU set, if cpusets are enabled")
    })
    supports_parsing_out = True

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        typecheck(self.misc["properties"], ValidPerfStatPropertyList(), "Properties setting of perf stat runner")
        if not is_perf_available():
            raise KeyboardInterrupt("The perf tool needed for the perf stat runner isn't installed. You can install it "
                                    "via the linux-tools (or so) package of your distribution. If it's installed, "
                                    "you might by only allowed to use it with super user rights. Test a simple command "
                                    "like `perf stat /bin/echo` to see what you have to do if you want to use with "
                                    "your current rights.")

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):

        do_repeat = self.misc["repeat"] > 1

        def modify_cmd(cmd):
            return "perf stat --sync {cpus} {repeat} {x} -e {props} -- $SUDO$ {cmd}".format(
                props=",".join(x for x in self.misc["properties"] if x != "wall-clock"),
                cmd=cmd,
                repeat="--repeat {}".format(self.misc["repeat"]) if do_repeat else "",
                x="-x ';'" if "wall-clock" not in self.misc["properties"] else "",
                cpus="--cpu={}".format(cpuset.get_sub_set(set_id))
                     if cpuset is not None and has_root_privileges() and self.misc["limit_to_cpuset"]
                     else ""
            )

        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        res = res or BenchmarkingResultBlock()
        m = {"__ov-time": exec_res.time}
        props = self.misc["properties"]  # type: t.List[str]
        has_wall_clock = "wall-clock" in props
        if has_wall_clock:
            props = props.copy()
            props.remove("wall-clock")
            props.append("wall-clock")
        missing_props = len(props)
        for line in reversed(exec_res.stderr.strip().split("\n")):
            if missing_props == 0:
                break
            prop = props[missing_props - 1]
            if ',' in line or ';' in line or "." in line or prop in line:
                try:
                    line = line.strip()
                    assert prop in line or prop == "wall-clock"
                    if prop == "wall-clock" and "time elapsed" not in line:
                        continue
                    val = ""  # type: str
                    if ";" in line:  # csv output with separator ';'
                        val = line.split(";")[0]
                    else:
                        val = line.split(" ")[0]
                    val = val.replace(",", "")
                    divisor = 1000.0 if "msec" in line else 1
                    m[prop] = (float(val) / divisor) if "." in val else (int(val) // divisor)
                    missing_props -= 1
                except BaseException as ex:
                    #logging.error(ex)
                    pass
        res.add_run_data(m)
        return res


def get_av_rusage_properties() -> t.Dict[str, str]:
    """
    Returns the available properties for the RusageExecRunner mapped to their descriptions.
    """
    return {
        "utime": "user CPU time used",
        "stime": "system CPU time used",
        "maxrss": "maximum resident set size",
        "ixrss": "integral shared memory size",
        "idrss": "integral unshared data size",
        "isrss": "integral unshared stack size",
        "nswap": "swaps",
        "minflt": "page reclaims (soft page faults)",
        "majflt": "page faults (hard page faults)",
        "inblock": "block input operations",
        "oublock": "block output operations",
        "msgsnd": "IPC messages sent",
        "msgrcv": "IPC messages received",
        "nsignals": "signals received",
        "nvcsw": "voluntary context switches",
        "nivcsw": "involuntary context switches"
    }


class ValidPropertyList(Type):
    """
    Checks for the value to be a valid property list that contains only elements from a given list.
    """

    def __init__(self, av_properties: t.Iterable[str]):
        """
        Creates an instance.

        :param av_properties: allowed list elements
        """
        super().__init__(completion_hints={
            "zsh": "({})".format(" ".join(av_properties)),
            "fish": {
                "hint": list(av_properties)
            }
        })
        self.av = av_properties  # type: t.Iterable[str]
        """ Allowed list elements """

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not isinstance(value, List(Str())):
            return info.errormsg(self)
        for elem in value:
            if elem not in self.av:
                return info.errormsg(self, "No such property " + repr(elem))
        return info.wrap(True)

    def __str__(self) -> str:
        return "ValidPropertyList()"

    def _eq_impl(self, other):
        return True


class ValidRusagePropertyList(ValidPropertyList):
    """
    Checks for the value to be a valid rusage runner measurement property list.
    """

    def __init__(self):
        super().__init__(get_av_rusage_properties().keys())

    def __str__(self) -> str:
        return "ValidRusagePropertyList()"

    def _eq_impl(self, other):
        return True


@ExecRunDriver.register_runner()
class RusageExecRunner(ExecRunner):
    """
    Runner that uses the getrusage(2) function to obtain resource measurements.
    """

    name = "rusage"
    misc_options = Dict({
        "properties": ValidRusagePropertyList() // Default(sorted(list(get_av_rusage_properties().keys())))
                      // Description("Measured properties that are stored in the benchmarking result")
    })

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        if not does_command_succeed(setup.script_relative("rusage/rusage") + " true"):
            raise KeyboardInterrupt("The needed c code for rusage seems to be not compiled properly. "
                                    "Please run temci setup.")

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):

        def modify_cmd(cmd):
            return "{} {!r}".format(
                setup.script_relative("rusage/rusage"),
                cmd
            )

        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        res = res or BenchmarkingResultBlock()
        m = {"__ov-time": exec_res.time}
        for line in reversed(exec_res.stdout.strip().split("\n")):
            if '#' in line:
                break
            if ' ' in line:
                var, val = line.strip().split(" ")
                if var in self.misc["properties"]:
                    try:
                        m[var] = float(val)
                    except:
                        pass
        res.add_run_data(m)
        return res

    def get_property_descriptions(self) -> t.Dict[str, str]:
        return get_av_rusage_properties()


@ExecRunDriver.register_runner()
class SpecExecRunner(ExecRunner):
    """
    Runner for SPEC like single benchmarking suites.
    It works with resulting property files, in which the properties are colon
    separated from their values.
    """

    name = "spec"
    misc_options = Dict({
        "file": Str() // Default("") // Description("SPEC result file"),
        "base_path": Str() // Default("") // Description("Base property path that all other paths are relative to."),
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
        self._path_regexp = re.compile(self.misc["path_regexp"])

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
        block["run_cmds"] = ["{} > /dev/null; cat {}".format(cmd, self.misc["file"]) for cmd in block["run_cmds"]]

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
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
            matches = self._path_regexp.match(whole_path)
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

            if prop not in data:
                data[prop] = []
            result = eval(self.misc["code"])
            if isinstance(result, list):
                data[prop].extend(result)
            else:
                data[prop].append(result)

        if len(data) == 0:
            raise BenchmarkingError("No properties in the result file matched begin with {!r} "
                                    "and match the passed regular expression {!r}"
                                    .format(self.misc["base_path"], self._path_regexp))

        res = res or BenchmarkingResultBlock()
        res.add_run_data(data)
        return res


@ExecRunDriver.register_runner()
class CPUSpecExecRunner(ExecRunner):
    """
    A runner that uses a tool that runs the SPEC CPU benchmarks and parses the resulting files.
    """

    name = "spec.py"
    misc_options = Dict({
        "files": ListOrTuple(Str()) // Default(["result/CINT2000.*.raw",
                                                "result/CFP2000.*.raw"])
                 // Description("File patterns (the newest file will be used)"),
        "randomize": Bool() // Default(False)
                     // Description("Randomize the assembly during compiling?"),
        "rand_conf": Builder.rand_conf_scheme // Default(Settings()["build/rand"])
                     // Description("Randomisation ")
    })

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
        file_cmds = []
        for file in self.misc["files"]:
            file_cmds.append("realpath `ls --sort=time {} | head -n 1`".format(file))
        if self.misc["randomize"]:
            block["env"].update(env_variables_for_rand_conf(self.misc["rand_conf"]))
        pre = "PATH='{}' ".format(block["env"]["PATH"]) if self.misc["randomize"] else ""
        block["run_cmds"] = [pre + cmd + " > /dev/null; " + "; ".join(file_cmds) for cmd in block["run_cmds"]]
        # print(block["run_cmds"])

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        data = {}  # type: t.Dict[str, t.List[float]]
        pre_data = {}  # type: t.Dict[str, t.Dict[int, float]]
        prop_pattern = re.compile(r"spec\.cpu[0-9]{4}\.results\.")
        lines = exec_res.stdout.strip().split("\n")
        file_lines = []
        n = len(self.misc["files"])
        for l in reversed(lines):
            if n == 0:
                break
            l = l.strip()
            if os.path.exists(l):
                n -= 1
                with open(l, "r") as f:
                    file_lines.extend(f.read().split("\n"))
        for line in file_lines:
            try:
                line = line.strip()
                if line.count(":") != 1:
                    continue
                prop, val = [part.strip() for part in line.split(":")]
                if not prop_pattern.match(prop):
                    continue
                prop = prop_pattern.sub("", prop, count=1)
                if prop.count(".") != 3:
                    continue
                name, *parts, number, subprop = prop.split(".")
                number = int(number)
                if subprop == "reported_time":
                    if val == "--":
                        val = -1
                    else:
                        val = float(val)
                    if name not in pre_data:
                        pre_data[name] = {}
                    if number not in pre_data[name]:
                        pre_data[name][number] = val
                elif subprop == "valid":
                    if int(val) != 1:  # => ${name} is invalid
                        pre_data[name][number] = -1
            except BaseException as ex:
                logging.info("Can't parse the following line properly: " + line)
                logging.info("Error message: " + str(ex))

        for prop in pre_data:
            valids = [x for x in pre_data[prop].values() if x > -1]
            if len(valids) > 0:
                data[prop] = valids
        res = res or BenchmarkingResultBlock()
        res.add_run_data(data)
        return res


def time_file(_tmp=[]) -> str:
    """ Returns the command used to execute the (GNU) ``time`` tool (not the built in shell tool). """
    if len(_tmp) == 0:
        if on_apple_os():
            if does_program_exist("gtime"):
                _tmp.append(shutil.which("gtime"))
            else:
                return "false && "
        else:
            _tmp.append("/usr/bin/time") # shutil.which("time") doesn't work in later versions
    assert _tmp[0] is not None
    return _tmp[0]


def get_av_time_properties_with_format_specifiers() -> t.Dict[str, t.Tuple[str, str]]:
    """
    Returns the available properties for the TimeExecRunner mapped to their descriptions and time format specifiers.
    """
    return {
        "utime": ("user CPU time used (in seconds)", "U"),
        "stime": ("system (kernel) CPU time used (in seconds)", "S"),
        "avg_unshared_data": ("average unshared data size in K", "D"),
        "etime": ("elapsed real (wall clock) time (in seconds)", "e"),
        "major_page_faults": ("major page faults (required physical I/O)", "F"),
        "file_system_inputs": ("blocks wrote in the file system", "I"),
        "avg_mem_usage": ("average total mem usage (in K)", "K"),
        "max_res_set": ("maximum resident set (not swapped out) size in K", "M"),
        "avg_res_set": ("average resident set (not swapped out) size in K", "K"),
        "file_system_output": ("blocks read from the file system", "O"),
        "cpu_perc": ("percent of CPU this job got (total cpu time / elapsed time)", "P"),
        "minor_page_faults": ("minor page faults (reclaims; no physical I/O involved)", "R"),
        "times_swapped_out": ("times swapped out", "W"),
        "avg_shared_text": ("average amount of shared text in K", "X"),
        "page_size": ("page size", "Z"),
        "invol_context_switches": ("involuntary context switches", "c"),
        "vol_context_switches": ("voluntary context switches", "w"),
        "signals_delivered": ("signals delivered", "k"),
        "avg_unshared_stack": ("average unshared stack size in K", "p"),
        "socket_msg_rec": ("socket messages received", "s"),
        "socket_msg_sent": ("socket messages sent", "s")
    }


def get_av_time_properties() -> t.Dict[str, str]:
    """
    Returns the available properties for the TimeExecRunner mapped to their descriptions.
    """
    d = {}
    t = get_av_time_properties_with_format_specifiers()
    for key in t:
        d[key] = t[key][0]
    return d


class ValidTimePropertyList(ValidPropertyList):
    """
    Checks for the value to be a valid time runner measurement property list.
    """

    def __init__(self):
        super().__init__(get_av_time_properties().keys())

    def __str__(self) -> str:
        return "ValidTimePropertyList()"

    def _eq_impl(self, other):
        return True


@ExecRunDriver.register_runner()
class TimeExecRunner(ExecRunner):
    """
    Uses the GNU ``time``tool and is mostly equivalent to the rusage runner but more user friendly.
    """

    name = "time"
    misc_options = Dict({
        "properties": ValidTimePropertyList() // Default(["utime", "stime", "etime", "avg_mem_usage",
                                                          "max_res_set", "avg_res_set"])
                      // Description("Measured properties that are included in the benchmarking results")
    })
    supports_parsing_out = True

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        if not does_command_succeed(time_file() + " -v true"):
            raise KeyboardInterrupt("gnu time seems to be not installed and the time runner can therefore not be used")
        fmts = get_av_time_properties_with_format_specifiers()
        self._time_format_spec = "### " + " ".join(["%" + fmts[prop][1] for prop in self.misc["properties"]])

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):

        def modify_cmd(cmd):
            return "{} -f {} /bin/sh -c {}".format(time_file(), shlex.quote(self._time_format_spec), shlex.quote(cmd))

        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        res = res or BenchmarkingResultBlock()
        m = {"__ov-time": exec_res.time}
        for line in reversed(exec_res.stderr.strip().split("\n")):
            if line.startswith("### "):
                _, *parts = line.strip().split(" ")
                if len(parts) == len(self.misc["properties"]):
                    for (i, part) in enumerate(parts):
                        try:
                            m[self.misc["properties"][i]] = float(part)
                        except:
                            pass
        res.add_run_data(m)
        return res

    def get_property_descriptions(self) -> t.Dict[str, str]:
        return get_av_time_properties()


@ExecRunDriver.register_runner()
class OutputExecRunner(ExecRunner):
    """
    Parses the output of the called command as YAML dictionary (or list of dictionaries) populate
    the benchmark results (string key and int or float value).

    For the simplest case, a program just outputs something like `time: 1000.0`.
    """

    name = "output"
    misc_options = Dict({})

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
        pass

    def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        res = res or BenchmarkingResultBlock()
        dict_type = Dict(unknown_keys=True, key_type=Str(), value_type=Either(Int(), Float(), List(Either(Int(), Float()))))
        output = yaml.safe_load(exec_res.stdout.strip())
        if isinstance(output, dict_type):
            res.add_run_data(dict(output))
        elif isinstance(output, List(dict_type)):
            for entry in list(output):
                res.add_run_data(entry)
        else:
            raise BenchmarkingError("Not a valid benchmarking program output: " + exec_res.stdout)
        return res

    def get_property_descriptions(self) -> t.Dict[str, str]:
        return {}


class BenchmarkingError(RuntimeError):
    """
    Thrown when the benchmarking of a program block fails.
    """


class BenchmarkingProgramError(BenchmarkingError):
    """
    Thrown when the benchmarked program fails
    """

    def __init__(self, recorded_error: 'RecordedProgramError'):
        super().__init__(recorded_error.message)
        self.recorded_error = recorded_error


class TimeoutException(BenchmarkingProgramError):

    def __init__(self, cmd: str, timeout: float, out: str, err: str, ret_code: int):
        from temci.report.rundata import RecordedProgramError
        super().__init__(RecordedProgramError("The following run command hit a timeout after {}: {}"
                                              .format(humanfriendly.format_timespan(timeout), cmd), out, err,
                                              ret_code))
