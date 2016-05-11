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

import typing as t

__all__ = [
    "Type",
    "Exact",
    "ExactEither",
    "T",
    "E",
    "Any",
    "Int",
    "Float",
    "NonExistent",
    "Bool",
    "BoolOrNone",
    "Str",
    "NaturalNumber",
    "FileName",
    "FileNameOrStdOut",
    "ValidYamlFileName",
    "PositiveInt",
    "DirName",
    "ValidTimeSpan",

    "Info",
    "Description",
    "Default",
    "CompletionHint",
    "YAML_FILE_COMPLETION_HINT",

    "All",
    "Either",
    "Optional",
    "Constraint",
    "NonErrorConstraint",
    "List",
    "StrList",
    "ListOrTuple",
    "Tuple",
    "Dict",
    "verbose_isinstance",
    "typecheck",
    "typecheck_locals"
]

import pytimeparse
import itertools, os, click, inspect
try:
    import yaml
except ImportError:
    import pureyaml as yaml

class ConstraintError(ValueError):
    """
    Error that is thrown if a constraint isn't met.
    """
    pass


class Info:
    """
    Information object that is used to produce meaningful type check error messages.
    """

    def __init__(self, value_name: str = None, value = None, _app_str: str = None):
        """
        Creates a new info object.

        :param value_name: name of the value that is type checked
        :param value: value that is type checked
        """
        self.value_name = value_name  # type: str
        """ Name of the value that is typechecked """
        self._app_str = _app_str or ""  # type: str
        if value_name is None:
            self._value_name = "value {{!r}}{}".format(self._app_str)
        else:
            self._value_name = "{}{} of value {{!r}}".format(self.value_name, self._app_str)
        self.value = None
        """ Main value that is type checked """
        self.has_value = False  # type: bool
        """ Is the value property of this info object set to a meaningful value? """
        if value is not None:
            self.value = value
            self.has_value = True

    def set_value(self, value):
        """ Set the main value of this object """
        self.value = value
        self.has_value = True

    def get_value(self) -> t.Any:
        """
        Get the main value of this object.
        :raises: ValueError if the main value isn't set
        """
        if not self.has_value:
            raise ValueError("value is not defined")
        return self.value

    def add_to_name(self, app_str: str) -> 'Info':
        """
        Creates a new info object based on this one with the given appendix to it's value representation.
        It's used to give information about what part of the main value is currently examined.

        :param app_str: app string appended to the own app string to create the app string for the new info object
        :return: new info object
        """
        return Info(self.value_name, self.value, self._app_str + app_str)

    def _str(self):
        return self._value_name.format(self.get_value())

    def errormsg(self, constraint: 'Type', msg: str = None) -> 'InfoMsg':
        """
        Creates an info message object with the passed expected type and the optional message.

        :param constraint: passed expected type
        :param msg: additional message, it should give more information about why the constraint isn't met
        """
        app = ": " + (msg or "")
        return InfoMsg("{} hasn't the expected type {}{}".format(self._str(), constraint, app))

    def errormsg_cond(self, cond: bool, constraint: 'Type', msg: str = None) -> 'InfoMsg':
        """
        Creates an info message object with the passed expected type and the optional message.

        :param cond: if this is false `InfoMsg(True)` is returned.
        :param constraint: passed expected type
        :param msg: additional message, it should give more information about why the constraint isn't met
        """
        if cond:
            return InfoMsg(True)
        else:
            return self.errormsg(constraint, msg)

    def errormsg_non_existent(self, constraint: 'Type') -> 'InfoMsg':
        """
        Creates an info message object with the passed expected type that contains the message that
        currently examined part of the value is unexpected.

        :param constraint: passed expected type
        """
        return InfoMsg("{} is non existent, expected value of type {}".format(self._str(), constraint))

    def errormsg_too_many(self, constraint: 'Type', value_len: int, constraint_len: int) -> 'InfoMsg':
        """
        Creates an info message object with the passed expected type that contains the message that
        currently examined part of the value has to many elements.

        :param constraint: passed expected type
        :param value_len: actual number of elements
        :param constraint_len: expected number of elements
        """
        return InfoMsg("{} has to many elements ({}), " \
               "expected value of type {} with {} elements".format(self._str(), value_len, constraint, constraint_len))

    def wrap(self, result: bool) -> 'InfoMsg':
        """
        Wrap the passed bool into a InfoMsg object.
        """
        return InfoMsg(result)

    def __getitem__(self, item):
        """ This method isn't implemented """
        raise NotImplementedError()

    def __setitem__(self, key, value):
        """ This method isn't implemented """
        raise NotImplementedError()


class NoInfo(Info):
    """
    A dumb version of the information class that is used when meaningful error messages aren't needed.
    It has better performance characteristics as it doesn't store any values or create strings.
    """

    def __init__(self, value_name: str = None, _app_str: str = None, value=None):
        if False:
            super().__init__(value_name, _app_str, value)
        self.has_value = True

    def get_value(self) -> None:
        return None

    def set_value(self, value):
        pass

    def add_to_name(self, app_str: str) -> 'NoInfo':
        return self

    def errormsg(self, constraint: 'Type', msg: str = None) -> 'InfoMsg':
        return InfoMsg(False)

    def errormsg_cond(self, cond: bool, constraint: 'Type', msg: str = None) -> 'InfoMsg':
        return InfoMsg(cond)

    def errormsg_non_existent(self, constraint: 'Type') -> 'InfoMsg':
        return InfoMsg(False)

    def errormsg_too_many(self, constraint: 'Type', value_len: int, constraint_len: int) -> 'InfoMsg':
        return InfoMsg(False)

    def wrap(self, result: bool) -> 'InfoMsg':
        return InfoMsg(result)


