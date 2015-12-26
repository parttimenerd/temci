"""
This module consists of the abstract run worker pool class and several implementations.
"""
from ..utils.typecheck import *
from ..utils.settings import Settings
from .run_driver import RunProgramBlock, BenchmarkingResultBlock, AbstractRunDriver, RunDriverRegistry
from queue import Queue, Empty
from fn import _
from .cpuset import CPUSet
import logging, threading, subprocess, shlex, os, tempfile, yaml

class RunWorkerPool:
    """
    This run worker pool implements the sequential benchmarking of program blocks.
    """

    def __init__(self, run_driver_name: str = None):
        """
        Initializes a worker pool.
        :param run_driver_name: name of the used run driver or None if the one set in the Settings should be used
        """
        self.queue = Queue()
        self.result_queue = Queue()
        if run_driver_name is None:
            run_driver_name = RunDriverRegistry().get_used()
        self.run_driver = RunDriverRegistry().get_for_name(run_driver_name)
        self.cpuset = CPUSet(parallel=0) if Settings()["run/cpuset/active"] else None
        self.parallel_number = 1

    def submit(self, block: RunProgramBlock, id: int, runs: int):
        """
        Submits the passed block for "runs" times benchmarking.
        It also sets the blocks is_enqueued property to True.

        :param block: passed run program block
        :param id: id of the passed block
        :param runs: number of individual benchmarking runs
        """
        typecheck(block, RunProgramBlock)
        typecheck(runs, NaturalNumber())
        typecheck(id, Int(_ >= 0))
        block.is_enqueued = True
        self.result_queue.put((block, self.run_driver.benchmark(block, runs), id))
        block.is_enqueued = False

    def results(self):
        """
        An iterator over all available benchmarking results.
        The items of this iterator are tuples consisting of
        the benchmarked block, the benchmarking result and the
        blocks id.
        The benchmarking results are simple
        ..run_driver.BenchmarkingResultBlock objects.
        """
        while not self.result_queue.empty():
            yield self.result_queue.get()

    def teardown(self):
        """
        Tears down the inherited run driver.
        This should be called if all benchmarking with this pool is finished.
        """
        self.run_driver.teardown()
        if self.cpuset is not None:
            self.cpuset.teardown()


class ParallelRunWorkerPool:
    """
    This run worker pool implements the parallel benchmarking of program blocks.
    It uses a server-client-model to benchmark on different cpu cores.
    """

    def __init__(self, run_driver_name: str = None):
        """
        Initializes a worker pool.
        :param run_driver_name: name of the used run driver or None if the one set in the Settings should be used
        """
        self.submit_queue = Queue()
        self.intermediate_queue = Queue()
        self.result_queue = Queue()
        if run_driver_name is None:
            run_driver_name = RunDriverRegistry().get_used()
        if Settings()["run/cpuset/active"]:
            self.cpuset = CPUSet()
        else:
            raise ValueError("Only works with run/cpuset/active=True")
        self.parallel_number = self.cpuset.parallel_number
        logging.info("Using {} parallel processes to benchmark.".format(self.parallel_number))
        self.threads = []
        self.run_driver = RunDriverRegistry.get_for_name(run_driver_name)
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
        """
        Submits the passed block for "runs" times benchmarking.
        It also sets the blocks is_enqueued property to True.

        :param block: passed run program block
        :param id: id of the passed block
        :param runs: number of individual benchmarking runs
        """
        typecheck(block, RunProgramBlock)
        typecheck(runs, NaturalNumber())
        typecheck(id, Int(_ >= 0))
        block.is_enqueued = True
        self.submit_queue.put((block, id, runs))

    def results(self):
        """
        An iterator over all available benchmarking results.
        The items of this iterator are tuples consisting of
        the benchmarked block, the benchmarking result and the
        blocks id.
        The benchmarking results are simple
        ..run_driver.BenchmarkingResultBlock objects.
        """
        while not self.intermediate_queue.empty() or not self.submit_queue.empty() or not self.result_queue.empty():
            yield self.result_queue.get()
            #print("++intermediate size", self.intermediate_queue.qsize())
            #rint("++submit queue size", self.submit_queue.qsize())

    def teardown(self):
        """
        Tears down the inherited run driver.
        This should be called if all benchmarking with this pool is finished.
        """
        self.cpuset.teardown()
        self.run_driver.teardown()
        try:
            for thread in self.threads:
                thread.stop = True
                thread.teardown()
        except BaseException as err:
            pass


class BenchmarkingThread(threading.Thread):

    def __init__(self, id: int, pool: ParallelRunWorkerPool, driver: AbstractRunDriver, cpuset: CPUSet):
        threading.Thread.__init__(self)
        self.stop = False
        self.id = id
        self.pool = pool
        self.driver = driver
        self.cpuset = cpuset

    def run(self):
        while True:
            try:
                (block, block_id, runs) = self.pool.submit_queue.get(timeout=1)
            except Empty:
                if self.stop:
                    return
                else:
                    continue
            self.pool.intermediate_queue.put(block_id)
            try:
                self.pool.result_queue.put((block, self._process_block(block, runs), block_id))
                logging.info("Thread {set_id}: Benchmarked block {id}".format(set_id=self.id, id=block_id))
                block.is_enqueued = False
                self.pool.intermediate_queue.get()
            except BaseException:
                logging.error("Forced teardown of BenchmarkingThread")
                self.teardown()
                raise

    def _process_block(self, block: RunProgramBlock, runs: int) -> BenchmarkingResultBlock:
        return self.driver.benchmark(block, runs, self.cpuset, self.id)

    def teardown(self):
        pass