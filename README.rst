.. title:: temci

temci
=====

.. image:: https://travis-ci.org/parttimenerd/temci.svg?branch=master
    :target: https://travis-ci.org/parttimenerd/temci

An advanced benchmarking tool written in python3 that supports binary randomization and the generation of visually appealing reports.

It runs on sufficiently new Linux systems and (rudimentary) on Apple's OS X systems.

The development started as part of my bachelor thesis in October 2015. The bachelor thesis (written in German) can be found `here <https://pp.info.uni-karlsruhe.de/uploads/publikationen/bechberger16bachelorarbeit.pdf>`_.

Why should you use temci?
-------------------------

temci allows you to easily measure the execution time (and other things)
of programs and compare them against each other resulting in a pretty
HTML5 based report. Furthermore it sets up the environment to ensure
benchmarking results with a low variance and use some kind of assembly
randomisation to reduce the effect of caching.

Installation
------------

The simplest way to install temci and its dependencies on either Linux or macOS
is to use the `Nix package manager <https://nixos.org/nix/>`_. After installing
Nix, execute

.. code:: sh

          nix-env -f https://github.com/parttimenerd/temci/archive/master.tar.gz -i

Alternatively, installing temci on Linux systems should be possible by just installing it via ``pip3``::

    pip3 install temci

If this results in any problems or you're on an Apple system, visit the
Installation_ page.

Installing a version with minimal dependencies and without support for `temci init` and the HTML report generation is possible by setting the enviroment variable `MINIMAL_TEMCI` to `1` prior to the installation. This is currently done by the Nix installation and requires at least python 3.6.

Open an issue in the `issue tracker <https://github.com/parttimenerd/temci/issues>`_
if you experience any weird errors.

To simplify using temci, enable tab completion for your favorite shell
(bash and zsh are supported) by adding the following line to your bash or zsh configuration file

.. code:: sh

        source `temci_completion [bash|zsh]`