class InfoMsg:
    """
    Simple message class used by the Info class.
    """

    def __init__(self, msg_or_bool: t.Union[str, bool]):
        """
        Creates an message object.

        :param msg_or_bool: if the value isn't true than is expected to be unsuccessful
        """
        self.success = msg_or_bool is True  # type: bool
        """ Was the type checking succesfull? """
        self.msg = msg_or_bool if isinstance(msg_or_bool, str) else str(self.success)  # type: str
        """ The error message or true if the type checking was successful """

    def __str__(self) -> str:
        return self.msg

    def __bool__(self) -> bool:
        return self.success


class Description:
    """
    A description of a Type, that annotates it.
    Usage example::

        Int() // Description("Description of Int()")
    """

    def __init__(self, description: str):
        typecheck(description, str)
        self.description = description
        """ Description string """

    def __str__(self) -> str:
        return self.description


class Default:
    """
    A default value annotation for a Type.
    Usage example::

        Int() // Default(3)

    Especially useful to declare the default value for a key of an dictionary.
    Allows to use Dict(...).get_default() -> dict.
    """

    def __init__(self, default):
        self.default = default
        """ Default value of the annotated type """


YAML_FILE_COMPLETION_HINT = "_files -g '*\.yaml'"  # type: str
""" YAML file name completion hint for ZSH """

class CompletionHint(object):
    """
    A completion hint annotation for a type.
    Usage example::

        Int() // Completion(zsh="_files")
    """

    def __init__(self, **hints):
        self.hints = hints
        """ Completion hints for every supported shell """


class Type(object):
    """
    A simple type checker type class.
    """

    def __init__(self, completion_hints: t.Dict[str, t.Any] = None):
        """
        Creates an instance.

        :param completion_hints: completion hints for supported shells for this type instance
        """
        self.description = None  # type: t.Optional[str]
        """ Description of this type instance """
        self.default = None  # type: t.Optional[Default]
        """ Default value of this type instance """
        self.typecheck_default = True  # type: bool
        """ Type check the default value """
        self.completion_hints = {}  # type: t.Dict[str, t.Any]
        """ Completion hints for supported shells for this type instance """

    def __instancecheck__(self, value, info: Info = NoInfo()) -> InfoMsg:
        """
        Checks whether or not the passed value has the type specified by this instance.

        :param value: passed value
        :param info: info object for creating error messages
        """
        if not info.has_value:
            info.set_value(value)
        return self._instancecheck_impl(value, info)

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        """
        This method should be implemented by all sub classes.
        It checks whether or not the passed value has the type specified by this type instance.

        :param value: passed value
        :param info: info object used to produce (meaningful) error or success messages
        """
        return info.wrap(False)

    def __str__(self) -> str:
        return "Type()"

    def _validate_types(self, *types: t.Tuple['Type']):
        """
        Checks if all the passed values are instance of the Type class (or a sub class)
        :param types: passed values
        :raises: ConstraintError if this isn't the case
        """
        for t in types:
            if not isinstance(t, Type):
                raise ConstraintError("{} is not an instance of a Type subclass".format(t))

    def __and__(self, other: 'Type') -> 'Type':
        """
        Alias for All(self, other)
        """
        return All(self, other)

    def __or__(self, other: 'Type') -> 'Type':
        """
        Alias for Either(self, other).
        The only difference is that it flattens trees of Either instances.
        """
        if isinstance(other, Either):
            other.types.index(other, 0)
            return other
        return Either(self, other)

    def __floordiv__(self, other: t.Union[str, Description, Default, CompletionHint,
                                          t.Callable[[t.Any], bool]]) -> 'Type':
        """
        Alias for Constraint(other, self). Self mustn't be a Type.
        If other is a string the description property of this Type object is set.
        It also can annotate the object with Description, Default or CompletionHint objects.
        """
        if isinstance(other, str) or isinstance(other, Description):
            self.description = str(other)
            return self
        if isinstance(other, Default):
            self.default = other
            if self.typecheck_default:
                typecheck(self.default.default, self)
            return self
        if isinstance(other, CompletionHint):
            for shell in other.hints:
                self.completion_hints[shell] = other.hints[shell]
            return self
        if isinstance(other, Type):
            raise ConstraintError("{} mustn't be an instance of a Type subclass".format(other))
        return Constraint(other, self)

    def __eq__(self, other) -> bool:
        if type(other) == type(self):
            return self._eq_impl(other)
        return False

    def _eq_impl(self, other: 'Type') -> bool:
        return False

    def get_default(self) -> t.Any:
        """
        Returns the default value of this type
        :raises: ValueError if the default value isn't set
        """
        if self.default is None:
            raise ValueError("{} has no default value.".format(self))
        return self.default.default

    def has_default(self) -> bool:
        """
        Does this type instance have an default value?
        """
        return self.default is not None

    def get_default_yaml(self, indents: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) \
            -> t.Union[str, t.List[str]]:
        """
        Produce a YAML like string that contains the default value and the description of this type and it's possible sub types.

        :param indents: number of indents in front of each produced line
        :param indentation: indentation width in number of white spaces
        :param str_list: return a list of lines instead of a combined string?
        :param defaults: default value that should be used instead of the default value of this instance
        """
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

    def string_representation(self, indents: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) \
            -> t.Union[str, t.List[str]]:
        """
        Produce a YAML string that contains the default value (if possible), the description of this type
        and more and it's possible sub types.

        :param indents: number of indents in front of each produced line
        :param indentation: indentation width in number of white spaces
        :param str_list: return a list of lines instead of a combined string?
        :param defaults: default value that should be used instead of the default value of this instance
        """
        def pad(text: t.Union[str, t.List[str]], offset: int) -> t.Union[str, t.List[str]]:
            os = " " * (offset * indentation)
            if isinstance(text, str):
                return os + "\n".join(pad(text.split("\n"), offset))
            return list(map(lambda x: os + x, text))

        if defaults is None:
            if self.has_default():
                defaults = self.get_default()

        default_str = None
        if defaults:
            default_str = yaml.dump(defaults).strip()
            if default_str.endswith("\n..."):
                default_str = default_str[0:-4]
        y_str = str(self)
        #if self.description:
        #    y_str += "\n" + pad("description: " + pad(self.description, 1), 1)
        if default_str:
            y_str += "\n" + pad("default: " + pad(default_str, 0), 1)
        text = pad(y_str, indents)
        return text.split("\n") if str_list else text

    def dont_typecheck_default(self) -> 'Type':
        """
        Disable type checking the default value.
        :return: self
        """
        self.typecheck_default = False
        return self


