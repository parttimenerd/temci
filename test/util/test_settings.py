from temci.utils.settings import Settings, SettingsError
import unittest, os, shutil
from temci.utils.typecheck import *

class TestSettings(unittest.TestCase):

    def tearDown(self):
        Settings().reset()

    def test_get(self):
        set = Settings()
        self.assertEqual(set.get("tmp_dir"), "/tmp/temci")
        self.assertEqual(set.get("env/nice"), 10)
        with self.assertRaises(SettingsError):
            set.get("non existent")

    def test_set_and_get(self):
        set = Settings()
        set.set("tmp_dir", "blub")
        self.assertEqual(set.get("tmp_dir"), "blub")
        with self.assertRaises(SettingsError):
            set.set("non existent", "bla")
        with self.assertRaises(SettingsError):
            set.set("tmp_dir", 4)
        with self.assertRaises(SettingsError):
            set.set("nice", 100)
        set.set("env/randomize_binary", True)
        self.assertEqual(set.get("env/randomize_binary/enable"), True)
        set.set("env/randomize_binary", False)
        self.assertEqual(set.get("env/randomize_binary/enable"), False)
        shutil.rmtree("blub", ignore_errors=True)

    def test_load_file(self):
        set = Settings()
        set.load_file(os.path.join(os.path.dirname(__file__), "test.yaml"))
        self.assertEqual(set.get("tmp_dir"), "/tmp/abc")
        self.assertEqual(set.get("env/nice"), 5)

    def test_modify(self):
        Settings().modify_setting("abcd", type_scheme=Dict(), default_value={})
        self.assertEqual(Settings()["abcd"], {})
        self.assertEqual(Settings().get_default_value("abcd"), {})
        self.assertEqual(Settings().get_type_scheme("abcd"), Dict())