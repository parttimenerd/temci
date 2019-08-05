"""
Implements an autotuning for temci settings.

The intermediate goal is to get a list of applied plugins that
reduces the standard deviation for a given run configuration.

It uses the temci meta runner and a greedy algorithm.
"""
import abc
import copy
import logging
import os
import subprocess
import tempfile
import typing as t
import numpy as np
from functools import total_ordering

import yaml

from temci.report.rundata import RunData, RunDataStatsHelper
from temci.run.run_driver import ExecRunDriver
from temci.utils.settings import Settings
from temci.utils.util import has_root_privileges

LOG = logging.getLogger("auto tune")


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

    def __str__(self):
        return self.to_cli_options()

    def __repr__(self):
        return "[" + self.to_cli_options() + "]"


class PluginSubConfiguration(SubConfiguration):

    def apply_to_settings_dict(self, d: dict):
        d["run"]["exec_plugins"][self.name + "_active"] = True

    def to_cli_options(self) -> str:
        return "--" + self.name


class Setting:
    """
    Contains the sub configurations for a specific setting (or plugin)
    """

    def __init__(self, name: str):
        self.name = name

    def configurations(self) -> t.List[SubConfiguration]:
        pass


class PluginSetting(Setting):

    def configurations(self) -> t.List[SubConfiguration]:
        return [PluginSubConfiguration(self.name)]


@total_ordering
class ConfigurationMeasurements:
    """
    Contains the measurements for a concrete configuration
    """

    def __init__(self, conf: 'Configuration', stats: RunDataStatsHelper):
        self.conf = conf
        self.stats = stats

    def __lt__(self, other: 'ConfigurationMeasurements') -> bool:
        return self.mean_std() < other.mean_std()

    def mean_std(self) -> float:
        return np.mean([prop.std_dev_per_mean() for rundata in self.stats.runs for prop in rundata.get_single_properties().values()])

    def __eq__(self, other: 'ConfigurationMeasurements') -> bool:
        return self.mean_std() == other.mean_std()


    def __str__(self):
        return str(self.mean_std())


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
        d["run"]["exec_misc"]["preset"] = "none"
        for sub in self.subs.values():
            sub.apply_to_settings_dict(d)
        with open(file_name, "w") as f:
            print(Settings().type_scheme.get_default_yaml(defaults=d), file=f)

    def to_cli_options(self) -> str:
        """
        Returns a string that contains all needed command line options
        """
        return "--preset none " + " ".join(sub.to_cli_options() for sub in self.subs.values())

    def __add__(self, conf: SubConfiguration) -> 'Configuration':
        assert isinstance(conf, SubConfiguration)
        d = self.subs.copy()
        d[conf.name] = conf
        return Configuration(d)

    def __contains__(self, name: str) -> bool:
        return name in self.subs

    def __lt__(self, other: 'Configuration') -> bool:
        return self.measurements < other.measurements

    def __eq__(self, other: 'Configuration') -> bool:
        return self.measurements == other.measurements

    def __str__(self):
        return self.to_cli_options()

    def __repr__(self):
        return "[" + self.to_cli_options() + "]"


class SettingCombination:

    def __init__(self, *settings: Setting):
        self.settings = settings

    def available_new_settings(self, config: Configuration) -> t.Iterable[Setting]:
        new = []
        for setting in self.settings:
            if setting.name not in config.subs:
                new.append(setting)
        return new


BASIC_SETTINGS = SettingCombination(
    *(PluginSetting(p) for p in ExecRunDriver.registry)
)
if not has_root_privileges():
    BASIC_SETTINGS = SettingCombination(
        *(PluginSetting(p) for p, v in ExecRunDriver.registry.items() if not v.needs_root_privileges)
    )


