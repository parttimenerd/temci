import os, subprocess, logging

def script_relative(file: str):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "../scripts", file)

def exec(dir: str, cmd: str):
    """
    Run the passed command in the passed directory
    :param dir: passed directory
    :param cmd: passed command
    """
    proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        cwd=script_relative(dir))
    out, err = proc.communicate()
    if proc.poll() > 0:
        logging.error("Build error: " + str(err))
        exit(proc.poll())

def make_scripts():
    exec("hadori", "make")
    exec("cpu_cache", "make")
    exec("rusage", "make")