"""
Utilities for loading plugins.
Plugins are python files (ending `.py`) that are loaded prior to building the cli.
These files may e.g. add runners, plugins, …

Plugins are loaded from the application directory (`~/.temci`) and from the paths given in the
environment variable `TEMCI_PLUGIN_PATH` which contains a colon separated list of paths.
"""
import logging
import os

from typing import List

APP_DIR = os.path.expanduser("~/.temci")


def plugin_paths() -> List[str]:
    """
    Returns the paths that plugins are located in (might return folders and files)
    """
    paths = [APP_DIR]
    path_env = os.getenv("TEMCI_PLUGIN_PATH", "")
    if path_env:
        paths.extend([os.path.expandvars(os.path.expanduser(path)) for path in path_env.split(":")])
    return paths


def load_plugins():
    """
    Load the plugins from the plugin folders
    :return:
    """
    for path in plugin_paths():
        _load_path(path)


def _load_path(path: str):
    if os.path.isfile(path):
        _load_file(path)
    else:
        _load_folder(path)


def _load_folder(folder: str):
    """
    Load the plugins in the passed folder and its sub folders
    """
    if not os.path.exists(folder):
        return
    for (dirpath, dirnames, filenames) in os.walk(folder):
        for file in filenames:
            if file.endswith(".py"):
                _load_file(file)


def _load_file(file: str):
    try:
        exec(open(file).read())
    except BaseException as ex:
        logging.exception(ex)
        raise
