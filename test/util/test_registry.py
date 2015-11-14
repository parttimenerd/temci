from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.utils.registry import AbstractRegistry, register
import unittest

class TestRegistry(unittest.TestCase):

    def test_small_methods(self):
        Settings().modify_setting("abcd", Dict(all_keys=False), {})

        class MockRegistry(AbstractRegistry):

            def __init__(self):
                super().__init__(["abcd"], "test", True, ["plugin"])

        with self.assertRaises(ValueError):
            MockRegistry().get_for_name("asd")

        @register(MockRegistry, "plugin", Dict(), {})
        class Plugin:
            def __init__(self, a):
                self.a = a

        @register(MockRegistry, "plugin2", Dict(), {})
        class Plugin2:
            def __init__(self, a):
                self.a = a

        self.assertListEqual(MockRegistry().get_used(), ["plugin"])
        Settings()["abcd/test"] = ["plugin2", "plugin"]
        self.assertListEqual(MockRegistry().get_used(), ["plugin2", "plugin"])

        Settings().modify_setting("abc", Dict(all_keys=False), {})

        class MockRegistryNoList(AbstractRegistry):

            def __init__(self):
                super().__init__(["abc"], "test", False, "plugin")

        with self.assertRaises(ValueError):
            MockRegistryNoList().get_for_name("asd")

        @register(MockRegistryNoList, "plugin", Dict(), {})
        class Plugin:
            def __init__(self, a):
                self.a = a

        @register(MockRegistryNoList, "plugin2", Dict(), {})
        class Plugin2:
            def __init__(self, a):
                self.a = a

        self.assertEqual(MockRegistryNoList().get_used(), "plugin")
        Settings()["abc/test"] = "plugin2"
        self.assertEqual(MockRegistryNoList().get_used(), "plugin2")