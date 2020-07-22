from temci.utils.number import FNumber

import yaml
import copy
import os, logging
import click

from temci.utils.typecheck import Obsolete
from temci.utils.util import recursive_exec_for_leafs, Singleton, sphinx_doc
from temci.utils.typecheck import *
import multiprocessing
import typing as t


def ValidCPUCoreNumber() -> Int:
    """
    Creates a Type instance that matches all valid CPU core numbers.
    """
    return Int(range=range(0, multiprocessing.cpu_count()))

class SettingsError(ValueError):
    """ Error raised if something with the settings goes wrong """
    pass


class Settings(metaclass=Singleton):
    """
    Manages the Settings.
    The settings keys and sub keys are combined by a slash, e.g. "report/in".

    The current settings are:

    .. code: yaml


    """

    config_file_name = "temci.yaml"  # type: str
    """ Default name of the configuration files """
    type_scheme = Dict({
        "settings": Str() // Description("Additional settings file")
                        // Default(config_file_name if os.path.exists(config_file_name) else "")
                        // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
        "config": Str() // Description("Alias for settings")
                    // Default(config_file_name if os.path.exists(config_file_name) else "")
                    // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
        "tmp_dir": Str() // Default("/tmp/temci") // Description("Used temporary directory"),
        "log_level": ExactEither("debug", "info", "warn", "error", "quiet") // Default("info")
                     // Description("Logging level"),
        "stats": Dict({
            "properties": ListOrTuple(Str()) // Default(["all"])
                        // CompletionHint(zsh="(" + " ".join(["__ov-time", "cache-misses", "cycles", "task-clock",
                                                              "instructions", "branch-misses", "cache-references",
                                                              "all"])
                                              + ")")
                        // Description("Properties to use for reporting and null hypothesis tests, "
                                       "can be regular expressions"),
            "uncertainty_range": Tuple(Float(lambda x: x >= 0), Float(lambda x: x >= 0)) // Default([0.05, 0.15])
                        // Description("Range of p values that allow no conclusion.")
        }, unknown_keys=True),
        "report": Dict({
            #  "reporter": Str() // Default("console") // Description(),
            "in": Either(Str(), ListOrTuple(Str())) // Default("run_output.yaml")
                  // Description("Files that contain the benchmarking results")
                  // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "excluded_properties": ListOrTuple(Str()) // Default(["__ov-time"])
                    // Description("Properties that aren't shown in the report."),
            "exclude_invalid": BoolOrNone() // Default(True)
                    // Description("Exclude all data sets that contain only NaNs."),
            "long_properties": BoolOrNone() // Default(False)
                    // Description("Replace the property names in reports with longer more descriptive versions?"),
            "xkcd_like_plots": BoolOrNone() // Default(False)
                    // Description("Produce xkcd like plots (requires the humor sans font to be installed)"),
            "number": FNumber.settings_format,
            "included_blocks": ListOrTuple(Str()) // Default(["all"])
                               // Description("List of included run blocks (all: include all), "
                                              "identified by their description or tag attribute, "
                                              "can be regular expressions"),
        }, unknown_keys=True),
        "run": Dict({
            "discarded_runs": NaturalNumber() // Description("First n runs that are discarded") // Default(1),
            "min_runs": NaturalNumber() // Default(20) // Description("Minimum number of benchmarking runs"),
            "max_runs": NaturalNumber() // Default(100) // Description("Maximum number of benchmarking runs"),
            "max_runs_per_tag": Dict(unknown_keys=True, key_type=Str() // Description("Tag"), value_type=NaturalNumber() // Description("Max runs"))
                                 // Default({}) // Description("Maximum runs per tag (block attribute 'tag'), min('max_runs', 'per_tag') is used"),
            "min_runs_per_tag": Dict(unknown_keys=True, key_type=Str() // Description("Tag"),
                                     value_type=NaturalNumber() // Description("Min runs"))
                                // Default({}) // Description(
                                "Minimum runs per tag (block attribute 'tag'), max('min_runs', 'per_tag') is used"),
            "runs_per_tag": Dict(unknown_keys=True, key_type=Str() // Description("Tag"),
                                     value_type=NaturalNumber() // Description("Runs"))
                                // Default({}) // Description(
                                 "Runs per tag (block attribute 'tag'), max('runs', 'per_tag') is used"),
            "runs": Int(lambda x: x >= -1) // Default(-1) // Description("if != -1 sets max and min runs to its value"),
            "max_time": ValidTimeSpan() // Default("-1") // Description("Maximum time the whole benchmarking should take, "
                                                                        "-1 == no timeout, supports normal time span expressions"), # in seconds
            "max_block_time": ValidTimeSpan() // Default("-1") // Description("Maximum time one run block should take, "
                                                                              "-1 == no timeout, supports normal time span expressions"),
            "run_block_size": PositiveInt() // Default(1)
                              // Description("Number of benchmarking runs that are done together"),
            "in": Str() // Default("input.exec.yaml")
                  // Description("Input file with the program blocks to benchmark")
                  // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "out": Str() // Default("run_output.yaml") // Description("Output file for the benchmarking results")
                    // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "store_often": Bool() // Default(False)
                           // Description("Store the result file after each set of blocks is benchmarked"),
            "exec_plugins": Dict({

            }),
            "included_blocks" : ListOrTuple(Str()) // Default(["all"])
                              // Description("List of included run blocks (all: include all), "
                                             "or their tag attribute "
                                             "or their number in the file (starting with 0), "
                                             "can be regular expressions"),
            "cpuset": Dict({
                "active": Bool() // Description("Use cpuset functionality?") // Default(False),
                "base_core_number": ValidCPUCoreNumber()
                                    // Description("Number of cpu cores for the base (remaining part of the) system") // Default(1),
                "parallel": Int(lambda x: x >= -1) // Description("0: benchmark sequential, "
                                                      "> 0: benchmark parallel with n instances, "
                                                      "-1: determine n automatically") // Default(0),
                "sub_core_number": ValidCPUCoreNumber() // Description("Number of cpu cores per parallel running program.")
                                   // Default(1),
                "temci_in_base_set": Bool() // Default(True)
                                     // Description("place temci in the same cpu set as the rest of the system?")
            }),
            "disable_hyper_threading": Bool() // Default(False)
                                       // Description("Disable the hyper threaded cores. Good for cpu bound programs."),
            "show_report": Bool() // Default(True)
                // Description("Print console report if log_level=info"),
            "append": Bool() // Default(False)
                      // Description("Append to the output file instead of overwriting by adding new run data blocks"),
            "shuffle": Bool() // Default(True) // Description("Randomize the order in which the program blocks are "
                                                              "benchmarked."),
            "send_mail": Str() // Default("")
                         // Description("If not empty, recipient of a mail after the benchmarking finished."),
            "discard_all_data_for_block_on_error": Bool() // Default(False)
                         // Description("Discard all run data for the failing program on error"),
            "record_errors_in_file": Bool() // Default(True)
                         // Description("Record the caught errors in the run_output file"),
            "no_build": Bool() // Default(False)
                         // Description("Do not build if build configs are present, only works if the working directory "
                                        "of the blocks does not change"),
            "only_build": Bool() // Default(False) // Description("Only build"),
            "abort_after_build_error": Bool() // Default(True)
                                    // Description("Abort after the first failing build")
        }),
        "build": Dict({
            "in": Str() // Default("build.yaml") // Description("Input file with the program blocks to build")
                // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "out": Str() // Default("run_config.yaml") // Description("Resulting run config file"),
            "threads": PositiveInt() // Default(1) // Description("Number of threads that build simultaneously"),
            "rand": Obsolete("Removed builder randomization", "0.8") // Description("Obsolete randomization configuration")
        }, unknown_keys=True),
        "package": Obsolete("Removed temci package", "0.8"),
        "env": Dict({"USER": Str(), "PATH": Str()}, unknown_keys=True)
               // Default({"USER": "", "PATH": ""})
               // Description("Environment variables for the benchmarked programs, includes the user used for "
                              "generated files"),
        "sudo": Bool() // Default(False) // Description("Acquire sudo privileges and run benchmark programs with "
                                                        "non-sudo user. Only supported on the command line.")
    }, unknown_keys=True)  # type: Dict
    """ Type scheme of the settings """

    def __init__(self):
        """
        Initializes a Settings singleton object and thereby loads the Settings files.
        It loads the settings files from the app folder (config.yaml) and
        the current working directory (temci.yaml) if they exist.

        :raises: SettingsError if some of the settings aren't in the format described via the type_scheme class property
        """
        self.prefs = copy.deepcopy(self.type_scheme.get_default())  # type: t.Dict[str, t.Any]
        """ The set sonfigurations """
        res = self._validate_settings_dict(self.prefs, "default settings")
        if not res:
            raise SettingsError(str(res))
        self._setup()

    def load_files(self):
        """ Loads the configuration files from the current and the config directory """
        self.load_from_config_dir()
        self.load_from_current_dir()
        self._setup()

    def _setup(self):
        """
        Simple setup method that checks if basic directories exist and creates them if necessary.
        """
        if not os.path.exists(self.prefs["tmp_dir"]):
            os.mkdir(self.prefs["tmp_dir"])
        log_level = self["log_level"]
        logging.Logger.disabled = log_level == "quiet"
        logger = logging.getLogger()
        mapping = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warn": logging.WARNING,
            "error": logging.ERROR,
            "quiet": logging.ERROR
        }
        logger.setLevel(mapping[log_level])
        self._update_doc()

    def _update_doc(self):
        """
        Update the class documentation
        """
        if sphinx_doc():
            self.__doc__ = self.__doc__.split(".. code: yaml")[0] + """.. code: yaml 

        """ + "\n        ".join(self.type_scheme.get_default_yaml().split("\n"))

    def reset(self):
        """
        Resets the current settings to the defaults.
        """
        self.prefs = copy.deepcopy(self.type_scheme.get_default())

    def _validate_settings_dict(self, data: t.Dict[str, t.Any], description: str = None):
        """
        Check whether the passed dictionary matches the settings type scheme.

        :param data: passed dictionary
        :param description: short description of the passed dictionary
        :return: True like object if valid, else string like object which is the error message
        """
        return verbose_isinstance(data, self.type_scheme, description or "Settings")

    def load_file(self, file: str):
        """
        Loads the configuration from the configuration YAML file.

        :param file: path to the file
        :raises: SettingsError if the settings file is incorrect or doesn't exist
        """
        self.prefs = self.type_scheme.get_default()
        tmp = copy.deepcopy(self.prefs)
        try:
            with open(file, 'r') as stream:
                map = yaml.safe_load(stream.read().replace("!!python/tuple", ""))

                def func(key, path, value):
                    self._set_default(path, value)
                    self._set(path, value)

                recursive_exec_for_leafs(map, func)
        except (yaml.YAMLError, IOError) as err:
            self.prefs = tmp
            raise SettingsError(str(err))
        res = self._validate_settings_dict(self.prefs, "settings with ones from file '{}'".format(file))
        if not res:
            self.prefs = tmp
            raise SettingsError(str(res))
        self._setup()

    def load_from_dict(self, config_dict: t.Dict[str, t.Any]):
        """
        Load the configuration from the passed dictionary.

        :param config_dict: passed configuration dictionary
        """
        self.prefs = self.type_scheme.get_default()
        tmp = copy.deepcopy(self.prefs)

        def func(key, path, value):
            self._set_default(path, value)

        recursive_exec_for_leafs(config_dict, func)
        res = self._validate_settings_dict(self.prefs, "settings with ones config dict")
        if not res:
            self.prefs = tmp
            raise SettingsError(str(res))
        self._setup()

    def load_from_dir(self, dir: str):
        """
        Load the configuration from the configuration file inside the passed directory.

        :param dir: path of the directory
        """
        self.load_file(os.path.join(dir, "config.yaml"))

    def load_from_config_dir(self):
        """
        Load the config file from the application directory (e.g. in the users home folder) if it exists.
        """
        conf = os.path.join(click.get_app_dir("temci"), "config.yaml")
        if os.path.exists(conf) and os.path.isfile(conf):
            self.load_file(conf)

    def load_from_current_dir(self):
        """
        Load the configuration from the `configuration file in the current working directory if it exists.
        """
        if os.path.exists(self.config_file_name) and os.path.isfile(self.config_file_name):
            self.load_file(self.config_file_name)

    def get(self, key: str) -> t.Any:
        """
        Get the setting with the given key.

        :param key: name of the setting
        :return: value of the setting
        :raises: SettingsError if the setting doesn't exist
        """
        if self.is_obsolete(key):
            raise SettingsError("Using obsolete setting {!r}: {}".format(key, self.obsoleteness_reason(key)))
        path = key.split("/")
        if not self.validate_key_path(path):
            raise SettingsError("No such setting {}".format(key))
        data = self.prefs
        for sub in path:
            data = data[sub]
        return data

    def __getitem__(self, key: str) -> t.Any:
        """
        Alias for self.get(self, key).
        """
        return self.get(key)

    def _set(self, path: t.List[str], value):
        """
        Set the setting at the passed path.

        :param path: passed key path
        :param value: new value
        """
        if self.is_obsolete(path):
            return
        tmp_pref = self.prefs
        tmp_type = self.type_scheme
        for key in path[0:-1]:
            if key not in tmp_pref:
                tmp_pref[key] = {}
                tmp_type[key] = Dict(unknown_keys=True, key_type=Str())
            tmp_pref = tmp_pref[key]
            tmp_type = tmp_type[key]
        tmp_pref[path[-1]] = value
        if path[-1] not in tmp_type.data:
            tmp_type[path[-1]] = Any() // Default(value)
        if (path == ["config"] or path == ["settings"]) and value != "":
            self.load_file(value)
        self._update_doc()

    def validate(self):
        """
        Validate this settings object

        :raises: SettingsError if the setting isn't valid
        """
        self._validate_settings_dict(self.prefs)

    def set(self, key: str, value, validate: bool = True):
        """
        Sets the setting key to the passed new value

        :param key: settings key
        :param value: new value
        :param validate: validate after the setting operation
        :raises: SettingsError if the setting isn't valid
        """
        tmp = copy.deepcopy(self.prefs)
        path = key.split("/")
        self._set(path, value)
        if validate:
            res = self._validate_settings_dict(self.prefs, "settings with new setting ({}={!r})".format(key, value))
            if not res:
                self.prefs = tmp
                raise SettingsError(str(res))
        self._setup()

    def __setitem__(self, key: str, value):
        """
        Alias for self.set(key, value).
        """
        self.set(key, value)

    def validate_key_path(self, path: t.List[str]) -> bool:
        """
        Validates a path into in to the settings trees,
        :param path: list of sub keys
        :return: Is this key path valid?
        """
        if self.is_obsolete(path):
            return True
        tmp = self.prefs
        for item in path:
            if item not in tmp:
                return False
            tmp = tmp[item]
        return True

    def has_key(self, key: str) -> bool:
        """ Does the passed key exist? """
        return self.validate_key_path(key.split("/"))

    def _set_default(self, path: t.List[str], value):
        """
        Set the default value of the setting with the passed path

        :param path: passed key path
        :param value: new default value
        """
        self.modify_type_scheme("/".join(path), lambda t: t // Default(value))
        self._update_doc()

    def modify_setting(self, key: str, type_scheme: Type):
        """
        Modifies the setting with the given key and adds it if it doesn't exist.

        :param key: key of the setting
        :param type_scheme: Type of the setting
        :param default_value: default value of the setting
        :raises: SettingsError if the settings domain (the key without the last element) doesn't exist
        :raises: TypeError if the default value doesn't adhere the type scheme
        """
        if self.is_obsolete(key):
            logging.info("Using obsolete setting {!r}: {}".format(key, self.obsoleteness_reason(key)))
            return
        path = key.split("/")
        domain = "/".join(path[:-1])
        if len(path) > 1 and not self.validate_key_path(path[:-1]) \
                and not isinstance(self.get(domain), dict):
            raise SettingsError("Setting domain {} doesn't exist".format(domain))
        tmp_typ = self.type_scheme
        tmp_prefs = self.prefs
        for subkey in path[:-1]:
            tmp_typ = tmp_typ[subkey]
            tmp_prefs = tmp_prefs[subkey]
        tmp_typ[path[-1]] = type_scheme
        if path[-1] in tmp_prefs:
            if type_scheme.typecheck_default:
                typecheck(tmp_prefs[path[-1]], type_scheme)
            tmp_typ[path[-1]] = type_scheme
        else:
            tmp_prefs[path[-1]] = type_scheme.get_default()

    def get_type_scheme(self, key: str) -> Type:
        """
        Returns the type scheme of the given key.

        :param key: given key
        :return: type scheme
        :raises: SettingsError if the setting with the given key doesn't exist
        """
        if not self.validate_key_path(key.split("/")):
            raise SettingsError("Setting {} doesn't exist".format(key))
        tmp_typ = self.type_scheme
        for subkey in key.split("/"):
            tmp_typ = tmp_typ[subkey]
        return tmp_typ

    def modify_type_scheme(self, key: str, modificator: t.Callable[[Type], Type]):
        """
        Modifies the type scheme of the given key via a modificator function.

        :param key: given key
        :param modificator: gets the type scheme and returns its modified version
        :raises: SettingsError if the setting with the given key doesn't exist
        """
        if self.is_obsolete(key):
            return
        if not self.validate_key_path(key.split("/")):
            raise SettingsError("Setting {} doesn't exist".format(key))
        tmp_typ = self.type_scheme
        subkeys = key.split("/")
        for subkey in subkeys[:-1]:
            tmp_typ = tmp_typ[subkey]
        tmp_typ[subkeys[-1]] = modificator(tmp_typ[subkeys[-1]])
        assert isinstance(tmp_typ[subkeys[-1]], Type)

    def default(self, value: t.Optional[t.Any], key: str):
        """
        Returns the passed value if isn't None else the settings value under the passed key.

        :param value: passed value
        :param key: passed settings key
        """
        if value is None:
            return self[key]
        typecheck(value, self.get_type_scheme(key))
        return value

    def store_into_file(self, file_name: str):
        """
        Stores the current settings into a yaml file with comments.

        :param file_name: name of the resulting file
        """
        with open(file_name, "w") as f:
            print(self.type_scheme.get_default_yaml(defaults=self.prefs), file=f)

    def has_log_level(self, level: str) -> bool:
        """
        Is the current log level the passed level?

        :param level: passed level (in ["error", "warn", "info", "debug"])
        """
        levels = ["error", "warn", "info", "debug"]
        return levels.index(level) <= levels.index(self["log_level"])

    def is_obsolete(self, key: t.Union[str, t.List[str]]) -> bool:
        """
        Is the setting with the passed key obsolete?

        :param key: key or key path
        :return: obsolete setting?
        """
        return self.obsoleteness_reason(key) is not None

    def obsoleteness_reason(self, key: t.Union[str, t.List[str]]) -> t.Optional[Obsolete]:
        """
        Returns the obsolete type object for obsolete settings

        :param key: key or path
        :return: object that contains information on the obsoleteness or None
        """
        path = key.split("/") if isinstance(key, str) else key
        tmp_type = self.type_scheme
        for subkey in path[:-1]:
            if tmp_type.is_obsolete(subkey):
                return tmp_type.obsoleteness_reason(subkey)
            if subkey not in tmp_type:
                return None
            if isinstance(tmp_type[subkey], Obsolete):
                return tmp_type[subkey]
            tmp_type = tmp_type[subkey]
        if path[-1] in tmp_type and isinstance(tmp_type[path[-1]], Obsolete):
            return tmp_type[subkey]
        return None
