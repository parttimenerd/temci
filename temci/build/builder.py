import concurrent
import datetime
import logging
import os, sys, yaml, json, subprocess
import queue
import random
import shutil
import threading
from collections import namedtuple

import multiprocessing
from time import sleep

import temci.setup.setup as setup
from path import Path

from ..utils.typecheck import *
from ..utils.vcs import VCSDriver
from ..utils.settings import Settings

class Builder:

    rand_conf_type = Dict({
            "heap": (NaturalNumber() | NonExistent())
                    // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
            "stack": (NaturalNumber() | NonExistent())
                    // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
            "bss": (Bool() | NonExistent())
                    // Description("Randomize the bss sub segments?"),
            "data": (Bool() | NonExistent())
                    // Description("Randomize the data sub segments?"),
            "rodata": (Bool() | NonExistent())
                    // Description("Randomize the rodata sub segments?"),
            "file_structure": (Bool() | NonExistent())
                              // Description("Randomize the file structure.")
        }, all_keys=False)

    def __init__(self, build_dir: str, build_cmd: str, revision, number: int, rand_conf: dict,
                 base_dir: str, branch: str):
        typecheck(build_dir, DirName())
        typecheck(build_cmd, str)
        typecheck(revision, Int() | Str())
        typecheck(number, PositiveInt())
        typecheck(base_dir, DirName())
        _rand_conf = rand_conf
        rand_conf = Settings()["build/rand"]
        rand_conf.update(rand_conf)
        typecheck(rand_conf, self.rand_conf_type)
        self.build_dir = os.path.join(base_dir, build_dir)
        self.build_cmd = build_cmd
        self.revision = revision
        self.number = number
        self.rand_conf = rand_conf
        self.vcs_driver = VCSDriver.get_suited_vcs(dir=self.build_dir, branch=None if branch is "" else branch)

    def build(self, thread_count: int = None) -> list:
        """
        Build the program blocks.
        """
        thread_count = thread_count or multiprocessing.cpu_count()
        logging.info("Create base temporary directory and copy build directory")
        time_tag = datetime.datetime.now().strftime("%s%f")
        def tmp_dirname(i: int = "base"):
            tmp_dir = os.path.join(Settings()["tmp_dir"], "build", time_tag, str(i))
            return tmp_dir
        tmp_dir = tmp_dirname()
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

    def __init__(self, error, result):
        self.error = error
        self.result = result


BuilderQueueItem = namedtuple("BuilderQueueItem", ["id", "tmp_build_dir", "tmp_dir", "rand_conf", "build_cmd"])


class BuilderThread(threading.Thread):

    def __init__(self, id: int, submit_queue: queue.Queue):
        threading.Thread.__init__(self)
        self.stop = False
        self.id = id
        self.submit_queue = submit_queue

    def run(self):
        while not self.stop:
            item = None
            try:
                item = self.submit_queue.get(timeout=1)
            except queue.Empty:
                return
            tmp_build_dir = item.tmp_build_dir
            shutil.copytree(item.tmp_dir, tmp_build_dir)
            as_path = Path(__file__).parent.parent + "/scripts"
            env = {
                "RANDOMIZATION": json.dumps(item.rand_conf),
                "PATH": as_path + "/:" + os.environ["PATH"],
                "LANG": "en_US.UTF-8",
                "LANGUAGE": "en_US"
            }
            logging.info("Thread {}: Start building number {}".format(self.id, item.id))
            proc = subprocess.Popen(["/bin/sh", "-c", "export PATH={}/:$PATH; sync;".format(as_path)
                                     + item.build_cmd],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True,
                                    cwd=tmp_build_dir, env=env)
            out, err = proc.communicate()
            logging.info("Thread {}: {}".format(self.id, str(out)))
            setup.exec("hadori", "./hadori {} {}".format(item.tmp_dir, tmp_build_dir))
            if proc.poll() > 0 or len(str(err).strip()) > 0:
                shutil.rmtree(tmp_build_dir)
                raise EnvironmentError("Thread {}: Build error: {}".format(self.id, str(err)))