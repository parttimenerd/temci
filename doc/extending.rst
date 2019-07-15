Extending temci
===============

Temci can be extended by either editing the code of temci directly or by placing the code in a file in your
local ``~/.temci`` folder or in a folder that is passed to temci via the ``TEMCI_PLUGIN_PATH`` variable.

This page documents how to implement new reporters, runners and run plugins and how to use temci directly as
a library.

Usage as a Library
------------------
temci can be used in library mode by importing via

.. code:: python

    import temci.utils.library_init


New Reporter
------------
New reporters can be added be creating a subclass of `AbstractReporter <temci.report.html#temci.report.report.AbstractReporter>`_.
Adding a new reporter can be useful to integrate temci into other tools. It has the advantage over using temci as a
library that it is directly integrated into the cli and the settings framework.

The following is an implementation of a sample reporter that outputs some benchmarking information as JSON.
This reporter is based on the ``codespeed`` reporter:

.. code:: python3

    @register(ReporterRegistry, "json", Dict({
        # define the settings for this reporter
        # currently every setting has to have a valid default value
        "project": Str() // Default("") // Description("Project name reported to codespeed."),
    })) # the register call registers the reporter
    class JSONReporter(AbstractReporter):
        """
        Outputs the benchmarking information with some meta data on the command line.
        """

        def report(self):
            """
            Create a report and output it as configured.
            """
            import json
            self.meta = {
                "project": self.misc["project"]  # access the settings specific to this reporter
            }
            data = [self._report_prop(run, prop)
                    # iterate overall recorded properties of all run programs
                    for run in self.stats_helper.runs
                    for prop in sorted(run.get_single_properties()]
            json.dump(data, sys.stdout)

        def _report_prop(self, run: RunData, prop: SingleProperty) -> dict:
            return {
                **self.meta,
                "benchmark": "{}: {}".format(run.description(), prop.property),
                "result_value": prop.mean(),
                "std_dev": prop.stddev(),
                "min": prop.min(),
                "max": prop.max(),
            }

For more information, consider looking into the documentation of the `report module <temci.report.html>`_.

New Runner
~~~~~~~~~~

Before implementing a new runner, you should consider whether using the ``output`` runner is enough.
The output runner parses the output of the benchmarked programs as a list of ``property: value`` mappings, e.g.
the output of a program could be `time: 10000.0`.

Implementing a new runner offers more flexibility, but is also slightly more work. A runner can be implemented
by extending the `ExecRunner <temci.run.html#temci.run.run_driver.ExecRunner>`_ class.

A good example is the `OutputRunner <temci.run.html#temci.run.run_driver.OutputRunner>`_ itself, with some added
documentation:

.. code:: python

    @ExecRunDriver.register_runner()  # register the runner
    class OutputExecRunner(ExecRunner):
        """
        Parses the output of the called command as YAML dictionary (or list of dictionaries)
        populate the benchmark results (string key and int or float value).
        For the simplest case, a program just outputs something like `time: 1000.0`.
        """

        name = "output"   # name of the runner
        misc_options = Dict({})
        # settings of the runner, these can be set under `run/exec/NAME_misc` in the settings file

        def __init__(self, block: RunProgramBlock):
            """
            Creates an instance.

            :param block: run program block to measure
            """
            super().__init__(block)

        def setup_block(self, block: RunProgramBlock, cpuset: CPUSet = None, set_id: int = 0):
            """
            Configure the passed copy of a run program block (e.g. the run command).

            The parts of the command between two `$SUDO$` occurrences is run with
            super user privileges if in `--sudo` mode.

            :param block:  modified copy of a block
            :param cpuset: used CPUSet instance
            :param set_id: id of the cpu set the benchmarking takes place in
            """
            pass

        def parse_result_impl(self, exec_res: ExecRunDriver.ExecResult,
                         res: BenchmarkingResultBlock = None) -> BenchmarkingResultBlock:
            """
            Parse the output of a program and turn it into benchmarking results.
            :param exec_res: program output
            :param res:      benchmarking result to which the extracted results should be added
                             or None if they should be added to an empty one
            :return: the modified benchmarking result block
            """
            res = res or BenchmarkingResultBlock()
            # schema for the output of a program
            dict_type = Dict(key_type=Str(),
                             value_type=Either(Int(), Float(), List(Either(Int(), Float()))),
                             unknown_keys=True)
            output = yaml.safe_load(exec_res.stdout.strip())
            if isinstance(output, dict_type):
                res.add_run_data(dict(output))
            elif isinstance(output, List(dict_type)):
                for entry in list(output):
                    res.add_run_data(entry)
            else:
                raise BenchmarkingError("Not a valid benchmarking program output: {}"
                                        .format(exec_res.stdout))
            return res

        def get_property_descriptions(self) -> t.Dict[str, str]:
            """
            Returns a dictionary that maps some properties to their short descriptions.
            """
            return {}

New exec Plugin
~~~~~~~~~~~~~~~

New plugins for setting up the benchmarking environment can be developed by extending the
`AbstractRunDriverPlugin <temci.run.html#temci.run.run_driver_plugin.AbstractRunDriverPlugin>`_ class.

A simple example is the `DisableSwap` plugin:

.. code:: python3

    # register the plugin and state the configuration
    @register(ExecRunDriver, "disable_swap", Dict({}))
    class DisableSwap(AbstractRunDriverPlugin):
        """
        Disables swapping on the system before the benchmarking and enables it after.
        """

        needs_root_privileges = True

        def setup(self):  # called before the whole benchmarking starts
            self._exec_command("swapoff -a")

        def teardown(self):  # called after the benchmarking (and on abort)
            self._exec_command("swapon -a")
