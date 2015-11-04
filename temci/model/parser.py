"""
Parser for the range expressions, that produces lists (of lists) of RangeList objects.

The syntax of range expressions are defined in the grammar that is some where below.

https://github.com/erikrose/parsimonious
https://github.com/erikrose/parsimonious/blob/master/parsimonious/grammar.py
"""

from parsimonious.grammar import Grammar, NodeVisitor
import parsimonious
from temci.utils.typecheck import Str, NonErrorConstraint

class RangeList(object):
    """
    The basic abstract range.
    """

    def filter(self, av_list: set) -> list:
        """
        Returns a list of the item of the list of available items that are present in this range.
        :param av_list: list of available items
        """
        return av_list

    def additional(self, av_list: set) -> list:
        """
        Returns the own items that are not present in the list of available items.
        :param av_list: list of available items
        """
        return []

    def __str__(self):
        raise NotImplementedError()

    def __repr__(self):
        raise NotImplementedError()


class BranchList(RangeList):
    """
    Represents all revisions in the current branch.
    Note: Doesn't implement the filter and additional method properly.
    """

    def __str__(self):
        return "[branch]"

    def __repr__(self):
        return '"[branch]"'


class InfRange(RangeList):
    """
    A range that contains every element.
    """

    def __str__(self):
        return "[..]"

    def __repr__(self):
        return "\"" + self.__str__() + "\""

class IntRange(RangeList):
    """
    A range of integers with start an end. That includes every item in between it's borders (and the border values)
    """

    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end

    def filter(self, av_list: set) -> list:
        return [x for x in av_list if self.start <= x <= self.end]

    def additional(self, av_list: set) -> list:
        return [x for x in range(self.start, self.end + 1) if x not in av_list]

    def __str__(self):
        return "[{}..{}]".format(self.start, self.end)


class IntRangeOpenEnd(RangeList):
    """
    A range of integers that includes every item that is >= its start value.
    """

    def __init__(self, start: int):
        self.start = start

    def filter(self, av_list: set) -> list:
        return [x for x in av_list if self.start <= x]

    def additional(self, av_list: set) -> list:
        return [x for x in list(range(self.start, min(*av_list))) if x not in av_list]

    def __str__(self):
        return "[{}..]".format(self.start)


class IntRangeOpenStart(RangeList):
    """
    A range of integers that includes every item that is >= its end value.
    """

    def __init__(self, end: int):
        self.end = end

    def filter(self, av_list: set) -> list:
        return [x for x in av_list if self.end >= x]

    def additional(self, av_list: set) -> list:
        return [x for x in list(range(max(*av_list), self.end)) if x not in av_list]

    def __str__(self):
        return "[..{}]".format(self.end)


class ListRangeList(RangeList):
    """
    A list that includes only items that really present in its raw list.
    And also all string elements that have unambiguous prefix in its raw list
    """

    def __init__(self, raw_list: set):
        if isinstance(raw_list, str) or isinstance(raw_list, int):
            self.raw_list = [raw_list]
        else:
            self.raw_list = raw_list

    def _has_prefix(self, new_element, elements: set):
        if not isinstance(new_element, str):
            return False
        raws = [x for x in self.raw_list if isinstance(x, str) and new_element.startswith(x)]
        return [elem for elem in elements if isinstance(elem, str)
                    and len([x for x in raws if elem.startsWith(x)]) > 0] == 1

    def filter(self, av_list: set) -> list:
        return [x for x in av_list if x in self.raw_list or self._has_prefix(x, av_list)]

    def additional(self, av_list: set) -> list:
        return [x for x in self.raw_list if x not in av_list]

    def __str__(self):
        return "[{}]".format(", ".join((("'" + x + "'") if isinstance(x, str) else str(x)) for x in self.raw_list))


