"""
Enables the randomization of assembler files and can be used as a wrapper for as (@see ../scripts/as).

Currently only tested on a 64 bit systems and with GCC and CParser/libFirm.
"""

import json
import logging
import random
import re
import sys, os, subprocess, copy
import tempfile

import time

import shutil

from temci.utils.typecheck import *
import typing as t
import temci.utils.settings


class Line:
    """
    A line of assembly code.
    """

    def __init__(self, content: str, number: int):
        """
        Constructs a new Line object.

        :param content: content of the line (without line separator)
        :param number: line number (starting at 0)
        """
        typecheck(content, Str())
        typecheck(number, Int())
        self.content = content  # type: str
        """ Content of this line """
        self.number = number  # type: int
        """ Number of this line (starting at zero) in the original assembler file """

    def __str__(self) -> str:
        """ Returns the content of this line. """
        return self.content

    def is_label(self) -> bool:
        """ Is this line an assembler label? """
        return ":" in self.content and ":" in self.content.strip().split(" ")[0]

    def is_function_label(self) -> bool:
        """ Is this line a function label (a label not starting with a dot)? """
        return self.is_label() and not self.get_label().startswith(".")

    def get_label(self) -> t.Optional[str]:
        """ Returns the label if the line is a label. """
        return self.content.split(":")[0] if self.is_label() else None

    def is_statement(self) -> bool:
        """ Is this line an assembler statement or directive? """
        return not self.is_label() and not self.startswith("/") and self.content.strip() != ""

    def to_statement_line(self) -> 'StatementLine':
        """ Convert this line to an StatementLine object (simply by creating a new object with the same contents). """
        return StatementLine(self.content, self.number)

    def is_segment_directive(self, segment_names: t.List[str] = ["bss", "data", "rodata", "text"]) -> bool:
        """
        Is this line an assembler segment directive?
        :param segment_names: names of possible segments
        """
        checked_starts = ["." + x for x in segment_names] + [".section ." + x for x in segment_names]
        return self.is_statement() and any(self.startswith(x) for x in checked_starts)

    def split_section_before(self) -> bool:
        """ Does this statement split the current set of lines into to sections? """
        if not self.is_statement():
            return False
        return len(self.content.strip()) == 0 or \
                self.is_segment_directive() or \
                self.number == 1

    def startswith(self, other_str: str) -> bool:
        """
        Does this line start with the given string (omitting all trailing whitespace and tabs and multiple whitespace)?

        :param other_str: string to check against
        """
        return re.sub(r"\s+", " ", self.content.strip()).startswith(other_str)


class StatementLine(Line):
    """
    A line of assembly code representing and statement or directive
    """

    def __init__(self, content: str, number: int):
        """
        Creates a new statement line object.
        :param content: content of the line
        :param number: line number (starting at zero)
        :raises: ValueError if the content doesn't represent a valid assembly statement
        """
        super().__init__(content, number)
        if not self.is_statement():
            raise ValueError(content + "isn't a valid statement line")
        arr = re.split(r"\s+", self.content.strip(), maxsplit=1)
        self.statement = arr[0]  # type: str
        """ Statement or first part of this line """
        self.rest = arr[1] if len(arr) == 2 else ""  # type: str
        """ The second part of the line or empty string if the line only consists of a statement """


