import datetime
import logging
import os, sys, yaml, json, subprocess
import random
import shutil
import temci.setup.setup as setup
from path import Path

from ..utils.typecheck import *
from ..utils.vcs import VCSDriver
from ..utils.settings import Settings

class Builder:

    def __init__(self, build_dir: str, build_cmd: str, revision, number: int, rand_conf: dict):
        typecheck(build_dir, DirName())
        typecheck(build_cmd, str)
        typecheck(revision, Int() | Str())
        typecheck(number, PositiveInt())
        _rand_conf = rand_conf
        rand_conf = Settings()["build/rand"]
        rand_conf.update(rand_conf)
        typecheck(rand_conf, Dict({
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
        }, all_keys=False))
        self.build_dir = build_dir
        self.build_cmd = build_cmd
        self.revision = revision
        self.number = number
        self.rand_conf = rand_conf
        self.vcs_driver = VCSDriver.get_suited_vcs(dir=self.build_dir)

    def build(self) -> list:
        """
        Build the program blocks.
        """
        time_tag = datetime.datetime.now().strftime("%s%f")
        def tmp_dirname(i: int = "base"):
            tmp_dir = os.path.join(Settings()["tmp_dir"], "build", time_tag, str(i))
            return tmp_dir
        tmp_dir = tmp_dirname()
        os.makedirs(tmp_dir)
        self.vcs_driver.copy_revision(self.revision, self.build_dir, tmp_dir)

        ret_list = []
        for i in range(0, self.number):
            tmp_build_dir = tmp_dirname(i)
            ret_list.append(tmp_build_dir)
            shutil.copytree(tmp_dir, tmp_build_dir)
            as_path = Path(__file__).parent.parent + "/scripts"
            env = {
                "RANDOMIZATION": json.dumps(self.rand_conf),
                "PATH": as_path + "/:" + os.environ["PATH"],
                "LANG": "en_US.UTF-8",
                "LANGUAGE": "en_US"
            }
            proc = subprocess.Popen(["/usr/bin/zsh", "-c", "export PATH={}/:$PATH; ".format(as_path) + self.build_cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                                cwd=tmp_build_dir, env=env)
            out, err = proc.communicate()
            logging.info(str(out))
            setup.exec("hadori", "./hadori {} {}".format(tmp_dir, tmp_build_dir))
            if proc.poll() > 0 or len(str(err).strip()) > 0:
                logging.error("Build error: ", str(err))
                shutil.rmtree(tmp_build_dir)
                exit(proc.poll())
        shutil.rmtree(tmp_dir)
        return ret_list