import inspect
import os
import typing as t

import shutil

import subprocess

import time
import yaml, copy
from colorlog import logging

from temci.package.util import abspath, normalize_path, _new_id
from temci.utils.mail import send_mail
from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.package.database import Database, FileId
from temci.utils.util import has_root_privileges, get_distribution_name, join_strs, get_distribution_release


class ActionRegistry:

    registered = {}  # type: t.Dict[str, type]


    @classmethod
    def action_for_config(cls, id: str, action_name: str, config: t.Dict[str, t.Any]) -> 'Action':
        assert action_name in cls.registered
        action_class = cls.registered[action_name]
        cfg = action_class.config_type.get_default() if action_class.config_type.has_default() else {}
        cfg.update(config)
        action = action_class(**cfg)
        action.id = id
        return action

    @classmethod
    def add_action_class(cls, action_class):
        config_type = action_class.config_type
        typecheck_locals(config_type=T(Dict))
        has_default = config_type.has_default()
        cls.registered[action_class.name] = action_class


def register_action(cls: type) -> type:
    ActionRegistry.add_action_class(cls)
    Database.add_entry_type(cls.name, cls.db_entry_type)
    return cls


class Actions:

    def __init__(self, actions: t.List['Action'] = None):
        self.actions = []  # type: t.List['Action']
        self.action_reprs = set()  # type: t.Set[str]
        if actions:
            for action in actions:
                self.add(action)

    def load_from_config(self, config: t.List[t.Dict[str, t.Any]]):
        typecheck_locals(config=List(Dict({"id": Str(), "action": Str(), "config": Dict(key_type=Str(), all_keys=False)})))
        for conf in config:
            self.add(ActionRegistry.action_for_config(conf["id"], conf["action"], conf["config"]))

    def load_from_file(self, file: str):
        with open(file, "r") as f:
            self.load_from_config(yaml.load(f))

    def store_all(self, db: Database):
        for action in self.actions:
            action.store(db)

    def execute_all(self, db: Database):
        for action in self.actions:
            action.execute(db)

    def _reverse_all(self) -> 'Actions':
        actions = []
        for action in self.actions:
            actions.extend(action.reverse())
        return Actions(actions)

    def reverse_and_store_all_in_db(self, new_db: Database) -> 'Actions':
        actions = self._reverse_all()
        actions.store_all_in_db(new_db)
        return actions

    def serialize(self) -> t.List[t.Dict[str, t.Any]]:
        ret = []
        for action in self.actions:
            ret.append({
                "id": action.id,
                "action": action.name,
                "config": action.serialize(exclude_id=True)
            })
        return ret

    def store_in_file(self, filename: str):
        with open(filename, "w") as f:
            yaml.dump(self.serialize(), f)

    def store_in_db(self, db: Database):
        filename = os.path.join(Settings()["tmp_dir"], "actions.yaml")
        self.store_in_file(filename)
        db.store_file("actions", "file", filename)
        os.remove(filename)

    def store_all_in_db(self, db: Database):
        self.store_in_db(db)
        self.store_all(db)

    def load_from_db(self, db: Database):
        filename = os.path.join(Settings()["tmp_dir"], "actions.yaml")
        db.retrieve_file("actions", "file", filename)
        self.load_from_file(filename)
        os.remove(filename)

    def add(self, action: t.Union['Action', t.List['Action']]):
        """
        Adds the passed action(s) and ignores base and duplicate actions.
        :param action: passed action(s)
        """
        typecheck_locals(action=T(Action)|List(T(Action)))
        if isinstance(action, list):
            for a in action:
                self.add(a)
        elif not action.name == Action.name:
            action_repr = repr([action.name, action.serialize(exclude_id=True)])
            if action_repr not in self.action_reprs:
                self.actions.append(action)
                self.action_reprs.add(action_repr)

    def __lshift__(self, action: t.Union['Action', t.List['Action']]) -> 'Actions':
        """
        Like add(…) but returns the actions object.
        :param other: action to be added
        :return: self
        """
        self.add(action)
        return self

