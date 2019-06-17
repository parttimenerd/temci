import inspect
import os
import typing as t

import shutil

import subprocess

import time
try:
    import yaml
except ImportError:
    import pureyaml as yaml
import logging

from temci.package.util import abspath, normalize_path, hashed_name_of_file
from temci.utils.mail import send_mail
from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.utils.util import has_root_privileges, get_distribution_name, join_strs, get_distribution_release, \
    does_command_succeed

Key = t.Union[str, 'Action']
KeySubKey = t.Tuple[Key, str]
FileId = str

class Database:
    """
    A database that can store files and other data and can be stored in a compressed archive.
    """

    _entry_types = {
        "any": Dict(unknown_keys=True)
    }  # type: t.Dict[str, Dict]

    def __init__(self, data: t.Dict[str, t.Dict[str, Any]] = None, tmp_dir: str = None):
        """
        Creates an instance.

        :param data: data per entry type
        :param tmp_dir: temporary directory to temporary store all included files in
        """
        self.tmp_dir = tmp_dir or os.path.join(Settings()["tmp_dir"], "package" + str(time.time()))  # type: str
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
        os.mkdir(self.tmp_dir)
        self._data_yaml_file_name = os.path.join(self.tmp_dir, "data.yaml")  # type: str
        self._data = data or {}  # type: t.Dict[str, t.Dict[str, Any]]

    def __setitem__(self, key: t.Union[Key, KeySubKey], value: dict):
        key, subkey = self._key_subkey(key, normalize=False)
        key_n = self._normalize_key(key)
        if key_n not in self._data:
            #from temci.package.action import Action
            self._data[key_n] = {
                "value": {},
                "entry_type": "any"
            }
            if not isinstance(key, str):
                if key.name not in self._entry_types:
                    self.add_entry_type(key.name, key.db_entry_type)
                self._data[key_n]["entry_type"] = key.name
                if key.db_entry_type.has_default():
                    self._data[key_n]["value"] = key.db_entry_type.get_default()
        entry_type = self._entry_types[self._data[key_n]["entry_type"]]
        if subkey:
            typecheck_locals(value=entry_type[subkey])
            self._data[key_n]["value"][subkey] = value
        else:
            val = entry_type.get_default() if entry_type.has_default() else {}
            val.update(value)
            typecheck(val, entry_type)
            self._data[key_n]["value"] = val

    def __getitem__(self, key: t.Union[Key, KeySubKey]):
        key, subkey = self._key_subkey(key)
        if subkey:
            return self._data[key]["value"][subkey]
        return self._data[key]["value"]

    def store_file(self, key: Key, subkey: str, file_path: str):
        """
        Stores a file in the database and stores the files id under the passed key as an string.
        It uses the hashed (sha512 + md5) file contents as the id. A file can't be deleted by storing
        another file under the same key.

        :param key: passed key
        :param file_path: path of the file to store
        """
        file_path = abspath(file_path)
        typecheck_locals(file_path=FileName())
        file_id = hashed_name_of_file(file_path)
        shutil.copy(file_path, self._storage_filename(file_id))
        self[key, subkey] = file_id

    def retrieve_file(self, key: Key, subkey: str, destination: str):
        """
        Copies the stored file under the passed key to its new destination.
        """
        destination = abspath(destination)
        source = self._storage_filename(self[key, subkey])
        shutil.copy(source, destination)

    def _storage_filename(self, id: FileId) -> str:
        return os.path.join(self.tmp_dir, id)

    def _store_yaml(self):
        with open(self._data_yaml_file_name, "w") as f:
            yaml.dump(self._data, f)

    def _load_yaml(self):
        with open(self._data_yaml_file_name, "r") as f:
            self._data = yaml.safe_load(f)

    def store(self, filename: str, compression_level: int = None):
        """
        Store the whole database as a compressed archive under the given file name.

        :param filename: passed file name
        :param compression_level: used compression level, from -1 (low) to -9 (high)
        """
        compression_level = compression_level or Settings()["package/compression/level"]
        self._store_yaml()
        filename = abspath(filename)
        used_prog = "gzip"
        av_programs = ["pixz", "xz"] if Settings()["package/compression/program"] == "xz" else ["pigz", "gzip"]
        for prog in av_programs:
            if does_command_succeed(prog + " --version"):
                used_prog = prog
                break
        cmd = "cd {dir}; XZ={l} GZIP={l} tar cf '{dest}' . --use-compress-program={prog}"\
            .format(l=compression_level, dest=filename, dir=self.tmp_dir, prog=used_prog)
        res = subprocess.check_output(["/bin/sh", "-c", cmd])

    def load(self, filename: str):
        """
        Cleans the database and then loads the database from the compressed archive.

        :param filename: name of the compressed archive
        """
        os.system("tar xf '{file}' -C '{dest}'".format(file=abspath(filename), dest=self.tmp_dir))
        self._data.clear()
        self._load_yaml()

    def clean(self):
        """
        Removes the used temporary directory.
        """
        shutil.rmtree(self.tmp_dir)

    @classmethod
    def _key_subkey(cls, key: KeySubKey, normalize: bool = True) -> t.Tuple[str, str]:
        def norm(key: Key):
            return cls._normalize_key(key) if normalize else key
        if isinstance(key, tuple):
            return norm(key[0]), key[1]
        return norm(key), None

    @classmethod
    def add_entry_type(cls, key: str, entry_type: Type):
        """
        Add another entry type.

        :param key: name of this entries type
        :param entry_type: type of this entry
        """
        #typecheck_locals(entry_type=T(Dict))
        cls._entry_types[key] = entry_type

    @classmethod
    def _normalize_key(cls, key: Key) -> str:
        #from temci.package.action import Action
        if not isinstance(key, str):
            return key.id
        return key


