"""
This module contains the model classes that build up the tree like model data structure.
It's (mostly) independent from any other project module (except utils.util) for the sake of
easier testing and cleaner design.

The main idea behind this is that this data model is a serializable representation of all data
that has to be transfered between the the three main program parts (env setup, stat and report).

The implementation is a testbed for the (relatively) new type annotation feature of python
and some custom type checking. Hopefully this will provide a less error prone implementation
of a central data structure of this project.
"""

import os

import yaml


def expect(data: dict, key: str, exp_type: type = None, data_name: str = None) -> None:
    """
    Simple helper method that throws an StructureError if the passed dictionary hasn't the passed key
    or if the dictionaries value at this key hasn't the expected type.
    The type parameter is ignored if it's None.

    :param data: passed dictionary
    :param key: passed key
    :param exp_type: expected type or None if the type isn't important
    :param data_name: name of the passed dictionary that makes the error message better understandable
    :raises StructureError if something isn't the way it should be
    """
    data_name = str(data_name) if data_name is not None else "The passed data object"

    if not isinstance(data, dict):
        raise StructureError("{} isn't of type dict but of type {}".format(data_name, type(data)))
    if key not in data.keys():
        raise StructureError("{} has no key {} it was expected".format(data_name, key))
    if exp_type is not None and not isinstance(data[key], exp_type):
        raise StructureError("{} has a key {}, but the associated value is of type {}, "
                             "not of type {} as expected".format(data_name, key, type(data[key]), exp_type))


def expect_t(data: dict, type_tuples: dict = None, data_name: str = None) -> None:
    """
    Works the same as the expect function, but checks more than one (expected key, expected type) tuple.
    It checks for each tuple whether the passed dictionary has the expected key that is associated
    with the a value of the expected type. The type is isn't checked if the expected type is None .

    :param data: passed dictionary
    :param type_tuples: the key-value-pairs represent the list of (key name, type) tuples.
    :param data_name: name of the passed dictionary that makes the error message better understandable
    :raises StructureError if something isn't the way it should be
    """
    if isinstance(type_tuples, None):
        return
    for key in type_tuples.keys():
        expect(data, key, exp_type=type_tuples[key], data_name=data_name)


class StructureError(ValueError):
    pass


class MainModel(object):
    """
    This is the main model. It consists of RevisionModels and has some helper methods
    to work with the model tree, like storing the model into and retrieving from the
    `info.yaml` file.
    """

    def __init__(self, working_dir: str, revisions: list = None):
        """
        Initializes the main model by providing the working directory in which the whole
        model operates and it's child models.
        :param working_dir: working directory
        :param revisions: child revision models
        """
        if revisions is None:
            revisions = []
        self.working_dir = working_dir
        """The current working directory for the model, e.g. the Settings()['tmp_file']."""
        self.revisions = revisions
        """List of the revision models of this main model"""

    @classmethod
    def load_from_file(cls, file: str) -> MainModel:
        """
        Loads the main model from the passed (yaml) file.
        The format is defined in the models module documentation.

        :param file: name (and path) of the file
        :return new main model
        :rtype MainModel
        :raises FileExistsError if the passed file doesn't exist
        """
        if not os.path.exists(file):
            raise FileExistsError(file)
        with open(file, 'r') as stream:
            data = yaml.load(stream)
            cls.load_from_dict(data)

    @classmethod
    def load_from_dict(cls, data: dict) -> MainModel:
        """
        Loads the main model from the passed dictionary.
        It has the following structure (with types instead of values)::

            "working_dir": str,
            "revisions": list # ... of dictionaries representing revisions

        :param data: passed dictionary
        :type data: dict
        :return new main model
        :rtype MainModel
        :raises StructureError if the passed dictionary hasn't the expected structure
        """
        expect_t(data, {"working_dir": str, "revisions": list}, "main model data structure")
        working_dir = data["working_dir"]
        revisions = [RevisionModel.load_from_dict(rev) for rev in data["revisions"]]
        return MainModel(working_dir, revisions)

    def store_into_file(self, file: str):
        """
        Stores this main model into the given file as in the yaml format.

        :param file: name of the given file
        :raises FileExistsError if the passed file doesn't exist
        """
        if not os.path.exists(file):
            raise FileExistsError(file)
        with open(file, 'w') as stream:
            data = self.to_dict()
            yaml.dump(data, stream)

    def to_dict(self) -> dict:
        """
        Converts this main model into a dictionary structure.
        """
        data = {
            "working_dir": self.working_dir,
            "revisions": [rev.to_dict() for rev in self.revisions]
        }
        return data

