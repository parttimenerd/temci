temci report
============

``temci report`` supports the statistical evaluation of benchmarking runs. It processes the output file
of ``temci exec``. This page gives an overview over the different reporters and the expected format of
the input file. The creation of a new reporter is explained in `Extending temci <extending.html#new-reporter>`_.

There a currently four different reporters:

``console``
    Outputs a summary of the benchmarks on the console, the default reporter
``html2``
    Creates a HTML based report with many graphics
``csv``
    Outputs a configurable csv table
``codespeed``
    Outputs JSON as expected by the `codespeed <https://github.com/tobami/codespeed>`_ tool

Usage
-----

.. code: sh

    # using the console reporter
    > temci report run_output.yaml # see below for more examples
    Report for single runs
    sleep 0.5            (    2 single benchmarks)
         utime mean =        1.(211)m, deviation = 33.27828%

    sleep 1              (    2 single benchmarks)
         utime mean =        1.(172)m, deviation = 29.91891%

    Equal program blocks
         sleep 0.5  ⟷  sleep 1
             utime confidence =        95%, speed up =      3.26%


    # using any other reporter
    > temci report run_output.yaml --reporter [console,html2,csv,codespeed]
    …

    # pass reporter specific options either via the reporter/REPORTER_misc settings block
    # in the settings file, or via --REPORTER_SETTING
    # options common to all reporters are passed without prefix or via the reporter settings
    # block, for example to generate pdfs for all graphics and tables in the HTML2 reporter
    # use the following
    > temci report run_output.yaml --reporter html2 --html2_gen_pdf
    …

Using the html2 reporter:

.. raw:: html

    <iframe src="https://uqudy.serpens.uberspace.de/files/report/report.html" style="width: 133.3333%;
    height: 400px;
    -ms-zoom: 0.75;
    -moz-transform: scale(0.75);
    -moz-transform-origin: 0 0;
    -o-transform: scale(0.75);
    -o-transform-origin: 0 0;
    -webkit-transform: scale(0.75);
    -webkit-transform-origin: 0 0; transform: scale(0.75); transform-origin: 0 0;"></iframe>

File format
-----------

The input file for ``temci report`` consists of list of entries per run program block:

.. code:: yaml

    -
      # Optional attributes that describe the block
      attributes:
          description:         Optional(Str())

          # Tags of this block
          tags:         ListOrTuple(Str())

      data:
          property_1: List(Either(Int()|Float()))
          …

      # the run program aborted with an error
      error:
          message: Str()
          return_code': Int()
          output: Str()
          error_output: Str()

      # there was an internal error
      internal_error:
          message: Str()

      # only the error or the internal_error block can be present
      # the recorded data is the data recorded till the error occurred

    # optional property descriptions
    - property_descriptions:
          property_1: long name of property_1


