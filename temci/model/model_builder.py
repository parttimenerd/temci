from temci.utils.settings import Settings
from temci.utils.vcs import VCSDriver, VCSError
from .models import MainModel, RevisionModel
import temci.model.parser as parser
import os

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
        self.main_model.revisions.append(RevisionModel(info))

    def add_uncommitted_revision(self, vcs: VCSDriver):
        """
        Adds the uncommitted changes revision to the main model if this revision exists.
        :param vcs: used vcs driver
        """
        if vcs.has_uncommitted():
            self.add_revision(vcs, -1)