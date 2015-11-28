"""
This modules contains the base run driver, needed helper classes and registries.
"""

from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register
from .cpuset import CPUSet
from copy import deepcopy
import logging, time, random, subprocess
from collections import namedtuple
import shlex, gc

class RunDriverRegistry(AbstractRegistry):
    """
    The registry for run drivers.
    """

    settings_key_path = "run"
    use_key = "driver"
    use_list = False
    default = "exec"
    _register = {}


class RunProgramBlock:
    """
    An object that contains every needed information of a program block.
    """

    def __init__(self, data, attributes: dict, run_driver: type = None):
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

    def __repr__(self):
        return "RunDataBlock({}, {})".format(self.data, self.attributes)

    def copy(self):
        """
        Copy this run program block.
        Deep copies the data and uses the same type scheme and attributes.
        :return:
        """
        return RunProgramBlock(deepcopy(self.data), self.attributes, self.run_driver_class)

    @classmethod
    def from_dict(cls, data, run_driver: type = None):
        """
        Structure of data::

             {
                "attributes": {"attr1": ..., ...},
                "run_config": {"prop1": ..., ...}
             }

        :param data:
        :param run_driver:
        :return:
        """
        typecheck(data, Dict({
            "attributes": Dict(all_keys=False, key_type=Str()),
            "run_config": Dict(all_keys=False)
        }))
        return RunProgramBlock(data["run_config"], data["attributes"], run_driver)

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
    _register = {}

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
    "runner": (Exact("simple") | Exact("perf_stat")) // Default("perf_stat"),
    "properties": StrList() // Description("only needed for perf_stat runner")
                              // Default(["task-clock", "branch-misses", "cache-references",
                                          "cache-misses", "cycles", "instructions"]),
    "perf_stat_repeat": PositiveInt() // Description("If runner=perf_stat make measurements of the program"
                                                     "repeated n times. Therefore scale the number of times a program"
                                                     "is benchmarked.") // Default(1)
}))
class ExecRunDriver(AbstractRunDriver):
    """
    Implements a simple run driver that just executes one of the passed run_cmds
    in each benchmarking run.
    It meausures the time either simply by taking the time the execution takes
    (runner=simple) or by using the perf stat tool (runner=perf_stat).
    """

    settings_key_path = "run/exec_plugins"
    use_key = "exec_active"
    use_list = True
    default = ["nice", "preheat"]
    block_type_scheme = Dict({
        "run_cmds": List(Str()),
        "env": Dict(all_keys=False, key_type=Str()),
        "cmd_prefix": List(Str())
    })
    block_default = {
        "env": {},
        "cmd_prefix": []
    }
    _register = {}

    def benchmark(self, block: RunProgramBlock, runs: int,
                  cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        t = time.time()
        block = block.copy()
        self._setup_block(block)
        runner = self.misc_settings["runner"]
        gc.collect()
        gc.disable()
        try:
            res = {
                "simple": self._simple,
                "perf_stat": self._perf_stat
            }[runner](block, runs, cpuset, set_id)
        except BaseException:
            self.teardown()
            logging.error("Forced teardown of RunProcessor")
            raise
        finally:
            gc.enable()
        self._teardown_block(block)
        t = time.time() - t
        assert isinstance(res, BenchmarkingResultBlock)
        #print(t)
        res.data["ov-time"] = [t / runs] * runs
        #print(res.data)
        return res

    ExecResult = namedtuple("ExecResult", ['time', 'stderr'])
    """ A simple named tuple named ExecResult with to properties: time and stderr """

    def _simple(self, block: RunProgramBlock, runs: int,
                cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        """
        Implements a simple
        :param block: passed block
        :return:
        """
        res = BenchmarkingResultBlock(["ov-time"])
        for i in range(runs):
            res.add_run_data({
                "ov-time": self._exec_command(block["run_cmds"], block, cpuset, set_id).time
            })
        return res

    def _perf_stat(self, block: RunProgramBlock, runs: int,
                   cpuset: CPUSet = None, set_id: int = 0) -> BenchmarkingResultBlock:
        do_repeat = self.misc_settings["perf_stat_repeat"] > 1
        def modify_cmd(cmd):
            return "perf stat {repeat} -x ';' -e {props} -- {cmd}".format(
                props=",".join(self.misc_settings["properties"]),
                cmd=cmd,
                repeat="--repeat {}".format(self.misc_settings["perf_stat_repeat"]) if do_repeat else ""
            )
        
        def parse_perf_stat(exec_res: self.ExecResult):
            m = {"ov-time": exec_res.time}
            for line in exec_res.stderr.strip().split("\n"):
                if ';' in line:
                    var, empty, descr = line.split(";")[0:3]
                    m[descr] = float(var)
            return m
        
        cmds = [modify_cmd(cmd) for cmd in block["run_cmds"]]
        res = BenchmarkingResultBlock(self.misc_settings["properties"] + ["ov-time"])
        for i in range(runs):
            exec_res = self._exec_command(cmds, block, cpuset, set_id)
            res.add_run_data(parse_perf_stat(exec_res))
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
        cmd = random.choice(cmds)
        executed_cmd = block["cmd_prefix"] + [cmd]
        if cpuset is not None:
            executed_cmd.insert(0, "sudo cset proc --move --force --pid $$ {} > /dev/null"\
                .format(cpuset.get_sub_set(set_id)))
        env = block["env"]
        env.update({'LC_NUMERIC': 'en_US.ASCII'})
        t = time.time()
        executed_cmd = "; ".join(executed_cmd)
        proc = subprocess.Popen(["/usr/bin/zsh", "-c", executed_cmd], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                                env=env)
        out, err = proc.communicate()
        t = time.time() - t
        if proc.poll() > 0:
            msg = "Error executing " + cmd + ": "+ str(err) + " " + str(out)
            logging.error(msg)
            raise BenchmarkingError(msg)
        return self.ExecResult(time=t, stderr=str(err))


class BenchmarkingError(RuntimeError):
    """
    Thrown when the benchmarking of a program block fails.
    """