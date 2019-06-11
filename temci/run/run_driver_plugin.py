"""
This module consists of run driver plugin implementations.
"""
from temci.run.run_worker_pool import AbstractRunWorkerPool
from temci.utils.registry import register
from temci.utils.settings import Settings
from temci.utils.util import get_memory_page_size, does_program_exist, does_command_succeed, has_root_privileges
from .run_driver import RunProgramBlock
from .run_driver import ExecRunDriver
from ..utils.typecheck import *
import temci.setup.setup as setup
import subprocess, logging, os, signal, random, multiprocessing, time
import typing as t

class AbstractRunDriverPlugin:
    """
    A plugin for a run driver. It allows additional modifications.
    The object is instantiated before the benchmarking starts and
    used for the whole benchmarking runs.
    """

    needs_root_privileges = False  # type: bool
    """ Does this plugin work only with root privileges? """

    def __init__(self, misc_settings):
        """
        Creates an instance.

        :param misc_settings: configuration of this plugin
        """
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
        :param runs: number of times the program block is run (and measured) at once.
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
        """
        pass

    def _exec_command(self, cmd: str) -> str:
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            msg = "Error executing '" + cmd + "' in {}: ".format(type(self)) + str(err) + " " + str(out)
            #logging.error(msg)
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

    needs_root_privileges = True

    def __init__(self, misc_settings):
        super().__init__(misc_settings)
        self._old_nice = int(self._exec_command("nice"))
        self._old_io_nice = int(self._exec_command("ionice").split(" prio ")[1])

    def setup(self):
        self._set_nice(self.misc_settings["nice"])
        self._set_io_nice(self.misc_settings["io_nice"])

    def _set_nice(self, nice: int):
        self._exec_command("renice -n {} -p {}".format(nice, os.getpid()))

    def _set_io_nice(self, nice: int):
        self._exec_command("ionice -n {} -p {}".format(nice, os.getpid()))

    def teardown(self):
        self._set_nice(self._old_nice)
        self._set_io_nice(self._old_io_nice)


@register(ExecRunDriver, "env_randomize", Dict({
    "min": NaturalNumber() // Default(4) // Description("Minimum number of added random environment variables"),
    "max": PositiveInt() // Default(4) // Description("Maximum number of added random environment variables"),
    "var_max": PositiveInt() // Default(get_memory_page_size()) // Description("Maximum length of each random value"),
    "key_max": PositiveInt() // Default(get_memory_page_size()) // Description("Maximum length of each random key")
}))
class EnvRandomizePlugin(AbstractRunDriverPlugin):
    """
    Adds random environment variables.
    """

    def setup_block_run(self, block: RunProgramBlock, runs: int = 1):
        env = {}
        for i in range(random.randint(self.misc_settings["min"], self.misc_settings["max"] + 1)):
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
        if does_command_succeed("python3 -c 'import numpy as np; '") and does_program_exist("bash"):
            # source: http://bruxy.regnet.cz/web/linux/EN/mandelbrot-set-in-bash/
            cmd = """bash -c "
            #!/bin/bash
            S0=S;S1=H;S2=E;S3=L;S4=L;e=echo;b=bc;I=-1;for x in {1..24};
            do R=-2;for y in {1..80};do B=0;r=0;i=0;while [ $B -le 32 ];do
            r2=`$e "$r*$r"|$b`;i2=`$e "$i*$i"|$b`;i=`$e "2*$i*$r+$I"|$b`;
            r=`$e "$r2-$i2+$R"|$b`;: $((B+=1));V=`$e "($r2 +$i2)>4"|$b`;
            if [ "$V" -eq 1 ];then break;fi;done; if [ $B -ge 32 ];then
            $e -n " ";else U=$(((B*4)/15+30));$e -en "\E[01;$U""m";C=$((C%5));
            eval "$e -ne \$E\$S$C";: $((C+=1));fi;R=`$e "$R+0.03125"|$b`
            done;$e -e "\E[m\E(\r";I=`$e "$I+0.08333"|$b`;done      #(c)BruXy "
            """
        procs = []
        for i in range(0, multiprocessing.cpu_count()):
            proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
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
                                      // Default(19),
    "min_nice": Int(range=range(-15, 20)) // Default(-10)
                // Description("Processes with lower nice values are ignored.")
}))
class OtherNicePlugin(AbstractRunDriverPlugin):
    """
    Allows the setting of the nice value of most other processes (as far as possible).
    """

    def __init__(self, misc_settings):
        super().__init__(misc_settings)
        self._old_nices = {}

    def setup(self):
        for line in self._exec_command("/bin/ps --noheaders -e -o pid,nice").split("\n"):
            line = line.strip()
            arr = list(filter(lambda x: len(x) > 0, line.split(" ")))
            if len(arr) == 0:
                continue
            pid = int(arr[0].strip())
            nice = arr[1].strip()
            if nice != "-" and int(nice) > self.misc_settings["min_nice"] and pid != os.getpid():
                self._old_nices[pid] = int(nice)
                try:
                    self._set_nice(pid, self.misc_settings["nice"])
                except EnvironmentError as err:
                    #logging.info(err)
                    pass

    def _set_nice(self, pid: int, nice: int):
        self._exec_command("renice -n {} -p {}".format(nice, pid))

    def teardown(self):
        for pid in self._old_nices:
            try:
                self._set_nice(pid, self._old_nices[pid])
            except EnvironmentError as err:
                #logging.info(err)
                pass


@register(ExecRunDriver, "stop_start", Dict({
    "min_nice": Int(range=range(-15, 20)) // Default(-10)
                // Description("Processes with lower nice values are ignored."),
    "min_id": PositiveInt() // Default(1500)
                // Description("Processes with lower id are ignored."),
    "comm_prefixes": ListOrTuple(Str()) // Default(["ssh", "xorg", "bluetoothd"])
                // Description("Each process which name (lower cased) starts with one of the prefixes is not ignored. "
                               "Overrides the decision based on the min_id."),
    "comm_prefixes_ignored": ListOrTuple(Str()) // Default(["dbus", "kworker"])
                // Description("Each process which name (lower cased) starts with one of the prefixes is ignored. "
                               "It overrides the decisions based on comm_prefixes and min_id."),
    "subtree_suffixes": ListOrTuple(Str()) // Default(["dm", "apache"])
                        // Description("Suffixes of processes names which are stopped."),
    "dry_run": Bool() // Default(False)
               // Description("Just output the to be stopped processes but don't actually stop them?")
}))
class StopStartPlugin(AbstractRunDriverPlugin):
    """
    Stop almost all other processes (as far as possible).
    """

    def __init__(self, misc_settings):
        super().__init__(misc_settings)
        self._processes = {}  # type: t.Dict[str, t.Union[str, int]]
        self._pids = []  # type: t.List[int]

    def parse_processes(self):
        self._processes = {}
        for line in self._exec_command("/bin/ps --noheaders -e -o pid,nice,comm,cmd,ppid").split("\n"):
            line = line.strip()
            arr = list(map(lambda x: x.strip(), filter(lambda x: len(x) > 0, line.split(" "))))
            if len(arr) == 0:
                continue
            self._processes[int(arr[0])] = {
                "pid": int(arr[0]) if arr[0] != "-" else -1,
                "nice": int(arr[1]) if arr[1] != "-" else -20,
                "comm": arr[2],
                "cmd": arr[3],
                "ppid": int(arr[4]) if len(arr) == 5 else 0
            }

    def _get_ppids(self, pid: int) -> t.List[int]:
        ppids = []
        cur_pid = pid
        while cur_pid >= 1:
            cur_pid = self._processes[cur_pid]["ppid"]
            if cur_pid != 0:
                ppids.append(cur_pid)
        return ppids

    def _get_pcomms(self, pid: int) -> t.List[str]:
        return [self._processes[id]["comm"] for id in self._get_ppids(pid)]

    def _get_child_pids(self, pid: int) -> t.List[int]:
        ids = []
        for proc in self._processes:
            if proc["ppid"] == pid:
                ids.append(proc["ppid"])
        return ids

    def _get_child_comms(self, pid: int) -> t.List[str]:
        return [self._processes[id] for id in self._get_child_pids(pid)]

    def _proc_dict_to_str(self, proc_dict: t.Dict) -> str:
        return "Process(id={pid:5d}, parent={ppid:5d}, nice={nice:2d}, name={comm})".format(**proc_dict)

    def setup(self):
        self.parse_processes()
        for proc in self._processes.values():
            if proc["pid"] == os.getpid():
                continue
            if any(proc["comm"].startswith(pref) for pref in self.misc_settings["comm_prefixes_ignored"]):
                continue
            if proc["nice"] == "-" or int(proc["nice"]) < self.misc_settings["min_nice"]:
                continue
            suffixes = self.misc_settings["subtree_suffixes"]
            if any(proc["comm"].startswith(pref) for pref in self.misc_settings["comm_prefixes"]) or \
                    proc["pid"] >= self.misc_settings["min_id"] or \
                    any(any(pcomm.endswith(suff) for suff in suffixes) for pcomm in self._get_pcomms(proc["pid"])):
                if self.misc_settings["dry_run"]:
                    logging.info(self._proc_dict_to_str(proc))
                else:
                    self._pids.append(proc["pid"])
        if self.misc_settings["dry_run"]:
            raise KeyboardInterrupt()
        self._send_signal(signal.SIGSTOP)

    def _send_signal(self, signal: int):
        for pid in self._pids:
            try:
                os.kill(pid, signal)
            except BaseException as ex:
                #logging.info(ex)
                pass

    def teardown(self):
        self._send_signal(signal.SIGCONT)


@register(ExecRunDriver, "sync", Dict({}))
class SyncPlugin(AbstractRunDriverPlugin):
    """
    Calls ``sync`` before each program execution.
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
    Drop page cache, directoy entries and inodes before every benchmarking run.
    """

    needs_root_privileges = True

    def setup_block_run(self, block: RunProgramBlock):
        num = self.misc_settings["free_pagecache"] + 2 * self.misc_settings["free_dentries_inodes"]
        self._exec_command("sync; echo {} > /proc/sys/vm/drop_caches".format(num))


@register(ExecRunDriver, "disable_swap", Dict({}))
class DisableSwap(AbstractRunDriverPlugin):
    """
    Disables swapping on the system before the benchmarking and enables it after.
    """

    needs_root_privileges = True

    def setup(self):
        self._exec_command("swapoff -a")

    def teardown(self):
        self._exec_command("swapon -a")


@register(ExecRunDriver, "disable_cpu_caches", Dict({}))
class DisableCPUCaches(AbstractRunDriverPlugin):
    """
    Disable the L1 and L2 caches on x86 and x86-64 architectures.
    Uses a small custom kernel module (be sure to compile it via 'temci setup').

    :warning: slows program down significantly and has probably other weird consequences
    :warning: this is untested
    :warning: a linux-forum user declared: Disabling cpu caches gives you a pentium I like processor!!!
    """

    needs_root_privileges = True

    def setup(self):
        setup.exec("cpu_cache", "insmod disable_cache.ko")

    def teardown(self):
        setup.exec("cpu_cache", "rmmod disable_cache.ko")


@register(ExecRunDriver, "cpu_governor", Dict({
    "governor": Str() // Default("performance") // Description("New scaling governor for all cpus")
}))
class CPUGovernor(AbstractRunDriverPlugin):
    """
    Allows the setting of the scaling governor of all cpu cores, to ensure that all use the same.
    """

    needs_root_privileges = True

    def __init__(self, misc_settings):
        super().__init__(misc_settings)
        self._cpu_paths = []  # type: t.List[str]
        self._old_governors = []  # type: t.List[str]
        self._av_governors = []  # type: t.List[str]

    def setup(self):
        cpu_dir_temp = "/sys/devices/system/cpu/cpu{}/cpufreq/"
        num = 0
        while os.path.exists(cpu_dir_temp.format(num)) and os.path.isdir(cpu_dir_temp.format(num)):
            cpu_path = cpu_dir_temp.format(num)
            self._cpu_paths.append(cpu_path)
            with open(cpu_path + "scaling_governor", "r") as f:
                self._old_governors.append(f.readline().strip())
            with open(cpu_path + "scaling_available_governors") as f:
                self._av_governors.extend(f.readline().strip().split(" "))
            num += 1
        for cpu in range(len(self._cpu_paths)):
            self._set_scaling_governor(cpu, self.misc_settings["governor"])

    def teardown(self):
        for cpu in range(len(self._cpu_paths)):
            self._set_scaling_governor(cpu, self._old_governors[cpu])

    def _set_scaling_governor(self, cpu: int, governor: str):
        assert cpu <= len(self._cpu_paths)
        if governor not in self._av_governors:
            raise ValueError("No such governor {} for cpu {}, expected one of these: ".
                             format(cpu, governor, ", ".join(self._av_governors)))
        cpu_file = self._cpu_paths[cpu] + "scaling_governor"
        if list(open(cpu_file, "r"))[0].strip() != governor:
            try:
                self._exec_command("echo {} >  {}".format(governor, cpu_file))
            except EnvironmentError as err:
                logging.info(err)


@register(ExecRunDriver, "disable_aslr", Dict({}))
class DisableASLR(AbstractRunDriverPlugin):
    """
    Disable address space randomization
    """

    needs_root_privileges = True

    def setup(self):
        self._exec_command("echo 0 > /proc/sys/kernel/randomize_va_space")

    def teardown(self):
        self._exec_command("echo 1 > /proc/sys/kernel/randomize_va_space")


@register(ExecRunDriver, "disable_ht", Dict({}))
class DisableHyperThreading(AbstractRunDriverPlugin):
    """
    Disable hyper-threading
    """

    needs_root_privileges = True

    def setup(self):
        AbstractRunWorkerPool.disable_hyper_threading()

    def teardown(self):
        AbstractRunWorkerPool.enable_hyper_threading()


@register(ExecRunDriver, "disable_intel_turbo", Dict({}))
class DisableIntelTurbo(AbstractRunDriverPlugin):
    """
    Disable intel turbo mode
    """

    needs_root_privileges = True

    def setup(self):
        self._exec_command("echo 1 > /sys/devices/system/cpu/intel_pstate/no_turbo")

    def teardown(self):
        self._exec_command("echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo")


@register(ExecRunDriver, "cpuset", Dict({}))
class DisableIntelTurbo(AbstractRunDriverPlugin):
    """
    Enable cpusets, simply sets run/cpuset/active to true
    """

    needs_root_privileges = True

    def setup(self):
        Settings()["run/cpuset/active"] = True
