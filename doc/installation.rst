Installation
============
This page covers installating and updating temci.

System Requirements
-------------------

* Linux or macOS (see `Supported Operating Systems <temci.run.html>`_)
* Processor with an x86 or AMD64 architecture (although most features should work on ARM too)

Using Nix
---------

The simplest way is to use the `Nix package manager <https://nixos.org/nix/>`_. After installing Nix, run:

.. code:: sh

          nix-env -f https://github.com/parttimenerd/temci/archive/master.tar.gz -i

This method has the advantage that Nix downloads a suitable python3 interpreter and all packages like
matplotlib that could otherwise cause problems. The Nix installation also runs all the test cases, to ensure
that temci works properly on your system.

To install temci from source, run:

.. code:: sh

    git clone https://github.com/parttimenerd/temci
    cd temci
    nix-env -i -f .

``nix-env -i -f .`` can also be used to update your installation after updating the git repository. For a more
convenient development environment, see also `Temporary Python environment with nix-shell <https://github.com/NixOS/nixpkgs/blob/master/doc/languages-frameworks/python.section.md#temporary-python-environment-with-nix-shell>`_.

Using pip3
----------

There is also the traditional way of using pip, requiring at least Python 3.6.

temci depends on the existence of some packages that cannot be installed properly using pip and have to be installed manually:

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
        # From GitHub
        pip3 install git+https://github.com/parttimenerd/temci.git

        # From PyPi
        pip3 install temci

To use temci plugins that need super user privileges, e.g. cpu sets, install temci globally.

If there a problems with ``click`` (if you get an exception like ``ImportError: cannot import name 'ParameterSource'``), try installing
it directly from github:

.. code:: sh

      pip3 install https://github.com/pallets/click/archive/f537a208591088499b388b06b2aca4efd5445119.zip

To install temci from source, run:

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

Temci can generate auto completion files for bash and zsh. Add the following line to your `.bashrc` or `.zshrc`:

.. code:: sh

    . `temci_completion $0`
