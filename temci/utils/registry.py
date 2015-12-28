from .settings import Settings
from .util import Singleton
from .typecheck import *


class AbstractRegistry:
    """
    An abstract registry.
    To create an own registry set the settings_key_path (type str),
    the use_key (type str), the use_list (type bool) and the default
    attribute (type (use_list ? list of strings : str).

    Important: Be sure to have a "_register = {}" line in your extending class.
    """

    settings_key_path = ""
    use_key = None
    use_list = False
    default = []

    registry = {}

    @classmethod
    def get_for_name(cls, name: str, *args, **kwargs):
        """
        Creates a plugin with the given name.

        :param name: name of the registered class
        :return: object of the registered class
        :raises ValueError if there isn't such a class
        """
        if name not in cls.registry:
            raise ValueError("No such registered class {}".format(name))
        misc_settings = Settings()["/".join([cls.settings_key_path, name + "_misc"])]
        return cls.registry[name](misc_settings, *args, **kwargs)

    @classmethod
    def get_used(cls):
        """
        Get the list of name of the used plugins (use_list=True)
        or the name of the used plugin (use_list=False).
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
        misc_default = misc_type.get_default()
        description = None
        if klass.__doc__ is not None:
            header = ""# "Description of {} (class {}):\n".format(name, klass.__qualname__)
            lines = str(klass.__doc__.strip()).split("\n")
            lines = map(lambda x: "  " + x.strip(), lines)
            description = Description(header + "\n".join(lines))
            klass.__description__ = description.description
            misc_type //= description
        else:
            klass.__description__ = ""
        Settings().modify_setting("{}_misc".format("/".join([cls.settings_key_path, name])),
                                  misc_type)
        use_key_path = "/".join([cls.settings_key_path, cls.use_key])
        if cls.use_list:
            if not Settings().validate_key_path(use_key_path.split("/")) \
                    or isinstance(Settings().get_type_scheme(use_key_path), Any):
                t = (StrList() | Exact(name))
                t.typecheck_default = False
                Settings().modify_setting(use_key_path, t // Default(cls.default))
            else:
                use_key_list = Settings().get_type_scheme(use_key_path)
                assert isinstance(use_key_list, StrList)
                use_key_list |= Exact(name)
            use_key_list = Settings().get_type_scheme(use_key_path)
            use_key_list // Description("Possible plugins are: {}"\
                    .format(repr(sorted(use_key_list.allowed_values))[1:-1]))
            active_path = "{}_active".format("/".join([cls.settings_key_path, name]))
            if not Settings().validate_key_path(active_path.split("/")):
                Settings().modify_setting(active_path, BoolOrNone() // Default(None))
            Settings().get_type_scheme(active_path) // Description("Enable: " + klass.__description__)
        else:
            if not Settings().validate_key_path(use_key_path.split("/")) \
                    or not isinstance(Settings().get_type_scheme(use_key_path), ExactEither):
                t = ExactEither(name)
                t.typecheck_default = False
                Settings().modify_setting(use_key_path, t // Default(cls.default))
            else:
                Settings().modify_setting(use_key_path, Settings().get_type_scheme(use_key_path) | Exact(name))
            t = Settings().get_type_scheme(use_key_path)
            t // Description("Possible plugins are: {}"\
                .format(repr(sorted(t.exp_values))[1:-1]))
        cls.registry[name] = klass

    @classmethod
    def __getitem__(cls, name: str):
        """
        Alias for get_for_name(name).
        """
        return cls.get_for_name(name)

    @classmethod
    def get_class(cls, name: str):
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