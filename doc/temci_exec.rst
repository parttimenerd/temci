temci exec
==========

This page explains ``temci exec`` and ``temci short exec`` that allow you to do the actual benchmarks.

temci short exec
----------------
Make basic benchmarks, without creating a configuration file. It supports the same command line options
as ``temci exec``:

.. code:: sh

    Usage: temci short exec [OPTIONS] COMMANDS

    -wd, --without_description COMMAND
        Benchmark the command and use itself as its description.
    -d, --with_description DESCRIPTION COMMAND...
        Benchmark the command and set its description attribute.
    …
    (options of temci exec)

Options
-------
For a whole list of command line options run ``temci exec --help``.

Number of runs
~~~~~~~~~~~~~~

Configuration File
------------------

Runners
-------
The runners are selected on the command line using the ``--runner`` option and the configuration file
via ``run/exec_misc/runner``.


Plugins
-------

The plugins are enabled via the command line option ``--NAME_active`` and in the configuration file
via ``run/exec_plugins/NAME_active``.

Presets
-------

The following explains the different plugins.

DisableCaches
~~~~~~~~~~~~~

Build it via "temci setup". Needs the kernel develop packet of your
distribution. It's called ``kernel-devel`` on Fedora.

*Attention*: Benchmarks will get very very slow. It might require a restart
of your system. Example for the slow down: for a silly Haskell program
(just printing ``"sdf"``), the measured task-clock went from just 1.4
seconds to 875.2 seconds. The speed up with caches is 62084%.

StopStart
~~~~~~~~~

This plugin tries to stop most other processes on the system that
aren't really needed. By default most processes that are children (or
children's children, …) of a process whose name ends with "dm" are stopped.
This is a simple heuristic to stop all processes that are not vital
(i.e. created by some sort of display manager). SSH and X11 are stopped
too.

Advantages of this plugin (which is used via the command line flag
``--stop_start``):
* No one can start other programs on the system (via
ssh or the user interface) => fewer processes can interfere with the
benchmarking
* Noisy processes like Firefox don't interfere with the
benchmarking as they are stopped - this reduces the variance of benchmarks
significantly

Disadvantages:
* You can't interact with the system (therefore use the
send\_mail option to get mails after the benchmarking finished)
* Not all processes that could be safely stopped are stopped as this decision
is hard to make
* You can't stop the benchmarking as all keyboard
interaction is disabled (by stopping X11)

Stopping a process here means to send a process a SIGSTOP signal and
resume it by sending a SIGCONT signal later.



Error Codes
-----------

==== =======================================
   0 no error
   1 at least one benchmarked program failed
 255 temci itself failed
==== =======================================
