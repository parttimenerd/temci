import sys
import typing as t
from enum import Enum

import math
from temci.utils.typecheck import *

Number = t.Union[int, float]
""" Numeric type """


def fnumber(number: Number, rel_deviation: Number = None, abs_deviation: Number = None, is_percent: bool = False) -> str:
    return FNumber(number, rel_deviation, abs_deviation, is_percent).format()


class ParenthesesMode(Enum):

    DIGIT_CHANGE = "d"
    ORDER_OF_MAGNITUDE = "o"

    @classmethod
    def map(cls, key: t.Union[str, 'ParenthesesMode']) -> 'ParenthesesMode':
        if isinstance(key, ParenthesesMode):
            return key
        return {
            "d": ParenthesesMode.DIGIT_CHANGE,
            "o": ParenthesesMode.ORDER_OF_MAGNITUDE
        }[key]


class FNumber:
    """
    A formattable number wrapper.
    """

    settings_format = Dict({
        "parentheses": Bool() // Description("Show parentheses around non significant digits? (If a std dev is given)")
                      // Default(True),
        "min_decimal_places": NaturalNumber() // Description("The minimum number of shown decimal places "
                                                             "if decimal places are shown") // Default(3),
        "max_decimal_places": NaturalNumber() // Description("The maximum number of decimal places")
                      // Default(5),
        "scientific_notation": Bool() // Description("Use the exponential notation, i.e. '10e3' for 1000")
                      // Default(True),
        "scientific_notation_si_prefixes": Bool() // Description("Use si prefixes instead of 'e…'")
                      // Default(True),
        "omit_insignificant_decimal_places": Bool() // Description("Omit insignificant decimal places")
                      // Default(False),
        "force_min_decimal_places": Bool() // Description("Don't omit the minimum number of decimal places "
                                                          "if insignificant?") // Default(True),
        "percentages": Bool() // Description("Show as percentages") // Default(False),
        "sigmas": NaturalNumber(lambda i: i > 0) // Description("Number of standard deviation used for the digit "
                                                                "significance evaluation")
                      // Default(2),
        "parentheses_mode": ExactEither("d", "o") // Description("Mode for showing the parentheses: either "
                                                                 "d (Digits are considered significant if they "
                                                                 "don't change if the number itself changes += "
                                                                 "$sigmas * std dev) or o (digits are considered"
                                                                 "significant if they are bigger than $sigmas * std "
                                                                 "dev)")
                    // Default("o")
    })
    settings = settings_format.get_default()  # type: t.Dict[str, t.Union[int, bool]]

    def __init__(self, number: Number, rel_deviation: Number = None, abs_deviation: Number = None,
                 is_percent: bool = None, scientific_notation: bool = None,
                 parentheses_mode: t.Union[str, ParenthesesMode] = None,
                 parentheses: bool = None):
        self.number = number  # type: Number
        assert not (rel_deviation is not None and abs_deviation is not None)
        self.deviation = None  # type: t.Optional[Number]
        """ Relative deviation """
        if abs_deviation is not None:
            if number != 0:
                self.deviation = abs(abs_deviation / number)
            else:
                self.deviation = 0
        elif rel_deviation is not None:
            self.deviation = abs(rel_deviation)
        self.is_percent = is_percent if is_percent is not None else self.settings["percentages"]
        self.scientific_notation = scientific_notation if scientific_notation is not None \
                                                       else self.settings["scientific_notation"]
        self.parentheses_mode = ParenthesesMode.map(parentheses_mode if parentheses_mode is not None \
                                                                     else self.settings["parentheses_mode"])
        self.parentheses = parentheses if parentheses is not None \
                                       else self.settings["parentheses"]
    def __int__(self) -> int:
        return int(self.number)

    def __float__(self) -> float:
        return float(self.number)

    def __bool__(self):
        return bool(self.number)

    def __str__(self) -> str:
        if math.isnan(self.number):
            return str(self.number)
        dev = self.deviation
        parentheses = self.parentheses
        if dev is None or dev is 0:
            dev = 0
            parentheses = False
        num = self.number
        scientific_notation = self.scientific_notation
        if self.is_percent:
            dev *= 100.0
            num *= 100.0
            scientific_notation = False

        return format_number(num, deviation=dev, parentheses=parentheses,
                             min_decimal_places=self.settings["min_decimal_places"],
                             max_decimal_places=self.settings["max_decimal_places"],
                             scientific_notation=scientific_notation,
                             scientific_notation_si_prefixes=self.settings["scientific_notation_si_prefixes"],
                             omit_insignificant_decimal_places=self.settings["omit_insignificant_decimal_places"],
                             force_min_decimal_places=self.settings["force_min_decimal_places"],
                             sigmas=self.settings["sigmas"],
                             parentheses_mode=self.parentheses_mode
                             ) + ("%" if self.is_percent else "")

    def format(self) -> str:
        return str(self)

    @classmethod
    def init_settings(cls, new_settings: t.Dict[str, t.Union[int, bool]]):
        typecheck_locals(new_settings=cls.settings_format)
        cls.settings = cls.settings_format.get_default().copy()
        cls.settings.update(new_settings)


