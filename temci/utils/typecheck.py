"""
Implements basic type checking for complex types.

Why? Because it's nice to be able to type check complex structures that come directly
from the user (e.g. from YAML config files).

The Type instance are usable with the standard isinstance function::

    isinstance(4, Either(Float(), Int()))

Type instances also support the "&" (producres All(one, two)) and "|" (produces Either(one, two)) operators.
The above sample code can therefore be written as::

    isinstance(4, Float() | Int())

The native type wrappers also support custom constraints. With help of the fn module one can write::

    t = Float(_ > 0) | Int(_ > 10)
    isinstance(var, t)

"t" is a Type that matches only floats greater than 0 and ints greater than 10.

For more examples look into the test_typecheck.py file.
"""

__all__ = [
    "Type",
    "Exact",
    "ExactEither",
    "T",
    "Any",
    "Int",
    "Float",
    "NonExistent",
    "Bool",
    "Str",
    "NaturalNumber",
    "FileName",
    "FileNameOrStdOut",
    "ValidYamlFileName",
    "PositiveInt",
    "StrList",

    "Info",
    "Description",
    "Default",

    "All",
    "Either",
    "Optional",
    "Constraint",
    "NonErrorConstraint",
    "List",
    "Tuple",
    "Dict",
    "verbose_isinstance",
    "typecheck"
]

import fn
import itertools, os, yaml, click


class ConstraintError(ValueError):
    pass


class Info(object):

    def __init__(self, value_name: str = None, _app_str: str = None, value = None):
        self.value_name = value_name
        self._app_str = _app_str if _app_str is not None else ""
        if value_name is None:
            self._value_name = "value {{!r}}{}".format(self._app_str)
        else:
            self._value_name = "{}{} of value {{!r}}".format(self.value_name, self._app_str)
        if value is None:
            self.value = None
            self.has_value = False
        else:
            self.value = value
            self.has_value = True

    def set_value(self, value):
        self.value = value
        self.has_value = True

    def get_value(self):
        if not self.has_value:
            raise ValueError("value is not defined")
        return self.value

    def add_to_name(self, app_str: str):
        """
        Creates a new info object based on this one.
        :param app_str: app string appended to the own app string to create the app string for the new info object
        :return: new info object
        :rtype Info
        """
        return Info(self.value_name, self._app_str + app_str, self.value)

    def _str(self):
        return self._value_name.format(self.get_value())

    def errormsg(self, constraint, msg: str = None):
        app = ": " + msg if msg is not None else ""
        return InfoMsg("{} hasn't the expected type {}{}".format(self._str(), constraint, app))

    def errormsg_cond(self, cond, constraint, value):
        if cond:
            return InfoMsg(True)
        else:
            return InfoMsg(self.errormsg(constraint))

    def errormsg_non_existent(self, constraint):
        return InfoMsg("{} is non existent, expected value of type {}".format(self._str(), constraint))

    def errormsg_too_many(self, constraint, value_len, constraint_len):
        return InfoMsg("{} has to many elements ({}), " \
               "expected value of type {} with {} elements".format(self._str(), value_len, constraint, constraint_len))

    def wrap(self, result: bool):
        return InfoMsg(result)

    def __getitem__(self, item):
        raise NotImplementedError()

    def __setitem__(self, key, value):
        raise NotImplementedError()


class NoInfo(Info):

    def add_to_name(self, app_str):
        return self

    def errormsg(self, constraint, msg: str = None):
        return False

    def errormsg_cond(self, cond, constraint, value):
        return cond

    def errormsg_non_existent(self, constraint):
        return False

    def errormsg_too_many(self, constraint, value_len, constraint_len):
        return False

    def wrap(self, result: bool):
        return result


class InfoMsg(object):

    def __init__(self, msg_or_bool):
        self.success = msg_or_bool is True
        self.msg = msg_or_bool if isinstance(msg_or_bool, str) else str(self.success)

    def __str__(self):
        return self.msg

    def __bool__(self):
        return self.success


