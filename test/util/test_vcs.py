import temci.utils.vcs as vcs
import unittest, os, tempfile, shutil, subprocess, shlex
import temci.utils.settings
from temci.utils.settings import Settings

# todo syntax of self.assertEqual


def path(name):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), name))


def setup():
    try:
        os.rename(path("test_vcs/git"), path("test_vcs/.git"))
        os.rename(path("test_vcs2/git"), path("test_vcs2/.git"))
    except IOError:
        pass


def tearDown():
    os.rename(path("test_vcs/.git"), path("test_vcs/git"))
    os.rename(path("test_vcs2/.git"), path("test_vcs2/git"))


class TestVCSDriver(unittest.TestCase):

    @classmethod
    def setUpClass(cls=None):
        setup()

    @classmethod
    def tearDownClass(cls=None):
        tearDown()

    def test_get_suited_vcs(self):
        def test_dir(mode, dir, expected_cls=None, expect_error=False):
            if expect_error:
                with self.assertRaises(vcs.VCSError):
                    vcs.VCSDriver.get_suited_vcs(mode, dir)
            else:
                self.assertEqual(type(vcs.VCSDriver.get_suited_vcs(mode, dir)), expected_cls)
        test_dir("auto", path("."), vcs.FileDriver)
        test_dir("auto", path("test_vcs"), vcs.GitDriver)
        test_dir("file", path("."), vcs.FileDriver)
        test_dir("git", path("test_vcs"), vcs.GitDriver)
        test_dir("auto", path("sdf"), expect_error=True)
        test_dir("file", path("sdf"), expect_error=True)
        test_dir("git", path("sdf"), expect_error=True)
        test_dir("git", path("."), expect_error=True)

class TestFileDriver(unittest.TestCase):

    @classmethod
    def setUpClass(cls=None):
        setup()

    @classmethod
    def tearDownClass(cls=None):
        tearDown()

    def test_small_methods(self):
        self.assertTrue(vcs.FileDriver.is_suited_for_dir(path(".")))
        self.assertFalse(vcs.FileDriver.is_suited_for_dir(path("non existent")))
        self.assertFalse(vcs.FileDriver.is_suited_for_dir(__file__))
        driver = vcs.FileDriver(path("test_vcs"))
        with self.assertRaises(vcs.VCSError):
            driver.set_branch("sdfsdf")
        driver.set_branch(None)
        self.assertEqual(driver.number_of_revisions(), 0)
        self.assertTrue(driver.has_uncommitted())
        self.assertEqual(driver.get_info_for_revision(-1), {
            "commit_id": "",
            "commit_message": "",
            "commit_number": -1,
            "is_uncommitted": True,
            "is_from_other_branch": False,
            "branch": ""
        })
        with self.assertRaises(vcs.VCSError):
            driver.get_info_for_revision(10)
        with self.assertRaises(vcs.VCSError):
            driver.get_info_for_revision("")
        self.assertFalse(driver.validate_revision(10))
        self.assertTrue(driver.validate_revision(-1))

    def test_copy_revision(self):
        driver = vcs.FileDriver(path("test_vcs"))
        dir = tempfile.mkdtemp()
        driver.copy_revision(-1, ".", dir)
        for sub in ["new_dir", "abcd", "new_dir/abc"]:
            self.assertTrue(os.path.exists(os.path.join(dir, sub)))
        shutil.rmtree(dir)
        dir = tempfile.mkdtemp()
        driver.copy_revision(-1, "new_dir", dir)
        for sub in ["a", "abc"]:
            self.assertTrue(os.path.exists(os.path.join(dir, sub)))
        shutil.rmtree(dir)

