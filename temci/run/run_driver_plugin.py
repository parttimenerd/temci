"""
This module consists of run driver plugin implementations.
"""

from .run_driver import RunProgramBlock
from ..utils.util import ensure_root
from .run_driver import ExecRunDriver
from ..utils.registry import register
from ..utils.typecheck import *
import temci.setup.setup as setup
import subprocess, shlex, logging, os, signal, random, multiprocessing, time
import numpy as np


class AbstractRunDriverPlugin:
    """
    A plugin for a run driver. It allows additional modifications.
    The object is instantiated before the benchmarking starts and
    used for the whole benchmarking runs.
    """

    def __init__(self, misc_settings):
        self.misc_settings = misc_settings

    def setup(self):
        """
        Called before the whole benchmarking starts
        (e.g. to set the "nice" value of the benchmarking process).
        """
        pass

    def setup_block(self, block: RunProgramBlock, runs: int = 1):
        """
        Called before each run program block is run "runs" time.
        :param block: run program block to modify
        :param runs: number of times the program block is run at once.
        """
        pass

    def setup_block_run(self, block: RunProgramBlock):
        """
        Called before each run program block is run.
        :param block: run program block to modify
        """
        pass

    def teardown_block(self, block: RunProgramBlock):
        """
        Called after each run program block is run.
        :param block: run program block
        """
        pass

    def teardown(self):
        """
        Called after the whole benchmarking is finished.
        :return:
        """
        pass

    def _exec_command(self, cmd: str) -> str:
        proc = subprocess.Popen(["/bin/bash", "-c", cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            msg = "Error executing '" + cmd + "' in {}: ".format(type(self)) + str(err) + " " + str(out)
            logging.error(msg)
            raise EnvironmentError(msg)
        return str(out)


@register(ExecRunDriver, "nice", Dict({
    "nice": Int(range=range(-20, 20)) // Description("Niceness values range from -20 (most favorable "
                                                     "to the process) to 19 (least favorable to the process).")
                                      // Default(-15),
    "io_nice": Int(range=range(0, 4)) // Description("Specify the name or number of the scheduling class to use;"
                                                     "0 for none, 1 for realtime, 2 for best-effort, 3 for idle.")
                                      // Default(1)
}))
class NicePlugin(AbstractRunDriverPlugin):
    """
    Allows the setting of the nice and ionice values of the benchmarking process.
    """

    def __init__(self, misc_settings):
        super().__init__(misc_settings)
        self.old_nice = int(self._exec_command("nice"))
        self.old_io_nice = int(self._exec_command("ionice").split(" prio ")[1])

    def setup(self):
        ensure_root()
        self._set_nice(self.misc_settings["nice"])
        self._set_io_nice(self.misc_settings["io_nice"])

    def _set_nice(self, nice: int):
        self._exec_command("sudo renice -n {} -p {}".format(nice, os.getpid()))

    def _set_io_nice(self, nice: int):
        self._exec_command("sudo ionice -n {} -p {}".format(nice, os.getpid()))

    def teardown(self):
        self._set_nice(self.old_nice)
        self._set_io_nice(self.old_io_nice)


@register(ExecRunDriver, "env_randomize", Dict({
    "min": NaturalNumber() // Default(0) // Description("Minimum number of added random environment variables"),
    "max": PositiveInt() // Default(100) // Description("Maximum number of added random environment variables"),
    "var_max": PositiveInt() // Default(1000) // Description("Maximum length of each random value"),
    "key_max": PositiveInt() // Default(100) // Description("Maximum length of each random key")
}))
class EnvRandomizePlugin(AbstractRunDriverPlugin):
    """
    Adds random environment variables.
    """

    def setup_block(self, block: RunProgramBlock, runs: int = 1):
        env = {}
        for i in range(random.randint(self.misc_settings["min"], self.misc_settings["max"])):
            env["a" * random.randint(0, self.misc_settings["key_max"])] \
                = "a" * random.randint(0, self.misc_settings["var_max"])
        block["env"] = env


