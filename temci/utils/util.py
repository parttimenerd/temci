"""
Utility functions and classes that don't depend on the rest of the temci code base.
"""

import os
import subprocess
import typing as t

import sys
import logging

import shutil
from rainbow_logging_handler import RainbowLoggingHandler

from temci.utils.typecheck import Type


def recursive_exec_for_leafs(data: dict, func, _path_prep = []):
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


def has_root_privileges() -> bool:
    """
    Has the current user root privileges?
    """
    return does_command_succeed("head /proc/1/stack")


def has_pdflatex() -> bool:
    """
    Is pdflatex installed?
    """
    return does_command_succeed("pdflatex --version")


def does_command_succeed(cmd: str) -> bool:
    """ Does the passed command succeed (when executed by /bin/sh)?  """
    try:
        subprocess.check_call(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except:
        return False
    return True


def warn_for_pdflatex_non_existence_once(_warned = [False]):
    """ Log a warning if the pdflatex isn't available, but only if this function is called the first time """
    if not has_pdflatex() and not _warned[0]:
        logging.warning("pdflatex is not installed therefore no pdf plots are produced")
        _warned[0] = True


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


def get_memory_page_size() -> int:
    """ Returns the size of a main memory page """
    try:
        proc = subprocess.Popen(["/bin/sh", "-c", "getconf PAGESIZE"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        out, err = proc.communicate()
        if proc.poll() == 0:
            return int(out.strip())
    except:
        pass
    return 4096


def get_distribution_name() -> str:
    """ Returns the name of the current linux distribution (requires `lsb_release` to be installed) """
    return subprocess.check_output(["lsb_release", "-i", "-s"], universal_newlines=True).strip()


def get_distribution_release() -> str:
    """ Returns the used release of the current linux distribution (requires `lsb_release` to be installed) """
    return subprocess.check_output(["lsb_release", "-r", "-s"], universal_newlines=True).strip()


def does_program_exist(program: str) -> bool:
    """ Does the passed program exist? """
    return shutil.which(program) is not None


def on_apple_os() -> bool:
    """ Is the current operating system an apple OS X? """
    return sys.platform == 'darwin'


def join_strs(strs: t.List[str], last_word: str = "and") -> str:
    """
    Joins the passed strings together with ", " except for the last to strings that separated by the passed word.

    :param strs: strings to join
    :param last_word: passed word that is used between the two last strings
    """
    if not isinstance(strs, list):
        strs = list(strs)
    if len(strs) == 1:
        return strs[0]
    elif len(strs) > 1:
        return " {} ".format(last_word).join([", ".join(strs[0:-1]), strs[-1]])


allow_all_imports = False  # type: bool
""" Allow all imports (should the can_import method return true for every module)? """


def can_import(module: str) -> bool:
    """
    Can a module (like scipy, numpy or init/prompt_toolkit) be imported without a severe and avoidable
    performance penalty?
    The rational behind this is that some parts of temci don't need scipy or numpy.

    :param module: name of the module
    """
    if sphinx_doc():
        return False
    if allow_all_imports:
        return True
    if module not in ["scipy", "numpy", "init", "prompt_toolkit"]:
        return True
    if in_standalone_mode:
        return False
    if module in ["init", "prompt_toolkit"]:
        return len(sys.argv) >= 2 and sys.argv[1] == "init"
    if len(sys.argv) == 1 or sys.argv[1] in ["completion", "version", "assembler"]:
        return False
    return True


in_standalone_mode = False  # type: bool
""" In rudimentary standalone mode (executed via run.py) """

_sphinx_doc = os.environ.get("SPHINXDOC", os.environ.get('READTHEDOCS', None)) == 'True'

def sphinx_doc() -> bool:
    """ Is the code only loaded to document it with sphinx? """
    return _sphinx_doc


def get_doc_for_type_scheme(type_scheme: Type) -> str:
    """ Return a class documentation string for the given type scheme. Use the default_yaml method. """
    return """

    .. code-block:: yaml

        {default_yaml}

    """.format(default_yaml="\n        ".join(type_scheme.get_default_yaml().split("\n")))


class Singleton(type):
    """
    Singleton meta class.
    @see http://stackoverflow.com/a/6798042
    """
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class InsertionTimeOrderedDict:
    """
    A dictionary which's elements are sorted by their insertion time.
    """

    def __init__(self):
        self._dict = {}
        self._keys = []
        dict()

    def __delitem__(self, key):
        """ Remove the entry with the passed key """
        del(self._dict[key])
        del(self._keys[self._keys.index(key)])

    def __getitem__(self, key):
        """ Get the entry with the passed key """
        return self._dict[key]

    def __setitem__(self, key, value):
        """ Set the value of the item with the passed key """
        if key not in self._dict:
            self._keys.append(key)
        self._dict[key] = value

    def __iter__(self):
        """ Iterate over all keys """
        return self._keys.__iter__()

    def values(self) -> t.List:
        """ Rerturns all values of this dictionary. They are sorted by their insertion time. """
        return [self._dict[key] for key in self._keys]

    def keys(self) -> t.List:
        """ Returns all keys of this dictionary. They are sorted by their insertion time. """
        return self._keys

    def __len__(self):
        """ Returns the number of items in this dictionary """
        return len(self._keys)

    @classmethod
    def from_list(cls, items: t.Optional[list], key_func: t.Callable[[t.Any], t.Any]) -> 'InsertionTimeOrderedDict':
        """
        Creates an ordered dict out of a list of elements.

        :param items: list of elements
        :param key_func: function that returns a key for each passed list element
        :return: created ordered dict with the elements in the same order as in the passed list
        """
        if items is None:
            return InsertionTimeOrderedDict()
        ret = InsertionTimeOrderedDict()
        for item in items:
            ret[key_func(item)] = item
        return ret

#formatter = logging.Formatter("[%(asctime)s] %(name)s %(levelname)s \t%(message)s")
# setup `RainbowLoggingHandler`
handler = RainbowLoggingHandler(sys.stderr, color_funcName=('black', 'yellow', True))
""" Colored logging handler that is used for the root logger """
handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
logging.getLogger().addHandler(handler)


def geom_std(values: t.List[float]) -> float:
    """
    Calculates the geometric standard deviation for the passed values.
    Source: https://en.wikipedia.org/wiki/Geometric_standard_deviation
    """
    import scipy.stats as stats
    import scipy as sp
    gmean = stats.gmean(values)
    return sp.exp(sp.sqrt(sp.sum([sp.log(x / gmean) ** 2 for x in values]) / len(values)))