class Exact(Type):
    """
    Checks for value equivalence.
    """

    def __init__(self, exp_value):
        """
        Creates an Exact object.

        :param exp_value: value to check for
        """
        super().__init__()
        self.exp_value = exp_value
        """ Expected value """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        """
        Is the value the same as the expected one?
        """
        cond = isinstance(value, type(self.exp_value)) and value == self.exp_value
        return info.errormsg_cond(cond, self, value)

    def __str__(self):
        return "Exact({!r})".format(self.exp_value)

    def _eq_impl(self, other: 'Exact') -> bool:
        return other.exp_value == self.exp_value

    def __or__(self, other) -> t.Union['ExactEither', 'Either']:
        if isinstance(other, ExactEither):
            other.exp_values.insert(0, self.exp_value)
            return other
        if isinstance(other, Exact):
            return ExactEither(self.exp_value, other.exp_value)
        return Either(self, other)


def E(exp_value) -> Exact:
    """
    Alias for Exact.
    """
    return Exact(exp_value)


class Either(Type):
    """
    Checks for the value to be of one of several types.
    """

    def __init__(self, *types: tuple):
        """
        Creates an Either instance.

        :param types: list of types (or SpecialType subclasses)
        :raises: ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self._validate_types(*types)
        self.types = list(types)
        """ Possible types """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
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

    def _eq_impl(self, other: 'Either') -> bool:
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))

    def __or__(self, other) -> 'Either':
        if isinstance(other, Either):
            self.types += other.types
            return self
        return Either(self, other)


class ExactEither(Type):
    """
    Checks for the value to be of one of several exact values.
    """

    def __init__(self, *exp_values: tuple):
        """
        Creates an ExactEither instance.

        :param exp_values: list of types (or SpecialType subclasses)
        :raises: ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self.exp_values = list(exp_values)
        """ Expected values """
        self._update_completion_hints()

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        """
        Does the type of the value match one of the expected types?
        """
        if value in self.exp_values:
            return info.wrap(True)
        return info.errormsg(self)

    def __str__(self) -> str:
        return "ExactEither({})".format("|".join(repr(val) for val in self.exp_values))

    def _eq_impl(self, other: 'ExactEither') -> bool:
        return len(other.exp_values) == len(self.exp_values) \
               and all(other.exp_values[i] == self.exp_values[i] for i in range(len(self.exp_values)))

    def __or__(self, other) -> t.Union['ExactEither', Either]:
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

    def __init__(self, *types: t.Tuple[Type]):
        """
        Creates an All instance.

        :param types: list of types (or SpecialType subclasses)
        :raises: ConstraintError if some of the contraints aren't (typechecker) Types
        """
        super().__init__()
        self._validate_types(*types)
        self.types = types
        """ Expected types """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        """
        Does the type of the value match all of the expected types?
        """
        for type in self.types:
            res = type.__instancecheck__(value, info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self) -> str:
        return "All[{}]".format("|".join(str(type) for type in self.types))

    def _eq_impl(self, other: 'All') -> bool:
        return len(other.types) == len(self.types) \
               and all(other.types[i] == self.types[i] for i in range(len(self.types)))


class Any(Type):
    """
    Checks for the value to be of any type.
    """
    def __instancecheck__(self, value, info: Info = NoInfo()) -> InfoMsg:
        return info.wrap(True)

    def __str__(self) -> str:
        return "Any"

    def _eq_impl(self, other: 'Any') -> bool:
        return True


class T(Type):
    """
    Wrapper around a native type.
    """

    def __init__(self, native_type: type):
        """
        Creates an isntance.

        :param native_type: wrapped native type
        """
        super().__init__()
        if not isinstance(native_type, type):
            raise ConstraintError("{} is not a native type".format(type))
        self.native_type = native_type
        """ Native type that is wrapped """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        """
        Does the passed value be an instance of the wrapped native type?
        """
        return info.errormsg_cond(isinstance(value, self.native_type), self)

    def __str__(self) -> str:
        return "T({})".format(self.native_type)

    def _eq_impl(self, other: 'T'):
        return other.native_type == self.native_type