@register_action
class Action:
    """
    Base action that doesn't do anything.

    Expected workflow:

    Call store
    -> store the database and all somewhere
    -> load everything
    -> call reverse and create the reverse action (call store on it)
    -> call execute
    -> do the stuff you want
    -> call execute on the reverse action
    """

    name = "base"
    db_entry_type = Dict(all_keys=False)
    """ Type of the database entry. """
    config_type = Dict(all_keys=False)
    """ Type of the configuration. """

    def __init__(self):
        """
        Creates a new base action.
        """
        self.id = _new_id()

    def store(self, db: Database):
        """
        Store all valid information (like files) in the database.
        :param db: used database
        """
        pass

    def execute(self, db: Database):
        """
        Execute this action.
        :param db: used database
        """
        if Settings()["package/dry_run"]:
            msg = self._dry_run_message()
            if msg:
                logging.info("{} action: {}".format(self.name, msg))
        else:
            self._execute(db)

    def _execute(self, db: Database):
        pass

    def _dry_run_message(self) -> str:
        return ""

    def reverse(self) -> t.List['Action']:
        """
        Creates an action that reverts the changes made by executing this action.
        :return reverse action
        """
        return []

    def serialize(self, exclude_id: bool = False) -> t.Dict[str, t.Any]:
        properties = vars(self)
        ret = {}
        for key in properties:
            if key == "id" and exclude_id:
                continue
            if not key.startswith("_"):
                ret[key] = properties[key]
        return ret

    def typecheck(self):
        typecheck(self.serialize(exclude_id=True), self.config_type)

    def _fail(self, message: str):
        logging.error(message)
        send_mail(Settings()["package/send_mail"], "Error", message)
        exit(1)

    def _exec(self, cmd: str, fail_on_error: bool = False,
              error_message: str = "Failed executing {cmd}: out={out}, err={err}",
              timeout: int = 10) -> bool:
        out_mode = subprocess.PIPE if fail_on_error else subprocess.DEVNULL
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=out_mode, stderr=out_mode,
                                universal_newlines=True)
        out, err = proc.communicate(timeout=timeout)
        if proc.wait() > 0:
            if fail_on_error:
                self._fail(error_message.format(cmd=repr(cmd), out=repr(out), err=repr(err)))
            else:
                return False
        return True


def copy_tree_actions(base: str, include_pattern: t.Union[t.List[str], str] = ["**", "**/.*"],
                      exclude_patterns: t.List[str] = None) -> t.List[Action]:
    paths = matched_paths(base, include_pattern, exclude_patterns)
    files = set()  # type: t.Set[str]
    dirs = set()  # type: t.Set[str]
    ret = []  # type: t.List[Action]
    for path in paths:
        ret.extend(actions_for_dir_path(path, path_acc=dirs))
        if os.path.isfile(path) and path not in files:
            files.add(path)
            ret.append(CopyFile(normalize_path(path)))
    return ret

def matched_paths(base: str, include_pattern: t.Union[t.List['str']] = ["**", "**/.*"],
                  exclude_patterns: t.List[str] = None) -> t.List[str]:
    typecheck_locals(base=str, include_pattern=List(Str())|Str(), exclude_patterns=Optional(List(Str())))
    if isinstance(include_pattern, list):
        ret = []
        for pattern in include_pattern:
            ret.extend(matched_paths(base, pattern, exclude_patterns))
        return ret
    cwd = os.getcwd()
    os.chdir(abspath(base))
    import glob2, globster
    names = glob2.glob(include_pattern)
    if exclude_patterns:
        exclude_globster = globster.Globster(exclude_patterns)
        names = [x for x in names if not exclude_globster.match(x)]
    names = list(map(abspath, names))
    return names

