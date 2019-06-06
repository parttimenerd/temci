import logging
import multiprocessing
import re
import shutil
import subprocess, os, time
from temci.utils.settings import Settings, SettingsError
from temci.utils.util import has_root_privileges
from temci.utils.typecheck import *
import typing as t

CPUSET_DIR = '/cpuset'  # type: str
""" Location that the cpu set pseudo file system is mounted at """
NEW_ROOT_SET = 'bench.root'  # type: str
""" Name of the new root cpu set that contains most of the processes of the original root set """
BENCH_SET = 'temci.set'  # type: str
""" Name of the base cpu set used by temci for benchmarking purposes """
CONTROLLER_SUB_BENCH_SET = 'temci.set.controller'  # type: str
""" Name of the cpu set used by the temci control process """
SUB_BENCH_SET = 'temci.set.{}'  # type: str
""" Format of cpu sub set names for benchmarking """


class CPUSet:
    """
    This class allows the usage of cpusets (see `man cpuset`) and therefore requires root privileges.
    It uses the program cset to modify the cpusets.
    This class needs root privileges to operate properly. Warns if not.
    """

    def __init__(self, active: bool = True, base_core_number: int = None,
                 parallel: int = None, sub_core_number: int = None):
        """
        Initializes the cpu sets an determines the number of parallel programs (parallel_number variable).

        :param active: are cpu sets actually used?
        :param base_core_number: number of cpu cores for the base (remaining part of the) system
        :param parallel: 0: benchmark sequential, > 0: benchmark parallel with n instances, -1: determine n automatically
        :param sub_core_number: number of cpu cores per parallel running program
        :raises ValueError: if the passed parameters don't work together on the current platform
        :raises EnvironmentError: if the environment can't be setup properly (e.g. no root privileges)
        """
        #self.bench_set = "bench.set"
        self.active = active and has_root_privileges()  # type: bool
        """ Are cpu sets actually used? """
        self.base_core_number = Settings().default(base_core_number, "run/cpuset/base_core_number")  # type: int
        """ Number of cpu cores for the base (remaining part of the) system """
        self.parallel = Settings().default(parallel, "run/cpuset/parallel")  # type: int
        """ 0: benchmark sequential, > 0: benchmark parallel with n instances, -1: determine n automatically """
        self.sub_core_number = Settings().default(sub_core_number, "run/cpuset/sub_core_number")  # type: int
        """ Number of cpu cores per parallel running program """
        self.av_cores = len(self._cpus_of_set("")) if active else multiprocessing.cpu_count()  # zype: int
        """ Number of available cpu cores """
        self.parallel_number = 0  # type: int
        """ Number of used parallel instances, zero if the benchmarking is done sequentially """
        if self.parallel != 0:
            if self.parallel == -1:
                self.parallel_number = self._number_of_parallel_sets(self.base_core_number,
                                                                     True, self.sub_core_number)
            else:
                self.parallel_number = self.parallel
                if self.parallel > self._number_of_parallel_sets(self.base_core_number, True, self.sub_core_number)\
                        and self.active:
                    raise ValueError("Invalid values for base_core_number and sub_core_number "
                             "on system with just {} cores. Note: The benchmark controller "
                             "needs a cpuset too.".format(self.av_cores))
            self.base_core_number = self.av_cores - self.sub_core_number * self.parallel_number - 1
        if not self.active:
            if active and not has_root_privileges():
                logging.warning("CPUSet functionality is disabled because root privileges are missing.")
            return
        logging.info("Initialize CPUSet")
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
        if not self.active:
            return
        try:
            typecheck(pid, Int())
            typecheck(set_id, Int(range=range(0, self.parallel_number)))
            self._move_process_to_set(SUB_BENCH_SET.format(set_id), pid)
        except BaseException:
            logging.error("Forced teardown of CPUSet")
            self.teardown()
            raise

    def get_sub_set(self, set_id: int) -> str:
        """ Gets the name of the benchmarking cpu set with the given id / number (starting at zero). """
        if self.active:
            typecheck(set_id, Int(range=range(0, self.parallel_number)))
        return SUB_BENCH_SET.format(set_id)

    def teardown(self):
        """
        Tears the created cpusets down and makes the system usable again.
        """
        if not self.active:
            return
        for set in self.own_sets:
            try:
                self._delete_set(set)
            except EnvironmentError as ex:
                pass
                #logging.error(str(ex))
            except BaseException:
                raise

    def _number_of_parallel_sets(self, base_core_number: int, parallel: bool, sub_core_number: int) -> int:
        """
        Calculates the number of possible parallel sets.
        """
        typecheck([base_core_number, parallel, sub_core_number], List(Int()))
        if base_core_number + 1 + sub_core_number > self.av_cores and self.active:
            raise ValueError("Invalid values for base_core_number and sub_core_number "
                             "on system with just {} cores. Note: The benchmark controller"
                             "needs a cpuset too.".format(self.av_cores))
        av_cores_for_par = self.av_cores - base_core_number - 1
        if parallel:
            return av_cores_for_par // sub_core_number
        return 1

    def _init_cpuset(self):
        """
        Mounts the cpuset pseudo filesystem at ``CPUSET_DIR`` and creates the necessary cpusets.
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
                    "Probably you're not in root mode or you've already mounted cpuset elsewhere.", str(err))
        self._create_cpuset(NEW_ROOT_SET, self._get_av_cpus()[0: self.base_core_number])
        logging.info("Move all processes to new root cpuset")
        self._move_all_to_new_root()
        if self.parallel == 0: # just use all available cores, as the benchmarked program also runs in it
            self._create_cpuset(CONTROLLER_SUB_BENCH_SET, self._get_av_cpus()[self.base_core_number:self.av_cores])
        else:
            self._create_cpuset(CONTROLLER_SUB_BENCH_SET, self._get_av_cpus()[self.base_core_number:1])
        self._move_process_to_set(CONTROLLER_SUB_BENCH_SET)
        for i in range(0, self.parallel_number):
            start = self.base_core_number + 1 + (i * self.sub_core_number)
            self._create_cpuset(SUB_BENCH_SET.format(i), self._get_av_cpus()[start:start + self.sub_core_number])

    def _cpus_of_set(self, name: str) -> t.Optional[t.List[int]]:
        """ Gets all cpu cores that are assigned to the set with the passed name. """
        name = self._relname(name)
        if self._has_set(name):
            res = self._cset("set {}".format(name))
            arr = res.split("\n")[3].strip().split(" ")
            arr = [x for x in arr if x != ""]
            if "-" in arr[1]:
                start, end = map(int, arr[1].split("-"))
                return list(range(start, end + 1))
            elif "," in arr[1]:
                return list(map(int, arr[1].split(",")))
            else:
                return int(arr[1])
        return None

    def _get_av_cpus(self) -> t.List[int]:
        """ Gets the number of available cpu cores """
        return self._cpus_of_set("")

    def _ints_to_str(self, ints: t.List[int]) -> str:
        """ Turns a list of integers comma separated into a string """
        return ",".join(map(str, ints))

    def _has_set(self, name: str):
        """ Does the set with the given name exist? """
        name = self._relname(name)
        return name + "   " in self._cset("set -rl")

    def _delete_set(self, name: str):
        """ Delete the set with the given name """
        self._cset("set -r --force -d %s" % NEW_ROOT_SET)

    def _move_all_to_new_root(self, name: str = 'root', _count: int = 100):
        """
        Move all process from the root cpu set into the ``NEW_ROOT_SET``

        :param name: name of the root cpu set
        :param _count: maximum cpu set tree depth
        """
        cpus =  self._get_av_cpus()[0:self.base_core_number]
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
        """
        Move the process with the given id into the passed cpu set.

        :param cpuset: name of the passed cpu set
        :param pid: id of the process to move, default is the own process
        """
        self._cset("proc --move --force --pid %d --threads %s" % (pid, cpuset))

    def _absname(self, relname: str):
        """ Get the absolute set name for the given relative """
        if "/" in relname:
            return relname
        res = self._cset("set %s" % relname)
        arr = res.split("\n")[-1].strip().split(" ")
        arr = [x for x in arr if x != ""]
        return arr[7]

    def _relname(self, absname: str):
        """ Get the realtive set name for the given absolute """
        if not "/" in absname:
            return absname
        return absname.split("/")[-1]

    def _child_sets(self, name: str) -> t.List[str]:
        """ Get the list of child set for the set with the given name """
        name = self._relname(name)
        res = self._cset("set %s" % name)
        arr = []
        for line in res.split("\n")[4:]:
            line = line.strip()
            arr.append(line.split(" ")[0])
        return arr

    def _create_cpuset(self, name: str, cpus: t.List[int]):
        """ Create the cpuset with the given name and assign the given cpu cores to it """
        typecheck(cpus, List(Int()))
        cpu_range = self._ints_to_str(cpus)
        path = []
        for part in name.split("/"):
            path.append(part)
            self._cset("set --cpu {} {} ".format(cpu_range, "/".join(path)))

    def _set_cpu_affinity_of_set(self, set: str, cpus: t.List[int]):
        """ Set the cpu affinity for all processes that belong to the given set """
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

    def _set_cpu_affinity(self, pid: int, cpus: t.List[int]):
        """ Set the cpu affinity for the given process to the given cpu cores """
        cmd = "taskset --all-tasks --cpu-list -p {} {}; nice".format(self._ints_to_str(cpus), pid)
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
        """
        Execute the passed argument with the cset tool.

        :param passed argument for the tool
        :return: output of executing the combined command
        :raises EnvironmentError: if something goes wrong
        """
        #cmd = ["/bin/sh", "-c", "sudo cset {}".format(argument)]
        cmd = ["/bin/sh", "-c", "python3 -c 'import cpuset.main; print(cpuset.main.main())' " + argument]
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            raise EnvironmentError(
                "Error with cset tool. "
                " More specific error (cmd = 'cset {}'): ".format(argument) + str(err) + str(out)
            )
        return str(out)
