"""
Initialization dialogues for the build and run config files.
"""
import json
import os

import subprocess

import io

try:
    import yaml
except ImportError:
    import pureyaml as yaml
from prompt_toolkit.document import Document
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit import prompt
from prompt_toolkit.layout.lexers import PygmentsLexer
from prompt_toolkit.contrib.completers import WordCompleter, SystemCompleter, PathCompleter
from temci.run.run_driver import ExecRunDriver, PerfStatExecRunner, SpecExecRunner, get_av_perf_stat_properties, \
    ValidPerfStatPropertyList, RusageExecRunner, ValidRusagePropertyList, get_av_rusage_properties, TimeExecRunner, \
    ValidTimePropertyList, get_av_time_properties
from temci.utils.typecheck import *
import typing as t

from temci.utils.util import get_cache_line_size
from temci.utils.vcs import VCSDriver


def is_builtin_type(type, val: str) -> bool:
    """
    Checks whether the passed value is convertable into the given builtin type.

    :param type: builtin type (like int)
    :param val: tested value
    """
    try:
        type(val)
        return True
    except ValueError:
        return False


class TypeValidator(Validator):
    """
    A validator that validates against type schemes.
    """

    def __init__(self, type_scheme: Type, allow_empty: bool = False):
        """
        Creates an instance.

        :param type_scheme: expected type scheme
        :param allow_empty: allow an empty string?
        """
        self.type_scheme = type_scheme  # type: Type
        """ Expected type scheme """
        self.allow_empty = allow_empty  # type: bool
        """ Allow an empty string? """

    def _int_like(self) -> bool:
        return isinstance(self.type_scheme, Int) or self.type_scheme == int

    def _bool_like(self) -> bool:
        return isinstance(self.type_scheme, T(Bool) | T(BoolOrNone))  or self.type_scheme == bool

    def validate(self, document: Document):
        val = document.text

        def raise_error(msg: str = None):
            msg = msg or str(verbose_isinstance(val, self.type_scheme))
            raise ValidationError(message=msg, cursor_position=len(document.text))

        if val == "" and self.allow_empty:
            return

        if self._int_like():
            if not is_builtin_type(int, val):
                raise_error("Isn't a valid integer.")
            else:
                val = int(val)
        elif self._bool_like():
            if not is_builtin_type(bool, val):
                raise_error("Isn't a valid boolean")
            else:
                val = bool(val)
        if not isinstance(val, self.type_scheme):
            raise_error()


class WordValidator(Validator):
    """
    Like the SentenceValidator but accepts only one word.
    """

    def __init__(self, valid_words: t.List[str], ignore_case: bool = True, move_cursor_to_end: bool = False,
                 error_msg: str = None, allow_empty: bool = False):
        """
        Creates an instance.

        :param valid_words: allowed words
        :param ignore_case: ignore the case of the words?
        :param move_cursor_to_end: move the cursor to the end of the current line after the validation?
        :param error_msg: message shown when the validation fails
        :param allow_empty: allow an empty string?
        """
        self.valid_words = valid_words  # type: t.List[str]
        """ Allowed words """
        self.ignore_case = ignore_case  # type: bool
        """ Ignore the case of the words? """
        if ignore_case:
            self.valid_words = [word.lower() for word in self.valid_words]
        self.move_cursor_to_end = move_cursor_to_end  # type: bool
        """ Move the cursor to the end of the current line after the validation? """
        self.error_msg = error_msg  # type: str
        """ Message shown when the validation fails """
        self.allow_empty = allow_empty  # type: bool
        """ Allow an empty string? """

    def validate(self, document: Document):
        text = document.text.lower() if self.ignore_case else document.text
        if text == "" and self.allow_empty:
            return
        if text not in self.valid_words:
            msg = "Invalid word, expected one of these"
            if self.ignore_case:
                msg += " (case is ignored)"
            reprs = list(map(repr, self.valid_words))
            if len(reprs) > 1:
                msg += ":" + " or ".join([", ".join(reprs[:-1]), reprs[-1]])
            else:
                msg = "Invalid word, expected " + reprs[0]
            index = len(text) if self.move_cursor_to_end else 0
            if self.error_msg is not None:
                msg = self.error_msg
            raise ValidationError(message=msg, cursor_position=index)


