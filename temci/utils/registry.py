import logging

from temci.utils.util import join_strs, sphinx_doc
from .settings import Settings
from .typecheck import *
import typing as t


class AbstractRegistry:
    """
    An abstract registry.
    To create an own registry set the settings_key_path (type str),
    the use_key (type str), the use_list (type bool) and the default
    attribute (type (use_list ? list of strings : str).

    Important: Be sure to have a "register = {}" line in your extending class.
    """

    settings_key_path = ""  # type: str
    """ Used settings key path """
    use_key = None  # type: t.Optional[str]
    """ Used key that sets which registered class is currently used """
    use_list = False  # type: bool
    """ Allow more than one class to used at a specific moment in time """
    default = None  # type: t.Optional[t.Union[str, t.List[str]]]
    """ Name(s) of the class(es) used by default. Type depends on the `use_list` property."""

    registry = {}  # type: t.Dict[str, type]
    """ Registered classes (indexed by their name) """
    plugin_synonym = ("plugin", "plugins")  # type: t.Tuple[str, str]
    """ Singular and plural version of the word that is used in the documentation for the registered entities """

    @classmethod
    def get_for_name(cls, name: str, *args, **kwargs) -> t.Any:
        """
        Creates a plugin with the given name.

        :param name: name of the registered class
        :return: object of the registered class
        :raises: ValueError if there isn't such a class
        """
        if name not in cls.registry:
            raise ValueError("No such registered class {}".format(name))
        misc_settings = Settings()["/".join([cls.settings_key_path, name + "_misc"])]
        return cls.registry[name](misc_settings, *args, **kwargs)

    @classmethod
    def get_used(cls) -> t.Union[str, t.List[str]]:
        """
        Get the list of name of the used plugins (use_list=True)
        or the names of the used plugin (use_list=False).
        """
        key = "/".join([cls.settings_key_path, cls.use_key])
        if not Settings().has_key(key):
            return [] if cls.use_list else None
        if cls.use_list:
            plugin_allow_vals = {}
            active_list = Settings()[key].split(",") if not isinstance(Settings()[key], list) else Settings()[key]
            ret_list = []
            for name in sorted(cls.registry.keys()):
                active_path = "{}_active".format("/".join([cls.settings_key_path, name]))
                active = Settings()[active_path]
                if active is None and name in active_list:
                    ret_list.append(name)
                if active is True:
                    ret_list.append(name)
            return ret_list
        else:
            return Settings()[key]

    @classmethod
    def register(cls, name: str, klass: type, misc_type: Type):
        """
        Registers a new class.
        The constructor of the class gets as first argument the misc settings.

        :param name: common name of the registered class
        :param klass: actual class
        :param misc_type: type scheme of the {name}_misc settings
        :param misc_default: default value of the {name}_misc settings
        """

        def format_str_list(val: t.List[str], sep: str = "and") -> str:
            return join_strs(list(map(repr, val)), sep)

        misc_type_empty = misc_type == Dict() or misc_type == Dict({})
        misc_default = misc_type.get_default()
        description = None
        use_key_path = "/".join([cls.settings_key_path, cls.use_key])
        misc_key = "{}_misc".format("/".join([cls.settings_key_path, name]))

        if klass.__doc__ is not None:
            header = ""# "Description of {} (class {}):\n".format(name, klass.__qualname__)
            lines = str(klass.__doc__.strip()).split("\n")
            lines = map(lambda x: "  " + x.strip(), lines)
            description = Description(header + "\n".join(lines))
            klass.__description__ = description.description
            misc_type //= description
        else:
            klass.__description__ = ""
            logging.error("Class level documentation for {} is missing".format(klass.__name__))
        Settings().modify_setting(misc_key, misc_type)

        if cls.use_list:
            if not Settings().validate_key_path(use_key_path.split("/")) \
                    or isinstance(Settings().get_type_scheme(use_key_path), Any):
                use_key_type = (StrList() | Exact(name))
                use_key_type.typecheck_default = False
                Settings().modify_setting(use_key_path,
                                          use_key_type // Default(cls.default) if cls.default else use_key_type)
            else:
                use_key_list = Settings().get_type_scheme(use_key_path)
                assert isinstance(use_key_list, StrList)
                use_key_list |= Exact(name)
            use_key_list = Settings().get_type_scheme(use_key_path)
            use_key_list // Description("Possible {} are {}".format(cls.plugin_synonym[1],
                                                                    format_str_list(use_key_list.allowed_values)))
            active_path = "{}_active".format("/".join([cls.settings_key_path, name]))
            if not Settings().validate_key_path(active_path.split("/")):
                Settings().modify_setting(active_path, BoolOrNone() // Default(None))
            Settings().get_type_scheme(active_path) // Description("Enable: " + klass.__description__)
        else:
            if not Settings().validate_key_path(use_key_path.split("/")) \
                    or not isinstance(Settings().get_type_scheme(use_key_path), ExactEither):
                use_key_type = ExactEither(name)
                use_key_type.typecheck_default = False
                Settings().modify_setting(use_key_path,
                                          use_key_type // Default(cls.default) if cls.default else use_key_type)
            else:
                Settings().modify_setting(use_key_path, Settings().get_type_scheme(use_key_path) | Exact(name))
            use_key_type = Settings().get_type_scheme(use_key_path)
            use_key_type // Description("Possible {} are {}".format(cls.plugin_synonym[1],
                                                                    format_str_list(use_key_type.exp_values)))
        cls.registry[name] = klass

        if not sphinx_doc():
            return

        use_text = ""
        cls_use_text = ""
        if cls.use_list:
            use_text = "To use this {plugin} add it's name (`{name}`) to the list at settings key `{key}` or " \
                       "set `{active}` to true."\
                .format(plugin=cls.plugin_synonym[0], name=name, key=use_key_path,
                        active="{}_active".format("/".join([cls.settings_key_path, name])))
            cls_use_text = "The used {plugins} can be configured by editing the list under the settings key `{key}`."\
                .format(plugins=cls.plugin_synonym[1], key=use_key_path)
        else:
            use_text = "To use this {plugin} set the currently used {plugin} (at key `{key}`) to its name (`{name}`)."\
                .format(plugin=cls.plugin_synonym[0], name=name, key=use_key_path)
            cls_use_text = "The used {plugin} can be configured by editing the settings key `{key}`."\
                .format(plugin=cls.plugin_synonym[0], key=use_key_path)
        other_plugins_text = ""
        used_type = Settings().get_type_scheme(use_key_path)
        possible_plugins = used_type.allowed_values if cls.use_list else used_type.exp_values  # type: t.List[str]
        possbible_p_wo_self = [x for x in possible_plugins if x != name]
        if len(possible_plugins) == 2:
            other_plugins_text = "Another usable {plugin} is `{p}`.".format(plugin=cls.plugin_synonym[0],
                                                                            p=possbible_p_wo_self[0])
        if len(possible_plugins) > 2:
            other_plugins_text = "Other usable {plugins} are {p}.".format(plugins=cls.plugin_synonym[1],
                                                                          p=join_strs(["`{}`".format(x)
                                                                                       for x in possbible_p_wo_self]))
        default_plugins_text = ""
        if cls.default:
            if cls.use_list and len(cls.default) > 1:
                p = join_strs(["`{}`".format(x) for x in cls.default])
                default_plugins_text = "The default {plugins} are {p}.".format(plugins=cls.plugin_synonym[1],
                                                                               p=p)
            else:
                default = cls.default[0] if cls.use_list else cls.default
                default_plugins_text = "The default {plugin} is `{p}`.".format(plugin=cls.plugin_synonym[0],
                                                                            p=default)
        if not misc_type_empty:
            klass.__doc__ += """

    Configuration format:

    .. code-block:: yaml

        {default_yaml}


    This {plugin} can be configured under the settings key `{misc_key}`.

        """.format(default_yaml="\n        ".join(misc_type.get_default_yaml().split("\n")),
                   misc_key=misc_key, plugin=cls.plugin_synonym[0])
            klass.__doc__ += """

    {use_text}
    {other}
    {default}
        """.format(use_text=use_text, other=other_plugins_text, default=default_plugins_text)
        if not hasattr(cls, "__old_documentation__"):
            cls.__old_documentation__ = cls.__doc__ or ""
        cls.__doc__ = cls.__old_documentation__
        cls.__doc__ += """

    {use_text}
    {possible}
    """.format(
            use_text=cls_use_text,
            possible=Settings().get_type_scheme(use_key_path).description
        )


    @classmethod
    def __getitem__(cls, name: str) -> type:
        """
        Alias for get_for_name(name).
        """
        return cls.get_for_name(name)

    @classmethod
    def get_class(cls, name: str) -> type:
        return cls.registry[name]


def register(registry: type, name: str, misc_type: Type):
    """
    Class decorator that calls the register method for the decorated method.

    :param registry: the registry class to register the class in
    :param name: common name of the registered class
    :param misc_type: type scheme of the {name}_misc settings (each dict key must have a default value)
    """
    assert issubclass(registry, AbstractRegistry)

    def dec(klass):
        registry.register(name, klass, misc_type)
        return klass

    return dec