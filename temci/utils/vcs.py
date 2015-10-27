import os, shutil, errno, shlex, subprocess, logging, tarfile
from .settings import Settings
from os.path import abspath

class VCSDriver:
    """
    Abstract version control system driver class used to support different vcss.
    """

    dir = "."
    branch = None

    def __init__(self, dir="."):
        """
        Initializes the VCS driver for a given base directory.
        It also sets the current branch if it's defined in the Settings
        :param dir: base directory
        """
        self.settings = Settings()
        self.dir = os.path.abspath(dir)
        self.branch = self.get_branch()
        if self.branch is not None and self.settings.get("branch", default=self.get_branch()) is not self.branch:
            self.set_branch(Settings().get("branch"))

    @staticmethod
    def get_suited_vcs(mode="auto", dir="."):
        """
        Chose the best suited vcs driver for the passed base directory and the passed mode.
        If mode is "auto" the best suited vcs driver is chosen. If mode is "git" or "file",
        the GitDriver or the FileDriver is chosen. If the chosen driver isn't applicable than
        a VCSError is raised.
        :param mode: passed mode
        :param dir: base directory
        :return: vcs driver for the base directory
        :raises VCSError if the selected driver isn't applicable
        """
        if mode is "file" and FileDriver.is_suited_for_dir(dir):
            return FileDriver(dir)
        elif mode is "git" and GitDriver.is_suited_for_dir(dir):
            return GitDriver(dir)
        elif mode is "auto" and FileDriver.is_suited_for_dir(dir):
            avcls = [cls for cls in [GitDriver, FileDriver] if cls.is_suited_for_dir(dir)]
            return avcls[0](dir)
        else:
            raise NoSuchVCSError("No such vcs driver for mode {0} and directory {1}".format(mode, dir))

    @staticmethod
    def is_suited_for_dir(dir="."):
        """
        Checks whether or not this vcs driver can work with the passed base directory.
        :param dir: passed base directory path
        """
        raise NotImplementedError()

    def set_branch(self, new_branch):
        """
        Sets the current branch and throws an error if the branch doesn't exist.
        :param new_branch: new branch to set
        :raises VCSError if new_branch doesn't exist
        """
        raise NotImplementedError()

    def get_branch(self):
        """
        Gets the current branch.
        :return: current branch name
        :raises VCSError if something goes terribly wrong
        """
        raise NotImplementedError()

    def has_uncommitted(self):
        """
        Check for uncommitted changes in the repository.
        :return:
        """
        raise NotImplementedError()

    def number_of_revisions(self):
        """
        Number of commited revisions in the current branch (if branches are supported).
        :return number of revisions
        """
        raise NotImplementedError()

    def validate_revision(self, id_or_num):
        """
        Validate the existence of the referenced revision.
        :param id_or_num: id or number of the reverenced revision
        :return: does it exists?
        """
        raise NotImplementedError()

    def get_info_for_revision(self, id_or_num):
        """
        Get an info dict for the given commit (-1 represent the unstaged changes).
        Structure of the info dict:
        ```
        "commit_id"; …,
        "commit_message": …,
        "commit_number": …,
        "is_unstaged": True/False
        ```
        :param id_or_num: id or number of the commit
        :return info dict
        """
        raise NotImplementedError()

    def copy_revision(self, id_or_num, sub_dir, dest_dirs):
        """
        Copy the sub directory of the current vcs base directory into all of the destination directories.
        :param id_or_num: id or number of the revision (-1 represent the unstaged changes)
        :param sub_dir: sub directory of the current vcs base directory relative to it
        :param dest_dirs: list of destination directories in which the content of the sub dir is placed or dest dir string
        :raises VCSError if something goes wrong while copying the directories
        """
        raise NotImplementedError()

    def _copy_dir(self, src_dir, dest_dirs):
        """
        Helper method to copy a directory to many destination directories.
        It also works if for files.
        :param src_dir: source directory relative to the current base directory
        :param dest_dirs: list of destination directories or just one destination directory string
        """
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
                    else: raise
                except OSError as exc2:
                    raise VCSError(str(exc2))

    def _exec_command(self, command, error="Error executing {cmd}: {err}"):
        """
        Executes the given external command and returns the resulting output.
        :param command: given external command (as string or list)
        :param error: error message with can have a placeholder `cmd` for the command and `èrr` for stderr
        :return output as string
        :raises VCSError if the external command hasn't exit code 0
        """
        args = []
        if type(command) is list:
            args = command
        else:
            args = shlex.split(command)
        proc = subprocess.Popen(args, cwd=abspath(self.dir), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            msg = error.format(cmd=command, err=err)
            raise VCSError(msg)
        return str(out)

class FileDriver(VCSDriver):
    """
    The default driver, that works with plain old files and directories without any vcs.
    Therefore its also usable with every directory.
    It has only one revision: Number -1, the current directory content.

    This class is also a simple example implementation of a VCSDriver.
    """

    @staticmethod
    def is_suited_for_dir(dir="."):
        return os.path.exists(dir) and os.path.isdir(dir)

    def set_branch(self, new_branch):
        if new_branch is None:
            return
        raise VCSError("No branch support in FileDriver")

    def get_branch(self):
        return None

    def has_uncommitted(self):
        return True

    def number_of_revisions(self):
        return 0

    def validate_revision(self, id_or_num):
        return id_or_num == -1

    def get_info_for_revision(self, id_or_num):
        if not self.validate_revision(id_or_num):
            raise NoSuchRevision(id_or_num)
        return {
            "commit_id": "",
            "commit_message": "",
            "commit_number": -1,
            "is_unstaged": True,
            "from_other_branch": False
        }

    def copy_revision(self, id_or_num, sub_dir, dest_dirs):
        if not self.validate_revision(id_or_num):
            raise NoSuchRevision(id_or_num)
        self._copy_dir(sub_dir, dest_dirs)

class GitDriver(VCSDriver):
    """
    The driver for git repositories.
    """

    @staticmethod
    def is_suited_for_dir(dir="."):
        return os.path.exists(os.path.join(dir, ".git"))

    def get_branch(self):
        if self.branch is not None:
            return self.branch
        return self._exec_command(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                  error="Can't get current branch. Somethings wrong with the repository: {err}").strip()

    def set_branch(self, new_branch):
        if new_branch is self.get_branch():
            return
        out = self._exec_command("git branch --list".format(new_branch))
        if new_branch not in out:
            raise VCSError("No such branch {}".format(new_branch))
        self.branch = new_branch

    def has_uncommitted(self):
        return subprocess.call(shlex.split("git diff --cached --quiet"), cwd=abspath(self.dir)) == 1

    def _list_of_commit_tuples(self):
        """
        Executes `git log BRANCH` and parses it's output lines into tuples (hash, msg).
        :return list of tuples
        """
        res = self._exec_command("git log --oneline {}".format(self.branch)).split("\n")
        list = []
        for line in res:
            if len(line.strip()) > 0:
                list.append(line.strip().split(" ", 1))
        return list

    def number_of_revisions(self):
        return len(self._list_of_commit_tuples())

    def _commit_number_to_id(self, num):
        """
        Returns a commit id for the given commit number and normalizes passed commit ids.
        :param num: commit number
        :return commit id (string)
        :raises VCSError if the commit number isn't valid
        """
        if type(num) is not int:
            return self._normalize_commit_id(num)
        if num >= self.number_of_revisions() or num < -1:
            raise VCSError("{} isn't a valid commit number (they are counted from 0).".format(num))
        cid, __ = self._list_of_commit_tuples()[num]
        return cid

    def _normalize_commit_id(self, id):
        """
        Normalizes the given commit id.
        :return normalized commit id
        :raises VCSError if something goes wrong
        """
        out = self._exec_command("git show {}".format(id))
        out = out.split("\n")[0].strip()
        return out.split(" ")[1]


    def validate_revision(self, id_or_num):
        if id_or_num is -1:
            return self.has_uncommitted()
        if id_or_num < -1:
            return False
        try:
            cid = self._commit_number_to_id(id_or_num)
            return subprocess.call(shlex.split("git show {}".format(cid)), cwd=abspath(dir)) == 0
        except VCSError:
            return False

    def get_info_for_revision(self, id_or_num):
        if id_or_num == -1:
            return {
                "commit_id": "",
                "commit_message": "[Uncommited]",
                "commit_number": -1,
                "is_unstaged": True,
                "from_other_branch": False
            }
        cid = self._commit_number_to_id(id_or_num)
        lines = self._exec_command("git show {} --oneline".format(cid)).split("\n")
        lines = [line.strip() for line in lines]
        cid, msg = lines[0].split(" ", 1)
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
            "commit_message": msg,
            "commit_number": commit_number,
            "is_unstaged": False,
            "from_other_branch": other_branch
        }

    def copy_revision(self, id_or_num, sub_dir, dest_dirs):
        if type(dest_dirs) is str:
            dest_dirs = [dest_dirs]
        if id_or_num == -1:
            self._copy_dir(sub_dir, dest_dirs)
        tar_file = os.path.abspath(os.path.join(self.settings["tmp_dir"], "tmp.tar"))
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
    """
    Error for everything that goes fataly wrong with vcs handling.
    """
    pass

class NoSuchVCSError(VCSError):
    pass

class NoSuchRevision(VCSError):
    pass