class NonEmptyValidator(Validator):
    """
    Matches all non empty strings.
    """

    def validate(self, document: Document):
        if document.text == "":
            raise ValidationError(message="The input mustn't be empty")


class RevisionValidator(Validator):
    """
    Matches all valid revision ids.
    """

    def __init__(self, vcs: VCSDriver, allow_empty_string: bool = True):
        """
        Creates an instance.

        :param vcs: used VCSDriver
        :param allow_empty_string: allow an empty string?
        """
        self.vcs = vcs  # type: VCSDriver
        self.allow_empty_string = allow_empty_string  # type: bool
        """ Allow an empty string? """

    def validate(self, document: Document):
        val = document.text
        if val == "" and self.allow_empty_string:
            return
        if is_builtin_type(int, val):
            val = int(val)
        if val == "" or not self.vcs.validate_revision(val):
            raise ValidationError(message="Invalid revision id")


def create_revision_completer(vcs: VCSDriver) -> WordCompleter:
    """
    Creates a WordCompleter for revision ids.

    :param vcs: used vcs driver
    :return: WordCompleter
    """
    valid = []
    meta_dict = {}
    if vcs.has_uncommitted():
        valid.append("HEAD")
        meta_dict["HEAD"] = "Uncommitted changes"
    for info_dict in vcs.get_info_for_all_revisions(max=50):
        commit_number = str(info_dict["commit_number"])
        if not info_dict["is_uncommitted"]:
            valid.append(str(info_dict["commit_id"]))
            msg = info_dict["commit_message"]
            other_branch_str = " from branch " + info_dict["branch"] + "" if info_dict["is_from_other_branch"] else ""
            msg = "Commit no. {commit_number}{other_branch_str}: {msg}".format(**locals())
            meta_dict[info_dict["commit_id"]] = msg
    return WordCompleter(valid, ignore_case=True, meta_dict=meta_dict)


class StrListValidator(Validator):
    """
    Matches comma separated lists of strings that are acceptable python identifiers.
    """

    def __init__(self, allow_empty: bool = False):
        """
        Creates an instance.

        :param allow_empty: allow an empty string?
        """
        self.allow_empty = allow_empty
        """ Allow an empty string? """

    def validate(self, document: Document):
        if document.text == "":
            if self.allow_empty:
                return
            else:
                raise ValidationError("Empty list isn't allowed")

        for elem in document.text.split(","):
            elem = elem.strip()
            if not elem.isidentifier():
                raise ValidationError("{!r} is not a valid entry of this comma separated list")


def prompt_bash(msg: str, allow_empty: bool) -> str:
    """
    Prompts for bash shell code.

    :param msg: shown message
    :param allow_empty: allow an empty string?
    :return: user input
    """
    from pygments.lexers.shell import BashLexer
    validator = None if allow_empty else NonEmptyValidator()
    return prompt(msg, lexer=PygmentsLexer(BashLexer), completer=SystemCompleter())


def prompt_python(msg: str, get_globals: t.Callable[[str], t.Any], get_locals: t.Callable[[str], t.Any]) -> str:
    """
    Prompt for python code.

    :param get_globals: function that returns the global variables
    :param get_locals: function that returns the local variables
    :return: user input
    """
    from ptpython.completer import PythonCompleter
    from pygments.lexers.python import Python3Lexer
    python_completer = PythonCompleter(get_globals, get_locals)
    return prompt(msg, multiline=True, mouse_support=True, lexer=PygmentsLexer(Python3Lexer),
                         completer=python_completer)


def prompt_yesno(msg: str, default: bool = None, meta_dict: t.Dict[str, str] = None) -> bool:
    """
    Prompt for simple yes or no decision.

    :param msg: asked question
    :param default: default value
    :param meta_dict: mapping 'yes' or 'no' to further explanations
    :return: user input converted to bool
    """
    valid_words = ["yes", "no", "y", "n"]
    if default is not None:
        msg += "[" + ("y" if default else "n") + "] "
        valid_words.append("")
    completer = WordCompleter(["yes", "no"], ignore_case=True, meta_dict=meta_dict)
    text = prompt(msg, completer=completer, display_completions_in_columns=True,
                  validator=WordValidator(valid_words, ignore_case=True))
    if text == "":
        return default
    return text.lower().startswith("y")


