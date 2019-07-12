Installation
============
This page covers the installation and updating of temci.

System Requirements
-------------------

* Linux or OS X (see `Supported Operating Systems <temci.run.html>`_)
* Processor with an x86 or AMD64 architecture (although most features should work on ARM too)

Using Nix
---------

The simplest way is to use the `Nix package manager <https://nixos.org/nix/>`_, after installing nix, run:

.. code:: sh

          nix-env -f https://github.com/parttimenerd/temci/archive/master.tar.gz -i

This method has the advantage that nix downloads a suitable python3 interpreter and all packages likes
matplotlib that could otherwise cause problems. The nix install also runs all the test cases, to ensure
that temci works properly on your system.

To install temci from source run:

.. code:: sh

    git clone https://github.com/parttimenerd/temci
    cd temci
    nix build -f .

``nix-build -f .`` can also be used to re-run all test cases and to update your install after updating the git repository.

Using pip3
----------

There is also the traditional way of using pip, requiring at least python3.6.

Temci depends on the existence of some packages that cannot be installed properly using pip and have to be installed manually:

.. code:: sh

    # on debian/ubuntu/…
    time python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy linux-tools-`uname -r`
    # on fedora
    time python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy perf
    # on OS X (using homebrew)
    gnu-time

The Linux packages can be installed by calling the ``install_packages.sh`` script.

After installing these packages, temci can be installed by calling:

.. code:: sh

        pip3 install git+https://github.com/parttimenerd/temci.git

A package called temci exists on pypi, but temci depends on an unpublished version of the ``click`` library that is only available on
github. This should change in the near future when the version 8.0 of ``click`` is published.

To install temci from source run:

.. code:: sh

    git clone https://github.com/parttimenerd/temci
    cd temci
    pip3 install -e

Post Installation
~~~~~~~~~~~~~~~~~
Run the following command after the installation to compile some binaries needed for the ``rusage`` runner or
the disabling of caches:

.. code:: sh

   temci setup

This requires ``gcc`` and ``make`` to be installed.

Optional Requirements
---------------------

Requirements that aren't normally needed are the following:

- ``kernel-devel`` packages (for compiling the kernel module to disable caches)
- ``pdflatex`` (for ``pdf`` report generation)

Temci runs perfectly fine without them if you are not using the mentioned features.


Auto Completion
~~~~~~~~~~~~~~~

Temci can generate auto completion files for bash and zsh, run the following to use it for your respective shell:

.. code:: sh

    . `temci_completion [bash|zsh]`
