import curses
import os
import sys
import threading
import time
from typing import Callable, List


class Screen:
    """
    A simple curses based screen to build a watch like behavior for temci exec
    """

    def __init__(self, scroll: bool = False, keep_first_lines: int = 0, print_buffer_on_exit: bool = True):
        """
        :param keep_first_lines: keep the first n lines on the screen fixed when scrolling
        """
        self.scr = curses.initscr()
        curses.noecho()
        try:
            curses.cbreak()
        except:
            pass
        curses.curs_set(0)
        self.scr.keypad(True)
        self.current_line = 0
        self.buffer = [""]  # type: List[str]
        self._shown_buffer = [""]  # type: List[str]
        self.keep_first_lines = keep_first_lines
        self.x = 0
        self.y = self.keep_first_lines
        self.print_buffer_on_exit = print_buffer_on_exit
        self.enabled = True
        if scroll:
            t = threading.Thread(target=self._create_scroll_thread())
            t.setDaemon(True)
            t.start()

    def _create_scroll_thread(self) -> Callable:
        def func():
            while True:
                c = self.scr.getch()
                curses.flushinp()
                updated = True
                if c == curses.KEY_LEFT:
                    self._move_cursor(x_offset=-1)
                elif c == curses.KEY_RIGHT:
                    self._move_cursor(x_offset=1)
                elif c == curses.KEY_UP or c == curses.KEY_SR:
                    self._move_cursor(y_offset=-1)
                elif c == curses.KEY_DOWN or c == curses.KEY_SF:
                    self._move_cursor(y_offset=1)
                else:
                    updated = False
                if updated:
                    self._flush2()
                time.sleep(0.05)
        return func

    def __enter__(self):
        return self

    def _copy_over(self):
        self._shown_buffer = self.buffer

    def reset(self):
        """
        Clear the current screen recording (does not change the displayed screen)
        """
        self.current_line = 0
        self.buffer = [""]

    def isatty(self):
        """ Only required for click """
        return True

    def write(self, text: str):
       if not self.enabled:
           pass
       text = text.replace("\n", "\r\n")
       for line in text.splitlines(keepends=True):
           first = True
           for part in line[0:len(line) - (1 if line.endswith("\n") else 0)].split("\r"):
              self._write_single_line(part, -1 if first else 0)
              first = False
           if line.endswith("\n"):
               self.advance_line()

    def _write_single_line(self, text: str, y: int = -1):
        """ -1: end of line """
        assert "\r" not in text and "\r" not in text
        if y == -1:
            self.buffer[self.current_line] += text
        else:
            cur = self.buffer[self.current_line]
            self.buffer[self.current_line] = cur[0:y] + text + cur[len(text)+y:]

    def advance_line(self):
        self.current_line += 1
        self.buffer.append("")

    def flush(self):
        pass

    def display(self):
        """
        Replace the current screen with the recorded. Call reset() if you don't want to add to this screen.
        """
        self._copy_over()
        self._flush2()


    def _flush2(self):
        """ Refreshes the screen """
        max_y, max_x = self.scr.getmaxyx()
        for y in range(0, min(max_y, self.keep_first_lines, len(self._shown_buffer))):
            self.scr.addstr(0, y, self._shown_buffer[y][0:max_x].replace("\\[", ""))
        end = max(0, min(len(self._shown_buffer) - 1, max_y - self.keep_first_lines + self.y))
        for y in range(self.y, end):
            self.scr.addstr(y + self.keep_first_lines - self.y, 0, " " * max_x)
            self.scr.addstr(y + self.keep_first_lines - self.y, 0,
                            self._shown_buffer[y][self.x:min(len(self._shown_buffer[y]) - self.x, max_x) + self.x])
        for y in range(end + self.keep_first_lines - self.y, max_y):
            try:
                self.scr.addstr(y, 0, " " * max_x)
            except:
                pass
        self.scr.refresh()

    def _move_cursor(self, x_offset: int = 0, y_offset: int = 0):
        self.x = max(0, self.x + x_offset)
        self.y = max(self.keep_first_lines, self.y + y_offset)

    def writelines(self, lines: List[str]):
        for line in lines:
            self.write(line)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            curses.nocbreak()
            self.scr.keypad(False)
            curses.echo()
            curses.endwin()
            os.system('stty sane')
        except BaseException as ex:
            pass
        if self.print_buffer_on_exit:
            sys.stdout.writelines([s + "\n" for s in self._shown_buffer])

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