def message(msg: str, default: t.Optional = None) -> str:
    """
    A utility function to a valid message string with an optional default value.

    :param msg: original message
    :param default: optional default value
    :return: modified message
    """
    if not msg.endswith(" "):
        msg += " "
    if default is not None:
        return msg + "[" + str(default) + "] "
    return msg


def default_prompt(msg: str, default: t.Optional = None, **kwargs):
    """
    Wrapper around prompt that shows a nicer prompt with a default value that isn't editable.
    Interpretes the empty string as "use default value".

    :param msg: message
    :param default: default value
    :param kwargs: arguments passed directly to the prompt function
    :return: user input
    """
    msg = message(msg, default)
    if default is not None and "validator" in kwargs:
        vali = kwargs["validator"]
        if isinstance(vali, TypeValidator):
            vali.allow_empty = True
        if isinstance(vali, WordValidator):
            vali.allow_empty = True
    res = prompt(msg, **kwargs)
    if res == "" and default is not None:
        return default
    return res


def prompt_dir(msg: str) -> str:
    """
    Prompt a directory path. Default is ".".

    :param msg: shown message
    :return: user input
    """
    return default_prompt(msg, default=".", validator=TypeValidator(DirName()),
                          completer=PathCompleter(only_directories=True))


def prompt_attributes_dict(default_description: str = None) -> t.Dict[str, str]:
    """
    Prompts for the contents of the attributes dict.

    :param default_description: default value for the description attribute
    :return: attributes dict
    """
    attributes = {}
    descr_msg = "Give a description for the current block: "
    if default_description is not None:
        attributes["description"] = default_prompt(descr_msg, default_description,
                                                   completer=WordCompleter([default_description]))
    else:
        attributes["description"] = prompt(descr_msg, validator=NonEmptyValidator())
    try:
        while prompt_yesno("Do you want to set or add another attribute? ", default=False):
            name = prompt("Attribute name: ", validator=NonEmptyValidator(),
                          completer=WordCompleter(sorted(list(attributes.keys())), meta_dict=attributes))
            default = attributes[name] if name in attributes else ""
            attributes[name] = prompt("Attribute value: ", default=default, validator=NonEmptyValidator())
    except KeyboardInterrupt:
        pass
    return attributes


def prompt_build_dict(with_header: bool = True, whole_config: bool = True) -> dict:
    """
    Prompts for the contents of the build config dictionary.

    :param with_header: print "Create the  …" header?
    :param whole_config: prompt for the whole build config (with attributes and run config)
    :return: build config dictionary
    """

    if with_header:
        print("Create the build configuration for the program block")
    old_cwd = os.path.realpath(".")
    build_dict = {}
    build_dict["base_dir"] = prompt_dir("Base directory: ")
    os.chdir(build_dict["base_dir"])

    build_dict["working_dir"] = prompt_dir("Working directory (relative to the base dir): ")
    os.chdir(build_dict["working_dir"])
    working_dir_abs = os.path.realpath(".")

    build_dict["build_cmd"] = prompt_bash("Command to build the program: ", allow_empty=True)

    vcs = VCSDriver.get_suited_vcs()
    cur_branch = vcs.get_branch()
    default_description = None
    if cur_branch is not None: # version control system is used
        build_dict["branch"] = default_prompt("Used branch? ", default=cur_branch,
                                              completer=WordCompleter(vcs.get_valid_branches(), meta_dict={
                                                  cur_branch: "Current branch"
                                              }),
                                              validator=WordValidator(vcs.get_valid_branches(),
                                                                      ignore_case=False,
                                                                      error_msg="Invalid branch name"),
                                              display_completions_in_columns=True)
        vcs.set_branch(build_dict["branch"])
        build_dict["revision"] = default_prompt("Revision in this branch: ", default="HEAD",
                                        completer=create_revision_completer(vcs),
                                        validator=RevisionValidator(vcs),
                                        display_completions_in_columns=True)
        if is_builtin_type(int, build_dict["revision"]):
            build_dict["revision"] = int(build_dict["revision"])
        default_description = vcs.get_info_for_revision(build_dict["revision"])["commit_message"]

    rand_dict = dict()
    if prompt_yesno("Randomize program binaries (works with gcc and cparser built programs)? ", default=True):
        meta_dict = {str(get_cache_line_size()): "Current cache line size", "0": "No padding"}
        size_completer = WordCompleter(sorted(list(meta_dict.keys())), meta_dict=meta_dict)
        rand_dict["heap"] = int(default_prompt("Maximum size of the random padding of each heap allocation? ",
                                               default=get_cache_line_size(), completer=size_completer,
                                               validator=TypeValidator(NaturalNumber())))
        #rand_dict["stack"] = int(default_prompt("Maximum size of the random padding of each stack frame? ",
        #                                        default=get_cache_line_size(), completer=size_completer,
        #                                        validator=TypeValidator(NaturalNumber())))
        rand_dict["bss"] = prompt_yesno("Randomize bss segment? ", default=True)
        rand_dict["data"] = prompt_yesno("Randomize data segment? ", default=True)
        rand_dict["rodata"] = prompt_yesno("Randomize rodata segment? ", default=True)
        rand_dict["file_structure"] = prompt_yesno("Randomize the file structure (location of functions)? ",
                                                   default=True)
    if prompt_yesno("Randomize the link order (works with gcc and cparser)?", default=True):
        rand_dict["linker"] = True
    if rand_dict:
        build_dict["randomization"] = rand_dict

    build_dict["number"] = int(prompt("How many times should the program be built? ", validator=TypeValidator(Int())))
    os.chdir(old_cwd)
    if whole_config:
        attributes_dict = prompt_attributes_dict(default_description)
        run_config = prompt_run_dict(working_dir=build_dict["working_dir"], binary_number=build_dict["number"],
                                     whole_config=False, driver="exec")
        return {
            "attributes": attributes_dict,
            "build_config": build_dict,
            "run_config": run_config
        }
    return build_dict


