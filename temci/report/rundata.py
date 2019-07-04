"""
Contains the RunData object for benchmarking data of specific program block
and the RunDataStatsHelper that provides helper methods for working with
these objects.
"""
import traceback
from functools import reduce

from temci.report.testers import Tester, TesterRegistry
from temci.run.run_driver import filter_runs
from temci.utils.typecheck import *
from temci.utils.settings import Settings
import temci.utils.util as util
from collections import defaultdict
if util.can_import("scipy"):
    import scipy
import typing as t


Number = t.Union[int, float]
""" Numeric value """


def get_for_tags(per_tag_settings_key: str, main_key: str, tags: t.List[str], combinator: t.Callable[[t.Any, t.Any], t.Any]):
    if tags is None:
        return Settings()[main_key]
    return reduce(combinator, (get_for_tag(per_tag_settings_key, main_key, t) for t in tags))


def get_for_tag(per_tag_settings_key: str, main_key: str, tag: t.Optional[str]):
    per_tag = Settings()[per_tag_settings_key]
    return per_tag[tag] if tag is not None and tag in per_tag else Settings()[main_key]


class RecordedError:

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return self.message


class RecordedProgramError(RecordedError):

    def __init__(self, message: str, out: str, err: str, ret_code: int):
        super().__init__("""
{}
        
Output:
------
    {}
        
Error output:
------------
    {}

Return code: {}""".format(message, "\n\t".join(out.split("\n")), "\n\t".join(err.split("\n")), ret_code))
        self.message = message
        self.out = out
        self.err = err
        self.ret_code = ret_code


class RecordedInternalError(RecordedError):

    def __init__(self, message: str):
        self.message = message

    @classmethod
    def for_exception(cls, ex: BaseException) -> 'RecordedInternalError':
        return RecordedInternalError(str(ex) + "\n" +
                                     "\n".join(traceback.format_exception(None, ex, ex.__traceback__)))


@util.document(block_type_scheme="An entry in the run output list",
               property_descriptions_scheme="An entry in the run output list that specifies the long names "
                                            "for the properties")
