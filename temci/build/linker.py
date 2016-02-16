"""
Enables the linker randomization (the order in which the libraries are linked).

Currently only tested on 64 bit systems.
"""
import random
import typing as t
import os, json, subprocess, shutil
import temci.utils.settings


def link(argv: t.List[str], randomize: bool = True, ld_tool: str = "/usr/bin/ld"):
    args = argv[1:] # type: t.List[str]
    arg_groups = [] # type: t.List[t.Tuple[bool, t.List[str]]]

    def is_randomizable(arg: str) -> bool:
        return arg.startswith("-L") or arg.endswith(".o")

    new_args = args
    if randomize:
        for arg in args:
            r = is_randomizable(arg)
            if not arg_groups or arg_groups[-1][0] != r:
                arg_groups.append((r, [arg]))
            else:
                arg_groups[-1][1].append(arg)

        for (r, g) in arg_groups:
            if r:
                random.shuffle(g)

        new_args = [x for (r, g) in arg_groups for x in g]
    cmd = "{} {}".format(ld_tool, " ".join(new_args))
    proc = subprocess.Popen(["/bin/sh", "-c", cmd], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.poll() > 0:
        raise OSError("Linker failed: out={!r}, err={!r}".format(out, err))


def process_linker(call: t.List[str]):
    config = json.loads(os.environ["RANDOMIZATION"]) if "RANDOMIZATION" in os.environ else {}
    randomize = "linker" in config and config["linker"]
    ld_tool = config["used_ld"] if "used_ld" in config else "/usr/bin/ld"
    if randomize:
        for i in range(0, 6):
            try:
                link(call, randomize=randomize, ld_tool=ld_tool)
            except OSError:
                continue
            return
    os.system("{} {}".format(ld_tool, " ".join(call[1:])))