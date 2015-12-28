import os
import subprocess


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


def ensure_root():
    proc = subprocess.Popen(["/usr/bin/sudo", "-n", "/usr/bin/id"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.communicate()
    if proc.poll() > 0:
        raise EnvironmentError("This program needs to be run with super user privileges")


def get_cache_line_size(cache_level: int = None) -> int:
    """
    Returns the cache line size of the cache on the given level.
    :param cache_level: if None the highest level cache is used
    :return: cache line size
    """
    if cache_level is None:
        cache_level = 1
        for path in os.listdir("/sys/devices/system/cpu/cpu0/cache/"):
            if path.startswith("index"):
                cache_level = max(cache_level, int(path.split("index")[1]))
    level_dir = "/sys/devices/system/cpu/cpu0/cache/index" + str(cache_level)
    with open(level_dir + "/coherency_line_size") as f:
        return int(f.readline().strip())


class Singleton(type):
    """ Singleton meta class.
    See http://stackoverflow.com/a/6798042
    """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]