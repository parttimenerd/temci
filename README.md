temci
=====
An advanced benchmarking tool. Currently developed as my bachelor thesis.
Therefore expect some rough parts, but most of the features should (hopefully) work well.

Why should you use temci?
-------------------------
temci allows you to easily measure the execution time (and other things) of programs and compare them against each other
resulting in a pretty HTML5 based report.
Furthermore it set's up the environment to ensure benchmarking results with a low variance and use some kind of assembly
randomisation to reduce the effect of caching.

System Requirements
-------------------
- at least 2 CPU cores
- x86 (other architectures aren't tested yet)

Requirements
------------
- python3
    - numpy and scipy (and some other packages), if you want to be sure install all needed ones via
        - Ubuntu or Debian:
            ```
                sudo dnf install python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy
            ```
        - Fedora (version 23):
            ```
                sudo dnf install python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy
            ```
- linux (other oses aren't supported)
    - tested with Fedora 23 and Ubuntu 15.10
    - most distros with a kernel version >= 3.0 should work

Optional Requirements
---------------------
Requirements not needed to run simple benchmarks.
- perf (e.g. from the ubuntu package `linux-tools-generics` only required if you want to use it to benchmark)
- super user rights (for benchmarking, only required if you want to use some advanced functionality)
- gcc (for compiling a needed tool for `temci build`)
- kernel-devel packages (for compiling the kernel module to disable caches, not required, see below)
- (pdf)latex (for pdf report generation)

Testing
-------
The initial goal was to develop this application in a test driven way.
But as testing is only reasonable for non UI and non OS interacting code,
automatic testing is only feasible for a small amount of code.
Therefore the code is extensively tested by hand.

Installing
----------
First you have to install

- numpy and scipy (python packages)
- latex (most linux distros use texlive) only required if you want to output plots as pdfs

If they aren't installed already.

Then install temci itself either via pip3:

```sh
    pip3 install temci
```

Or from source:
Clone this repository locally and install it via

```sh
    cd FOLDER_THIS_README_LIES_IN
    pip3 install .
```

If you want to use this DisableCaches Plugin or the `temci build` tool, you have to run

```sh
    temci setup
```


To simplify using temci, enable tab completion for your favorite shell (bash and zsh are supported):

Add the following line to your bash or zsh configuration file

```sh
    source `temci_completion [bash|zsh]`
```

To update the completion after an update (or after developing some plugins), run:

```sh
    temci completion [bash|zsh]
```

It's a variant of `temci_completion` that rebuilds the completion files every time its called.

Usage
-----
*Side note: This tool needs root privileges for some benchmarking features.*
*If you're not root, it will not fail, but only warn you and disable the*
*features.*

There are currently two good ways to explore the features of temci:
    1. Play around with temci using the provided tab completion for zsh (preferred) and bash
    2. Look into the annotated settings file (it can be generated via `temci init settings`)

A user guide is planned but a priority as it's not part of my bachelor thesis.

Geting started with simple benchmarking
---------------------------------------
*Or: How to benchmarking a simple program called ls (a program is every valid shell code that is executable by /bin/sh)*

There are two ways to benchmark a program: A short and a long one.

The short one first: Just type:

```sh
    temci short exec -wd "ls" --runs 100 --out out.yaml
```

Explanation:

- `short` is the category of small helper subprograms that allow to use some temci features without config files
- `-wd` is the short option for `--without_description` an tells temci to use the program as its own description
- `ls` is the executed program
- `--runs 100` is short for `--min_runs 100 --max_runs 100`
   - `--min_runs 100` tells temci to benchmark `ls` at least 100 times (the default value is currently 20)
   - `--max_runs 100` tells temci to benchmark `ls` at most 100 times (the default value is currently 100)
   - setting min and max runs non equal makes only sense when comparing two or more programs via temci
- `--out out.yaml` tells temci to store the YAML result file as `out.yaml` (default is `result.yaml`)

The long one now: Just type

```sh
    temci init run_config
```

This let's you create a temci run config file by using a textual interface (if you don't want to create it entirely by hand).
To actually run the configuration type:

```sh
    temci exec [file you stored the run config in] --out out.yaml
```

Explanation:

- `exec` is the sub program that takes a run config an benchmarks all the included program blocks
- `--out out.yaml` tells temci where to store the YAML file containing the benchmarking results
- the measured `__ov-time` property is just a time information used by temci internally

Now you have a YAML result file that has the following structure:

```yaml
- attributes:
     description: ls
  data:
     …
     task-clock:
        - [first measurement for property task-clock]
        - …
     …
```

You can either create a report by parsing the YAML file yourself or by using the temci report tool. To use the latter
type:

```
    temci report out.yaml --reporter html2 --html2_out ls_report
```

Explanation:

- `out.yaml` is the previously generated benchmarking result file
- `--reporter html2` tells temci to use the HTML2Reporter. This reporter creates a fancy HTML5 based report in
the folder `ls_report`. The main HTML file is named `report.html`. Other possible reporters are `html` and `console`. The default reporter is `html2`
- `--html2_out` tells the HTML2Reporter the folder in which to place the report.

Now you have a report on the performance of `ls`.

###How to go further from here
- Benchmark two programs against each other either by adding a `-wd [other program]` to the command line or appending
    the run config file (also possible via `temci init run_config`)
- If using `temci short exec`
    - add a better description for the benchmarked program by using `-d [DESCRIPTION] [PROGRAM]` instead `-wd`. `-d` is
        short for `--with_description`
- If using `temci init run_config`:
    - Choose another set of measured properties (e.g. to measure the LL1 cache misses)
    - Change the used runner. The default runner is `time` and uses `time` (gnu time, not shell builtin)
      to actually measure the program.
      Other possible runners are for example `perf_stat`, `rusage` and `spec`:
        - The `perf_stat` runner that uses the `perf` tool (especially `perf stat`) to measure the performance and read
        performance counters.
        - The `rusage` runner uses a small C wrapper around the `getrusage(2)` system call to measure things like the
        maximum resource usage (it's comparable to `time`)
        - The `spec` runner gets its measurements by parsing a SPEC benchmark like result file. This allows using
        the SPEC benchmark with temci.
- Append `--send_mail [you're email adress]` to get a mail after the benchmarking finished. This mail has the benchmarking
  result file in it's appendix
- Try to benchmark a failing program (e.g. "lsabc"). temci will create a new run config file (with the ending
".erroneous.yaml" that contains all failing run program blocks. Try to append the benchmarking
result via "--append" to the original benchmarking result file.


temci build usage
-----------------
Some random notes about using `temci build` that should later be transformed in an actual description.

###Haskell support for assembly randomisation.

To build haskell projects randomized (or any other compiled language that is not
directly supported by gcc) you'll to tell the compiler to use the gcc or the gnu as tool.
This is e.g. possible with ghc's "-pgmc" option.


Fancy Plugins
-------------

###DisableCaches

Build it via "temci setup". Needs the kernel develop packet of you're distribitution. It's called
`kernel-devel` on fedora.

_Attention_: Everything takes very very long. It might require a restart of you're system.
Example for the slow down: A silly haskell program (just printing `"sdf"`): the measured
task-clock went from just 1.4 seconds to 875,2 seconds. The speed up with caches is 62084%.

###StopStart
This plugin tries to stop most other processes on the system, that aren't really needed.
By default most processes that are children (or children's children, …) of a process which ends with "dm" are stopped.
This is a simple heuristic to stop all processes that are not vital (e.i. created by some sort of display manager).
SSH and X11 are stopped too.

The advantages of this plugin (which is used via the command line flag `--stop_start`):
    - No one can start other programs on the system (via ssh or the user interface) => less other processes interfere with the benchmarking
    - Processes like firefox don't interfere with the benchmarking as they are stopped
    - It reduces the variance of benchmarks significantly

Disadvantages:
    - You can't interact with the system (therefore use the send_mail option to get mails after the benchmarking finished)
    - Not all processes that could be safely stopped are stopped as this decision is hard to make
    - You can't stop the benchmarking as all keyboard interaction is disabled (by stopping X11)

Stopping a process here means to send a process a SIGSTOP signal and resume it by sending a SIGCONT signal later.


Why is temci called temci?
--------------------------
The problem in naming programs is that most good program names are already taken. A good program or project name
has (in my opinion) the following properties:
- it shouldn't be used on the relevant platforms (in this case: github and pypi)
- it should be short (no one want's to type long program names)
- it should be pronounceable
- it should have at least something to do with the program
temci is such a name. It's lojban for time (i.e. the time duration between to moments or events).


Contributing
------------
Bug reports are highly appreciated.

As this is the code for my bachelor thesis, actual code contributions are problematic. Whole classes or modules (like
plugins, reporters are runners can be contributed, as they pose no attribution problem (I can clearly state that
a class is written by XYZ). Other kinds of code contribution could pose problems for me.
