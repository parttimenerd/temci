"""
The methods in this module provide an easy way to create packages.
"""
import os
import typing as t
from pprint import pprint

import time

from temci.package.util import normalize_path
from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.package.database import Database
from temci.package.action import Actions, Action, CopyFile, ExecuteCmd, actions_for_dir_path, copy_tree_actions, \
    RequireRootPrivileges, Sleep, RequireDistribution, InstallPackage, UninstallPackage, RequireDistributionRelease

actions = Actions()

def dry_run():
    Settings()["package/dry_run"] = True

def _store_in_db(db: Database = None):
    """
    Store all actions (and their dependencies) in the passed database.
    :param db: passed database or None if the default database should be used
    """
    typecheck_locals(db=Optional(T(Database)))
    db = db or Database()
    actions.store_all_in_db(db)


def store(package_file: str, db: Database = None):
    """
    Stores all actions and the database into the passed file and cleans up the temporary directory.
    :param package_file: name of the passed file
    :param db: passed database or None if the default database should be used
    """
    typecheck_locals(package_file=FileName(), db=Optional(T(Database)))
    db = db or Database()
    _store_in_db(db)
    db.store(package_file)
    db.clean()


def load(package_file: str, db: Database = None) -> Database:
    typecheck_locals(package_file=FileName(allow_non_existent=False))
    db = db or Database()
    db.load(package_file)
    global actions
    actions = Actions()
    actions.load_from_db(db)
    return db


def run(package_file: str, reverse_file: str = None):
    """
    Execute the package and create a package that can be executed afterwards that reverses (most of the) made changes.
    """
    reverse_file = reverse_file or Settings()["package/reverse_file"]
    db = load(package_file)
    rev_db = Database()
    actions.reverse_and_store_all_in_db(rev_db)
    rev_db.store(reverse_file)
    rev_db.clean()
    actions.execute_all(db)


def execute(package_file: str):
    """
    Execute the package (without creating a reverse package).
    """
    db = load(package_file)
    actions.execute_all(db)


def IncludeFile(filename: str) -> t.List[Action]:
    """
    Include the file with the given name.
    :param filename: given name
    """
    typecheck_locals(filename=FileName(allow_non_existent=False))
    ret = []
    ret.extend(actions_for_dir_path(filename))
    ret.append(CopyFile(normalize_path(filename)))
    return ret


def IncludeTree(base_dir: str, include_pattern: t.Union[t.List[str], str] = ["**", "**/.*"],
                      exclude_patterns: t.List[str] = None) -> t.List[Action]:
    typecheck_locals(base_dir=DirName(), include_pattern=List(Str())|Str(), exclude_patterns=Optional(List(Str())))
    return copy_tree_actions(base_dir, include_pattern, exclude_patterns)


if __name__ == "__main__":
    actions << InstallPackage("ls") \
        << IncludeTree(".") \
        << ExecuteCmd("temci short exec -wd 'ls'") \
        << ExecuteCmd("temci report run_output.yaml")
    store("package.tar.xz")
    dry_run()
    #include_file("dsl.py")
    #t = time.time()
    #include_tree(".", exclude_patterns=["*.pyc"])
    #command("bla")
    #actions << RequireRootPrivileges() << Sleep(1) << RequireDistributionRelease() \
    #    << InstallPackage("bf") << InstallPackage("vim")
    #pprint(actions.serialize())
    #actions.execute_all(Database())
    #actions.d
    #print(time.time() - t)
    #store("bla.tar.xz")
    #print(time.time() - t)
    #db = load("bla.tar.xz")
    #reversed_actions = execute(db)
    #pprint(reversed_actions.serialize())
    #print(time.time() - t)
