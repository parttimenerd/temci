"""
Contains the RunData object for benchmarking data of specific program block
and the RunDataStatsHelper that provides helper methods for working with
these objects.
"""

from .testers import Tester, TesterRegistry
from ..utils.typecheck import *
from ..utils.settings import Settings
import scipy


class RunData(object):
    """
    A set of benchmarking data for a specific program block.
    """

    def __init__(self, properties: list, data: dict = None, attributes: dict = None):
        """
        Initializes a new run data object with a list of measured properties,
        an optional dictionary mapping each property to a list of actual values and
        a dictionary of optional attributes that describe its program block.
        :raises ValueError if something is wrong with data or the properties don't include 'ov-time'
        """
        typecheck(properties, List(T(str)))
        typecheck(attributes, Exact(None) | Dict(key_type=Str(), all_keys=False))
        self.properties = properties
        if 'ov-time' not in properties and properties != "all":
            raise ValueError("Properties don't include the overall time ('ov-time')")
        self.data = {}
        for prop in self.properties:
            self.data[prop] = []
        if data is not None:
            self.add_data_block(data)
        self.attributes = {} if attributes is None else attributes

    def add_data_block(self, data_block: dict):
        """
        Adds a block of data. The passed dictionary maps each of the run datas properties to list of
        actual values (from each benchmarking run). Additional values are added too.
        :raises ValueError if not all properties have values associated or if they are not of equal length
        """
        typecheck(data_block, Dict(key_type=Str(), value_type= List(Int() | Float()), all_keys=False))
        if any(prop not in data_block for prop in self.properties):
            raise ValueError("Not all properties have associated values in the passed dictionary.")
        values = list(data_block.values())
        if any(len(values[0]) != len(value) for value in values):
            raise ValueError("Not all properties have the same amount of actual values.")
        for prop in data_block:
            if prop not in self.data:
                self.data[prop] = []
            self.data[prop].extend(data_block[prop])

    def __len__(self) -> int:
        return len(list(self.data.values()))

    def __getitem__(self, property: str):
        """
        Returns the benchmarking values associated with the passed property.
        """
        return self.data[property]

    def to_dict(self) -> dict:
        """
        Returns a dictionary that represents this run data object.
        """
        return {
            "attributes": self.attributes,
            "data": self.data
        }

    def __str__(self):
        return repr(self.attributes)

    def description(self):
        if "description" in self.attributes:
            return self.attributes["description"]
        else:
            return repr(self.attributes)


