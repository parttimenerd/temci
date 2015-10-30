from temci.utils.typecheck import *
import unittest, collections
from fn import _


class TestTypecheckModule(unittest.TestCase):

    def assertTypesCorrect(self, *tuples: object):
        for (value, type_constraint) in tuples:
            msg = "Value {!r} doesn't adhere to {!s}".format(value, type_constraint)
            res = type_constraint.__instancecheck__(value, Info("abc"))
            self.assertTrue(bool(res), msg="{}: {!s}".format(msg, res))
            self.assertTrue(isinstance(value, type_constraint), msg=msg)

    def assertTypesInCorrect(self, *tuples: object):
        for (value, type_constraint) in tuples:
            msg = "Value {!r} should adhere to {}".format(value, type_constraint)
            res = type_constraint.__instancecheck__(value, Info("abc"))
            self.assertFalse(bool(res), msg="{}: {}".format(msg, res))
            self.assertFalse(isinstance(value, type_constraint), msg=msg)

    def test_t(self):
        self.assertTypesCorrect(
            (3, T(int)),
            (True, T(bool)),
            (dict, T(type)),
            ("s", T(str)),
            (T(str), T(Type))
        )
        self.assertTypesInCorrect(
            ("fds", T(dict)),
            (4, T(float)),
            (int, T(int))
        )

    def test_exact(self):
        self.assertTypesCorrect(
            ("a", Exact("a")),
            (324, Exact(324)),
            ([4,5], Exact([4, 5])),
            (None, Exact(None))
        )
        self.assertTypesInCorrect(
            ("sd", Exact("s")),
            (3, Exact(3.0))
        )

    def test_either(self):
        self.assertTypesCorrect(
            (3, Either(T(int), T(float), T(str))),
            (3.0, Either(T(int), T(float), T(str))),
            ("sdf", Either(T(int), T(float), T(str))),
            ("sdf", Either(Exact("SDF"), Exact("sdf")))
        )
        self.assertTypesInCorrect(
            ([4, 5], Either(T(str), T(int))),
            ([], Either())
        )
        self.assertTypesCorrect(
            (3, T(int) | T(float) | T(str)),
            (3.0, Either(T(int), T(float), T(str))),
            ("sdf", Either(T(int), T(float), T(str))),
            ("sdf", Either(Exact("SDF"), Exact("sdf")))
        )
        self.assertTypesInCorrect(
            ([4, 5], Either(T(str), T(int))),
            ([], Either())
        )

    def test_all(self):
        self.assertTypesCorrect(
            ("asd", All(Any())),
            ("asd", All(Any(), T(str))),
            ("asd", All(Either(Exact("SDF"), Exact("asd")), T(str))),
            (4, All(Either(T(int), T(float)), T(int), Exact(4))),
            (3, All())
        )
        self.assertTypesInCorrect(
            (34, All(T(int), T(float))),
            ("as", All(T(str), T(list)))
        )
        self.assertTypesCorrect(
            ("asd", Any() | T(str)),
            ("asd", (Exact("SDF") | Exact("asd")) | T(str)),
            (4, T(int) | T(float) | T(int) | Exact(4)),
            (3, All())
        )
        self.assertTypesInCorrect(
            (34, T(int) & T(float)),
            ("as", T(str) & T(list))
        )

    def test_any(self):
        self.assertTypesCorrect(
            (3, Any()),
            (345, Any())
        )

    def test_optional(self):
        self.assertTypesCorrect(
            (None, Optional(T(int))),
            (00, Optional(T(int))),
            (0, Optional(Exact(0))),
            (None, Optional(Exact(0)))
        )
        self.assertTypesInCorrect(
            (0, Optional(Exact(1)))
        )

    def test_constraint(self):
        def biggerThanZero(x):
            return x > 0

        self.assertTypesCorrect(
            (4, Int(_ > 0 | _ != 0)),
            (4, Constraint(biggerThanZero)),
            (4.0, Constraint(biggerThanZero)),
            (4, Constraint(biggerThanZero, T(int))),
            (4, Either(Constraint(lambda x: len(x) == 0, T(list)), Constraint(biggerThanZero)))
        )
        self.assertTypesInCorrect(
            (-1, Constraint(biggerThanZero)),
            (1, Constraint(biggerThanZero, T(float))),
            (-1, Float(_ == -1))
        )

    def test_list(self):
        self.assertTypesCorrect(
            ([4, 5], List(T(int))),
            ([4.0, 5.0], Either(List(T(int)), List(T(float)))),
            ([4, 5], Either(List(T(int)), List(T(float)))),
            ([4, 5.0], List(Either(T(int), T(float)))),
            ([4, 5], List(Any())),
            ([4], List())
        )
        self.assertTypesInCorrect(
            ([4], List(T(str))),
            ([55, 4], List(Exact(55)))
        )

    def test_dict(self):
        self.assertTypesCorrect(
            ({
                "sdf": 4,
                "feature": "yes"
             }, Dict({
                "sdf": T(int),
                "feature": Either(Exact("yes"), Constraint(lambda x: x > 0, T(int)))
            })),
            ({
                "sdf": 4,
                "feature": 4
             }, Dict({
                "sdf": T(int),
                "feature": Either(Exact("yes"), Constraint(lambda x: x > 0, T(int)))
            })),
            ({
                "sdf": 4,
                "feature": 4
             }, Dict({
                "sdf": T(int),
                "feature": Either(Exact("yes"), Int(_ > 0))
            })),
            ({"sdf": 4}, Dict({"sdf": T(int)}))
        )
        self.assertTypesCorrect(
            ({}, Dict()),
            ({"sdf": 4}, Dict(all_keys=False)),
            ({"sdf": 4}, Dict(key_type=T(str), all_keys=False)),
            ({"sdf": 4}, Dict(key_type=T(str), value_type=Exact(4), all_keys=False)),
            ({"sdf": 4}, Dict(key_type=T(str), value_type=T(int), all_keys=False)),
            ({"sdf": 4}, Dict(key_type=T(str), value_type=Exact(4), all_keys=False))
        )
        self.assertTypesInCorrect(
            ({
                "sdf": 4,
                "feature": -1
             }, Dict({
                "sdf": T(int),
                "feature": Either(Exact("yes"), Constraint(lambda x: x > 0, T(int)))
            }))
        )

    def test_nonexistent(self):
        print(T(str) | (T(str)))
        t = Dict({"asdf": Either(
                 NonExistent(),
                 Dict({"ads":  Either(NonExistent(), Int(_ != 4)) })
             )})
        self.assertTypesCorrect(
            ({"asdf": {}}, t),
            ({}, t),
            ({"asdf": {"ads": 3}}, t),
            ({"asdf": 4}, Dict({"asdf": Either(NonExistent(), Int(_ > 3))})),
            ({}, Dict({"ads": Either(NonExistent(), Int(_ > 3))})),
            ({}, Dict({"ads": NonExistent()})),
            ({"ads": 3}, Dict({"ads": Either(NonExistent(), Any())}))
        )
        t = Dict({"asdf": NonExistent() | Dict({"ads":  NonExistent() | Int(_ != 4) })})
        self.assertTypesCorrect(
            ({"asdf": {}}, t),
            ({}, t),
            ({"asdf": {"ads": 3}}, t)
        )