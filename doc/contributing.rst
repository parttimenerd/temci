Contributing
============

Pull requests and issues are always welcomed.

Issues
------
Issues can be submitted at `GitHub <https://github.com/parttimenerd/temci/issues>`_ and should specify the used
settings (and if possible the local ``temci.yaml`` configuration file).

New Features
------------
New features, runners, reporters, … are welcome. To learn how to extend temci, see `Extending temci <extending.html>`_.
The code can be added to the appropriate places and should be tested with a few tests.

Coding Style
------------
The code should use type annotations everywhere and use functionality of the `typecheck module <temci.utils.typecheck.html>`_
whenever there is uncertainty over the type of a variable (e.g. when reading from a YAML file).
The currently used python version 3.6, all code should run in python 3.6 and above.

Documentation
-------------
Be sure to keep the documentation up to date and document your code. The code comments are written in
`reStructuredText <http://docutils.sourceforge.net/docs/user/rst/quickref.html>`_.

Testing
-------

The tests are located in the ``tests`` folder and roughly grouped by the temci subcommand they belong to.
New features should by covered by tests.

There is also support for doctests that can be added into the documentation.

The tests are using the pytest framework and can be executed by simply calling

.. code:: sh

    ./test.sh

It recommended to install the package ``pytest-clarity`` to improve the error output.
