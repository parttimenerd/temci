import unittest
from temci.model.parser import parse_revision_list, parse_build_cmd_list, parse_path_list, \
    parse_run_cmd_list, parse_report_tuple_list, RevisionListStr, BuildCmdListStr, PathListStr,\
    RunCmdListStr, ReportTupleListStr
from parsimonious.exceptions import ParseError


class TestParser(unittest.TestCase):

    def test_parse_revision_list_and_basic_grammar(self):
        def correct(text: str, res_strs: list = None):
            res_strs = [] if res_strs is None else res_strs
            msg = ""
            res = []
            try:
                res = parse_revision_list(text)
            except ParseError as exp:
                msg = text + ": " + str(exp)
                self.assertEqual("", msg)
                self.assertTrue(isinstance(text, RevisionListStr()))
            if res_strs:
                self.assertListEqual(res_strs, [str(x) for x in res])

        def incorrect(text: str):
            self.assertFalse(isinstance(text, RevisionListStr()))
            with self.assertRaises(ParseError):
                print(parse_revision_list(text))

        correct("[..9]", ["[..9]"])
        correct("[9..]", ["[9..]"])
        correct("[-9..9]", ["[-9..9]"])
        correct("[-0..-0]", ["[0..0]"])
        correct("[branch] ;[branch]", ["[branch]", "[branch]"])
        correct("[branch] ;   [branch]", ["[branch]", "[branch]"])
        correct("[9,8]; [branch]; ['sdf', '\\'sdfsdf']", ["[9, 8]", "[branch]", "['sdf', ''sdfsdf']"])

        incorrect("[..] ;[..]")
        incorrect("[..] ;   [..]")
        incorrect("[..4..]")
        incorrect("..")
        incorrect(";")
        incorrect("-")
        incorrect("'sdf'")
        incorrect("4")
        incorrect("; ;     ")
        incorrect("[-0..-0")
        incorrect("[..")
        incorrect("[0,.]")
        incorrect("[0, ..]")
        incorrect("[0,     ")

    def test_parse_build_cmd_list(self):
        def correct(text: str, res_strs: list = None):
            res_strs = [] if res_strs is None else res_strs
            msg = ""
            res = []
            try:
                res = parse_build_cmd_list(text)
            except ParseError as exp:
                msg = text + ": " + str(exp)
            self.assertTrue(isinstance(text, BuildCmdListStr()))
            if res_strs:
                self.assertEqual("", msg)
                self.assertListEqual(res_strs, [[str(x2) for x2 in x] for x in res])

        def incorrect(text):
            self.assertFalse(isinstance(text, BuildCmdListStr()))
            with self.assertRaises(ParseError):
                print(parse_build_cmd_list(text))

        correct("[..9]:['']", [["[..9]", "['']"]])
        correct("[9..]:['as']")
        correct("[..] : ['a\\'', 'as '] ;[..]:   ['a', 'b', 'c']",
                [["[..]", "['a'', 'as ']"], ["[..]", "['a', 'b', 'c']"]])
        correct("[branch]: ['s']", [["[branch]", "['s']"]])

        incorrect("[..]")
        incorrect("[..")
        incorrect("[..]: [9..9]")
        incorrect("[..]: [0]")

    def test_parse_path_list(self):
        def correct(text: str, res_strs: list = None):
            res_strs = [] if res_strs is None else res_strs
            msg = ""
            res = []
            try:
                res = parse_path_list(text)
            except ParseError as exp:
                msg = text + ": " + str(exp)
            self.assertTrue(isinstance(text, PathListStr()))
            if res_strs:
                self.assertEqual("", msg)
                self.assertListEqual(res_strs, [[str(x2) for x2 in x] for x in res])

        def incorrect(text):
            self.assertFalse(isinstance(text, PathListStr()))
            with self.assertRaises(ParseError):
                print(parse_path_list(text))

        correct("[..] :    'sd'", [["[..]", 'sd']])
        correct("[..] : 'sd'; [..] : 'sd'", [["[..]", 'sd'], ["[..]", 'sd']])
        correct("[..] : ['make'] :'sd'", [["[..]", "['make']", 'sd']])
        correct("   [9..] : ['make'] :'sd'", [["[9..]", "['make']", 'sd']])
        correct("   [..] : ['make'] :'sd'", [["[..]", "['make']", 'sd']])
        correct("   [9,2] : ['make'] :'sd'", [["[9, 2]", "['make']", 'sd']])
        correct("[9,3,4] : [''] :'sdf'", [["[9, 3, 4]", "['']", 'sdf']])
        correct("[branch]: ['s']: 'sd'", [["[branch]", "['s']", 'sd']])

        incorrect("[..]: [9] : 'sd'")
        incorrect("[..] : [..] : 'sd'")
        incorrect("[..]: [9] : ")
        incorrect("[..] : [..] : ")
        incorrect("[..]: [9] ")
        incorrect("[..] : [..] ")
        incorrect("[..]: [9] : ")
        incorrect("[..] : [] : ''")

    def test_run_cmd_list(self):
        def correct(text: str, res_strs: list = None):
            res_strs = [] if res_strs is None else res_strs
            msg = ""
            res = []
            try:
                res = parse_run_cmd_list(text)
            except ParseError as exp:
                msg = text + ": " + str(exp)
            if res_strs:
                self.assertEqual("", msg)
                self.assertListEqual(res_strs, [[str(x2) for x2 in x] for x in res])
            self.assertTrue(isinstance(text, RunCmdListStr()))

        def incorrect(text):
            self.assertFalse(isinstance(text, RunCmdListStr()))
            with self.assertRaises(ParseError):
                print(parse_run_cmd_list(text))

        correct("[..]: ['d', 'e']", [["[..]", "['d', 'e']"]])
        correct("[..]: ['ads', 'sdf']: ['d']", [["[..]", "['ads', 'sdf']", "['d']"]])
        correct("[..]: ['d', 'e']   ;   [..]: ['d', 'e']", [["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"]])
        correct("[..]: ['d', 'e']   ;[..]: ['d', 'e'];[..]: [    'd', 'e']     ",
                [["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"]])
        correct("[branch]: ['s']: ['s']", [["[branch]", "['s']", "['s']"]])

        incorrect("[..]: ['ads'. 'sdf']: ['d']")
        incorrect("[..]: ['ads'. 'sdf']: [..]")
        incorrect("[..] : [..] : ['as']")
        incorrect("[8,9] : [9] : ['as']")
        incorrect("[..]: 'as'")
        incorrect("[..]: ['a']; ")
        incorrect(";")
        incorrect("    ")

    def test_parse_report_tuple_list(self):
        def correct(text: str, res_strs: list = None):
            res_strs = [] if res_strs is None else res_strs
            msg = ""
            res = []
            try:
                res = parse_report_tuple_list(text)
            except ParseError as exp:
                msg = text + ": " + str(exp)
            self.assertTrue(isinstance(text, ReportTupleListStr()))
            if res_strs:
                self.assertEqual("", msg)
                self.assertListEqual(res_strs, [[str(x2) for x2 in x] for x in res])

        def incorrect(text):
            self.assertFalse(isinstance(text, ReportTupleListStr()))
            with self.assertRaises(ParseError):
                print(parse_report_tuple_list(text))

        correct("[..]: ['d', 'e']", [["[..]", "['d', 'e']"]])
        correct("[..]: ['ads', 'sdf']: ['d']", [["[..]", "['ads', 'sdf']", "['d']"]])
        correct("[..]: ['d', 'e']   ;   [..]: ['d', 'e']", [["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"]])
        correct("[..]: ['d', 'e']   ;   [..]: ['d', 'e'];   [..]: ['d', 'e']",
                [["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"], ["[..]", "['d', 'e']"]])
        correct("[..]: [..]", [["[..]", "[..]"]])
        correct("[..]: ['ads', 'sdf']: [..]", [["[..]", "['ads', 'sdf']", "[..]"]])
        correct("[..]: [..] : [..]", [["[..]", "[..]", "[..]"]])
        correct("[..]: ['sdfa', 'd'] : [..] ", [["[..]", "['sdfa', 'd']", "[..]"]])
        correct("[branch]: ['s']: [..]", [["[branch]", "['s']", "[..]"]])

        incorrect("[..]: ['ads'. 'sdf']: ['d']")
        incorrect("[8,9] : [9] : ['as']")
        incorrect("[..]: 'as'")
        incorrect("[..]: ['a']; ")
        incorrect(";")
        incorrect("    ")