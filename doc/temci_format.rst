temci format
============

A small formatting utility, to format numbers with their standard deviation and si prefixes.

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
