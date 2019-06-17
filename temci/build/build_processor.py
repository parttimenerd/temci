from temci.utils.util import get_doc_for_type_scheme, sphinx_doc, document

try:
    import yaml
except ImportError:
    import pureyaml as yaml
from ..utils.typecheck import *
from ..utils.settings import Settings
from .builder import Builder, BuilderKeyboardInterrupt
import typing as t


@document(block_scheme="A block in the configuration has the following format:")
class BuildProcessor:
    """
    Build programs with possible randomizations.
    """

    block_scheme = Dict({     # type: Dict
        "attributes": Dict(unknown_keys=True, key_type=Str())
            // Description("Attributes of the program block"),
        "run_config": Dict(unknown_keys=True) // Description("Run configuration for this program block"),
        "build_config": Dict({
            "cmd": Str() // Default("") // Description("Command to build this program block"),
            "number": (PositiveInt() | NonExistent()) // Default(1)
                      // Description("Number of times to build this program"),
            "randomization": Builder.rand_conf_scheme // Default({})
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
                build_blocks = yaml.safe_load(f)
        self.build_blocks = self.preprocess_build_blocks(build_blocks)
        typecheck(Settings()["build/out"], FileName())
        typecheck_locals(build_blocks=List())
        self.out = Settings()["build/out"]  # type. str
        """ Temporary directory in which the building takes place """

    @classmethod
    def preprocess_build_blocks(cls, blocks: t.List[t.Dict[str, t.Any]]) -> t.List[t.Dict[str, t.Any]]:
        """
        Pre process and check build blocks

        :return: pre processed copy
        """
        typecheck(blocks, List(cls.block_scheme))
        build_blocks = [cls.block_scheme.get_default() for _ in range(len(blocks))]
        """
        Build block configurations.
        type: t.Optional[t.List[t.Dict[str, t.Any]]]
        """
        for i, block in enumerate(blocks):
            for key in block.keys():
                build_blocks[i][key].update(block[key])
            typecheck(build_blocks[i], cls.block_scheme, "build block {}".format(i))
        return build_blocks

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
                                            block["build_config"]["cmd"], block["build_config"]["revision"],
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
