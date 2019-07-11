Supported Operating Systems
===========================

Linux is the main target for this tool.
The support for other Unix like operating systems is limited. Most of the advanced environment setup functionality,
like cpu sets or disabling hyper threading, is Linux specific.

What works and what does not
----------------------------
- ``temci exec`` and ``temci short``
    - the ``perf_stat`` runner is Linux specific
    - all other runners should work, but it is uncertain whether the ``rusage`` runner works
    - the ``time`` runner requires the ``gtime`` program to be installed
    - most the environment setup code (i.e. the plugins) don't work, with the exception of
      ``preheat`` and ``sleep`` that are implemented in python
    - ``--sudo`` is only supported on Linux
- ``temci shell``
    - see ``temci exec`` for the supported plugins
- ``temci setup``
    - might not work
- ``temci report``, ``temci build``, ``temci clean``, ``temci completion``, …
    - without any constraints

Other Unixes
------------
Other Unix like operating systems aren't currently tested. But there is a chance that they might work as well.

Windows
-------
Windows is currently not supported, but `temci report` might still work. The Linux subsystem in Windows might
enable the usage of the features that work on Apples OS X.