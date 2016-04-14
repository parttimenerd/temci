"""
Enables the randomization of the link order during the building of programs.
It's used to create a wrapper for `ld` (@see ../scripts/ld).

An implementation of this wrapper in C++ is given in the ../scripts/linker directory.
This python implementation is only the fall back solution if the C++ version isn't available.

The link order randomization only works for compilers that use the `ld` tool.
"""

import random
import typing as t
import os, json, subprocess

def link(argv: t.List[str], randomize: bool = True, ld_tool: str = "/usr/bin/ld"):
    """
    Function that gets all argument the `ld` wrapper gets passed, randomized their order and executes the original `ld`.

    :param argv: `ld` arguments
    :param randomize: actually randomize the order of the arguments?
    :param ld_tool: used `ld` tool
    """
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
    """
    Uses the passed `ld` arguments to randomize the link order during linking.
    It's configured by environment variables.

    :param call: arguments for `ld`
    """
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