import os
import shlex
import subprocess
import sys

import tempfile
import traceback
from typing import Dict, Union, NamedTuple, Tuple, Any

import yaml

from click.testing import CliRunner

sys.path.append(os.path.dirname(__file__) + "/..")
import temci.utils.util
temci.utils.util.allow_all_imports = True

from temci.utils.settings import Settings


from temci.scripts.cli import cli, ErrorCode


class Result(NamedTuple):
    out: str
    err: str
    ret_code: int
    file_contents: Dict[str, str]
    yaml_contents: Dict[str, dict]


def run_temci_proc(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None,
                   expect_success: bool = True, misc_env: Dict[str, str] = None) \
        -> Result:
    """
    Run temci with the passed arguments
    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}c at
    :param expect_success: expect a zero return code

    :return: result of the call
    """
    with tempfile.TemporaryDirectory() as d:
        _store_files(files, str(d))
        cmd = "python3 {}/temci/scripts/cli.py {}".format(os.path.dirname(os.path.dirname(__file__)), args)
        if settings is not None:
            with open(d + "/settings.yaml", "w") as f:
                yaml.dump(settings, f)
            cmd += " --config settings.yaml"
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.utf-8"
        env.update(misc_env or {})
        proc = subprocess.Popen(["/bin/sh", "-c", cmd],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=str(d),
                                env=env,
                                universal_newlines=True)
        out, err = proc.communicate()
        file_contents, yaml_contents = _load_files(files, d=d)
        ret = Result(str(out).strip(), str(err).strip(), proc.returncode, file_contents, yaml_contents)
        if expect_success:
            assert proc.returncode == 0, repr(ret)
        return ret


def _store_files(files: Dict[str, Union[dict, list, str]] = None, d: str = "."):
    if files is not None:
        for file, content in files.items():
            with open(d + "/" + file, "w") as f:
                if isinstance(f, str):
                    print(content, file=f)
                else:
                    yaml.dump(content, f)


def _load_files(files: Dict[str, Any], d: str = ".") -> Tuple[Dict[str, str], Dict[str, Union[dict, str, list]]]:
    file_contents = {}
    yaml_contents = {}
    for root, directory, fs in os.walk(d):
        for f in fs:
            fd = root + "/" + f
            if os.path.isfile(fd) and f != "settings.yaml" and (files is None or f not in files):
                with open(fd) as fs:
                    try:
                        file_contents[f] = fs.read()
                        if f.endswith(".yaml"):
                            yaml_contents[f] = yaml.safe_load(file_contents[f].replace("!!python/tuple", ""))
                    except UnicodeDecodeError:
                        pass
    return file_contents, yaml_contents


def run_temci_click(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None,
                    expect_success: bool = True, misc_env: Dict[str, str] = None, raise_exc: bool = False) \
        -> Result:
    """
    Run temci with the passed arguments

    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}
    :param expect_success: expect a zero return code
    :param misc_env: additional environment variables
    :return: result of the call
    """

    runner = CliRunner()
    set = Settings().type_scheme.get_default().copy()
    prior = set.copy()
    set.update(settings or {})
    with runner.isolated_filesystem():
        cmd = args
        _store_files(files)
        with open("settings.yaml", "w") as f:
            yaml.dump(set, f)
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.utf-8"
        env.update(misc_env or {})
        args = sys.argv.copy()
        sys.argv = shlex.split("temci " + cmd)
        err_code = None
        exc = None
        try:
            result = runner.invoke(cli, cmd.replace(" ", " --settings settings.yaml ", 1), env=env, catch_exceptions=True)
        except Exception as ex:
            print("".join(traceback.format_exception(None, ex, ex.__traceback__)), sys.stderr)
            err_code = ErrorCode.TEMCI_ERROR
            exc = ex
        sys.argv = args
        file_contents, yaml_contents = _load_files(files)
        ret = Result(result.output.strip(), str(result.stderr_bytes).strip(),
                     err_code if err_code is not None else result.exit_code, file_contents, yaml_contents)
        Settings().load_from_dict(prior)
        if result.exception and not isinstance(result.exception, SystemExit):
            print(repr(ret))
            if raise_exc:
                raise result.exception
        if exc and raise_exc:
            raise exc
        if expect_success:
            assert result.exit_code == 0, repr(ret)
        return ret


def run_temci(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None,
              expect_success: bool = True, misc_env: Dict[str, str] = None, raise_exc: bool = False) \
        -> Result:
    """
    Run temci with the passed arguments

    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}
    :param expect_success: expect a zero return code
    :param misc_env: additional environment variables
    :return: result of the call
    """
    if os.getenv("TEMCI_TEST_CMD", "0") == "1":
        return run_temci_proc(args, settings, files, expect_success, misc_env=misc_env)
    return run_temci_click(args, settings, files, expect_success, misc_env=misc_env, raise_exc=raise_exc)

