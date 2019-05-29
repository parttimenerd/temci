"""
This module consists of the abstract run worker pool class and several implementations.
"""
import re

import time

import humanfriendly

from temci.utils.util import has_root_privileges, parse_timespan
from ..utils.typecheck import *
from ..utils.settings import Settings
from .run_driver import RunProgramBlock, BenchmarkingResultBlock, AbstractRunDriver, RunDriverRegistry
from queue import Queue, Empty
from .cpuset import CPUSet
import logging, threading, subprocess, shlex, os, tempfile
import typing as t


ResultGenerator = t.Iterator[t.Tuple[RunProgramBlock, BenchmarkingResultBlock, int]]
""" Return type of the run worker pool ``results`` method """


class AbstractRunWorkerPool:
    """
    An abstract run worker pool that just deals with the hyper threading setting.
    """

    def __init__(self, run_driver_name: str = None, end_time: float = -1):
        """
        Create an instance.

        :param run_driver_name: name of the used run driver, if None the one configured in the settings is used
        """
        self.submit_queue = Queue()  # type: Queue
        """ Queue for submitted but not benchmarked run program blocks """
        self.result_queue = Queue()  # type: Queue
        """
        Queue of benchmarking results.
        The queue items are tuples consisting of
        the benchmarked block, the benchmarking result and the
        blocks id.
        """
        self.parallel_number = 1  # type: int
        """ Number of instances in which the benchmarks takes place in parallel """
        run_driver_name = run_driver_name or RunDriverRegistry.get_used()
        self.run_driver = RunDriverRegistry().get_for_name(run_driver_name)  # type: AbstractRunDriver
        """ Used run driver instance """
        self.cpuset = None  # type: CPUSet
        self.end_time = end_time
        """ Used cpu set instance """
        if Settings()["run/disable_hyper_threading"]:
            if not has_root_privileges():
                logging.warning("Can't disable hyper threading as root privileges are missing")
                return
            #if Settings()["run/cpuset/active"]:
            #    logging.warning("Currently disabling hyper threading doesn't work well in combination with cpusets")
            #    return
            self.disable_hyper_threading()

    def submit(self, block: RunProgramBlock, id: int, runs: int):
        """
        Submits the passed block for "runs" times benchmarking.
        It also sets the blocks is_enqueued property to True.

        :param block: passed run program block
        :param id: id of the passed block
        :param runs: number of individual benchmarking runs
        """
        raise NotImplementedError()

    def results(self, expected_num: int) \
            -> ResultGenerator:
        """
        A generator for all available benchmarking results.
        The items of this generator are tuples consisting of
        the benchmarked block, the benchmarking result and the
        blocks id.

        :param expected_num: expected number of results
        """
        raise NotImplementedError()

    def teardown(self):
        """
        Tears down the inherited run driver.
        This should be called if all benchmarking with this pool is finished.
        """
        if Settings()["run/disable_hyper_threading"]:
            self.enable_hyper_threading()

    def time_left(self) -> float:
        """
        Does not work properly if self.end_time == -1
        """
        return max(self.end_time - time.time(), 0)

    def has_time_left(self) -> bool:
        return self.end_time == -1 or self.time_left() > 0

    @classmethod
    def get_hyper_threading_cores(cls) -> t.List[int]:
        """
         Adapted from http://unix.stackexchange.com/a/223322
        """
        total_logical_cpus = 0
        total_physical_cpus = 0
        total_cores = 0
        cpu = None

        logical_cpus = {}
        physical_cpus = {}
        cores = {}

        hyperthreading = False

        for line in open('/proc/cpuinfo').readlines():
            if re.match('processor', line):
                cpu = int(line.split()[2])

                if cpu not in  logical_cpus:
                    logical_cpus[cpu] = []
                    total_logical_cpus += 1

            if re.match('physical id', line):
                phys_id = int(line.split()[3])

                if phys_id not in physical_cpus:
                    physical_cpus[phys_id] = []
                    total_physical_cpus += 1

            if re.match('core id', line):
                core = int(line.split()[3])

                if core not in cores:
                    cores[core] = []
                    total_cores += 1

                cores[core].append(cpu)

        if (total_cores * total_physical_cpus) * 2 == total_logical_cpus:
            hyperthreading = True

        ht_cores = []  # type: t.List[int]

        if hyperthreading:

            for c in cores:
                for p, val in enumerate(cores[c]):
                    if p > 0:
                        ht_cores.append(val)
        return ht_cores

    def next_block_timeout(self) -> float:
        timeout = parse_timespan(Settings()["run/max_block_time"])
        if not self.has_time_left():
            return 0
        if timeout > -1:
            return max(min(self.time_left() if self.end_time != -1 else timeout, timeout), 0)
        return -1 if self.end_time == -1 else max(self.time_left(), 0)

    @classmethod
    def disable_hyper_threading(cls):
        if has_root_privileges():
            cls._set_status_of_ht_cores(cls.get_hyper_threading_cores(), 0)

    @classmethod
    def enable_hyper_threading(cls):
        if has_root_privileges():
            cls._set_status_of_ht_cores(cls.get_hyper_threading_cores(), 1)

    @classmethod
    def _set_status_of_ht_cores(cls, ht_cores: t.List[int], online_status: int):
        if len(ht_cores) == 0:
            return
        arg = "\n".join("echo {} > /sys/devices/system/cpu/cpu{}/online"
                        .format(online_status, core_id) for core_id in ht_cores)
        proc = subprocess.Popen(["/bin/sh", "-c", arg],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            raise EnvironmentError("Error while disabling the hyper threaded cores: " + str(err))


class RunWorkerPool(AbstractRunWorkerPool):
    """
    This run worker pool implements the sequential benchmarking of program blocks.
    """

    def __init__(self, run_driver_name: str = None, end_time: float = -1):
        super().__init__(run_driver_name, end_time)
        if run_driver_name is None:
            run_driver_name = RunDriverRegistry().get_used()
        self.cpuset = CPUSet(parallel=0) if Settings()["run/cpuset/active"] else CPUSet(active=False)
        self.parallel_number = 1

    def submit(self, block: RunProgramBlock, id: int, runs: int):
        typecheck(block, RunProgramBlock)
        typecheck(runs, NaturalNumber())
        typecheck(id, NaturalNumber())
        block.is_enqueued = True
        self.result_queue.put((block, self.run_driver.benchmark(block, runs, timeout=self.next_block_timeout()), id))
        block.is_enqueued = False

    def results(self, expected_num: int) -> ResultGenerator:
        for i in range(expected_num):#while not self.result_queue.empty():
            yield self.result_queue.get()

    def teardown(self):
        super().teardown()
        self.run_driver.teardown()
        if self.cpuset is not None:
            self.cpuset.teardown()


class ParallelRunWorkerPool(AbstractRunWorkerPool):
    """
    This run worker pool implements the parallel benchmarking of program blocks.
    It uses a server-client-model to benchmark on different cpu cores.
    """

    def __init__(self, run_driver_name: str = None, end_time: float = -1):
        super().__init__(run_driver_name, end_time)
        if run_driver_name is None:
            run_driver_name = RunDriverRegistry().get_used()
        if Settings()["run/cpuset/active"]:
            self.cpuset = CPUSet()
        else:
            self.cpuset = CPUSet(active=False)
            #raise ValueError("Only works with run/cpuset/active=True")
        self.parallel_number = self.cpuset.parallel_number
        logging.info("Using {} parallel processes to benchmark.".format(self.parallel_number))
        self.threads = []  # type: t.List[BenchmarkingThread]
        """ Running benchmarking threads """
        try:
            for i in range(0, self.parallel_number):
                thread = BenchmarkingThread(i, self, self.run_driver, self.cpuset)
                self.threads.append(thread)
                thread.start()
        except BaseException:
            logging.error("Forced teardown of ParallelRunWorkerPool")
            self.teardown()
            raise

    def submit(self, block: RunProgramBlock, id: int, runs: int):
        if self.time_left() <= 0:
            return
        typecheck(block, RunProgramBlock)
        typecheck(runs, NaturalNumber())
        typecheck(id, NaturalNumber())
        block.is_enqueued = True
        self.submit_queue.put((block, id, runs))

    def results(self, expected_num: int) -> ResultGenerator:
        #while not self.intermediate_queue.empty() or not self.submit_queue.empty() or not self.result_queue.empty():
        for i in range(expected_num):#while not self.submit_queue.empty() or not self.result_queue.empty() or not self.submit_queue.all_tasks_done:
            yield self.result_queue.get()

    def teardown(self):
        super().teardown()
        self.cpuset.teardown()
        self.run_driver.teardown()
        try:
            for thread in self.threads:
                thread.stop = True
                #thread.teardown()
        except:
            pass


class BenchmarkingThread(threading.Thread):
    """
    A thread that allows parallel benchmarking.
    """

    def __init__(self, id: int, pool: ParallelRunWorkerPool, driver: AbstractRunDriver, cpuset: CPUSet):
        """
        Creates an instance.

        :param id: id of this thread
        :param pool: parent run worked pool
        :param driver: use run driver instance
        :param cpuset: used CPUSet instance
        """
        threading.Thread.__init__(self)
        self.stop = False  # type: bool
        """ Stop the run loop? """
        self.id = id  # type: int
        """ Id of this thread """
        self.pool = pool  # type: ParallelRunWorkerPool
        """ Parent run worker pool """
        self.driver = driver  # type: AbstractRunDriver
        """ Used run driver instance """
        self.cpuset = cpuset  # type: CPUSet
        """ Used CPUSet instance """

    def run(self):
        """
        Start the run loop. It fetches run program blocks from the pool's submit queue, benchmarks them
        and stores the results in the pool's result queue.
        It stops if ``stop`` is true.
        """
        while True:
            try:
                #time.sleep(1)
                (block, block_id, runs) = self.pool.submit_queue.get(timeout=1)
            except Empty:
                if self.stop:
                    return
                else:
                    continue
            try:
                self.pool.result_queue.put((block, self._process_block(block, runs), block_id))
                logging.debug("Thread {set_id}: Benchmarked block {id}".format(set_id=self.id, id=block_id))
                block.is_enqueued = False
                self.pool.submit_queue.task_done()
            except BaseException:
                logging.error("Forced teardown of BenchmarkingThread")
                #self.teardown()
                raise

    def _process_block(self, block: RunProgramBlock, runs: int) -> BenchmarkingResultBlock:
        return self.driver.benchmark(block, runs, self.cpuset, self.id, timeout=self.pool.next_block_timeout())
