from .settings import Settings
from .util import Singleton
from .typecheck import *

class AbstractRegistry(metaclass=Singleton):

    def __init__(self, settings_key_path: list, use_key: str, use_list: bool, default: str):
        """

        :param settings_key_path:
        :param use_key:
        :param use_list:
        :return:
        """
        self.settings_key_path = settings_key_path
        self.use_key = use_key
        self.use_list = use_list
        self.default = default
        self._register = {}

    def get_for_name(self, name: str, *args, **kwargs):
        """
        Creates a plugin with the given name.
        :param name: name of the registered class
        :return: object of the registered class
        :raises ValueError if there isn't such a class
        """
        if name not in self._register:
            raise ValueError("No such registered class {}".format(name))
        return self._register[name](Settings()["/".join(self.settings_key_path + [name + "_misc"])], *args, **kwargs)

    def get_used(self):
        """
        Get the list of name of the used plugins (use_list=True)
        or the name of the used plugin (use_list=False).
        """
        return Settings()["/".join(self.settings_key_path + [self.use_key])]

    def register(self, name: str, klass: type, misc_type: Type, misc_default):
        """
        Registers a new class.
        The constructor of the class gets as first argument the misc settings.
        :param name: common name of the registered class
        :param klass: actual class
        :param misc_type: type scheme of the {name}_misc settings
        :param misc_default: default value of the {name}_misc settings
        """
        Settings().modify_setting("{}_misc".format("/".join(self.settings_key_path + [name])),
                                  misc_type, misc_default)
        use_key_path = "/".join(self.settings_key_path + [self.use_key])
        if self.use_list:
            if not Settings().validate_key_path(use_key_path.split("/")):
                Settings().modify_setting(use_key_path, List(Exact(name)), self.default)
            else:
                use_key_list = Settings().get_type_scheme(use_key_path)
                assert isinstance(use_key_list, List)
                use_key_list.elem_type |= Exact(name)
        else:
            if not Settings().validate_key_path(use_key_path.split("/")):
                Settings().modify_setting(use_key_path, Exact(name), self.default)
            else:
                Settings().modify_setting(use_key_path, Settings().get_type_scheme(use_key_path) | Exact(name),
                                          Settings().get_default_value(use_key_path))
        self._register[name] = klass

def register(registry: type, name: str, misc_type: Type, misc_default):
    """
    Class decorator that calls the register method for the decorated method.
    :param registry: the registry class to register the class in
    :param name: common name of the registered class
    :param misc_type: type scheme of the {name}_misc settings
    :param misc_default: default value of the {name}_misc settings
    """
    assert issubclass(registry, AbstractRegistry)
    def dec(klass):
        registry().register(name, klass, misc_type, misc_default)
        return klass

    return dec