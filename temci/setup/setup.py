import os, subprocess, logging

def script_relative(file: str):
    return os.path.join(os.path.realpath(os.path.dirname(__file__)), "../scripts", file)


class ExecError(BaseException):

    def __init__(self, cmd: str, out: str, err: str):
        super().__init__()
        self.cmd = cmd
        self.out = out
        self.err = err

    def __str__(self):
        return "Running {!r} failed: out={!r}, err={!r}".format(self.cmd, self.out, self.err)


def exec(dir: str, cmd: str):
    """
    Run the passed command in the passed directory
    :param dir: passed directory
    :param cmd: passed command
    :raises ExecError if the executed program has a > 0 error code
    """
    proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        cwd=script_relative(dir))
    out, err = proc.communicate()
    if proc.poll() > 0:
        raise ExecError(cmd, str(out), str(err))


def make_scripts():
    try:
        exec("hadori", "make")
        exec("rusage", "make")
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
