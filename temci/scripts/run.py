import os
import sys
from temci.utils.util import has_root_privileges


def run():
    sudo_opt_index = sys.argv.index("--sudo") if "--sudo" in sys.argv else sys.maxsize
    raw_opt_index = sys.argv.index("--") if "--" in sys.argv else sys.maxsize
    has_sudo_opt = sudo_opt_index != sys.maxsize and sudo_opt_index < raw_opt_index

    if not has_sudo_opt or has_root_privileges():
        from temci.scripts.cli import cli_with_error_catching
        cli_with_error_catching()
    else:
        if has_sudo_opt:
            sys.argv.remove("--sudo")
        import json, shlex
        cmd = "sudo TEMCI_ENV={} {}".format(
            shlex.quote(json.dumps({k:os.environ[k] for k in os.environ})),
            " ".join(shlex.quote(arg) for arg in sys.argv))
        os.system(cmd)


if __name__ == "__main__":
    run()