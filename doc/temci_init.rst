temci init
==========

Commands to create documented sample config files. Accepts the option ``--settings FILE`` to configure a backing
settings file.

temci init settings
    Creates a sample settings file with all the default (and currently applied) settings. Might be used to
    update a settings file for a new version of temci.
temci init build_config
    Creates a sample build configuration file, for more information on the format see `temci build <temci_build.html#file-format>`_.
temci init run_config
    Creates a sample exec configuration, for more information on the format see `temci exec <temci_exec.html#file-format>`_