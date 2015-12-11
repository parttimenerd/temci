from ..utils.typecheck import *
from .run_worker_pool import RunWorkerPool, ParallelRunWorkerPool
from .run_driver import RunProgramBlock, BenchmarkingResultBlock, RunDriverRegistry, ExecRunDriver
import temci.run.run_driver_plugin
from ..tester.rundata import RunDataStatsHelper, RunData
from ..utils.settings import Settings
from ..tester.testers import TesterRegistry
from temci.tester.report_processor import ReportProcessor, ReporterRegistry
from temci.tester.report import ConsoleReporter
import time, logging, humanfriendly, yaml, sys, math, pytimeparse

class RunProcessor:
    """
    This class handles the coordination of the whole benchmarking process.
    It is configured by setting the settings of the stats and run domain.
    """

    def __init__(self, runs: list = None, append: bool = False, show_report: bool = True):
        """
        Important note: this constructor also setups the cpusets and plugins that can alter the system,
        e.g. confine most processes on only one core. Be sure to call the teardown() or the
        benchmark() method to make the system usable again.

        :param runs: list of dictionaries that represent run program blocks if None Settings()["run/in"] is used
        """
        if runs is None:
            typecheck(Settings()["run/in"], ValidYamlFileName())
            with open(Settings()["run/in"], "r") as f:
                runs = yaml.load(f)
        typecheck(runs, List(Dict({
            "attributes": Dict(all_keys=False, key_type=Str()),
            "run_config": Dict(all_keys=False)
        })))
        self.run_blocks = [RunProgramBlock.from_dict(id, run) for (id, run) in enumerate(runs)]
        self.append = Settings().default(append, "run/append")
        self.show_report = Settings().default(show_report, "run/show_report")
        if Settings()["run/cpuset/parallel"] == 0:
            self.pool = RunWorkerPool()
        else:
            self.pool = ParallelRunWorkerPool()
        if self.append:
            run_data = []
            typecheck(Settings()["run/out"], ValidYamlFileName())
            with open(Settings()["run/out"], "r") as f:
                run_data = yaml.load(f)
            self.stats_helper = RunDataStatsHelper.init_from_dicts(Settings()["stats"], run_data)
        else:
            tester = TesterRegistry.get_for_name(TesterRegistry.get_used(), Settings()["stats/uncertainty_range"])
            self.stats_helper = RunDataStatsHelper.init_from_dicts(Settings()["stats"], runs)
        self.run_block_size = Settings()["run/run_block_size"]
        self.discarded_blocks = Settings()["run/discarded_blocks"]
        self.pre_runs = self.discarded_blocks * self.run_block_size
        self.max_runs = max(Settings()["run/min_runs"], Settings()["run/max_runs"]) + self.pre_runs
        self.min_runs = min(Settings()["run/min_runs"], Settings()["run/max_runs"]) + self.pre_runs
        self.start_time = round(time.time())
        self.end_time = self.start_time + pytimeparse.parse(Settings()["run/max_time"])
        self.block_run_count = 0

    def _finished(self):
        return (len(self.stats_helper.get_program_ids_to_bench()) == 0 \
               or not self._can_run_next_block()) and self.min_runs <= self.block_run_count

    def _can_run_next_block(self):
        estimated_time = self.stats_helper.estimate_time_for_next_round(self.run_block_size,
                                                                        all=self.block_run_count < self.min_runs)
        to_bench_count = len(self.stats_helper.get_program_ids_to_bench())
        if round(time.time() + estimated_time) > self.end_time:
            logging.warning("Ran to long ({}) and is therefore now aborted. "
                            "{} program blocks should've been benchmarked again."
                            .format(humanfriendly.format_timespan(time.time() + estimated_time),
                                    to_bench_count))
            return False
        if self.block_run_count >= self.max_runs and self.block_run_count + self.run_block_size > self.min_runs:
            #print("benchmarked too often, block run count ", self.block_run_count, self.block_run_count + self.run_block_size > self.min_runs)
            logging.warning("Benchmarked program blocks to often and aborted therefore now.")
            return False
        return True

    def benchmark(self):
        try:
            last_round_time = time.time()
            while self.block_run_count <= self.pre_runs or not self._finished():
                last_round_span = time.time() - last_round_time
                last_round_time = time.time()
                if Settings()["log_level"] == "info" and self.block_run_count > self.pre_runs and \
                        ("exec" != RunDriverRegistry.get_used() or "start_stop" not in ExecRunDriver.get_used()):
                    last_round_actual_estimate = \
                        self.stats_helper.estimate_time_for_next_round(self.run_block_size,
                                                                       all=self.block_run_count < self.min_runs)
                    estimate = self.stats_helper.estimate_time(self.run_block_size, self.min_runs, self.max_runs)
                    estimate *= last_round_span / last_round_actual_estimate
                    estimate = (estimate / self.pool.parallel_number) - (time.time() - self.start_time)

                    estimate_str = humanfriendly.format_timespan(math.floor(estimate))
                    logging.info("[{nr:>3}] Estimated time to completion: {time:>20}"
                             .format(nr=self.block_run_count - self.pre_runs,
                                     time=estimate_str))
                self._benchmarking_block_run()
                #print(not self._finished(), len(self.stats_helper.get_program_ids_to_bench()), self._can_run_next_block())
            print()
        except BaseException as ex:
            logging.error("Forced teardown of RunProcessor")
            self.store_and_teardown()
            if isinstance(ex, KeyboardInterrupt) and Settings()["log_level"] == "info" and self.block_run_count > 0\
                    and self.show_report:
                self.print_report()
            raise
        self.store_and_teardown()
        if Settings()["log_level"] == "info" and self.show_report:
            self.print_report()

    def _benchmarking_block_run(self):
        try:
            self.block_run_count += self.run_block_size
            to_bench = []
            if self.block_run_count < self.min_runs:
                to_bench = enumerate(self.run_blocks)
            else:
                to_bench = [(i, self.run_blocks[i]) for i in self.stats_helper.get_program_ids_to_bench()]
            for (id, run_block) in to_bench:
                self.pool.submit(run_block, id, self.run_block_size)
            for (block, result, id) in self.pool.results():
                if self.block_run_count > self.pre_runs:
                    self.stats_helper.add_data_block(id, result.data)

        except BaseException:
            self.store_and_teardown()
            logging.error("Forced teardown of RunProcessor")
            raise
        self.store()

    def teardown(self):
        self.pool.teardown()

    def store_and_teardown(self):
        self.teardown()
        self.store()

    def store(self):
        with open(Settings()["run/out"], "w") as f:
            f.write(yaml.dump(self.stats_helper.to_dict()["runs"]))

    def print_report(self) -> str:
        ReporterRegistry.get_for_name("console", self.stats_helper).report()