def format_number(number: Number, deviation: float = 0.0,
                  parentheses: bool = True, explicit_deviation: bool = False,
                  is_deviation_absolute: bool = False,
                  min_decimal_places: int = 3,
                  max_decimal_places: t.Optional[int] = None,
                  omit_insignificant_decimal_places: bool = True,
                  scientific_notation: bool = False,
                  scientific_notation_steps: int = 3,
                  scientific_notation_decimal_places: int = None,
                  scientific_notation_si_prefixes: bool = True,
                  force_min_decimal_places: bool = False,
                  relative_to_deviation: bool = False,
                  sigmas: int = 2,
                  parentheses_mode: ParenthesesMode = ParenthesesMode.ORDER_OF_MAGNITUDE
                  ) -> str:
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
    :param scientific_notation: use the exponential notation, i.e. "10e3" for 1000
    :param scientic_notation_steps: steps in which the exponential part is incremented
    :param scientific_notation_decimal_places: number of decimal places that are shown in the scientic notation
    :param scientific_notation_si_prefixes: use si prefixes instead of "e…"
    :param force_min_decimal_places: don't omit the minimum number of decimal places if insignificant?
    :param relative_to_deviation: format the number relative to its deviation, i.e. "10 sigma"
    :param sigmas: number of standard deviations for significance
    :param parentheses_mode: mode for selecting the significant digits
    :return: the number formatted as a string
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
        "scientific_notation": scientific_notation,
        "sigmas": sigmas,
        "parentheses_mode": parentheses_mode
    }
    if explicit_deviation:
        return prefix + _format_number(**kwargs)
    if scientific_notation:
        #kwargs["scientic_notation_steps"] = scientic_notation_steps
        #kwargs["scientific_notation_decimal_places"] = scientific_notation_decimal_places
        return prefix + format_number_sn(scientific_notation_steps=scientific_notation_steps,
                                         decimal_places=scientific_notation_decimal_places,
                                         si_prefixes=scientific_notation_si_prefixes,
                                         **kwargs)
    else:
        return prefix + _format_number(**kwargs)


