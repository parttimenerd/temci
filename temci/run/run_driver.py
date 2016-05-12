"""
This modules contains the base run driver, needed helper classes and registries.
"""
import os
import datetime
import re
import shutil
import collections
from temci.build.builder import Builder, env_variables_for_rand_conf
from temci.setup import setup
from temci.utils.settings import Settings
from temci.utils.typecheck import NoInfo
from temci.utils.util import has_root_privileges, join_strs, does_command_succeed, sphinx_doc, on_apple_os, \
    does_program_exist
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

    """.format(yaml="\n        ".join(klass.block_type_scheme.string_representation().split("\n")))


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
        block = RunProgramBlock(id, data["run_config"], data["attributes"], run_driver)
        return block

    def to_dict(self) -> t.Dict:
        """
        Serializes this instance into a data structure that is accepted by the ``from_dict`` method.
        """
        return {
            "attributes": self.attributes,
            "run_config": self.data
        }


class BenchmarkingResultBlock:
    """
    Result of the benchmarking of one block.
    It includes the error object if an error occurred.
    """

    def __init__(self, data: t.Dict[str, t.List[Number]] = None, error: BaseException = None):
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

    def properties(self) -> t.List[str]:
        """ Get a list of the measured properties """
        return list(self.data.keys())

    def add_run_data(self, data: t.Dict[str, t.Union[Number, t.List[Number]]]):
        """
        Add data.

        :param data: data to be added (measured data per property)
        """
        typecheck(data, Dict(all_keys=False, key_type=Str(), value_type=Int() | Float() | List(Int() | Float())))
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
                #        "data": Dict(all_keys=False)
                #    }, all_keys=False))
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
        for used in self.get_used():
            klass = self.get_class(used)
            if klass.needs_root_privileges and not is_root:
                miss_root_plugins.append(used)
            else:
                self.used_plugins.append(self.get_for_name(used))
        if miss_root_plugins:
            logging.warning("The following plugins are disabled because they need root privileges: " +
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
        :param cpuset: used CPUSet instance
        :param set_id: id of the cpu set the benchmarked block should be executed in
        :return: object that contains a dictionary of properties with associated raw run data
        """
        raise NotImplementedError()

    def get_property_descriptions(self) -> t.Dict[str, str]:
        """
        Returns a dictionary that maps some properties to their short descriptions.
        """
        return {}


class ExecValidator:
    """
    Output validator.
    """

    config_type_scheme = Dict({
        "expected_output": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that should be present in the program output"),
        "unexpected_output": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that shouldn't be present in the program output"),
        "expected_erroutput": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that should be present in the program error output"),
        "unexpected_erroutput": (List(Str()) | Str()) // Default([]) // Description(
            "Strings that shouldn't be present in the program output"),
        "expected_return_code": (List(Int()) | Int()) // Default(0) // Description("Allowed return code(s)"),
    })
    """ Configuration type scheme """

    def __init__(self, config: dict):
        """
        Creates an instance.

        :param config: validator configuration
        """
        self.config = config  # type: t.Dict[str, t.Union[t.List[int], t.List[str], int, str]
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
        self._match(cmd, "program output", out, self.config["expected_output"], True)
        self._match(cmd, "program output", out, self.config["unexpected_output"], False)
        self._match(cmd, "program error output", out, self.config["expected_erroutput"], True)
        self._match(cmd, "program error output", out, self.config["unexpected_erroutput"], False)
        self._match_return_code(cmd, self.config["expected_return_code"], return_code)

    def _match(self, cmd: str, name: str, checked_str: str, checker: List(Str()) | Str(), expect_match: bool):
        if not isinstance(checker, List()):
            checker = [checker]
        bools = [check in checked_str for check in checker]
        if expect_match and not all(bools):
            raise BenchmarkingError("{} for {!r} doesn't contain the string {!r}, it's: {}"
                                    .format(name, cmd, checker[bools.index(False)], checked_str))
        if not expect_match and any(bools):
            raise BenchmarkingError("{} for {!r} contains the string {!r}, it's: {}"
                                    .format(name, cmd, checker[bools.index(True)], checked_str))

    def _match_return_code(self, cmd: str, exptected_codes: t.Union[t.List[int], int], return_code: int):
        if isinstance(exptected_codes, int):
            exptected_codes = [exptected_codes]
        if return_code not in exptected_codes:
            raise BenchmarkingError("Unexpected return code {} of {!r}, expected {}"
                                    .format(str(return_code), cmd, join_strs(list(map(str, exptected_codes)), "or")))


