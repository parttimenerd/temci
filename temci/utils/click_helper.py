import click, sys
from temci.utils.typecheck import *
from temci.utils.settings import Settings
import temci.utils.util as util


def option_path_to_string(path: list) -> str:
    return "_".join(path)


def string_to_option_path(string: str, tree: dict) -> list:
    str_list = string.split("_")

    def sub_func(str_list: list, sub_tree: dict) -> list:
        typecheck(sub_tree, dict)
        for i in range(1, len(str_list) + 1):
            sub_key = "_".join(str_list[:i])
            if sub_key in sub_tree:
                if len(str_list[:i]) == len(str_list):
                    return [sub_key]
                else:
                    return [sub_key] + sub_func(str_list[i:], sub_tree[sub_key])

        return None

    return sub_func(str_list, tree)


def type_scheme_option(type_scheme: Dict):
    """
    Works like click.option, but uses the passed type scheme to produce options.


    :param type_scheme: type scheme to get the options from
    :param default_value: default values for the type scheme
    :param prefix: prefix of the options name
    :return: function that annotates a function like click.option(...)
    """
    default_value = type_scheme.get_default()
    if util.recursive_has_leaf_duplicates(default_value,
                                          lambda _1, path, _2: option_path_to_string(path)):
        raise ValueError("Would generate duplicate options")
    func = _type_scheme_option(type_scheme, default_value, [])
    #print(type(func))
    return func


def _type_scheme_option(type_scheme: Type, default_value, prefix: list):
    """

    :param type_scheme: type scheme to get the options from
    :param default_value: default values for the type scheme
    :param prefix: prefix of the options name
    :return: function that annotates a function like click.option(...)
    """

    typecheck(type_scheme, Dict)

    def func(decorated_func):
        res_func = decorated_func
        for key in reversed(sorted(type_scheme.data.keys())):
            sub_scheme = type_scheme[key]
            sub_default = default_value[key]
            if isinstance(sub_scheme, Dict):
                res_func = _type_scheme_option(sub_scheme, sub_default, prefix + [key])(res_func)
            else:
                res_func = _type_scheme_option_raw(option_path_to_string(prefix + [key]),
                                                   sub_scheme, sub_default,
                                                   type_scheme.get_description(key))(res_func)
        return res_func
    return func

def _type_scheme_option_raw(option_name: str, type_scheme: Type, default_value, help_text: str = None):
    __type_scheme = type_scheme
    def raw_type(_type):
        while isinstance(_type, Constraint) or isinstance(_type, NonErrorConstraint):
            _type = _type.constrained_type
        if not isinstance(_type, Type):
            return _type
        if isinstance(_type, T):
            return _type.native_type
        if isinstance(_type, Int):
            return int
        if isinstance(_type, Str):
            return str
        if isinstance(_type, ExactEither) and isinstance(_type.exp_values, List(T(type(_type.exp_values[0])))):
            return _type.exp_values[0]
        else:
            raise ValueError("type scheme {} (option {}) is not annotatable".format(str(type_scheme), option_name))

    def func(decorated_func):
        used_raw_type = None
        multiple = False
        type_scheme = __type_scheme
        _type_scheme = type_scheme
        while isinstance(type_scheme, Either):
            type_scheme = type_scheme.types[0]
        while isinstance(type_scheme, Constraint) or isinstance(type_scheme, NonErrorConstraint):
            type_scheme = type_scheme.constrained_type
        if isinstance(type_scheme, List):
            multiple = True
            type_scheme = type_scheme.elem_type
        if isinstance(type_scheme, click.ParamType):
            used_raw_type = type_scheme
        elif isinstance(type_scheme, ExactEither):
            used_raw_type = click.Choice(type_scheme.exp_values)
        elif isinstance(type_scheme, Exact):
            used_raw_type = click.Choice(type_scheme.exp_value)
        elif isinstance(type_scheme, Tuple):
            used_raw_type = tuple([raw_type(x) for x in type_scheme.elem_types])
        elif isinstance(type_scheme, Any):
            used_raw_type = object
        elif isinstance(type_scheme, T):
            used_raw_type = type_scheme.native_type
        elif isinstance(type_scheme, Str):
            used_raw_type = str
        else:
            used_raw_type = raw_type(type_scheme)
        option_args = {
            "default": default_value,
            "show_default": True,
            "type": used_raw_type
        }
        if not isinstance(option_args["type"], click.ParamType):
            option_args["callback"] = validate(_type_scheme)
            if not isinstance(option_args["type"], Either(T(tuple), T(str))):
                option_args["type"] = raw_type(option_args["type"])
        #print(type(option_args["callback"]), option_name, type_scheme)
        if help_text is not None:
            typecheck(help_text, Str())
            option_args["help"] = help_text
        f = click.option("--{}".format(option_name), **option_args)(decorated_func)
        #print(type(f()))
        return f
    return func


def validate(type_scheme):
    """
    Creates a valid click option validator function that can be passed to click via the callback
    parameter.
    The validator function expects the type of the value to be the raw type of the type scheme.
    :param type_scheme: type scheme the validator validates against
    :return: the validator function
    """
    def func(ctx, param, value):
        param = param.human_readable_name
        param = param.replace("-", "")
        res = verbose_isinstance(value, type_scheme, value_name=param)
        if not res:
            raise click.BadParameter(str(res))
        return value
    return func


def settings(**kwargs):
    type_scheme = Settings().type_scheme
    default_values = type_scheme.get_default()
    for key in kwargs:
            arr = string_to_option_path(key, default_values)
            if arr is not None:
                settings_key = "/".join(arr)
                Settings()[settings_key] = kwargs[key]


def settings_completion_dict(**kwargs):
    type_scheme = Settings().type_scheme
    default_values = type_scheme.get_default()
    comp_dict = {}
    for key in kwargs:
        arr = string_to_option_path(key, default_values)
        if arr is not None:
            settings_key = "/".join(arr)
            type_scheme = Settings().get_type_scheme(settings_key)
            descr = type_scheme.description
            default = type_scheme.get_default()
            comp_dict[key] = {
                "default": default
            }
            if descr is not None:
                comp_dict[key]["description"] = descr
            if hasattr(type_scheme, "completion_hints"):
                comp_dict[key]["completion_hints"] = type_scheme.completion_hints
    return comp_dict

#@annotate(Dict({"count": Int(), "abc": Str(), "d": Dict({
#    "abc": NaturalNumber()
#})}), {"count": 3, "abc": "", "d": {"abc": 1}}, {"count": "Hilfe!!!"})

"""
(Dict({
    "abc": Int() // Default(4),
    "d": Dict({
        "sad": (CommaSepStringList() | Exact("f")) // Default("f")
    })
})
"""

"""
@click.command()
@type_scheme_option(Settings().type_scheme)
def cmd(**kwargs):
    def f(**kwargs):
        print(kwargs)
    return f
cmd()
"""
