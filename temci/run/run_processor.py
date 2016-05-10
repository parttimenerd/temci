import copy
import random

import click

from temci.utils.util import join_strs, in_standalone_mode

from temci.utils.mail import send_mail
from temci.utils.typecheck import *
from temci.run.run_worker_pool import RunWorkerPool, ParallelRunWorkerPool, AbstractRunWorkerPool
from temci.run.run_driver import RunProgramBlock, BenchmarkingResultBlock, RunDriverRegistry, ExecRunDriver, \
    is_perf_available
import temci.run.run_driver_plugin
from temci.report.rundata import RunDataStatsHelper, RunData
from temci.utils.settings import Settings
from temci.report.report_processor import ReporterRegistry
import time, logging, humanfriendly, sys, math, pytimeparse, os
import typing as t
try:
    import yaml
except ImportError:
    import pureyaml as yaml
#from temci.run.remote import RemoteRunWorkerPool

class RunProcessor:
    """
    This class handles the coordination of the whole benchmarking process.
    It is configured by setting the settings of the stats and run domain.

    Important note: the constructor also setups the cpu sets and plugins that can alter the system,
    e.g. confine most processes on only one core. Be sure to call the ``teardown()`` or the
    ``benchmark()`` method to make the system usable again.
    """

    def __init__(self, runs: t.List[dict] = None, append: bool = None, show_report: bool = None):
        """
        Creates an instance and setup everything.

        :param runs: list of dictionaries that represent run program blocks if None Settings()["run/in"] is used
        :param append: append to the old benchmarks if there are any in the result file?
        :param show_report: show a short report after finishing the benchmarking?
        """
        if runs is None:
            typecheck(Settings()["run/in"], ValidYamlFileName())
            with open(Settings()["run/in"], "r") as f:
                runs = yaml.load(f)
        typecheck(runs, List(Dict({
            "attributes": Dict(all_keys=False, key_type=Str()),
            "run_config": Dict(all_keys=False)
        })))
        self.runs = runs  # type: t.List[dict]
        """ List of dictionaries that represent run program blocks """
        self.run_blocks = []  # type: t.List[RunProgramBlock]
        """ Run program blocks for each dictionary in ``runs```"""
        for (id, run) in enumerate(runs):
            self.run_blocks.append(RunProgramBlock.from_dict(id, copy.deepcopy(run)))
        self.append = Settings().default(append, "run/append")  # type: bool
        """ Append to the old benchmarks if there are any in the result file? """
        self.show_report = Settings().default(show_report, "run/show_report")  # type: bool
        """  Show a short report after finishing the benchmarking? """
        self.stats_helper = None  # type: RunDataStatsHelper
        """ Used stats helper to help with measurements """
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
        #if Settings()["run/remote"]:
        #    self.pool = RemoteRunWorkerPool(Settings()["run/remote"], Settings()["run/remote_port"])
            if os.path.exists(Settings()["run/out"]):
                os.remove(Settings()["run/out"])
        self.pool = None  # type: AbstractRunWorkerPool
        """ Used run worker pool that abstracts the benchmarking """
        if Settings()["run/cpuset/parallel"] == 0:
            self.pool = RunWorkerPool()
        else:
            self.pool = ParallelRunWorkerPool()
        self.run_block_size = Settings()["run/run_block_size"]  # type: int
        """ Number of benchmarking runs that are done together """
        self.discarded_runs = Settings()["run/discarded_runs"]  # type: int
        """ First n runs that are discarded """
        self.max_runs = Settings()["run/max_runs"]  # type: int
        """ Maximum number of benchmarking runs """
        self.min_runs = Settings()["run/min_runs"]  # type: int
        """ Minimum number of benchmarking runs """
        if self.min_runs > self.max_runs:
            logging.warning("min_runs ({}) is bigger than max_runs ({}), therefore they are swapped."
                            .format(self.min_runs, self.max_runs))
            tmp = self.min_runs
            self.min_runs = self.max_runs
            self.max_runs = tmp

        self.shuffle = Settings()["run/shuffle"]  # type: bool
        """ Randomize the order in which the program blocks are benchmarked. """
        self.fixed_runs = Settings()["run/runs"] != -1  # type: bool
        """ Do a fixed number of benchmarking runs? """
        if self.fixed_runs:
            self.min_runs = self.max_runs = self.min_runs = Settings()["run/runs"]
        self.start_time = round(time.time())  # type: float
        """ Unix time stamp of the start of the benchmarking """
        self.end_time = None  # type: float
        """ Unix time stamp of the point in time that the benchmarking can at most reach """
        try:
            self.end_time = self.start_time + pytimeparse.parse(Settings()["run/max_time"])
        except:
            self.teardown()
            raise
        self.store_often = Settings()["run/store_often"]  # type: bool
        """ Store the result file after each set of blocks is benchmarked """
        self.block_run_count = 0  # type: int
        """ Number of benchmarked blocks """
        self.erroneous_run_blocks = []  # type: t.List[t.Tuple[int, BenchmarkingResultBlock]]
        """ List of all failing run blocks (id and results till failing) """

    def _finished(self) -> bool:
        if self.fixed_runs:
            return self.block_run_count >= self.max_runs
        return (len(self.stats_helper.get_program_ids_to_bench()) == 0 \
               or not self._can_run_next_block()) and self.min_runs <= self.block_run_count

    def _can_run_next_block(self) -> bool:
        if not in_standalone_mode:
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
        """
        Benchmark and teardown.
        """
        try:

            show_progress = Settings().has_log_level("info") and \
                            ("exec" != RunDriverRegistry.get_used() or "start_stop" not in ExecRunDriver.get_used())
            showed_progress_before = False
            discard_label = "Make the {} discarded benchmarks".format(self.discarded_runs)
            if self.fixed_runs:
                label = "Benchmark {} times".format(self.max_runs)
            else:
                label = "Benchmark {} to {} times".format(self.min_runs, self.max_runs)
            start_label = discard_label if self.discarded_runs > 0 else label
            label_format = "{:32s}"
            if show_progress:
                with click.progressbar(range(0, self.max_runs + self.discarded_runs),
                                       label=label_format.format(start_label)) as runs:
                    for run in runs:
                        if run < self.discarded_runs:
                            self._benchmarking_block_run(block_size=1, discard=True)
                        else:
                            if self._finished():
                                break
                            self._benchmarking_block_run()
                        if run == self.discarded_runs - 1:
                            runs.label = label_format.format(label)
            else:
                time_per_run = self._make_discarded_runs()
                last_round_time = time.time()
                if time_per_run != None:
                    last_round_time -= time_per_run * self.run_block_size
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
            if not bench_all and self.block_run_count < self.max_runs and not in_standalone_mode:
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
        """ Teardown everything (make the system useable again) """
        self.pool.teardown()

    def store_and_teardown(self):
        """
        Teardown everything, store the result file, print a short report and send an email
        if configured to do so.
        """
        if Settings().has_log_level("info") and self.show_report:
            self.print_report()
        self.teardown()
        self.store()
        if len(self.stats_helper.valid_runs()) > 0 \
                and all(x.benchmarks() > 0 for x in self.stats_helper.valid_runs()):
            report = ""
            if not in_standalone_mode:
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
        """ Store the result file """
        try:
            self.stats_helper.add_property_descriptions(self.pool.run_driver.get_property_descriptions())
        except (IOError, OSError) as ex:
            logging.error(ex)
        if len(self.stats_helper.valid_runs()) > 0 \
            and all(x.benchmarks() > 0 for x in self.stats_helper.valid_runs()):
            with open(Settings()["run/out"], "w") as f:
                f.write(yaml.dump(self.stats_helper.serialize()))

    def store_erroneous(self):
        """ Store the failing program blocks in a file ending with ``.erroneous.yaml``. """
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
        if in_standalone_mode:
            return
        """ Print a short report if possible. """
        try:
            if len(self.stats_helper.valid_runs()) > 0 and \
                    all(x.benchmarks() > 0 for x in self.stats_helper.valid_runs()):
                ReporterRegistry.get_for_name("console", self.stats_helper).report(with_tester_results=False)
        except:
            pass