@register(RunDriverRegistry, "exec", Dict({
    "runner": ExactEither("")
              // Description("If not '' overrides the runner setting for each program block")
              // Default(""),
    "random_cmd": Bool() // Default(True)
                  // Description("Pick a random command if more than one run command is passed.")
}, all_keys=False))
class ExecRunDriver(AbstractRunDriver):
    """
    Implements a simple run driver that just executes one of the passed run_cmds
    in each benchmarking run.
    It meausures the time  using the perf stat tool (runner=perf_stat).

    The constructor calls the ``setup`` method.
    """

    settings_key_path = "run/exec_plugins"
    use_key = "exec_active"
    use_list = True
    default = ["nice"]
    block_type_scheme = Dict({
        "run_cmd": (List(Str()) | Str()) // Default("") // Description("Commands to benchmark"),
        "env": Dict(all_keys=False, key_type=Str()) // Default({}) // Description("Environment variables"),
        "cmd_prefix": List(Str()) // Default([]) // Description("Command to append before the commands to benchmark"),
        "revision": (Int(lambda x: x >= -1) | Str()) // Default(-1) // Description("Used revision (or revision number)."
                                                                                   "-1 is the current revision."),
        "cwd": (List(Str()) | Str()) // Default(".") // Description("Execution directories for each command"),
        "runner": ExactEither().dont_typecheck_default() // Default("time") // Description("Used runner"),
        "disable_aslr": Bool() // Default(False) // Description("Disable the address space layout randomization"),
        "validator": ExecValidator.config_type_scheme // Description(
            "Configuration for the output and return code validator")
    }, all_keys=False)

    registry = {}

    def __init__(self, misc_settings: dict = None):
        super().__init__(misc_settings)
        self._dirs = {}
        self.runner = None  # type: t.Optional[ExecRunner]

    def _setup_block(self, block: RunProgramBlock):
        if isinstance(block["run_cmd"], List(Str())):
            block["run_cmds"] = block["run_cmd"]
        else:
            block["run_cmds"] = [block["run_cmd"]]
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
        super()._setup_block(block)

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        t = time.time()
        block = block.copy()
        try:
            self._setup_block(block)
            gc.collect()
            gc.disable()
        except IOError as err:
            return BenchmarkingResultBlock(error=err)
        try:
            res = self._benchmark(block, runs, cpuset, set_id)
        except BaseException as ex:
            return BenchmarkingResultBlock(error=ex)
        finally:
            gc.enable()
        try:
            self._teardown_block(block)
        except BaseException as err:
            return BenchmarkingResultBlock(error=err)
        t = time.time() - t
        assert isinstance(res, BenchmarkingResultBlock)
        res.data["__ov-time"] = [t / runs] * runs
        # print(res.data)
        return res

    ExecResult = namedtuple("ExecResult", ['time', 'stderr', 'stdout'])
    """ A simple named tuple named ExecResult with to properties: time, stderr and stdout """

    def _benchmark(self, block: RunProgramBlock, runs: int, cpuset: CPUSet = None, set_id: int = 0):
        block = block.copy()
        self.runner = self.get_runner(block)
        self.runner.setup_block(block, cpuset, set_id)
        results = []
        for i in range(runs):
            self._setup_block_run(block)
            results.append(self._exec_command(block["run_cmds"], block, cpuset, set_id))
        res = None  # type: BenchmarkingResultBlock
        for exec_res in results:
            res = self.runner.parse_result(exec_res, res)
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
        rand_index = random.randrange(0, len(cmds)) if self.misc_settings["random_cmd"] else 0
        cmd = cmds[rand_index]
        cwd = block["cwds"][rand_index]
        executed_cmd = block["cmd_prefix"] + [cmd]
        if cpuset is not None and has_root_privileges():
            executed_cmd.insert(0, "cset proc --move --force --pid $$ {} > /dev/null" \
                                .format(cpuset.get_sub_set(set_id)))
        env = os.environ.copy()
        env.update(block["env"])
        env.update({'LC_NUMERIC': 'en_US.UTF-8'})
        # print(env["PATH"])
        t = time.time()
        executed_cmd = "; ".join(executed_cmd)
        proc = None
        try:
            proc = subprocess.Popen(["/bin/sh", "-c", executed_cmd], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True,
                                    cwd=cwd,
                                    env=env, )
            # preexec_fn=os.setsid)
            out, err = proc.communicate()
            t = time.time() - t
            ExecValidator(block["validator"]).validate(cmd, out, err, proc.poll())
            # if proc.poll() > 0:
            #    msg = "Error executing " + cmd + ": "+ str(err) + " " + str(out)
            # logging.error(msg)
            #    raise BenchmarkingError(msg)
            return self.ExecResult(time=t, stderr=str(err), stdout=str(out))
        except:
            if proc is not None:
                try:
                    proc.terminate()
                    # os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except BaseException as err:
                    pass
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
    or the setting under the key ``run/exec_misc/runner`` to it's name.

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


