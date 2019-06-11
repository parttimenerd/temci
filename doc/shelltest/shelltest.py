import os
import subprocess
import sys
import tempfile

from docutils.parsers.rst import directives
from sphinx.directives import CodeBlock


import unittest


def do_run_tests() -> bool:
    return os.getenv("SHELLTEST", "0") == "1"


tests = unittest.TestSuite() if do_run_tests() else None


class CodeBlockTestCase(unittest.TestCase):

    def __init__(self, code: str, cmd: str, name: str = None, out_reg: str = None, err_code: str = 0, err_reg: str = None, **kwargs):
        super().__init__("test")
        self.code = code
        self.cmd = cmd if len(cmd.strip()) > 0 else "$CMD"
        self.output_regexp = out_reg
        self.err_regexp = err_reg
        self.err_code = err_code if err_code is not None else 0
        self.is_file = "$FILE" in cmd
        self._testMethodDoc = "Test " + (name or self.cmd).replace("$CMD", code)
        self._cleanups = False

    def test(self) -> unittest.TestCase:
        with tempfile.TemporaryDirectory() as d:
            with tempfile.TemporaryFile("w") as f:
                f.write(self.code)
                cmd = self.cmd.replace("$FILE", f.name) if self.is_file else self.cmd.replace("$CMD", self.code)
                proc = subprocess.Popen(["/bin/sh", "-c", cmd],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        cwd=str(d),
                                        env={"LC_ALL": "C"},
                                        universal_newlines=True)
                out, err = proc.communicate()
                msg = "Output: {}; Error output: {}".format(out, err)
                if self.err_code != -1:
                    self.assertEqual(self.err_code, proc.returncode % 127, "Error code, " + msg)
                if self.output_regexp is not None:
                    self.assertRegex(str(out), self.output_regexp, "Output")
                if self.err_regexp:
                    self.assertRegex(str(err), self.err_regexp, "Error output")

    def __str__(self):
        return self._testMethodDoc


class TestedCodeBlock(CodeBlock):

    test_options = {
        "cmd": None,
        "test": None,
        "out_reg": None,
        "err_reg": None,
        "err_code": None
    }

    option_spec = dict(**{k:directives.unchanged for k in test_options}, **CodeBlock.option_spec)

    CodeBlock.option_spec = option_spec

    already_added = set()

    def run(self):
        opts = self.test_options.copy()
        opts.update(self.options)
        opts["cmd"] = opts["test"] if opts["cmd"] is None else opts["cmd"]
        opts["code"] = "\n".join(self.content)
        if do_run_tests() and opts["cmd"] is not None and repr(opts) not in self.already_added:
            tests.addTest(CodeBlockTestCase(**opts))
            self.already_added.add(repr(opts))
        return super().run()


def run_tests():
    if do_run_tests():
        unittest.TextTestRunner(verbosity=2).run(tests)


def setup(app):
    app.add_directive("code", TestedCodeBlock)
    app.connect("build-finished", lambda *k: run_tests())
    return {
        'version': "0.1",
        'parallel_read_safe': False,
        'parallel_write_safe': False
    }