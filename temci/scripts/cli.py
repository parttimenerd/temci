import locale

from temci.utils.util import sphinx_doc, get_doc_for_type_scheme

import warnings

from temci.scripts.temci_completion import completion_file_name, create_completion_dir
from temci.utils import util
if __name__ == "__main__":
    util.allow_all_imports = True

warnings.simplefilter("ignore")
import shutil
import subprocess

import time

import humanfriendly

if util.can_import("init"):
    from temci.scripts.init import prompt_run_config, prompt_build_config
from temci.utils.typecheck import *

from temci.run.run_processor import RunProcessor
from temci.build.assembly import AssemblyProcessor, process_assembler
from temci.build.build_processor import BuildProcessor
import temci.run.run_driver as run_driver
import temci.run.run_driver_plugin
from temci.report.report import ReporterRegistry
from temci.utils.settings import Settings
from temci.report.report_processor import ReportProcessor
import temci.report.report
import temci.report.testers
import click, sys, logging, json, os
try:
    import yaml
except ImportError:
    import pureyaml as yaml
from temci.utils.click_helper import type_scheme_option, cmd_option, CmdOption, CmdOptionList, document_func
import temci.scripts.version

Settings().load_files()

@click.group(epilog="""
temci (version {})  Copyright (C) 2016 Johannes Bechberger

This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions.
For details, see the LICENSE file in the source folder of temci.

This program is still in an alpha stage. It may happen that
you're system needs to be rebooted to be usable again.
""".format(temci.scripts.version.version))
def cli():
    pass


command_docs = {
    "assembler": "Wrapper around the gnu assembler to allow assembler randomization",
    "build": "Build program blocks",
    "report": "Generate a report from benchmarking result",
    "init": "Helper commands to initialize files (like settings)",
    "completion": "Creates completion files for several shells.",
    "short": "Utility commands to ease working directly on the command line",
    "clean": "Clean up the temporary files",
    "setup": "Compile all needed binaries in the temci scripts folder",
    "version": "Print the current version ({})".format(temci.scripts.version.version),
    "run_package": "Execute a package and create a package that can be executed afterwards to reverse most changes",
    "exec_package": "Execute a package"
}
for driver in run_driver.RunDriverRegistry.registry:
    command_docs[driver] = run_driver.RunDriverRegistry.registry[driver].__description__.strip().split("\n")[0]

common_options = CmdOptionList(
    CmdOption.from_non_plugin_settings("")
)

run_options = {
    "common": CmdOptionList(
        CmdOption.from_non_plugin_settings("run"),
        CmdOption.from_non_plugin_settings("stats", name_prefix="stats_")
    ),
    "run_driver_specific": {  # besides DRIVER_misc and plugins
        "exec": CmdOptionList()
    }
}

# init the run_options dictionary
for driver in run_driver.RunDriverRegistry.registry:
    options = CmdOptionList(
        CmdOption.from_registry(run_driver.RunDriverRegistry.registry[driver]),
        CmdOption.from_non_plugin_settings("run/{}_misc".format(driver)),
        CmdOption.from_non_plugin_settings("run/cpuset", name_prefix="cpuset_"),
        run_options["common"]
    )
    if driver not in run_options["run_driver_specific"]:
        run_options["run_driver_specific"][driver] = options
    else:
        run_options["run_driver_specific"][driver].append(options)


report_options = CmdOptionList(
    CmdOption.from_non_plugin_settings("report"),
    CmdOption.from_non_plugin_settings("stats")
)
# init the report_options dictionary
for reporter in ReporterRegistry.registry:
    options = CmdOption.from_non_plugin_settings("report/{}_misc".format(reporter), name_prefix=reporter + "_")
    report_options.append(options)

build_options = CmdOptionList(
    CmdOption.from_non_plugin_settings("build")
)

package_options = CmdOption.from_non_plugin_settings("package")