Common Options
--------------
These options are passed in the ``reporter`` settings block
(see `Settings API </temci.utils.html#temci.utils.settings.Settings>`_ or directly on the command line
(flags are of the schema ``--SETTING/--no-SETTING``):

.. code:: yaml

    # Exclude all data sets that contain only NaNs.
    exclude_invalid:         BoolOrNone()
                default: true

    # Properties that aren't shown in the report.
    excluded_properties:         ListOrTuple(Str())
                default: [__ov-time]

    # Files that contain the benchmarking results
    in:         Either(Str()|ListOrTuple(Str()))
                default: run_output.yaml

    # List of included run blocks (all: include all), identified by their description
    # or tag attribute
    included_blocks:         ListOrTuple(Str())
                default: [all]

    # Replace the property names in reports with longer more descriptive versions?
    long_properties:         BoolOrNone()

    # Possible reporter are 'console', 'html2', 'csv' and 'codespeed'
    reporter:         ExactEither('console'|'html2'|'csv'|'codespeed')
                default: console

    # Produce xkcd like plots (requires the humor sans font to be installed)
    xkcd_like_plots:         BoolOrNone()

Furthermore the formatting of numbers can be partially configured using the settings file block
described in `temci format <temci_format.html>`_.

The statistical evaluation and the used properties can be configured via the ``stats`` settings block
or with the unprefixed options of the same names:

.. code:: yaml

        # Properties to use for reporting and null hypothesis tests
    properties:         ListOrTuple(Str())
                default: [all]

    # Possible testers are 't', 'ks' and 'anderson'
    tester:         ExactEither('t'|'ks'|'anderson')
                default: t

    # Range of p values that allow no conclusion.
    uncertainty_range:         Tuple(float, float)
                default: [0.05, 0.15]


Console
-------

A simple reporter that just outputs a basic analysis of the benchmarks on the command line.
It works for large result files and can compute pair-wise statistical tests.

This reporter is either configured via the ``report/console_misc`` settings block or via the
command line options of the same name (prefixed with ``console_``):

.. code:: yaml

    # 'auto': report clusters (runs with the same description)
    #         and singles (clusters with a single entry, combined) separately
    # 'single': report all clusters together as one
    # 'cluster': report all clusters separately
    # 'both': append the output of 'cluster' to the output of 'single'
    mode: auto

    # Output file name or `-` (stdout)
    out: '-'

    # Report on the failing blocks
    report_errors: true

    # Print statistical tests for every property for every two programs
    with_tester_results: true

Output for a simple benchmark (with ``--properties utime``):

.. code:: sh

    Report for single runs
    sleep 0.5            (    2 single benchmarks)
         utime mean =        1.(211)m, deviation = 33.27828%

    sleep 1              (    2 single benchmarks)
         utime mean =        1.(172)m, deviation = 29.91891%

    Equal program blocks
         sleep 0.5  ⟷  sleep 1
             utime confidence =        95%, speed up =      3.26%

The sample ``run_output.yaml`` was created via ``temci short exec 'sleep 0.5' 'sleep 1' --runs 5 --runner rusage``:

.. code:: yaml

    - attributes:
        description: sleep 0.5
      data:
        utime: [0.00145, 0.001275, 0.001518, 0.002089, 0.001971]
        # …
    - attributes:
        description: sleep 1
      data:
        utime: [0.00174, 0.000736, 0.001581, 0.00085, 0.000785]


HTML2
-----

Creates a report with many graphics (box-plots and bar-graphs) and tables that can be exported to TeX.
The produced HTML page also contains many explanations. Viewing it requires an internet connection.

Output for the simple benchmark from above (with ``--properties utime --properties maxrss``):

.. raw:: html

    <iframe src="https://uqudy.serpens.uberspace.de/files/report/report.html" style="width: 133.3333%;
    height: 400px;
    -ms-zoom: 0.75;
    -moz-transform: scale(0.75);
    -moz-transform-origin: 0 0;
    -o-transform: scale(0.75);
    -o-transform-origin: 0 0;
    -webkit-transform: scale(0.75);
    -webkit-transform-origin: 0 0; transform: scale(0.75); transform-origin: 0 0;"></iframe>


All images and tables are statically generated, this results in a large HTML file with many ressources.
It is therefore not recommended to use this reporter with a large number of benchmarking results
(benchmarked programs and properties). Rule of thumb: Only use it to analyse results comparing less than
eight programs.


This reporter is either configured via the ``report/html2_misc`` settings block or via the
command line options of the same name (prefixed with ``html2_``)

.. code:: sh

    # Alpha value for confidence intervals
    alpha: 0.05

    # Height per run block for the big comparison box plots
    boxplot_height: 2.0

    # Width of all big plotted figures
    fig_width_big: 25.0

    # Width of all small plotted figures
    fig_width_small: 15.0

    # Format string used to format floats
    float_format: '{:5.2e}'

    # Override the contents of the output directory if it already exists?
    force_override: false

    # Generate pdf versions of the plotted figures?
    gen_pdf: false

    # Generate simple latex versions of the plotted figures?
    gen_tex: true

    # Generate excel files for all tables
    gen_xls: false

    # Name of the HTML file
    html_filename: report.html

    # Show the mean related values in the big comparison table
    mean_in_comparison_tables: true

    # Show the mininmum related values in the big comparison table
    min_in_comparison_tables: false

    # Output directory
    out: report

    # Format string used to format floats as percentages
    percent_format: '{:5.2%}'

    # Show zoomed out (x min = 0) figures in the extended summaries?
    show_zoomed_out: false


CSV
---

A reporter that outputs the configurable csv table with rows for each run block.
It can be used to access the benchmarking result for further processing in other tools
without using temci as a library or creating a new reporter (see `Extending temci <extending.html#new-reporter>`_).

This reporter is either configured via the ``report/csv_misc`` settings block or via the
command line options of the same name (prefixed with ``csv_``):

.. code:: yaml

    # List of valid column specs
    # format is a comma separated list of 'PROPERTY[mod]' or 'ATTRIBUTE'
    # mod is one of: mean, stddev, property, min, max and stddev per mean
    # optionally a formatting option can be given via PROPERTY[mod|OPT1OPT2…]
    # where the OPTs are one of the following:
    #        % (format as percentage)
    #        p (wrap insignificant digits in parentheses (+- 2 std dev))
    #        s (use scientific notation, configured in report/number) and
    #        o (wrap digits in the order of magnitude of 2 std devs in parentheses).
    # PROPERTY can be either the description or the short version of the property.
    # Configure the number formatting further via the number settings in the settings file
    columns: [description]

    # Output file name or standard out (-)
    out: '-'

Output for a simple benchmark (with ``--csv_columns "utime[mean|p],utime[stddev],utime[max]"``, see `Console <temci_report.html#Console>`):

.. code:: yaml

    utime[mean|p],utime[stddev],utime[max]
    0.00(2),0.000,0.002
    0.00(1),0.000,0.002


Codespeed
---------
Reporter that outputs JSON as expected by `codespeed <https://github.com/tobami/codespeed>`_.
Branch name and commit ID are taken from the current directory. Use it like this:

.. code:: sh

    temci report --reporter codespeed ... \
       | curl --data-urlencode json@- http://localhost:8000/result/add/json/

This reporter is either configured via the ``report/codespeed_misc`` settings block or via the
command line options of the same name (prefixed with ``codespeed_``):

.. code:: sh

    # Branch name reported to codespeed. Defaults to current branch or else 'master'.
    branch: ''

    # Commit ID reported to codespeed. Defaults to current commit.
    commit_id: ''

    # Environment name reported to codespeed. Defaults to current host name.
    environment: ''

    # Executable name reported to codespeed. Defaults to the project name.
    executable: ''

    # Project name reported to codespeed.
    project: ''

Output for a simple benchmark (with ``--properties utime``, see `Console <#Console>`):

.. code:: json

    [
       {
          "project":"",
          "executable":"",
          "environment":"i44pc17",
          "branch":"master",
          "commitid":null,
          "benchmark":"sleep 0.5: utime",
          "result_value":0.0016606000000000004,
          "std_dev":0.0003140857207833556,
          "min":0.001275,
          "max":0.002089
       },
       {
          "project":"",
          "executable":"",
          "environment":"i44pc17",
          "branch":"master",
          "commitid":null,
          "benchmark":"sleep 1: utime",
          "result_value":0.0011384,
          "std_dev":0.00043076889395591227,
          "min":0.000736,
          "max":0.00174
       }
    ]