class Optional(Either):
    """
    Checks the value and checks that its either of native type None or of another Type constraint.
    Alias for Either(Exact(None), other_type)
    """

    def __init__(self, other_type: Type):
        """
        Creates an Optional instance.

        :param other_type: type to make optional
        :raises: ConstraintError if other_type isn't a (typechecker) Types
        """
        super().__init__(Exact(None), other_type)

    def __str__(self) -> str:
        return "Optional({})".format(self.types[1])


class Constraint(Type):
    """
    Checks the passed value by an user defined constraint.
    """

    def __init__(self, constraint: t.Callable[[t.Any], bool], constrained_type: Type = Any(), description: str = None):
        """
        Creates an Constraint instance.

        :param constraint: function that returns True if the user defined constraint is satisfied
        :param constrained_type: Type that the constraint is applied on
        :param description: short description of the constraint (e.g. ">0")
        :raises: ConstraintError if constrained_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(constrained_type)
        self.constraint = constraint  # type: t.Callable[[t.Any], bool]
        """ Function that returns True if the user defined constraint is satisfied """
        self.constrained_type = constrained_type  # type: Type
        """ Type that the constraint is applied on """
        self.description = description  # type: str
        """ Short description of the constraint (e.g. ">0") """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
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

    def __str__(self) -> str:
        descr = self.description
        if self.description is None:
            #if isinstance(self.constraint, type(fn._)):
            #    descr = str(self.constraint)
            #else:
            descr = "<function>"
        return "{}:{}".format(self.constrained_type, descr)


class NonErrorConstraint(Type):
    """
    Checks the passed value by an user defined constraint that fails if it raises an error.
    """

    def __init__(self, constraint: t.Callable[[t.Any], t.Any], error_cls: type, constrained_type: Type = Any(),
                 description: str = None):
        """
        Creates a new instance

        :param constraint: function that doesn't raise an error if the user defined constraint is satisfied
        :param error_cls: class of the errors the constraint method raises
        :param constrained_type: Type that the constraint is applied on
        :param description: short description of the constraint (e.g. ">0")
        :raises: ConstraintError if constrained_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(constrained_type)
        self.constraint = constraint  # type: t.Callable[[t.Any], t.Any]
        """ Function that returns True if the user defined constraint is satisfied """
        self.error_cls = error_cls  # type: type
        """ Class of the errors the constraint method raises """
        self.constrained_type = constrained_type  # type: Type
        """ Type that the constraint is applied on """
        self.description = description  # type: str
        """ Short description of the constraint (e.g. ">0") """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
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

    def __str__(self) -> str:
        descr = self.description
        if self.description is None:
            descr = "<function>"
        return "{}:{}".format(self.constrained_type, descr)