def prompt_run_dict(with_header: bool = True, working_dir: str = None,
                    binary_number: int = None, whole_config: bool = True,
                    driver: str = None) -> dict:
    """
    Prompt the contents of the run config dictionary.

    :param with_header: print the explanation header
    :param working_dir: current working dir preset
    :param binary_number: number of available binaries
    :param whole_config: return the whole run config (with attributes part)?
    :param driver: used run driver
    :return: run config dict
    """
    if with_header:
        print("Create the run configuration for the program block")

    run_drivers = {
        "exec": {
            "func": prompt_exec_driver_dict,
            "description": ExecRunDriver.__description__
        }
    }

    assert driver in run_drivers or driver is None
    if driver is None:
        valid = sorted(list(run_drivers.keys()))
        meta_dict = {}
        for driver in run_drivers:
            meta_dict[driver] = run_drivers[driver]["description"]
        driver = prompt("Used run driver: ", completer=WordCompleter(words=valid, ignore_case=True,
                                                                     meta_dict=meta_dict),
                        validator=WordValidator(ignore_case=False, valid_words=valid,
                                                error_msg="Invalid run driver name"))
    run_dict = run_drivers[driver]["func"](choose_revision=whole_config,
                                           working_dir=working_dir)

    if whole_config:
        attributes_dict = prompt_attributes_dict()
        return {
            "attributes": attributes_dict,
            "run_config": run_dict
        }
    return run_dict


