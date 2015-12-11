"""
Enables the randomization of assembler files and can be used as a wrapper for as.

Currently only tested on 64bit system.
"""


import random
import re
import sys, os, subprocess, shlex
import tempfile

import time

from temci.utils.typecheck import *


class Line:
    """
    A line of assembly
    """

    def __init__(self, content: str, number: int):
        """

        :param content: content of the line (without line separator)
        :param number: line number (starting at 0)
        """
        typecheck(content, Str())
        typecheck(number, Int())
        self.content = content
        self.number = number

    def __str__(self) -> bool:
        return self.content

    def is_label(self) -> bool:
        return ":" in self.content and ":" in self.content.strip().split(" ")[0]

    def is_function_label(self) -> bool:
        return self.is_label() and not self.get_label().startswith(".")

    def get_label(self) -> str:
        """
        Returns the label if the line consists of label, None otherwise.
        """
        return self.content.split(":")[0] if self.is_label() else None

    def is_statement(self) -> bool:
        #print(self.content, not self.is_label(), self.startswith("\t"), not self.startswith("/"))
        return not self.is_label() and not self.startswith("/") and self.content.strip() != ""

    def to_statement_line(self) -> 'StatementLine':
        return StatementLine(self.content, self.number)

    def is_segment_statement(self, segment_names: list = None) -> bool:
        segment_names = segment_names or ["bss", "data", "rodata", "text"]
        checked_starts = ["." + x for x in segment_names] + [".section ." + x for x in segment_names]
        return self.is_statement() and any(self.startswith(x) for x in checked_starts)

    def split_section_before(self) -> bool:
        """
        Does this statement split the current set of lines into to sections?
        """
        if not self.is_statement():
            return False
        return len(self.content.strip()) == 0 or \
                self.is_segment_statement() or \
                self.number == 1

    def startswith(self, other_str: str) -> bool:
        return re.sub(r"\s+", " ", self.content.strip()).startswith(other_str)

class StatementLine(Line):
    """
    An assembly statement.
    """

    def __init__(self, content: str, number: int):
        super().__init__(content, number)
        if not self.is_statement():
            raise ValueError(content + "isn't a valid statement line")
        arr = re.split(r"\s+", self.content.strip(), maxsplit=1)
        self.statement = arr[0]
        self.rest = arr[1] if len(arr) == 2 else ""


class Section:
    """
    A set of assembly lines.
    """

    def __init__(self, lines: list = None):
        self.lines = lines or []

    def append(self, line: Line):
        typecheck(line, Line)
        self.lines.append(line)

    def extend(self, lines: list):
        typecheck(lines, List(Line))
        self.lines.extend(lines)

    def __str__(self) -> str:
        return "\n".join(str(x) for x in self.lines if not x.startswith(".loc "))

    def __len__(self) -> int:
        return len(self.lines)

    @classmethod
    def from_lines(cls, lines: list) -> 'Section':
        typecheck(lines, List(T(Line)))
        if any(line.is_function_label() for line in lines):
            return FunctionSection(lines)
        section = Section(lines)
        return section

    def starts_with_segement_statement(self) -> bool:
        """
        Does the first (non empty) line of this section starts a new segment?
        """
        for line in self.lines:
            if line.is_segment_statement():
                return True
            if not line.is_empty():
                return False
        return False

    def randomize_segment(self, segment_name: str):
        """
        Randomizes the segment part in the current section by splitting it into label induced subsections
        and shuffling them.

        :param segment_name: bss, data or rodata (text doesn't make any sense)
        """
        typecheck(segment_name, ExactEither("bss", "data", "rodata"))
        i = 0
        while i < len(self.lines):
            possible_starts = ["." + segment_name, ".section " + segment_name]
            while i < len(self.lines) and \
                not any(self.lines[i].startswith(x) for x in possible_starts):
                i += 1
            if i == len(self.lines):
                return
            j = i + 1
            while j < len(self.lines) and not self.lines[i].split_section_before():
                j += 1
            if j == len(self.lines):
                return
            parts_to_shuffle = self.lines[i + 1:j]
            # split the lines at the labels and shuffle these subsections
            subsections = [[]]
            for line in parts_to_shuffle:
                if line.is_label() and len(subsections[-1]) > 0:
                    subsections.append([])
                subsections[-1].append(line)
            random.shuffle(subsections)
            parts_to_shuffle = [x for sublist in subsections for x in sublist]
            self.lines[i + 1:j] = parts_to_shuffle
            i = j

    def randomize_malloc_calls(self, padding: range):
        """
        Randomizes the malloc calls (and thereby the heap) by adding the given padding to each malloc call.
        :param padding: given padding
        """
        def rand() -> int:
            return random.randrange(padding.start, padding.stop, padding.step)
        subq_statement_format = "\taddq ${}, %rdi" if sys.maxsize > 2**32 else "\tadd ${}, %edi"
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if line.is_statement() and line.to_statement_line().statement == "call":
                arr = re.split(r"\s+", line.to_statement_line().rest.strip())
                if len(arr) == 0 or arr[0] != "malloc":
                    i += 1
                    continue
                self.lines.insert(i, Line(subq_statement_format.format(rand()), i))
                i += 1
            i += 1

