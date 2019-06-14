import datetime
import logging
import os
import json
import subprocess
import queue
import shutil
import threading
from collections import namedtuple
from ..utils.typecheck import *
from ..utils.vcs import VCSDriver
from ..utils.settings import Settings
import typing as t


class Builder:
    """
    Allows the randomized building of a program configured by a program block configuration.
    """

    rand_conf_scheme = Dict({        # type: Dict
            "heap": (NaturalNumber() | NonExistent())
                    // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
            "bss": (Bool() | NonExistent())
                    // Description("Randomize the bss sub segments?"),
            "data": (Bool() | NonExistent())
                    // Description("Randomize the data sub segments?"),
            "rodata": (Bool() | NonExistent())
                    // Description("Randomize the rodata sub segments?"),
            "file_structure": (Bool() | NonExistent())
                              // Description("Randomize the file structure."),
            "linker": (Bool() | NonExistent())
                              // Description("Randomize the linking order"),
            "used_as": (Str() | NonExistent()) // Description("Used gnu assembler, default is /usr/bin/as"),
            "used_ld": (Str() | NonExistent()) // Description("Used gnu linker, default is /usr/bin/ld")
        }, unknown_keys=True)
    """ Type scheme of the randomization configuration for a program block """

    def __init__(self, build_dir: str, build_cmd: str, revision: t.Union[str, int], number: int, rand_conf: dict,
                 base_dir: str, branch: str):
        """
        Creates a new builder for a program block.

        :param build_dir: working directory in which the build command is run
        :param build_cmd: command to build this program block
        :param revision: used version control system revision of the program (-1 is the current revision)
        :param number: number of times to build this program
        :param rand_conf: randomization configuration
        :param base_dir: base directory that contains everything to build an run the program
        :param branch: used version control system branch
        """
        typecheck(build_dir, DirName())
        typecheck(build_cmd, str)
        typecheck(revision, Int() | Str())
        typecheck(number, PositiveInt())
        typecheck(base_dir, DirName())
        _rand_conf = rand_conf
        _rand_conf = Settings()["build/rand"]
        _rand_conf.update(rand_conf)
        rand_conf = _rand_conf
        typecheck(rand_conf, self.rand_conf_scheme)
        self.build_dir = os.path.join(base_dir, build_dir) if base_dir != "." else build_dir # type: str
        """ Working directory in which the build command is run """
        self.build_cmd = build_cmd  # type: str
        """ Command to build this program block """
        self.revision = revision  # type: t.Union[str, int]
        """ Used version control system revision of the program """
        self.number = number  # type: int
        """ Number of times to build this program """
        self.rand_conf = rand_conf
        """ Randomization configuration """
        self.vcs_driver = VCSDriver.get_suited_vcs(dir=self.build_dir, branch=None if branch is "" else branch)
        """ Used version control system driver """

    def build(self, thread_count: t.Optional[int] = None) -> t.List[str]:
        """
        Build the program block in parallel with at maximum `thread_count` threads in parallel.

        :param thread_count: number of threads to use at maximum to build the configured number of time,
               defaults to `build/threads`
        :return: list of base directories for the different builds
        """
        thread_count = thread_count or Settings()["build/threads"]

        time_tag = datetime.datetime.now().strftime("%s%f")

        def tmp_dirname(i: t.Union[int, str] = "base"):
            tmp_dir = os.path.join(Settings()["tmp_dir"], "build", time_tag, str(i))
            return tmp_dir

        tmp_dir = tmp_dirname()
        if self.revision == -1 and self.number == 1:
            tmp_dir = self.build_dir
            os.makedirs(tmp_dir, exist_ok=True)
            submit_queue = queue.Queue()
            submit_queue.put(BuilderQueueItem(0, tmp_dir, tmp_dir, self.rand_conf, self.build_cmd))
            BuilderThread(0, submit_queue).run()

            logging.info("Finished building")
            return [tmp_dir]

        logging.info("Create base temporary directory and copy build directory")
        os.makedirs(tmp_dir)
        self.vcs_driver.copy_revision(self.revision, self.build_dir, tmp_dir)

        ret_list = []
        submit_queue = queue.Queue()
        threads = []
        for i in range(0, self.number):
            tmp_build_dir = tmp_dirname(i)
            submit_queue.put(BuilderQueueItem(i, tmp_build_dir, tmp_dir, self.rand_conf, self.build_cmd))
            ret_list.append(tmp_build_dir)
        try:
            for i in range(min(thread_count, self.number)):
                thread = BuilderThread(i, submit_queue)
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()
        except BaseException as err:
            for thread in threads:
                thread.stop = True
            shutil.rmtree(tmp_dir)
            logging.info("Error while building")
            raise BuilderKeyboardInterrupt(err, ret_list)
        logging.info("Finished building")
        shutil.rmtree(tmp_dir)
        return ret_list