class List(Type):
    """
    Checks for the value to be a list with elements of a given type.
    """

    def __init__(self, elem_type: Type = Any()):
        """
        Creates a new instance.

        :param elem_type: type of the list elements
        :raises: ConstraintError if elem_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(elem_type)
        self.elem_type = elem_type  # type: Type
        """ Expected type of the list elements """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        if not isinstance(value, list):
            return info.errormsg(self)
        for (i, elem) in enumerate(value):
            new_info = info.add_to_name("[{}]".format(i))
            res = self.elem_type.__instancecheck__(elem, new_info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self) -> str:
        return "List({})".format(self.elem_type)

    def _eq_impl(self, other: 'List') -> bool:
        return other.elem_type == self.elem_type


class ListOrTuple(Type):
    """
    Checks for the value to be a list or tuple with elements of a given type.
    """

    def __init__(self, elem_type: Type = Any()):
        """
        Creates an instance.

        :param elem_type: type of the list or tuple elements
        :raises: ConstraintError if elem_type isn't a (typechecker) Types
        """
        super().__init__()
        self._validate_types(elem_type)
        self.elem_type = elem_type  # type: Type
        """ Expected type of the list or tuple elements """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
        if not isinstance(value, T(list) | T(tuple)):
            return info.errormsg(self)
        for (i, elem) in enumerate(list(value)):
            new_info = info.add_to_name("[{}]".format(i))
            res = self.elem_type.__instancecheck__(elem, new_info)
            if not res:
                return res
        return info.wrap(True)

    def __str__(self) -> str:
        return "ListOrTuple({})".format(self.elem_type)

    def _eq_impl(self, other: 'ListOrTuple') -> bool:
        return other.elem_type == self.elem_type


class Tuple(Type):
    """
    Checks for the value to be a tuple (or a list) with elements of the given types.
    """

    def __init__(self, *elem_types: t.Tuple[Type]):
        """
        Creates a new instance.

        :param elem_types: types of each tuple element
        :raises: ConstraintError if elem_type isn't a (typechecker) Types
        """
        super().__init__()
        for elem_type in elem_types:
            self._validate_types(elem_type)
        self.elem_types = elem_types  # type: t.Tuple[Type]
        """ Expected type of each tuple element """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
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

    def __str__(self) -> str:
        return "Tuple({})".format(", ".join(str(t) for t in self.elem_types))

    def _eq_impl(self, other: 'Tuple') -> bool:
        return len(other.elem_types) == len(self.elem_types) and \
               all(a == b for (a, b) in itertools.product(self.elem_types, other.elem_types))


class _NonExistentVal(object):
    """
    Helper class for NonExistent Type.
    """

    def __str__(self) -> str:
        return "<non existent>"

    def __repr__(self) -> str:
        return self.__str__()

_non_existent_val = _NonExistentVal()


class NonExistent(Type):
    """
    Checks a key of a dictionary for existence if its associated value has this type.
    """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        return info.errormsg_cond(type(value) == _NonExistentVal, self, "[value]")

    def __str__(self) -> str:
        return "non existent"

    def _eq_impl(self, other: 'NonExistent') -> bool:
        return True


class Dict(Type):
    """
    Checks for the value to be a dictionary with expected keys and values satisfy given type constraints.
    """

    def __init__(self, data: t.Dict[t.Any, Type] = None, all_keys: bool = True, key_type: Type = Any(),
                 value_type: Type = Any()):
        """
        Creates a new instance.

        :param data: dictionary with the expected keys and the expected types of the associated values
        :param all_keys: does the type checking fail if more keys are present in the value than in data?
        :param key_type: expected Type of all dictionary keys
        :param value_type: expected Type of all dictionary values
        :raises: ConstraintError if one of the given types isn't a (typechecker) Types
        """
        super().__init__()
        self.data = data or {}  # type: t.Dict[t.Any, Type]
        self._validate_types(*self.data.values())
        self._validate_types(key_type, value_type)
        self.all_keys = all_keys  # type: bool
        """ Does the type checking fail if more keys are present in the value than in data? """
        self.key_type = key_type  # type: Type
        """ Expected Type of all dictionary keys """
        self.value_type = value_type  # type: Type
        """ Expected Type of all dictionary values """

    def _instancecheck_impl(self, value, info: Info = NoInfo()) -> InfoMsg:
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

    def __str__(self) -> str:
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

    def __setitem__(self, key, value: Type):
        """
        Sets the Type of the keys values.
        :raises: ValueError if the key or the value have the wrong types (don't match key_type and value_type)
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
        return all(key in self.data and key in other.data and self.data[key] == other.data[key]
                   and self.get_description(key) == other.get_description(key)
                   for key in itertools.chain(self.data.keys(), other.data.keys()))

    def get_default(self) -> dict:
        default_dict = {}
        if self.default is not None:
            default_dict = self.default.default
        for key in self.data:
            if key not in default_dict:
                default_dict[key] = self[key].get_default()
        return default_dict

    def has_default(self) -> bool:
        default_dict = {}
        if self.default is not None:
            default_dict = self.default.default
        return all(self[key].has_default() for key in self.data if key not in default_dict)

    def get_default_yaml(self, indent: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) -> str:
        if len(self.data.keys()) == 0:
            ret = "!!map {}"
            return [ret] if str_list else ret
        if defaults is None:
            defaults = self.get_default()
        else:
            typecheck(defaults, self)

        strs = []
        groups = {
            "simple": [],
            "misc": []
        }
        for key in self.data:
            if isinstance(self.data[key], Dict):
                groups["misc"].append(key)
            else:
                groups["simple"].append(key)
        keys = sorted(groups["simple"]) + sorted(groups["misc"])

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

    def string_representation(self, indents: int = 0, indentation: int = 4, str_list: bool = False, defaults = None) \
            -> t.Union[str, t.List[str]]:
        """
        Produce a YAML string that contains the default value (if possible), the description of this type
        and more and it's possible sub types.

        :param indents: number of indents in front of each produced line
        :param indentation: indentation width in number of white spaces
        :param str_list: return a list of lines instead of a combined string?
        :param defaults: default value that should be used instead of the default value of this instance
        """
        if len(self.data.keys()) == 0:
            return super().string_representation(indents, indentation, str_list, defaults)

        def pad(text: t.Union[str, t.List[str]], offset: int) -> t.Union[str, t.List[str]]:
            os = " " * (offset * indentation)
            if isinstance(text, str):
                return os + "\n".join(pad(text.split("\n"), offset))
            return list(map(lambda x: os + x, text))

        if defaults is None:
            if self.has_default():
                defaults = self.get_default()

        strs = []
        groups = {
            "simple": [],
            "misc": []
        }
        for key in self.data:
            if isinstance(self.data[key], Dict):
                groups["misc"].append(key)
            else:
                groups["simple"].append(key)
        keys = sorted(groups["simple"]) + sorted(groups["misc"])
        for i in range(0, len(keys)):
            #if i != 0:
            strs.append("")
            key = keys[i]
            if self.data[key].description is not None:
                comment_lines = self.data[key].description.split("\n")
                comment_lines = map(lambda x: "# " + x, comment_lines)
                strs.extend(comment_lines)
            key_yaml = yaml.dump(key).split("\n")[0]
            if len(self.data[key].string_representation(str_list=True, defaults=defaults[key])) == 1 and \
                    (not isinstance(self.data[key], Dict) or len(self.data[key].data.keys()) == 0):
                value_yaml = self.data[key].string_representation(1, indentation, str_list=False, defaults=defaults[key])
                strs.append("{}: {}".format(key_yaml, value_yaml))
            else:
                value_yaml = self.data[key].string_representation(1, indentation, str_list=True, defaults=defaults[key])
                strs.append("{}: {}".format(key_yaml, value_yaml[0]))
                if len(value_yaml) > 1:
                    strs.extend(value_yaml[1:])
        strs = pad(strs, indents)
        return strs if str_list else "\n".join(strs)


class Int(Type):
    """
    Checks for the value to be of type int and to adhere to some constraints.
    """

    def __init__(self, constraint: t.Callable[[t.Any], bool] = None, range: range = None, description: str = None):
        """
        Creates an instance.

        :param constraint: function that returns True if the user defined constraint is satisfied
        :param range: range (or list) that the value has to be part of
        :param description: description of the constraints
        """
        super().__init__()
        self.constraint = constraint  # type: t.Optional[t.Callable[[t.Any], bool]]
        """ Function that returns True if the user defined constraint is satisfied """
        self.range = range  # type: range
        """ Range (or list) that the value has to be part of """
        self.description = description  # type: str
        """ Description of the constraints """
        if range is not None and len(range) <= 20:
            self.completion_hints = {  # type: t.Dict[str, t.Any]
                "zsh": "({})".format(" ".join(str(x) for x in range)),
                "fish": {
                    "hint": list(self.range)
                }
            }
            """ Completion hints for supported shells for this type instance """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        if not isinstance(value, int) or (self.constraint is not None and not self.constraint(value)) \
                or (self.range is not None and value not in self.range):
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self) -> str:
        arr = []
        if self.constraint is not None:
            descr = "<function>"
            arr.append("constraint={}".format(descr))
        if self.range is not None:
            arr.append("range={}".format(self.range))
        return "Int({})".format(",".join(arr))

    def _eq_impl(self, other: 'Int') -> bool:
        return other.constraint == self.constraint and other.range == self.range