If you can't install temci via `pip3`, using it to benchmark programs is possible
by using `temci/scripts/run` instead of temci (execute this file with your favorite python3 interpreter directly if this interpreter isn't located at `/usr/bin/python3`).


Usage
-----

*Side note: This tool needs root privileges for some benchmarking
features (using the `--sudo` flag is preferred over calling temci
with sudo directly).* *If you're not root, it will not fail, but
it will warn you and disable the* *features.*

There are currently two good ways to explore the features of temci: 1.
Play around with temci using the provided tab completion for zsh
(preferred) and bash 2. Look into the annotated settings file (it can be
generated via ``temci init settings``).

A user guide is planned. Until it's finished consider reading the
`code documentation <https://temci.readthedocs.io/en/latest/temci.html>`_.

A documentation of all command line commands and options is given in
the `documentation for the cli module <https://temci.readthedocs.io/en/latest/temci.scripts.html#module-temci.scripts.cli>`_.

A documentation for all available run drivers, runners and run
driver plugins is given in the `documentation for the run module <https://temci.readthedocs.io/en/latest/temci.run.html>`_

The status of the documentation is given in the section `Status of the documentation`_.

Getting started with simple benchmarking
----------------------------------------

*Or: How to benchmarking a simple program called ls (a program is every
valid shell code that is executable by /bin/sh)*

There are two ways to benchmark a program: A short and a long one.

The short one first: Just type:

.. code:: sh

        temci short exec "ls" --runs 10 --out out.yaml

Explanation:

-  ``short`` is the category of small helper subprograms that allow to
   use some temci features without config files
-  ``ls`` is the executed program
    - this is equivalent to ``-wd "ls"``
    -  where ``-wd`` is the short option for ``--without_description`` an tells
       temci to use the program as its own description
-  ``--runs 100`` is short for ``--min_runs 100 --max_runs 100``
-  ``--min_runs 100`` tells temci to benchmark ``ls`` at least 100 times
   (the default value is currently 20)
-  ``--max_runs 100`` tells temci to benchmark ``ls`` at most 100 times
   (the default value is currently 100)
-  setting min and max runs non equal makes only sense when comparing
   two or more programs via temci
-  ``--out out.yaml`` tells temci to store the YAML result file as
   ``out.yaml`` (default is ``result.yaml``)

The long one now: Just type

.. code:: sh

        temci init run_config

This let's you create a temci run config file by using a textual
interface (if you don't want to create it entirely by hand). To actually
run the configuration type:

.. code:: sh

        temci exec [file you stored the run config in] --out out.yaml

Explanation:

-  ``exec`` is the sub program that takes a run config an benchmarks all
   the included program blocks
-  ``--out out.yaml`` tells temci where to store the YAML file
   containing the benchmarking results
-  the measured ``__ov-time`` property is just a time information used
   by temci internally

Now you have a YAML result file that has the following structure:

.. code:: yaml

    - attributes:
         description: ls
      data:
         …
         task-clock:
            - [first measurement for property task-clock]
            - …
         …

You can either create a report by parsing the YAML file yourself or by
using the temci report tool. To use the latter type:

.. code:: sh

        temci report out.yaml --reporter html2 --html2_out ls_report

Explanation:

-  ``out.yaml`` is the previously generated benchmarking result file
-  ``--reporter html2`` tells temci to use the HTML2Reporter. This
   reporter creates a fancy HTML5 based report in the folder
   ``ls_report``. The main HTML file is named ``report.html``. Other
   possible reporters are ``html`` and ``console``. The default reporter
   is ``html2``
-  ``--html2_out`` tells the HTML2Reporter the folder in which to place
   the report.

Now you have a report on the performance of ``ls``.

How to go further from here
~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  Benchmark two programs against each other either by adding a
   ``-wd [other program]`` to the command line or appending the run
   config file (also possible via ``temci init run_config``)
-  If using ``temci short exec``

   -  add a better description for the benchmarked program by using
      ``-d [DESCRIPTION] [PROGRAM]`` instead ``-wd``. ``-d`` is short
      for ``--with_description``

-  If using ``temci init run_config``:

   -  Choose another set of measured properties (e.g. to measure the L1
      cache misses)
   -  Change the used runner. The default runner is ``time`` and uses
      ``time`` (gnu time, not shell builtin) to actually measure the
      program. Other possible runners are for example ``perf_stat``,
      ``rusage`` and ``spec``:

      -  The ``perf_stat`` runner that uses the ``perf`` tool
         (especially ``perf stat``) to measure the performance and read
         performance counters.
      -  The ``rusage`` runner uses a small C wrapper around the
         ``getrusage(2)`` system call to measure things like the maximum
         resource usage (it's comparable to ``time``)
      -  The ``spec`` runner gets its measurements by parsing a SPEC
         benchmark like result file. This allows using the SPEC
         benchmark with temci.

-  Append ``--send_mail [your email adress]`` to get a mail after the
   benchmarking finished. This mail has the benchmarking result file in
   its appendix
-  Try to benchmark a failing program (e.g. "lsabc"). temci will create
   a new run config file (with the ending ".erroneous.yaml" that
   contains all failing run program blocks. Try to append the
   benchmarking result via "--append" to the original benchmarking
   result file.


Use temci as a library
~~~~~~~~~~~~~~~~~~~~~~
This is useful for example for processing the benchmarking results.
Before importing other parts of the library the module `temci.utils.library_init` has to be loaded,
which runs the necessary setup code (reading the settings file, …).

Use temci to setup a benchmarking environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Use `temci short shell COMMAND` to run a command (`sh` by default) in a shell that is inside
the benchmarking environment. Most options (like `--preset`) of `temci short exec` are
supported.


Why is temci called temci?
--------------------------

The problem in naming programs is that most good program names are
already taken. A good program or project name has (in my opinion) the
following properties: - it shouldn't be used on the relevant platforms
(in this case: github and pypi) - it should be short (no one want's to
type long program names) - it should be pronounceable - it should have
at least something to do with the program temci is such a name. It's
lojban for time (i.e. the time duration between to moments or events).


Contributing
------------

`Bug reports <https://github.com/parttimenerd/temci/issues>`_ and
`Code contributions <https://github.com/parttimenerd/temci>`_ are highly appreciated.


Basic Testing
-------------
Basic integration tests are run via `SHELLTEST=1 ./doc.sh` using a custom sphinx plugin.
There are no tests yet.

Unit Testing
------------
Install temci via `pip` and run the tests via

.. code:: sh

    pytest tests

The tests can be found in the `tests` folder and use the pytest framework.


Status of the documentation
---------------------------

===================== ========================
README/this page      Work in progress
Installation_         Finished
Resources_            Finished
===================== ========================

.. _Installation: https://temci.readthedocs.io/en/latest/installation.html

.. _Resources: https://temci.readthedocs.io/en/latest/resources.html