def prompt_exec_driver_dict(choose_revision: bool, working_dir: str = None) -> dict:
    """
    Prompt for the contents of run config dict for suitable for the exec run driver.

    :param choose_revision: can the user choose a specific vcs revision?
    :param working_dir: default working dir for the exec driver
    """
    from pygments.lexers.shell import BashLexer
    old_cwd = os.path.realpath(".")
    working_dir = working_dir or prompt_dir("Working directory: ")
    run_dict = {}
    run_dict["cwd"] = working_dir
    os.chdir(working_dir)
    run_dict["run_cmd"] = prompt_bash("Command to execute the program: ", allow_empty=False)

    if prompt_yesno("Set some environment variables? ", default=False):
        env_dict = {}
        def set_env_var():
            name = prompt("Environment variable name: ", validator=NonEmptyValidator(),
                          completer=WordCompleter(sorted(list(env_dict.keys())), meta_dict=env_dict))
            default = env_dict[name] if name in env_dict else ""
            env_dict[name] = prompt("New value: ", default=default)
        try:
            set_env_var()
            while prompt_yesno("Set another environment variable? "):
                set_env_var()
        except KeyboardInterrupt:
            pass
        run_dict["env"] = env_dict

    if choose_revision:
        vcs = VCSDriver.get_suited_vcs()
        if vcs.number_of_revisions() + int(vcs.has_uncommitted()) > 1:
            run_dict["revision"] = default_prompt("Choose a revision in the current repository: ", default="HEAD",
                                    completer=create_revision_completer(vcs),
                                    validator=RevisionValidator(vcs),
                                    display_completions_in_columns=True)
            if is_builtin_type(int, run_dict["revision"]):
                run_dict["revision"] = int(run_dict["revision"])

    if prompt_yesno("Run some commands before that actually benchmarked command? ", default=False):
        print("The commands are entered via a multiline input. ")
        print("Press [Meta+Enter] or [Esc] followed by [Enter] to accept input.")
        print("You can click with the mouse in order to select text.")
        run_dict["cmd_prefix"] = prompt('', multiline=True, mouse_support=True, lexer=PygmentsLexer(BashLexer),
                        completer=SystemCompleter())

    runners = {
        "perf_stat": {
            "func": prompt_perf_stat_exec_dict,
            "description": PerfStatExecRunner.__description__,
        },
        "rusage": {
            "func": prompt_rusage_exec_dict,
            "description": RusageExecRunner.__description__,
        },
        "spec": {
            "func": prompt_spec_exec_dict,
            "description": SpecExecRunner.__description__
        },
        "time": {
            "func": prompt_time_exec_dict,
            "description": TimeExecRunner.__description__
        }
    }

    valid = sorted(list(runners.keys()))
    meta_dict = {}
    for driver in runners:
        meta_dict[driver] = runners[driver]["description"]
    driver = prompt("Used runner: ", completer=WordCompleter(words=valid, ignore_case=True,
                                                                 meta_dict=meta_dict),
                    validator=WordValidator(ignore_case=False, valid_words=valid, error_msg="Invalid runner"),
                    display_completions_in_columns=True)
    run_dict["runner"] = driver
    run_dict[driver] = runners[driver]["func"](run_dict)
    os.chdir(old_cwd)
    return run_dict


def prompt_perf_stat_exec_dict(run_dict: dict) -> dict:
    """
    Prompt for the config of the perf stat exec runner.

    :param run_dict: run config dict (without the runner part)
    :return: runner config
    """
    runner_dict = {}
    default_repeat = PerfStatExecRunner.misc_options["repeat"].get_default()
    runner_dict["repeat"] = int(default_prompt("How many times should perf stat itself repeat the measurement? ",
                                               default=default_repeat, validator=TypeValidator(PositiveInt())))
    default_props = ", ".join(PerfStatExecRunner.misc_options["properties"].get_default())

    class PerfStatPropertiesValidator(Validator):

        def validate(self, document: Document):
            vals = [elem.strip() for elem in document.text.split(",")]
            cmd = "perf stat -x ';' -e {props} -- /bin/echo".format(props=",".join(vals))
            proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, universal_newlines=True)
            out, err = proc.communicate()
            if proc.poll() > 0:
                msg = str(err).split("\n")[0].strip()
                raise ValidationError(message=msg, cursor_position=len(document.text))

    props = prompt("Which properties should perf stat measure? ",
                   validator=PerfStatPropertiesValidator(), default=default_props,
                   completer=WordCompleter(sorted(list(set(get_av_perf_stat_properties()))), ignore_case=False, WORD=True))
    runner_dict["properties"] = [prop.strip() for prop in props.split(",")]
    return runner_dict


def prompt_rusage_exec_dict(run_dict: dict) -> dict:
    """
    Prompt for the config of the rusage exec runner.

    :param run_dict: run config dict (without the runner part)
    :return: runner config
    """
    runner_dict = {}
    default_props = ", ".join(RusageExecRunner.misc_options["properties"].get_default())

    class RusagePropertiesValidator(Validator):

        def validate(self, document: Document):
            vals = [elem.strip() for elem in document.text.split(",")]
            ret = verbose_isinstance(vals, ValidRusagePropertyList())
            if not ret:
                raise ValidationError(message=str(ret), cursor_position=len(document.text))

    props = prompt("Which properties should be obtained from getrusage(1)? ",
                   validator=RusagePropertiesValidator(), default=default_props,
                   completer=WordCompleter(sorted(list(set(get_av_rusage_properties().keys()))),
                                           meta_dict=get_av_rusage_properties(), ignore_case=False, WORD=True))
    runner_dict["properties"] = [prop.strip() for prop in props.split(",")]
    return runner_dict