def actions_for_dir_path(path: str, create: bool = True, path_acc: t.Set[str] = set()) -> t.List[Action]:
    path = abspath(path)
    typecheck_locals(path=FileName(allow_non_existent=False)|DirName(), create=Bool())
    assert os.path.exists(path)
    if path == "" or path == "~":
        return []
    path = normalize_path(path)
    parts = path.split("/")
    ret = []
    for i in range(2 if parts[0] == "~" else 1, len(parts) + 1 if os.path.isdir(abspath(path)) else len(parts)):
        subpath = "/".join(parts[:i])
        subpath_norm = normalize_path(subpath)
        if subpath_norm in path_acc:
            continue
        if create:
            ret.append(CreateDir(subpath_norm))
        else:
            ret.append(RemoveDir(subpath_norm))
        path_acc.add(subpath_norm)
    return ret


@register_action
class ExecuteCmd(Action):
    """
    Execute a command and mail it's output (optional).
    """

    name = "execute_cmd"
    config_type = Dict({
        "cmd": Str() // Default(""),
        "working_dir": Str() // Default(normalize_path(".")),
        "send_mail": Bool() // Default(False),
        "mail_address": Optional(Str()),
        "mail_header": Optional(Str())
    })

    def __init__(self, cmd: str, working_dir: str = normalize_path("."), send_mail: bool = None,
                 mail_address: str = None, mail_header: str = None):
        super().__init__()
        if send_mail == None:
            send_mail = Settings()["package/send_mail"] != ""
        if mail_address == None:
            mail_address = Settings()["package/send_mail"]
            if mail_address == "":
                mail_address = None
        assert mail_address or not send_mail
        self.cmd = cmd
        self.working_dir = working_dir
        self.send_mail = send_mail
        self.mail_address = mail_address
        self.mail_header = mail_header or "Executed command {!r}".format(self.cmd)
        self.typecheck()

    def _dry_run_message(self) -> str:
       return  "Would execute {!r} in directory {!r}".format(self.cmd, self.working_dir)

    def _execute(self, db: Database):
        proc = subprocess.Popen(["/bin/sh", "-c", self.cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, shell=True, cwd=self.working_dir)
        out, err = proc.communicate()
        ret_code = proc.wait()
        if self.send_mail:
            def format_out(out):
                return out.replace("\n", "\n\t")
            content = """
Command: {cmd}
Return code: {ret}
Standard out:
    {out}
Standard Error:
    {err}
            """.format(cmd=self.cmd, ret=ret_code, out=format_out(out), err=format_out(err))
            send_mail(self.mail_address, self.mail_header, content)


@register_action
class CopyFile(Action):

    name = "copy_file"
    config_type = Dict({
        "source": Str(),
        "dest": Str() | NonExistent()
    })
    db_entry_type = Dict({
        "file": T(FileId)
    })

    def __init__(self, source: str, dest: str = None):
        super().__init__()
        self.source = source
        self.dest = dest or normalize_path(self.source)
        self.typecheck()

    def store(self, db: Database):
        db.store_file(self, "file", self.source)

    def _dry_run_message(self) -> str:
        verb = "override" if os.path.exists(abspath(self.dest)) else "create"
        return "Would {} file {!r}".format(verb, self.dest)

    def _execute(self, db: Database):
        db.retrieve_file(self, "file", self.dest)

    def reverse(self) -> t.List[Action]:
        if os.path.exists(abspath(self.dest)):
            return [CopyFile(self.dest)]
        return [RemoveFile(self.dest)]


class RemoveFile(Action):

    name = "remove_file"
    config_type = Dict({
        "file": Str()
    })
    db_entry_type = Dict({
        "old_file": T(FileId)
    })

    def __init__(self, file: str):
        super().__init__()
        self.file = file
        self.typecheck()

    def _dry_run_message(self) -> str:
        if os.path.exists(self.file):
            return "Would remove file {!r}".format(self.file)
        return "Wouldn't remove file {!r} as it doesn't exist".format(self.file)

    def _execute(self, db: Database):
         if os.path.exists(self.file):
            os.remove(abspath(self.file))

    def reverse(self) -> t.List[CopyFile]:
        if os.path.exists(self.file):
            return [CopyFile(self.file)]
        return []


@register_action
class CreateDir(Action):
    """
    Action that creates a directory.
    """
    name = "create_dir"
    config_type = Dict({
        "directory": Str()
    })

    def __init__(self, directory: str):
        super().__init__()
        self.directory = directory
        self.typecheck()

    def _dry_run_message(self) -> str:
        if not os.path.exists(abspath(self.directory)):
            return "Would create directory {!r}".format(self.directory)
        return "Wouldn't create directory {!r} as it already exists".format(self.directory)

    def _execute(self, db: Database):
        if not os.path.exists(abspath(self.directory)):
            os.mkdir(abspath(self.directory))

    def reverse(self) -> t.List['RemoveDir']:
        if os.path.exists(abspath(self.directory)):
            return []
        return [RemoveDir(self.directory)]


@register_action
class RemoveDir(Action):
    """
    Action that removes a directory.
    """

    name = "remove_dir"
    config_type = Dict({
        "directory": Str()
    })

    def __init__(self, directory: str):
        super().__init__()
        self.directory = directory
        self.typecheck()

    def _dry_run_message(self) -> str:
        return "Would remove directory {!r}".format(self.directory)

    def _execute(self, db: Database):
        shutil.rmtree(abspath(self.directory))

    def reverse(self) -> t.List[Action]:
        return copy_tree_actions(self.directory)


@register_action
class RequireRootPrivileges(Action):
    """
    Action that exits temci with an error if root privileges are missing.
    """

    name = "require_root"

    def _dry_run_message(self) -> str:
        return "Would check for root privileges (and {})".format("succeed" if has_root_privileges() else "fail")

    def _execute(self, db: Database):
        if not has_root_privileges():
            self._fail("Root privileges are missing")


@register_action
class Sleep(Action):
    """
    Sleep several seconds. Use it before running any benchmarking command.
    """

    name = "sleep"
    config_type = Dict({"seconds": Optional(NaturalNumber())})

    def __init__(self, seconds: int = Settings()["package/actions/sleep"]):
        super().__init__()
        self.seconds = seconds
        self.typecheck()

    def _dry_run_message(self) -> str:
        return "Would sleep {} seconds".format(self.seconds)

    def _execute(self, db: Database):
        time.sleep(self.seconds)


@register_action
class Sync(Action):
    """
    Write changed file system blocks to disk. Use it before running any benchmarking command.
    """

    name = "sync"

    def _dry_run_message(self) -> str:
        return "Would call write changed blocks to disk"

    def _execute(self, db: Database):
        os.sync()


@register_action
class RequireDistribution(Action):
    """
    Require one of the passed distributions to be the current distribution.
    """

    name = "require_distribution"
    config_type = Dict({
        "possible_distributions": List(Str())
    })

    def __init__(self, possible_distributions: t.List[str] = [get_distribution_name()]):
        super().__init__()
        self.possible_distributions = possible_distributions
        self.typecheck()

    def _unsupported_distribution(self) -> bool:
        return get_distribution_name() not in self.possible_distributions

    def _dry_run_message(self) -> str:
        return "Would check the distribution (and {})".format("fail" if self._unsupported_distribution() else "succeed")

    def _execute(self, db: Database):
        if self._unsupported_distribution():
            self._fail("Unsupported distribution {}, expected {}".format(get_distribution_name(),
                                                                        join_strs(self.possible_distributions, "or")))


@register_action
class RequireDistributionRelease(Action):
    """
    Require one of the passed distributions to be the current distribution. Also require a specific release.
    """

    name = "require_distribution_release"
    config_type = Dict({
        "possible_distributions": List(Tuple(Str(), Str()))
    })

    def __init__(self, possible_distributions: t.List[t.Tuple[str, str]] = [(get_distribution_name(),
                                                                             get_distribution_release())]):
        super().__init__()
        self.possible_distributions = possible_distributions
        self.typecheck()

    def _unsupported_distribution(self) -> bool:
        current_distro = get_distribution_name()
        current_release = get_distribution_release()
        for (distro, release) in self.possible_distributions:
            if distro == current_distro and release == current_release:
                return False
        return True

    def _dry_run_message(self) -> str:
        return "Would check the distribution and the release (and {})".format("fail" if self._unsupported_distribution() else "succeed")

    def _execute(self, db: Database):
        if self._unsupported_distribution():
            expected = join_strs(["{} {} ".format(*l) for l in self.possible_distributions], "or")
            self._fail("Unsupported distribution {} and release {}, expected {}".format(get_distribution_name(),
                                                                                        get_distribution_release(),
                                                                                        expected))


@register_action
class InstallPackage(Action):
    """
    Install a package if it isn't already available.
    Currently only Ubuntu and Debian are supported.
    """

    name = "install_package"
    config_type = Dict({
        "package": Str(),
        "name_in_distros": Dict(all_keys=False, key_type=Str(), value_type=Str())
    })
    supported_distributions = ["Ubuntu", "Debian"]
    """ Supported linux distributions """
    install_cmds = {
        "Debian": "yes | apt-get install {}",
        "Ubuntu": "yes | apt-get install {}"
    }
    """ Commands to install a package """
    check_cmds = {
        "Debian": "dpkg -s {}",
        "Ubuntu": "dpkg -s {}"
    }
    """ Commands that only succeed if the package is already installed """
    uninstall_cmds = {
        "Debian": "yes | apt-get remove {}",
        "Ubuntu": "yes | apt-get remove {}"
    }
    """ Commands to uninstall (or remove) a package """

    def __init__(self, package: str, name_in_distros: t.Dict[str, str] = None):
        super().__init__()
        self.package = package  # type: str
        self.name_in_distros = name_in_distros or {}  # type: t.Dict[str, str]
        pkg = {}
        for distro in self.name_in_distros:
            if distro not in self.supported_distributions:
                logging.warning("Ignore unsupported distribution {}".format(distro))
            else:
                pkg[distro] = self.name_in_distros[distro]
        for distro in self.supported_distributions:
            if distro not in pkg:
                pkg[distro] = package
        self.name_in_distros = pkg
        self.typecheck()
        self._current_distro = get_distribution_name()
        self._current_package_name = self.name_in_distros[self._current_distro]
        self._current_install_cmd = self.install_cmds[self._current_distro].format(self._current_package_name)
        self._current_check_cmd = self.check_cmds[self._current_distro].format(self._current_package_name)
        self._current_uninstall_cmd = self.uninstall_cmds[self._current_distro].format(self._current_package_name)

    def _already_installed(self) -> bool:
        self._fail_on_unsupported_distro()
        return self._exec(self._current_check_cmd)

    def _fail_on_unsupported_distro(self):
        if get_distribution_name() not in self.name_in_distros:
            self._fail("Unsupported distribution {} for package {}".format(get_distribution_name(), self.package))

    def _dry_run_message(self) -> str:
        if not self._already_installed():
            return "Would install package {}".format(self._current_package_name)
        return "Would not install package {} as it's already installed".format(self._current_package_name)

    def _execute(self, db: Database):
        self._fail_on_unsupported_distro()
        if not self._already_installed():
            self._exec(self._current_install_cmd, fail_on_error=True,
                          error_message="Failed installing package {}: cmd={{cmd}}, out={{out}}, err={{err}}"
                                  .format(self._current_package_name))

    def reverse(self) -> t.List['UninstallPackage']:
        if not self._already_installed():
            return [UninstallPackage(package=self.package, name_in_distros=self.name_in_distros)]
        return []


@register_action
class UninstallPackage(InstallPackage):

    name = "uninstall_package"

    def _dry_run_message(self) -> str:
        if self._already_installed():
            return "Would uninstall package {}".format(self._current_package_name)
        return "Would not uninstall package {} as it isn't installed".format(self._current_package_name)

    def _execute(self, db: Database):
        self._fail_on_unsupported_distro()
        if self._already_installed():
            self._exec(self._current_uninstall_cmd, fail_on_error=True,
                          error_message="Failed uninstalling package {}: cmd={{cmd}}, out={{out}}, err={{err}}"
                                  .format(self._current_package_name))

    def reverse(self) -> t.List['UninstallPackage']:
        if self._already_installed():
            return [InstallPackage(package=self.package, name_in_distros=self.name_in_distros)]
        return []
