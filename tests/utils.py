import os
import subprocess

import tempfile
from typing import Dict, Union, NamedTuple

import yaml


class Result(NamedTuple):
    out: str
    err: str
    ret_code: int
    file_contents: Dict[str, str]
    yaml_contents: Dict[str, dict]


def run_temci(args: str, settings: dict = None, files: Dict[str, Union[dict, list, str]] = None, timeout: int = None,
              expect_success: bool = True) \
        -> Result:
    """
    Run temci with the passed arguments
    :param args: arguments for temci
    :param settings: settings dictionary, stored in a file called `settings.yaml` and appended to the arguments
    :param files: {file name: content as string or dictionary that is converted into YAML first}
    :param timeout: timeout for the command
    :param expect_success: expect a zero return code
    :return: result of the call
    """
    with tempfile.TemporaryDirectory() as d:
        if files is not None:
            for file, content in files.items():
                with open(d + "/" + file, "w") as f:
                    if isinstance(f, str):
                        print(content, file=f)
                    else:
                        yaml.dump(content, f)
        cmd = "temci " + args
        if settings is not None:
            with open(d + "/settings.yaml", "w") as f:
                yaml.dump(settings, f)
            cmd += " --config settings.yaml"
        env = os.environ.copy()
        env["LC_ALL"] = "C";
        proc = subprocess.Popen(["/bin/sh", "-c", cmd],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=str(d),
                                env=env,
                                universal_newlines=True)
        out, err = proc.communicate(timeout=timeout)
        file_contents = {}
        yaml_contents = {}
        for f in os.listdir(d):
            fd = d + "/" + f
            if os.path.isfile(fd) and f != "settings.yaml" and (files is None or f not in files):
                with open(fd) as fs:
                    file_contents[f] = fs.read()
                    if f.endswith(".yaml"):
                        yaml_contents[f] = yaml.load(file_contents[f])
        ret = Result(str(out).strip(), str(err).strip(), proc.returncode, file_contents, yaml_contents)
        if expect_success:
            assert proc.returncode == 0, repr(ret)
        return ret
