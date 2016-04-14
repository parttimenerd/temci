"""
The methods in this module provide an easy way to create packages.
"""
import os
import typing as t

from temci.package.util import normalize_path
from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.package.action import Database, Actions, Action, CopyFile, ExecuteCmd, actions_for_dir_path, copy_tree_actions, \
    RequireRootPrivileges, Sleep, RequireDistribution, InstallPackage, UninstallPackage, RequireDistributionRelease

actions = Actions()

def dry_run():
    """ Set the ``package/dry_run`` setting to true. """
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
    """
    Loads the package file into the passed database.

    :param package_file: name of the used package file
    :param db: used database or None if a new database should be used
    :return: used database
    """
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

    :param package_file: name of the used package file
    :param reverse_file: name of the reverse package file or None if the setting ``package/reverse_file``
    should be used.
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

    :param package_file: file name of the used package
    """
    db = load(package_file)
    actions.execute_all(db)


def IncludeFile(filename: str) -> t.List[Action]:
    """
    Returns the actions to include the file with the given name.

    :param filename: given file name
    :return: created actions
    """
    typecheck_locals(filename=FileName(allow_non_existent=False))
    ret = []
    ret.extend(actions_for_dir_path(filename))
    ret.append(CopyFile(normalize_path(filename)))
    return ret


def IncludeTree(base_dir: str, include_patterns: t.Union[t.List[str], str] = ["**", "**/.*"],
                exclude_patterns: t.List[str] = None) -> t.List[Action]:
    """
    Returns the actions to include the passed directory tree.

    ``*`` in the pattern matches all files in a directory.
    ``**`` matches all directories and sub directories.

    :param base_dir: directory to include
    :param include_patterns: include file patterns
    :param exclude_patterns: exclude file patterns
    :return: created actions
    """
    typecheck_locals(base_dir=DirName(), include_pattern=List(Str())|Str(), exclude_patterns=Optional(List(Str())))
    return copy_tree_actions(base_dir, include_patterns, exclude_patterns)


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
