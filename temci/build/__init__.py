"""
This module contains the build part of temci (usable from the command line with `temci build`).

It's separated into four parts with the following purposes:

- build_processor.py: fassade for the the builders
- builder.py: Build programs with possible randomizations.
- assembly.py: randomize the assembler and provide some sort of a wrapper for `as`. It's called by ../scripts/as
- linker.py: randomize the link order and provide some sort of a wrapper for `ld`. It's called by ../scripts/ld and
  reimplemented in c++ in ../scripts/linker.
"""