class ActionRegistry:

    registered = {}  # type: t.Dict[str, type]
    """ Registered action types """

    @classmethod
    def action_for_config(cls, id: str, action_name: str, config: t.Dict[str, t.Any]) -> 'Action':
        """
        Create an action suited for the passed arguments.

        :param id: id of the created action
        :param action_name: name of the action type
        :param config: configuration of the action
        :return: created action
        """
        assert action_name in cls.registered
        action_class = cls.registered[action_name]
        cfg = action_class.config_type.get_default() if action_class.config_type.has_default() else {}
        cfg.update(config)
        action = action_class(**cfg)
        action.id = id
        return action

    @classmethod
    def add_action_class(cls, action_class: type):
        """
        Add an action type.

        :param action_class: action class, has to be a sub class of Action
        """
        #assert issubclass(action_class, Action)
        config_type = action_class.config_type
        typecheck_locals(config_type=T(Dict))
        has_default = config_type.has_default()
        cls.registered[action_class.name] = action_class


def register_action(cls: type) -> type:
    """
    Decorator to register an action type in the ActionRegistry and the Database.

    :param cls: class to register.
    :return: passed class
    """
    ActionRegistry.add_action_class(cls)
    Database.add_entry_type(cls.name, cls.db_entry_type)
    return cls