class FunctionSection(Section):
    """
    A set of lines for a specific function.
    Assumptions:
    - a function uses "pushq %rbp" as its first real instruction
    - a function uses [real instruction] \n "ret" to return from it
    """

    def pad_stack(self, amount: int):
        self._replace_leave()
        """
        Pads the stack at the beginning of each function call by the given amount.
        :param amount: amount to pad the stack
        """
        # search for function label
        i = 0
        while i < len(self.lines) and not self.lines[i].is_function_label():
            i += 1
        if i == len(self.lines):
            return
        # search for the first "pushq %rbp" instruction

        def is_push_instr():
            line = self.lines[i]
            if not line.is_statement():
                return False
            splitted = re.split(r"\s+", line.content.strip(), maxsplit=1)
            if len(splitted) != 2:
                return False
            return splitted[0].strip() == "pushq" and splitted[1].strip().startswith("%rbp")

        while i < len(self.lines) and not is_push_instr():
            i += 1
        if i == len(self.lines):
            return False
        # insert a subq $xxx, %rsp instruction, that shouldn't have any bad side effect
        self.lines.insert(i + 1, Line("\tsubq ${}, %rsp\n".format(amount), i))
        i += 1
        # search for all ret instructions and place a "subq $-xxx, %rbp" like statement
        # right before the (real) instruction before the ret instruction

        def is_real_instruction(line: Line):
            return line.is_statement() and line.to_statement_line().statement == "popq"

        def is_ret_instruction(line: Line):
            return line.is_statement() and line.to_statement_line().statement == "ret"

        while i < len(self.lines):
            j = i

            # search for ret instruction
            while j < len(self.lines) and not is_ret_instruction(self.lines[j]):
                j += 1
            if j == len(self.lines):
                return
            # no self.lines[j] =~ "ret" and search for real instruction directly before
            k = j
            while k > i and not is_real_instruction(self.lines[k]):
                k -= 1
            if k == i:
                #print("error", self.lines[k])
                return
            self.lines.insert(k, Line("\taddq ${}, %rsp\n".format(amount), k))
            i = k + 2

    def _replace_leave(self):
        i = 0
        while i < len(self.lines):
            j = i
            while j < len(self.lines) and not (self.lines[j].is_statement() and
                                                       self.lines[j].to_statement_line().statement == "leave"):
                j += 1
            if j == len(self.lines):
                return
            self.lines[j] = Line("mov %rbp, %rsp", j)
            self.lines.insert(j + 1, Line("popq %rbp", j))
            j += 2
            i = j



