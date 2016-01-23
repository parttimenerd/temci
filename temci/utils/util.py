import os
import subprocess
import typing as t

import sys


def recursive_exec_for_leafs(data: dict, func, _path_prep=[]):
    """
    Executes the function for every leaf key (a key without any sub keys) of the data dict tree.
    :param data: dict tree
    :param func: function that gets passed the leaf key, the key path and the actual value
    """
    if not isinstance(data, dict):
        return
    for subkey in data.keys():
        if type(data[subkey]) is dict:
            recursive_exec_for_leafs(data[subkey], func, _path_prep=_path_prep + [subkey])
        else:
            func(subkey, _path_prep + [subkey], data[subkey])


def ensure_root(reason: str):
    """
    Throws an error if the user has no root privileges.
    :param reason: why do you need root privileges? To improve the error message.
    :raises EnvironmentError if the current user has no root privileges.
    """
    proc = subprocess.Popen(["/usr/bin/sudo", "-n", "/usr/bin/id"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.communicate()
    if proc.poll() > 0:
        raise EnvironmentError("This program needs to be run with super user privileges: " + reason)


def get_cache_line_size(cache_level: int = None) -> t.Optional[int]:
    """
    Returns the cache line size of the cache on the given level.
    Level 0 and 1 are actually on the same level.
    :param cache_level: if None the highest level cache is used
    :return: cache line size or none if the cache on the given level doesn't exist
    """
    if cache_level is None:
        cache_level = -1
        for path in os.listdir("/sys/devices/system/cpu/cpu0/cache/"):
            if path.startswith("index"):
                cache_level = max(cache_level, int(path.split("index")[1]))
        if cache_level == -1:
            return None
    level_dir = "/sys/devices/system/cpu/cpu0/cache/index" + str(cache_level)
    with open(level_dir + "/coherency_line_size") as f:
        return int(f.readline().strip())


def join_strs(strs: t.List[str], last_word: str = "and") -> str:
    """
    Joins the passed strings together with ", " except for the last to strings that separated by the passed word.
    """
    if len(strs) == 1:
        return strs[0]
    elif len(strs) > 1:
        return " {} ".format(last_word).join([", ".join(strs[0:-1]), strs[-1]])

allow_all_imports = False

def can_import(module: str) -> bool:
    """
    Can a module (like scipy or numpy) be imported without a severe and avoidable performance penalty?
    :param module: name of the module
    """
    if allow_all_imports:
        return True
    if module not in ["scipy", "numpy"]:
        return True
    if len(sys.argv) == 1 or sys.argv[1] in ["completion", "version"]:
        return False
    return True


class Singleton(type):
    """ Singleton meta class.
    See http://stackoverflow.com/a/6798042
    """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class InsertionTimeOrderedDict:
    """
    It's a dict which's elements are sorted by their insertion time.
    """

    def __init__(self):
        self._dict = {}
        self._keys = []
        dict()

    def __delitem__(self, key):
        del(self._dict[key])
        del(self._keys[self._keys.index(key)])

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        self._dict[key] = value
        self._keys.append(key)

    def __iter__(self):
        return self._keys.__iter__()

    def values(self) -> t.List:
        return [self._dict[key] for key in self._keys]

    def keys(self) -> t.List:
        return self._keys

    def __len__(self):
        return len(self._keys)