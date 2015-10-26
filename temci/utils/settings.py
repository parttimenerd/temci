import yaml
import copy
from .util import recursive_contains, recursive_get, \
    recursive_find_key, recursive_exec_for_leafs, Singleton

class Settings:

    """ Manages the Settings.
    """

    __metaclass__ = Singleton

    defaults = {
        "tmp_dir": "/tmp/temci",
        "env": {
            "randomize_binary": {
                "enable": True
            },
            "nice": "10"
        },
        "stat": {

        },
        "report": {

        }
    }

    prefs = copy.deepcopy(defaults)

    program = None

    _valid_part_programs = ["env", "stat", "report"]

    def __init__(self, program=None):
        """ Inits a Settingss singleton object and thereby loads the Settings files.
        :param program: Name of the part program, this code runs in, e.g. "env", "stat" or "report"
        """
        self.program = program

    def reset(self):
        """ Resets the current settings to the defaults.
        """
        self.prefs = copy.deepcopy(self.defaults)

    def load_file(self, file):
        """
        Loads the settings from the settings yaml file.
        :param file: path to the file
        """
        with open(file, 'r') as stream:
            map = yaml.load(stream)
            def func(key, path, value):
                if key[0] not in self._valid_part_programs or key[0] is self.program:
                    self.set("/".join(path), value)
            recursive_exec_for_leafs(map, func)

    def get(self, key, default=None):
        """ Get the setting with the given key.
        Keys can either be simple identifiers of a setting or "/" separated paths (e.g. "env/tmp_path")
        :param key: name of the Settings
        :param default: if a default value is passed a non existent Settings doesn't throw an error
        :return value of the Settings or default (if passed)
        :raises SettingsError if the Settings is non existent (and no default value is passed)
        """
        try:
            keys = self._key_to_list(key)
            data = self.prefs
            for sub in keys:
                data = data[sub]
            return data
        except SettingsError:
            if default is None:
                raise
            else:
                return default

    def __getitem__(self, key):
        """ Alias for self.get(self, key).
        """
        return self.get(key)

    def set(self, key, value):
        """
        Sets a setting to the passed value (if it exists).
        If the setting has options, setting it sets the boolean option "enable".
        :param key: name of the setting to modify
        :param value: new value of the setting
        :raises SettingsError if the setting doesn't exists
        """
        keys = self._key_to_list(key)
        if len(keys) is 2 and type(self.prefs[keys[0]][keys[1]]) is dict:
            self.prefs[keys[0]][keys[1]]["enable"] = bool(value)
        else:
            data = self.prefs
            for sub in keys[0:-1]:
                data = data[sub]
            data[keys[-1]] = value

    def __setitem__(self, key, value):
        """
        Alias for self.set(key, value).
        """

    def _key_to_list(self, key):
        """
        Converts a Settings key to a valid list of keys for the different levels of the Settings tree
        :param key: Settings key
        :return: list of sub keys
        :raises: SettingsError if the passed key isn't valid or doesn't exist
        """
        keys = key.split("/")
        if len(keys) > 1:
            for k in [keys, ("%s/%s" % (self.program, key)).split("/")]:
                tmp = self.prefs
                for elem in k:
                    if tmp is not None and elem in tmp.keys():
                        tmp = tmp[elem]
                    else:
                        tmp = None
                if tmp is not None:
                    return k
            raise SettingsError("No such Settings %s" % key)
        elif key not in self._valid_part_programs:
            data = {}
            for subkey in self.prefs.keys():
                if subkey not in self._valid_part_programs or subkey is self.program:
                    data[subkey] = self.prefs[subkey]
            if recursive_contains(key, data) > 1:
                raise SettingsError("The key %s is ambiguous." % key)
            path = recursive_find_key(key, data)
            if path is not None:
                return path
        raise SettingsError("No such Settings %s" % key)

    def set_program(self, name):
        """ Set the part program, that is currently run (e.g. "env", "stat" or "report")
        """
        if name not in self._valid_part_programs:
            raise SettingsError("No such part program %s" % name)
        self.program = name

class SettingsError(ValueError):
    pass