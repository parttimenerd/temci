.. title:: temci

temci
=====

.. image:: https://github.com/parttimenerd/temci/actions/workflows/test.yml/badge.svg
    :target: https://github.com/parttimenerd/temci/actions/workflows/test.yml

.. image:: https://readthedocs.org/projects/temci/badge/?version=latest&style=plain
    :target: https://temci.readthedocs.org

An advanced benchmarking tool written in Python 3 that supports
`setting up an environment for benchmarking <https://temci.readthedocs.io/en/latest/temci_exec.html#plugins>`_
and the generation of `visually appealing reports <http://mostlynerdless.de/files/report_readme/report.html>`_.

It runs on Linux systems and (rudimentarily) on macOS.

Why should you use temci?
-------------------------

temci allows you to easily measure the execution time (and other things)
of programs and compare them against each other resulting in a pretty
HTML5 based report. Furthermore it can set up the environment to ensure
benchmarking results with a low variance. The latter feature can be used
without using temci for benchmarking
by using `temci short shell <https://temci.readthedocs.io/en/latest/temci_shell.html>`_.

Usage
-----

The main commands of temci are `temci exec <https://temci.readthedocs.io/en/latest/temci_exec.html>`_ and
`temci report <https://temci.readthedocs.io/en/latest/temci_report.html>`_.

Suppose you want to see whether grepping for the strings that consist of ``a`` and ``b`` in the current
folder is slower than for strings that consist only of ``a``.

First we have to install temci (using `Nix <https://nixos.org/nix/>`_, see below for more instructions):

.. code:: sh

    nix-env -f https://github.com/parttimenerd/temci/archive/master.tar.gz -i

After this, we can benchmark both commands with temci:

.. code:: sh

    # benchmark both commands 20 times
    temci short exec "grep '[ab]*' -R ." "grep 'a*' -R ." --runs 10

    # append --watch to get report (in which you can move with the arrow keys and scroll)
    # after every benchmark completed (use --watch_every to decrease interval)
    temci short exec "grep '[ab]*' -R ." "grep 'a*' -R ." --runs 10 --watch

    # if you want to improve the stability your benchmarks, run them with root privileges
    # the benchmarked programs are run with your current privileges
    temci short exec "grep '[ab]*' -R ." "grep 'a*' -R ." --runs 10 --sudo --preset usable

This results in a ``run_output.yaml`` file that should look like:

.. code:: yaml

    - attributes: {description: 'grep ''[ab]*'' -R .'}
      data:
        etime: [0.03, 0.02, 0.02, 0.03, 0.03, 0.03, 0.02, 0.03, 0.03, 0.02]
        … # other properties
    - attributes: {description: grep 'a*' -R .}
      data:
        etime: [0.02, 0.03, 0.02, 0.03, 0.03, 0.02, 0.03, 0.03, 0.02, 0.02]
        … # other properties
    - property_descriptions: {etime: elapsed real (wall clock) time, … }

For more information on the support measurement tools (like
`perf stat <https://temci.readthedocs.io/en/latest/temci_exec.html#perf-stat-runner>`_ and
`rusage <https://temci.readthedocs.io/en/latest/temci_exec.html#rusage-runner>`_),
the supported `plugins for setting up the environment <https://temci.readthedocs.io/en/latest/temci_exec.html#plugins>`_
and more, see `temci exec <https://temci.readthedocs.io/en/latest/temci_exec.html>`_.

We can now create a report from these benchmarking results using
`temci report <https://temci.readthedocs.io/en/latest/temci_report.html>`_.
We use the option ``--properties`` to include only the elapsed time in the
report to keep the report simple:


.. code:: sh

    > temci report run_output.yaml --properties etime
    Report for single runs
    grep '[ab]*' -R .    (   10 single benchmarks)
         etime mean =     2(6).(000)m, deviation = 18.84223%

    grep 'a*' -R .       (   10 single benchmarks)
         etime mean =     2(5).(000)m, deviation = 20.00000%

    Equal program blocks
         grep '[ab]*' -R .  ⟷  grep 'a*' -R .
             etime confidence =        67%, speed up =      3.85%

We see that there is no significant difference between the two commands.

There are multiple reporters besides the default
`console reporter <https://temci.readthedocs.io/en/latest/temci_report.html#console>`_.
Another reporter is the `html2 reporter <https://temci.readthedocs.io/en/latest/temci_report.html#html2>`_
that produces an HTML report, use it by adding the ``--reporter html2`` option:

.. image:: http://mostlynerdless.de/files/report_readme/html_report.png
    :target: http://mostlynerdless.de/files/report_readme/report.html

Installation
------------

The simplest way is to use the `Nix package manager <https://nixos.org/nix/>`_, after installing Nix, run:

.. code:: sh

          nix-env -f https://github.com/parttimenerd/temci/archive/master.tar.gz -i

Using pip requiring at least Python 3.6:

.. code:: sh

        sudo pip3 install temci

For more information see the Installation_ page.


Auto completion
~~~~~~~~~~~~~~~

Temci can generate auto completion files for bash and zsh. Add the following line to your `.bashrc` or `.zshrc`:

.. code:: sh

    . `temci_completion $0`


Using temci to set up a benchmarking environment
------------------------------------------------
Use the ``temci short shell COMMAND`` to run a command (``sh`` by default) in a shell that is inside
the benchmarking environment. Most options of ``temci short exec`` are supported.
For more information, see `temci shell <https://temci.readthedocs.io/en/latest/temci_shell.html>`_.


Why is temci called temci?
--------------------------

The problem in naming programs is that most good program names are
already taken. A good program or project name has (in my opinion) the
following properties:

* it shouldn't be used on the relevant platforms (in this case: github and pypi)
* it should be short (no one wants to type long program names)
* it should be pronounceable
* it should have at least something to do with the program

temci is such a name. It's lojban for time (i.e. the time duration between two moments or events).


Contributing
------------

`Bug reports <https://github.com/parttimenerd/temci/issues>`_ and
`code contributions <https://github.com/parttimenerd/temci>`_ are highly appreciated.

For more information, see the `Contributing <https://temci.readthedocs.io/en/latest/contributing.html>`_ page.


.. _Installation: https://temci.readthedocs.io/en/latest/installation.html

.. _Resources: https://temci.readthedocs.io/en/latest/resources.html