class StrList(Type, click.ParamType):
    """
    A comma separated string list which contains elements from a fixed set of allowed values.
    """

    name = "comma_sep_str_list"  # type: str
    """ click.ParamType name, that makes this class usable as a click type """

    def __init__(self):
        super().__init__()
        self.allowed_values = None  # type: t.Optional[t.List[str]]
        """ Possible values that can appear in the string list, if None all values are allowed. """

    def __or__(self, other) -> t.Union[Either, 'StrList']:
        if isinstance(other, Exact) and isinstance(other.exp_value, Str()):
            if self.allowed_values is None:
                self.allowed_values = [other.exp_value]
            else:
                self.allowed_values.append(other.exp_value)
            return self
        return super().__or__(other)

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        res = List(Str()).__instancecheck__(value, info)
        if not res:
            return info.errormsg(self, "Not a list of strings")
        if self.allowed_values is None or all(val in self.allowed_values for val in value):
            return info.wrap(True)
        return info.errormsg(self, "Does contain invalid elements")

    def convert(self, value, param, ctx: click.Context) -> t.List[str]:
        """
        Convert method that makes this class usable as a click type.
        """
        if isinstance(value, self):
            return value
        elif isinstance(value, str):
            value = str(value)
            return value.split(",")
        self.fail("{} is no valid comma separated string list".format(value), param, ctx)

    def __str__(self) -> str:
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

    def _eq_impl(self, other: 'StrList') -> bool:
        return self.allowed_values == other.allowed_values


class Str(Type):
    """
    Checks for the value to be a string an optionally meet some constraints.
    """

    def __init__(self, constraint: t.Callable[[t.Any], bool] = None):
        """
        Creates an instance.

        :param constraint: function that returns True if the user defined constraint is satisfied
        """
        super().__init__()
        self.constraint = constraint  # type: t.Optional[t.Callable[[t.Any], bool]]
        """ Function that returns True if the user defined constraint is satisfied """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        if not isinstance(value, str):
            return info.errormsg(self)
        if self.constraint is not None and not self.constraint(value):
            return info.errormsg(self)
        return info.wrap(True)

    def __str__(self) -> str:
        if self.constraint is not None:
            return "Str({})".format(repr(self.constraint))
        else:
            return "Str()"

    def _eq_impl(self, other: 'Str') -> bool:
        return self.constraint == other.constraint


class FileName(Str):
    """
    A valid file name. If the file doesn't exist, at least the parent directory must exist
    and the file must be creatable.
    """

    def __init__(self, constraint: t.Callable[[t.Any], bool] = None, allow_std: bool = False,
                 allow_non_existent: bool = True):
        """
        Creates an instance.

        :param constraint: function that returns True if the user defined constraint is satisfied
        :param allow_std: allow '-' as standard out or in
        :param allow_non_existent: allow files that don't exist
        """
        super().__init__()
        self.constraint = constraint  # type: t.Optional[t.Callable[[t.Any], bool]]
        """ Function that returns True if the user defined constraint is satisfied """
        self.completion_hints = {   # type: t.Dict[str, t.Any]
            "zsh": "_files",
            "fish": {
                "files": True
            }
        }
        """ Completion hints for supported shells for this type instance """
        self.allow_std = allow_std  # type: bool
        """ Allow '-' as standard out or in """
        self.allow_non_existent = allow_non_existent  # type: bool
        """ Allow files that don't exist """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        if not isinstance(value, str) or value == "":
            return info.errormsg(self)
        value = os.path.expanduser(value)
        if self.allow_std and value == "-" and (self.constraint is None or self.constraint(value)):
            return info.wrap(True)
        is_valid = True
        if os.path.exists(value):
            if os.path.isfile(value) and os.access(os.path.abspath(value), os.W_OK)\
                    and (self.constraint is None or self.constraint(value)):
                return info.wrap(True)
            return info.errormsg(self)
        if not self.allow_non_existent:
            return info.errormsg(self, "File doesn't exist")
        abs_name = os.path.abspath(value)
        dir_name = os.path.dirname(abs_name)
        if os.path.exists(dir_name) and os.access(dir_name, os.EX_OK) and os.access(dir_name, os.W_OK) \
            and (self.constraint is None or self.constraint(value)):
            return info.wrap(True)
        return info.errormsg(self)

    def __str__(self) -> str:
        if self.constraint is not None:
            return "FileName({}, allow_std={})".format(repr(self.constraint), self.allow_std)
        else:
            return "FileName(allow_std={})".format(self.allow_std)

    def _eq_impl(self, other: 'FileName') -> bool:
        return self.constraint == other.constraint and self.allow_std == other.allow_std \
               and self.allow_non_existent == other.allow_non_existent