class RunDataStatsHelper(object):
    """
    This class helps to simplify the work with a set of run data observations.
    """

    def __init__(self, stats: dict, properties: list, tester: Tester, runs: list):
        """
        Don't use the constructor use init_from_dicts if possible.
        :param stats: to simplify the conversion of this object into a dictionary structure
        :param properties: list of (property name, property description) or just a list of names tuples
        :param tester:
        :param runs: list of run data objects
        """
        self.stats = stats
        if isinstance(properties, List(Str())):
            properties = [(prop, prop) for prop in properties]
        self.properties = properties
        self.tester = tester
        typecheck(runs, List(T(RunData)))
        self.runs = runs

    @classmethod
    def init_from_dicts(cls, stats: dict, runs: list = []):
        """
        Expected structure of the stats settings and the runs parameter::

            "stats": {
                "tester": ...,
                "properties": ["prop1", ...],
                # or
                "properties": [("prop1", "description of prop1"), ...],
                "uncertainty_range": (0.1, 0.3)
            }

            "runs": [
                {"attributes": {"attr1": ..., ...},
                 "data": {"ov-time": [...], ...}},
                 ...
            ]


        :param stats: stats settings part
        :param runs: list of dictionaries representing the benchmarking runs for each program block
        :rtype RunDataStatsHelper
        :raises ValueError if the stats of the runs parameter have not the correct structure
        """
        res = verbose_isinstance(stats, Settings.type_scheme["stats"], value_name="stats parameter")
        if not res:
            raise ValueError(res)
        typecheck(runs, List(Dict({
                    "data": Dict(key_type=Str(), value_type=List(Int()|Float()), all_keys=False) | NonExistent(),
                    "attributes": Dict(key_type=Str(), all_keys=False)
                }, all_keys=False)),
                value_name="runs parameter")
        properties = stats["properties"]
        props_w_descr = []
        props_wo_descr = []
        if len(properties) is 0:
            raise ValueError("Properties must contain at least 'ov-time'")
        if isinstance(properties, List(Tuple(Str(), Str()))):
            props_w_descr = properties
            props_wo_descr = [name for (name, _) in properties]
        elif isinstance(properties, List(Str())):
            props_wo_descr = properties
            props_w_descr = [(name, name) for name in properties]
        tester = TesterRegistry().get_for_name(stats["tester"], stats["uncertainty_range"])
        run_datas = []
        for run in runs:
            if "data" not in run:
                run["data"] = {}
                for prop in props_wo_descr:
                    run["data"][prop] = []
            run_datas.append(RunData(props_wo_descr, run["data"], run["attributes"]))
        return RunDataStatsHelper(stats, props_w_descr, tester, run_datas)

    def to_dict(self) -> dict:
        """
        Returns a dictionary that includes the resulting stats and runs dictionaries.
        """
        return {
            "stats": self.stats,
            "runs": [run.to_dict() for run in self.runs]
        }

    def _is_uncertain(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_uncertain(data1[property], data2[property])

    def _is_equal(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_equal(data1[property], data2[property])

    def _is_unequal(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_unequal(data1[property], data2[property])

    def _speed_up(self, property: str, data1: RunData, data2: RunData):
        """
        Calculates the speed up from the second to the first
        (e.g. the first is RESULT * 100 % faster than the second).
        """
        return (scipy.mean(data2[property]) - scipy.mean(data1[property])) \
               / scipy.mean(data1[property])

    def _estimate_time_for_run_datas(self, run_bin_size: int, data1: RunData, data2: RunData,
                                     min_runs: int, max_runs: int) -> float:
        if min(len(data1), len(data2)) == 0:
            return max_runs
        needed_runs = []
        for (prop, descr) in self.properties:
            estimate = self.tester.estimate_needed_runs(data1[prop], data2[prop],
                                                                run_bin_size, min_runs, max_runs)
            needed_runs.append(estimate)
        #print("needed_runs", needed_runs)
        avg_time = max(scipy.mean(data1["ov-time"]), scipy.mean(data2["ov-time"]))
        return max(needed_runs) * avg_time

    def get_program_ids_to_bench(self) -> list:
        """
        Returns the ids (the first gets id 0, …) of the program block / run data object that
        should be benchmarked again.
        """
        to_bench = set()
        for (i, run) in enumerate(self.runs):
            if i in to_bench:
                continue
            for j in range(i):
                if j in to_bench:
                    continue
                run2 = self.runs[j]
                if any(self._is_uncertain(prop, run, run2) for (prop, descr) in self.properties):
                    to_bench.add(i)
                    to_bench.add(j)
        return list(to_bench)

    def estimate_time(self, run_bin_size: int, min_runs: int, max_runs: int) -> float:
        """
        Roughly erstimates the time needed to finish benchmarking all program blocks.
        It doesn't take any parallelism into account. Therefore divide the number by the used parallel processes.
        :param run_bin_size: times a program block is benchmarked in a single block of time
        :param min_runs: minimum number of allowed runs
        :param max_runs: maximum number of allowed runs
        :return estimated time in seconds or float("inf") if no proper estimation could be made
        """
        to_bench = self.get_program_ids_to_bench()
        max_times = [0 for i in to_bench]
        for i in to_bench:
            run = self.runs[i]
            for j in to_bench:
                max_time = self._estimate_time_for_run_datas(run_bin_size, run, self.runs[j],
                                                             min_runs, max_runs)
                max_times[i] = max(max_times[i], max_time)
                max_times[j] = max(max_times[j], max_time)
                if max_time == float("inf"):
                    return float("inf")
        return sum(max_times)

    def estimate_time_for_next_round(self, run_bin_size: int, all: bool) -> float:
        """
        Roughly estimates the time needed for the next benchmarking round.
        :param run_bin_size: times a program block is benchmarked in a single block of time and the size of a round
        :param all: expect all program block to be benchmarked
        :return estimated time in seconds
        """
        summed = 0
        to_bench = range(0, len(self.runs)) if all else self.get_program_ids_to_bench()
        for i in to_bench:
            summed += scipy.mean(self.runs[i]["ov-time"]) * run_bin_size
        return summed

    def add_run_data(self, data: list = None, attributes: dict = None) -> int:
        """
        Adds a new run data (corresponding to a program block) and returns its id.
        :param data: benchmarking data of the new run data object
        :param attributes: attributes of the new run data object
        :return: id of the run data object (and its corresponding program block)
        """
        self.runs.append(RunData([name for (name, _) in self.properties], data, attributes))
        return len(self.runs) - 1

    def add_data_block(self, program_id: int, data_block: dict):
        """
        Add block of data for the program block with the given id.
        :param program_id: id of the program.
        :param data_block: list of data from several benchmarking runs of the program block
        :raises ValueError if the program block with the given id doesn't exist
        """
        assert program_id >= 0
        if program_id >= len(self.runs):
            raise ValueError("Program block with id {} doesn't exist".format(program_id))
        self.runs[program_id].add_data_block(data_block)

    def get_evaluation(self, with_equal: bool, with_unequal: bool, with_uncertain: bool) -> dict:
        """

        Structure of the returned list items::

            - data: # set of two run data objects
              properties: # information for each property that is equal, ...
                  -prop:
                      - equal: True/False
                        uncertain: True/False
                        p_val: probability of the null hypothesis
                        speed_up: speed up from the first to the second
                        description: description of the property

        :param with_equal: with tuple with at least one "equal" property
        :param with_unequal: ... unequal property
        :param with_uncertain: include also uncertain properties
        :return: list of tuples for which at least one property matches the criteria
        """
        # todo rewrite
        arr = []
        for i in range(0, len(self.runs) - 1):
            for j in range(i + 1, len(self.runs)):
                data = (self.runs[i], self.runs[j])
                props = {}
                for (prop, descr) in self.properties:
                    map = {"p_val": self.tester.test(data[0][prop], data[1][prop]),
                           "speed_up": self._speed_up(prop, *data),
                           "description": descr,
                           "equal": self._is_equal(prop, *data),
                           "unequal": self._is_unequal(prop, *data),
                           "uncertain": self._is_uncertain(prop, *data)}
                    if map["unequal"] == with_unequal and map["equal"] == with_equal \
                            and map["uncertain"] == with_uncertain:
                        props[prop] = map
                if len(props) > 0:
                    arr.append({
                        "data": data,
                        "properties": props
                    })
        return arr