grammar = Grammar(
    """
    # for testing purposes
    run = token+

    revision_list = revision_list_item / revision_list_token_wo_inf
    revision_list_item = ws* revision_list_token_wo_inf ws* ";" ws* revision_list ws*

    build_cmd_list = build_cmd_list_item / bc_token
    build_cmd_list_item = ws* bc_token ws* ";" ws* build_cmd_list ws*
    bc_token = ws* revision_list_token ws* ":" ws* str_list ws*

    path_list = path_list_item / path_list_token
    path_list_item = ws* path_list_token ws* ";" ws* path_list ws*
    path_list_token = path_list_long_token / path_list_short_token
    path_list_long_token = bc_w_inf_token ":" string
    path_list_short_token = inf_range ":" string
    bc_w_inf_token = ws* revision_list_token ws* ":" ws* str_list_or_inf_range ws*

    run_cmd_list = run_cmd_list_item / run_cmd_list_token
    run_cmd_list_item = ws* run_cmd_list_token ws* ";" ws* run_cmd_list ws*
    run_cmd_list_token = run_cmd_list_long_token / run_cmd_list_short_token
    run_cmd_list_long_token = bc_w_inf_token ":" str_list
    run_cmd_list_short_token = inf_range ":" str_list

    # used for the "revisions" parameter of "temci report"
    report_tuple_list = report_tuple_list_item / report_tuple_list_token
    report_tuple_list_item = ws* report_tuple_list_token ws* ";" ws* report_tuple_list ws*
    report_tuple_list_token = report_tuple_list_long_token / report_tuple_list_short_token / report_list_inf_token
    report_tuple_list_long_token = rt_bc_token ":" rt_token
    report_tuple_list_short_token = inf_range ":" rt_token
    report_list_inf_token = ws* inf_range ws*
    rt_token = str_list / inf_range
    rt_bc_token = ws* revision_list_token ws* ":" ws* rt_token ws*

    #basic grammar below

    token = inf_range / number_range_open_start / number_range_open_end / list / number_range
    revision_list_token = token / branch
    revision_list_token_wo_inf = number_range_open_start / number_range_open_end / list / number_range / branch

    inf_range = ws* "[..]" ws*
    number_range = ws* "[" ws* number ".." number ws* "]" ws*
    number_range_open_start = ws* "[" ws* ".." number ws* "]" ws*
    number_range_open_end = ws* "[" ws* number ".." ws* "]" ws*
    list = ws* "[" ws* list_item ws* "]" ws*
    list_item =  list_item2 / atom
    list_item2 = atom "," list_item
    str_list = ws* "[" ws* str_list_item ws* "]" ws*
    str_list_item =  str_list_item2 / string
    str_list_item2 = string "," str_list_item
    str_list_or_inf_range = inf_range / str_list

    atom = string / number
    number = ws* ~r"-[0-9]+|[0-9]+" ws*
    string = ws* ~r"'(\\\\'|(?!').)*'" ws*
    branch = ws* "[branch]" ws*

    # all ignored stuff (like whitespace or comments)
    ws = ~r"\ *(//([^;]*)*)*"
    """
)

