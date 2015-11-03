import temci.utils.vcs as vcs
import unittest, os, tempfile, shutil, subprocess, shlex
from temci.utils.settings import Settings
from temci.model.models import MainModel, RevisionModel
from temci.model.model_builder import ModelBuilder

"""
Information about the used git repository (test_vcs folder):

branches:
  list
* master
  new_branch

commits in branch master (default):
90b09c2 sdf
2bf3fe6 changed abcd again
ecc4b55 changed abcd
fde5e8c with abcd

commits in branch new_branch:
910535b sa
7763cea modified new_dir/file again
5b6a57a modified new_dir/file
2bf3fe6 changed abcd again
ecc4b55 changed abcd
fde5e8c with abcd
"""

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


class TestGitDriver(unittest.TestCase):

    commit_msg_master_list = ["sdf", "changed abcd again", "changed abcd", "with abcd"]

    @classmethod
    def setUpClass(cls=None):
        setup()

    @classmethod
    def tearDownClass(cls=None):
        tearDown()

    def setUp(self):
        self.model = MainModel(Settings().get("tmp_dir"))
        self.builder = ModelBuilder(self.model)
        self.vcs = vcs.GitDriver(path("test_vcs"))

    def test_parse_revision_list(self):
        def correct(rev_list: str, expected_msgs: list):
            self.model.clear()
            self.builder.parse_revision_list(rev_list, self.vcs)
            list = [rev.message.strip() for rev in self.model.revisions]
            self.assertListEqual(list, expected_msgs)

        correct("[branch]", self.commit_msg_master_list)
        correct("[0..2]", self.commit_msg_master_list[0:3])
        correct("[..2]", self.commit_msg_master_list[0:3])
        correct("[1..]", self.commit_msg_master_list[1:])
        correct("[1..]; [1..]; [1..]", self.commit_msg_master_list[1:] * 3)
        correct("[0, 3, 3]", [self.commit_msg_master_list[0]] + [self.commit_msg_master_list[3]] * 2)
        correct("['90b09c2', 'fde5e8c', 'fde5e8c']",
                [self.commit_msg_master_list[0]] + [self.commit_msg_master_list[3]] * 2)

    def test_add_revision(self):
        self.builder.add_revision(self.vcs, "ecc4b55")
        self.builder.add_revision(self.vcs, 0)
        list = [rev.message.strip() for rev in self.model.revisions]
        self.assertListEqual(list, [self.commit_msg_master_list[2], self.commit_msg_master_list[0]])

    """
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
"""