class RevisionModel(object):
    """
    The instances of this class represent models of the revisions.
    They contain the associated BuildModels and allow (de)serialization into
    dictionaries.
    """

    def __init__(self, info: dict, build_cmds: list = None):
        """
        Constructs a new RevisionModel that represents the revision with
        the given characteristics and has the passed BuildCmdModels as child models
        The info dictionary has the following structure::

            "commit_id"; …,
            "commit_message": …,
            "commit_number": …,
            "is_unstaged": True/False,
            "from_other_branch": True/False,
            "branch": str

        :param info: given characteristics
        :param build_cmds: child BuildCmdModels
        :raises StructureError if the info dictionary is malformed
        """
        if build_cmds is None:
            build_cmds = []
        expect_t(info, {"commit_id": int,
                        "commit_message": str,
                        "commit_number": int,
                        "is_unstaged": None,
                        "from_other_branch": None,
                        "branch": str}, "Revision info")
        self.id = str(info["commit_id"])
        """Id of the represented commit or "" if this model represents uncommitted changes"""
        self.message = str(info["commit_message"])
        """Message of the represented commit."""
        self.commit_number = int(info["commit_number"])
        """Number of the represented commit. -1 for uncommitted revision. -2 for revision from other branch."""
        self.is_uncommitted = bool(info["is_uncommitted"])
        """Does this revision represent uncommitted changes?"""
        self.is_from_other_branch = bool(info["is_from_other_branch"])
        """Is this revision from another branch (not the selected main branch)?"""
        self.branch = info["branch"]
        """Branch that this revision belongs to."""
        self.build_cmds = build_cmds
        """List of child BuildCmdModels"""

    @classmethod
    def load_from_dict(cls, data: dict) -> RevisionModel:
        """
        Loads a revision model from the given data structure.
        It has the following structure::

            "info": dict # see the constructor for detailed information
            "build_cmds": list # of dicts representing BuildCmdModels

        :param data: given data structure
        :return new revision model
        :rtype RevisionModel
        :raises StructureError if the passed dictionary hasn't the expected structure
        """
        expect_t(data, {"info": dict, "build_cmds": list}, "revision data structure")
        build_cmds = [BuildCmdModel.load_from_dict(d) for d in data["build_cmds"]]
        return RevisionModel(data["info"], build_cmds)

    def to_dict(self) -> dict:
        """
        Converts this model into a dictionary structure.
        :return dictionary structure
        """
        data = {
            "info": {
                "commit_id": self.id,
                "commit_message": self.message,
                "commit_number": self.commit_number,
                "is_uncommitted": self.is_uncommitted,
                "is_from_other_branch": self.is_from_other_branch,
                "branch": self.branch
            },
            "build_cmds": [cmd.to_dict() for cmd in self.build_cmds]
        }
        return data


class BuildCmdModel(object):
    """
    Represents a (revision, build command) tuple.
    """

    def __init__(self, cmd: str, build_dir: str, binary_dir: str,
                 binary_number: int = 0, run_cmds: Optional[list] = None):
        """
        Initializes a model representing a (revision, build command) tuple.
        :param cmd: actual build command
        :param build_dir: directory in which the building of the binaries takes place
        :param binary_dir: directory which contains everything to run the binaries
        :param binary_number: number of binary folders associated with this tuple
        :param run_cmds: list of associated RunCmdModels, if there are any
        """
        self.cmd = cmd
        """Actual build command"""
        self.build_dir = build_dir
        """Build directory in which the building of the binaries takes place"""
        self.binary_dir = binary_dir
        """Binary directory which contains everything to run the binaries"""
        self.binary_number = binary_number
        """Number of binary folders associated with this (revision, build cmd) tuple"""
        self.run_cmds = run_cmds if run_cmds is not None else []
        """list of associated RunCmdModels, if there are any"""

    @classmethod
    def load_from_dict(cls, data: dict) -> BuildCmdModel:
        """
        Loads a BuildCmdModel from the given data structure.
        It has the following structure::

            "cmd": str,
            "build_dir": str,
            "binary_dir": str,
            "binary_number": int,
            "run_cmds": list # of RunCmdModels, ommitted if there aren't any

        :param data: given data structure
        :return new BuildCmdModel
        :rtype BuildCmdModel
        :raises StructureError if the passed dictionary hasn't the expected structure
        """
        data_name = "(revision, build_cmd) tuple (aka BuildCmdModel) data structure"
        expect_t(data, {
            "cmd": str,
            "build_dir": str,
            "binary_dir": str,
            "binary_number": int
            }, data_name=data_name)
        run_cmds = []
        if "run_cmds" in data.keys():
            expect(data, key="run_cmds", exp_type=list, data_name=data_name)
            run_cmds = [RunCmdModel.load_from_dict(m) for m in data["run_cmds"]]

        return BuildCmdModel(data["cmd"], data["build_dir"], data["binary_dir"],
                             data["binary_number"], run_cmds)

    def to_dict(self) -> dict:
        """
        Converts this model into a dictionary structure.
        :return dictionary structure
        """
        data = {
            "cmd": self.cmd,
            "build_dir": self.build_dir,
            "binary_dir": self.binary_dir,
            "binary_number": self.binary_number
        }
        if self.has_run_cmds():
            data["run_cmds"] = [cmd.to_dict() for cmd in self.run_cmds]
        return data

    def has_run_cmds(self) -> bool:
        """
        Checks whether or not this model has associated RunCmdModels.
        """
        return len(self.run_cmds) > 0