misc_commands = {
    "init": {
        "common": CmdOptionList(),
        "sub_commands": {
            "settings": CmdOptionList(),
            "build_config": CmdOptionList(),
            "run_config": CmdOptionList()
        }
    },
    "completion": {
        "common": CmdOptionList(),
        "sub_commands": {
            "bash": CmdOptionList(),
            #"fish": CmdOptionList(),
            "zsh": CmdOptionList()
        }
    },
    "short": {
        "common": CmdOptionList(),
        "sub_commands": {
            "exec": CmdOptionList(CmdOption("with_description",
                                    type_scheme=ListOrTuple(Tuple(Str(), Str()))
                                                // Description("DESCRIPTION COMMAND: Benchmark the command and set its"
                                                               " description attribute."),
                                    short="d", completion_hints={"zsh": "_command"}),
                          CmdOption("without_description", short="wd",
                                    type_scheme=ListOrTuple(Str()) // Description("COMMAND: Benchmark the command and use "
                                                                           "itself as its description."),
                                    completion_hints={"zsh": "_command"}),
                          run_options["run_driver_specific"]["exec"],
                          run_options["common"]
                          )
        }
    },
    "clean": CmdOptionList()
}
misc_commands_description = {
    "completion": {
        "zsh": "Creates a new tab completion file for zsh and returns it's file name",
        #"fish": "Creates a file /tmp/temci_fish_completion for fish completion support.",
        "bash": "Creates a new tab completion file for zsh and returns it's file name",
    },
    "init": {
        "settings": "Create a new settings file temci.yaml in the current directory",
        "build_config": "Interactive cli to create (or append to) a build config file",
        "run_config": "Interactive cli to create (or append to) a run config file"
    },
    "short": {
        "exec": "Exec code snippets directly with the exec run driver"
    }
}


# Register a command for each run driver
for driver in run_driver.RunDriverRegistry.registry:
    _options = CmdOptionList(common_options, run_options["common"], run_options["run_driver_specific"][driver])

    @cli.command(name=driver, short_help=command_docs[driver])
    @click.argument("run_file")
    @cmd_option(_options)
    def _func(*args, **kwargs):
        globals()["temci__" + driver](*args, **kwargs)

    def _func2(run_file, **kwargs):
        Settings()["run/driver"] = driver
        Settings()["run/in"] = run_file
        try:
            RunProcessor().benchmark()
        except KeyboardInterrupt:
            logging.error("KeyboardInterrupt. Cleaned up everything.")
    _func2.__name__ = "temci__" + driver
    document_func(command_docs[driver], _options, argument="configuration YAML file")(_func2)
    globals()["temci__" + driver] = _func2



def temci__short():
    pass
temci__short.__doc__ = command_docs["short"]


@cli.group(short_help=command_docs["short"])
@cmd_option(common_options)
def short(**kwargs):
    pass


@short.command(short_help=misc_commands_description["short"]["exec"])
@cmd_option(common_options)
@cmd_option(misc_commands["short"]["sub_commands"]["exec"])
@cmd_option(run_options["run_driver_specific"]["exec"])
def exec(**kwargs):
    temci__short__exec(**kwargs)


@document_func(misc_commands_description["short"]["exec"], common_options,
               misc_commands["short"]["sub_commands"]["exec"],
               run_options["run_driver_specific"]["exec"])
def temci__short__exec(with_description: list = None, without_description: list = None, **kwargs):
    runs = []
    if with_description is not None:
        for (descr, cmd) in with_description:
            runs.append({
                "run_config": {
                    "run_cmd": [cmd]
                },
                "attributes": {
                    "description": descr
                }
            })
    if without_description is not None:
        for cmd in without_description:
            runs.append({"run_config": {
                    "run_cmd": [cmd]
                },
                "attributes": {
                    "description": cmd
                }
            })
    Settings()["run/driver"] = "exec"
    try:
        RunProcessor(runs).benchmark()
    except KeyboardInterrupt:
        logging.error("KeyboardInterrupt. Cleaned up everything.")


@cli.command(short_help=command_docs["report"])
@click.argument('report_file', type=click.Path(exists=True))
@cmd_option(common_options)
@cmd_option(report_options)
def report(*args, **kwargs):
    temci__report(*args, **kwargs)


@document_func(command_docs["report"], common_options, report_options)
def temci__report(report_file: str, **kwargs):
    Settings()["report/in"] = report_file
    ReportProcessor().report()


@cli.group(short_help=command_docs["init"])
@cmd_option(misc_commands["init"]["common"])
@cmd_option(common_options)
def init(**kwargs):
    pass


