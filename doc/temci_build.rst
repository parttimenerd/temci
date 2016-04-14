temci build
===========

Some random notes about using ``temci build`` that should later be
transformed in an actual description.

Haskell support for assembly randomisation.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build haskell projects randomized (or any other compiled language
that is not directly supported by gcc) you'll to tell the compiler to
use the gcc or the gnu as tool. This is e.g. possible with ghc's "-pgmc"
option.