class Description(object):
    """
    A description of a Type, that annotates it.
    Usage example::

        Int() // Description("Description of Int()")
    """

    def __init__(self, description: str):
        typecheck(description, str)
        self.description = description

    def __str__(self):
        return self.description


class Default(object):
    """
    A default value annotation for a Type.
    Usage example::

        Int() // Default(3)

    Especially useful to declare the default value for a key of an dictionary.
    Allows to use Dict(...).get_default() -> dict.
    """

    def __init__(self, default):
        self.default = default


class Type(object):
    """
    A simple type checker type class.
    """

    def __init__(self):
        self.description = None
        self.default = None
        self.typecheck_default = True
        self.completion_hints = {}

    def __instancecheck__(self, value, info: Info = NoInfo()):
        """
        Checks whether or not the passed value has the type specified by this instance.
        :param value: passed value
        """
        if not info.has_value:
            info.set_value(value)
        return self._instancecheck_impl(value, info)

    def _instancecheck_impl(self, value, info: Info):
        return False

    def __str__(self):
        return "Type[]"

    def _validate_types(self, *types):
        for t in types:
            if not isinstance(t, Type):
                raise ConstraintError("{} is not an instance of a Type subclass".format(t))

    def __and__(self, other):
        """
        Alias for All(self, other)
        """
        return All(self, other)

    def __or__(self, other):
        """
        Alias for Either(self, other).
        The only difference is that it flattens trees of Either instances
        """
        if isinstance(other, Either):
            other.types.index(other, 0)
            return other
        return Either(self, other)

    def __floordiv__(self, other):
        """
        Alias for Constraint(other, self). Self mustn't be a Type.
        If other is a string the description property of this Type object is set.
        It also can annotate the object with Description or Default objects.
        """
        if isinstance(other, str) or isinstance(other, Description):
            self.description = str(other)
            return self
        if isinstance(other, Default):
            self.default = other
            if self.typecheck_default:
                typecheck(self.default.default, self)
            return self
        if isinstance(other, Type):
            raise ConstraintError("{} mustn't be an instance of a Type subclass".format(other))
        return Constraint(other, self)

    def __eq__(self, other):
        if type(other) == type(self):
            return self._eq_impl(other)
        return False

    def _eq_impl(self, other):
        return False

    def get_default(self):
        if self.default is None:
            raise ValueError("{} has no default value.".format(self))
        return self.default.default

    def get_default_yaml(self, indents: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) -> str:
        if defaults is None:
            defaults = self.get_default()
        else:
            typecheck(defaults, self)
        i_str = " " * indents * indentation
        y_str = yaml.dump(defaults).strip()
        if y_str.endswith("\n..."):
            y_str = y_str[0:-4]
        strs = list(map(lambda x: i_str + x, y_str.split("\n")))
        return strs if str_list else "\n".join(strs)


