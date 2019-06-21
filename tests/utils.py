import os
import shlex
import subprocess
import sys

import tempfile
from typing import Dict, Union, NamedTuple, Tuple, Any

import yaml

from click.testing import CliRunner

sys.path.append(os.path.dirname(__file__) + "/..")
import temci.utils.util
temci.utils.util.allow_all_imports = True

from temci.utils.settings import Settings


from temci.scripts.cli import cli


class Result(NamedTuple):
    out: str
    err: str
    ret_code: int
    file_contents: Dict[str, str]
    yaml_contents: Dict[str, dict]


def run_temci_proc(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None,
                   expect_success: bool = True) \
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
        cmd = "temci " + args
        if settings is not None:
            with open(d + "/settings.yaml", "w") as f:
                yaml.dump(settings, f)
            cmd += " --config settings.yaml"
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.utf-8"
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
    for f in os.listdir(d):
        fd = d + "/" + f
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
                    expect_success: bool = True) \
        -> Result:
    """
    Run temci with the passed arguments

    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}
    :param expect_success: expect a zero return code
    :return: result of the call
    """

    runner = CliRunner()
    set = Settings().type_scheme.get_default().copy()
    set.update(settings or {})
    with runner.isolated_filesystem():
        cmd = args
        _store_files(files)
        with open("settings.yaml", "w") as f:
            yaml.dump(set, f)
        cmd += " --config settings.yaml"
        env = os.environ.copy()
        env["LC_ALL"] = "en_US.utf-8"
        args = sys.argv.copy()
        sys.argv = shlex.split("temci " + cmd)
        result = runner.invoke(cli, cmd, env=env, catch_exceptions=True)
        sys.argv = args
        file_contents, yaml_contents = _load_files(files)
        ret = Result(result.output.strip(), str(result.stderr_bytes).strip(), result.exit_code, file_contents, yaml_contents)
        if result.exception and not isinstance(result.exception, SystemExit):
            print(repr(ret))
            raise result.exception
        if expect_success:
            assert result.exit_code == 0, repr(ret)
        return ret


def run_temci(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None,
              expect_success: bool = True) \
        -> Result:
    """
    Run temci with the passed arguments

    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}
    :param expect_success: expect a zero return code
    :return: result of the call
    """
    if os.getenv("TEMCI_TEST_CMD"):
        return run_temci_proc(args, settings, files, expect_success)
    return run_temci_click(args, settings, files, expect_success)

