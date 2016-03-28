"""
This module simplifies the creation of click options from settings and type schemes.
"""

import logging
import warnings

import click
from temci.utils.typecheck import *
from temci.utils.settings import Settings, SettingsError
from temci.utils.registry import AbstractRegistry
import typing as t

from temci.utils.util import sphinx_doc


def type_scheme_option(option_name: str, type_scheme: Type, is_flag: bool = False,
                       callback = t.Callable[[str, t.Any], t.Any], short: str = None, with_default: bool = True,
                       default = None) -> t.Callable[[t.Callable], t.Callable]:
    """
    Is essentially a wrapper around click.option that works with type schemes.

    :param option_name: name of the option
    :param type_scheme: type scheme to use
    :param is_flag: is this option a "--ABC/--no-ABC" like flag
    :param callback: callback that is called with the parameter and the argument and has to returns its argument
    :param short: short name of the option (ignored if flag=True)
    :param with_default: set a default value for the option if possible?
    :param default: default value (if with_default is true), default: default value of the type scheme
    """
    __type_scheme = type_scheme
    __short = short
    help_text = type_scheme.description
    has_default = with_default
    default_value = default
    if with_default and not default_value:
        try:
            default_value = type_scheme.get_default()
        except ValueError:
            has_default = False

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
        if isinstance(type_scheme, List) or isinstance(type_scheme, ListOrTuple):
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
            "type": used_raw_type,
            "callback": None,
            "multiple": multiple
        }
        if has_default:
            option_args["default"] = default_value
            option_args["show_default"] = True
        #else:
        #    option_args["show_default"] = False
        if not isinstance(option_args["type"], click.ParamType):
            option_args["callback"] = validate(_type_scheme)
            if not isinstance(option_args["type"], Either(T(tuple), T(str))):
                option_args["type"] = raw_type(option_args["type"])
        if callback is not None:
            if option_args["callback"] is None:
                option_args["callback"] = lambda ctx, param, value: callback(param, value)
            else:
                old_callback = option_args["callback"]
                option_args["callback"] = lambda ctx, param, value: callback(param, old_callback(ctx, param, value))
        if is_flag:
            option_args["is_flag"] = True

        #print(type(option_args["callback"]), option_name, type_scheme)
        opt = None
        if help_text is not None:
            typecheck(help_text, Str())
            option_args["help"] = help_text
        if is_flag:
            del(option_args["type"])
            opt = click.option("--{name}/--no-{name}".format(name=option_name), **option_args)(decorated_func)
        if __short is not None:
            opt = click.option("--{}".format(option_name), "-" + __short, **option_args)(decorated_func)
        else:
            opt = click.option("--{}".format(option_name), **option_args)(decorated_func)
        return opt
        #print(type(f()))
    return func


def validate(type_scheme: Type) -> t.Callable[[click.Context, str, t.Any], t.Any]:
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


