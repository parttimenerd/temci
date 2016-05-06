try:
    import yaml
except ImportError:
    import pureyaml as yaml
from ..utils.typecheck import *
from ..utils.settings import Settings
from .builder import Builder, BuilderKeyboardInterrupt
import typing as t


class BuildProcessor:
    """
    Build programs with possible randomizations.
    """

    block_scheme = Dict({     # type: Dict
        "attributes": Dict(all_keys=False, key_type=Str())
            // Description("Attributes of the program block"),
        "run_config": Dict(all_keys=False) // Description("Run configuration for this program block"),
        "build_config": Dict({
            "build_cmd": Str() // Default("") // Description("Command to build this program block"),
            "number": (PositiveInt() | NonExistent()) // Default(1)
                      // Description("Number of times to build this program"),
            "randomization": (Dict(key_type=Str(), value_type=Int()|Bool()) | NonExistent())
                             // Default({})
                // Description("Randomization configuration"),
            "working_dir": (DirName() | NonExistent()) // Default(".")
                // Description("Working directory in which the build command is run"),
            "revision": (Str() | Int() | NonExistent()) // Default(-1)
                // Description("Used version control system revision of the program (-1 is the current revision)"),
            "branch": (Str() | NonExistent()) // Default("")
                // Description("Used version control system branch (default is the current branch)"),
            "base_dir": (DirName() | NonExistent()) // Default(".")
                // Description("Base directory that contains everything to build an run the program")
        }) // Description("Build configuration for this program block")
    })
    """ Type scheme of the program block configurations """

    def __init__(self, build_blocks: t.Optional[t.List[t.Dict[str, t.Any]]] = None):
        """
        Creates a build processor for the passed build block configurations.

        :param build_blocks: passed build block configurations
        """
        if build_blocks is None:
            typecheck(Settings()["build/in"], ValidYamlFileName())
            with open(Settings()["build/in"], "r") as f:
                build_blocks = yaml.load(f)
        typecheck(build_blocks, List(self.block_scheme))
        self.build_blocks = [self.block_scheme.get_default() for _ in range(len(build_blocks))]
        """
        Build block configurations.
        type: t.Optional[t.List[t.Dict[str, t.Any]]]
        """
        for i, block in enumerate(build_blocks):
            for key in block.keys():
                self.build_blocks[i][key].update(block[key])
            typecheck(self.build_blocks[i], self.block_scheme, "build block {}".format(i))
        typecheck(Settings()["build/out"], FileName())
        typecheck_locals(build_blocks=List())
        self.out = Settings()["build/out"]  # type. str
        """ Temporary directory in which the building takes place """

    def build(self):
        """
        Build the configured programs.
        """
        run_blocks = []
        try:
            for block in self.build_blocks:
                error = None
                try:
                    block_builder = Builder(block["build_config"]["working_dir"],
                                            block["build_config"]["build_cmd"], block["build_config"]["revision"],
                                            block["build_config"]["number"], block["build_config"]["randomization"],
                                            block["build_config"]["base_dir"], block["build_config"]["branch"])
                    working_dirs = block_builder.build()
                except BuilderKeyboardInterrupt as err:
                    working_dirs = err.result
                    error = err.error
                block["run_config"]["cwd"] = working_dirs
                run_blocks.append({
                    "attributes": block["attributes"],
                    "run_config": block["run_config"]
                })

                if error:
                    raise error
        except KeyboardInterrupt as err:
            with open(self.out, "w") as f:
                yaml.dump(run_blocks, f)
            raise err
        with open(self.out, "w") as f:
            yaml.dump(run_blocks, f)