class ValidYamlFileName(Str):
    """
    A valid file name that refers to a valid YAML file.
    """

    def __init__(self, allow_non_existent: bool = False):
        """
        Create an instance.

        :param allow_non_existent: allow files that don't exist
        """
        super().__init__()
        self.completion_hints = {  # type: t.Dict[str, t.Any]
            "zsh": "_files",
            "fish": {
                "files": True
            }
        }
        """ Completion hints for supported shells for this type instance """
        self.allow_non_existent = allow_non_existent  # type: bool
        """ Allow files that don't exist """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        if not isinstance(value, str):
            return info.errormsg(self, "isn't a string")
        if not os.path.exists(value):
            if not self.allow_non_existent or not isinstance(value, FileName()):
                return info.errormsg(self, "doesn't exist or hasn't an accessible parent directory")
            return info.wrap(True)
        if not os.path.isfile(value):
            return info.errormsg(self, "isn't a file")
        try:
            with open(value, "r") as f:
                 yaml.load(f)
        except (IOError, Exception) as ex:
            return info.errormsg(self, "YAML parse error: " + str(ex))
        return info.wrap(True)

    def __str__(self) -> str:
        return "ValidYamlFileName()"

    def _eq_impl(self, other: 'ValidYamlFileName') -> bool:
        return self.allow_non_existent == other.allow_non_existent


class DirName(Str):
    """
    A valid directory name. If the directory doesn't exist, at least the parent directory must exist.
    """

    def __init__(self, constraint: t.Callable[[t.Any], bool] = None):
        """
        Creates an instance.

        :param constraint: function that returns True if the user defined constraint is satisfied
        """
        super().__init__()
        self.constraint = constraint  # type: t.Optional[t.Callable[[t.Any], bool]]
        """ Function that returns True if the user defined constraint is satisfied """
        self.completion_hints = {  # type: t.Dict[str, t.Any]
            "zsh": "_directories",
            "fish": {
                "files": True
            }
        }
        """ Completion hints for supported shells for this type instance """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        if not isinstance(value, str):
            return info.errormsg(self)
        is_valid = True
        if os.path.exists(value):
            if os.path.isdir(value) and os.access(os.path.abspath(value), os.W_OK)\
                    and (self.constraint is None or self.constraint(value)):
                return info.wrap(True)
            return info.errormsg(self)
        abs_name = os.path.abspath(value)
        dir_name = os.path.dirname(abs_name)
        if os.path.exists(dir_name) and os.access(dir_name, os.EX_OK) and os.access(dir_name, os.W_OK) \
            and (self.constraint is None or self.constraint(value)):
            return info.wrap(True)
        return info.errormsg(self)

    def __str__(self) -> str:
        if self.constraint is not None:
            return "DirName({})".format(repr(self.constraint))
        else:
            return "DirName()"

    def _eq_impl(self, other: 'DirName') -> bool:
        return self.constraint == other.constraint


class BoolOrNone(Type, click.ParamType):
    """
    Like Bool but with a third value none that declares that the value no boolean value.
    It has None as its default value (by default).
    """

    name = "bool_or_none"  # type: str
    """ click.ParamType name, that makes this class usable as a click type """

    def __init__(self):
        super().__init__()
        self.completion_hints = {  # type: t.Dict[str, t.Any]
            "zsh": "(true, false, none)",
            "fish": {
                "hint": ["true", "false", "none"]
            }
        }
        """ Completion hints for supported shells for this type instance """
        self.default = None  # type: None
        """ The default value of this instance """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        res = ExactEither(True, False, None).__instancecheck__(value, info)
        return info.errormsg_cond(bool(res), self, str(res))

    def convert(self, value, param, ctx: click.Context) -> t.Optional[bool]:
        """
        Convert method that makes this class usable as a click type.
        """
        if isinstance(value, self):
            return value
        elif isinstance(value, str):
            value = value.lower()
            if value == "true" :
                return True
            elif value == "false":
                return False
            elif value == "none":
                return None
        self.fail("{} is no valid bool or 'none'".format(value), param, ctx)

    def __str__(self) -> str:
        return "BoolOrNone()"

    def _eq_impl(self, other: 'BoolOrNone') -> bool:
        return True


class Bool(Type, click.ParamType):
    """
    Like Bool but with a third value none that declares that the value no boolean value.
    It has None as its default value (by default).
    """

    name = "bool"  # type: str
    """ click.ParamType name, that makes this class usable as a click type """

    def __init__(self):
        super().__init__()
        self.completion_hints = {  # type: t.Dict[str, t.Any]
            "zsh": "(true, false)",
            "fish": {
                "hint": ["true", "false"]
            }
        }
        """ Completion hints for supported shells for this type instance """

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        res = ExactEither(True, False).__instancecheck__(value, info)
        return info.errormsg_cond(bool(res), self, str(res))

    def __str__(self) -> str:
        return "Bool()"

    def _eq_impl(self, other: 'Bool') -> bool:
        return True