def _format_number(number: Number, deviation: float,
                   parentheses: bool = True, explicit_deviation: bool = False,
                   is_deviation_absolute: bool = False,
                   min_decimal_places: int = 3,
                   max_decimal_places: t.Optional[int] = None,
                   omit_insignificant_decimal_places: bool = True,
                   force_min_decimal_places: bool = False,
                   relative_to_deviation: bool = False,
                   scientific_notation: bool = False,
                   scientific_notation_si_prefixes: bool = True,
                   sigmas: int = 2,
                   parentheses_mode: ParenthesesMode = ParenthesesMode.ORDER_OF_MAGNITUDE) -> str:
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
                            scientific_notation=scientific_notation,
                            scientific_notation_si_prefixes=scientific_notation_si_prefixes,
                            sigmas=sigmas,
                            parentheses_mode=parentheses_mode)
        dev = format_number(deviation, deviation, parentheses=False, explicit_deviation=False,
                            is_deviation_absolute=True, min_decimal_places=min_decimal_places,
                            max_decimal_places=max_decimal_places,
                            omit_insignificant_decimal_places=omit_insignificant_decimal_places,
                            force_min_decimal_places=force_min_decimal_places,
                            relative_to_deviation=relative_to_deviation,
                            scientific_notation=scientific_notation,
                            scientific_notation_si_prefixes=scientific_notation_si_prefixes,
                            sigmas=sigmas)
        return num + "±" + dev
    last_sig = -10000
    if not math.isnan(deviation):
        last_sig = _last_significant_digit(number, deviation, sigmas, parentheses_mode)

    num = ""

    decimal_places = 0
    if last_sig >= 0:  # decimal part is insignificant
        if not omit_insignificant_decimal_places or force_min_decimal_places:
            if force_min_decimal_places:
                decimal_places = min_decimal_places
    else:
        decimal_places = min_decimal_places
        if not omit_insignificant_decimal_places or force_min_decimal_places:
            decimal_places = max(abs(last_sig), min_decimal_places)
        if max_decimal_places is not None:
            decimal_places = min(decimal_places, max_decimal_places)

    # round the number
    number = round(number * (10 ** decimal_places)) / (10 ** decimal_places)

    # format the integer part
    if last_sig <= 0 or not parentheses:   # integer part is significant
        num = str(int(number))
    else:
        num = str(int(number))
        num = num[0:len(num) - last_sig] + "(" + num[len(num) - last_sig:] + ")"

    # format the decimal part
    if last_sig >= 0: # decimal part is insignificant
        if not omit_insignificant_decimal_places or force_min_decimal_places:
            dec_part = "{{:.{}f}}".format(decimal_places).format(number - math.floor(number))[2:]
            if max_decimal_places is not 0:
                num += "."
                if parentheses:
                    num += "(" + dec_part + ")"
                else:
                    num += dec_part
    else:
        dec_digits = min_decimal_places
        dec_part = "{{:.{}f}}".format(decimal_places)
        dec_part = dec_part.format(number - math.floor(number))[2:]
        if max_decimal_places is not 0:
            num += "."
            if parentheses and len(dec_part[abs(last_sig):]) > 0:
                num += dec_part[0:abs(last_sig)] + "(" + dec_part[abs(last_sig):] + ")"
            else:
                num += dec_part
    return num + app



def format_number_sn(number: Number, scientific_notation_steps: int = 3,
                     deviation: t.Optional[float] = None, decimal_places: int = None,
                     si_prefixes: bool = True, **kwargs):
    if si_prefixes:
        decimal_places = 3
    sig = _first_digit(number) // scientific_notation_steps
    p = math.pow(10, sig * scientific_notation_steps)
    decimal_places = decimal_places or (3 if isinstance(number, float) or p >= 1000 else 0)
    number /= p
    if deviation and ("is_deviation_absolute" in kwargs
                                  and kwargs["is_deviation_absolute"]):
        deviation /= p
    fmt = "%.{}f".format(decimal_places) % number
    e = "e" + str(sig * scientific_notation_steps)
    if si_prefixes:
        e = _number_to_si_prefix(sig * 3)
    kwargs["scientific_notation"] = False
    if deviation:
        fmt = _format_number(number, deviation=deviation, **kwargs)
    if sig != 0:
        fmt += e
    return fmt


def _number_to_si_prefix(exponent: int) -> str:
    assert exponent % 3 == 0 and 24 >= exponent >= -24
    return ["Y", "Z", "E", "P", "T", "G", "M", "k",
            "", "m", "µ", "n", "f", "a", "z", "y"][int((24 - exponent) / 3)]


def _last_significant_digit(number: Number, abs_deviation: float, sigmas: int = 2,
                            parentheses_mode: ParenthesesMode = ParenthesesMode.ORDER_OF_MAGNITUDE) -> int:
    """
    Calculates the position down to which the passed number is significant.
    […][2][1][0].[-1][-2][…]

    Significant <=>
        DIGIT_CHANGE mode -> the digit does not change if the number is $sigmas deviations bigger or smaller
        OOM -> the digit position is bigger than the order of magnitude than $sigmas deviations
    """
    if abs_deviation == 0:
        return -1
    if number < 0 or abs_deviation < 0:
        raise Exception()

    if parentheses_mode is ParenthesesMode.ORDER_OF_MAGNITUDE:
        return math.ceil(math.log10(sigmas * abs_deviation))

    upper = number + sigmas * abs_deviation
    lower = number - sigmas * abs_deviation

    current_power = math.ceil(math.log10(upper))
    min_power = math.floor(math.log10(sys.float_info.min))

    while current_power >= min_power:
        if _n_th_digit(upper, current_power) != _n_th_digit(lower, current_power):
            return current_power + 1
        current_power -= 1
    return -1


def _n_th_digit(number: Number, n: int) -> int:
    return math.floor(number / math.pow(10, n)) % 10


def _first_digit(number: Number) -> int:
    # […][2][1][0].[-1][-2][…]
    if number == 0:
        return 0
    return math.floor(math.log10(number))