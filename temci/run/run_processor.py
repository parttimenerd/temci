import copy
import random

import click
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
from temci.run.remote import RemoteRunWorkerPool

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
        if Settings()["run/remote"]:
            self.pool = RemoteRunWorkerPool(Settings()["run/remote"], Settings()["run/remote_port"])
        elif Settings()["run/cpuset/parallel"] == 0:
            self.pool = RunWorkerPool()
        else:
            self.pool = ParallelRunWorkerPool()
        self.run_block_size = Settings()["run/run_block_size"]
        self.discarded_runs = Settings()["run/discarded_runs"]

        self.max_runs = Settings()["run/max_runs"]
        self.min_runs = Settings()["run/min_runs"]
        if self.min_runs > self.max_runs:
            logging.warning("min_runs ({}) is bigger than max_runs ({}), therefore they are swapped."
                            .format(self.min_runs, self.max_runs))
            tmp = self.min_runs
            self.min_runs = self.max_runs
            self.max_runs = tmp

        self.shuffle = Settings()["run/shuffle"]
        self.fixed_runs = Settings()["run/runs"] != -1
        if self.fixed_runs:
            self.min_runs = self.max_runs = self.min_runs = Settings()["run/runs"]
        self.start_time = round(time.time())
        try:
            self.end_time = self.start_time + pytimeparse.parse(Settings()["run/max_time"])
        except:
            self.teardown()
            raise
        self.store_often = Settings()["run/store_often"]
        self.block_run_count = 0
        self.erroneous_run_blocks = [] # type: t.List[t.Tuple[int, BenchmarkingResultBlock]]

    def _finished(self):
        if self.fixed_runs:
            return self.block_run_count >= self.max_runs
        return (len(self.stats_helper.get_program_ids_to_bench()) == 0 \
               or not self._can_run_next_block()) and self.min_runs <= self.block_run_count

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
        if self.block_run_count >= self.max_runs and self.block_run_count >= self.min_runs:
            #print("benchmarked too often, block run count ", self.block_run_count, self.block_run_count + self.run_block_size > self.min_runs)
            logging.warning("Benchmarked program blocks to often and aborted therefore now.")
            return False
        return True

    def benchmark(self):
        try:
            time_per_run = self._make_discarded_runs()
            last_round_time = time.time()
            if time_per_run != None:
                last_round_time -= time_per_run * self.run_block_size
            show_progress = Settings().has_log_level("info") and \
                            ("exec" != RunDriverRegistry.get_used() or "start_stop" not in ExecRunDriver.get_used())
            showed_progress_before = False
            if show_progress:
                if self.fixed_runs:
                    label = "Benchmark {} times".format(self.max_runs)
                else:
                    label = "Benchmark between {} and {} times".format(self.min_runs, self.max_runs)
                with click.progressbar(range(0, self.max_runs), label=label) as runs:
                    for run in runs:
                        if self._finished():
                            break
                        self._benchmarking_block_run()
            else:
                while not self._finished():
                    self._benchmarking_block_run()
        except BaseException as ex:
            logging.error("Forced teardown of RunProcessor")
            self.store_and_teardown()
            if isinstance(ex, KeyboardInterrupt) and Settings()["log_level"] == "info" and self.block_run_count > 0\
                    and self.show_report:
                self.print_report()
            raise
        self.store_and_teardown()

    def _benchmarking_block_run(self, block_size: int = None, discard: bool = False, bench_all: bool = None):
        block_size = block_size or self.run_block_size
        if bench_all is None:
            bench_all = self.block_run_count < self.min_runs
        try:
            to_bench = list(enumerate(self.run_blocks))
            if not bench_all and self.block_run_count < self.max_runs:
                to_bench = [(i, self.run_blocks[i]) for i in self.stats_helper.get_program_ids_to_bench()]
            to_bench = [(i, b) for (i, b) in to_bench if self.stats_helper.runs[i] is not None]
            if self.shuffle:
                random.shuffle(to_bench)
            if len(to_bench) == 0:
                return
            for (id, run_block) in to_bench:
                self.pool.submit(run_block, id, self.run_block_size)
            for (block, result, id) in self.pool.results(len(to_bench)):
                if result.error:
                    self.erroneous_run_blocks.append((id, result))
                    self.stats_helper.disable_run_data(id)
                    logging.error("Program block no. {} failed: {}".format(id, result.error))
                    self.store_erroneous()
                elif not discard:
                    self.stats_helper.add_data_block(id, result.data)
            if not discard:
                self.block_run_count += block_size
        except BaseException as ex:
            self.store_and_teardown()
            logging.error("Forced teardown of RunProcessor")
            raise
        if not discard and self.store_often:
            self.store()

    def _make_discarded_runs(self) -> t.Optional[int]:
        if self.discarded_runs == 0:
            return None
        start_time = time.time()
        self._benchmarking_block_run(block_size=self.discarded_runs, discard=True, bench_all=True)
        return (time.time() - start_time) / self.discarded_runs

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