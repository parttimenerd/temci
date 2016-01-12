import os, sys, yaml, json, subprocess
from ..utils.typecheck import *
from ..utils.vcs import VCSDriver
from ..utils.settings import Settings
from .builder import Builder, BuilderKeyboardInterrupt


class BuildProcessor:

    block_scheme = Dict({
        "attributes": Dict(all_keys=False, key_type=Str()),
        "run_config": Dict(all_keys=False),
        "build_config": Dict({
            "build_cmd": Str() // Default(""),
            "number": (PositiveInt() | NonExistent()) // Default(1),
            "randomization": (Dict(all_keys=False) | NonExistent()) // Default({}),
            "working_dir": (DirName() | NonExistent()) // Default("."),
            "revision": (Str() | Int() | NonExistent()) // Default(-1),
            "branch": (Str() | NonExistent()) // Default(""),
            "base_dir": (DirName() | NonExistent()) // Default(".")
        })
    })

    def __init__(self, build_blocks: list = None):
        if build_blocks is None:
            typecheck(Settings()["build/in"], ValidYamlFileName())
            with open(Settings()["build/in"], "r") as f:
                build_blocks = yaml.load(f)
        typecheck(build_blocks, List(self.block_scheme))
        self.build_blocks = [self.block_scheme.get_default() for i in range(len(build_blocks))]
        #print(json.dumps(self.build_blocks))
        for i, block in enumerate(build_blocks):
            for key in block.keys():
                self.build_blocks[i][key].update(block[key])
            typecheck(self.build_blocks[i], self.block_scheme, "build block {}".format(i))
        #print(json.dumps(self.build_blocks))
        typecheck(Settings()["build/out"], FileName())
        typecheck_locals(build_blocks=List())
        self.out = Settings()["build/out"]

    def build(self):
        run_blocks = []
        try:
            for block in self.build_blocks:
                working_dirs = []
                error = None
                try:
                    block_builder = Builder(block["build_config"]["working_dir"],
                            block["build_config"]["build_cmd"], block["build_config"]["revision"],
                            block["build_config"]["number"], block["build_config"]["randomization"],
                            block["build_config"]["base_dir"], block["build_config"]["branch"])
                    working_dirs = block_builder.build()
                except BuilderKeyboardInterrupt as err:
                    working_dirs = err.result
                    error = err.error
                block["run_config"]["cwd"] = working_dirs
                run_blocks.append({
                    "attributes": block["attributes"],
                    "run_config": block["run_config"]
                })

                if error:
                    raise error
        except KeyboardInterrupt as err:
            with open(self.out, "w") as f:
                yaml.dump(run_blocks, f)
            raise err
        with open(self.out, "w") as f:
            yaml.dump(run_blocks, f)