class ValidTimeSpan(Type, click.ParamType):
    """
    A string that is parseable as timespan by pytimeparse.
    E.g. "32m" or "2h 32m".
    """

    name = "valid_timespan"  # type: str
    """ click.ParamType name, that makes this class usable as a click type """

    def __init__(self):
        super().__init__()

    def _instancecheck_impl(self, value, info: Info) -> InfoMsg:
        res = Str().__instancecheck__(value, info)
        wrong = not bool(res) or pytimeparse.parse(value) == None
        if wrong:
            return info.errormsg(self, value)
        return info.wrap(True)

    def convert(self, value, param, ctx: click.Context) -> int:
        """
        Convert method that makes this class usable as a click type.
        """
        if isinstance(value, self):
            return value
        self.fail("{} is no valid time span".format(value), param, ctx)

    def __str__(self) -> str:
        return "ValidTimespan()"

    def _eq_impl(self, other: 'ValidTimeSpan') -> bool:
        return True


def NaturalNumber(constraint: t.Callable[[t.Any], bool] = None) -> Int:
    """
    Matches all natural numbers (ints >= 0) that satisfy the optional user defined constrained.

    :param constraint: function that returns True if the user defined constraint is satisfied
    """
    if constraint is not None:
        return Int(lambda x: x >= 0 and constraint(x))
    return Int(lambda x: x >= 0)


def PositiveInt(constraint: t.Callable[[t.Any], bool] = None) -> Int:
    """
    Matches all positive integers that satisfy the optional user defined constrained.

    :param constraint: function that returns True if the user defined constraint is satisfied
    """
    if constraint is not None:
        return Int(lambda x: x > 0 and constraint(x))
    return Int(lambda x: x > 0)


def Float(constraint: t.Callable[[t.Any], bool] = None) -> t.Union[T, Constraint]:
    """
    Alias for Constraint(constraint, T(float)) or T(float)

    :param constraint: function that returns True if the user defined constraint is satisfied
    """
    if constraint is not None:
        return Constraint(constraint, T(float))
    return T(float)


def FileNameOrStdOut() -> FileName:
    """
    A valid file name or "-" for standard out.
    """
    return FileName(allow_std=True)


def verbose_isinstance(value, type: t.Union[Type, type], value_name: str = None) -> InfoMsg:
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


def typecheck(value, type: t.Union[Type, type], value_name: str = None):
    """
    Like verbose_isinstance but raises an error if the value hasn't the expected type.

    :param value: passed value
    :param type: expected type of the value
    :param value_name: optional description of the value
    :raises: TypeError
    """
    if not bool(isinstance(value, type)):
        ret = verbose_isinstance(value, type, value_name)
        if not ret:
            raise TypeError(str(ret))


def typecheck_locals(locals: t.Dict[str, t.Any] = None, **variables: t.Dict[str, t.Union[Type, type]]):
    """
    Like typecheck but checks several variables for their associated expected type.
    The advantage against typecheck is that it sets the value descriptions properly.
    Example usage::

        def func(a: str, b: int):
            typecheck_locals(locals(), a=Str(), b=Int())

    :param locals: directory to get the variable values from
    :param variables: variable names with their associated expected types
    :raises: TypeError
    """
    if locals is None:
        locals = inspect.currentframe().f_back.f_locals
    else:
        typecheck(locals, Dict(all_keys=False, key_type=Str()))
    for var in variables:
        typecheck(locals[var], variables[var], value_name=var)


#class Callable(Type):
#    """
#    Checks for the value to be a callable or function.
#    WOrks only with simple types.
#    """
#
#    def __init__(self, arg_types: t.List[Type] = None, ret_type: Type = None):
#        super().__init__()
#        if arg_types:
#            self._validate_types(*arg_types)
#        if ret_type:
#            self._validate_types(ret_type)
#        self.arg_types = arg_types
#        self.ret_type = ret_type
#
#    def _instancecheck_impl(self, value, info: Info):
#        if type(value).__name__ != "function":
#            return info.errormsg(self)
#
#        def check_type(key: str, expected_type: Type) -> InfoMsg:
#            if key not in value.__annotations__:
#                return info.errormsg(self, "No type annotation for {!r}".format(key))
#            actual = typing_to_typecheck_type(value.__annotations__[key])
#            if actual != expected_type:
#                return info.errormsg(self, "Expected type {}, but got {} for {!r}".format(expected_type, actual, key))
#        if self.ret_type:
#            ret = check_type("return", self.ret_type)
#            if not ret:
#                return ret
#        if self.arg_types:
#            if len(self.arg_types) != len()
#
#
#def typing_to_typecheck_type(t_type: t.Union[t.List[t.Any], t.Any]) -> t.Union[Type, t.Iterable[Type]]:
#    if isinstance(t_type, list):
#        return [typing_to_typecheck_type(sub) for sub in t_type]
#    if isinstance(t_type, t.AnyMeta):
#        return Any()
#    elif isinstance(t_type, t.UnionMeta):
#        return Union(*typing_to_typecheck_type(*t_type.__union_params__))
#    elif isinstance(t_type, t.TupleMeta):
#        return Tuple(*typing_to_typecheck_type(*t_type.__tuple_params__))
#    elif isinstance(t_type, t.CallableMeta):
#        return Callable(typing_to_typecheck_type(t_type.__args__),
#                        typing_to_typecheck_type(t_type.__result__))
#    else:
#        return T(t_type)
#
#if __name__ == "__main__":
#    typecheck(None, typing_to_typecheck_type(t.Optional[int]))


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