def temci__init():
    pass
temci__init.__doc__ = short_help=command_docs["init"]


@init.command(short_help=misc_commands_description["init"]["settings"])
@cmd_option(misc_commands["init"]["sub_commands"]["settings"])
@cmd_option(common_options)
def settings(**kwargs):
    temci__init__settings(**kwargs)


@document_func(misc_commands_description["init"]["settings"],
               misc_commands["init"]["sub_commands"]["settings"],
               common_options)
def temci__init__settings(**kwargs):
    Settings().store_into_file("temci.yaml")


@init.command(short_help=misc_commands_description["init"]["build_config"])
@cmd_option(misc_commands["init"]["sub_commands"]["build_config"])
@cmd_option(common_options)
def build_config(**kwargs):
    temci__init__build_config(**kwargs)


@document_func(misc_commands_description["init"]["build_config"],
               misc_commands["init"]["sub_commands"]["build_config"],
               common_options)
def temci__init__build_config(**kwargs):
    prompt_build_config()


@init.command(short_help=misc_commands_description["init"]["run_config"])
@cmd_option(misc_commands["init"]["sub_commands"]["run_config"])
@cmd_option(common_options)
def run_config(**kwargs):
    prompt_run_config()


@document_func(misc_commands_description["init"]["run_config"],
               misc_commands["init"]["sub_commands"]["run_config"],
               common_options)
def temci__init__run_config(**kwargs):
    prompt_run_config()


@cli.command(short_help=command_docs["build"])
@click.argument('build_file', type=click.Path(exists=True))
@cmd_option(CmdOptionList(common_options, build_options))
def build(build_file: str, **kwargs):
    temci__build(build_file, **kwargs)


@document_func(command_docs["build"], common_options, build_options, argument="build configuration YAML file")
def temci__build(build_file: str, **kwargs):
    try:
        Settings()["build/in"] = build_file
        BuildProcessor().build()
    except KeyboardInterrupt:
        logging.error("Aborted")
    except BaseException as err:
        print(err)
        logging.error(str(err))


@cli.command(short_help=command_docs["clean"])
@cmd_option(common_options)
def clean(**kwargs):
    temci__clean(**kwargs)


@document_func(command_docs["clean"], common_options)
def temci__clean(**kwargs):
    shutil.rmtree(Settings()["tmp_dir"])


@cli.command(short_help=command_docs["version"])
@cmd_option(common_options)
def version(**kwargs):
    print(temci.scripts.version.version)


@document_func(command_docs["version"], common_options)
def temci__version(**kwargs):
    print(temci.scripts.version.version)


@cli.command(short_help=command_docs["run_package"])
@click.argument('package', type=click.Path(exists=True))
@cmd_option(common_options)
@cmd_option(package_options)
def run_package(package: str, **kwargs):
    temci__run_package(package)


@document_func(command_docs["run_package"], common_options, package_options,
               argument="Used temci package")
def temci__run_package(package: str):
    from temci.package.dsl import run
    run(package)


@cli.command(short_help=command_docs["exec_package"])
@click.argument('package', type=click.Path(exists=True))
@cmd_option(common_options)
@cmd_option(package_options)
def run_package(package: str, **kwargs):
    temci__exec_package(package)


@document_func(command_docs["exec_package"], common_options, package_options,
               argument="Used temci package")
def temci__exec_package(package: str):
    from temci.package.dsl import execute
    execute(package)



def temci__completion():
    pass
temci__completion.__doc__ = command_docs["completion"]


@cli.group(short_help=command_docs["completion"])
@cmd_option(common_options)
def completion(**kwargs):
    pass


@completion.command(short_help=misc_commands_description["completion"]["zsh"])
@cmd_option(common_options)
def zsh(**kwargs):
    temci__completion__zsh()