class AssemblyFile:
    """
    A class that simplifies dealing with the lines of an assembly file.
    It allows the simple randomization of the assembly file.

    Attention: Most methods change the AssemblyFile directly,
    """

    def __init__(self, lines: list):
        self._lines = []
        self.sections = []
        self.add_lines(lines)

    def _init_sections(self):
        self.sections = []
        if any(line.startswith("# Begin") for line in self._lines): # libfirm mode
            cur = Section()
            for i, line in enumerate(self._lines):
                if line.content.strip() == "":
                    self.sections.append(cur)
                    cur = Section()
                cur.append(line)
            self.sections.append(cur)
        elif any(line.startswith(".cfi") for line in self._lines): # gcc mode
            cur = Section()
            for line in self._lines:
                if line.content.strip() == ".text":
                    self.sections.append(cur)
                    cur = Section()
                cur.append(line)
            self.sections.append(cur)
        else:
            raise ValueError("Unknown assembler")

    def add_lines(self, lines: list):
        """
        Add the passed lines.
        :param lines: either list of Lines or strings representing Lines
        """
        typecheck(lines, List(T(Line)|Str()))
        start_num = len(self._lines)
        for (i, line) in enumerate(lines):
            if isinstance(line, T(Line)):
                line.number = i + start_num
                self._lines.append(line)
            else:
                self._lines.append(Line(line, i + start_num))
        self._init_sections()

    def randomize_file_structure(self, small_changes = True):
        """
        Randomizes the sections relative positions but doesn't change the first section.
        """
        _sections = self.sections[1:-1]
        if small_changes:
            i = 0
            while i < len(_sections) - 1:
                if random.randrange(0, 2) == 0:
                    tmp = _sections[i]
                    _sections[i] = _sections[i + 1]
                    _sections[i + 1] = tmp
                i += 2
        else:
            random.shuffle(_sections)
        self.sections[1:-1] = _sections

    def randomize_stack(self, padding: range):
        for section in self.sections:
            if isinstance(section, FunctionSection):
                section.pad_stack(random.randrange(padding.start, padding.stop, padding.step))

    def randomize_sub_segments(self, segment_name: str):
        """
        Randomize the segments of the given name.
        :param segment_name: segment name, e.g. "bss", "data" or "rodata"
        """
        for section in self.sections:
            section.randomize_segment(segment_name)

    def randomize_malloc_calls(self, padding: range):
        for section in self.sections:
            section.randomize_malloc_calls(padding)

    def __str__(self):
        return "\n/****/\n".join(map(str, self.sections)) + "\n"

    @classmethod
    def from_file(cls, file: str):
        with open(file, "r") as f:
            return AssemblyFile([line.rstrip() for line in f.readlines()])

    def to_file(self, file: str):
        with open(file, "w") as f:
            f.write(str(self))


class AssemblyProcessor:

    config_scheme = Dict({
        "heap": NaturalNumber() // Default(0)
                // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
        "stack": NaturalNumber() // Default(0)
                // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
        "bss": Bool() // Default(False)
                // Description("Randomize the bss sub segments?"),
        "data": Bool() // Default(False)
                // Description("Randomize the data sub segments?"),
        "rodata": Bool() // Default(False)
                // Description("Randomize the rodata sub segments?"),
        "file_structure": Bool() // Default(False)
                          // Description("Randomize the file structure.")
    })

    def __init__(self, config: dict):
        self.config = self.config_scheme.get_default()
        self.config.update(config)
        typecheck(self.config, self.config_scheme)

    def process(self, file: str, small_changes = False):
        assm = AssemblyFile.from_file(file)
        assm.to_file("/tmp/abc.s")
        if self.config["file_structure"]:
            assm.randomize_file_structure(small_changes)
        if self.config["heap"] > 0:
            assm.randomize_malloc_calls(padding=range(0, self.config["heap"]))
        if self.config["stack"] > 0:
            assm.randomize_stack(padding=range(0, self.config["stack"]))
        if self.config["bss"]:
            assm.randomize_sub_segments("bss")
        if self.config["data"]:
            assm.randomize_sub_segments("data")
        if self.config["rodata"]:
            assm.randomize_sub_segments("rodata")
        assm.to_file(file)
        assm.to_file("/tmp/abcd.s")

if __name__ == "__main__":

    def test(assm: AssemblyFile):
        tmp_file = "/tmp/test.s"
        assm.to_file(tmp_file)
        os.system("gcc {} -o /tmp/test && /tmp/test".format(tmp_file))

    print(Line("	.section	.text.unlikely\n", 1).is_segment_statement())
    #exit(0)
    #assm = AssemblyFile.from_file("/home/parttimenerd/Documents/Studium/Bachelorarbeit/test/hello2/hello.s")
    assm = AssemblyFile.from_file("/tmp/abc.s")
    #test(assm)
    #assm.randomize_malloc_calls(padding=range(1, 1000))
    #test(assm)
    assm.randomize_file_structure()
    test(assm)
    #print("till randomize")
    #assm.randomize_stack(padding=range(1, 100))
    #test(assm)
    #for x in  ["bss", "data", "rodata"]:
    #    assm.randomize_sub_segments(x)
    #    test(assm)
