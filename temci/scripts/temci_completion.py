"""
Just a more performant version of `temci completion` that rebuilds the completion
files only if the temci version changed.
The advantage over using `temci completion` directly is, that it's normally
significantly faster.

Usage:

```
    temci_completion [zsh|bash]
```
This returns the location of the completion file.
"""

import os

import click
import subprocess

from temci.scripts.version import version
from sys import argv
from os.path import exists

SUPPORTED_SHELLS = ["zsh", "bash"]


def print_help():
    print("""
temci (version {})  Copyright (C) 2016 Johannes Bechberger
This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions.
For details, see the LICENSE file in the source folder of temci.

Usage of temci_completion:

    temci_completion [{}]

This will return the completion file name.
    """.format(version, "|".join(SUPPORTED_SHELLS)))


def create_completion_dir() -> str:
    """ Create the directory for the completion files if it doesn't already exist. """
    subprocess.check_output(["/bin/mkdir", "-p", completion_dir()])


def completion_dir() -> str:
    """ Get the name of the completion directory """
    return click.get_app_dir("temci")


def completion_file_name(shell: str) -> str:
    """ Get the completion file name for the passed shell and the current temci version """
    assert shell in SUPPORTED_SHELLS
    return os.path.join(completion_dir(), "{shell}.{version}.sh".format(shell=shell, version=version))


def cli():
    """ Process the command line arguments and call ``temci completion`` if needed. """

    if len(argv) != 2 or argv[1] not in SUPPORTED_SHELLS:
        print_help()
        exit(len(argv) != 1)

    shell = argv[1]
    file_name = completion_file_name(shell)
    if exists(file_name):
        print(file_name)
    else:
        import subprocess
        try:
            subprocess.check_output(["/bin/sh", "-c", "temci completion " + shell])
        except subprocess.CalledProcessError as ex:
            print("While executing {!r} and error occured: {}".format(ex.cmd, ex.output))
            exit(1)
        print(file_name)

if __name__ == "__main__":
    cli()