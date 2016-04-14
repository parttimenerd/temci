import typing as t

from temci.utils.settings import Settings
from temci.utils.typecheck import *
import base64
import hashlib
import os

HOME_DIR = os.path.expanduser("~")  # type: str
""" Home directory of the current user """


def hashed_name_of_file(filename: str, block_size: int = 2**20) -> str:
    """
    Generates a unique filename for a file from its hashed (using sha512 and md5) content.
    :param filename: name of the file
    :param block_size: number of bytes that are read at once
    :return: unique filename for the file based on its content
    """
    def bytes_to_filename(bytes: bytes) -> str:
        return base64.b64encode(bytes).decode().replace("/", "_")[:-2]

    md5 = hashlib.md5()
    sha512 = hashlib.sha512()
    with open(filename , "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            md5.update(data)
            sha512.update(data)
    return bytes_to_filename(sha512.digest()) + bytes_to_filename(md5.digest())


def abspath(path: str) -> str:
    """
    Returns the absolute path and can work with "~".
    """
    return os.path.abspath(os.path.expanduser(path))


def normalize_path(path: str) -> str:
    """
    Returns the absolute version of the passed path and replaces the home directory with "~".
    """
    path = abspath(path)
    if path.startswith(HOME_DIR):
        path = path.replace(HOME_DIR, "~", 1)
    return path