@register(ExecRunDriver, "preheat", Dict({
    "time": NaturalNumber() // Default(10)
            // Description("Number of seconds to preheat the system with an cpu bound task")
}))
class PreheatPlugin(AbstractRunDriverPlugin):
    """
    Preheats the system with a cpu bound task
    (calculating the inverse of a big random matrice with numpy).
    """

    def setup(self):
        heat_time = self.misc_settings["time"]
        logging.info("Preheat the system for {} seconds with a cpu bound task"
                     .format(heat_time))
        cmd = "timeout {} python3 -c 'import numpy as np; " \
              "m = np.random.randint(0, 100, (500, 500)); " \
              "print(list(map(lambda x: len(np.linalg.eig(m)), range(10000))))' > /dev/null".format(heat_time)
        procs = []
        for i in range(0, multiprocessing.cpu_count()):
            proc = subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True)
            procs.append(proc)
        time.sleep(heat_time)
        for proc in procs:
            try:
                proc.poll()
            except BaseException as ex:
                logging.error(ex)


@register(ExecRunDriver, "other_nice", Dict({
    "nice": Int(range=range(-20, 20)) // Description("Niceness values for other processes.")
                                      // Default(18)
}))
class OtherNicePlugin(AbstractRunDriverPlugin):
    """
    Allows the setting of the nice value of all other processes (tha have nice > -10).
    """

    def __init__(self, misc_settings):
        ensure_root()
        super().__init__(misc_settings)
        self.old_nices = {}


    def setup(self):
        ensure_root()
        for line in self._exec_command("sudo /bin/ps --noheaders -e -o pid,nice").split("\n"):
            line = line.strip()
            arr = list(filter(lambda x: len(x) > 0, line.split(" ")))
            if len(arr) == 0:
                continue
            pid = int(arr[0].strip())
            nice = arr[1].strip()
            if nice != "-" and int(nice) > -10 and pid != os.getpid():
                self.old_nices[pid] = int(nice)
                try:
                    self._set_nice(pid, self.misc_settings["nice"])
                except EnvironmentError as err:
                    logging.info(err)

    def _set_nice(self, pid: int, nice: int):
        self._exec_command("sudo renice -n {} -p {}".format(nice, pid))

    def teardown(self):
        for pid in self.old_nices:
            try:
                self._set_nice(pid, self.old_nices[pid])
            except EnvironmentError as err:
                logging.info(err)


@register(ExecRunDriver, "stop_start", Dict({
    "min_nice": Int(range=range(-15, 20)) // Default(-10)
                // Description("Processes with lower nice values are ignored.")
}))
class StopStartPlugin(AbstractRunDriverPlugin):
    """
    Stop almost all other processes.
    """

    def __init__(self, misc_settings):
        ensure_root()
        super().__init__(misc_settings)
        self.pids = []


    def setup(self):
        ensure_root()
        for line in self._exec_command("/bin/ps --noheaders -e -o pid,nice").split("\n"):
            line = line.strip()
            arr = list(filter(lambda x: len(x) > 0, line.split(" ")))
            if len(arr) == 0:
                continue
            pid = int(arr[0].strip())
            nice = arr[1].strip()
            if nice != "-" and int(nice) >= self.misc_settings["min_nice"] and pid != os.getpid():
                self.pids.append(pid)
        self._send_signal(signal.SIGSTOP)

    def _send_signal(self, signal: int):
        for pid in self.pids:
            try:
                os.kill(pid, signal)
            except BaseException as ex:
                pass

    def teardown(self):
        self._send_signal(signal.SIGCONT)


@register(ExecRunDriver, "sync", Dict({}))
class SyncPlugin(AbstractRunDriverPlugin):
    """
    Call sync before each program execution.
    """

    def setup_block_run(self, block: RunProgramBlock, runs: int = 1):
        os.sync()


