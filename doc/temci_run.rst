temci run
=========


Fancy Plugins
-------------

DisableCaches
~~~~~~~~~~~~~

Build it via "temci setup". Needs the kernel develop packet of you're
distribitution. It's called ``kernel-devel`` on fedora.

*Attention*: Everything takes very very long. It might require a restart
of you're system. Example for the slow down: A silly haskell program
(just printing ``"sdf"``): the measured task-clock went from just 1.4
seconds to 875,2 seconds. The speed up with caches is 62084%.

StopStart
~~~~~~~~~

This plugin tries to stop most other processes on the system, that
aren't really needed. By default most processes that are children (or
children's children, …) of a process which ends with "dm" are stopped.
This is a simple heuristic to stop all processes that are not vital
(e.i. created by some sort of display manager). SSH and X11 are stopped
too.

The advantages of this plugin (which is used via the command line flag
``--stop_start``): - No one can start other programs on the system (via
ssh or the user interface) => less other processes interfere with the
benchmarking - Processes like firefox don't interfere with the
benchmarking as they are stopped - It reduces the variance of benchmarks
significantly

Disadvantages: - You can't interact with the system (therefore use the
send\_mail option to get mails after the benchmarking finished) - Not
all processes that could be safely stopped are stopped as this decision
is hard to make - You can't stop the benchmarking as all keyboard
interaction is disabled (by stopping X11)

Stopping a process here means to send a process a SIGSTOP signal and
resume it by sending a SIGCONT signal later.