temci format
============

.. code:: sh

    temci format [OPTIONS] NUMBER [ABS_DEVIATION]

A small formatting utility, to format numbers with their standard deviation and si prefixes.

Usage Example
-------------

.. code:: sh

    > temci format 1.0 0.5
    1.(000)

    > temci format 1.56 0.005
    1.56(0)

    > temci format 1560 --scientific_notation
    1.560k

    > temci format 1560 --no-scientific_notation_si_prefixes
    1.560e3

This tool uses the number formatting module `temci.utils.number <temci.utils.html#temci.utils.number>`_.
The therein defined method `format_number <temci.utils.html#temci.utils.number.format_number>`_ can be
used to format numbers and has the same options as the tool itself.
Read `Usage as a Library <extending.html#usage-as-a-library>`_ on how to use the module in a project other
than temci.

Options
-------

.. code:: sh

    Usage: temci format [OPTIONS] NUMBER [ABS_DEVIATION]

    Options:
      --settings TEXT                 Additional settings file  [default: ]
      --log_level [debug|info|warn|error|quiet]
                                      Logging level  [default: info]
      --sigmas INTEGER                Number of standard deviation used for the
                                      digit significance evaluation  [default: 2]
      --scientific_notation_si_prefixes
                                      Use si prefixes instead of 'e…'  [default:
                                      True]
      --scientific_notation_si_prefixes / --no-scientific_notation_si_prefixes
                                      Use si prefixes instead of 'e…'  [default:
                                      True]
      --scientific_notation           Use the exponential notation, i.e. '10e3'
                                      for 1000  [default: True]
      --scientific_notation / --no-scientific_notation
                                      Use the exponential notation, i.e. '10e3'
                                      for 1000  [default: True]
      --percentages                   Show as percentages  [default: False]
      --percentages / --no-percentages
                                      Show as percentages  [default: False]
      --parentheses_mode [d|o]        Mode for showing the parentheses: either d
                                      (Digits are considered significant if they
                                      don't change if the number itself changes +=
                                      $sigmas * std dev) or o (digits are
                                      consideredsignificant if they are bigger
                                      than $sigmas * std dev)  [default: o]
      --parentheses                   Show parentheses around non significant
                                      digits? (If a std dev is given)  [default:
                                      True]
      --parentheses / --no-parentheses
                                      Show parentheses around non significant
                                      digits? (If a std dev is given)  [default:
                                      True]
      --omit_insignificant_decimal_places
                                      Omit insignificant decimal places  [default:
                                      False]
      --omit_insignificant_decimal_places / --no-omit_insignificant_decimal_places
                                      Omit insignificant decimal places  [default:
                                      False]
      --min_decimal_places INTEGER    The minimum number of shown decimal places
                                      if decimal places are shown  [default: 3]
      --max_decimal_places INTEGER    The maximum number of decimal places
                                      [default: 5]
      --force_min_decimal_places      Don't omit the minimum number of decimal
                                      places if insignificant?  [default: True]
      --force_min_decimal_places / --no-force_min_decimal_places
                                      Don't omit the minimum number of decimal
                                      places if insignificant?  [default: True]
      --help                          Show this message and exit.


These options can also be set in the settings file, under ``report/number``.
