"""
Contains the RunData object for benchmarking data of specific program block
and the RunDataStatsHelper that provides helper methods for working with
these objects.
"""

from .testers import Tester, TesterRegistry
from ..utils.typecheck import *
from ..utils.settings import Settings

#todo write tests!!!

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
            self.data[prop] += data_block[prop]

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

class RunDataStatsHelper(object):
    """
    This class helps to simplify the work with a set of run data observations.
    """

    def __init__(self, stats: dict, properties: list, tester: Tester, runs: list):
        """
        Don't use the constructor use init_from_dicts if possible.
        :param stats: to simplify the conversion of this object into a dictionary structure
        :param properties: list of (property name, property description) tuples
        :param tester:
        :param runs: list of run data objects
        """
        self.stats = stats
        self.properties = properties
        self.tester = tester
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
        res = verbose_isinstance(runs, List(Dict({
                    "data": Dict(key_type=Str(), value_type=List(Int()|Float()), all_keys=False),
                    "attributes": Dict(key_type=Str(), all_keys=False)
                })),
                value_name="runs parameter")
        if not res:
            raise ValueError(res)
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
        run_datas = [RunData(props_wo_descr, run["data"], run["attributes"]) for run in runs]
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

    def _estimate_time_for_run_datas(self, run_bin_size: int, data1: RunData, data2: RunData) -> float:
        needed_runs = []
        for (prop, descr) in self.properties:
            needed_runs.append(self.tester.estimate_needed_runs(data1[prop], data2[prop], run_bin_size))
        avg_time = max(sum(i for i in data1["ov-time"]) / len(data1), sum(i for i in data2["ov-time"]) / len(data2))
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
            for (j, run2) in enumerate(self.runs):
                if any(self._is_uncertain(prop, run, run2) for (prop, descr) in self.properties):
                    to_bench.add(i)
                    to_bench.add(j)
        return list(to_bench)

    def estimate_time(self, run_bin_size: int = 10) -> float:
        """
        Roughly erstimates the time needed to finish benchmarking all program blocks.
        It doesn't take any parallelism into account. Therefore divide the number by the used parallel processes.
        :param run_bin_size: times a program block is benchmarked in a single block of time
        :return estimated time in seconds
        """
        to_bench = self.get_program_ids_to_bench()
        max_times = [0 for i in to_bench]
        for i in to_bench:
            run = self.runs[i]
            for j in to_bench:
                max_time = self._estimate_time_for_run_datas(run_bin_size, run, self.runs[j])
                max_times[i] = max(max_times[i], max_time)
                max_times[j] = max(max_times[j], max_time)
        return sum(max_times)

    def estimate_time_for_next_round(self, run_bin_size: int = 10) -> float:
        """
        Roughly estimates the time needed for the next benchmarking round.
        :param run_bin_size: times a program block is benchmarked in a single block of time and the size of a round
        :return estimated time in seconds
        """
        summed = 0
        for i in self.get_program_ids_to_bench():
            summed += sum(self.runs[i]["ov-time"]) / len(self.runs[i])
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
                - prop:
                  equal: True/False
                  uncertain: True/False
                  p_val: probability of the null hypothesis
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
                    props[prop]["p_val"] = self.tester.test(data[0][prop], data[1][prop])
                    props[prop]["description"] = descr
                    if with_equal and self._is_equal(prop, *data):
                        props[prop]["equal"] = True
                    if with_unequal and not self._is_equal(prop, *data):
                        props[prop]["equal"] = False
                    if with_uncertain:
                        props[prop] = self._is_uncertain(prop, *data)
                    else:
                        if self._is_uncertain(prop, *data):
                            props.__delitem__(prop)
                if len(props) > 0:
                    arr.append({
                        "data": set(data),
                        "properties": props
                    })
        return arr
