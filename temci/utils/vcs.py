import os, shutil, errno, subprocess, tarfile
from .settings import Settings
from os.path import abspath
from temci.utils.typecheck import *
import typing as t

class VCSDriver:
    """
    Abstract version control system driver class used to support different vcss.
    """

    id_type = Str()|Int()

    def __init__(self, dir: str = ".", branch: str = None):
        """
        Initializes the VCS driver for a given base directory.
        It also sets the current branch if it's defined in the Settings

        :param dir: base directory
        :param branch: used branch
        """
        typecheck_locals(dir=Str(), branch=Optional(Str()))
        self._exec_command_cache = {}
        self._exec_err_code_cache = {}
        self.dir = os.path.abspath(dir)  # type: str
        """ Base directory """
        self.branch = branch or self.get_branch()  # type: str
        """ Used branch """

    @classmethod
    def get_suited_vcs(cls, mode="auto", dir=".", branch: str = None) -> 'VCSDriver':
        """
        Chose the best suited vcs driver for the passed base directory and the passed mode.
        If mode is "auto" the best suited vcs driver is chosen. If mode is "git" or "file",
        the GitDriver or the FileDriver is chosen. If the chosen driver isn't applicable than
        a VCSError is raised.

        :param mode: passed mode
        :param dir: base directory
        :param branch: used branch
        :return: vcs driver for the base directory
        :raises: VCSError if the selected driver isn't applicable
        """
        typecheck_locals(mode=ExactEither("file", "git", "auto"), dir=Str(), branch=Optional(Str()))
        if mode is "file" and FileDriver.is_suited_for_dir(dir):
            return FileDriver(dir, branch)
        elif mode is "git" and GitDriver.is_suited_for_dir(dir):
            return GitDriver(dir, branch)
        elif mode is "auto" and FileDriver.is_suited_for_dir(dir):
            avcls = [cls for cls in [GitDriver, FileDriver] if cls.is_suited_for_dir(dir)]
            return avcls[0](dir, branch)
        else:
            raise NoSuchVCSError("No such vcs driver for mode {0} and directory {1}".format(mode, dir))

    @classmethod
    def is_suited_for_dir(cls, dir: str = ".") -> bool:
        """
        Checks whether or not this vcs driver can work with the passed base directory.

        :param dir: passed base directory path
        """
        raise NotImplementedError()

    def set_branch(self, new_branch: str):
        """
        Sets the current branch and throws an error if the branch doesn't exist.

        :param new_branch: new branch to set
        :raises: VCSError if new_branch doesn't exist
        """
        raise NotImplementedError()

    def get_branch(self) -> t.Optional[str]:
        """
        Gets the current branch.

        :return: current branch name
        :raises: VCSError if something goes terribly wrong
        """
        raise None

    def get_valid_branches(self) -> t.Optional[t.List[str]]:
        """
        Gets the valid branches for the associated repository or None if the vcs doesn't support branches.
        """
        return None

    def has_uncommitted(self) -> bool:
        """
        Check for uncommitted changes in the repository.
        """
        raise NotImplementedError()

    def number_of_revisions(self) -> int:
        """
        Number of committed revisions in the current branch (if branches are supported).
        :return: number of revisions
        """
        raise NotImplementedError()

    def validate_revision(self, id_or_num: t.Union[int, str]) -> bool:
        """
        Validate the existence of the referenced revision.

        :param id_or_num: id or number of the reverenced revision
        :return: does it exists?
        """
        raise NotImplementedError()

    def get_info_for_revision(self, id_or_num: t.Union[int, str]) -> dict:
        """
        Get an info dict for the given commit (-1 and 'HEAD' represent the uncommitted changes).
        Structure of the info dict::

            "commit_id"; …,
            "commit_message": …,
            "commit_number": …,
            "is_uncommitted": True/False,
            "is_from_other_branch": True/False,
            "branch": … # branch name or empty string if this commit belongs to no branch

        :param id_or_num: id or number of the commit
        :return: info dict
        :raises: VCSError if the number or id isn't valid
        """
        raise NotImplementedError()

    def get_info_for_all_revisions(self, max: int = -1) -> t.List[t.Dict[str, t.Any]]:
        """
        Get an info dict for all revisions.
        A single info dict has the following structure::

            "commit_id"; …,
            "commit_message": …,
            "commit_number": …,
            "is_uncommitted": True/False,
            "is_from_other_branch": True/False,
            "branch": … # branch name or empty string if this commit belongs to no branch

        :param max: if max isn't -1 it gives the maximum number of revision infos returned
        :return: list of info dicts
        """
        info_dicts = []
        if self.has_uncommitted() and (max >= 1 or max == -1):
            info_dicts.append(self.get_info_for_revision(-1))
            if max != -1:
                max -= 1
        num = self.number_of_revisions()
        if max != -1 and max < num:
            num = max
        for i in range(num):
            info_dicts.append(self.get_info_for_revision(i))

        return info_dicts


    def copy_revision(self, id_or_num: t.Union[int, str], sub_dir: str, dest_dirs: t.List[str]):
        """
        Copy the sub directory of the current vcs base directory into all of the destination directories.

        :param id_or_num: id or number of the revision (-1 and 'HEAD' represent the uncommitted changes)
        :param sub_dir: sub directory of the current vcs base directory relative to it
        :param dest_dirs: list of destination directories in which the content of the sub dir is placed or dest dir string
        :raises: VCSError if something goes wrong while copying the directories
        """
        raise NotImplementedError()

    def _copy_dir(self, src_dir: str, dest_dirs: t.List[str]):
        """
        Helper method to copy a directory to many destination directories.
        It also works if for files.

        :param src_dir: source directory relative to the current base directory
        :param dest_dirs: list of destination directories or just one destination directory string
        """
        typecheck_locals(src_dir=Str(), dest_dirs=List(Str())|Str())
        src_dir_path = os.path.abspath(os.path.join(self.dir, src_dir))
        dest_dir_paths = []
        if type(dest_dirs) is str:
            dest_dir_paths = [os.path.abspath(dest_dirs)]
        else:
            dest_dir_paths = [os.path.abspath(dest) for dest in dest_dirs]
        for dest in dest_dir_paths:
            try:
                shutil.rmtree(dest)
                shutil.copytree(src_dir_path, dest)
            except OSError as exc:
                try:
                    if exc.errno == errno.ENOTDIR:
                        shutil.copy(src_dir_path, dest)
                    else:
                        raise
                except OSError as exc2:
                    raise VCSError(str(exc2))

    def _exec_command(self, command: str, error: str = "Error executing {cmd}: {err}", cacheable: bool = False):
        """
        Executes the given external command and returns the resulting output.

        :param command: given external command, list or string (uses /bin/sh)
        :param error: error message with can have a placeholder `cmd` for the command and `èrr` for stderr
        :param cacheable: can the result of the command be cached to reduce the number of needed calls?
        :return: output as string
        :raises: VCSError if the external command hasn't exit code 0
        """
        typecheck_locals(command=List()|Str(), error=Str(), cacheable=Bool())
        args = command
        if isinstance(command, Str()):
            args = ["/bin/sh", "-c", command]

        args_str = "#~#".join(args)
        if cacheable and args_str in self._exec_command_cache:
            return self._exec_command_cache[args_str]
        proc = subprocess.Popen(args, cwd=abspath(self.dir), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            msg = error.format(cmd=command, err=err)
            raise VCSError(msg)

        if cacheable:
            self._exec_command_cache[args_str] = str(out)

        return str(out)

    def _exec_err_code(self, command: str, cacheable: bool = False):
        """
        Executes the given external command and returns its error code.

        :param command: given external command (as string or list)
        :param cacheable: can the result of the command be cached to reduce the number of needed calls?
        :return: error code of the command (or 0 if no error occurred)
        """
        typecheck_locals(command=List(Str())|Str(), cacheable=Bool())
        args = []
        if isinstance(command, list):
            args = command
        else:
            args = ["/bin/sh", "-c", command]

        args_str = "#~#".join(args)
        if cacheable and args_str in self._exec_err_code_cache:
            return self._exec_err_code_cache[args_str]

        proc = subprocess.Popen(args, cwd=abspath(self.dir), universal_newlines=True,
                                stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        out, err = proc.communicate()

        err_code = proc.poll()

        if cacheable:
            self._exec_err_code_cache[args_str] = err_code

        return err_code

class FileDriver(VCSDriver):
    """
    The default driver, that works with plain old files and directories without any vcs.
    Therefore its also usable with every directory.
    It has only one revision: Number -1 or 'HEAD', the current directory content.

    This class is also a simple example implementation of a VCSDriver.
    """

    @classmethod
    def is_suited_for_dir(cls, dir: str = "."):
        typecheck_locals(dir=Str())
        return os.path.exists(dir) and os.path.isdir(dir)

    def set_branch(self, new_branch: str):
        typecheck_locals(new_branch=Optional(Str()))
        if new_branch is None:
            return
        raise VCSError("No branch support in FileDriver")

    def get_branch(self) -> t.Optional[str]:
        return None

    def has_uncommitted(self) -> bool:
        return True

    def number_of_revisions(self) -> int:
        return 0

    def validate_revision(self, id_or_num: t.Union[int, str]) -> bool:
        return id_or_num == -1 or id_or_num == 'HEAD'

    def get_info_for_revision(self, id_or_num: t.Union[int, str]) -> dict:
        typecheck_locals(id_or_num=self.id_type)
        if not self.validate_revision(id_or_num):
            raise NoSuchRevision(id_or_num)
        return {
            "commit_id": "",
            "commit_message": "",
            "commit_number": -1,
            "is_uncommitted": True,
            "is_from_other_branch": False,
            "branch": ""
        }

    def copy_revision(self, id_or_num: t.Union[int, str], sub_dir: str, dest_dirs: t.List[str]):
        typecheck_locals(id_or_num=self.id_type, dest_dirs=List(Str())|Str())
        if not self.validate_revision(id_or_num):
            raise NoSuchRevision(id_or_num)
        self._copy_dir(sub_dir, dest_dirs)


class GitDriver(VCSDriver):
    """
    The driver for git repositories.
    """

    def __init__(self, dir: str = ".", branch: str = None):
        super().__init__(dir, branch)
        self.base_path = self._get_git_base_dir(dir)

    @classmethod
    def is_suited_for_dir(cls, dir: str = ".") -> bool:
        typecheck_locals(dir=Str())
        return cls._get_git_base_dir(dir) is not None

    @classmethod
    def _get_git_base_dir(cls, dir: str = ".") -> str:
        path = os.path.abspath(dir).split("/")
        if path[-1] == "":
            path = path[0:-1]
        for i in reversed(range(1, len(path) - 1)):
            sub_path = path[0:i]
            if os.path.isdir(os.path.join("/", os.path.join(*sub_path),  ".git")):
                return os.path.join(*path[i:])
        return None

    def get_branch(self) -> t.Optional[str]:
        if self.branch is not None:
            return self.branch
        return self._exec_command("git rev-parse --abbrev-ref HEAD",
                                  error="Can't get current branch. Somethings wrong with the repository: {err}").strip()

    def set_branch(self, new_branch: str):
        typecheck_locals(new_branch=Str())
        if new_branch is self.get_branch():
            return
        out = self._exec_command("git branch --list".format(new_branch), cacheable=True)
        if new_branch not in out:
            raise VCSError("No such branch {}".format(new_branch))
        self.branch = new_branch

    def get_valid_branches(self) -> t.Optional[t.List[str]]:
        res = self._exec_command("git branch --list", cacheable=True).split(" ")
        branches = []
        for line in res:
            line = line.split("\n")[0].strip()
            if line != "":
                branches.append(line)
        return branches

    def has_uncommitted(self) -> bool:
        return self._exec_err_code("git diff --cached --quiet", cacheable=True) == 1

    def _list_of_commit_tuples(self) -> t.List[t.Tuple[str, str]]:
        """
        Executes `git log BRANCH` and parses it's output lines into tuples (hash, msg).
        :return: list of tuples
        """
        res = self._exec_command("git log --oneline {}".format(self.branch), cacheable=True).split("\n")
        list = []
        for line in res:
            if len(line.strip()) > 0:
                list.append(line.strip().split(" ", 1))
        return list

    def number_of_revisions(self) -> str:
        return len(self._list_of_commit_tuples())

    def _commit_number_to_id(self, num: int) -> str:
        """
        Returns a commit id for the given commit number and normalizes passed commit ids.

        :param num: commit number
        :return: commit id (string)
        :raises: VCSError if the commit number isn't valid
        """
        typecheck_locals(num=self.id_type)
        if not isinstance(num, int):
            return self._normalize_commit_id(num)
        if num >= self.number_of_revisions() or num < -1:
            raise VCSError("{} isn't a valid commit number (they are counted from 0).".format(num))
        cid, __ = self._list_of_commit_tuples()[num]
        return cid

    def _normalize_commit_id(self, id: str) -> str:
        """
        Normalizes the given commit id.
        :return: normalized commit id
        :raises: VCSError if something goes wrong
        """
        out = self._exec_command("git show {} | head -n 1".format(id), cacheable=True).strip()
        return out.split(" ")[1]

    def validate_revision(self, id_or_num: t.Union[int, str]) -> bool:
        typecheck_locals(id_or_num=self.id_type)
        if id_or_num is -1 or id_or_num == "HEAD":
            return self.has_uncommitted()
        if isinstance(id_or_num, int) and id_or_num < -1:
            return False
        try:
            cid = self._commit_number_to_id(id_or_num)
            return self._exec_err_code("git show {} | head -n 1".format(cid), cacheable=True) == 0
        except VCSError:
            return False

    def _get_branch_for_revision(self, id_or_num: t.Union[int, str]) -> str:
        if id_or_num == -1 or id_or_num == "HEAD":
            return self.get_branch()
        id = self._commit_number_to_id(id_or_num)
        out = self._exec_command("git branch --contains {}".format(id), cacheable=True)
        out = out.split("\n")[0].strip()
        return out.split(" ")[-1]

    def get_info_for_revision(self, id_or_num: t.Union[int, str]) -> dict:
        typecheck_locals(id_or_num=self.id_type)
        if id_or_num == -1 or id_or_num == "HEAD":
            return {
                "commit_id": "HEAD",
                "commit_message": "Uncommitted changes",
                "commit_number": -1,
                "is_uncommitted": True,
                "is_from_other_branch": False,
                "branch": self._get_branch_for_revision(id_or_num)
            }
        cid = self._commit_number_to_id(id_or_num)
        line = self._exec_command("git show {} --oneline | head -n 1".format(cid), cacheable=True).strip()
        cid, msg = line.split(" ", 1)
        branch = self._get_branch_for_revision(id_or_num)
        cid = self._normalize_commit_id(cid)
        other_branch = True
        commit_number = -2
        tuples = self._list_of_commit_tuples()
        for i in range(0, len(tuples)):
            if self._normalize_commit_id(tuples[i][0]) == cid:
                commit_number = i
                other_branch = False
                break
        return {
            "commit_id": cid,
            "commit_message": msg.strip(),
            "commit_number": commit_number,
            "is_uncommitted": False,
            "is_from_other_branch": other_branch,
            "branch": branch
        }

    def copy_revision(self, id_or_num: t.Union[int, str], sub_dir: str, dest_dirs: t.List[str]):
        typecheck_locals(id_or_num=self.id_type, dest_dirs=List(Str())|Str())
        if isinstance(dest_dirs, str):
            dest_dirs = [dest_dirs]
        if id_or_num == -1 or id_or_num == "HEAD":
            self._copy_dir(sub_dir, dest_dirs)
        sub_dir = os.path.join(self.base_path, sub_dir)
        tar_file = os.path.abspath(os.path.join(Settings()["tmp_dir"], "tmp.tar"))
        cmd = "git archive --format tar --output {} {}".format(tar_file, self._commit_number_to_id(id_or_num))
        self._exec_command(cmd)
        try:
            with tarfile.open(tar_file) as tar:
                for dest in dest_dirs:
                    if sub_dir == ".":
                        tar.extractall(os.path.abspath(dest))
                    else:
                        subdir_and_files = [
                                tarinfo for tarinfo in tar.getmembers() if tarinfo.name.startswith(sub_dir + "/") or tarinfo.name is sub_dir
                            ]
                        tar.extractall(members=subdir_and_files, path=os.path.abspath(dest))
        except tarfile.TarError as err:
            os.remove(tar_file)
            raise VCSError(str(err))
        os.remove(tar_file)


class VCSError(EnvironmentError):
    """ Base error for the errors that occur during vcs handling """
    pass


class NoSuchVCSError(VCSError):
    """ Thrown if there isn't a vcs with the specific name """
    pass


class NoSuchRevision(VCSError):
    """ Thrown if a specific revision doesn't exist """
    pass