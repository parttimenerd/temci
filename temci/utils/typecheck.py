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
    "T",
    "Any",
    "Int",
    "Float",
    "NonExistent",
    "BoolLike",
    "Str",

    "Info",

    "All",
    "Either",
    "Optional",
    "Constraint",
    "List",
    "Dict",
    "verbose_issinstance"
]

import fn
import itertools

class ConstraintError(ValueError):
    pass


class Info(object):

    def __init__(self, value_name: str = None, _app_str: str = None):
        self.value_name = value_name
        self._app_str = _app_str if _app_str is not None else ""
        if value_name is None:
            self._value_name = "value {{!r}}{}".format(self._app_str)
        else:
            self._value_name = "{}{} of value {{!r}}".format(self.value_name, self._app_str)
        self.value = None
        self.has_value = False

    def set_value(self, value):
        self.value = value
        self.has_value = True

    def get_value(self):
        if not self.has_value:
            raise ValueError("value is not defined")
        return self.value

    def add_to_name(self, app_str):
        """

        :param app_str:
        :return:
        :rtype Info
        """
        return Info(self.value_name, self._app_str + app_str)

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

class NoInfo(Info):

    def add_to_name(self, app_str):
        return self

    def errormsg(self, constraint, msg: str = None):
        return False

    def errormsg_cond(self, cond, constraint, value):
        return cond

    def errormsg_non_existent(self, constraint):
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

class Type(object):
    """
    A simple type checker type class.
    """

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
        for type in types:
            if not isinstance(type, Type):
                raise ConstraintError("{} is not an instance of a Type subclass".format(type))

    def __and__(self, other):
        """
        Alias for All(self, other)
        """
        return All(self, other)

    def __or__(self, other):
        """
        Alias for Either(self, other).
        """
        return Either(self, other)

    def __floordiv__(self, other):
        """
        Alias for Constraint(other, self). Self mustn't be a Type.
        """
        if isinstance(other, Type):
            raise ConstraintError("{} mustn't be an instance of a Type subclass".format(other))
        return Constraint(other, self)

    def __eq__(self, other):
        if type(other) == type(self):
            return self._eq_impl(other)
        return False

    def _eq_impl(self, other):
        return False

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

class Either(Type):
    """
    Checks for the value to be of one of several types.
    """

    def __init__(self, *types: Type):
        """
        :param types: list of types (or SpecialType subclasses)
        :raises ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self._validate_types(*types)
        self.types = types

    def _instancecheck_impl(self, value, info: Info = NoInfo()):
        """
        Does the type of the value match one of the expected types?
        """
        for type in self.types:
            res = type.__instancecheck__(value, info)
            if res:
                return True
        return info.errormsg(self)

    def __str__(self):
        return "Either({})".format("|".join(str(type) for type in self.types))

    def _eq_impl(self, other):
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))

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
        return True

    def __str__(self):
        return "All[{}]".format("|".join(str(type) for type in self.types))

    def _eq_impl(self, other):
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))

class Any(Type):
    """
    Checks for the value to be of any type.
    """
    def __instancecheck__(self, value, info: Info =NoInfo()):
        return True

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
        return True

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
        return True

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
        return True

    def __str__(self):
        return "List({})".format(self.elem_type)

    def _eq_impl(self, other):
        return other.elem_type == self.elem_type


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
        self.data = data if data is not None else dict()
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
        return True

    def __str__(self):
        fmt = "Dict({data}, keys={key_type}, values={value_type})"
        data_str = ", ".join("{!r}: {}".format(key, self.data[key]) for key in self.data)
        if self.all_keys:
            fmt = "Dict({{{data}}}, {all_keys}, keys={key_type}, values={value_type})"
        return fmt.format(data=data_str, all_keys=self.all_keys, key_type=self.key_type,
                          value_type=self.value_type)

    def __getitem__(self, key):
        """
        Returns the Type of the keys value.
        """
        if key in self.data:
            return self.data[key]
        if not self.all_keys and isinstance(key, self.key_type):
            return self.value_type
        return NonExistent()

    def _eq_impl(self, other):
        # hack improve this method
        return all(self.data[key] == other.data[key] for key in itertools.chain(self.data.keys(), other.data.keys()))


class Int(Type):
    """
    Checks for the value to be of type int and to adhere to some constraints.
    """

    def __init__(self, constraint = None, range = None, description: str = None):
        """
        :param constraint: user defined constrained function
        :param range. range (or list) that the value has to be part of
        :param description: description of the constraints
        """
        self.constraint = constraint
        self.range = range
        self.description = description

    def _instancecheck_impl(self, value, info: Info):
        if not isinstance(value, int) or (self.constraint != None and not self.constraint(value)) \
                or (self.range != None and value not in self.range):
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


def NaturalNumber(constraint = None):
    """
    Matches all natural numbers (ints larger than zero) that satisfy the optional user defined constrained.
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


def Str(constraint = None):
    """
    Alias for Constraint(constraint, T(str)) or T(str)
    """
    if constraint is not None:
        return Constraint(constraint, T(str))
    return T(str)


def BoolLike(constraint = None):
    """
    Alias for Constraint(constraint, t) or t, with t being an alias
    for Constraint(lambda x: x in ["true", "false", 0, 1, True, False])
    """
    t = Constraint(lambda x: x in ["true", "false", 0, 1, True, False])
    if constraint is not None:
        return Constraint(constraint, t)
    return t


def verbose_issinstance(value, type, value_name: str = None):
    """
    Verbose version of isinstance that returns a InfoMsg object.

    :param value: value to check
    :param type: type or Type to check for
    :param value_name: name of the passed value (improves the error message)
    """
    if not isinstance(type, Type):
        type = T(type)
    return type.__instancecheck__(value, Info(value_name))