class CmdOption:
    """
    Represents a command line option.
    """

    def __init__(self, option_name: str, settings_key: str = None, type_scheme: Type = None,
                 short: str = None, completion_hints: t.Dict[str, t.Any] = None, is_flag: bool = None):
        """
        Initializes a option either based on a setting (via settings key) or on a type scheme.
        If this is backed by a settings key, the setting is automatically set.
        If is_flag is None, it is set True if type_scheme is an instance of Bool() or BoolOrNone()

        :param option_name: name of the option
        :param settings_key: settings key of the option
        :param type_scheme: type scheme with default value
        :param short: short version of the option (ignored if is_flag=True)
        :param completion_hints: additional completion hints (dict with keys for each shell)
        :param is_flag: is the option a "--ABC/--no-ABC" flag like option?
        """
        typecheck(option_name, Str())
        self.option_name = option_name  # type: str
        """ Name of this option """
        self.settings_key = settings_key  # type: t.Optional[str]
        """ Settings key of this option """
        self.short = short  # type: t.Optional[str]
        """ Short version of the option (ignored if is_flag=True) """
        self.completion_hints = completion_hints  # type: t.Optional[t.Dict[str, t.Any]]
        """ Additional completion hints (dict with keys for each shell) """
        if (settings_key is None) == (type_scheme is None):
            raise ValueError("settings_key and type_scheme are both None (or not None)")
        self.type_scheme = type_scheme  # type: Type
        """ Type scheme with default value """
        if not self.type_scheme:
            self.type_scheme = Settings().get_type_scheme(settings_key)
        #self.callback = lambda a, b: None
        #""" Callback that sets the setting """
        self.callback = None  # type: t.Optional[t.Callable[[click.Option, t.Any], None]]
        """ Callback that sets the setting """
        if type_scheme is not None and not isinstance(type_scheme, click.ParamType):
            self.callback = lambda a, b: None
        if settings_key is not None and not isinstance(self.type_scheme, click.ParamType):
            def callback(param: click.Option, val):
                try:
                    Settings()[settings_key] = val
                except SettingsError as err:
                    logging.error("Error while processing the passed value ({val}) of option {opt}: {msg}".format(
                        val=repr(val),
                        opt=option_name,
                        msg=str(err)
                    ))
                    exit(1)
            self.callback = callback
        else:
            self.callback = None
        self.description = self.type_scheme.description.strip().split("\n")[0]  # type: str
        """ Description of this option """
        self.has_description = self.description not in [None, ""]  # type: bool
        """ Does this option has a description? """
        if not self.has_description:
            warnings.warn("Option {} is without documentation.".format(option_name))
        self.has_default = True  # type: bool
        """ Does this option has a default value? """
        self.default = None  # type: t.Any
        """ Default value of this option """
        try:
            self.default = self.type_scheme.get_default()
        except ValueError:
            self.has_default = False
        if settings_key:
            self.default = Settings()[settings_key]
        if hasattr(self.type_scheme, "completion_hints") and self.completion_hints is None:
            self.completion_hints = self.type_scheme.completion_hints
        self.is_flag = is_flag is True or (is_flag is None and type(self.type_scheme) in [Bool, BoolOrNone])  # type: bool
        """ Is this option flag like? """
        if self.is_flag:
            self.completion_hints = None
            self.short = None

            def callback(param, val):
                if val is not None:
                    try:
                        Settings()[settings_key] = val
                    except SettingsError as err:
                        logging.error("Error while processing the passed value ({val}) of option {opt}: {msg}".format(
                            val=val,
                            opt=option_name,
                            msg=str(err)
                        ))
                return val
            self.callback = callback
        self.has_completion_hints = self.completion_hints is not None  # type: bool
        """ Does this option has completion hints? """
        self.has_short = short is not None  # type: bool
        """ Does this option has a short version? """

    def __lt__(self, other) -> bool:
        """
        Compare by option_name.
        """
        typecheck(other, CmdOption)
        return self.option_name < other.option_name

    def __str__(self) -> str:
        return self.option_name

    def __repr__(self) -> str:
        return "CmdOption({})".format(self.option_name)

    @classmethod
    def from_registry(cls, registry: type, name_prefix: str = None) -> 'CmdOptionList':
        """
        Creates a list of CmdOption objects from an registry.
        It creates an activation flag (--OPT/--no-OPT) for each registered plugin and
        creates for each plugin preference an option with name OPT_PREF. Deeper nesting
        is intentionally not supported.

        :param registry: used registry
        :param name_prefix: prefix of each option name (usable to avoid ambiguity problems)
        :return: list of CmdOptions
        """
        assert issubclass(registry, AbstractRegistry)
        typecheck_locals(name_prefix=Str()|E(None))
        name_prefix = name_prefix if name_prefix is not None else ""
        ret_list = CmdOptionList()
        for plugin in registry.registry:
            active_key = "{}_active".format("/".join([registry.settings_key_path, plugin]))
            ret_list.append(CmdOption(
                option_name=name_prefix + plugin,
                settings_key=active_key
            ))
            misc_key = "{}_misc".format("/".join(registry.settings_key_path.split("/") + [plugin]))
            misc = Settings().get_type_scheme(misc_key)
            typecheck(misc, Dict)
            for misc_sub_key in misc.data:
                misc_sub = misc[misc_sub_key]
                if not isinstance(misc_sub, Dict):
                    ret_list.append(CmdOption(
                        option_name="{}{}_{}".format(name_prefix, plugin, misc_sub_key),
                        settings_key="{}/{}".format(misc_key, misc_sub_key)
                    ))
        return ret_list

    @classmethod
    def from_non_plugin_settings(cls, settings_domain: str,
                                 exclude: t.List[Str] = None, name_prefix: str = None) -> 'CmdOptionList':
        """
        Creates a list of CmdOption object from all sub settings (in the settings domain).
        It excludes all sub settings that are either in the exclude list or end with
        "_active" or "_misc" (used for plugin settings).
        Also every setting that is of type Dict is ignored.

        :param settings_domain: settings domain to look into (or "" for the root domain)
        :param exclude: list of sub keys to exclude
        :return: list of CmdOptions
        """
        exclude = exclude or []
        name_prefix = name_prefix or ""
        typecheck_locals(settings_domain=str, exclude=List(Str()), name_prefix=Str())
        domain = Settings().type_scheme
        if settings_domain != "":
            domain = Settings().get_type_scheme(settings_domain)
        ret_list = []
        for sub_key in domain.data:
            if sub_key not in exclude and all(not sub_key.endswith(suf) for suf in ["_active", "_misc"]) \
               and not isinstance(domain[sub_key], Dict):
                ret_list.append(CmdOption(
                    option_name=name_prefix + sub_key,
                    settings_key=settings_domain + "/" + sub_key if settings_domain != "" else sub_key
                ))
        return CmdOptionList(*ret_list)


