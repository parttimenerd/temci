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


class TestModelBuilder(unittest.TestCase):

    commit_msg_master_list = ["sdf", "changed abcd again", "changed abcd", "with abcd"]

    @classmethod
    def setUpClass(cls):
        setup()

    @classmethod
    def tearDownClass(cls):
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

    def test_parse_build_cmd_list(self):
        def correct(rev_list: str, cmd_list: str, build_dir_list: str, binary_dir_list: str,
                    expected_commit_id_cmd_dict: dict):
            self.model.clear()
            self.builder.parse_revision_list(rev_list, self.vcs)
            self.builder.parse_build_cmd_list(cmd_list, build_dir_list, binary_dir_list, 0)
            id_cmd_dict = {}
            for rev in self.model.revisions:
                id_cmd_dict[rev.id[0:3]] = [(build.cmd, build.build_dir, build.binary_dir) for build in rev.build_cmds]
            self.assertDictEqual(id_cmd_dict, expected_commit_id_cmd_dict)
        expected = {
            "90b": [('a', 'p', 's'), ('b', 'p', 's')],
            "fde": [('a', 'p', 's'), ('b', 'p', 's')]
        }
        correct("[0..0]; [3..3]", "[branch]:['a', 'b']", "[..]:'p'", "[..]:'s'", expected)
        correct("[0,3]", "[branch]:['a', 'b']", "[..]:'p'", "[..]:'s'", expected)
        correct("[3..]; [..0]", "[3..]:['a', 'b']; [..0]:['a', 'b']", "[..]:'p'", "[..]:'s'", expected)
        correct("[3..]; [..0]", "[branch]:['a', 'b']", "[..]:'p'", "[..]:'s'", expected)
        correct("[0,3]", "[..]:['a', 'b']", "[0,3]:[..]:'p'", "[0,3]:[..]:'s'", expected)
        correct("[0,3]", "[0,3]:['a', 'b']", "[0,3]:[..]:'p'", "[0,3]:[..]:'s'", expected)
        correct("[0,3]", "[0,3]:['a', 'b']", "[0,3]:[..]:'s'; [0,3]:[..]:'p'",
                "[0,3]:[..]:'p'; [0,3]:[..]:'s'", expected)
        correct("[0,3]", "[0,3]:['a', 'b']", "[0,3]:['a', 'b']:'s'; [0,3]:[..]:'p'",
                "[0,3]:[..]:'p'; [0,3]:[..]:'s'", expected)
        correct("[0,3]", "[0,3]:['a', 'b']", "[0,3]:[..]:'p'", "[..]:[..]:'s'", expected)
        with self.assertLogs(level='WARN') as cm:
            correct("[0,3]", "[0,2,3]:['a', 'b']", "[0,3]:[..]:'p'", "[..]:[..]:'s'", expected)
        self.assertEqual(len(cm.output), 1)

    def test_parse_run_cmd_list(self):
        cmds = ["[0, 3]", "[branch]:['a', 'b']", "[..]:'p'", "[..]:'s'"]
        def correct(run_cmd_list: str, expected_commit_id_cmd_dict: dict):
            rev_list, cmd_list, build_dir_list, binary_dir_list = cmds
            self.model.clear()
            self.builder.parse_revision_list(rev_list, self.vcs)
            self.builder.parse_build_cmd_list(cmd_list, build_dir_list, binary_dir_list, 0)
            self.builder.parse_run_cmd_list(run_cmd_list)
            id_cmd_dict = {}
            for rev in self.model.revisions:
                id_cmd_dict[rev.id[0:3]] = [(build.cmd, build.build_dir, build.binary_dir,
                                             [run_cmd.cmd for run_cmd in build.run_cmds]) for build in rev.build_cmds]
            self.assertDictEqual(id_cmd_dict, expected_commit_id_cmd_dict)

        correct("[..]:['r']", {
            "90b": [('a', 'p', 's', ['r']), ('b', 'p', 's', ['r'])],
            "fde": [('a', 'p', 's', ['r']), ('b', 'p', 's', ['r'])]
        })
        with self.assertLogs(level='WARN') as cm:
            cmds[0] = "[0, 3]"
            correct("[0]:['a', 'b', 'c']:['r']", {
                "90b": [('a', 'p', 's', ['r']), ('b', 'p', 's', ['r'])],
                "fde": [('a', 'p', 's', []), ('b', 'p', 's', [])]
            })
            cmds[0] = "[0]"
        self.assertEqual(len(cm.output), 1)

    def test_get_main_model_subset(self):
        pass