class RunData(object):
    """
    A set of benchmarking data for a specific program block.
    """

    block_type_scheme = Dict({
                    "data": Dict(key_type=Str(), value_type=List(Int()|Float()), unknown_keys=True) // Default({}),
                    "attributes": Dict({
                        "tags": ListOrTuple(Str()) // Default([]) // Description("Tags of this block"),
                        "description": (Str() | NonExistent())
                    }, key_type=Str(), unknown_keys=True),
                    "error": (Dict({"message": Str(), "return_code": Int(), "output": Str(),
                                    "error_output": Str()}) | NonExistent()),
                    "internal_error": (Dict({"message": Str()}) | NonExistent())
                }, unknown_keys=True) // Constraint(lambda d: [k in d for k in ["error", "internal_error"]].count(True) <= 1,
                                                    description="Either 'error' or 'internal_error' can be present")

    property_descriptions_scheme = Dict({
            "property_descriptions": NonExistent() |
                                     Dict(key_type=Str(), value_type=Str(), unknown_keys=True)})

    def __init__(self, data: t.Dict[str, t.List[Number]] = None, attributes: t.Dict[str, str] = None,
                 recorded_error: RecordedError = None,
                 external: bool = False):
        """
        Initializes a new run data object.
        
        :param data: optional dictionary mapping each property to a list of actual values
        :param attributes: dictionary of optional attributes that describe its program block
        :param recorded_error: either program error or internal error
        :param external: does the data come from a prior benchmarking?
        """
        typecheck(data, E(None) | Dict(unknown_keys=True))
        typecheck(attributes, Exact(None) | Dict(key_type=Str(), unknown_keys=True))
        self.external = external  # type: bool
        """ Does the data come from a prior benchmarking? """
        self.properties = [] # type: t.List[str]
        """ List of measured properties. They might not all be measured the same number of times. """
        self.data = {} # type: t.Dict[str, t.List[Number]]
        """ Raw benchmarking data, mapping properties to their corresponding values """
        if data is not None and len(data) > 0:
            self.add_data_block(data)
        self.attributes = attributes or {}  # type: t.Dict[str, str]
        """ Dictionary of optional attributes that describe its program block """
        self.tags = attributes["tags"] if "tags" in self.attributes else None
        self.max_runs = get_for_tags("run/max_runs_per_tag", "run/max_runs", self.tags, min)
        self.recorded_error = recorded_error
        self.discarded = False

    def clone(self, data: t.Dict[str, t.List[Number]] = None, attributes: t.Dict[str, str] = None,
              recorded_error: RecordedError = None, external: bool = None) -> 'RunData':
        """
        Clone this instance and replaces thereby some instance properties.

        :param data: optional dictionary mapping each property to a list of actual values
        :param attributes: dictionary of optional attributes that describe its program block
        :param external: does the data come from a prior benchmarking?
        :return: new instance
        """
        def alt(new, old):
            return new if new is not None else old
        return RunData(data=alt(data, self.data), attributes=alt(attributes, self.attributes),
                       recorded_error=alt(recorded_error, self.recorded_error),
                       external=alt(external, self.external))

    def add_data_block(self, data_block: t.Dict[str, t.List[Number]]):
        """
        Adds a block of data. 
        
        :param data_block: maps each of the run datas properties to list of actual values (from each benchmarking run).
        """
        typecheck(data_block, Dict(key_type=Str(), value_type= List(Int() | Float()), unknown_keys=True))
        self.properties = set(self.properties).union(set(data_block.keys()))
        for prop in data_block:
            if prop not in self.data:
                self.data[prop] = []
                self.properties.add(prop)
            self.data[prop].extend(data_block[prop])
        self.properties = sorted(list(self.properties))

    def __len__(self) -> int:
        """
        Returns the number of measured properties.
        """
        return len(self.data)

    def min_values(self) -> int:
        """
        Returns the minimum number of measured values for the associated program block
        over all properties.
        """
        return min(map(len, self.data.values())) if len(self) > 0 else 0

    def benchmarks(self) -> int:
        """
        Returns the maximum number of measured values for the associated program block
        over all properties.
        """
        return max(map(len, self.data.values())) if len(self) > 0 else 0

    def __getitem__(self, property: str) -> list:
        """
        Returns the benchmarking values associated with the passed property.
        """
        return self.data[property]

    def to_dict(self) -> t.Dict[str, t.Union[t.Dict[str, str], t.Dict[str, t.List[Number]]]]:
        """
        Returns a dictionary that represents this run data object.
        """
        d = {
            "attributes": self.attributes,
            "data": self.data
        }
        if self.has_error():
            if isinstance(self.recorded_error, RecordedInternalError):
                d["internal_error"] = {
                    "message": self.recorded_error.message
                }
            if isinstance(self.recorded_error, RecordedProgramError):
                d["error"] = {
                    "message": self.recorded_error.message,
                    "return_code": self.recorded_error.ret_code,
                    "output": self.recorded_error.out,
                    "error_output": self.recorded_error.err
                }
        return d

    def __str__(self) -> str:
        return repr(self.attributes)

    def description(self) -> str:
        """ Description of this instance based on the attributes """
        if "description" in self.attributes and self.attributes["description"] is not None:
            return self.attributes["description"]
        return ", ".join("{}={}".format(key, self.attributes[key]) for key in self.attributes)

    def exclude_properties(self, properties: t.List[str]) -> 'RunData':
        """
        Creates a new run data instance without the passed properties.

        :param properties: excluded properties
        :return: new run data instance
        """
        data = {}
        for prop in self.data:
            if prop not in properties:
                data[prop] = self.data[prop]
        return self.clone(data=data)

    def include_properties(self, properties: t.List[str]) -> 'RunData':
        """
        Creates a new run data instance with only the passed properties.

        :param properties: included properties
        :return: new run data instance
        """
        data = {}
        for prop in self.data:
            if prop in properties:
                data[prop] = self.data[prop]
        return self.clone(data=data)

    def exclude_invalid(self) -> t.Tuple[t.Optional['RunData'], t.List[str]]:
        """
        Exclude properties that only have NaNs as measurements.

        :return: (new run data instance or None if all properties are excluded or the current if nothing changed,
                  excluded properties)
        """
        data = {}
        excluded = []
        nan = float("nan")
        for prop in self.data:
            if not all(x == nan for x in self.data[prop]):
                data[prop] = self.data[prop]
            else:
                excluded.append(prop)
        excluded = sorted(excluded)
        if not excluded:
            return self, []
        if len(data) > 0:
            return self.clone(data=data), excluded
        return None, excluded

    def long_properties(self, long_versions: t.Dict[str, str]) -> 'RunData':
        """
        Replace the short properties names with their long version from the passed dictionary.

        :param long_versions: long versions of some properties
        :return: new run data instance (or current instance if nothing changed)
        """
        if not long_versions:
            return self
        data = {}
        for prop in self.data:
            longer_prop = prop
            if prop in long_versions:
                longer_prop = long_versions[prop]
            data[longer_prop] = self.data[prop]
        return self.clone(data=data)

    def has_error(self) -> bool:
        return self.recorded_error is not None


