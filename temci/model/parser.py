"""
A parser for the range expressions, that works with the main model and can extend it.

https://github.com/erikrose/parsimonious
https://github.com/erikrose/parsimonious/blob/master/parsimonious/grammar.py
"""

from parsimonious.grammar import Grammar, NodeVisitor

class RangeList(object):
    """
    The basic range.
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
        return "[..]"

    def __repr__(self):
        return "\"" + self.__str__() + "\""


class InfList(RangeList):
    """
    Alias for RangeList. A list that contains every element.
    """

class IntRange(RangeList):
    """
    A range of integers with start an end. That includes every item in between it's borders (and the border values)
    """

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def filter(self, av_list: list) -> list:
        return [x for x in av_list if self.start <= x <= self.end]

    def additional(self, av_list) -> list:
        return [x for x in range(self.start, self.end + 1) if x not in av_list]

    def __str__(self):
        return "[{}..{}]".format(self.start, self.end)


class IntRangeOpenEnd(RangeList):
    """
    A range of integers that includes every item that is >= its start value.
    """

    def __init__(self, start):
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

    def __init__(self, end):
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
        self.raw_list = raw_list

    def _has_prefix(self, new_element, elements):
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
    run = token+

    revision_list = revision_list_item / token
    revision_list_item = ws* token ws* ";" ws* revision_list ws*

    build_cmd_list = build_cmd_list_item / bc_token
    build_cmd_list_item = ws* bc_token ws* ";" ws* build_cmd_list ws*
    bc_token = ws* token ws* ":" ws* str_list ws*

    path_list = path_list_item / path_list_token
    path_list_item = ws* path_list_token ws* ";" ws* path_list ws*
    path_list_token = path_list_long_token / path_list_short_token
    path_list_long_token = bc_token ":" string
    path_list_short_token = inf_range ":" string

    run_cmd_list = run_cmd_list_item / run_cmd_list_token
    run_cmd_list_item = ws* run_cmd_list_token ws* ";" ws* run_cmd_list ws*
    run_cmd_list_token = run_cmd_list_long_token / run_cmd_list_short_token
    run_cmd_list_long_token = bc_token ":" str_list
    run_cmd_list_short_token = inf_range ":" str_list

    #basic grammar below

    token = inf_range / number_range_open_start / number_range_open_end / list / number_range

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
    ws = ~r"\ *"
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
        return RangeList()

    def visit_number_range(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRange(numbers[0], numbers[1])

    def visit_number_range_open_start(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRangeOpenStart(numbers[0])

    def visit_number_range_open_end(self, value, children: list):
        numbers = self._filter_str_and_num(children)
        return IntRangeOpenEnd(numbers[0])

    def visit_list(self, value, children: list):
        non_empty = [x for x in children if len(x) != 0]
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
    """
    grammar = globals()["grammar"].default("revision_list")
    res = RevisionListVisitor().visit(grammar.parse(text))
    if not isinstance(res, list):
        return [res]
    return res


class BuildCmdListVisitor(Visitor):

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
        return self.filter_non_empty(children)

    def visit_path_list_long_token(self, value, children: list):
        children = self.filter_non_empty(children)
        res = self.filter_non_empty(children[0]) + [children[1]]
        return res


def parse_path_list(text: str) -> list:
    """
    Parses a path list (see Notes).
    :param text: string to parse
    :return: list of lists of RangeList and string objects
    """
    grammar = globals()["grammar"].default("path_list")
    res = PathListVisitor().visit(grammar.parse(text))
    while isinstance(res[0], list) and len(res) == 1:
            res = res[0]
    if isinstance(res[0], RangeList):
        res = [res]
    return res


class RunCmdListVisitor(Visitor):

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
        return self.filter_non_empty(children)

    def visit_run_cmd_list_long_token(self, value, children: list):
        children = self.filter_non_empty(children)
        res = self.filter_non_empty(children[0]) + [children[1]]
        return res


def parse_run_cmd_list(text: str) -> list:
    """
    Parses a run cmd list (see Notes).
    :param text: string to parse
    :return: list of lists of RangeList objects
    """
    grammar = globals()["grammar"].default("run_cmd_list")
    res = RunCmdListVisitor().visit(grammar.parse(text))
    while isinstance(res[0], list) and len(res) == 1:
            res = res[0]
    if isinstance(res[0], RangeList):
        res = [res]
    return res