class CmdOptionList:
    """
    A simple list for CmdOptions that supports list flattening.
    """

    def __init__(self, *options: t.Tuple[t.Union[CmdOption, 'CmdOptionList']]):
        """
        Create an instance.

        :param options: options that this list consists of
        """
        self.options = []
        """ Options that build up this list """
        for option in options:
            self.append(option)

    def append(self, options: t.Union[CmdOption, 'CmdOptionList']) -> 'CmdOptionList':
        """
        Appends the passed CmdÖptionList or CmdOption and flattens the resulting list.

        :param options: CmdÖptionList or CmdOption
        :return: self
        """
        typecheck_locals(options=T(CmdOptionList)|T(CmdOption))
        if isinstance(options, CmdOption):
            self.options.append(options)
        else:
            self.options.extend(options.options)
        return self

    def set_short(self, option_name: str, new_short: str) -> 'CmdOptionList':
        """
        Sets the short option name of the included option with the passed name.

        :param option_name: passed option name
        :param new_short: new short option name
        :return: self
        :raises: IndexError if the option with the passed name doesn't exist
        """
        self[option_name].short = new_short
        return self

    def __getitem__(self, key: t.Union[int, str]) -> CmdOption:
        """
        Get the included option with the passed name or at the passed index.

        :param key: passed name or index
        :return: found cmd option
        :raises: IndexError if the option doesn't exist
        """
        if isinstance(key. int):
            return self.options[key]
        for option in self.options:
            if option.option_name == key:
                return option
        raise IndexError("No such key {!r}".format(key))

    def __iter__(self):
        return self.options.__iter__()

    def __str__(self) -> str:
        return str(self.options)

    def __repr__(self) -> str:
        return repr(self.options)

    def __len__(self) -> int:
        return len(self.options)

    def get_sphinx_doc(self) -> str:
        """ Returns the documentation string for the enclosed options """
        def format_option(option: CmdOption) -> str:
            names = ["--" + option.option_name]
            if option.has_short:
                names.append("-" + option.short)
            if option.is_flag:
                names.append("--no-" + option.option_name)
            name_str =  "|".join(names)

            ret = """
``{name}``:

    :Description: {descr}
            """.format(name=name_str, descr=option.description)
            if not option.is_flag:
                ret += """

    :Argument type: {}
                """.format(str(option.type_scheme).strip())
            if option.has_default:
                ret += """

    :Default: :python:`{!r}`

                """.format(option.default)
            return ret
        return "\n".join([format_option(x) for x in self.options])


def cmd_option(option: t.Union[CmdOption, CmdOptionList], name_prefix: str = None) \
        -> t.Callable[[t.Callable], t.Callable]:
    """
    Wrapper around click.option that works with CmdOption objects.
    If option is a list of CmdOptions then the type_scheme_option decorators are chained.
    Also supports nested lists in the same manner.

    :param option: CmdOption or (possibly nested) list of CmdOptions
    :param name_prefix: prefix of all options
    :return: click.option(...) like decorator
    """
    typecheck(option, T(CmdOption) | T(CmdOptionList))
    name_prefix = name_prefix or ""
    typecheck(name_prefix, Str())
    if isinstance(option, CmdOption):
        return type_scheme_option(option_name=name_prefix + option.option_name,
                                  type_scheme=option.type_scheme,
                                  short=option.short,
                                  is_flag=option.is_flag,
                                  callback=option.callback,
                                  with_default=option.has_default,
                                  default=option.default
                                  )

    def func(f: t.Callable):
        name = f.__name__
        #args = f.__arguments__
        annotations = f.__annotations__
        module = f.__module__
        doc = f.__doc__
        qname = f.__qualname__
        for opt in sorted(option.options):
            f = cmd_option(opt, name_prefix)(f)
        f.__name__ = name[0:-2] if name.endswith("_") else name
        f.__qualname__ = qname[0:-2] if qname.endswith("_") else qname
        #f.__args__ = args
        f.__annotations__ = annotations
        f.__module__ = module
        f.__doc__ = doc
        return f
    return func


def document_func(description: str, *options: t.Tuple[t.Union[CmdOptionList, CmdOption]],
                  argument: str = None, only_if_sphinx_doc: bool = True) -> t.Callable[[t.Callable], t.Callable]:
    """
    Function decorator that appends an command documentation to the functions __doc__ attribute.


    :param description: description of the command
    :param options: options to generate a documentation for
    :param argument: optional argument description of the command
    :param only_if_sphinx_doc: only generate the documentation if the file is executed for documentation generation
    """
    options = CmdOptionList(*options)
    options_str = options.get_sphinx_doc()
    def func(f):
        if not sphinx_doc():
            return f
        full_cmd = f.__name__.replace("__", " ")
        if not f.__doc__:
            f.__doc__ = ""
        f.__doc__ += """
    .. role:: python(code)
    :language: python

    :Command: ``{full_cmd}``

    :Description: {description}

        """.format(full_cmd=full_cmd, description=description)
        if argument:
            f.__doc__ += """

    :Argument: {argument}
    """.format(argument=argument)
        if len(options) > 0:
            f.__doc__ += """

    **Options**:

        {options}
            """.format(options="\n        ".join(options_str.split("\n")))
        return f
    return func




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