class BuilderKeyboardInterrupt(KeyboardInterrupt):
    """
    KeyboardInterrupt that wraps an error that occurred during the building of a program block
    """

    def __init__(self, error: BaseException, result: t.List[str]):
        self.error = error
        """ Wrapped error """
        self.result = result
        """ Base directories of the succesfull builds """


BuilderQueueItem = namedtuple("BuilderQueueItem", ["id", "tmp_build_dir", "tmp_dir", "rand_conf", "build_cmd"])


def env_variables_for_rand_conf(rand_conf: t.Dict) -> t.Dict[str, str]:
    """
    Creates a dictionary of environment variables to use the assembler randomisation.

    :param rand_conf: configuration (@see Builder.rand_conf_type)
    """
    typecheck_locals(rand_conf=Builder.rand_conf_scheme)
    _rand_conf = Settings()["build/rand"]
    _rand_conf.update(rand_conf)
    as_path = os.path.abspath(os.path.abspath(__file__) + "../../../scripts")
    return {
        "RANDOMIZATION": json.dumps(_rand_conf),
        "PATH": as_path + "/linker/:" + as_path + "/:" + os.environ["PATH"],
        "LANG": "en_US.UTF-8",
        "LANGUAGE": "en_US",
        "TMP_DIR": Settings()["tmp_dir"],
        "RANDOMIZATION_linker": "true" if rand_conf["linker"] else "false",
        "RANDOMIZATION_used_ld": rand_conf["used_ld"]
    }


class BuilderThread(threading.Thread):
    """
    Thread that fetches configurations from a queue and builds the therein described program blocks.
    """

    def __init__(self, id: int, submit_queue: queue.Queue):
        """
        Creates a new builder thread

        :param id: id of the thread
        :param submit_queue: used queue
        """
        threading.Thread.__init__(self)
        self.stop = False
        """ Stop the queue fetch loop? """
        self.id = id
        """ Id of this thread """
        self.submit_queue = submit_queue
        """ Used queue """

    def run(self):
        """
        Queue fetch loop, that builds the fetched program block configurations.
        """
        while not self.stop:
            item = None
            try:
                item = self.submit_queue.get(timeout=1)
            except queue.Empty:
                return
            tmp_build_dir = item.tmp_build_dir
            if tmp_build_dir != item.tmp_dir:
                if os.path.exists(tmp_build_dir):
                    shutil.rmtree(tmp_build_dir)
                shutil.copytree(item.tmp_dir, tmp_build_dir)
            env = os.environ.copy()
            env.update(env_variables_for_rand_conf(item.rand_conf))
            logging.info("Thread {}: Building number {}".format(self.id, item.id))
            proc = subprocess.Popen(["/bin/sh", "-c", "export PATH={}; sync;".format(env["PATH"])
                                     + item.build_cmd],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True,
                                    cwd=tmp_build_dir, env=env)
            out, err = proc.communicate()
            if proc.poll() > 0:
                proc = subprocess.Popen(["/bin/sh", "-c", item.build_cmd],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True,
                                    cwd=tmp_build_dir, env=env)
                out, err = proc.communicate()
                if proc.poll() > 0:
                    if tmp_build_dir != item.tmp_dir:
                        shutil.rmtree(tmp_build_dir)
                    #self.submit_queue.put(item)
                    raise EnvironmentError("Thread {}: Build error: {}".format(self.id, str(err)))
            #logging.info("Thread {}: Finished building… {}".format(self.id, str(out)))
            #setup.exec("hadori", "./hadori {} {}".format(item.tmp_dir, tmp_build_dir))