class Actions:
    """
    Deduplicating list of actions that can execute methods on all actions.
    """

    def __init__(self, actions: t.List['Action'] = None):
        """
        Creates an instance.

        :param actions: included actions
        """
        self.actions = []  # type: t.List['Action']
        """ Included actions """
        self._action_reprs = set()  # type: t.Set[str]
        """ String representations of all included actions used for deduplication """
        if actions:
            for action in actions:
                self.add(action)

    def load_from_config(self, config: t.List[t.Dict[str, t.Any]]):
        """
        Load actions from the passed list.

        :param config: passed list of dictionaries that represent actions
        """
        typecheck_locals(config=List(Dict({"id": Str(), "action": Str(), "config": Dict(key_type=Str(), unknown_keys=True)})))
        for conf in config:
            self.add(ActionRegistry.action_for_config(conf["id"], conf["action"], conf["config"]))

    def load_from_file(self, file: str):
        """
        Load the actions from the passed file.

        :param file: name of the passed file
        """
        with open(file, "r") as f:
            self.load_from_config(yaml.safe_load(f))

    def store_all(self, db: Database):
        """
        Stores all actions data in the passed database.

        :param db: passed database
        """
        for action in self.actions:
            action.store(db)

    def execute_all(self, db: Database):
        """
        Executes all actions using the passed database.

        :param db: passed database
        """
        for action in self.actions:
            action.execute(db)

    def _reverse_all(self) -> 'Actions':
        actions = []
        for action in self.actions:
            actions.extend(action.reverse())
        return Actions(actions)

    def reverse_and_store_all_in_db(self, new_db: Database) -> 'Actions':
        """
        Create the reverse actions for all actions and store their data in the passed database.

        :param new_db: passed database
        :return: Actions instance containing the newly created actions
        """
        actions = self._reverse_all()
        actions.store_all_in_db(new_db)
        return actions

    def serialize(self) -> t.List[t.Dict[str, t.Any]]:
        """
        Serialize this instance into a data structure that is processable by the ``load_from_dict`` method.

        :return: serialization of this instance
        """
        ret = []
        for action in self.actions:
            ret.append({
                "id": action.id,
                "action": action.name,
                "config": self._serialize_action(action, exclude_id=True)
            })
        return ret

    def _serialize_action(self, action: 'Action', exclude_id: bool) -> str:
        properties = vars(action)
        ret = {}
        for key in properties:
            if key == "id" and exclude_id:
                continue
            if not key.startswith("_"):
                ret[key] = properties[key]
        return ret

    def store_in_file(self, filename: str):
        """
        Store the serialization of this instance in the YAML format in the passed file.

        :param filename: name of the passed file
        """
        with open(filename, "w") as f:
            yaml.dump(self.serialize(), f)

    def store_in_db(self, db: Database):
        """
        Serializes this instance into a file and includes this file in the passed database.

        :param db: passed database
        """
        filename = os.path.join(Settings()["tmp_dir"], "actions.yaml")
        self.store_in_file(filename)
        db.store_file("actions", "file", filename)
        os.remove(filename)

    def store_all_in_db(self, db: Database):
        """
        Stores this instance and all actions data into the passed database.

        :param db: passed database
        """
        self.store_in_db(db)
        self.store_all(db)

    def load_from_db(self, db: Database):
        """
        Load the actions from the passed database.

        :param db: passed database
        """
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
            action_repr = repr([action.name, self._serialize_action(action, exclude_id=True)])
            if action_repr not in self._action_reprs:
                self.actions.append(action)
                self._action_reprs.add(action_repr)

    def __lshift__(self, action: t.Union['Action', t.List['Action']]) -> 'Actions':
        """
        Like ``add(…)`` but returns the actions object.

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
    db_entry_type = Dict(unknown_keys=True)
    """ Type of the database entry. """
    config_type = Dict(unknown_keys=True)
    """ Type of the configuration. """
    _id_counter = 0  # type: int


    def __init__(self):
        """
        Creates a new base action.
        """
        self.id = self._id_counter  # type: int
        """ Id of this action """
        self._id_counter += 1

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

        :return: reverse action
        """
        return []

    def typecheck(self):
        """
        Check that the own properties not starting with ``_`` and excluding the ``id``` property
        match the ``config_type``.

        :raises TypeError: if the check fails
        """
        typecheck(self.serialize(exclude_id=True), self.config_type)

    def _fail(self, message: str):
        """
        Fail with the given error message and send an error mail if configured to do so

        :param message: given error message
        """
        logging.error(message)
        send_mail(Settings()["package/send_mail"], "Error", message)
        exit(1)

    def _exec(self, cmd: str, fail_on_error: bool = False,
              error_message: str = "Failed executing {cmd!r}: out={out!r}, err={err!r}",
              timeout: int = 10) -> bool:
        """
        Execute the passed command.

        :param cmd:
        :param fail_on_error:
        :param error_message: error message format
        :param timeout: time in seconds after which the command is aborted
        :return: Was the command executed successfully?
        """
        out_mode = subprocess.PIPE if fail_on_error else subprocess.DEVNULL
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=out_mode, stderr=out_mode,
                                universal_newlines=True)
        out, err = proc.communicate(timeout=timeout)
        if proc.wait() > 0:
            if fail_on_error:
                self._fail(error_message.format(cmd=cmd, out=out, err=err))
            else:
                return False
        return True


def copy_tree_actions(base: str, include_patterns: t.Union[t.List[str], str] = ["**", "**/.*"],
                      exclude_patterns: t.List[str] = None) -> t.List[Action]:
    """
    Actions for all files and directories in the base directory that match the given patterns.
    It's used to copy a whole directory tree.

    :param base: base directory
    :param include_pattern: patterns that match the paths that should be included
    :param exclude_patterns: patterns that match the paths that should be excluded
    :return: list of actions
    """
    paths = matched_paths(base, include_patterns, exclude_patterns)
    files = set()  # type: t.Set[str]
    dirs = set()  # type: t.Set[str]
    ret = []  # type: t.List[Action]
    for path in paths:
        ret.extend(actions_for_dir_path(path, path_acc=dirs))
        if os.path.isfile(path) and path not in files:
            files.add(path)
            ret.append(CopyFile(normalize_path(path)))
    return ret


def matched_paths(base: str, include_patterns: t.Union[t.List['str'], str] = ["**", "**/.*"],
                  exclude_patterns: t.List[str] = None) -> t.List[str]:
    """
    All matching paths in base directory and its child directories.

    :param base: base directory
    :param include_patterns: patterns that match the paths that should be included
    :param exclude_patterns: patterns that match the paths that should be excluded
    :return: matching paths
    """
    typecheck_locals(base=str, include_pattern=List(Str())|Str(), exclude_patterns=Optional(List(Str())))
    if isinstance(include_patterns, list):
        ret = []
        for pattern in include_patterns:
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


def actions_for_dir_path(path: str, path_acc: t.Set[str] = set()) -> t.List[Action]:
    """
    Returns a list of actions that is needed to create a folder and its parent folders.

    :param path:
    :param path_acc: paths already examined
    """
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
        ret.append(CreateDir(subpath_norm))
        path_acc.add(subpath_norm)
    return ret