class RunDataStatsHelper(object):
    """
    This class helps to simplify the work with a set of run data observations.
    """

    def __init__(self, runs: t.List[RunData], tester: Tester = None, external_count: int = 0,
                 property_descriptions: t.Dict[str, str] = None,
                 errorneous_runs: t.List[RunData] = None,
                 included_blocks: str = None):
        """
        Don't use the constructor use init_from_dicts if possible.

        :param runs: list of run data objects
        :param tester: used tester or tester that is set in the settings
        :param external_count: Number of external program blocks (blocks for which the data was obtained in a
        different benchmarking session)
        :param property_descriptions: mapping of some properties to their descriptions or longer versions
        :param errorneous_runs: runs that resulted in errors
        :param included_blocks: include query
        """
        self.tester = tester or TesterRegistry.get_for_name(TesterRegistry.get_used(),  # type: Tester
                                                            Settings()["stats/uncertainty_range"])
        """ Used statistical tester """
        typecheck(runs, List(T(RunData)))
        self.runs = filter_runs(runs, included_blocks or Settings()["report/included_blocks"])  # type: t.List[RunData]
        self.errorneous_runs = errorneous_runs or [r for r in self.runs if r.has_error()]
        self.runs = [r for r in self.runs if not r.has_error() or (any(len(v) > 0 for v,p in r.data.items()))]
        """ Data of serveral runs from several measured program blocks """
        self.external_count = external_count  # type: int
        """
        Number of external program blocks (blocks for which the data was obtained in a different benchmarking session)
        """
        self.property_descriptions = property_descriptions or {}  # type: t.Dict[str, str]

    def clone(self, runs: t.List[RunData] = None, tester: Tester = None, external_count: int = None,
              property_descriptions: t.Dict[str, str] = None) -> 'RunDataStatsHelper':
        """
        Clones this instance and replaces the given instance properties.

        :param runs: list of run data objects
        :param tester: used tester or tester that is set in the settings
        :param external_count: Number of external program blocks (blocks for which the data was obtained in a
        different benchmarking session)
        :param property_descriptions: mapping of some properties to their descriptions or longer versions
        :return: cloned instance
        """
        def alt(new, old):
            return new if new is not None else old
        return RunDataStatsHelper(runs=alt(runs, self.runs), tester=alt(tester, self.tester),
                                  external_count=alt(external_count, self.external_count),
                                  property_descriptions=alt(property_descriptions, self.property_descriptions),
                                  errorneous_runs=self.errorneous_runs)

    def make_descriptions_distinct(self):
        """
        Append numbers to descriptions if needed to make them unique
        """
        descr_attrs = defaultdict(lambda: 0)  # type: t.Dict[str, int]
        descr_nr_zero = {}  # type: t.Dict[str, RunData]

        for single in self.runs:
            if "description" in single.attributes and single.attributes["description"] is not None:
                descr = single.attributes["description"]
                num = descr_attrs[descr]
                descr_attrs[descr] += 1
                if num != 0:
                    single.attributes["description"] += " [{}]".format(num)
                    if num == 1:
                        descr_nr_zero[descr].attributes["description"] += " [0]"
                else:
                    descr_nr_zero[descr] = single
                single.attributes["__description"] = descr

    def get_description_clusters(self) -> t.Dict[str, t.List['RunData']]:
        """
        Set of runs per description, call RunDataStatsHelper.make_descriptions_distinct first

        :return: set of runs per description
        """
        clusters = util.InsertionTimeOrderedDict()
        for r in self.runs:
            d = r.attributes["__description" if "__description" in r.attributes else "description"] \
                if "description" in r.attributes \
                else ""
            if d not in clusters:
                clusters[d] = []
            clusters[d].append(r)
        return clusters

    def get_description_clusters_and_single(self) -> t.Tuple[t.List['RunData'], t.Dict[str, t.List['RunData']]]:
        """
        Set of runs per description, call RunDataStatsHelper.make_descriptions_distinct first

        :return: set of runs per description
        """
        clusters = self.get_description_clusters()
        new_clusters = util.InsertionTimeOrderedDict()
        single = []
        for n, c in clusters.items():
            if len(c) is 1:
                single.extend(c)
            else:
                new_clusters[n] = c
        return single, new_clusters

    def properties(self) -> t.List[str]:
        """
        Returns a sorted list of all properties that exist in all run data blocks.
        """
        if not self.runs:
            return []
        props = set(self.runs[0].properties)
        for rd in self.runs[1:]:
            if rd:
                props = props.intersection(rd.properties)
        return list(sorted(props))

    @classmethod
    def init_from_dicts(cls, runs: t.List[t.Union[t.Dict[str, str], t.Dict[str, t.List[Number]]]] = None,
                        external: bool = False,
                        included_blocks: str = None) -> 'RunDataStatsHelper':
        """
        Expected structure of the stats settings and the runs parameter::

            "stats": {
                "tester": ...,
                "properties": ["prop1", ...],
                # or
                "properties": ["prop1", ...],
                "uncertainty_range": (0.1, 0.3)
            }

            "runs": [
                {"attributes": {"attr1": ..., ..., ["description": …], ["tags": …]},
                 "data": {"__ov-time": [...], ...},
                 "error": {"return_code": …, "output": "…", "error_output": "…"},
                 "internal_error": {"message": "…"} (either "error" or "internal_error" might be present)
                 ["property_descriptions": {"__ov-time": "Overall time"}]},
                 ...
            ]


        :param runs: list of dictionaries representing the benchmarking runs for each program block
        :param external: are the passed runs not from this benchmarking session but from another?
        :param included_blocks: include query
        :raises ValueError: if the stats of the runs parameter have not the correct structure
        """
        typecheck(runs, List(
            Dict({
                "data": Dict(key_type=Str(), value_type=List(Int() | Float()), unknown_keys=True) | NonExistent(),
                "run_config": Dict(unknown_keys=True)
            }, unknown_keys=True) |
                    RunData.block_type_scheme |
                    RunData.property_descriptions_scheme),
                value_name="runs parameter")
        run_datas = []
        runs = runs or [] # type: t.List[dict]
        prop_descrs = {}  # type: t.Dict[str, str]
        for run in runs:
            props = {}
            if "property_descriptions" in run:
                prop_descrs.update(run["property_descriptions"])
            else:
                if "data" not in run:
                    run["data"] = {}
                error = None
                if "error" in run:
                    error = RecordedProgramError(run["error"]["message"], run["error"]["output"],
                                                 run["error"]["error_output"], run["error"]["return_code"])
                elif "internal_error" in run:
                    error = RecordedInternalError(run["internal_error"]["message"])
                run_datas.append(RunData(run["data"], run["attributes"] if "attributes" in run else {}, recorded_error=error,
                                         external=external))
        return RunDataStatsHelper(run_datas, external_count=len(run_datas) if external else 0,
                                  property_descriptions=prop_descrs, included_blocks=included_blocks)

    def _is_uncertain(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_uncertain(data1[property], data2[property])

    def _is_equal(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_equal(data1[property], data2[property])

    def _is_unequal(self, property: str, data1: RunData, data2: RunData) -> bool:
        return self.tester.is_unequal(data1[property], data2[property])

    def is_uncertain(self, p_val: float) -> bool:
        """
        Does the passed probability of the null hypothesis for two samples lie in the uncertainty range?
        :param p_val: passed probability of the null hypothesis
        """
        return min(*Settings()["stats/uncertainty_range"]) <= p_val <= max(*Settings()["stats/uncertainty_range"])

    def is_equal(self, p_val: float) -> bool:
        """ Is the passed value above the uncertainty range for null hypothesis probabilities? """
        return p_val > max(*Settings()["stats/uncertainty_range"])

    def is_unequal(self, p_val: float) -> bool:
        """ Is the passed value above the uncertainty range for null hypothesis probabilities? """
        return p_val < min(*Settings()["stats/uncertainty_range"])

    def _speed_up(self, property: str, data1: RunData, data2: RunData):
        """
        Calculates the speed up from the second to the first
        (e.g. the first is RESULT * 100 % faster than the second).
        """
        return (scipy.mean(data1[property]) - scipy.mean(data2[property])) \
               / scipy.mean(data1[property])

    def _estimate_time_for_run_datas(self, run_bin_size: int, data1: RunData, data2: RunData,
                                     min_runs: int, max_runs: int) -> float:
        if min(len(data1), len(data2)) == 0 \
                or "__ov-time" not in data1.properties \
                or "__ov-time" not in data2.properties:
            return max_runs
        needed_runs = []
        for prop in set(data1.properties).intersection(data2.properties):
            estimate = self.tester.estimate_needed_runs(data1[prop], data2[prop],
                                                                run_bin_size, min_runs, max_runs)
            needed_runs.append(estimate)
        avg_time = max(scipy.mean(data1["__ov-time"]), scipy.mean(data2["__ov-time"]))
        return max(needed_runs) * avg_time

    def get_program_ids_to_bench(self) -> t.List[int]:
        """
        Returns the ids (the first gets id 0, …) of the program block / run data object that
        should be benchmarked again.
        """
        to_bench = set()
        for (i, run) in enumerate(self.runs):
            if i in to_bench or run is None or run.has_error():
                continue
            for j in range(i):
                if j in to_bench or self.runs[j] is None or self.runs[j].has_error():
                    continue
                run2 = self.runs[j]
                if run2.min_values() == 0 or run.min_values() == 0 or \
                        any(self._is_uncertain(prop, run, run2) for prop in set(run.properties)
                        .intersection(run2.properties)):
                    to_bench.add(i)
                    to_bench.add(j)
        return [i - self.external_count for i in to_bench if i >= self.external_count]

    def estimate_time(self, run_bin_size: int, min_runs: int, max_runs: int) -> float:
        """
        Roughly erstimates the time needed to finish benchmarking all program blocks.
        It doesn't take any parallelism into account. Therefore divide the number by the used parallel processes.

        :warning: Doesn't work well.

        :param run_bin_size: times a program block is benchmarked in a single block of time
        :param min_runs: minimum number of allowed runs
        :param max_runs: maximum number of allowed runs
        :return: estimated time in seconds or float("inf") if no proper estimation could be made
        """
        to_bench = self.get_program_ids_to_bench()
        max_times = [0 for i in self.runs]
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
        :return: estimated time in seconds
        """
        if "__ov-time" not in self.properties():
            return -1
        summed = 0
        to_bench = range(0, len(self.runs)) if all else self.get_program_ids_to_bench()
        for i in to_bench:
            summed += scipy.mean(self.runs[i]["__ov-time"] if "__ov-time" in self.runs[i].data else 0) * run_bin_size
        return summed

    #ef add_run_data(self, data: t.Dict[str, t.List[Number]] = None, attributes: t.Dict[str, str] = None,
    #                property_descriptions: t.Dict[str, str] = None) -> int:
    #   """
    #   Adds a new run data (corresponding to a program block) and returns its id.
    #
    #   :param data: benchmarking data of the new run data object
    #   :param attributes: attributes of the new run data object
    #   :param property_descriptions: mapping of property to a description
    #   :return: id of the run data object (and its corresponding program block)
    #   """
    #   self.runs.append(RunData(data, attributes=attributes, property_descriptions))
    #   return len(self.runs) - 1

    def discard_run_data(self, id: int):
        """
        Disable that run data object with the given id.
        """
        self.runs[id].discarded = True

    def add_data_block(self, program_id: int, data_block: t.Dict[str, t.List[Number]]):
        """
        Add block of data for the program block with the given id.

        :param program_id: id of the program.
        :param data_block: list of data from several benchmarking runs of the program block
        :raises ValueError: if the program block with the given id doesn't exist
        """
        program_id += self.external_count
        assert program_id >= self.external_count
        if program_id >= len(self.runs):
            raise ValueError("Program block with id {} doesn't exist".format(program_id - self.external_count))
        self.runs[program_id].add_data_block(data_block)

    def add_error(self, program_id: id, error: RecordedError):
        """
        Set the error for a program
        """
        program_id += self.external_count
        assert program_id >= self.external_count
        self.runs[program_id].recorded_error = error
        self.errorneous_runs.append(self.runs[program_id])

    def has_error(self, program_id: int) -> bool:
        """ Is there an error recorded for the program with the given id? """
        return self.runs[program_id + self.external_count].has_error()

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
        arr = []
        for i in range(0, len(self.runs) - 1):
            for j in range(i + 1, len(self.runs)):
                if self.runs[i].discarded or self.runs[j].discarded:
                    continue
                data = (self.runs[i], self.runs[j])
                props = {}
                for prop in self.properties():
                    map = {"p_val": self.tester.test(data[0][prop], data[1][prop]),
                           "speed_up": self._speed_up(prop, *data),
                           "description": prop,
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

    def serialize(self) -> t.List[t.Union[t.Dict[str, str], t.Dict[str, t.List[Number]]]]:
        """
        Serialize this instance into a data structure that is accepted by the ``init_from_dicts`` method.
        """
        ret = [x.to_dict() for x in self.runs if not x.discarded]
        if self.property_descriptions:
            ps = {}  # type: t.Dict[str, str]
            props = self.properties()
            for prop in props:
                if prop in self.property_descriptions:
                    ps[prop] = self.property_descriptions[prop]
            ret.append({"property_descriptions": ps})
        return ret

    def valid_runs(self) -> t.List[RunData]:
        """ Number of valid (with measured data) runs """
        res = [x for x in self.runs if not x.discarded]
        return res

    def exclude_properties(self, properties: t.List[str]) -> 'RunDataStatsHelper':
        """
        Create a new instance without the passed properties.

        :param properties: excluded properties
        :return: new instance
        """
        runs = []
        for run in self.runs:
            if not run.discarded:
                runs.append(run.exclude_properties(properties))
        return self.clone(runs=runs)

    def include_properties(self, properties: t.List[str]) -> 'RunDataStatsHelper':
        """
        Create a new instance with only the passed properties.

        :param properties: included properties
        :return: new instance
        """
        runs = []
        for run in self.runs:
            if not run.discarded:
                runs.append(run.include_properties(properties))
        return self.clone(runs=runs)

    def exclude_invalid(self) -> t.Tuple['RunDataStatsHelper', 'ExcludedInvalidData']:
        """
        Exclude all properties of run datas that only have zeros or NaNs as measurements.

        :return: (new instance, info about the excluded data)
        """
        excl = ExcludedInvalidData()
        runs = []
        external_count = self.external_count
        for run in self.runs:
            run_data, excl_props = run.exclude_invalid()
            if run_data:
                if excl_props:
                    excl.excluded_properties_per_run_data[run.description()] = excl_props
                runs.append(run_data)
            else:
                excl.excluded_run_datas.append(run.description())
                if run.external:
                    external_count -= 1
        return self.clone(runs=runs, external_count=external_count), excl

    def add_property_descriptions(self, property_descriptions: t.Dict[str, str]):
        """
        Adds the given property descriptions.

        :param property_descriptions: mapping of some properties to their descriptions or longer versions
        """
        if not property_descriptions:
            return
        self.property_descriptions.update(property_descriptions)

    def long_properties(self, property_format: str = "[{}]") -> t.Tuple['RunDataStatsHelper', t.Dict[str, str]]:
        """
        Replace the short properties names with their descriptions if possible.

        :param property_format: format string that gets a property description and produces a longer property name
        :return: new instance, a dict that returns a long property name for a given short property name
        """
        runs = []
        formatted_properties = {}  # type: t.Dict[str, str]
        for p in self.property_descriptions:
            formatted_properties[p] = property_format.format(self.property_descriptions[p])
        for run in self.runs:
            if not run.discarded:
                runs.append(run.long_properties(formatted_properties))

        return self.clone(runs=runs), formatted_properties


class ExcludedInvalidData:
    """
    Info object that contains information about the excluded invalid data.
    """

    def __init__(self):
        self.excluded_run_datas = []  # type: t.List[str]
        """ Descriptions of the fully excluded run datas """
        self.excluded_properties_per_run_data = util.InsertionTimeOrderedDict()  # type: t.Dict[str, t.List[str]]
        """
        Run data descriptions mapped to the excluded properties per run data.
        Only includes not fully excluded run datas.
        """