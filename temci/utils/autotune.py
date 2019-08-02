"""
Implements an autotuning for temci settings.

The intermediate goal is to get a list of applied plugins that
reduces the standard deviation for a given run configuration.

It uses the temci meta runner and a greedy algorithm.
"""
import copy
import typing as t
import numpy as np
from functools import total_ordering

from temci.report.rundata import RunData
from temci.utils.settings import Settings


class SubConfiguration:
    """ An instance per major setting """

    def __init__(self, name: str):
        self.name = name

    def apply_to_settings_dict(self, d: dict):
        """
        Store the configuration in the settings dict
        """
        pass

    def to_cli_options(self) -> str:
        """
        Returns a string that contains all needed command line options
        """
        pass


class Setting:
    """
    Contains the sub configurations for a specific setting (or plugin)
    """

    def configurations(self) -> t.List[SubConfiguration]:
        pass


@total_ordering
class ConfigurationMeasurements:
    """
    Contains the measurements for a concrete configuration
    """

    def __init__(self, conf: 'Configuration', rundata: RunData):
        self.conf = conf
        self.rundata = rundata

    def __lt__(self, other: 'ConfigurationMeasurements') -> bool:
        return self.mean_std() < other.mean_std()

    def mean_std(self) -> float:
        return np.mean([prop.std() for prop in self.rundata.get_single_properties().values()])

    def __eq__(self, other: 'ConfigurationMeasurements') -> bool:
        return self.mean_std() == other.mean_std()


@total_ordering
class Configuration:

    def __init__(self, subs: t.Dict[str, SubConfiguration] = None):
        self.subs = subs or {}
        """ Sub configurations """
        self.measurements = None  # type: t.Optional[ConfigurationMeasurements]

    def to_settings_file(self, file_name="temci.yaml"):
        """
        Store the configuration in a settings file
        """
        d = copy.deepcopy(Settings().prefs)
        for sub in self.subs.values():
            sub.apply_to_settings_dict(d)
        with open(file_name, "w") as f:
            print(Settings().type_scheme.get_default_yaml(defaults=d), file=f)

    def to_cli_options(self) -> str:
        """
        Returns a string that contains all needed command line options
        """
        return " ".join(sub.to_cli_options() for sub in self.subs.values())

    def __add__(self, conf: SubConfiguration) -> 'Configuration':
        d = self.subs.copy()
        d[conf.name] = conf
        return Configuration(d)

    def __contains__(self, name: str) -> bool:
        return name in self.subs

    def __lt__(self, other: 'Configuration') -> bool:
        return self.measurements < other.measurements

    def __eq__(self, other: 'Configuration') -> bool:
        return self.measurements == other.measurements


class SettingCombination:

    settings = []  # type: t.List[Setting]


class Algorithm:

    def __init__(self, run_conf: t.Dict[str, dict], settings: SettingCombination, times: int = 1):
        self.run_conf = run_conf
        self.settings = settings
        self.times = times
        self.history = []  # type: t.List[Configuration]

    def tune(self, start: Configuration = None) -> Configuration:
        pass

    def select_new_configuration(self, last: Configuration) -> Configuration:
        raise NotImplementedError()

    def measure(self, config: Configuration) -> ConfigurationMeasurements:
        pass