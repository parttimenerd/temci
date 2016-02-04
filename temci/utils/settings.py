import yaml
import copy
import os, logging
import click
from temci.utils.util import recursive_exec_for_leafs, Singleton
from temci.utils.typecheck import *
import multiprocessing
import typing as t

def ValidCPUCoreNumber():
    return Int(range=range(0, multiprocessing.cpu_count()))

class SettingsError(ValueError):
    pass


class Settings(metaclass=Singleton):
    """
    Manages the Settings.
    """

    type_scheme = Dict({
        "settings_file": Str() // Description("Additional settings file") // Default("")
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
                        // Description("Properties to use for reporting and null hypothesis tests"),
            "uncertainty_range": Tuple(Float(lambda x: x >= 0), Float(lambda x: x >= 0)) // Default((0.05, 0.15))
                        // Description("Range of p values that allow no conclusion.")
        }, all_keys=False),
        "report": Dict({
            #  "reporter": Str() // Default("console") // Description(),
            "in": Str() // Default("run_output.yaml") // Description("File that contains the benchmarking results")
                    // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
        }, all_keys=False),
        "run": Dict({
            "discarded_blocks": NaturalNumber() // Description("First n blocks that are discarded") // Default(2),
            "min_runs": NaturalNumber() // Default(20) // Description("Minimum number of benchmarking runs"),
            "max_runs": NaturalNumber() // Default(100) // Description("Maximum number of benchmarking runs"),
            "runs": Int(lambda x: x >= -1) // Default(-1) // Description("if != -1 sets max and min runs to it's value"),
            "max_time": ValidTimeSpan() // Default("2h") // Description("Maximum time the whole benchmarking should take "
                                                                        "+- time to execute one block."), # in seconds
            "run_block_size": PositiveInt() // Default(5)
                              // Description("Number of benchmarking runs that are done together"),
            "in": Str() // Default("input.exec.yaml")
                  // Description("Input file with the program blocks to benchmark")
                  // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "out": Str() // Default("run_output.yaml") // Description("Output file for the benchmarking results")
                    // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "exec_plugins": Dict({

            }),
            "cpuset": Dict({
                "active": Bool() // Description("Use cpuset functionality?") // Default(True),
                "base_core_number": ValidCPUCoreNumber() // Description("Number of cpu cores for the base "
                                                                 "(remaining part of the) system") // Default(1),
                "parallel": Int(lambda x: x >= -1) // Description("0: benchmark sequential, "
                                                      "> 0: benchmark parallel with n instances, "
                                                      "-1: determine n automatically") // Default(0),
                "sub_core_number": ValidCPUCoreNumber() // Description("Number of cpu cores per parallel running program.")
                                   // Default(1)
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
                         // Description("If not empty, recipient of a mail after the benchmarking finished.")
        }),
        "build": Dict({
            "rand": Dict({
                "heap": NaturalNumber() // Default(0)
                        // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
                "stack": NaturalNumber() // Default(0)
                        // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
                "bss": Bool() // Default(False)
                        // Description("Randomize the bss sub segments?"),
                "data": Bool() // Default(False)
                        // Description("Randomize the data sub segments?"),
                "rodata": Bool() // Default(False)
                        // Description("Randomize the rodata sub segments?"),
                "file_structure": Bool() // Default(False)
                                  // Description("Randomize the file structure.")
            }) // Description("Assembly randomization"),
            "in": Str() // Default("build.yaml") // Description("Input file with the program blocks to build")
                // CompletionHint(zsh=YAML_FILE_COMPLETION_HINT),
            "out": Str() // Default("run.exec.yaml") // Description("Resulting run config file")
        })
    }, all_keys=False)
    config_file_name = "temci.yaml"

    def __init__(self):
        """
         Inits a Settings singleton object and thereby loads the Settings files.
        It loads the settings files from the app folder (config.yaml) and
        the current working directory (temci.yaml) if they exist.
        :raises SettingsError if some of the settings aren't in the format described via the type_scheme class property
        """
        self.prefs = copy.deepcopy(self.type_scheme.get_default())
        res = self._validate_settings_dict(self.prefs, "default settings")
        if not res:
            self.prefs = copy.deepcopy(self.defaults)
            raise SettingsError(str(res))
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

    def reset(self):
        """
        Resets the current settings to the defaults.
        """
        self.prefs = copy.deepcopy(self.type_scheme.get_default())

    def _validate_settings_dict(self, data, description: str):
        """
        Check whether the passed dictionary matches the settings type scheme.

        :param data: passed dictionary
        :param description: short description of the passed dictionary
        :return True like object if valid, else string like object which is the error message
        """
        return verbose_isinstance(data, self.type_scheme, description)

    def load_file(self, file: str):
        """
        Loads the settings from the settings yaml file.
        :param file: path to the file
        :raises SettingsError if the settings file is incorrect or doesn't exist
        """
        tmp = copy.deepcopy(self.prefs)
        try:
            with open(file, 'r') as stream:
                map = yaml.load(stream)

                def func(key, path, value):
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

    def load_from_dir(self, dir: str):
        """
        Loads the settings from the `config.yaml` file inside the passed directory.
        :param dir: path of the directory
        """
        self.load_file(os.path.join(dir, "config.yaml"))

    def load_from_config_dir(self):
        """
        Loads the config file from the application directory (e.g. in the users home folder).
        If it exists.
        """
        conf = os.path.join(click.get_app_dir("temci"), "config.yaml")
        if os.path.exists(conf) and os.path.isfile(conf):
            self.load_file(conf)

    def load_from_current_dir(self):
        """
        Loads the settings from the `temci.yaml` file from the current working directory if it exists.
        """
        if os.path.exists(self.config_file_name) and os.path.isfile(self.config_file_name):
            self.load_file(self.config_file_name)

    def get(self, key: str):
        """
        Get the setting with the given key.
        :param key: name of the setting
        :return value of the setting
        :raises SettingsError if the setting doesn't exist
        """
        path = key.split("/")
        if not self.validate_key_path(path):
            raise SettingsError("No such setting {}".format(key))
        data = self.prefs
        for sub in path:
            data = data[sub]
        return data

    def __getitem__(self, key: str):
        """
        Alias for self.get(self, key).
        """
        return self.get(key)

    def _set(self, path: list, value):
        tmp_pref = self.prefs
        tmp_type = self.type_scheme
        for key in path[0:-1]:
            if key not in tmp_pref:
                tmp_pref[key] = {}
                tmp_type[key] = Dict(all_keys=False, key_type=Str())
            tmp_pref = tmp_pref[key]
            tmp_type = tmp_type[key]
        tmp_pref[path[-1]] = value
        if path[-1] not in tmp_type.data:
            tmp_type[path[-1]] = Any() // Default(value)
        if path == ["settings_file"] and value is not "":
            self.load_file(value)

    def set(self, key, value):
        """
        Sets the setting key to the passed new value
        :param key: settings key
        :param value: new value
        :raises SettingsError if the setting isn't valid
        """
        tmp = copy.deepcopy(self.prefs)
        path = key.split("/")
        self._set(path, value)
        res = self._validate_settings_dict(self.prefs, "settings with new setting ({}={!r})".format(key, value))
        if not res:
            self.prefs = tmp
            raise SettingsError(str(res))
        self._setup()

    def __setitem__(self, key: str, value):
        """
        Alias for self.set(key, value).
        :raises SettingsError if the setting isn't valid
        """
        self.set(key, value)

    def validate_key_path(self, path: list):
        """
        Validates a path into in to the settings trees,
        :param path: list of sub keys
        :return Is this key path valid?
        """
        tmp = self.prefs
        for item in path:
            if item not in tmp:
                return False
            tmp = tmp[item]
        return True

    def has_key(self, key: str) -> bool:
        return self.validate_key_path(key.split("/"))

    def modify_setting(self, key: str, type_scheme: Type):
        """
        Modifies the setting with the given key and adds it if it doesn't exist.
        :param key: key of the setting
        :param type_scheme: Type of the setting
        :param default_value: default value of the setting
        :raises SettingsError if the settings domain (the key without the last element) doesn't exist
        :raises TypeError if the default value doesn't adhere the type scheme
        """
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
        :raises SettingsError if the setting with the given key doesn't exist
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
        :raises SettingsError if the setting with the given key doesn't exist
        """
        if not self.validate_key_path(key.split("/")):
            raise SettingsError("Setting {} doesn't exist".format(key))
        tmp_typ = self.type_scheme
        subkeys = key.split("/")
        for subkey in subkeys[:-1]:
            tmp_typ = tmp_typ[subkey]
        tmp_typ[subkeys[-1]] = modificator(tmp_typ[subkeys[-1]])
        assert isinstance(tmp_typ[subkeys[-1]], Type)

    def get_default_value(self, key: str):
        """
        Returns the default value of the given key.
        :param key: given key
        :return: default value
        :raises SettingsError if the setting with the given key doesn't exist
        """
        if not self.validate_key_path(key.split("/")):
            raise SettingsError("Setting {} doesn't exist".format(key))
        tmp_def = self.defaults
        for subkey in key.split("/"):
            tmp_def = tmp_def[subkey]
        return tmp_def

    def default(self, value, key: str):
        """

        :param value:
        :param key:
        :return:
        """
        if value is None:
            return self[key]
        typecheck(value, self.get_type_scheme(key))
        return value

    def store_into_file(self, file_name):
        """
        Stores the current settings into a yaml file with comments.
        :param file_name: name of the resulting file
        """
        with open(file_name, "w") as f:
            print(self.type_scheme.get_default_yaml(defaults=self.prefs), file=f)

    def has_log_level(self, level: str) -> bool:
        levels = ["error", "warn", "info", "debug"]
        return levels.index(level) <= levels.index(self["log_level"])