class RunCmdModel(object):

    def __init__(self, cmd: string, run_data: RunDataModel = None):
        self.cmd = cmd
        self.run_data = run_data

    @classmethod
    def load_from_dict(cls, data: dict) -> RunCmdModel:
        """
        Loads a RunCmdModel from the given data structure.
        It has the following structure::

            "cmd": str,
            "run_data": dict # representing a RunDataModel, optional

        :param data: given data structure
        :return new RunCmdModel
        :rtype RunCmdModel
        :raises StructureError if the passed dictionary hasn't the expected structure
        """
        expect(data, "cmd", str, data_name="Run cmd data structure")
        model = None
        if "run_data" in data:
            expect(data, "run_data", dict, data_name="Run cmd data structure")
            model = RunDataModel.load_from_dict(data["run_data"])
        return RunCmdModel(data["cmd"], model)

    def to_dict(self) -> dict:
        """
        Converts this model into a dictionary structure.
        :return dictionary structure
        """
        data = {
            "cmd": self.cmd
        }
        if self.has_run_data():
            data["run_data"] = self.run_data.to_dict()
        return data

    def has_run_data(self):
        return isinstance(self.run_data, RunDataModel)

    def add_data_item(self, item: dict):
        if not self.has_run_data():
            self.run_data = RunDataModel(item.keys(), [item])
        else:
            self.run_data.add_data_item(item)


class RunDataModel(object):
    """
    Represents the raw data of the benchmarking runs for a single
    (revision, build command, run command) tuple.
    """

    def __init__(self, properties: iterable, data: list = None):
        self.properties = properties
        if len(self.properties) == 0:
            raise ValueError("A run data model without measurement properties doesn't make sense")
        if isinstance(data, None):
            self.data = []
        else:
            for item in data:
                self.add_data_item(item)
        pass

    @classmethod
    def load_from_dict(cls, data: dict) -> RunDataModel:
        """
        Loads a RunDataModel from the given data structure.
        It has the following structure::

            "properties": list # property this that each single benchmarking run data contains
            "data": [
                {"PROPERTY1": int|float, …}
                …
            ]

        :param data: given data structure
        :return new RunDataModel
        :rtype RunDataModel
        :raises StructureError if the passed dictionary hasn't the expected structure
        """
        expect_t(data, {"properties": list, "data": dict}, "Run data structure")
        if not all(type(item) is string for item in data["properties"]):
            raise StructureError("Expected properties list of strings in a run data structure")
        return RunDataModel(data["properties"], data["data"])

    def to_dict(self) -> dict:
        """
        Converts this model into a dictionary structure.
        :return dictionary structure
        """
        return {
            "properties": self.properties,
            "data": self.data
        }

    def is_empty(self) -> bool:
        return len(self.data) == 0

    def add_data_item(self, data_item: dict):
        if not isinstance(data_item, dict):
            raise StructureError("Expected data item of type dict, but got one of type {}".format(type(data_item)))
        if len(data_item) == 0:
            raise StructureError("Expected data item with at least one measurement property")
        if len(data_item) < len(self.properties):
            raise StructureError("Expected data item with {} properties, "
                                 "but got one with {}".format(len(self.properties), len(data_item)))
        new_item = {}
        for prop in self.properties:
            if prop not in data_item:
                raise StructureError("Expected data item with property {}".format(prop))
            if type(data_item[key]) not in [float, int]:
                raise StructureError("Expected data item with values of type float or int, "
                                     "but got property {} with value type {}".format(prop, type(data_item[prop])))
            new_item[key] = float(data_item[key])
        self.data.append(new_item)