import warnings
warnings.simplefilter("ignore")
import shutil
import subprocess

import time

import humanfriendly

from temci.scripts.init import prompt_run_config, prompt_build_config
from temci.utils.typecheck import *

from pympler import tracker, classtracker
tr = tracker.SummaryTracker()
ctr = classtracker.ClassTracker()
ctr.track_class(Type)
ctr.create_snapshot()

from temci.run.run_processor import RunProcessor
from temci.build.assembly import AssemblyProcessor
from temci.build.build_processor import BuildProcessor
import temci.run.run_driver as run_driver
import temci.run.run_driver_plugin
from temci.tester.report import ReporterRegistry
from temci.utils.settings import Settings
from temci.tester.report_processor import ReportProcessor
import click, sys, yaml, logging, json, os
from temci.utils.click_helper import type_scheme_option, cmd_option, CmdOption, CmdOptionList

ctr.create_snapshot()

@click.group(epilog="""
This program is still in an early aplha stage. It may happen that
you're system needs to be rebooted to be usable again.

The main workflow is to write config files and use them with the program.
Although command line options are supported, config files are way easier to use.

It's licence is GPLv3.
""")
def cli():
    pass


command_docs = {
    "build": "Build program blocks",
    "report": "Generate a report from benchmarking result",
    "init": "Helper commands to initialize files (like settings)",
    "completion": "Creates completion files for several shells.",
    "short": "Utility commands to ease working directly on the command line",
    "clean": "Clean up the temporary files"
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
        "zsh": "Creates a file /tmp/temci_zsh_completion for zsh completion support. ",
        #"fish": "Creates a file /tmp/temci_fish_completion for fish completion support.",
        "bash": "Creates a file /tmp/temci_bash_completion for bash completion support."
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
    @cli.command(name=driver, short_help=command_docs[driver])
    @click.argument("run_file")
    @cmd_option(common_options)
    @cmd_option(run_options["common"])
    @cmd_option(run_options["run_driver_specific"][driver])
    def func(run_file, **kwargs):
        Settings()["run/driver"] = driver
        Settings()["run/in"] = run_file
        try:
            RunProcessor().benchmark()
        except KeyboardInterrupt:
            logging.error("KeyboardInterrupt. Cleaned up everything.")

@cli.group(short_help=command_docs["short"])
@cmd_option(common_options)
@cmd_option(misc_commands["short"]["common"])
def short(**kwargs):
    pass

@short.command(short_help=misc_commands_description["short"]["exec"])
@cmd_option(common_options)
@cmd_option(misc_commands["short"]["sub_commands"]["exec"])
@cmd_option(run_options["run_driver_specific"]["exec"])
def exec(with_description: list = None, without_description: list = None, **kwargs):
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


@cli.command(short_help="Generate a report from benchmarking result")
@click.argument('report_file', type=click.Path(exists=True))
@cmd_option(common_options)
@cmd_option(report_options)
def report(report_file: str, **kwargs):
    Settings()["report/in"] = report_file
    ReportProcessor().report()


@cli.group(short_help=command_docs["init"])
@cmd_option(misc_commands["init"]["common"])
@cmd_option(common_options)
def init(**kwargs):
    pass


@init.command(short_help=misc_commands_description["init"]["settings"])
@cmd_option(misc_commands["init"]["sub_commands"]["settings"])
@cmd_option(common_options)
def settings(**kwargs):
    Settings().store_into_file("temci.yaml")


@init.command(short_help=misc_commands_description["init"]["build_config"])
@cmd_option(misc_commands["init"]["sub_commands"]["build_config"])
@cmd_option(common_options)
def build_config(**kwargs):
    prompt_build_config()


@init.command(short_help=misc_commands_description["init"]["run_config"])
@cmd_option(misc_commands["init"]["sub_commands"]["run_config"])
@cmd_option(common_options)
def run_config(**kwargs):
    prompt_run_config()


@cli.command(short_help=command_docs["build"])
@click.argument('build_file', type=click.Path(exists=True))
@cmd_option(common_options)
def build(build_file: str, **kwargs):
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
    shutil.rmtree(Settings()["tmp_dir"])


@cli.group(short_help=command_docs["completion"])
@cmd_option(common_options)
def completion(**kwargs):
    pass


@completion.command(short_help="Creates a file /tmp/temci_zsh_completion for zsh completion support. ")
@cmd_option(common_options)
def zsh(**kwargs):
    subcommands = "\n\t".join(['"{}:{}"'.format(cmd, command_docs[cmd])
                               for cmd in sorted(command_docs.keys())])

    def process_options(options: CmdOptionList, one_line=False):
        typecheck(options, CmdOptionList)
        strs = []
        for option in sorted(options):
            assert isinstance(option, CmdOption)
            descr = "{}".format(option.description) if option.description is not None else "Undoc"
            option_str = "--{}".format(option.option_name)
            if option.has_short:
                option_str = "{{-{},--{}}}".format(option.short, option.option_name)
            if option.is_flag:
                option_str = "{{--{o},--no-{o}}}".format(o=option.option_name)
            if option.has_completion_hints and "zsh" in option.completion_hints:
                strs.append('{option_str}\"[{descr}]: :{hint}"'.format(
                    option_str=option_str, descr=descr, hint=option.completion_hints["zsh"]
                ))
            else:
                format_str = '{option_str}\"[{descr}]"' if option.is_flag else '{option_str}\"[{descr}]: :()"'
                strs.append(format_str.format(
                    option_str=option_str, descr=descr
                ))

        if one_line:
            return " ".join(strs)
        return "\n\t".join(strs)

    misc_cmds_wo_subcmds = list(filter(lambda x: isinstance(misc_commands[x], CmdOptionList), misc_commands.keys()))
    misc_cmds_w_subcmds = list(filter(lambda x: isinstance(misc_commands[x], dict), misc_commands.keys()))

    ret_str = """

#compdef temci
_temci(){{
    printf '%s\n' "${{words[@]}}" > /tmp/out
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
               misc_cmds_wo_subs="|".join(misc_cmds_wo_subcmds))
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

    ret_str += """
        (report)
            #echo "(report)" $words[2]
            case $words[2] in
                *.yaml)
                    args=(
                    $common_opts
                    {report_opts}
                    )
                    _arguments "1:: :echo 3" $args && ret=0
                ;;
                *)
                    _arguments "1:: :echo 3" && ret=0
            esac
        ;;
        (build)
            case $words[2] in
                *.yaml)
                    args=(
                    $common_opts
                    {build_opts}
                    )
                    _arguments "1:: :echo 3" $args && ret=0
                ;;
                *)
                    _arguments "1:: :echo 3" && ret=0
            esac
        ;;
    """.format(report_opts=process_options(report_options),
               build_opts=process_options(build_options))

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
            echo "{misc_cmd}" $words[@] >> tmp_file
            args+=(
                {opts}
            )
            case $words[2] in
                $sub_cmd)
                    _arguments "1:: :echo 3" $args && ret=0
                    ;;
                *)
                    echo "Hi" >> tmp_file
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
    with open("/tmp/temci_zsh_completion.sh", "w") as f:
        f.write(ret_str)
        print("\n".join("{:>3}: {}".format(i, s) for (i, s) in enumerate(ret_str.split("\n"))))
        f.flush()


@completion.command(short_help="Creates a file /tmp/temci_bash_completion for bash completion support. ")
@cmd_option(common_options)
def bash(**kwargs):
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
                            printf '   _%s\n' "${{args[@]}}" >> /tmp/out
                            printf '   __%s\n' "${{args[*]}}" >> /tmp/out
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
    _temci(){{
        #printf '%s\n' "${{COMP_WORDS[@]}}" > /tmp/out
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
               run_cmd_file_code=run_cmd_file_code
               )
    with open("/tmp/temci_bash_completion.sh", "w") as f:
        f.write(file_structure)
        print("\n".join("{:>3}: {}".format(i, s) for (i, s) in enumerate(file_structure.split("\n"))))
        f.flush()


@cli.command(short_help="Wrapper around the gnu assembler")
@click.argument("call", type=str)
def assembler(call: str):
    call = call.split(" ")
    input_file = os.path.abspath(call[-1])
    config = json.loads(os.environ["RANDOMIZATION"]) if "RANDOMIZATION" in os.environ else {}
    as_tool = os.environ["USED_AS"] if "USED_AS" in os.environ else "/usr/bin/as"

    def exec(cmd):
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True)
        out, err = proc.communicate()
        if proc.poll() > 0:
            return str(err)
        return None

    processor = AssemblyProcessor(config)
    shutil.copy(input_file, "/tmp/temci_assembler.s")
    call[0] = as_tool
    shutil.copy("/tmp/temci_assembler.s", input_file)
    processor.process(input_file)
    ret = exec(" ".join(call))
    if ret is None:
        return
    for i in range(0, 6):
        shutil.copy("/tmp/temci_assembler.s", input_file)
        processor.process(input_file, small_changes=True)
        ret = exec(" ".join(call))
        if ret is None:
            return
        #else:
        #    logging.debug("Another try")
    if processor.config["file_structure"]:
        logging.warning("Disabled file structure randomization")
        config["file_structure"] = False
        for i in range(0, 6):
            processor = AssemblyProcessor(config)
            shutil.copy("/tmp/temci_assembler.s", input_file)
            processor.process(input_file)
            ret = exec(" ".join(call))
            if ret is None:
                return
            logging.info("Another try")
    logging.error(ret)
    shutil.copy("/tmp/temci_assembler.s", input_file)
    ret = exec(" ".join(call))
    if ret is not None:
        logging.error(ret)
        exit(1)

def cli_with_error_catching():
    try:
        cli()
    except TypeError as err:
        logging.error("TypeError: " + str(err))
        exit(1)

@cli.command(short_help="Compile all needed binaries in the temci scripts folder")
def setup():
    from temci.setup.setup import make_scripts
    make_scripts()

if __name__ == "__main__":
    #sys.argv[1:] = ["exec", "-wd", "ls", "-wd", "ls ..", "-wd", "ls /tmp", "--min_runs", "5", "--max_runs", "5",
    #                "--out", "ls_100.yaml", "--stop_start"]
    sys.argv[1:] = ["report", "run_output.yaml", "--reporter", "html2"]
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

    import cProfile
    t = time.time()
    cProfile.runctx("cli()", globals(), locals(), filename="cli.profile")
    print("Execution took ", humanfriendly.format_timespan(time.time() - t))
    ctr.create_snapshot()
    #ctr.stats.print_summary()
    #tr.print_diff()
    #cli()