@register(ExecRunDriver, "sleep", Dict({
    "seconds": PositiveInt() // Default(10) // Description("Seconds to sleep")
}))
class SleepPlugin(AbstractRunDriverPlugin):
    """
    Sleep a given amount of time before the benchmarking begins.

    See Gernot Heisers Systems Benchmarking Crimes:
    Make sure that the system is really quiescent when starting an experiment,
    leave enough time to ensure all previous data is flushed out.
    """

    def setup_block(self, block: RunProgramBlock, runs: int = 1):
        block["cmd_prefix"].append("sleep {}".format(self.misc_settings["seconds"]))


@register(ExecRunDriver, "drop_fs_caches", Dict({
    "free_pagecache": Bool() // Default(True) // Description("Free the page cache"),
    "free_dentries_inodes": Bool() // Default(True) // Description("Free dentries and inodes")
}))
class DropFSCaches(AbstractRunDriverPlugin):
    """
    Frees some (file system) caches before every benchmarking run.
    """

    def setup(self):
        ensure_root()

    def setup_block_run(self, block: RunProgramBlock):
        num = self.misc_settings["free_pagecache"] + 2 * self.misc_settings["free_dentries_inodes"]
        self._exec_command("sudo sync; sudo sh -c 'echo {} > /proc/sys/vm/drop_caches'".format(num))


@register(ExecRunDriver, "disable_swap", Dict({}))
class DisableSwap(AbstractRunDriverPlugin):
    """
    Disables swapping on the system before the benchmarking and enables it after.
    """

    def setup(self):
        ensure_root()
        self._exec_command("sudo swapoff -a")

    def teardown(self):
        self._exec_command("sudo swapon -a")


@register(ExecRunDriver, "disable_cpu_caches", Dict({}))
class DisableCPUCaches(AbstractRunDriverPlugin):
    """
    Disable the L1 and L2 caches on x86 and x86-64 architectures.
    Uses a small custom kernel module (be sure to compile it via `temci setup`).

    :warning slows program down significantly and has probably other weird consequences
    :warning this is untested
    :warning a linux-forum user declared: Disabling cpu caches gives you a pentium I like processor!!!
    """

    def setup(self):
        ensure_root()
        setup.exec("cpu_cache", "sudo insmod disable_cache.ko")

    def teardown(self):
        setup.exec("cpu_cache", "sudo rmmod disable_cache.ko")


@register(ExecRunDriver, "cpu_governor", Dict({
    "governor": Str() // Default("performance") // Description("New scaling governor for all cpus")
}))
class CPUGovernor(AbstractRunDriverPlugin):
    """
    Allows the setting of the scaling governor of all cpu cores, to ensure that all use the same.
    """

    def setup(self):
        cpu_dir_temp = "/sys/devices/system/cpu/cpu{}/cpufreq/"
        self.cpu_paths = []
        self.old_governors = []
        self.av_governors = []
        num = 0
        while os.path.exists(cpu_dir_temp.format(num)) and os.path.isdir(cpu_dir_temp.format(num)):
            cpu_path = cpu_dir_temp.format(num)
            self.cpu_paths.append(cpu_path)
            with open(cpu_path + "scaling_governor", "r") as f:
                self.old_governors.append(f.readline().strip())
            with open(cpu_path + "scaling_available_governors") as f:
                self.av_governors.append(f.readline().strip().split(" "))
            num += 1
        for cpu in range(len(self.cpu_paths)):
            self._set_scaling_governor(cpu, self.misc_settings["governor"])

    def teardown(self):
        for cpu in range(len(self.cpu_paths)):
            self._set_scaling_governor(cpu, self.old_governors[cpu])

    def _set_scaling_governor(self, cpu: int, governor: str):
        assert cpu <= len(self.cpu_paths)
        if governor not in self.av_governors:
            raise ValueError("No such governor {} for cpu {}, expected one of these: ".
                             format(cpu, governor, ", ".join(self.av_governors)))
        with open(self.cpu_paths[cpu] + "scaling_governor", "w") as f:
            self._exec_command("sudo bash -c 'echo {gov} >  {p}scaling_governor'"
                               .format(gov=governor, p=self.cpu_paths[cpu]))
