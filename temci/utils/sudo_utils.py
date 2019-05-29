import os
import sys
from io import TextIOWrapper, BufferedRandom, BufferedRWPair, BufferedWriter, IOBase
from pwd import getpwnam
from typing import Union, Tuple, Dict

from temci.utils.settings import Settings


def get_bench_user() -> str:
    user = Settings()["env"]["USER"]
    return os.getenv("USER", get_bench_user()) if user == "" else user


def bench_as_different_user() -> bool:
    return get_bench_user() != os.getenv("USER", get_bench_user())


def get_bench_uid_and_gid() -> Tuple[int, int]:
    pwnam = getpwnam(get_bench_user())
    return pwnam.pw_uid, pwnam.pw_gid


def chown(path: Union[str, TextIOWrapper, BufferedRandom, BufferedRWPair, BufferedWriter, IOBase]):
    if isinstance(path, IOBase) and path.isatty():
        return
    if not isinstance(path, str):
        return chown(path.name)
    try:
        os.chown(path, *get_bench_uid_and_gid())
    except FileNotFoundError:
        pass


def get_env_setting() -> Dict[str, str]:
    env = Settings()["env"].copy()
    if env["USER"] == "":
        env["USER"] = get_bench_user()
    if env["PATH"] == "":
        env["PATH"] = os.getenv("PATH", "")
    return env


if __name__ == '__main__':
    chown(sys.stdin)