class Exact(Type):
    """
    Checks for value equivalence.
    """

    def __init__(self, exp_value):
        """
        :param exp_value: value to check for
        """
        super().__init__()
        self.exp_value = exp_value

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Is the value the same as the expected one?
        """
        cond = isinstance(value, type(self.exp_value)) and value == self.exp_value
        return info.errormsg_cond(cond, self, value)

    def __str__(self):
        return "Exact({!r})".format(self.exp_value)

    def _eq_impl(self, other):
        return other.exp_value == self.exp_value

    def __or__(self, other):
        if isinstance(other, ExactEither):
            other.exp_values.insert(0, self.exp_value)
            return other
        if isinstance(other, Exact):
            return ExactEither(self.exp_value, other.exp_value)
        return Either(self, other)


class Either(Type):
    """
    Checks for the value to be of one of several types.
    """

    def __init__(self, *types: list):
        """
        :param types: list of types (or SpecialType subclasses)
        :raises ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self._validate_types(*types)
        self.types = list(types)

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Does the type of the value match one of the expected types?
        """
        for type in self.types:
            res = type.__instancecheck__(value, info)
            if res:
                return info.wrap(True)
        return info.errormsg(self)

    def __str__(self):
        return "Either({})".format("|".join(str(type) for type in self.types))

    def _eq_impl(self, other):
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))

    def __or__(self, other):
        if isinstance(other, Either):
            self.types += other.types
            return self
        return Either(self, other)


class ExactEither(Type):
    """
    Checks for the value to be of one of several exact values.
    """

    def __init__(self, *exp_values: list):
        """
        :param exp_values: list of types (or SpecialType subclasses)
        :raises ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self.exp_values = list(exp_values)
        self._update_completion_hints()

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Does the type of the value match one of the expected types?
        """
        if value in self.exp_values:
            return info.wrap(True)
        return info.errormsg(self)

    def __str__(self):
        return "ExactEither({})".format("|".join(repr(val) for val in self.exp_values))

    def _eq_impl(self, other):
        return len(other.exp_values) == len(self.exp_values) \
               and all(other.exp_values[i] == self.exp_values[i] for i in range(len(self.exp_values)))

    def __or__(self, other):
        if isinstance(other, ExactEither):
            self.exp_values += other.exp_values
            self._update_completion_hints()
            return self
        if isinstance(other, Exact):
            self.exp_values.append(other.exp_value)
            self._update_completion_hints()
            return self
        return Either(self, other)

    def _update_completion_hints(self):
        self.completion_hints = {
            "zsh": "({})".format(" ".join(repr(val) for val in self.exp_values)),
            "fish": {
                "hint": self.exp_values
            }
        }

class Union(Either):
    """
    Alias for Either. Checks for the value to be of one of several types.
    """


class All(Type):
    """
    Checks for the value to be of all of several types.
    """

    def __init__(self, *types):
        """
        :param types: list of types (or SpecialType subclasses)
        :raises ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self._validate_types(*types)
        self.types = types

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Does the type of the value match all of the expected types?
        """
        for type in self.types:
            res = type.__instancecheck__(value, info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self):
        return "All[{}]".format("|".join(str(type) for type in self.types))

    def _eq_impl(self, other):
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))

class Any(Type):
    """
    Checks for the value to be of any type.
    """
    def __instancecheck__(self, value, info: Info = NoInfo()):
        return info.wrap(True)

    def __str__(self):
        return "Any"

    def _eq_impl(self, other):
        return True


class T(Type):
    """
    Wrapper around a native type.
    """

    def __init__(self, native_type):
        super().__init__()
        if not isinstance(native_type, type):
            raise ConstraintError("{} is not a native type".format(type))
        self.native_type = native_type

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Does the passed value be an instance of the wrapped native type?
        """
        return info.errormsg_cond(isinstance(value, self.native_type), self, info)

    def __str__(self):
        return "T({})".format(self.native_type)

    def _eq_impl(self, other):
        return other.native_type == self.native_type


class Optional(Either):
    """
    Checks the value and checks that its either of native type None or of another Type constraint.
    Alias for Either(Exact(None), other_type)
    """

    def __init__(self, other_type):
        """
        :raises ConstraintError if other_type isn't a (typechecker) Types
        """
        super().__init__(Exact(None), other_type)

    def __str__(self):
        return "Optional({})".format(self.types[1])


class Constraint(Type):
    """
    Checks the passed value by an user defined constraint.
    """

    def __init__(self, constraint, constrained_type: Type = Any(), description: str = None):
        """
        :param constraint: function that returns True if the user defined constraint is satisfied
        :param constrained_type: Type that the constrain is applied on
        :param description: short description of the constraint (e.g. ">0")
        :raises ConstraintError if constrained_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(constrained_type)
        self.constraint = constraint
        self.constrained_type = constrained_type
        self.description = description

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Checks the passed value to be of the constrained type and to
        adhere the user defined constraint.
        """
        res = self.constrained_type.__instancecheck__(value, info)
        if not res:
            return res
        if not self.constraint(value):
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self):
        descr = self.description
        if self.description is None:
            if isinstance(self.constraint, type(fn._)):
                descr = str(self.constraint)
            else:
                descr = "<function>"
        return "{}:{}".format(self.constrained_type, descr)