@document_func(misc_commands_description["completion"]["zsh"], common_options)
def temci__completion__zsh():
    subcommands = "\n\t".join(['"{}:{}"'.format(cmd, command_docs[cmd])
                               for cmd in sorted(command_docs.keys())])

    def process_options(options: CmdOptionList, one_line=False):
        typecheck(options, CmdOptionList)
        strs = []
        for option in sorted(options):
            multiple = isinstance(option.type_scheme, List) or isinstance(option.type_scheme, ListOrTuple)
            rounds = 10 if multiple else 1 # hack to allow multiple applications of an option
            assert isinstance(option, CmdOption)
            descr = "{}".format(option.description) if option.description is not None else "Undoc"
            option_str = "--{}".format(option.option_name)
            if option.has_short:
                option_str = "{{-{},--{}}}".format(option.short, option.option_name)
            if option.is_flag:
                option_str = "{{--{o},--no-{o}}}".format(o=option.option_name)
            new_completion = ""
            if option.has_completion_hints and "zsh" in option.completion_hints:
                new_completion = '{option_str}\"[{descr}]: :{hint}"'.format(
                    option_str=option_str, descr=descr, hint=option.completion_hints["zsh"]
                )
            else:
                format_str = '{option_str}\"[{descr}]"' if option.is_flag else '{option_str}\"[{descr}]: :()"'
                new_completion = format_str.format(
                    option_str=option_str, descr=descr
                )
            for i in range(rounds):
                strs.append(new_completion)

        if one_line:
            return " ".join(strs)
        return "\n\t".join(strs)

    misc_cmds_wo_subcmds = list(filter(lambda x: isinstance(misc_commands[x], CmdOptionList), misc_commands.keys()))
    misc_cmds_w_subcmds = list(filter(lambda x: isinstance(misc_commands[x], dict), misc_commands.keys()))

    ret_str = """
# Auto generated tab completion for the temci ({version}) benchmarking tool.


#compdef temci
_temci(){{
    # printf '%s ' "${{words[@]}}" > /tmp/out
    local ret=11 state

    local -a common_opts
    common_opts=(
        {common_opts}
    )

    typeset -A opt_args
    _arguments   -C  ':subcommand:->subcommand' '2: :->second_level' '*::options:->options' && ret=0
    #echo $state > tmp_file

    local sub_cmd=""
    case $words[1] in
        temci)
            sub_cmd=$words[2]
            ;;
        *)
            sub_cmd=$words[1]
    esac

    #echo $words[@] >> tmp_file

    case $words[2] in
        ({misc_cmds_wo_subs})
            state="options"
            ;;
    esac


    case $state in
    subcommand)
        local -a subcommands
        subcommands=(
            {subcommands}
        )

        _describe -t subcommands 'temci subcommand' subcommands && ret=0
    ;;
    """.format(common_opts=process_options(common_options),
               subcommands=" ".join("\"{}:{}\"".format(cmd, command_docs[cmd]) for cmd in command_docs),
               misc_cmds_wo_subs="|".join(misc_cmds_wo_subcmds),
               version=temci.scripts.version.version)
    ret_str += """
    second_level)

        #echo $words[@] > tmp_file
        case $words[2] in
    """
    for misc_cmd in misc_cmds_w_subcmds:
        ret_str += """
            ({misc_cmd})
                #echo "here" > tmp_file
                local -a subcommands
                subcommands=(
                    {sub_cmds}
                )
                _describe -t subcommands 'temci subcommand' subcommands && ret=0 && return 0
                ;;
        """.format(misc_cmd=misc_cmd,
                   sub_cmds="\n\t".join("\"{}:{}\"".format(x, misc_commands_description[misc_cmd][x])
                                        for x in misc_commands_description[misc_cmd]))
    ret_str += """
            (build|report|{drivers})
                _arguments "2: :_files -g '*\.yaml' "\
            ;;
            (exec_package|run_package)
                _arguments "2: :_files -g '*\.temci' "\
            ;;
        esac
        ;;
        """.format(drivers="|".join(sorted(run_driver.RunDriverRegistry.registry.keys())))
    ret_str +="""
    (options)
        local -a args
        args=(
        $common_opts
        )
        #echo "options" $words[@] > tmp_file


        case $words[1] in

        """

    for driver in run_driver.RunDriverRegistry.registry.keys():
        ret_str += """
        {driver})
            case $words[2] in
                *.yaml)
                    args=(
                    $common_opts
                    {opts}
                    )
                    _arguments "1:: :echo 3" $args && ret=0
                ;;
                *)
                    _arguments "1:: :echo 3" && ret=0
            esac
        ;;
        """.format(driver=driver, opts=process_options(run_options["run_driver_specific"][driver]))

    cmds = {
        "report": {
            "pattern": "*.yaml",
            "options": report_options,
        },
        "build": {
            "pattern": "*.yaml",
            "options": build_options
        },
        "exec_package|run_package": {
            "pattern": "*.temci",
            "options": package_options
        }
    }

    for name in cmds:
        ret_str += """
            ({name})
                #echo "({name})" $words[2]
                case $words[2] in
                    {pattern})
                        args=(
                        $common_opts
                        {options}
                        )
                        _arguments "1:: :echo 3" $args && ret=0
                    ;;
                    *)
                        _arguments "1:: :echo 3" && ret=0
                esac
            ;;
        """.format(name=name, pattern=cmds[name]["pattern"], options=process_options(cmds[name]["options"]))

    for misc_cmd in misc_cmds_w_subcmds:
        ret_str += """
        ({misc_cmd})
            case $words[2] in
            """.format(misc_cmd=misc_cmd)
        for sub_cmd in misc_commands[misc_cmd]["sub_commands"]:
            ret_str +="""
                {sub_cmd})
                    #echo "{sub_cmd}" $words[@] > tmp_file
                    args+=(
                        {common_opts}
                        {opts}
                    )

                    #echo "sdf" $args[@] > tmp_file
                    _arguments "1:: :echo 3" $args && ret=0
                ;;
            """.format(sub_cmd=sub_cmd,
                       opts=process_options(misc_commands[misc_cmd]["sub_commands"][sub_cmd]),
                       common_opts=process_options(misc_commands[misc_cmd]["common"]))
        ret_str += """
            esac
            ;;
        """

    ret_str += """
    esac



        case $sub_cmd in
    """

    for misc_cmd in misc_cmds_wo_subcmds:
        ret_str += """
        {misc_cmd})
            # echo "{misc_cmd}" $words[@] >> tmp_file
            args+=(
                {opts}
            )
            case $words[2] in
                $sub_cmd)
                    _arguments "1:: :echo 3" $args && ret=0
                    ;;
                *)
                    # echo "Hi" >> tmp_file
                    _arguments $args && ret=0
                    ;;
            esac
        ;;
    """.format(misc_cmd=misc_cmd, opts=process_options(misc_commands[misc_cmd]))

    ret_str += """
        esac

        #_arguments $common_opts && ret=0 && return 0
    ;;
    esac
    }

    compdef _temci temci=temci
    """
    create_completion_dir()
    file_name = completion_file_name("zsh")
    if not os.path.exists(os.path.dirname(file_name)):
        os.mkdir(os.path.dirname(file_name))
    with open(file_name, "w") as f:
        f.write(ret_str)
        logging.debug("\n".join("{:>3}: {}".format(i, s) for (i, s) in enumerate(ret_str.split("\n"))))
        f.flush()
    os.chmod(file_name, 0o777)
    print(file_name)


