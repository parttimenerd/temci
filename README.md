temci
=====
An advanced benchmarking tool. Currently developed as my bachelor thesis.
Therefore expect some rough parts, but most of the features should work well.


Requirements
------------
- python3
    - numpy and scipy
    - perf (e.g. from the ubuntu package `linux-tools-generics`
- super user rights (for benchmarking, although it's possible without)
- linux (other oses aren't supported)
    - tested with Fedora 23 and Ubuntu 15.10 (most distros with a kernel version >= 3.0 should work)
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
    - latex (most linux distros use texlive) if you want to output plots as pdfs
if they aren't installed already.

Then install temci itself either via pip3:
```
    pip3 install temci
```
Or from source:
Clone this repository locally and install it via
```
    cd FOLDER_THIS_README_LIES_IN
    pip3 install .
```
If you want to use this DisableCaches Plugin or the `temci build` tool, you have to run
```
    temci setup
```


To simplify using temci, enable tab completion for your favorite shell (bash and zsh are supported):
Add the following line to your bash or zsh configuration file
```
    source `temci_completion [bash|zsh]`
```
To update the completion after an update (or after developing some plugins), run:
```
    temci completion [bash|zsh]
```
It's a variant of `temci_completion` that rebuilds the completion files every time its called.

Usage
-----
As temci has a well build command line interface with tab completion, just play
around with it. By using the zsh you get completions with descriptions.


`temci build` usage
-------------------

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