def prompt_time_exec_dict(run_dict: dict) -> dict:
    """
    Prompt for the config of the time exec runner.

    :param run_dict: run config dict (without the runner part)
    :return: runner config
    """
    runner_dict = {}
    default_props = ", ".join(TimeExecRunner.misc_options["properties"].get_default())

    class TimePropertiesValidator(Validator):

        def validate(self, document: Document):
            vals = [elem.strip() for elem in document.text.split(",")]
            ret = verbose_isinstance(vals, ValidTimePropertyList())
            if not ret:
                raise ValidationError(message=str(ret), cursor_position=len(document.text))

    props = prompt("Which properties should be obtained from gnu time? ",
                   validator=TimePropertiesValidator(), default=default_props,
                   completer=WordCompleter(sorted(list(set(get_av_time_properties().keys()))),
                                           meta_dict=get_av_rusage_properties(), ignore_case=False, WORD=True))
    runner_dict["properties"] = [prop.strip() for prop in props.split(",")]
    return runner_dict


def prompt_spec_exec_dict(run_dict: dict) -> dict:
    """
    Prompt for the config of the spec exec runner.

    :param run_dict: run config dict (without the runner part)
    :return: runner config
    """
    runner_dict = {}

    runner_dict["file"] = default_prompt("SPEC like result file to use: ",
                                         validator=TypeValidator(FileName()),
                                         completer=PathCompleter())

    runner_dict["base_path"] = prompt("Property base path: ")

    runner_dict["path_regexp"] = prompt("Regexp matching the property path for each measured property: ",
                                        validator=NonEmptyValidator())

    def get(sub_path: str = ""): # just a mock
        """
        Get the value of the property with the given path.
        :param sub_path: given path relative to the base path
        :return: value of the property
        """
    print("The python code is entered via a multiline input. ")
    print("Press [Meta+Enter] or [Esc] followed by [Enter] to accept input.")
    print("You can click with the mouse in order to select text.")
    print("Use the get(sub_path: str) -> str function to obtain a properties value.")
    locs = locals()
    runner_dict["code"] = prompt_python("The python is executed for each measured property: \n", lambda: {}, lambda: {"get": locs["get"]})

    return runner_dict


def prompt_config(name: str, prompt_dict_func: t.Callable[[], dict]):
    """
    Prompt for the whole config file.

    :param name: description of the config (i.e. "run config")
    :param prompt_dict_func: function to get a single config dict
    """
    blocks = []
    file = prompt("YAML file to store the {name} in: ".format(name=name),
                                     validator=TypeValidator(ValidYamlFileName(allow_non_existent=True)),
                                     completer=PathCompleter())

    fd = None # type: io.IOBase
    if os.path.exists(file):
        actions = {
            "append": "Append to the file",
            "overwrite": "Overwrite the file"
        }
        res = prompt("The file already exists. What should be done? ",
                  completer=WordCompleter(sorted(list(actions.keys())), meta_dict=actions, ignore_case=True),
                  validator=WordValidator(list(actions.keys()) + ["a", "o"], error_msg="Not a valid action"))
        if res.startswith("a"):
            fd = open(file, "a+")
        elif res.startswith("o"):
            fd = open(file, "w+")
    else:
        fd = open(file, "w+")

    blocks.append(prompt_dict_func())

    def store_in_file():
        #print(blocks)
        yaml.dump(blocks, fd)
        fd.flush()
        fd.close()

    while prompt_yesno("Add another {name}? ".format(name=name)):
        try:
            blocks.append(prompt_dict_func())
        except KeyboardInterrupt:
            store_in_file()
            return
        except BaseException as ex:
            store_in_file()
            raise ex
    store_in_file()

def prompt_build_config():
    """ Prompt for a build configuration and store it. """
    prompt_config("build config", prompt_build_dict)


def prompt_run_config():
    """ Prompt for a run configuration and store it. """
    prompt_config("run config", prompt_run_dict)


if __name__ == '__main__':
    #print(repr(prompt_attributes_dict("dsfsdf")))
    #print(repr(prompt_build_dict()))
    #print(repr(prompt_python(globals, locals)))
    #print(repr(prompt_spec_exec_dict({})))
    #vcs = VCSDriver.get_suited_vcs()
    #print(repr(vcs.validate_revision(13)))
    prompt_run_config()
    #print(isinstance("a", ValidYamlFileName(allow_non_existent=True)))