@register_action
class ExecuteCmd(Action):
    """
    Execute a command and mail its output (optional).
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
        """
        Creates an instance.

        :param cmd: command to execute
        :param working_dir: directory in which the command is executed
        :param send_mail: send a mail after the execution of the program?
        :param mail_address: recipient of the mail
        :param mail_header: header of the mail
        """
        super().__init__()
        if send_mail == None:
            send_mail = Settings()["package/send_mail"] != ""
        if mail_address == None:
            mail_address = Settings()["package/send_mail"]
            if mail_address == "":
                mail_address = None
        assert mail_address or not send_mail
        self.cmd = cmd  # type: str
        """ Command to execute """
        self.working_dir = working_dir  # type: str
        """ Directory in which the command is executed """
        self.send_mail = send_mail  # type: bool
        """ Send a mail after the execution of the program? """
        self.mail_address = mail_address  # type: str
        """ Recipient of the mail """
        self.mail_header = mail_header or "Executed command {!r}".format(self.cmd)  # type: str
        """ Header of the mail """
        self.typecheck()

    def _dry_run_message(self) -> str:
       return  "Would execute {!r} in directory {!r}".format(self.cmd, self.working_dir)

    def _execute(self, db: Database):
        logging.info("Execute {!r} in directory {!r}".format(self.cmd, self.working_dir))
        proc = subprocess.Popen(["/bin/sh", "-c", self.cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, cwd=abspath(self.working_dir))
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
        """
        Creates an instance.

        :param source: name of the file to copy
        :param dest: copy destination or None if ``source`` should be used
        """
        super().__init__()
        self.source = source  # type: str
        """ Name of the file to copy """
        self.dest = dest or normalize_path(self.source)  # type: str
        """ Copy destination """
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
        """
        Creates an instance.

        :param file: name of the file to remove
        """
        super().__init__()
        self.file = file  # type: str
        """ Name of the file to remove """
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
        """
        Creates an instance

        :param directory: name of the directory to create
        """
        super().__init__()
        self.directory = directory  # type: str
        """ Name of the directory to create """
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
        """
        Creates an instance.

        :param directory: name of the directory to remove
        """
        super().__init__()
        self.directory = directory  # type: str
        """ Name of the directory to remove """
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
        """
        Creates an instance.

        :param seconds: seconds to sleep
        """
        super().__init__()
        self.seconds = seconds  # type: int
        """ Seconds to sleep """
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
    Require one of the passed linux distributions to be the current distribution.
    """

    name = "require_distribution"
    config_type = Dict({
        "possible_distributions": List(Str())
    })

    def __init__(self, possible_distributions: t.List[str] = [get_distribution_name()]):
        """
        Creates an instance.

        :param possible_distributions: names of the allowed linux distributions
        """
        super().__init__()
        self.possible_distributions = possible_distributions  # type: t.List[str]
        """ Names of the allowed linux distributions """
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
    Require one of the passed linux distributions to be the current distribution. Also require a specific release.
    """

    name = "require_distribution_release"
    config_type = Dict({
        "possible_distributions": List(Tuple(Str(), Str()))
    })

    def __init__(self, possible_distributions: t.List[t.Tuple[str, str]] = [(get_distribution_name(),
                                                                             get_distribution_release())]):
        """
        Creates an instance.

        :param possible_distributions: allowed (distribution, release) tuples
        """
        super().__init__()
        self.possible_distributions = possible_distributions  # type: t.List[t.Tuple[str, str]]
        """ Allowed (distribution, release) tuples """
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
    config_type = Dict({  # type: Type
        "package": Str(),
        "name_in_distros": Dict(unknown_keys=True, key_type=Str(), value_type=Str())
    })
    supported_distributions = ["Ubuntu", "Debian"]  # type: t.List[str]
    """ Supported linux distributions """
    install_cmds = {  # type: t.Dict[str, str]
        "Debian": "yes | apt-get install {}",
        "Ubuntu": "yes | apt-get install {}"
    }
    """ Commands to install a package """
    check_cmds = {  # type: t.Dict[str, str]
        "Debian": "dpkg -s {}",
        "Ubuntu": "dpkg -s {}"
    }
    """ Commands that only succeed if the package is already installed """
    uninstall_cmds = {  # type: t.Dict[str, str]
        "Debian": "yes | apt-get remove {}",
        "Ubuntu": "yes | apt-get remove {}"
    }
    """ Commands to uninstall (or remove) a package """

    def __init__(self, package: str, name_in_distros: t.Dict[str, str] = None):
        """
        Creates an instance.

        :param package: name of the package
        :param name_in_distros: name in each supported linux distribution if it differs
        from the already given name
        """
        super().__init__()
        self.package = package  # type: str
        """ Name of the package """
        self.name_in_distros = name_in_distros or {}  # type: t.Dict[str, str]
        """ Name in each supported linux distribution if it differs from the package name """
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
