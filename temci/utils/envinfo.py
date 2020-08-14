import enum
import functools
import subprocess
import typing as t

from temci.utils import util


class Unit(enum.Enum):

    HZ = "Hz"
    IB = "ib"
    NORMAL = ""

    def format(self, val: int, fmt: str = "{:.3f}") -> str:
        pval = val * 1.0
        exponents = 0
        incr = 1024 if "i" in self.value else 1000
        while pval >= incr:
            pval /= incr
            exponents += 1

        return fmt.format(pval) + ["", "k", "M", "G", "T", "P"][exponents] + self.suffix()

    def suffix(self) -> str:
        return {self.IB: "iB", self.HZ: "Hz", self.NORMAL: ""}[self]


def format_nt(nt: t.NamedTuple, **units: Unit) -> t.List[t.Tuple[str, str]]:
    """
    Format the passed named tuple, some of its properties might have
    associated units
    """
    ret = []
    for i, f in enumerate(nt._fields):
        val = nt[i]
        if f in units:
            val = units[f].format(val)
        ret.append([f, str(val)])
    return ret


class CpuInfo(t.NamedTuple):

    cpu: str
    cores: int
    threads: int

    @staticmethod
    @functools.lru_cache(1)
    def create() -> 'CpuInfo':
        import multiprocessing
        if util.on_apple_os():

            def sysctl(key: str) -> str:
                return subprocess.check_output("/usr/sbin/sysctl -n {}".format(key), shell=True).strip()

            return CpuInfo(sysctl("machdep.cpu.brand_string"), int(sysctl("hw.physicalcpu")),
                           multiprocessing.cpu_count())
        else:
            physical_ids = []
            cpu = ""
            for line in open("/proc/cpuinfo").readlines():
                # based on https://github.com/qznc/dot/blob/master/bin/sysinfo
                if ":" not in line:
                    continue
                k, v = line.split(":")
                k = k.strip()
                if k == "physical id":
                    physical_ids.append(int(v.strip()))
                if k == "model name":
                    cpu = v.strip()
        return CpuInfo(cpu, len(physical_ids), multiprocessing.cpu_count())

    def format(self) -> t.List[t.Tuple[str, str]]:
        return format_nt(self, max_frequency=Unit.HZ)


class MemoryInfo(t.NamedTuple):

    total: int
    available: int

    @staticmethod
    @functools.lru_cache(1)
    def create() -> 'MemoryInfo':
        import psutil
        mem = psutil.virtual_memory()
        return MemoryInfo(mem.total, mem.available)

    def format(self) -> t.List[t.Tuple[str, str]]:
        return format_nt(self, total=Unit.IB, available=Unit.IB)


class OSInfo(t.NamedTuple):

    name: str
    release: str

    @staticmethod
    @functools.lru_cache(1)
    def create() -> 'OSInfo':
        import platform
        return OSInfo(platform.system(), platform.release())

    def format(self) -> t.List[t.Tuple[str, str]]:
        return format_nt(self)


FORMATTED_ENV_INFO = t.List[t.Tuple[str, t.List[t.Tuple[str, str]]]]


def format_env_info() -> FORMATTED_ENV_INFO:
    """ Returns the formatted environment info, per chapter (CPU, memory, …) """
    return [["Operating system", OSInfo.create().format()],
            ["CPU", CpuInfo.create().format()],
            ["Memory", MemoryInfo.create().format()]]