class Visitor(NodeVisitor):
    """
    Visitor for the basic grammar parts.
    """

    @staticmethod
    def _filter_str_and_num(children: list) -> list:
        arr = []
        for x in children:
            while isinstance(x, list) and len(x) > 0:
                x = x[0]
            if type(x) in [int, str]:
                arr.append(x)
        return arr

    @staticmethod
    def filter_non_empty(children: list) -> list:
        return [x for x in children if type(x) is not list or len(x) != 0]

    def visit_inf_range(self, _1, _2):
        return InfRange()

    def visit_number_range(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRange(numbers[0], numbers[1])

    def visit_number_range_open_start(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRangeOpenStart(numbers[0])

    def visit_number_range_open_end(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRangeOpenEnd(numbers[0])

    def visit_branch(self, node, children: list):
        return BranchList()

    def visit_list(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        return ListRangeList(non_empty[0])

    def visit_list_item(self, value, children: list):
        if len(children) == 1:
            return children[0]
        return children

    def visit_list_item2(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty

    def visit_str_list(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        while isinstance(non_empty[0], list):
            non_empty = non_empty[0]
        return ListRangeList(non_empty)

    def visit_str_list_item(self, value, children: list):
        if len(children) == 1:
            return children[0]
        return children

    def visit_str_list_item2(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty

    def visit_atom(self, value, children: list):
        return children[0]

    def visit_number(self, value, children: list):
        return int(value.text)

    def visit_string(self, value, children: list):
        return value.text.strip()[1:-1].replace("\\'", "'").replace("\\n", '\n')

    def generic_visit(self, node, children: list):
        if isinstance(children, list) and len(children) == 1:
            return children[0]
        return children

class RevisionListVisitor(Visitor):
    """
    Visitor for the grammar with default rule revision_list.
    """

    def visit_revision_list(self, value, children: list):
        return children[0]

    def visit_revision_list_item(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty


def parse_revision_list(text: str) -> list:
    """
    Parses a revision list (see Notes).
    :param text: string to parse
    :return: list of RangeList objects
    :raises parsimonious.exceptions.ParseError if a parse error occures
    """
    grammar = globals()["grammar"].default("revision_list")
    res = RevisionListVisitor().visit(grammar.parse(text))
    if not isinstance(res, list):
        return [res]
    return res


class BuildCmdListVisitor(Visitor):
    """
    Visitor for the grammar with default rule build_cmd_list.
    """

    def visit_build_cmd_list(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        return children

    def visit_build_cmd_list_item(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty


def parse_build_cmd_list(text: str) -> list:
    """
    Parses a build cmd list (see Notes).
    :param text: string to parse
    :return: list of lists of RangeList objects
    :raises parsimonious.exceptions.ParseError if a parse error occures
    """
    grammar = globals()["grammar"].default("build_cmd_list")
    res = BuildCmdListVisitor().visit(grammar.parse(text))
    res = res[0]
    if all(isinstance(r, list) for r in res):
        res = [Visitor.filter_non_empty(r) for r in res]
    else:
        res = [Visitor.filter_non_empty(res)]
    return res


class PathListVisitor(Visitor):
    """
    Visitor for the grammar with default rule path_list.
    """

    def visit_path_list(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        while isinstance(non_empty[0], list):
            non_empty = non_empty[0]
        return children

    def visit_path_list_item(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty

    def visit_path_list_token(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        return non_empty[0]

    def visit_path_list_short_token(self, value, children: list):
        res = [InfRange() if x == [] else x for x in children]
        return res

    def visit_path_list_long_token(self, value, children: list):
        children = self.filter_non_empty(children)
        res = self.filter_non_empty(children[0]) + [children[1]]
        return res


def parse_path_list(text: str) -> list:
    """
    Parses a path list (see Notes).
    :param text: string to parse
    :return: list of lists of RangeList and string objects
    :raises parsimonious.exceptions.ParseError if a parse error occures
    """
    grammar = globals()["grammar"].default("path_list")
    res = PathListVisitor().visit(grammar.parse(text))
    while isinstance(res[0], list) and len(res) == 1:
            res = res[0]
    if isinstance(res[0], RangeList):
        res = [res]
    return res


class RunCmdListVisitor(Visitor):
    """
    Visitor for the grammar with default rule run_cmd_list.
    """

    def visit_run_cmd_list(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        while isinstance(non_empty[0][0], list):
            non_empty = non_empty[0]
        return non_empty

    def visit_run_cmd_list_item(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        if isinstance(non_empty[1], list):
            non_empty = [non_empty[0]] + non_empty[1]
        return non_empty

    def visit_run_cmd_list_token(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        return non_empty[0]

    def visit_run_cmd_list_short_token(self, value, children: list):
        res = [InfRange() if x == [] else x for x in children]
        return res

    def visit_run_cmd_list_long_token(self, value, children: list):
        children = self.filter_non_empty(children)
        res = self.filter_non_empty(children[0]) + [children[1]]
        return res


def parse_run_cmd_list(text: str) -> list:
    """
    Parses a run cmd list (see Notes).
    :param text: string to parse
    :return: list of lists of RangeList objects
    :raises parsimonious.exceptions.ParseError if a parse error occures
    """
    grammar = globals()["grammar"].default("run_cmd_list")
    res = RunCmdListVisitor().visit(grammar.parse(text))
    while isinstance(res[0], list) and len(res) == 1:
            res = res[0]
    if isinstance(res[0], RangeList):
        res = [res]
    return res


class ReportTupleListVisitor(RunCmdListVisitor):
    """
    Visitor for the grammar with default rule report_tuple_list.
    """

    def visit_report_tuple_list(self, value, children: list):
        return self.visit_run_cmd_list(value, children)

    def visit_report_tuple_list_item(self, value, children: list):
        return self.visit_run_cmd_list_item(value, children)

    def visit_report_tuple_list_token(self, value, children: list):
        return self.visit_run_cmd_list_token(value, children)

    def visit_report_tuple_list_short_token(self, value, children: list):
        res = [InfRange() if x == [] else x for x in children]
        return res

    def visit_report_tuple_list_long_token(self, value, children: list):
        return self.visit_run_cmd_list_long_token(value, children)

    def visit_report_list_inf_token(self, value, children: list):
        non_empty = self.filter_non_empty(children)
        return non_empty * 3


def parse_report_tuple_list(text: str) -> list:
    """
    Parses a run cmd list that is used for parameter "revisions" for "temci report". That's basically the same
    as the run cmd list. The only difference is that the report tuple list allows inf_range ("[..]") for the
    last run cmd part and for the build command part. It allows for example::

        [..]:['make']:[..] # use all benchmarkings of binaries built with 'make'

    :param text: string to parse
    :return: list of lists of RangeList object
    :raises parsimonious.exceptions.ParseError if a parse error occures
    """
    grammar = globals()["grammar"].default("report_tuple_list")
    res = ReportTupleListVisitor().visit(grammar.parse(text))
    while isinstance(res[0], list) and len(res) == 1:
            res = res[0]
    if isinstance(res[0], RangeList):
        res = [res]
    return res


def SyntaxCheckedStr(parse_method, description: str) -> NonErrorConstraint:
    """
    Returns a typechecker type that checks for the value to be parseable by the passed parse method (yields no errors)
    that is described by the passed description.
    """
    return NonErrorConstraint(parse_method, parsimonious.exceptions.ParseError, Str(), description)


def RevisionListStr() -> NonErrorConstraint:
    """
    Returns a typecheck type that describes and matches all valid revision list strings.
    """
    return SyntaxCheckedStr(parse_revision_list, "revision list")


def BuildCmdListStr() -> NonErrorConstraint:
    """
    Returns a typecheck type that describes and matches all valid build command list strings.
    """
    return SyntaxCheckedStr(parse_build_cmd_list, "build command list")


def PathListStr() -> NonErrorConstraint:
    """
    Returns a typecheck type that describes and matches all valid path list strings.
    """
    return SyntaxCheckedStr(parse_path_list, "path list")


def RunCmdListStr() -> NonErrorConstraint:
    """
    Returns a typecheck type that describes and matches all valid run command list strings.
    """
    return SyntaxCheckedStr(parse_run_cmd_list, "run command list")


def ReportTupleListStr() -> NonErrorConstraint:
    """
    Returns a typecheck type that describes and matches all valid report tuple list strings (arguments for the
    "revisions" parameter of "temci report").
    """
    return SyntaxCheckedStr(parse_report_tuple_list, "report tuple list")