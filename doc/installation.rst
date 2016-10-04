Installation
============

System Requirements
-------------------

* Linux (although Apples OS X works to a certain degree), a kernel version >= 2.6.31 is recommended
* Processor with an x86 or AMD64 architecture (although most features should work on ARM too)
* python with a version >= 3.3

Required packages
-----------------

temci depends on the existence of some packages that aren't installible via `pip`. The following commands install the normally needed packages.

On **Ubuntu** or **Debian** (or a similar distribution) execute the following command with super user privileges::

   apt-get install time linux-tools-`uname -r` gcc make

On **Fedora** (or similar distribution using the `dnf` or `yum` package manager) execute the following command with super user privileges::

   dnf install perf gcc make

or::

   yum install perf gcc make

On **Apples OS X** install at least the gnu-time package with homebrew.


Optional Requirements
---------------------

Requirements that aren't normally needed.

- kernel-devel packages (for compiling the kernel module to disable caches)
- (pdf)latex (for pdf report generation)


Installation via pip3
---------------------
Just run (with super user privileges)::

   pip3 install temci



Installation from the Git repository
------------------------------------
Just clone temci and install it via::

   git clone https://github.com/parttimenerd/temci
   cd temci
   pip3 install .

Post installation
-----------------
Run the following command after the installation to compile some binaries needed e.g. for `temci build`::

   temci setup


Tab completion for zsh or bash
------------------------------
To enable zsh or bash tab completion support for temci add::

  source `temci_completion [bash|zsh]`

to your shell's configuration file.

To regenerate the tab completions run::

  temci completion [bash|zsh]