class ExecRunner:
    """
    Base class for runners for the ExecRunDriver.
    A runner deals with creating the commands that actually measure a program and parse their outputs.
    """

    name = None  # type: str
    """ Name of the runner """
    misc_options = Dict({})  # type: Type
    """ Type scheme of the options for this type of runner """

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
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        """
        Parse the output of a program and turn it into benchmarking results.

        :param exec_res: program output
        :param res: benchmarking result to which the extracted results should be added or None if they should be added
        to an empty one
        :return: the modfiied benchmarking result block
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
        subprocess.check_call(["perf", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        av = get_av_perf_stat_properties()
        super().__init__(completion_hints={
            "zsh": "({})".format(" ".join(av)),
            "fish": {
                "hint": list(av)
            }
        })

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
        "properties": ValidPerfStatPropertyList() // Default(["wall-clock", "cycles", "cpu-clock", "task-clock",
                                                              "instructions", "branch-misses", "cache-references"])
                      // Description("Measured properties. The number of properties that can be measured at once "
                                     "is limited.")
    })

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        if not is_perf_available():
            raise KeyboardInterrupt("The perf tool needed for the perf stat runner isn't installed. You can install it "
                                    "via the linux-tools (or so) package of your distribution.")

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
        do_repeat = self.misc["repeat"] > 1

        def modify_cmd(cmd):
            return "perf stat {repeat} {x} -e {props} -- {cmd}".format(
                props=",".join(x for x in self.misc["properties"] if x != "wall-clock"),
                cmd=cmd,
                repeat="--repeat {}".format(self.misc["repeat"]) if do_repeat else "",
                x="-x ';'" if "wall-clock" not in self.misc["properties"] else ""
            )

        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
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
            if ',' in line or ';' in line or "." in line:
                try:
                    line = line.strip()
                    prop = props[missing_props - 1]
                    assert prop in line or prop == "wall-clock"
                    val = ""  # type: str
                    if ";" in line:  # csv output with separator ';'
                        val = line.split(";")[0]
                    else:
                        val = line.split(" ")[0]
                    val = val.replace(",", "")
                    m[prop] = float(val) if "." in val else int(val)
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

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
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
                data[prop] = data
            data[prop].append(eval(self.misc["code"]))
        if len(data) == 0:
            raise BenchmarkingError("No properties in the result file matched begin with {!r} "
                                    "and match the passed regular expression {!r}"
                                    .format(self.misc["base_path"], self.path_regexp))

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

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
                     res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
        data = {}  # type: t.Dict[str, t.List[float]]
        pre_data = {}  # type: t.Dict[str, t.Dict[int, float]]
        prop_pattern = re.compile("spec\.cpu[0-9]{4}\.results\.")
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
            _tmp.append(shutil.which("time"))
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

    def __init__(self, block: RunProgramBlock):
        super().__init__(block)
        if not does_command_succeed(time_file() + " -v true"):
            raise KeyboardInterrupt("gnu time seems to be not installed and the time runner can therefore not be used")
        fmts = get_av_time_properties_with_format_specifiers()
        self._time_format_spec = "### " + " ".join(["%" + fmts[prop][1] for prop in self.misc["properties"]])

    def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):

        def modify_cmd(cmd):
            return "{} -f {!r} /bin/sh -c {!r}".format(time_file(), self._time_format_spec, cmd)

        block["run_cmds"] = [modify_cmd(cmd) for cmd in block["run_cmds"]]

    def parse_result(self, exec_res: ExecRunDriver.ExecResult,
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


class BenchmarkingError(RuntimeError):
    """
    Thrown when the benchmarking of a program block fails.
    """
