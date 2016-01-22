import logging
import re
import shutil
import subprocess, os, time
from temci.utils.settings import Settings, SettingsError
from temci.utils.util import ensure_root
from temci.utils.typecheck import *
import cgroupspy

CPUSET_DIR = '/cpuset'
NEW_ROOT_SET = 'bench.root'
BENCH_SET = 'temci.set'
CONTROLLER_SUB_BENCH_SET = 'temci.set.controller'
SUB_BENCH_SET = 'temci.set.{}'

class CPUSet:
    """
    This class allows the usage of cpusets (see `man cpuset`) and therefore requires root privileges.
    It uses the program cset to modify the cpusets.
    """

    def __init__(self, base_core_number: int = None, parallel: int = None, sub_core_number: int = None):
        """
        Initializes the cpu sets an determines the number of parallel programs (parallel_number variable).

        :param base_core_number:
        :param parallel:
        :param sub_core_number:
        :raises ValueError if the passed parameters don't work together on the current platform
        :raises EnvironmentError if the environment can't be setup properly (e.g. no root privileges)
        """
        #self.bench_set = "bench.set"
        logging.info("Initialize CPUSet")
        ensure_root()
        self.own_set = ''
        self.base_core_number = Settings().default(base_core_number, "run/cpuset/base_core_number")
        self.parallel = Settings().default(parallel, "run/cpuset/parallel")
        self.sub_core_number = Settings().default(sub_core_number, "run/cpuset/sub_core_number")
        self.av_cores = self._cpu_range_size("")
        if self.parallel == 0:
            self.parallel_number = 0
        else:
            if self.parallel == -1:
                self.parallel_number = self._number_of_parallel_sets(self.base_core_number,
                                                                     True, self.sub_core_number)
            else:
                self.parallel_number = self.parallel
                if self.parallel > self._number_of_parallel_sets(self.base_core_number, True, self.sub_core_number):
                    raise ValueError("Invalid values for base_core_number and sub_core_number "
                             "on system with just {} cores. Note: The benchmark controller"
                             "needs a cpuset too.".format(self.av_cores))
            self.base_core_number = self.av_cores - self.sub_core_number * self.parallel_number - 1
        av_cores = self._cpu_range_size("")
        typecheck(self.base_core_number, PositiveInt())
        typecheck(self.parallel_number, NaturalNumber())
        self.own_sets = [SUB_BENCH_SET.format(i) for i in range(0, self.parallel_number)] \
                   + [CONTROLLER_SUB_BENCH_SET, NEW_ROOT_SET, BENCH_SET]
        try:
            self._init_cpuset()
        except BaseException:
            logging.error("Forced teardown of CPUSet")
            self.teardown()
            raise
        logging.info("Finished initializing CPUSet")

    def move_process_to_set(self, pid: int, set_id: int):
        """
        Moves the process with the passed id to the parallel sub cpuset with the passed id.
        :param pid: passed process id
        :param set_id: passed parallel sub cpuset id
        """
        try:
            typecheck(pid, Int())
            typecheck(set_id, Int(range=range(0, self.parallel_number)))
            self._move_process_to_set(SUB_BENCH_SET.format(set_id), pid)
        except BaseException:
            logging.error("Forced teardown of CPUSet")
            self.teardown()
            raise

    def get_sub_set(self, set_id: int) -> str:
        typecheck(set_id, Int(range=range(0, self.parallel_number)))
        return SUB_BENCH_SET.format(set_id)

    def teardown(self):
        """
        Tears the created cpusets down and makes the system usable again.
        """
        for set in self.own_sets:
            try:
                self._delete_set(set)
            except EnvironmentError as ex:
                pass
                #logging.error(str(ex))
            except BaseException:
                raise

    def _number_of_parallel_sets(self, base_core_number: int, parallel: bool, sub_core_number: int) -> int:
        typecheck([base_core_number, parallel, sub_core_number], List(Int()))
        if base_core_number + 1 + sub_core_number > self.av_cores:
            raise ValueError("Invalid values for base_core_number and sub_core_number "
                             "on system with just {} cores. Note: The benchmark controller"
                             "needs a cpuset too.".format(self.av_cores))
        av_cores_for_par = self.av_cores - base_core_number - 1
        if parallel:
            return av_cores_for_par // sub_core_number
        return 1

    def _init_cpuset(self):
        """
        Mounts the cpuset pseudo filesystem at "/cpuset" and creates the necessary cpusets.
        :return:
        """
        if not os.path.exists(CPUSET_DIR + "/cgroup.procs"):
            if not os.path.exists(CPUSET_DIR):
                os.mkdir(CPUSET_DIR)
            proc = subprocess.Popen(["bash", "-c", "mount -t cpuset none /cpuset/"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
            out, err = proc.communicate()
            if proc.poll() > 0:
                raise EnvironmentError(
                    "Cannot mount /cpuset. " +
                    "Probably you're you're not in root mode or you've already mounted cpuset elsewhere.", str(err))
        self._create_cpuset(NEW_ROOT_SET, (0, self.base_core_number - 1))
        logging.info("Move all processes to new root cpuset")
        self._move_all_to_new_root()
        if self.parallel == 0: # just use all available cores, as the benchmarked program also runs in it
            self._create_cpuset(CONTROLLER_SUB_BENCH_SET, (self.base_core_number, self.av_cores - 1))
        else:
            self._create_cpuset(CONTROLLER_SUB_BENCH_SET, (self.base_core_number, self.base_core_number))
        self._move_process_to_set(CONTROLLER_SUB_BENCH_SET)
        for i in range(0, self.parallel_number):
            start = self.base_core_number + 1 + (i * self.sub_core_number)
            self._create_cpuset(SUB_BENCH_SET.format(i), (start, start + self.sub_core_number - 1))

    def _cpu_range_of_set(self, name: str) -> str:
        """
        Returns the range of cpu nodes the set with the passed name has.
        :param name: cpuset name
        :return: either "<NUM>-<NUM>" or None if the cpuset doesn't exist
        """
        name = self._relname(name)
        if self._has_set(name):
            res = self._cset("set {}".format(name))
            arr = res.split("\n")[3].strip().split(" ")
            arr = [x for x in arr if x != ""]
            return arr[1] if "-" in arr[1] else "{core}-{core}".format(core=arr[1])
        return None

    def _cpu_range_tuple_of_set(self, name: str) -> tuple:
        """
        Returns the range of cpu nodes the cpuset with passed name has as a tuple
        (first node, last node).
        :param name: cpuset name
        :return: tuple or None if the cpuset doesn't exist
        """
        if self._has_set(name):
            arr = self._cpu_range_of_set(name).split("-")
            return int(arr[0]), int(arr[0 if len(arr) == 1 else 1])
        return None

    def _cpu_range_size(self, name: str) -> int:
        if self._has_set(name):
            f, s = self._cpu_range_tuple_of_set(name)
            return s - f + 1
        return 0

    def _has_set(self, name):
        name = self._relname(name)
        return name + "   " in self._cset("set -rl")

    def _delete_set(self, name: str):
        self._cset("set -r --force -d %s" % NEW_ROOT_SET)

    def _move_all_to_new_root(self, name = 'root', _count: int = 100):
        cpus =  "{}-{}".format(0, self.base_core_number - 1) if self.base_core_number > 1 else 0
        self._set_cpu_affinity_of_set(name, cpus)
        if _count > 0:
            for child in self._child_sets(name):
                if len(child) > 1:
                    #print("moved from {child} to {root}".format(child=child, root=NEW_ROOT_SET))
                    try:
                        self._move_all_to_new_root(child, _count - 1)
                    except EnvironmentError as err:
                        pass
                        #logging.warning(str(err))
        self._move_processes(name, NEW_ROOT_SET)
        #if _count == 100:
        #    self._cset("proc --move -k --force --threads --pid=0-100000 --toset={}".format(NEW_ROOT_SET))

    def _move_processes(self, from_set: str, to_set: str):
        """
        Move all processes from the first to the second cpuset.
        Only some kernel threads are left behind.
        :param from_set: name of the first cpuset
        :param to_set: name of the second cpuset
        """
        from_set, to_set = (self._relname(from_set), self._relname(to_set))
        self._cset("proc --move --kthread --force --threads --fromset %s --toset %s" % (from_set, to_set))

    def _move_process_to_set(self, cpuset: str, pid: int = os.getpid()):
        self._cset("proc --move --force --pid %d --threads %s" % (pid, cpuset))

    def _absname(self, relname: str):
        if "/" in relname:
            return relname
        res = self._cset("set %s" % relname)
        arr = res.split("\n")[-1].strip().split(" ")
        arr = [x for x in arr if x != ""]
        return arr[7]

    def _relname(self, absname: str):
        if not "/" in absname:
            return absname
        return absname.split("/")[-1]

    def _child_sets(self, name: str):
        name = self._relname(name)
        res = self._cset("set %s" % name)
        arr = []
        for line in res.split("\n")[4:]:
            line = line.strip()
            arr.append(line.split(" ")[0])
        return arr

    def _create_cpuset(self, name: str, cpus: tuple):
        typecheck(cpus, Tuple(Int(), Int()))
        cpu_range = "{}-{}".format(*cpus)
        path = []
        for part in name.split("/"):
            path.append(part)
            self._cset("set --cpu {} {} ".format(cpu_range, "/".join(path)))

    def _set_cpu_affinity_of_set(self, set: str, cpus):
        if set == "root":
            set = ""
        app = "cgroup.procs"  if set == "" else set + "/cgroup.procs"
        with open(os.path.join(CPUSET_DIR + "/" + app), "r") as f:
            for line in f.readlines():
                try:
                    self._set_cpu_affinity(int(line.strip()), cpus)
                    #logging.info("success {}".format(line))
                except EnvironmentError as err:
                    pass
                    #logging.error(str(err))

    def _set_cpu_affinity(self, pid: int, cpus):
        cmd = "sudo taskset --all-tasks --cpu-list -p {} {}; sudo nice".format(cpus, pid)
        proc = subprocess.Popen(["/bin/sh", "-c", cmd],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            raise EnvironmentError (
                "taskset error (cmd = '{}'): ".format(cmd) + str(err) + str(out)
            )
        return str(out)

    def _cset(self, argument: str):
        proc = subprocess.Popen(["/bin/sh", "-c", "sudo cset {}".format(argument)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            raise EnvironmentError (
                "Error with cset tool. "
                " More specific error (cmd = 'sudo cset {}'): ".format(argument) + str(err) + str(out)
            )
        return str(out)