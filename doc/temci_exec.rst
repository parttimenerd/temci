temci exec
==========

This page explains ``temci exec`` and ``temci short exec`` that allow you to do the actual benchmarks.

The basic concept is that there are

run drivers
    that support a specific benchmarking concept (like benchmarking whole programs that can be executed on the shell),
    these run drivers use
:ref:`runners <Runners>`
    for the actual benchmarking and
:ref:`plugins <Plugins>`
    to setup up the benchmarking environment

Currently only one run driver is implemented, the exec run driver that supports benchmarking programs
executed in a shell.

The benchmarking process produces a YAML file with the benchmarking results.

There are multiple features that require root privileges. To use these features, call temci with
the ``--sudo`` option. It will run only temci in super user mode, but not the benchmarked programs
themself. Notable features that require these rights are cpu sets (for separating the benchmarked programs
from the rest of the system), disabling hyperthreading and settings the CPU governor.

temci short exec
----------------
Supports basic benchmarks, without creating a configuration file. It supports the same command line options
as ``temci exec``:

.. code:: sh

    Usage: temci short exec [OPTIONS] COMMANDS

    -wd, --without_description COMMAND
        Benchmark the command and use itself as its description.
    -d, --with_description DESCRIPTION COMMAND...
        Benchmark the command and set its description attribute.
    …
    (options of temci exec)

Usage
-----

Basic benchmarking of two programs using the :ref:`time<time runner>`:

.. code:: sh

    # compare the run times of two programs, running them each 20 times
    > temci short exec "sleep 0.1" "sleep 0.2" --runs 20
    Benchmark 20 times                [####################################]  100%
    Report for single runs
    sleep 0.1            (   20 single benchmarks)
         avg_mem_usage mean =           0.000, deviation =   0.0
         avg_res_set   mean =           0.000, deviation =   0.0
         etime         mean =      100.00000m, deviation = 0.00000%
         max_res_set   mean =         2.1800k, deviation = 3.86455%
         stime         mean =           0.000, deviation =   0.0
         utime         mean =           0.000, deviation =   0.0

    sleep 0.2            (   20 single benchmarks)
         avg_mem_usage mean =           0.000, deviation =   0.0
         avg_res_set   mean =           0.000, deviation =   0.0
         etime         mean =      200.00000m, deviation = 0.00000%
         max_res_set   mean =         2.1968k, deviation = 3.82530%
         stime         mean =           0.000, deviation =   0.0
         utime         mean =           0.000, deviation =   0.0

The produced ``run_output.yaml`` file is:

.. code:: yaml

    - attributes: {__description: sleep 0.1, description: sleep 0.1}
      data:
        max_res_set: [2148.0, 2288.0, 2152.0, 2120.0, 2340.0, 2076.0, 2152.0, 2280.0,
          2080.0, 2276.0, 2124.0, 2120.0, 2136.0, 2156.0, 2272.0, 2280.0, 2284.0, 2060.0,
          2120.0, 2136.0]
        …
    - attributes: {__description: sleep 0.2, description: sleep 0.2}
      data:
        max_res_set: [2080.0, 2284.0, 2140.0, 2124.0, 2156.0, 2096.0, 2096.0, 2284.0,
          2288.0, 2120.0, 2284.0, 2280.0, 2284.0, 2272.0, 2272.0, 2152.0, 2152.0, 2328.0,
          2152.0, 2092.0]
        …
    - property_descriptions: {avg_mem_usage: average total mem usage (in K), …}

More on the format of the result file can be found in the documentation for `temci report <temci_report.html#file-format>`_.

This documentation focuses on ``temci exec`` and its input file and options.

Presets
~~~~~~~
temci has the ``--preset`` option (and the setting ``run/exec_misc/preset``) that enables a specific
combination of plugins:

none
    no plugins are enabled, the default for non super user benchmarking
all
    Use all available plugins and render the system partially unusable by stopping all unnecessary processes, …,
    enables: :ref:`cpu_governor`, :ref:`disable_swap`, :ref:`sync`, :ref:`stop_start`, :ref:`other_nice`, :ref:`nice`,
    :ref:`disable_aslr`, :ref:`disable_ht`, :ref:`disable_intel_turbo`, :ref:`cpuset`
usable
    Use all plugins that do not affect other processes (besides restricting them to a single CPU),
    covers essentially the `benchmarking tips of the LLVM project <https://llvm.org/docs/Benchmarking.html>`_ and
    enables: :ref:`cpu_governor`, :ref:`disable_swap`, :ref:`sync`, :ref:`nice`, :ref:`disable_aslr`, :ref:`disable_ht`,
    :ref:`cpuset`, :ref:`disable_intel_turbo`.
    This preset is used by default in super user mode (with ``--sudo``option).

Important: These presets don't include the :ref:`sleep` plugin. Enable it via ``--sleep`` if needed.

An overview over all available plugins is given at :ref:`Overview`.

Runners
~~~~~~~
The runners are selected on the command line using the ``--runner`` option and the configuration file
via ``run/exec_misc/runner``. They obtain the actual measurements and are configured in the run configuration.
Configuring them in ``temci short exec`` is currently not possible.

:ref:`time<time runner>`
   Uses the GNU time utility to measure basic properties. This is the default runner. It is
   relatively imprecise but gives good ball park numbers for the performance.
:ref:`rusage<rusage runner>`
   Uses the ``getrusage`` method and a small wrapper written in C (be sure to call ``temci setup`` if
   you install temci via pip, to build the wrapper).
:ref:`perf_stat<perf_stat runner>`
   Uses ``perf stat`` for measurements, might require root privileges, allows to measure a wide
   range of properties
:ref:`output<output runner>`
   This runner obtains the measurements by parsing the output of the benchmarked program and interpreting
   it as a YAML mapping of property to measurement (``property: NUMBER`` lines).
   It can be used in combination with the :ref:`time<time runner>` and :ref:`perf_stat<perf_stat runner>` runners
   (using the ``--parse_output`` option or setting ``parse_output`` to true in the run block config).

Error Codes
~~~~~~~~~~~

==== =======================================
   0 no error
   1 at least one benchmarked program failed
 255 temci itself failed
==== =======================================

File format
-----------

The input file for ``temci exec`` consists of list of entries per run program block:

.. code:: yaml

    -
      # Optional build config to integrate the build step into the run step
      build_config:         Either(Dict(, keys=Any, values=Any, default = {})|non existent)

      # Optional attributes that describe the block
      attributes:
          description:         Optional(Str())

          # Tags of this block
          tags:         ListOrTuple(Str())

      run_config:
          # Command to benchmark, adds to run_cmd
          cmd:         Str()

          # Configuration per plugin
          time:
             …
          …

          # Command to append before the commands to benchmark
          cmd_prefix:         List(Str())

          # Execution directories for each command
          cwd:         Either(List(Str())|Str())
                      default: .

          # Disable the address space layout randomization
          disable_aslr:         Bool()

          # Override all other max runspecifications if > -1
          max_runs:         Int()
                      default: -1

          # Override all other min runspecifications if > -1
          min_runs:         Int()
                      default: -1

          # Parse the program output as a YAML dictionary of that gives for a specific property a
          # measurement. Not all runners support it.
          parse_output:         Bool()
                      default: False

          # Used revision (or revision number).-1 is the current revision, checks out the revision
          revision:         Either(Int()|Str())
                      default: -1

          # Commands to benchmark
          run_cmd:         Either(List(Str())|Str())

          # Used runner
          runner:         ExactEither()
                      default: time

          # Override min run and max runspecifications if > -1
          runs:         Int()
                      default: -1

          # Environment variables
          env:         Dict(, keys=Str(), values=Any, default = {})

          # Configuration for the output and return code validator
          validator:
              # Program error output without ignoring line breaks and spaces at the beginning
              # and the end
              expected_err_output:         Optional(Str())

              # Strings that should be present in the program error output
              expected_err_output_contains:         Either(List(Str())|Str())

              # Program output without ignoring line breaks and spaces at the beginning
              # and the end
              expected_output:         Optional(Str())

              # Strings that should be present in the program output
              expected_output_contains:         Either(List(Str())|Str())

              # Allowed return code(s)
              expected_return_code:         Either(List(Int())|Int())

              # Strings that shouldn't be present in the program output
              unexpected_err_output_contains:         Either(List(Str())|Str())

              # Strings that shouldn't be present in the program output
              unexpected_output_contains:         Either(List(Str())|Str())


A basic config file looks like:

.. code:: yaml

    - run_config:
        run_cmd: sleep 0.1
    - run_config:
        run_cmd: sleep 0.2

Common options
--------------
These options are passed in the ``run`` settings block
(see `Settings API </temci.utils.html#temci.utils.settings.Settings>`_ or directly on the command line,
flags are of the schema ``--SETTING/--no-SETTING``):

.. code:: yaml

    # Append to the output file instead of overwriting by adding new run data blocks
    append:         Bool()

    # Disable the hyper threaded cores. Good for cpu bound programs.
    disable_hyper_threading:         Bool()

    # Discard all run data for the failing program on error
    discard_all_data_for_block_on_error:         Bool()

    # First n runs that are discarded
    discarded_runs:         Int()
                default: 1

    # Possible run drivers are 'exec' and 'shell'
    driver:         ExactEither('exec'|'shell')
                default: exec

    # Input file with the program blocks to benchmark
    in:         Str()
                default: input.exec.yaml

    # List of included run blocks (all: include all)
    # or their tag attribute or their number in the
    # file (starting with 0)
    included_blocks:         ListOrTuple(Str())
                default: [all]

    # Maximum time one run block should take, -1 == no timeout,
    # supports normal time span expressions
    max_block_time:         ValidTimespan()
                default: '-1'

    # Maximum number of benchmarking runs
    max_runs:         Int()
                default: 100

    # Maximum time the whole benchmarking should take
    #    -1 == no timeout
    # supports normal time spans
    # expressions
    max_time:         ValidTimespan()
                default: '-1'

    # Minimum number of benchmarking runs
    min_runs:         Int()
                default: 20

    # Output file for the benchmarking results
    out:         Str()
                default: run_output.yaml

    # Record the caught errors in the run_output file
    record_errors_in_file:         Bool()
                default: true

    # Number of benchmarking runs that are done together
    run_block_size:         Int()
                default: 1

    # if != -1 sets max and min runs to its value
    runs:         Int()
                default: -1

    # If not empty, recipient of a mail after the benchmarking finished.
    send_mail:         Str()

    # Print console report if log_level=info
    show_report:         Bool()
                default: true

    # Randomize the order in which the program blocks are benchmarked.
    shuffle:         Bool()
                default: true

    # Store the result file after each set of blocks is benchmarked
    store_often:         Bool()

    cpuset:
        # Use cpuset functionality?
        active:         Bool()

        # Number of cpu cores for the base (remaining part of the) system
        base_core_number:         Int(range=range(0, 8))
                    default: 1

        #   0: benchmark sequential
        # > 0: benchmark parallel with n instances
        #  -1: determine n automatically (based on the number of cpu cores)
        parallel:         Int()

        # Number of cpu cores per parallel running program.
        sub_core_number:         Int(range=range(0, 8))
                    default: 1

     # Maximum runs per tag (block attribute 'tag'), min('max_runs', 'per_tag') is used
    max_runs_per_tag:         Dict(, keys=Str(), values=Int(), default = {})

    # Minimum runs per tag (block attribute 'tag'), max('min_runs', 'per_tag') is used
    min_runs_per_tag:         Dict(, keys=Str(), values=Int(), default = {})

    # Runs per tag (block attribute 'tag'), max('runs', 'per_tag') is used
    runs_per_tag:         Dict(, keys=Str(), values=Int(), default = {})

There also some exec run driver specific options:

.. code:: yaml

    # Parse the program output as a YAML dictionary of that gives for a specific property a
    # measurement. Not all runners support it.
    parse_output:         Bool()

    # Enable other plugins by default
    preset:         ExactEither('none'|'all'|'usable')
                default: none

    # Pick a random command if more than one run command is passed.
    random_cmd:         Bool()
                default: true

    # If not '' overrides the runner setting for each program block
    runner:         ExactEither(''|'perf_stat'|'rusage'|'spec'|'spec.py'|'time'|'output')


Note that the shell run driver is essentially an exec run driver.

Number of runs
~~~~~~~~~~~~~~
The number of runs per block is either fixed by the ``runs`` settings that apply or is between
the applying ``min_runs`` and ``max_runs`` setting. In the latter case, the benchmarking of a program
block is stopped if there is some of significance in the benchmarking results compared to all
other benchmarked programs.


Runners
-------
The runners are selected on the command line using the ``--runner`` option and the configuration file
via ``run/exec_misc/runner``. They are configured in the run configuration file using the settings
block named like the runner in each run block.

time runner
~~~~~~~~~~~

Uses the GNU ``time`` tool and is mostly equivalent to the rusage runner but more user friendly.

The runner is configured by modifying the ``time`` property of a run configuration.
This configuration has the following structure:

.. code:: yaml

    # Measured properties that are included in the benchmarking results
    properties:         ValidTimePropertyList()
                default: [utime, stime, etime, avg_mem_usage, max_res_set, avg_res_set]

The measurable properties are:

utime
    user CPU time used (in seconds)
stime
    system (kernel) CPU time used (in seconds)
avg_unshared_data
    average unshared data size in K
etime
    elapsed real (wall clock) time (in seconds)
major_page_faults
    major page faults (required physical I/O)
file_system_inputs
    blocks wrote in the file system
avg_mem_usage
    average total mem usage (in K)
max_res_set
    maximum resident set (not swapped out) size in K
avg_res_set
    average resident set (not swapped out) size in K
file_system_output
    blocks read from the file system
cpu_perc
    percent of CPU this job got (total cpu time / elapsed time)
minor_page_faults
    minor page faults (reclaims; no physical I/O involved)
times_swapped_out
    times swapped out
avg_shared_text
    average amount of shared text in K
page_size
    page size
invol_context_switches
    involuntary context switches
vol_context_switches
    voluntary context switches
signals_delivered
    signals delivered
avg_unshared_stack
    average unshared stack size in K
socket_msg_rec
    socket messages received
socket_msg_sent
    socket messages sent

This runner is implemented in the `TimeExecRunner <temci.run.html#temci.run.run_driver.TimeExecRunner>`_
class.

Supports the ``parse_output`` option.

rusage runner
~~~~~~~~~~~~~

Uses the ``getrusage`` method and a small wrapper written in C (be sure to call ``temci setup``
if you install temci via pip, to build the wrapper).

The runner is configured by modifying the ``rusage`` property of a run configuration.
This configuration has the following structure:

.. code:: yaml

    # Measured properties that are stored in the benchmarking result
    properties:         ValidRusagePropertyList()
                default: [idrss, inblock, isrss, ixrss,
                          majflt, maxrss, minflt,
                          msgrcv, msgsnd, nivcsw, nsignals,
                          nswap, nvcsw, oublock, stime, utime]

The measurable properties are:

utime
    user CPU time used
stime
    system CPU time used
maxrss
    maximum resident set size
ixrss
    integral shared memory size
idrss
    integral unshared data size
isrss
    integral unshared stack size
nswap
    swaps
minflt
    page reclaims (soft page faults)
majflt
    page faults (hard page faults)
inblock
    block input operations
oublock
    block output operations
msgsnd
    IPC messages sent
msgrcv
    IPC messages received
nsignals
    signals received
nvcsw
    voluntary context switches
nivcsw
    involuntary context switches


This runner is implemented in the `RusageExecRunner <temci.run.html#temci.run.run_driver.RusageExecRunner>`_
class.

perf_stat runner
~~~~~~~~~~~~~~~~

This runner uses ``perf stat`` tool to obtain measurements. It might have to be installed separately 
(see `Installation <installation.html>`).
``perf stat`` allows to measure a myriad of properties but might require root privileges.

The runner is configured by modifying the ``perf_stat`` property of a run configuration.
This configuration has the following structure:

.. code:: yaml

    # Limit measurements to CPU set, if cpusets are enabled
    limit_to_cpuset:         Bool()
                default: true

    # Measured properties. The number of properties that can be measured at once is limited.
    properties:         List(Str())
                default: [wall-clock, cycles, cpu-clock, task-clock,
                          instructions, branch-misses, cache-references]

    # If runner=perf_stat make measurements of the program repeated n times. Therefore scale the number of
    # times a program is benchmarked.
    repeat:         Int()
                default: 1

The measureable properties can be obtained by calling ``perf list``. Common properties are given above, other
notable properties are ``cache-misses`` and ``branch-misses``. The ``wall-clock`` property is obtained by
parsing the non-csv style output of ``perf stat`` which is fragile.


This runner is implemented in the `PerfStatExecRunner <temci.run.html#temci.run.run_driver.PerfStatExecRunner>`_
class.

Supports the ``parse_output`` option.

output runner
~~~~~~~~~~~~~

This runner obtains the measurements by parsing the output of the benchmarked program and interpreting
it as a YAML mapping of property to measurement (``property: NUMBER`` lines).

It can be used in combination with the :ref:`time<time runner>` and the :ref:`perf_stat<perf_stat runner>` runner,
(using the ``--parse_output`` option). Allowing to benchmark a command and parsing its result for additional
measurements.

An example output is:

.. code:: sh

    time: 10
    load_time: 5

It also supports lists of values if the lists of all properties have the same number of elements.
This can be used return the result of multiple measurements in on call of the benchmarked program:

.. code:: sh

    time:      [11.0, 10.01, 8.5]
    load_time: [5.0,   6.7,  4.8]

This runner is implemented in the `OutputExecRunner <temci.run.html#temci.run.run_driver.OutputExecRunner>`_
class.

spec runner
~~~~~~~~~~~

*This runner might not really work and is not really used.*

Runner for SPEC like single benchmarking suites.
It works with resulting property files, in which the properties are colon separated from their values.

The runner is configured by modifying the ``spec`` property of a run configuration.
This configuration has the following structure:

.. code:: sh

    # Base property path that all other paths are relative to.
    base_path:         Str()

    # Code that is executed for each matched path.
    # The code should evaluate to the actual measured value
    # for the path. It can use the function get(sub_path: str = '')
    # and the modules pytimeparse, numpy, math, random, datetime and time.
    code:         Str()
                default: get()

    # SPEC result file
    file:         Str()

    # Regexp matching the base property path for each measured property
    path_regexp:         Str()
                default: .*

An example configuration is given in the following:

.. code:: yaml

    - attributes:
        description: spec
      run_config:
        runner: spec
        spec:
          file: "spec_like_result.yaml"
          base_path: "abc.cde.efg"
          path_regexp: 'bench\d'
          code: 'get(".min") * 60 + get(".sec") + random.random()'
    - attributes:
        description: "spec2"
      run_config:
        runner: spec
        spec:
          file: "spec_like_result.yaml"
          base_path: "abc.cde.efg"
          path_regexp: 'bench\d'
          code: 'get(".min") * 60 + get(".sec") + 0.5 * random.random()'

This runner is implemented in the `SpecExecRunner <temci.run.html#temci.run.run_driver.OutputExecRunner>`_
class.

Plugins
-------

Plugins setup the benchmarking environment (e.g. set the CPU governor, …). All their actions are reversible and
are reversed if temci aborts or finishes.

The plugins are enabled via the command line option ``--NAME``, in the configuration file
via ``run/exec_plugins/NAME_active`` or by adding the name to set of active plugins in ``run/exec_plugins/exec_active``
. A collection of them can be activated using :ref:`Presets`.

All plugins are located in the `temci.run.run_driver_plugin <temci.run.html#module-temci.run.run_driver_plugin>`_
module.

Overview
~~~~~~~~

New plugins can be added easily (see `Extending temci <extending.html#new-exec-plugin>`_) but there are multiple
plugins already available:

:ref:`cpu_governor`
    Set the cpu governor
:ref:`cpuset`
    Uses :ref:`CPUSets` to separate the CPUs used for benchmarking from the CPUs that the rest of the system runs on
:ref:`disable_aslr`
    Disable address space randomisation
:ref:`disable_cpu_caches`
    Disables the L1 and L2 caches
:ref:`disable_ht`
    Disables hyper-threading
:ref:`disable_intel_turbo`
    Disables the turbo mode on Intel CPUs
:ref:`disable_swap`
    Disables swapping data from the RAM into a backing hard drive
:ref:`drop_fs_caches`
    Drops file system caches
:ref:`env_randomize`
    Adds random environment variables to mitigate some cache alignment effects
:ref:`nice`
    Increases the CPU and IO scheduling priorities of the benchmarked program
:ref:`other_nice`
    Decreases the CPU scheduling priority of all other programs
:ref:`preheat`
    Preheats the system with a CPU bound task
:ref:`sleep`
    Keeps the system idle for some time before the actual benchmarking
:ref:`stop_start`
    Stops almost all other processes (as far as possible)
:ref:`sync`
    Synchronizes cached writes of the file system to a persistent storage

cpu_governor
~~~~~~~~~~~~
Sets the CPU governor of all CPU cores.

The governor can be configured by either using the ``--cpu_governor_governor GOVERNOR`` option or by
setting ``run/exec_plugins/cpu_governor_misc/governor``.

The default governor is ``performance`` which is recommended for benchmarks.

The available governors can be obtained by calling

.. code:: sh

    cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors

Requires root privileges.

cpuset
~~~~~~
Uses cpusets to separate the CPUs used for benchmarking from the CPUs that the rest of the system runs on.
For more information see :ref:`CPUSets`.

Requires root privileges.

disable_aslr
~~~~~~~~~~~~
Disables the address space randomisation which might lead to less variance in the benchmarks.

Requires root privileges.

disable_cpu_caches
~~~~~~~~~~~~~~~~~~
Disables the L1 and L2 caches on x86 and x86-64 architectures.
It uses a small custom kernel module (be sure to compile it via ``temci setup`` after install the appropriate
``kernel-devel`` package, see `Installation <installation.html>`_).

*Attention*: It will slow down your system by orders of magnitude, giving you essentially a Pentium I like processor.
Only use it for demonstration purposes.

Requires root privileges.

disable_ht
~~~~~~~~~~
Disables hyper-threading, enabling it is equivalent to using the ``disable_hyper_threading`` option
(see `Common options <temci_exec.html#common-options>`_).

It disable a number of CPU cores so that only one core per physical CPU core is active, thereby effectively
disabling hyper-threading.

Requires root privileges.

disable_intel_turbo
~~~~~~~~~~~~~~~~~~~
Disables the turbo mode on Intel CPUs. Might reduce the variance of benchmarks, as the CPUs cannot overclock partially.

Requires root privileges.

disable_swap
~~~~~~~~~~~~
Disables swapping data from the RAM into a backing hard drive. Swapping during benchmarking sessions increases the
variance as accessing data on a hard drive is significantly slower than accessing data in RAM.

Requires root privileges.

drop_fs_caches
~~~~~~~~~~~~~~
Drops the page cache, directoy entries and inodes before every benchmarking run. This might improve the usability
of the produced benchmarks for IO bound programs.

It can be either configured by using the ``run/exec_plugins/drop_fs_caches_misc`` block in the settings
or by using the command line options of the same names prefixed by ``--drop_fs_caches_``:

.. code:: yaml

    # Free dentries and inodes
    free_dentries_inodes: true

    # Free the page cache
    free_pagecache: true

Requires root privileges.

env_randomize
~~~~~~~~~~~~~
Adds random environment variables before each benchmarking run. This causes the stack frames of the called
program to be aligned differently. Can mitigate effects caused by a specific cache alignment.

It can be either configured by using the ``run/exec_plugins/env_randomize_misc`` block in the settings
or by using the command line options of the same names prefixed by ``--env_randomize_``:

.. code:: yaml

    # Maximum length of each random key
    key_max: 4096

    # Maximum number of added random environment variables
    max: 4

    # Minimum number of added random environment variables
    min: 4

    # Maximum length of each random value
    var_max: 4096

nice
~~~~
Sets the ``nice`` and ``ionice`` values (and therefore the CPU and IO scheduler priorities) of the benchmarked program
to a specific value.

It can be either configured by using the ``run/exec_plugins/nice_misc`` block in the settings
or by using the command line options of the same names prefixed by ``--nice_``:

.. code:: yaml

    # Specify the name or number of the scheduling class to use
    #   0 for none
    #   1 for realtime
    #   2 for best-effort
    #   3 for idle
    io_nice: 1

    # Niceness values range from -20 (most favorable to the process)
    # to 19 (least favorable to the process).
    nice: -15

``nice`` values lower than -15 seem to cripple Linux systems.

Requires root privileges.

other_nice
~~~~~~~~~~
Sets the ``nice`` value of processes other than the benchmarked one. Prioritises the benchmarked program over all
other processes.

It can be either configured by using the ``run/exec_plugins/other_nice_misc`` block in the settings
or by using the command line options of the same names prefixed by ``--other_nice_``:

.. code:: yaml

    # Processes with lower nice values are ignored.
    min_nice: -10

    # Niceness values for other processes.
    nice: 19

Requires root privileges.

preheat
~~~~~~~
Preheats the system with a CPU bound task (calculating the inverse of a big random matrix with numpy on all CPU cores).

The length of the preheating can be configured by either using the ``--preheat_time SECONDS`` option or by
setting ``run/exec_plugins/preheat_misc/time``.

sleep
~~~~~
Keep the system idle for some time before the actual benchmarking.

See `Gernot Heisers Systems Benchmarking Crimes <https://www.cse.unsw.edu.au/~gernot/benchmarking-crimes.html#best>`_:

    Make sure that the system is really quiescent when starting an experiment,
    leave enough time to ensure all previous data is flushed out.

stop_start
~~~~~~~~~~
Stops almost all other processes (as far as possible).

This plugin tries to stop most other processes on the system that
aren't really needed. By default most processes that are children (or
children's children, …) of a process whose name ends with "dm" are stopped.
This is a simple heuristic to stop all processes that are not vital
(i.e. created by some sort of display manager). SSH and X11 are stopped
too.

Advantages of this plugin (which is used via the command line flag
``--stop_start``):

* No one can start other programs on the system (via ssh or the user interface)
* → fewer processes can interfere with the benchmarking
* Noisy processes like Firefox don't interfere with the benchmarking as they are stopped,
  this reduces the variance of benchmarks significantly

Disadvantages:

* You can't interact with the system (therefore use the send\_mail option to get mails after the benchmarking finished)
* Not all processes that could be safely stopped are stopped as this decision is hard to make
* You can't stop the benchmarking as all keyboard interaction is disabled (by stopping X11)
* You might have to wait several minutes to be able to use your system after the benchmarking ended

Stopping a process here means to send a process a SIGSTOP signal and
resume it by sending a SIGCONT signal later.


It can be either configured by using the ``run/exec_plugins/stop_start_misc`` block in the settings
or by using the command line options of the same names prefixed by ``--stop_start_``:

.. code:: yaml

    # Each process which name (lower cased) starts with one of the prefixes is not ignored.
    # Overrides the decision based on the min_id.
    comm_prefixes: [ssh, xorg, bluetoothd]

    # Each process which name (lower cased) starts with one of the prefixes is ignored.
    # It overrides the decisions based on comm_prefixes and min_id.
    comm_prefixes_ignored: [dbus, kworker]

    # Just output the to be stopped processes but don't actually stop them?
    dry_run: false

    # Processes with lower id are ignored.
    min_id: 1500

    # Processes with lower nice values are ignored.
    min_nice: -10

    # Suffixes of processes names which are stopped.
    subtree_suffixes: [dm, apache]

Requires root privileges.

sync
~~~~
Synchronizes cached writes of the file system to a persistent storage by calling ``sync``.

CPUSets
-------

The idea is to separate the benchmarked program from all other programs running on the system.

The usage of cpusets can be configured by using the following settings that are part of ``run/cpuset`` and
can also be set using the options with the same names prefixed with ``--cpuset_``:

.. code:: yaml

    # Use cpuset functionality?
    active:         Bool()

    # Number of cpu cores for the base (remaining part of the) system
    base_core_number:         Int(range=range(0, 8))
                default: 1

    #  0: benchmark sequential
    # > 0: benchmark parallel with n instances
    #  -1: determine n automatically, based on the number of CPU cores
    parallel:         Int()

    # Number of cpu cores per parallel running program.
    sub_core_number:         Int(range=range(0, 8))
                default: 1

This functionality can also be enabling by using the ``--cpuset`` flag or by enabling the :ref:`cpuset` plugin.