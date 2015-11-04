import yaml
import copy
import os, shutil
import click
from .util import recursive_contains, recursive_get, \
    recursive_find_key, recursive_exec_for_leafs, Singleton
from .typecheck import *
from ..model.parser import RevisionListStr, BuildCmdListStr, PathListStr, RunCmdListStr, ReportTupleListStr
from fn import _


class SettingsError(ValueError):
    pass


class Settings(metaclass=Singleton):
    """
    Manages the Settings.
    """

    defaults = {
        "tmp_dir": "/tmp/temci",
        "env": {
            "branch": "auto",
            "revisions": "[branch]",
            "randomize_binary": {
                "enable": True
            },
            "nice": 10
        },
        "stat": {
            "run_cmd": "[..]:['']"
        },
        "report": {

        }
    }

    type_scheme = Dict({
        "tmp_dir": T(str),
        "env": Dict({
            "branch": T(str),
            "revisions": RevisionListStr(),
            "randomize_binary": Dict({
                "enable": BoolLike()
            }),
            "nice": Int(range=range(-19, 19)),
        }),
        "stat": Dict({
            "run_cmd": RunCmdListStr()
        }),
        "report": Dict({

        })
    })

    def __init__(self):
        """
         Inits a Settings singleton object and thereby loads the Settings files.
        It loads the settings files from the app folder (config.yaml) and
        the current working directory (temci.yaml) if they exist.
        :raises SettingsError if some of the settings aren't in the format described via the type_scheme class property
        """
        self.prefs = copy.deepcopy(self.defaults)
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

    def reset(self):
        """
        Resets the current settings to the defaults.
        """
        self.prefs = copy.deepcopy(self.defaults)

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
        conf = "temci.yaml"
        if os.path.exists(conf) and os.path.isfile(conf):
            self.load_file(conf)

    def get(self, key: str):
        """
        Get the setting with the given key.
        :param key: name of the setting
        :return value of the setting
        :raises SettingsError if the setting doesn't exist
        """
        path = key.split("/")
        if not self._validate_key_path(path):
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
        """
        Sets a setting to the passed value (if it exists).
        If the setting has options, setting it sets the boolean option "enable".
        :param key: name of the setting to modify
        :param value: new value of the setting
        :raises SettingsError if the setting doesn't exists
        """
        self._validate_key_path(path)
        if len(path) is 2 and type(self.prefs[path[0]][path[1]]) is dict and "enable" in self.defaults[path[0]][path[1]]:
            self.prefs[path[0]][path[1]]["enable"] = bool(value)
        else:
            tmp = self.prefs
            for key in path[0:-1]:
                tmp = tmp[key]
            tmp[path[-1]] = value

    def set(self, key, value):
        """
        Sets the setting key to the passed new value
        :param key: settings key
        :param value: new value
        :raises SettingsError if the setting isn't valid
        """
        tmp = copy.deepcopy(self.prefs)
        path = key.split("/")
        if self._validate_key_path(path):
            self._set(path, value)
            res = self._validate_settings_dict(self.prefs, "settings with new setting ({}={!r})".format(key, value))
            if not res:
                self.prefs = tmp
                raise SettingsError(str(res))
        else:
            self.prefs = tmp
            raise SettingsError("Setting {} doesn't exist".format(key))
        self._setup()

    def __setitem__(self, key: str, value):
        """
        Alias for self.set(key, value).
        :raises SettingsError if the setting isn't valid
        """
        self.set(key, value)

    def _validate_key_path(self, path: list):
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