from temci.utils.settings import Settings
from temci.utils.vcs import VCSDriver, VCSError
from temci.utils.typecheck import *
from .models import MainModel, RevisionModel, BuildCmdModel, RunCmdModel
import temci.model.parser as parser
import logging, itertools
from fn import _
from collections import OrderedDict

class IncompleteInformation(ValueError):
    pass


class ModelBuilder(object):
    """
    Builds up a main model and modifies it.
    """

    def __init__(self, main_model: MainModel):
        """
        Creates a builder that modifies the passed main model.
        :param passed MainModel
        """
        self.main_model = main_model

    def parse_revision_list(self, text: str, vcs: VCSDriver):
        """
        Parse the passed revision list string and use the passed vcs driver to add the therein declared revisions
        to the main model.
        :param text: revision list string
        :param vcs: vcs driver
        :raises parsimonious.exceptions.ParseError if a parse error occurs
        :raises temci.vcs.VCSError if one of the revisions doesn't exist
        """
        list = parser.parse_revision_list(text)
        for item in list:
            if type(item) in [parser.BranchList, parser.IntRange, parser.IntRangeOpenEnd, parser.IntRangeOpenStart]:
                start = -1 if vcs.has_uncommitted() else 0
                end = vcs.number_of_revisions() - 1
                if isinstance(item, parser.IntRange):
                    start = item.start
                    end = item.end
                elif isinstance(item, parser.IntRangeOpenEnd):
                    start = item.start
                elif isinstance(item, parser.IntRangeOpenStart):
                    end = item.end

                for i in range(start, end + 1):
                    self.add_revision(vcs, i)
            elif isinstance(item, parser.ListRangeList):
                for list_item in item.raw_list:
                    self.add_revision(vcs, list_item)

    def add_revision(self, vcs: VCSDriver, num_or_id):
        """
        Adds the revision with the given number or id to the main model.
        :param vcs: used vcs driver
        :param num_or_id: used number or string id
        :raises temci.vcs.VCSError if the number or id isn't valid
        """
        info = vcs.get_info_for_revision(num_or_id)
        data = {
            "info": info,
            "build_cmds": []
        }
        self.main_model.revisions.append(RevisionModel.load_from_dict(data))

    def add_uncommitted_revision(self, vcs: VCSDriver):
        """
        Adds the uncommitted changes revision to the main model if this revision exists.
        :param vcs: used vcs driver
        """
        if vcs.has_uncommitted():
            self.add_revision(vcs, -1)

    def parse_build_cmd_list(self, build_cmd_list: str, build_dir_list: str, binary_dir_list: str, binary_numer: int):
        """
        Parses the given build command list string (that gives an array of build commands per revision range) and
        add BuildCmdModels accordingly to the main models RevisionModels.
        To create the models it needs to parse the passed path list string that specify the build and the binary path
        for each (revision, build command) tuple. The last given paths for each tuple are taken.
        If a revision, named in one of the list items, doesn't exist, a warning is given and the revision is ignored.
        That's also the case if a (revision, build command) tuple named in the path lists doesn't exist.
        :param build_cmd_list: build command list string
        :param build_dir_list: path list for the build directories
        :param binary_dir_list: path list for the binary directories
        :param binary_number: value of the binary number property of all BinaryCmdModels
        :raises IncompleteInformation if one of the tuples has no build and binary directories
        """
        build_list = parser.parse_build_cmd_list(build_cmd_list)
        rev_dict = {} # {revision: {"build_cmd": {"build_dir": …, "binary_dir": …}, …}, …}
        rev_dict_type = Dict(all_keys=False, key_type=T(RevisionModel),
                             value_type=Dict(all_keys=False, key_type=T(str),
                                             value_type=Dict({
                                                 "cmd": Str(),
                                                 "build_dir": Str(),
                                                 "binary_dir": Str(),
                                                 "binary_number": Int(_ >= 0)
                                             })))
        rev_cmds_ordered = {}
        for (rlist, item) in build_list:
            revisions = self._get_revisions(rlist)
            for (rev, cmd) in itertools.product(revisions, item.raw_list):
                if rev not in rev_dict:
                    rev_dict[rev] = {}
                    rev_cmds_ordered[rev] = []
                if cmd not in rev_cmds_ordered[rev]:
                    rev_cmds_ordered[rev].append(cmd)
                rev_dict[rev][cmd] = {
                    "cmd": cmd,
                    "build_dir": None,
                    "binary_dir": None,
                    "binary_number": binary_numer
                }

        def parse_path_list(path_list: str, rev_dict_key: str):
            path_list = parser.parse_path_list(path_list)
            for (rlist, blist, path) in path_list:
                revisions = self._get_revisions(rlist)
                if type(blist) is parser.InfRange:
                    for rev in revisions:
                        if rev in rev_dict:
                            for cmd in rev_dict[rev]:
                                rev_dict[rev][cmd][rev_dict_key] = path
                else:
                    for (rev, cmd) in itertools.product(revisions, blist.raw_list):
                        if rev in rev_dict:
                            if cmd not in rev_dict[rev]:
                                logging.warning("No such (revision, build command) tuple "
                                                "({}, {}) to set the {} path for".format(rev, cmd, rev_dict_key))
                            else:
                                rev_dict[rev][cmd][rev_dict_key] = path
        parse_path_list(build_dir_list, "build_dir")
        parse_path_list(binary_dir_list, "binary_dir")
        res = verbose_isinstance(rev_dict, rev_dict_type,
                                 value_name="mapping of (revision, build command) tuples to paths")
        if not res:
            raise IncompleteInformation(res)
        for revision in rev_dict:
            revision.build_cmds = [BuildCmdModel.load_from_dict(rev_dict[revision][cmd])
                                    for cmd in rev_cmds_ordered[revision]]

    def parse_run_cmd_list(self, run_cmd_list: str):
        """
        Parses the passed run command list (representing a list of (revision, build command, run command) tuples.
        Ignores (revision, build command) that don't exist and gives a warning.
        :param run_cmd_list: passed run command list
        """
        for (rlist, blist, run_list) in parser.parse_run_cmd_list(run_cmd_list):
            assert isinstance(run_list, parser.ListRangeList)
            assert isinstance(run_list.raw_list, List(Str()))
            for rev in self._get_revisions(rlist):
                for build_cmd in self._get_build_cmds(rev, blist):
                    for cmd in run_list.raw_list:
                        build_cmd.run_cmds.append(RunCmdModel.load_from_dict({"cmd": cmd}))

    def get_main_model_subset(self, report_tuple_list:str) -> MainModel:
        """
        Parses the passed report tuple list and returns a main model that is a subset of the actual main model and
        consists of the models that match the report tuple list.
        :param revision_tuple_list: string representing a list of (revision, build command, run command) tuples
        :return: main model subset
        """
        model = MainModel(self.main_model.working_dir)
        for (rlist, blist, run_list) in parser.parse_report_tuple_list(report_tuple_list):
            for rev in self._get_build_cmds(rlist):
                revision = RevisionModel.load_from_dict(rev.to_dict())
                revision.build_cmds.clear()
                model.revisions.append(revision)
                for build_cmd in self._get_build_cmds(rev, blist):
                    build_command = BuildCmdModel.load_from_dict(build_cmd.to_dict())
                    revision.build_cmds.append(build_command)
                    build_command.run_cmds.clear()
                    for run_cmd in self._get_build_cmds(rev, build_cmd, run_list):
                        build_command.run_cmds.append(RunCmdModel.load_from_dict(run_cmd.to_dict()))
        return model

    def _get_run_cmds(self, build: BuildCmdModel, run_cmd_list: parser.RangeList) -> list:
        """
        Returns the list of RunCmdModels that belong to passed build model and are in the passed list too.
        It gives a warning if an list item doesn't exist in the main model, and then ignores it.
        :param rev: passed revision model
        :param blist: passed list
        :return: list of matching RunCmdModels
        """
        if isinstance(run_cmd_list, parser.InfRange):
            return build.run_cmds
        else:
            assert isinstance(run_cmd_list, parser.ListRangeList)
            av_cmds = [run_cmd.cmd for run_cmd in build.run_cmds]
            used, not_used = (run_cmd_list.filter(av_cmds), run_cmd_list.additional(av_cmds))
            if len(not_used) > 0:
                logging.warning("Unused (build command, run command) "
                                "tuples ({}, {})".format(repr(build), not_used))
            return [build.run_cmds[av_cmds.index(cmd)] for cmd in used]

    def _get_build_cmds(self, rev: RevisionModel, blist: parser.RangeList) -> list:
        """
        Returns the list of BuildCmdModels that belong to the passed revision and are also in
        the passed list.
        It gives a warning if an list item doesn't exist in the main model, and then ignores it.
        :param rev: passed revision model
        :param blist: passed list
        :return: list of matching BuildCmdModels
        """
        if isinstance(blist, parser.InfRange):
            return rev.build_cmds
        else:
            assert isinstance(blist, parser.ListRangeList)
            av_cmds = [build_cmd.cmd for build_cmd in rev.build_cmds]
            used, not_used = (blist.filter(av_cmds), blist.additional(av_cmds))
            if len(not_used) > 0:
                logging.warning("Unused (revision, build command) tuples ({}, {})".format(repr(rev), not_used))
            return [rev.build_cmds[av_cmds.index(cmd)] for cmd in used]


    def _get_revisions(self, rlist: parser.RangeList) -> list:
        """
        Returns a list of revisions of the main model that are in the passed range list.
        If a revision, named explicitly in the range list, doesn't exist, a warning is given
        and the revision is ignored.
        :param rlist: range list
        :return: list of matching RevisionModels
        """
        if isinstance(rlist, parser.BranchList):
            return [rev for rev in self.main_model.revisions if not rev.is_from_other_branch]
        if isinstance(rlist, parser.InfRange):
            return self.main_model.revisions
        ids = [rev.id for rev in self.main_model.revisions]
        numbers = [rev.commit_number for rev in self.main_model.revisions]
        not_used = []
        used = []
        if type(rlist) is parser.ListRangeList:
            for id_or_num in rlist.raw_list:
                arr = ids if isinstance(id_or_num, str) else numbers
                if id_or_num in arr:
                    used.append(self.main_model.revisions[arr.index(id_or_num)])
                else:
                    not_used.append(id_or_num)
        else:
            used = rlist.filter(numbers)
            not_used = rlist.additional(numbers)
            used = [self.main_model.revisions[numbers.index(num)] for num in used]
        if len(not_used) > 0:
            logging.warning("Unused revisions: {}".format(not_used))
        return used