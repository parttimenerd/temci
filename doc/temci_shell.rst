temci shell
===========

``temci short shell`` opens a shell in a benchmarking environment. It allows to execute your own benchmarking suite
in its own cpuset with disabled hyper threading, ….
This command has the same options as `temci exec <temci_exec.html>`_ (regarding presets and plugins).

For example running your own benchmarking suite ``bench.sh`` in a reasonably setup environment can be done
via:

.. code:: sh

    temci short shell ./bench.sh

The launched shell is interactive:

.. code:: sh

    > temci short shell
    >> echo 1
    1


``temci shell`` accepts an input file as its argument which has the following structure
(see `ShellRunDriver <temci.run.html#temci.run.run_driver.ShellRunDriver>`_:

.. code:: yaml

    # Optional build config to integrate the build step into the run step
    build_config:         Either(Dict(, keys=Any, values=Any, default = {})|non existent)

    # Optional attributes that describe the block
    attributes:
        description:         Optional(Str())

        # Tags of this block
        tags:         ListOrTuple(Str())

    run_config:
        # Execution directory
        cwd:         Either(List(Str())|Str())
                    default: .

        # Command to run
        run_cmd:         Str()
                    default: sh

        # Environment variables
        env:         Dict(, keys=Str(), values=Any, default = {})