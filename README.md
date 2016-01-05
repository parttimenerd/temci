temci
=====
An advanced benchmarking tool.


Requirements
------------
- python3
    - numpy and scipy
- super user rights (for some run stuff)
- linux (other oses aren't supported)
    - tested with Fedora 23 and Ubuntu 15.10
- git
- perf stat
- gcc
- (pdf)latex (for report generation)

Testing
-------
The initial goal was to develop this application in a test driven way.
But as testing is only reasonable for non UI and non OS interacting code,
automatic testing is only feasible for a small amount of code.
Therefore the code is extensively tested by hand.

Installing
----------
First you have to install numpy, scipy, perf stat and latex (most linux distros use texlive)
if they aren't installed already.
Also install the cset tool from https://github.com/lpechacek/cpuset.
Then you can install temci from source:
```
    cd FOLDER_THIS_README_LIES_IN
    pip3 install .
```
To simplify using temci, enable tab completion for your favorite shell (bash and zsh are supported):
```
    temci completion [bash|zsh]
    source /tmp/temci_[bash|zsh]_completion.sh
```

Usage
-----


To build haskell projects randomized (or any other compiled language that is not
directly supported by gcc) you'll to tell the compiler to use the gcc or the gnu as tool.
This is e.g. possible with ghc's "-pgmc" option.
