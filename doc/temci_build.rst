temci build
===========

Build programs before the actual benchmarks, can checkout specific git commits.
This has the advantage of being able to configure the build for all benchmarked programs
and to build these programs at once. This build config also contains the run config for
each program. ``temci build`` compiles a run config and stores it into a file that can be
directly used with `temci exec <temci_exec.html>`_ (or other configured run drivers).

**For most cases using the builder capabilities of** `temci exec <temci_exec.html#building>`_
**should be enough. This also has the advantage of using a single command for all benchmarked
programs, whether they need to built or not.**

Usage
-----

.. code:: sh

    Usage: temci build [OPTIONS] BUILD_FILE

    Options:
      --tmp_dir TEXT                  Used temporary directory  [default:
                                      /tmp/temci]
      --threads INTEGER               Number of threads that build simultaneously
                                      [default: 1]
      --sudo                          Acquire sudo privileges and run benchmark
                                      programs with non-sudo user. Only supported
                                      on the command line.  [default: False]
      --sudo / --no-sudo              Acquire sudo privileges and run benchmark
                                      programs with non-sudo user. Only supported
                                      on the command line.  [default: False]
      --settings TEXT                 Additional settings file  [default: ]
      --out TEXT                      Resulting run config file  [default:
                                      run.exec.yaml]
      --log_level [debug|info|warn|error|quiet]
                                      Logging level  [default: info]
      --in TEXT                       Input file with the program blocks to build
                                      [default: build.yaml]
      --help                          Show this message and exit.

``in``, ``out`` and ``threads`` can also be set in the settings in the ``build`` block.

Be aware the parallel building or building multiple version of a program is still fragile.

Example
~~~~~~~
A build config (``build_config.yaml``) file for tool called ``test`` might look like this:

.. code:: yaml

    - attributes:
         description: 'test'
      run_config:
         run_cmd: 'sh test'
      build_config:
         build_cmd: 'echo "sleep 1" > test'

To build it, run ``temci build build_config.yaml``, resulting in the following ``run_config.yaml``:

.. code:: sh

    - attributes:
        description: test
        tags: []
      run_config:
        cwd: [.]
        run_cmd: sh test


File Format
-----------

``temci build`` accepts a file that consists of a YAML list of the entries in the following format:

.. code:: yaml

    # Optional attributes that describe the block
    attributes:
        description:         Optional(Str())

        # Tags of this block
        tags:         ListOrTuple(Str())

    # Build configuration for this program block
    build_config:
        # Base directory that contains everything to build an run the program
        base_dir:         Either(DirName()|non existent)
                    default: .

        # Used version control system branch (default is the current branch)
        branch:         Either(Str()|non existent)

        # Command to build this program block, might randomize it
        cmd:         Str()

        # Number of times to build this program
        number:         Either(Int()|non existent)
                    default: 1

        # Used version control system revision of the program (-1 is the current revision)
        revision:         Either(Either(Str()|Int())|non existent)
                    default: -1

        # Working directory in which the build command is run
        working_dir:         Either(DirName()|non existent)
                    default: .

    # Run configuration for this program block
    run_config:         Dict(, keys=Any, values=Any, default = {})


VCS Support
-----------
Currently only Git is supported, but adding support for other version control systems is simple.
The code for the VCS drivers is in the `temci.utils.vcs <temci.utils.html#module-temci.utils.vcs>`_ module.