class NonErrorConstraint(Type):
    """
    Checks the passed value by an user defined constraint that fails if it raise an error.
    """

    def __init__(self, constraint, error_cls, constrained_type: Type = Any(), description: str = None):
        """
        :param constraint: function that doesn't raise an error if the user defined constraint is satisfied
        :param error_cls: class of the errors the constraint method throws
        :param constrained_type: Type that the constrain is applied on
        :param description: short description of the constraint (e.g. ">0")
        :raises ConstraintError if constrained_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(constrained_type)
        self.constraint = constraint
        self.error_cls = error_cls
        self.constrained_type = constrained_type
        self.description = description

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Checks the passed value to be of the constrained type and to
        adhere the user defined constraint (that the method doesn't
        throw the user specified exception).
        """
        res = self.constrained_type.__instancecheck__(value, info)
        if not res:
            return res
        try:
            self.constraint(value)
        except self.error_cls as err:
            return info.errormsg(self, msg=str(err))
        return info.wrap(True)

    def __str__(self):
        descr = self.description
        if self.description is None:
            if isinstance(self.constraint, type(fn._)):
                descr = str(self.constraint)
            else:
                descr = "<function>"
        return "{}:{}".format(self.constrained_type, descr)


class List(Type):
    """
    Checks for the value to be a list with elements of a given type.
    """

    def __init__(self, elem_type=Any()):
        """
        :param elem_type: type of elements
        :param must_contain: the elements the value has to contain at least
        :raises ConstraintError if elem_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(elem_type)
        self.elem_type = elem_type

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not isinstance(value, list):
            return info.errormsg(self)
        for (i, elem) in enumerate(value):
            new_info = info.add_to_name("[{}]".format(i))
            res = self.elem_type.__instancecheck__(elem, new_info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self):
        return "List({})".format(self.elem_type)

    def _eq_impl(self, other):
        return other.elem_type == self.elem_type


class Tuple(Type):
    """
    Checks for the value to be a tuple (or a list) with elements of the given types.
    """

    def __init__(self, *elem_types):
        """
        :param elem_types: types of elements
        :raises ConstraintError if elem_type isn't a (typechecker) Types
        """
        super().__init__()
        for elem_type in elem_types:
            self._validate_types(elem_type)
        self.elem_types = elem_types

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not (isinstance(value, list) or isinstance(value, tuple)) or len(self.elem_types) != len(value):
            return info.errormsg(self)
        if len(self.elem_types) == 0:
            return info.wrap(True)
        for (i, elem) in enumerate(value):
            new_info = info.add_to_name("[{}]".format(i))
            res = self.elem_types[i].__instancecheck__(elem, new_info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self):
        return "Tuple({})".format(", ".join(str(t) for t in self.elem_types))

    def _eq_impl(self, other):
        return len(other.elem_types) == len(self.elem_types) and \
               all(a == b for (a, b) in itertools.product(self.elem_types, other.elem_types))


class _NonExistentVal(object):
    """
    Helper class for NonExistent Type.
    """

    def __str__(self):
        return "<non existent>"

    def __repr__(self):
        return self.__str__()

_non_existent_val = _NonExistentVal()


class NonExistent(Type):
    """
    Checks a key of a dictionary for existence if its associated value has this type.
    """

    def _instancecheck_impl(self, value, info: Info):
        return info.errormsg_cond(type(value) == _NonExistentVal, self, "[value]")

    def __str__(self):
        return "non existent"

    def _eq_impl(self, other):
        return True


class Dict(Type):
    """
    Checks for the value to be a dictionary with expected keys and values satisfy given type constraints.
    """

    def __init__(self, data: dict = None, all_keys=True, key_type: Type = Any(), value_type: Type = Any()):
        """
        :param data: dictionary with the expected keys and the expected types of the associated values
        :param all_keys: does the type checking fail if more keys are present in the value than in data?
        :param key_type: expected Type of all dictionary keys
        :param value_type: expected Type of all dictionary values
        :raises ConstraintError if one of the given types isn't a (typechecker) Types
        """
        super().__init__()
        self.data = data if data is not None else {}
        self._validate_types(*self.data.values())
        self._validate_types(key_type, value_type)
        self.all_keys = all_keys
        self.key_type = key_type
        self.value_type = value_type

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        if not isinstance(value, dict):
            return info.errormsg(self)
        non_existent_val_num = 0
        for key in self.data.keys():
            if key in value:
                res = self.data[key].__instancecheck__(value[key], info.add_to_name("[{!r}]".format(key)))
                if not res:
                    return res
            else:
                is_non_existent = self.data[key].__instancecheck__(_non_existent_val,
                                                                   info.add_to_name("[{!r}]".format(key)))
                non_existent_val_num += 1
                if key not in value and not is_non_existent:
                    info = info.add_to_name("[{!r}]".format(key))
                    return info.errormsg_non_existent(self)
        for key in value.keys():
            ninfo = info.add_to_name("(key={!r})".format(key))
            res = self.key_type.__instancecheck__(key, ninfo)
            if not res:
                return res
        for key in value.keys():
            val = value[key]
            ninfo = info.add_to_name("[{!r}]".format(key))
            res = self.value_type.__instancecheck__(val, ninfo)
            if not res:
                return res
        if self.all_keys and len(self.data) - non_existent_val_num != len(value):
            return info.errormsg_too_many(self, len(value), len(self.data))
        return info.wrap(True)

    def __str__(self):
        fmt = "Dict({data}, keys={key_type}, values={value_type})"
        data_str = ", ".join("{!r}: {}".format(key, self.data[key]) for key in self.data)
        if self.all_keys:
            fmt = "Dict({{{data}}}, {all_keys}, keys={key_type}, values={value_type})"
        return fmt.format(data=data_str, all_keys=self.all_keys, key_type=self.key_type,
                          value_type=self.value_type)

    def __getitem__(self, key) -> Type:
        """
        Returns the Type of the keys value.
        """
        if key in self.data:
            return self.data[key]
        if not self.all_keys and isinstance(key, self.key_type):
            return self.value_type
        return NonExistent()

    def __setitem__(self, key, value):
        """
        Sets the Type of the keys values.
        """
        if (key in self.data and isinstance(value, self.value_type)) or\
            (isinstance(key, self.key_type) and isinstance(value, self.value_type)):
            self.data[key] = value
        else:
            raise ValueError("Key or value have wrong types")

    def get_description(self, key: str) -> str:
        """
        Returns the description for the passed key or None if there isn't one.
        :param key: passed key
        """
        return self[key].description

    def _eq_impl(self, other) -> bool:
        return all(self.data[key] == other.data[key] and self.get_description(key) == other.get_description(key)
                   for key in itertools.chain(self.data.keys(), other.data.keys()))

    def get_default(self) -> dict:
        default_dict = {}
        if self.default is not None:
            default_dict = self.default.default
        for key in self.data:
            if key not in default_dict:
                default_dict[key] = self[key].get_default()
        return default_dict

    def get_default_yaml(self, indent: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) -> str:
        if len(self.data.keys()) == 0:
            ret = "!!map {}"
            return [ret] if str_list else ret
        if defaults is None:
            defaults = self.get_default()
        else:
            typecheck(defaults, self)

        strs = []
        keys = sorted(self.data.keys())
        for i in range(0, len(keys)):
            #if i != 0:
            strs.append("")
            key = keys[i]
            if self.data[key].description is not None:
                comment_lines = self.data[key].description.split("\n")
                comment_lines = map(lambda x: "# " + x, comment_lines)
                strs.extend(comment_lines)
            key_yaml = yaml.dump(key).split("\n")[0]
            if len(self.data[key].get_default_yaml(str_list=True, defaults=defaults[key])) == 1 and \
                    (not isinstance(self.data[key], Dict) or len(self.data[key].data.keys()) == 0):
                value_yaml = self.data[key].get_default_yaml(defaults=defaults[key])
                strs.append("{}: {}".format(key_yaml, value_yaml.strip()))
            else:
                value_yaml = self.data[key].get_default_yaml(1, indentation, str_list=True, defaults=defaults[key])
                strs.append("{}:".format(key_yaml))
                strs.extend(value_yaml)
        i_str = " " * indent * indentation
        ret_strs = list(map(lambda x: i_str + x, strs))
        return ret_strs if str_list else "\n".join(ret_strs)

class Int(Type):
    """
    Checks for the value to be of type int and to adhere to some constraints.
    """

    def __init__(self, constraint = None, range: range = None, description: str = None):
        """
        :param constraint: user defined constrained function
        :param range. range (or list) that the value has to be part of
        :param description: description of the constraints
        """
        super().__init__()
        self.constraint = constraint
        self.range = range
        self.description = description
        if range is not None and len(range) <= 10:
            self.completion_hints = {
                "zsh": "({})".format(" ".join(str(x) for x in range)),
                "fish": {
                    "hint": list(self.range)
                }
            }

    def _instancecheck_impl(self, value, info: Info):
        if not isinstance(value, int) or (self.constraint is not None and not self.constraint(value)) \
                or (self.range is not None and value not in self.range):
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self):
        arr = []
        if self.description is not None:
            arr.append(self.description)
        else:
            if self.constraint is not None:
                descr = ""
                if isinstance(self.constraint, type(fn._)):
                    descr = str(self.constraint)
                else:
                    descr = "<function>"
                arr.append("constraint={}".format(descr))
            if self.range is not None:
                arr.append("range={}".format(self.range))
        return "Int({})".format(",".join(arr))

    def _eq_impl(self, other):
        return other.constraint == self.constraint and other.range == self.range


class StrList(Type, click.ParamType):
    """
    A comma separated string list which contains elements from a fixed of allowed values.
    """

    name = "coma_sep_str_list"

    def __init__(self):
        super().__init__()
        self.allowed_values = None

    def __or__(self, other):
        if isinstance(other, Exact) and isinstance(other.exp_value, Str()):
            if self.allowed_values is None:
                self.allowed_values = [other.exp_value]
            else:
                self.allowed_values.append(other.exp_value)
            return self
        return super().__or__(other)

    def _instancecheck_impl(self, value, info: Info):
        res = List(Str()).__instancecheck__(value, info)
        if not res:
            return info.errormsg(self, "Not a list of strings")
        if self.allowed_values is None or all(val in self.allowed_values for val in value):
            return info.wrap(True)
        return info.errormsg(self, "Does contain invalid elements")

    def convert(self, value, param, ctx):
        if isinstance(value, self):
            return value
        elif isinstance(value, str):
            value = str(value)
            return value.split(",")
        self.fail("{} is no valid comma separated string list".format(value), param, ctx)

    def __str__(self):
        if self.allowed_values is None:
            return "StrList()"
        else:
            return "StrList(allowed={})".format(repr(self.allowed_values))

    def get_default_yaml(self, indents: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) -> str:
        if defaults is None:
            defaults = self.get_default()
        else:
            typecheck(defaults, self)
        i_str = " " * indents * indentation
        ret_str = i_str + "[{}]".format(", ".join(defaults))
        return [ret_str] if str_list else ret_str


class Str(Type):

    def __init__(self, constraint = None):
        super().__init__()
        self.constraint = constraint

    def _instancecheck_impl(self, value, info: Info):
        if not isinstance(value, str):
            return info.errormsg(self)
        if self.constraint is not None and not self.constraint(value):
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self):
        if self.constraint is not None:
            return "Str({})".format(repr(self.constraint))
        else:
            return "Str()"


class FileName(Str):
    """
    A valid file name. If the file doesn't exist, at least the parent directory must exist.
    """

    def __init__(self, constraint = None, allow_std=False):
        super().__init__()
        self.constraint = constraint
        self.completion_hints = {
            "zsh": "_files",
            "fish": {
                "files": True
            }
        }
        self.allow_std = allow_std

    def _instancecheck_impl(self, value, info: Info):
        if not isinstance(value, str):
            return info.errormsg(self)
        if self.allow_std and value == "-" and (self.constraint is None or self.constraint(value)):
            return info.wrap(True)
        is_valid = True
        if os.path.exists(value):
            if os.path.isfile(value) and os.access(os.path.abspath(value), os.W_OK)\
                    and (self.constraint is None or self.constraint(value)):
                return info.wrap(True)
            return info.errormsg(self)
        abs_name = os.path.abspath(value)
        dir_name = os.path.dirname(abs_name)
        if os.path.exists(dir_name) and os.access(dir_name, os.EX_OK) and os.access(dir_name, os.W_OK) \
            and (self.constraint is None or self.constraint(value)):
            return info.wrap(True)
        return info.errormsg(self)

    def __str__(self):
        if self.constraint is not None:
            return "FileName({}, allow_std={})".format(repr(self.constraint), self.allow_std)
        else:
            return "FileName(allow_std={})".format(self.allow_std)


class ValidYamlFileName(Str):
    """
    A valid file name that refers to a valid YAML file.
    """

    def __init__(self):
        super().__init__()
        self.completion_hints = {
            "zsh": "_files",
            "fish": {
                "files": True
            }
        }

    def _instancecheck_impl(self, value, info: Info):
        if not isinstance(value, str):
            return info.errormsg(self)
        if not os.path.exists(value) or not os.path.isfile(value):
            return info.errormsg(self)
        try:
            with open(value, "r") as f:
                 yaml.load(f.readline())
        except (IOError, yaml.YAMLError) as ex:
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self):
        return "ValidYamlFileName()"


def NaturalNumber(constraint = None):
    """
    Matches all natural numbers (ints >= 0) that satisfy the optional user defined constrained.
    """
    if constraint is not None:
        return Int(lambda x: x >= 0 and constraint(x))
    return Int(fn._ >= 0)


def PositiveInt(constraint = None):
    """
    Matches all positive integers that satisfy the optional user defined constrained.
    """
    if constraint is not None:
        return Int(lambda x: x > 0 and constraint(x))
    return Int(fn._ > 0)


def Float(constraint = None):
    """
    Alias for Constraint(constraint, T(float)) or T(float)
    """
    if constraint is not None:
        return Constraint(constraint, T(float))
    return T(float)


def FileNameOrStdOut():
    """
    A valid file name or "-" for standard out.
    """
    return FileName(allow_std=True)

def Bool():
    t = T(bool)
    t.completion_hints = {
        "zsh": "(true false)",
        "fish":{
            "hint": ["true", "false"]
        }
    }
    return t


def verbose_isinstance(value, type, value_name: str = None):
    """
    Verbose version of isinstance that returns a InfoMsg object.

    :param value: value to check
    :param type: type or Type to check for
    :param value_name: name of the passed value (improves the error message)
    """
    if not isinstance(type, Type):
        type = T(type)
    if not isinstance(value, type):
        return type.__instancecheck__(value, Info(value_name))
    return InfoMsg(True)


def typecheck(value, type, value_name: str = None):
    """
    Like verbose_isinstance but raises an error if the value hasn't the expected type.

    :param value: passed value
    :param type: expected type of the value
    :param value_name: optional description of the value
    :raises TypeError
    """
    if not isinstance(value, type):
        raise TypeError(str(verbose_isinstance(value, type, value_name)))

"""
# Hack: Implement a typed() decorator for runtime type testing

class typed(object):

    def __init__(self, *args, **kwargs):
        print(args, kwargs)

    def __call__(self, f):
        def wrapped_f(*args, **kwargs):
            print(args, kwargs)
            print("dsf")
            f(*args, **kwargs)
        return wrapped_f

@typed(3)
def func(a, b, c, d = 4, *ds):
    return "abc"

func(55)

exit()
"""