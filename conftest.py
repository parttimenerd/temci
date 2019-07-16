import py
from py.path import local


def pytest_ignore_collect(path: py.path.local):
    return "misc" in str(path) or "/doc/" in str(path) or "library_init" in str(path) or "cli" in str(path)
