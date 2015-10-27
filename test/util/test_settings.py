from temci.utils.settings import Settings, SettingsError
import unittest, os

class TestSettings(unittest.TestCase):

    def test_get(self):
        set = Settings()
        self.assertEqual(set.get("tmp_dir", "/tmp/temci2"), "/tmp/temci")
        self.assertEqual(set.get("env/nice", "10"), "10")
        self.assertEqual(set.get("non existent", "default"), "default")
        with self.assertRaises(SettingsError):
            set.get("non existent")
        set.reset()

    def test_set_and_get(self):
        set = Settings()
        set.set_program("env")
        set.set("tmp_dir", "blub")
        self.assertEqual(set.get("tmp_dir"), "blub")
        with self.assertRaises(SettingsError):
            set.set("non existent", "bla")
        set.set("randomize_binary", True)
        self.assertEqual(set.get("randomize_binary/enable"), True)
        set.set("randomize_binary", False)
        self.assertEqual(set.get("randomize_binary/enable"), False)
        set.reset()

    def test_load_file(self):
        set = Settings()
        set.set_program("env")
        set.load_file(os.path.join(os.path.dirname(__file__), "test.yaml"))
        self.assertEqual(set.get("tmp_dir"), "/tmp/abc")
        self.assertEqual(set.get("nice"), 1000)
        set.reset()