@completion.command(short_help=misc_commands_description["completion"]["bash"])
@cmd_option(common_options)
def bash(**kwargs):
    temci__completion__bash()


@document_func(misc_commands_description["completion"]["bash"], common_options)
def temci__completion__bash():
    subcommands = "\n\t".join(sorted(command_docs.keys()))

    def process_options(options: CmdOptionList) -> str:
        typecheck(options, CmdOptionList)
        strs = []
        for option in sorted(options.options):
            strs.append("--" + option.option_name)
            if option.short is not None:
                strs.append("-" + option.short)
            if option.is_flag:
                strs.append("--no-" + option.option_name)
        return "\n\t".join(strs)

    def process_misc_commands():
        ret_str = ""
        for misc_cmd in misc_commands:
            if "sub_commands" not in misc_commands[misc_cmd]:
                continue
            ret_str += """
                case ${{COMP_WORDS[1]}} in
                {misc_cmd})
                    case ${{COMP_WORDS[2]}} in
            """.format(misc_cmd=misc_cmd)
            for sub_cmd in misc_commands[misc_cmd]["sub_commands"].keys():
                ret_str += """
                        {sub_cmd})
                            args=(
                                ${{common_opts[@]}}
                                {common_opts}
                                {cmd_ops}
                            )
                            # printf '   _%s ' "${{args[@]}}" >> /tmp/out
                            # printf '   __%s ' "${{args[*]}}" >> /tmp/out
                            COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                        ;;
                """.format(sub_cmd=sub_cmd,
                           cmd_ops=process_options(misc_commands[misc_cmd]["sub_commands"][sub_cmd]),
                           common_opts=process_options(misc_commands[misc_cmd]["common"]))
            ret_str += """
                        *)
                            local args=( )
                            COMPREPLY=( $(compgen -W "" -- $cur) ) && return 0
                    esac
                    ;;
                *)
                ;;
              esac
            """
        return ret_str

    def process_misc_commands_case():
        ret_str = ""
        for misc_cmd in misc_commands:
            args = []
            if "sub_commands" in misc_commands[misc_cmd]:
                args = " ".join(sorted(misc_commands[misc_cmd]["sub_commands"].keys()))
            else:
                typecheck(misc_commands[misc_cmd], CmdOptionList)
                args = process_options(misc_commands[misc_cmd].append(common_options))
            ret_str += """
            {misc_cmd})
                args=({sub_cmds})
                ;;
            """.format(misc_cmd=misc_cmd, sub_cmds=args)
        return ret_str

    run_cmd_file_code = ""
    for driver in run_driver.RunDriverRegistry.registry:
        run_cmd_file_code += """
            {driver})
                case ${{COMP_WORDS[2]}} in
                *.yaml)
                    args=(
                        $common_opts
                        $run_common_opts
                        {driver_opts}
                    )
                    COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                ;;
                esac
                ;;
        """.format(driver=driver, driver_opts=process_options(run_options["run_driver_specific"][driver]))

    file_structure = """
    # Auto generated tab completion for the temci ({version}) benchmarking tool.


    _temci(){{
        local cur=${{COMP_WORDS[COMP_CWORD]}}
        local prev=${{COMP_WORDS[COMP_CWORD-1]}}

        local common_opts=(
            {common_opts}
        )
        local args=(
            {common_opts}
        )
        local run_common_opts=(
            {run_common_opts}
        )
        local report_common_opts=(
            {report_common_opts}
        )
        local build_common_opts=(
            {build_common_opts}
        )

        {misc_commands_code}

        case ${{COMP_WORDS[1]}} in
            report)
                case ${{COMP_WORDS[2]}} in
                *.yaml)
                    args=(
                        $common_opts
                        $report_common_opts
                    )
                    COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                ;;
                esac
                ;;
            build)
                case ${{COMP_WORDS[2]}} in
                *.yaml)
                    args=(
                        $common_opts
                        $build_common_opts
                    )
                    COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                ;;
                esac
                ;;
            run_package|exec_package)
                case ${{COMP_WORDS[2]}} in
                *.temci)
                    args=(
                        $common_opts
                        {package_opts}
                    )
                    COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                ;;
                esac
                ;;
            {run_cmd_file_code}
            *)
            ;;
        esac

        case ${{COMP_WORDS[1]}} in
            (report|build|{run_drivers})
                local IFS=$'\n'
                local LASTCHAR=' '
                COMPREPLY=($(compgen -o plusdirs -o nospace -f -X '!*.yaml' -- "${{COMP_WORDS[COMP_CWORD]}}"))

                if [ ${{#COMPREPLY[@]}} = 1 ]; then
                    [ -d "$COMPREPLY" ] && LASTCHAR=/
                    COMPREPLY=$(printf %q%s "$COMPREPLY" "$LASTCHAR")
                else
                    for ((i=0; i < ${{#COMPREPLY[@]}}; i++)); do
                        [ -d "${{COMPREPLY[$i]}}" ] && COMPREPLY[$i]=${{COMPREPLY[$i]}}/
                    done
                fi
                return 0
                ;;
            (run_package|exec_package)
                local IFS=$'\n'
                local LASTCHAR=' '
                COMPREPLY=($(compgen -o plusdirs -o nospace -f -X '!*.temci' -- "${{COMP_WORDS[COMP_CWORD]}}"))

                if [ ${{#COMPREPLY[@]}} = 1 ]; then
                    [ -d "$COMPREPLY" ] && LASTCHAR=/
                    COMPREPLY=$(printf %q%s "$COMPREPLY" "$LASTCHAR")
                else
                    for ((i=0; i < ${{#COMPREPLY[@]}}; i++)); do
                        [ -d "${{COMPREPLY[$i]}}" ] && COMPREPLY[$i]=${{COMPREPLY[$i]}}/
                    done
                fi
                return 0
                ;;
            {misc_commands_case_code}
            *)
                args=({commands})
        esac
        COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) )
    }}
    shopt -s extglob
    complete -F _temci temci
    """.format(common_opts=process_options(common_options),
               run_common_opts=process_options(run_options["common"]),
               report_common_opts=process_options(report_options),
               commands=" ".join(sorted(command_docs.keys())),
               run_drivers="|".join(run_options["run_driver_specific"].keys()),
               misc_commands_case_code=process_misc_commands_case(),
               misc_commands_code=process_misc_commands(),
               build_common_opts=process_options(build_options),
               run_cmd_file_code=run_cmd_file_code,
               version=temci.scripts.version.version,
               package_opts=process_options(package_options))
    create_completion_dir()
    file_name = completion_file_name("bash")
    with open(file_name, "w") as f:
        f.write(file_structure)
        logging.debug("\n".join("{:>3}: {}".format(i, s) for (i, s) in enumerate(file_structure.split("\n"))))
        f.flush()
    os.chmod(file_name, 0o777)
    print(file_name)