class Section:
    """
    A set of assembly lines headed by section directive.
    """

    def __init__(self, lines: t.Optional[t.List[Line]] = None):
        """
        Creates a new assembly section.

        :param lines: initial set of lines of this section, default is an empty list
        """
        self.lines = lines or []  # type: t.List[Line]
        """ Assembly lines that build up this section """

    def append(self, line: Line):
        """
        Append the passed line to the lines of this section.

        :param line: appended line
        """
        typecheck(line, Line)
        self.lines.append(line)

    def extend(self, lines: t.List[Line]):
        """
        Extend the lines of this section by the passed lines.
        :param lines: appended lines
        """
        typecheck(lines, List(Line))
        self.lines.extend(lines)

    def __str__(self) -> str:
        return "\n".join(str(x) for x in self.lines if not x.startswith(".loc "))

    def __repr__(self) -> str:
        if self.lines:
            return "Section({} to {})".format(self.lines[0].number, self.lines[-1].number)
        return "Section()"

    def __len__(self) -> int:
        """ Returns the number of lines in this section. """
        return len(self.lines)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.lines == other.lines

    @classmethod
    def from_lines(cls, lines: t.List[Line]) -> 'Section':
        """
        Creates a new section from the passed lines.
        A FunctionSection is created if any of the lines seems to be a function label or a function starting comment.
        :param lines: passed lines
        :return: created FunctionSection or Section object
        """
        typecheck(lines, List(T(Line)))
        libfirm_begin_pattern = re.compile("#[-\ ]* Begin ")
        if any(line.is_function_label() or libfirm_begin_pattern.match(line.content) for line in lines):
            return FunctionSection(lines)
        section = Section(lines)
        return section

    def starts_with_segement_statement(self) -> bool:
        """ Does the first (non empty) line of this section starts a new segment? """
        for line in self.lines:
            if line.is_segment_directive():
                return True
            if line.content:
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
        Randomizes the `[c|m]alloc` and `new` method calls (and thereby the heap)
        by adding the given padding to each malloc call.

        :param padding: given range of bytes to pad
        """
        def rand() -> int:
            return random.randrange(padding.start, padding.stop, padding.step)

        randomized_method_names = ["malloc", "_Znwm", "_Znam", "calloc"]
        # doesn't support realloc for now

        subq_statement_format = "\taddq ${}, %rdi" if sys.maxsize > 2**32 else "\tadd ${}, %edi"
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if line.is_statement() and line.to_statement_line().statement == "call":
                arr = re.split(r"\s+", line.to_statement_line().rest.strip())
                if len(arr) == 0 or arr[0] not in randomized_method_names:
                    i += 1
                    continue
                self.lines.insert(i, Line(subq_statement_format.format(rand()), i))
                i += 1
            i += 1


class FunctionSection(Section):
    """
    A section that represents the code of a function.
    """


class AssemblyFile:
    """
    An abstract assembly file that contains all lines and sections of an assembly file.
    It allows the simple randomization of the assembly file.

    Attention: Most methods change the AssemblyFile directly.
    """

    def __init__(self, lines: t.List[t.Union[Line, str]]):
        """
        Creates a new assembly file object from the passed assembly lines.

        :param lines: assembly line objects or strings
        """
        self._lines = []  # type: t.List[Line]
        """ Lines of the original assembly file """
        self.sections = []  # type: t.List[Section]
        """ Sections that build up the assembly file """
        self.add_lines(lines)

    def _init_sections(self):
        """
        Initialize the sections of this assembly file.
        Currently only works well for CParser/libFirm produced assembler and quirky for GCC produced assembler.

        :raises: ValueError if an unknown assembler format (not libFirm or GCC) is encountered.
        """
        self.sections.clear()
        libfirm_begin_pattern = re.compile("#[-\ ]* Begin ")
        if any(bool(libfirm_begin_pattern.match(line.content)) for line in self._lines): # libfirm mode
            cur = Section()
            for i, line in enumerate(self._lines):
                if line.content.strip() == "":
                    self.sections.append(Section.from_lines(cur.lines))
                    cur = Section()
                cur.append(line)
            self.sections.append(cur)
        elif any(line.startswith(".cfi") for line in self._lines): # gcc mode
            cur = Section()
            for i, line in enumerate(self._lines):
                if line.content.strip() == ".text" or line.is_segment_directive():
                    self.sections.append(Section.from_lines(cur.lines))
                    cur = Section()
                cur.append(line)
            self.sections.append(cur)
            #print(self)
        else:
            logging.error("\n".join(line.content for line in self._lines))
            raise ValueError("Unknown assembler")

    def add_lines(self, lines: t.List[t.Union[Line, str]]):
        """
        Add the passed assembly lines.

        :param lines: either list of Lines or strings
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

        :param small_changes: only make small random changes
        """
        if len(self.sections) == 0:
            return
        is_gcc = any(line.startswith(".cfi") for line in self._lines)
        _sections = self.sections[is_gcc:]
        if small_changes:
            i = 0
            while i < len(_sections) - 1:
                if random.randrange(0, 2) == 0:
                    tmp = _sections[i]
                    _sections[i] = _sections[i]
                    _sections[i + 1] = tmp
                i += 2
        else:
            random.shuffle(_sections)
        pre = self.sections[0]
        post = self.sections[-1]
        self.sections = [pre] + _sections + [post]
        #random.shuffle(self.sections)

    def randomize_sub_segments(self, segment_name: str):
        """
        Randomize the segments of the given name.

        :param segment_name: segment name, e.g. "bss", "data" or "rodata"
        """
        for section in self.sections:
            section.randomize_segment(segment_name)

    def randomize_malloc_calls(self, padding: range):
        """
        Randomizes the `[c|m]alloc` and `new` method calls (and thereby the heap)
        by adding the given padding to each malloc call.

        :param padding: given range of bytes to pad
        """
        for section in self.sections:
            section.randomize_malloc_calls(padding)

    def __str__(self):
        if len(self.sections) > 0:
            return "\n/****/\n".join(map(str, self.sections)) + "\n"
        return "\n".join(line.content for line in self._lines)

    @classmethod
    def from_file(cls, file: str):
        """
        Create an assembly file object from the contents of a file.

        :param file: name of the parsed file
        :return: created assembly file object
        """
        with open(file, "r") as f:
            return AssemblyFile([line.rstrip() for line in f.readlines()])

    def to_file(self, file: str):
        """
        Store the textual representation of this assembly file object into a file.

        :param file: name of the destination file
        """
        with open(file, "w") as f:
            f.write(str(self))


class AssemblyProcessor:
    """
    Fassade for the AssemblyFile class that processes a configuration dictionary.
    """

    config_scheme = Dict({         # type: Dict
        "heap": NaturalNumber() // Default(0)
                // Description("0: don't randomize, > 0 randomize with paddings in range(0, x)"),
        "bss": Bool() // Default(False)
                // Description("Randomize the bss sub segments?"),
        "data": Bool() // Default(False)
                // Description("Randomize the data sub segments?"),
        "rodata": Bool() // Default(False)
                // Description("Randomize the rodata sub segments?"),
        "file_structure": Bool() // Default(False)
                          // Description("Randomize the file structure.")
    }, all_keys=False)
    """ Configuration type scheme that also contains the default values and descriptions of its properties """

    def __init__(self, config: t.Dict[str, t.Union[int, bool]]):
        """
        Creates an AssemblyProcessor from the passed configuration dictionary.

        :param config: passed configuration dictionary
        """
        self.config = self.config_scheme.get_default()  # type: t.Dict[str, t.Union[int, bool]]
        self.config.update(config)
        typecheck(self.config, self.config_scheme)

    def process(self, file: str, small_changes: bool = False):
        """
        Processes the passed assembly file according to its configuration and stores the randomized file contents back.

        :param file: name of the passed file
        :param small_changes: don't randomize the file structure fully
        """
        if not any(self.config[x] for x in ["file_structure", "heap", "bss", "data", "rodata"]):
            return
        assm = AssemblyFile.from_file(file)
        if self.config["file_structure"]:
            assm.randomize_file_structure(small_changes)
        if self.config["heap"] > 0:
            assm.randomize_malloc_calls(padding=range(0, self.config["heap"]))
        if self.config["bss"]:
            assm.randomize_sub_segments("bss")
        if self.config["data"]:
            assm.randomize_sub_segments("data")
        if self.config["rodata"]:
            assm.randomize_sub_segments("rodata")
        assm.to_file(file)


def process_assembler(call: t.List[str]):
    """
    Process the passed `as` wrapper arguments and randomize the assembly file.
    This function is called directly by the `as` wrapper.

    :param call: arguments passed to the `as` wrapper (call[0] is the name of the wrapper itself)
    """
    input_file = os.path.abspath(call[-1])
    config = json.loads(os.environ["RANDOMIZATION"]) if "RANDOMIZATION" in os.environ else {}
    as_tool = config["used_as"] if "used_as" in config else "/usr/bin/as"
    #tmp_assm_file = os.path.join(os.environ["TMP_DIR"] if "TMP_DIR" in os.environ else "/tmp", "temci_assembler.s")
    input_file_content = ""
    with open(input_file, "r") as f:
        input_file_content = f.read()  # keep the original assembler some where...

    def exec(cmd):
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            return str(err)
        return None

    def store_original_assm():
        with open(input_file, "w") as f:
            f.write(input_file_content)

    processor = AssemblyProcessor(config)
    call[0] = as_tool
    for i in range(0, 2):
        res = processor.process(input_file)
        ret = exec(" ".join(call))
        if ret is None:
            return
        store_original_assm()
    for i in range(0, 6):
        processor.process(input_file, small_changes=True)
        ret = exec(" ".join(call))
        if ret is None:
            return
        store_original_assm()
        #else:
        #    logging.info("Another try")
    if processor.config["file_structure"]:
        logging.warning("Disabled file structure randomization")
        config["file_structure"] = False
        for i in range(0, 6):
            processor = AssemblyProcessor(config)
            processor.process(input_file)
            ret = exec(" ".join(call))
            if ret is None:
                return
            logging.info("Another try")
            store_original_assm()
    ret = exec(" ".join(call))
    if ret is not None:
        logging.error(ret)
        exit(1)


if __name__ == "__main__":

    def test(assm: AssemblyFile):
        tmp_file = "/tmp/test.s"
        assm.to_file(tmp_file)
        os.system("gcc {} -o /tmp/test && /tmp/test".format(tmp_file))

    print(Line("	.section	.text.unlikely\n", 1).is_segment_directive())
    #exit(0)
    #assm = AssemblyFile.from_file("/home/parttimenerd/Documents/Studium/Bachelorarbeit/test/hello2/hello.s")
    assm = AssemblyFile.from_file("/tmp/hello.s")
    #test(assm)
    #assm.randomize_malloc_calls(padding=range(1, 1000))
    #test(assm)
    #assm.randomize_file_structure()
    test(assm)
    #print("till randomize")
    #test(assm)
    #for x in  ["bss", "data", "rodata"]:
    #    assm.randomize_sub_segments(x)
    #    test(assm)