class Algorithm(abc.ABC):

    def __init__(self, run_config: t.Union[str, list], settings: SettingCombination,
                 sleep: int = 5, drop_fs_caches: bool = True,
                 properties: t.Iterable[str] = None):
        self.properties = properties or ["all"]
        self.drop_fs_caches = drop_fs_caches
        self.sleep = sleep
        self.run_config = run_config
        self.tmp_dir = tempfile.TemporaryDirectory()
        if isinstance(run_config, list):
            conf_dict = run_config
            self.run_config = self.tmp_dir.name + "/run_config.yaml"
            with open(self.run_config, "w") as f:
                yaml.safe_dump(conf_dict, f)
        self.settings = settings
        self.history = []  # type: t.List[Configuration]
        self.base_conf = None  # type: Configuration

    def tune(self, start: Configuration = None) -> Configuration:
        start = start or Configuration()
        new_conf = start
        initial_m = self.measure_initial(start)
        self.base_conf = start
        self.base_conf.measurements = initial_m
        LOG.info("Default config has deviation of {:3.3%}".format(initial_m.mean_std()))
        while new_conf:
            old_conf = new_conf
            new_conf = self.select_new_configuration(old_conf)
            if new_conf:
                LOG.info("Selected {}".format(new_conf.to_cli_options()))
                LOG.info("… {}".format(self.format_measurements(new_conf.measurements)))
                self.history.append(new_conf)
            else:
                LOG.info("{} seems to be good".format(old_conf.to_cli_options()))
                LOG.info("… {}".format(self.format_measurements(old_conf.measurements)))
                return old_conf
        return new_conf

    def select_new_configuration(self, last: Configuration) -> t.Optional[Configuration]:
        raise NotImplementedError()

    def measure(self, runs: int, config: Configuration) -> ConfigurationMeasurements:
        if config.measurements:
            return config
        output_file = self.tmp_dir.name + "/run_output.yaml"
        temci_cmd = "temci exec {} --runs {} --out {} {}".format(self.run_config, runs, output_file, config.to_cli_options())
        if self.sleep > 0:
            temci_cmd = "sleep {}; ".format(self.sleep) + temci_cmd
        if self.drop_fs_caches and has_root_privileges():
            temci_cmd = "sync; echo 3 > /proc/sys/vm/drop_caches; " + temci_cmd
        else:
            temci_cmd = "sync; " + temci_cmd
        proc = subprocess.Popen(["/bin/sh", "-c", temci_cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            msg = "Error executing '" + temci_cmd + "' in {}: ".format(type(self)) + str(err) + " " + str(out)
            # logging.error(msg)
            raise EnvironmentError(msg)
        from temci.report.rundata import RunDataStatsHelper
        measurements = ConfigurationMeasurements(config, RunDataStatsHelper.init_from_file(output_file).include_properties(self.properties))
        config.measurements = measurements
        LOG.debug("{}: {}".format(self.format_measurements(measurements), config.to_cli_options()))
        return measurements

    def measure_initial(self, start: Configuration) -> ConfigurationMeasurements:
        raise NotImplementedError()

    def __del__(self):
        self.tmp_dir.cleanup()

    def format_measurements(self, m: ConfigurationMeasurements) -> str:
        if self.base_conf is None or self.base_conf.measurements is None:
            return "{:>7s}".format("{:>3.3%}".format(m.mean_std()))
        rel = m.mean_std() / self.base_conf.measurements.mean_std()
        return "{:>3.3f} * base.std = {:>7s}".format(rel, "{:3.3%}".format(m.mean_std()))


class BasicGreedyAlgorithm(Algorithm):

    def __init__(self, run_config: t.Union[str, dict], settings: SettingCombination,
                 sleep: int = 5, drop_fs_caches: bool = True, runs: int = 10,
                 properties: t.Iterable[str] = None):
        super().__init__(run_config, settings, sleep, drop_fs_caches, properties)
        self.runs = runs
        self.measurements = {}  # type: Dict[str, ConfigurationMeasurements]

    def select_new_configuration(self, last: Configuration) -> t.Optional[Configuration]:
        new = last
        combined = []
        for setting in self.settings.available_new_settings(last):
            best_subconf = None
            for subconf in setting.configurations():
                conf = last + subconf
                if best_subconf:
                    if self.measure(self.runs, conf) < self.measure(self.runs, last + best_subconf):
                        best_subconf = subconf
            conf = conf + subconf
            if self.measure(self.runs, conf) < self.measure(self.runs, last):
                new += subconf
                combined.append(last + subconf)
        combined.append(new)
        new_max = last
        for c in combined:
            if self.measure(self.runs, c) < self.measure(self.runs, last):
                new_max = c
        if new_max != last:
            return new_max
        return None

    def measure(self, runs: int, config: Configuration) -> ConfigurationMeasurements:
        key = config.to_cli_options() + " ~ " + str(runs)
        if key not in self.measurements:
            self.measurements[key] = super().measure(runs, config)
        config.measurements = self.measurements[key]
        return self.measurements[key]

    def measure_initial(self, start: Configuration) -> ConfigurationMeasurements:
        return self.measure(self.runs, start)