@cli.command(short_help=command_docs["assembler"])
@click.argument("call", type=str)
def assembler(call: str):
    process_assembler(call.split(" "))


@document_func(command_docs["assembler"])
def temci__assembler(call: str):
    process_assembler(call.split(" "))


def cli_with_error_catching():
    """
    Process the command line arguments and catch (some) errors.
    """
    try:
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    except:
        pass
    try:
        cli()
    except EnvironmentError as err:
        logging.error(err)
        exit(1)


@cli.command(short_help=command_docs["setup"])
def setup():
    temci__setup()


@document_func(command_docs["setup"])
def temci__setup():
    from temci.setup.setup import make_scripts
    make_scripts()


if sphinx_doc():
    Settings.__doc__ += """

    The whole configuration file has the following structure:

""" + get_doc_for_type_scheme(Settings().type_scheme)



if __name__ == "__main__":
    # for testing purposes only

    sys.argv[1:] = ["short", "exec", "-wd", "ls", "--max_runs", "120", "--min_runs", "100"]
    #sys.argv[1:] = ["exec", "-wd", "ls", "-wd", "ls ..", "-wd", "ls /tmp", "--min_runs", "5", "--max_runs", "5",
    #                "--out", "ls_100.yaml", "--stop_start"]
    #sys.argv[1:] = ["report", "../misc/cparser_c_time.yaml", "--reporter", "html"]
    #sys.argv[1:] = ["init", "settings"]
    #sys.argv[1:] = ["completion", "zsh"]
    #sys.argv[1:] = ["assembler", "'dsafasdf sdaf'"]
    # default = Settings().type_scheme.get_default_yaml()
    # print(str(default))
    # print(yaml.load(default) == Settings().type_scheme.get_default())

    #sys.argv[1:] = ["run", "spec_like.exec.yaml", "--min_runs", "20", "--max_runs", "20"]

    #sys.argv[1:] = ["completion", "bash"]

    #if len(sys.argv) == 1:
    #    sys.argv[1:] = ['build', os.path.join(os.path.abspath("."), 'build.yaml')]
    #    os.chdir(os.path.abspath("../../../test/hadori"))

    #print(repr(sys.argv))

    #run_driver.ExecRunDriver.get_for_name("stop_start").setup()

    #import cProfile
    t = time.time()
    #cProfile.runctx("cli()", globals(), locals(), filename="cli.profile")
    print("Execution took ", humanfriendly.format_timespan(time.time() - t))
    #ctr.create_snapshot()
    # create kcachegrind valid file via "python3 -m pyprof2calltree -i cli.profile"
    #ctr.stats.print_summary()
    #tr.print_diff()
    cli()
