import copy
import random

from pyaml import pprint

from temci.utils.util import join_strs

from temci.utils.mail import send_mail
from temci.utils.typecheck import *
from temci.run.run_worker_pool import RunWorkerPool, ParallelRunWorkerPool
from temci.run.run_driver import RunProgramBlock, BenchmarkingResultBlock, RunDriverRegistry, ExecRunDriver, \
    is_perf_available
import temci.run.run_driver_plugin
from temci.tester.rundata import RunDataStatsHelper, RunData
from temci.utils.settings import Settings
from temci.tester.report_processor import ReporterRegistry
import time, logging, humanfriendly, yaml, sys, math, pytimeparse, os
import typing as t

class RunProcessor:
    """
    This class handles the coordination of the whole benchmarking process.
    It is configured by setting the settings of the stats and run domain.
    """

    def __init__(self, runs: list = None, append: bool = None, show_report: bool = None):
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
        self.runs = runs
        self.run_blocks = []
        for (id, run) in enumerate(runs):
            self.run_blocks.append(RunProgramBlock.from_dict(id, copy.deepcopy(run)))
        self.append = Settings().default(append, "run/append")
        self.show_report = Settings().default(show_report, "run/show_report")
        self.stats_helper = None # type: RunDataStatsHelper
        typecheck(Settings()["run/out"], FileName())
        if self.append:
            run_data = []
            try:
                if os.path.exists(Settings()["run/out"]):
                    with open(Settings()["run/out"], "r") as f:
                        run_data = yaml.load(f)
                self.stats_helper = RunDataStatsHelper.init_from_dicts(run_data, external=True)
                for run in runs:
                    self.stats_helper.runs.append(RunData(attributes=run["attributes"]))
            except:
                self.teardown()
                raise
        else:
            self.stats_helper = RunDataStatsHelper.init_from_dicts(copy.deepcopy(runs))
        if Settings()["run/cpuset/parallel"] == 0:
            self.pool = RunWorkerPool()
        else:
            self.pool = ParallelRunWorkerPool()
        self.run_block_size = Settings()["run/run_block_size"]
        self.discarded_blocks = Settings()["run/discarded_blocks"]
        self.pre_runs = self.discarded_blocks * self.run_block_size
        self.max_runs = max(Settings()["run/max_runs"], Settings()["run/min_runs"]) + self.pre_runs
        self.min_runs = Settings()["run/min_runs"] + self.pre_runs
        self.shuffle = Settings()["run/shuffle"]
        if Settings()["run/runs"] != -1:
            self.min_runs = self.max_runs = self.min_runs = Settings()["run/runs"] + self.pre_runs
        self.start_time = round(time.time())
        try:
            self.end_time = self.start_time + pytimeparse.parse(Settings()["run/max_time"], Settings()["run/discarded_blocks"])
        except:
            self.teardown()
            raise
        self.block_run_count = 0
        self.erroneous_run_blocks = [] # type: t.List[t.Tuple[int, BenchmarkingResultBlock]]

    def _finished(self):
        return (len(self.stats_helper.get_program_ids_to_bench()) == 0 \
               or not self._can_run_next_block()) and self.min_runs < self.block_run_count

    def _can_run_next_block(self):
        estimated_time = self.stats_helper.estimate_time_for_next_round(self.run_block_size,
                                                                        all=self.block_run_count < self.min_runs)
        to_bench_count = len(self.stats_helper.get_program_ids_to_bench())
        if round(time.time() + estimated_time) > self.end_time:
            logging.warning("Ran to long ({}) and is therefore now aborted. "
                            "{} program blocks should've been benchmarked again."
                            .format(humanfriendly.format_timespan(time.time() + estimated_time - self.start_time),
                                    to_bench_count))
            return False
        if self.block_run_count >= self.max_runs and self.block_run_count > self.min_runs:
            #print("benchmarked too often, block run count ", self.block_run_count, self.block_run_count + self.run_block_size > self.min_runs)
            logging.warning("Benchmarked program blocks to often and aborted therefore now.")
            return False
        return True

    def benchmark(self):
        try:
            last_round_time = time.time()
            while self.block_run_count <= self.pre_runs or not self._finished():
                if len(self.stats_helper.valid_runs()) == 0:
                    logging.warning("Finished benchmarking as there a now valid program block to benchmark")
                    break
                last_round_span = time.time() - last_round_time
                last_round_time = time.time()
                try:
                    if Settings().has_log_level("info") and self.block_run_count > self.pre_runs and \
                            ("exec" != RunDriverRegistry.get_used() or "start_stop" not in ExecRunDriver.get_used()):
                        # last_round_actual_estimate = \
                        #    self.stats_helper.estimate_time_for_next_round(self.run_block_size,
                        #                                                   all=self.block_run_count < self.min_runs)
                        # estimate = self.stats_helper.estimate_time(self.run_block_size, self.min_runs, self.max_runs)
                        # if last_round_actual_estimate != 0:
                        #    estimate *= last_round_span / last_round_actual_estimate
                        #    estimate = (estimate / self.pool.parallel_number) - (time.time() - self.start_time)
                        # else:
                        #    estimate = 0
                        nr = self.block_run_count - self.pre_runs
                        estimate, title = "", ""
                        if nr <= self.min_runs:
                            estimate = last_round_span * (self.min_runs - self.block_run_count)
                            title = "Estimated time till minimum runs completed"
                        else:
                            estimate = last_round_span * (self.max_runs - self.block_run_count)
                            title = "Estimated time till maximum runs completed"
                        estimate = min(estimate, self.end_time - time.time())
                        estimate_str = humanfriendly.format_timespan(math.floor(estimate))
                        logging.info("[Finished {nr:>3}] {title}: {time:>20}"
                                     .format(nr=nr, title=title, time=estimate_str))
                except:
                    logging.warning("Error in estimating and printing the needed time.")
                self._benchmarking_block_run()
            print()
        except BaseException as ex:
            logging.error("Forced teardown of RunProcessor")
            self.store_and_teardown()
            if isinstance(ex, KeyboardInterrupt) and Settings()["log_level"] == "info" and self.block_run_count > 0\
                    and self.show_report:
                self.print_report()
            raise
        self.store_and_teardown()

    def _benchmarking_block_run(self):
        try:
            self.block_run_count += self.run_block_size
            to_bench = []
            if self.block_run_count <= self.min_runs:
                to_bench = list(enumerate(self.run_blocks))
            else:
                to_bench = [(i, self.run_blocks[i]) for i in self.stats_helper.get_program_ids_to_bench()]
            to_bench = [(i, b) for (i, b) in to_bench if self.stats_helper.runs[i] is not None]
            if self.shuffle:
                random.shuffle(to_bench)
            if len(to_bench) == 0 or self.block_run_count > self.max_runs:
                return
            for (id, run_block) in to_bench:
                self.pool.submit(run_block, id, self.run_block_size)
            for (block, result, id) in self.pool.results(len(to_bench)):
                if result.error:
                    self.erroneous_run_blocks.append((id, result))
                    self.stats_helper.disable_run_data(id)
                    logging.error("Program block no. {} failed: {}".format(id, result.error))
                    self.store_erroneous()
                elif self.block_run_count > self.pre_runs:
                    self.stats_helper.add_data_block(id, result.data)
        except BaseException:
            self.store_and_teardown()
            logging.error("Forced teardown of RunProcessor")
            raise
        self.store()

    def teardown(self):
        self.pool.teardown()

    def store_and_teardown(self):
        if Settings().has_log_level("info") and self.show_report:
            self.print_report()
        self.teardown()
        self.store()
        if len(self.stats_helper.valid_runs()) > 0 \
                and all(x.benchmarks() > 0 for x in self.stats_helper.valid_runs()):
            report = ReporterRegistry.get_for_name("console", self.stats_helper)\
                .report(with_tester_results=False, to_string = True)
            self.stats_helper.valid_runs()[0].description()
            subject = "Finished " + join_strs([repr(run.description()) for run in self.stats_helper.valid_runs()])
            send_mail(Settings()["run/send_mail"], subject, report, [Settings()["run/out"]])
        if len(self.erroneous_run_blocks) > 0:
            descrs = []
            msgs = []
            for (i, result) in self.erroneous_run_blocks:
                descr = repr(RunData(attributes=self.runs[i]["attributes"]).description())
                descrs.append(descr)
                msg = descr + ":\n\t" + "\n\t".join(str(result.error).split("\n"))
                msgs.append(msg)
            subject = "Errors while benchmarking " + join_strs(descrs)
            send_mail(Settings()["run/send_mail"], subject, "\n\n".join(msgs), [Settings()["run/in"]  + ".erroneous.yaml"])

    def store(self):
        with open(Settings()["run/out"], "w") as f:
            f.write(yaml.dump(self.stats_helper.serialize()))

    def store_erroneous(self):
        if len(self.erroneous_run_blocks) == 0:
            return
        file_name = Settings()["run/in"] + ".erroneous.yaml"
        try:
            blocks = [self.runs[x[0]] for x in self.erroneous_run_blocks]
            with open(file_name, "w") as f:
                f.write(yaml.dump(blocks))
        except IOError as err:
            logging.error("Can't write erroneous program blocks to " + file_name)

    def print_report(self) -> str:
        try:
            if len(self.stats_helper.valid_runs()) > 0 and \
                    all(x.benchmarks() > 0 for x in self.stats_helper.valid_runs()):
                ReporterRegistry.get_for_name("console", self.stats_helper).report(with_tester_results=False)
        except:
            pass