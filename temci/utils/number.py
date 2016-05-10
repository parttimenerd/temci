from typing import Union, Optional
import math

Number = Union[int, float]
""" Numeric type """


def format_number(number: Number, deviation: float,
                  parentheses: bool = True, explicit_deviation: bool = False,
                  is_deviation_absolute: bool = False,
                  min_decimal_places: int = 3,
                  max_decimal_places: Optional[int] = None,
                  omit_insignificant_decimal_places: bool = True,
                  scientic_notation: bool = False,
                  scientic_notation_steps: int = 3,
                  scientific_notation_decimal_places: int = None,
                  scientific_notation_si_prefixes: bool = True,
                  force_min_decimal_places: bool = False,
                  relative_to_deviation: bool = False) -> str:
    """
    Format the passed number

    :param number: formatted number
    :param deviation: standard deviation associated with the number
    :param parentheses: show parentheses around non significant digits?
    :param explicit_deviation: show the absolute deviation, e.g. "100±456.4"
    :param is_deviation_absolute: is the given deviation absolute?
    :param min_decimal_places: the minimum number of shown decimal places if decimal places are shown
    :param max_decimal_places: the maximum number of decimal places
    :param omit_insignificant_decimal_places: omit insignificant decimal places
    :param scientic_notation: use the exponential notation, i.e. "10e3" for 1000
    :param scientic_notation_steps: steps in which the exponential part is incremented
    :param scientific_notation_decimal_places: number of decimal places that are shown in the scientic notation
    :param scientific_notation_si_prefixes: use si prefixes instead of "e…"
    :param force_min_decimal_places: don't omit the minimum number of decimal places if insignificant?
    :param relative_to_deviation: format the number relative to its deviation, i.e. "10\sigma"
    :return: the number formatted as a string
    """
    """
    :param number: number to format
    :param deviation: relative standard deviation associated with the number
    :param parentheses: show parantheses around non significant digits?
    :param explicit_deviation:

    """
    prefix = ""
    if number < 0:
        number = abs(number)
        prefix = "-"
    kwargs = {
        "number": number,
        "deviation": deviation,
        "explicit_deviation": explicit_deviation,
        "parentheses": parentheses,
        "is_deviation_absolute": is_deviation_absolute,
        "min_decimal_places": min_decimal_places,
        "max_decimal_places": max_decimal_places,
        "omit_insignificant_decimal_places": omit_insignificant_decimal_places,
        "force_min_decimal_places": force_min_decimal_places,
        "relative_to_deviation": relative_to_deviation,
        "scientific_notation": scientic_notation,
    }
    if explicit_deviation:
        return prefix + _format_number(**kwargs)
    if scientic_notation:
        #kwargs["scientic_notation_steps"] = scientic_notation_steps
        #kwargs["scientific_notation_decimal_places"] = scientific_notation_decimal_places
        return prefix + format_number_sn(scientic_notation_steps=scientic_notation_steps,
                                         decimal_places=scientific_notation_decimal_places,
                                         si_prefixes=scientific_notation_si_prefixes,
                                         **kwargs)
    else:
        return prefix + _format_number(**kwargs)



