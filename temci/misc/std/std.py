import click
import yaml
from typing import List

"""

Analyse the different plugins of temci on how they affect the standard deviation.

Sample call:

.. code:: sh
    
    python3 temci/misc/std/std.py create "temci short exec 'grep \"[ab]*\"-R .' --runs 10 " "sync,sleep,drop_fs_caches,disable_swap,cpu_governor,disable_aslr,disable_ht,disable_intel_turbo,cpuset,nice,other_nice,preheat,flush_cpu_caches" > test.yaml

"""


@click.group("std")
def std():
    pass


def combinations(plugins: List[str], mode: str) -> List[List[str]]:
    if mode == "single":
        return [[p] for p in plugins]


@std.command(short_help="Create config")
@click.argument("cmd")
@click.argument("plugins")
@click.argument("mode", type=click.Choice(["single"]), default="single")
@click.argument("out", default="-")
def create(cmd: str, plugins: str, mode: str, out: str):
    plugs = plugins.split(",")
    ret = []
    for plug_comb in combinations(plugs, mode):
        temci_cmd = cmd + " " + " ".join("--{}".format(p) for p in plug_comb)
        ret.append({
            "attributes": {
                "description": "_".join(plug_comb)
            },
            "run_config": {
                "run_cmd": temci_cmd
            }
        })
    with click.open_file(out, "w") as f:
        yaml.dump(ret, f)


if __name__ == "__main__":
    std()