class TestGitDriver(unittest.TestCase):

    @classmethod
    def setUpClass(cls=None):
        setup()

    @classmethod
    def tearDownClass(cls=None):
        tearDown()

    def setUp(self):
        Settings().reset()

    def tearDown(self):
        Settings().reset()

    def test_is_suited_for_dir(self):
        self.assertFalse(vcs.GitDriver.is_suited_for_dir(path(".")))
        self.assertFalse(vcs.GitDriver.is_suited_for_dir(path("test_vcs/new_dir")))
        self.assertFalse(vcs.GitDriver.is_suited_for_dir(path("test.yaml")))
        self.assertTrue(vcs.GitDriver.is_suited_for_dir(path("test_vcs")))

    def test_get_and_set_branch(self):
        driver = vcs.GitDriver(path("test_vcs"))
        self.assertEqual(driver.get_branch(), "master")
        with self.assertRaises(vcs.VCSError):
            driver.set_branch("new_master")
        self.assertEqual(driver.get_branch(), "master")
        driver.set_branch("new_branch")
        self.assertEqual(driver.get_branch(), "new_branch")

    def test_has_uncommitted(self):
        driver = vcs.GitDriver(path("test_vcs2"))
        self.assertTrue(driver.has_uncommitted())
        driver = vcs.GitDriver(path("test_vcs"))
        self.assertFalse(driver.has_uncommitted())

    def test_number_of_revisions(self):
        driver = vcs.GitDriver(path("test_vcs"))
        driver.set_branch("master")
        self.assertEqual(driver.number_of_revisions(), 4)
        driver.set_branch("new_branch")
        self.assertEqual(driver.number_of_revisions(), 6)

    def test_validate_revision(self):
        driver = vcs.GitDriver(path("test_vcs"))
        driver.set_branch("master")
        def invalid(id_or_num):
            self.assertFalse(driver.validate_revision(id_or_num))
        def valid(id_or_num):
            self.assertTrue(driver.validate_revision(id_or_num))

    def test_normalize_commit_id(self):
        driver = vcs.GitDriver(path("test_vcs"))
        def valid(id, expected_value):
            self.assertEqual(driver._normalize_commit_id(id), expected_value)

        def invalid(id):
            with self.assertRaises(vcs.VCSError):
                driver._normalize_commit_id(id)

        invalid("34")
        valid("90b09", "90b09c2339bfd962a93b68523f1958351db8256b")

    def test_get_info_for_revision(self):
        driver = vcs.GitDriver(path("test_vcs"))
        driver.set_branch("master")
        def get(id_or_name):
            return driver.get_info_for_revision(id_or_name)

        def valid(id_or_name, expected_value):
            self.assertEqual(get(id_or_name), expected_value)

        def invalid(id_or_name):
            with self.assertRaises(vcs.VCSError):
                get(id_or_name)
        invalid(-2)
        invalid("2dd")
        invalid("4b")
        invalid(4)
        valid(-1, {
                "commit_id": "",
                "commit_message": "[Uncommited]",
                "commit_number": -1,
                "is_uncommitted": True,
                "is_from_other_branch": False,
                "branch": "master"
            })
        valid(0, {
                "commit_id": "90b09c2339bfd962a93b68523f1958351db8256b",
                "commit_message": "sdf",
                "commit_number": 0,
                "is_uncommitted": False,
                "is_from_other_branch": False,
                "branch": "master"
            })

    def test_copy_revision(self):
        driver = vcs.GitDriver(path("test_vcs"))
        dir = tempfile.mkdtemp()
        driver.copy_revision(-1, ".", dir)
        for sub in ["new_dir", "abcd", "new_dir/abc"]:
            self.assertTrue(os.path.exists(os.path.join(dir, sub)))
        shutil.rmtree(dir)
        dir = tempfile.mkdtemp()
        driver.copy_revision(-1, "new_dir", dir)
        for sub in ["a", "abc"]:
            self.assertTrue(os.path.exists(os.path.join(dir, sub)))
        shutil.rmtree(dir)
        dir = tempfile.mkdtemp()
        driver.copy_revision(3, ".", dir)
        for sub in ["abcd"]:
            self.assertTrue(os.path.exists(os.path.join(dir, sub)), "sub directory {} doesn't exist".format(sub))
        self.assertFalse(os.path.exists(os.path.join(dir, "new_dir")), "sub directory new_dir does exist")
        shutil.rmtree(dir)