def _format_number(number: Number, deviation: float,
                   parentheses: bool = True, explicit_deviation: bool = False,
                   is_deviation_absolute: bool = False,
                   min_decimal_places: int = 3,
                   max_decimal_places: Optional[int] = None,
                   omit_insignificant_decimal_places: bool = True,
                   force_min_decimal_places: bool = False,
                   relative_to_deviation: bool = False,
                   scientific_notation: bool = False,
                   scientific_notation_si_prefixes: bool = True) -> str:
    app = ""
    if relative_to_deviation:
        app = "𝜎"
        if is_deviation_absolute:
            number /= deviation
        else:
            number = 1 / deviation
        deviation = 1
    if not is_deviation_absolute:
        deviation = number * deviation
    if explicit_deviation:
        num = format_number(number, deviation, parentheses, explicit_deviation=False,
                            is_deviation_absolute=True, min_decimal_places=min_decimal_places,
                            max_decimal_places=max_decimal_places,
                            omit_insignificant_decimal_places=omit_insignificant_decimal_places,
                            force_min_decimal_places=force_min_decimal_places,
                            relative_to_deviation=relative_to_deviation,
                            scientic_notation=scientific_notation,
                            scientific_notation_si_prefixes=scientific_notation_si_prefixes)
        dev = format_number(deviation, deviation, parentheses=False, explicit_deviation=False,
                            is_deviation_absolute=True, min_decimal_places=min_decimal_places,
                            max_decimal_places=max_decimal_places,
                            omit_insignificant_decimal_places=omit_insignificant_decimal_places,
                            force_min_decimal_places=force_min_decimal_places,
                            relative_to_deviation=relative_to_deviation,
                            scientic_notation=scientific_notation,
                            scientific_notation_si_prefixes=scientific_notation_si_prefixes)
        return num + "±" + dev
    last_sig = _last_significant_digit(number, deviation)

    num = ""

    # format the integer part
    if last_sig <= 0 or not parentheses:   # integer part is significant
        num = str(int(number))
    else:
        num = str(int(number))
        num = num[0:len(num) - last_sig] + "(" + num[len(num) - last_sig:] + ")"

    # format the decimal part
    if last_sig >= 0: # decimal part is insignificant
        if not omit_insignificant_decimal_places or force_min_decimal_places:
            decimal_places = 0
            if force_min_decimal_places:
                decimal_places = min_decimal_places
            dec_part = "{{:.{}f}}".format(decimal_places).format(number - math.floor(number))[2:]
            num += "."
            if parentheses:
                num += "(" + dec_part + ")"
            else:
                num += dec_part
    else:
        dec_digits = min_decimal_places
        if not omit_insignificant_decimal_places or force_min_decimal_places:
            dec_digits = max(abs(last_sig), min_decimal_places)
        if max_decimal_places is not None:
            dec_digits = min(dec_digits, max_decimal_places)
        dec_part = "{{:.{}f}}".format(dec_digits)
        dec_part = dec_part.format(number - math.floor(number))[2:]
        num += "."
        if parentheses and len(dec_part[abs(last_sig):]) > 0:
            num += dec_part[0:abs(last_sig)] + "(" + dec_part[abs(last_sig):] + ")"
        else:
            num += dec_part
    return num + app



def format_number_sn(number: Number, scientic_notation_steps: int = 3,
                     deviation: Optional[float] = None, decimal_places: int = None,
                     si_prefixes: bool = True, **kwargs):
    if si_prefixes:
        decimal_places = 3
    sig = _first_digit(number) // scientic_notation_steps
    p = math.pow(10, sig * scientic_notation_steps)
    decimal_places = decimal_places or (3 if isinstance(number, float) or p >= 1000 else 0)
    number /= p
    if deviation and ("is_deviation_absolute" in kwargs
                                  and kwargs["is_deviation_absolute"]):
        deviation /= p
    fmt = "%.{}f".format(decimal_places) % number
    e = "e" + str(sig * scientic_notation_steps)
    if si_prefixes:
        e = _number_to_si_prefix(sig * 3)
    kwargs["scientific_notation"] = False
    if deviation:
        fmt = _format_number(number, deviation=deviation, **kwargs)
    if sig != 0:
        fmt += e
    return fmt


def _number_to_si_prefix(exponent: int) -> str:
    assert exponent % 3 == 0 and exponent <= 24 and exponent >= -24
    return ["Y", "Z", "E", "P", "T", "G", "M", "k",
            "", "m", "µ", "n", "f", "a", "z", "y"][int((24 - exponent) / 3)]


def _last_significant_digit(number: Number, abs_deviation: float) -> int:
    """
    Calculates the position down to which the passed number is significant.
    […][2][1][0].[-1][-2][…]
    """
    sig_num = 0
    if abs_deviation == 0:
        return -1
    log = math.floor(math.log10(abs_deviation))
    if abs_deviation < 5 * math.pow(10, log):
        return log
    return log + 1


def _first_digit(number: Number) -> int:
    # […][2][1][0].[-1][-2][…]
    if number == 0:
        return 0
    return math.floor(math.log10(number))