"""
This module helps to build the C and C++ code in the scripts directory.
"""

import os, subprocess, logging


def script_relative(file: str) -> str:
    """
    Returns the absolute version of the passed file name.
    :param file: passed file name relative to the scripts directory
    """
    return os.path.join(os.path.realpath(os.path.dirname(__file__)), "../scripts", file)


class ExecError(BaseException):
    """
    Error raised if a command failed.
    """

    def __init__(self, cmd: str, out: str, err: str):
        super().__init__()
        self.cmd = cmd  # type: str
        """ Failed command """
        self.out = out # type: str
        """ Output of the command """
        self.err = err # type: str
        """ Error output of the command """

    def __str__(self) -> str:
        return "Running {!r} failed: out={!r}, err={!r}".format(self.cmd, self.out, self.err)


def exec(dir: str, cmd: str):
    """
    Run the passed command in the passed directory

    :param dir: passed directory
    :param cmd: passed command
    :raises ExecError: if the executed program has a > 0 error code
    """
    proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        cwd=script_relative(dir))
    out, err = proc.communicate()
    if proc.poll() > 0:
        raise ExecError(cmd, str(out), str(err))


def make_scripts():
    """
    Builds the C and C++ code inside the scripts directory.
    """
    try:
        exec("hadori", "make")
        exec("rusage", "make")
        exec("linker", "make")
    except ExecError as err:
        logging.error(err)
        exit(1)
    try:
        exec("cpu_cache", "make")
    except ExecError as err:
        logging.error(err)
        logging.error("You probably haven't installed the proper packages for kernel module development "
                      "(kernel-devel on fedora or linux-headers-generic on ubuntu).")
        logging.error("Not compiling the kernel module results in the malfunctioning of the DisableCaches "
                      "exec run driver plugin.")
