import shutil
import subprocess

from temci.run.run_processor import RunProcessor
from temci.build.assembly import AssemblyProcessor
from temci.build.build_processor import BuildProcessor
import temci.run.run_driver as run_driver
from temci.tester.report import ReporterRegistry
from temci.utils.settings import Settings
from temci.tester.report_processor import ReportProcessor
import click, sys, yaml, logging, json, os
from temci.utils.typecheck import *
from temci.utils.click_helper import type_scheme_option, cmd_option, CmdOption, CmdOptionList


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
    "run": "Benchmark some program blocks",
    "report": "Generate a report from benchmarking result",
    "init": "Create a temci settings file in the current directory with the current settings",
    "completion": "Creates completion files for several shells.",
    "exec": "Use the run driver the benchmark some programs",
    "clean": "Clean up the temporary files"
}

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
for driver in run_driver.RunDriverRegistry._register:
    options = CmdOptionList(
        CmdOption.from_registry(run_driver.RunDriverRegistry._register[driver]),
        CmdOption.from_non_plugin_settings("run/{}_misc".format(driver)))
    if driver not in run_options["run_driver_specific"]:
        run_options["run_driver_specific"][driver] = options
    else:
        run_options["run_driver_specific"][driver].append(options)

report_options = CmdOptionList(
    CmdOption.from_non_plugin_settings("report"),
    CmdOption.from_non_plugin_settings("stats")
)
# init the report_options dictionary
for reporter in ReporterRegistry._register:
    options = CmdOption.from_non_plugin_settings("report/{}_misc".format(reporter), name_prefix=reporter)
    report_options.append(options)

build_options = CmdOptionList(
    CmdOption.from_non_plugin_settings("build")
)

misc_commands = {
    "init": {
        "common": CmdOptionList(),
        "sub_commands": {
            "settings": CmdOptionList()
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
                          ),
    "clean": CmdOptionList()
}
misc_commands_description = {
    "completion": {
        "zsh": "Creates a file /tmp/temci_zsh_completion for zsh completion support. ",
        #"fish": "Creates a file /tmp/temci_fish_completion for fish completion support.",
        "bash": "Creates a file /tmp/temci_bash_completion for bash completion support."
    },
    "init": {
        "settings": "Create a new settings file temci.yaml in the current directory"
    }
}


@cli.command(short_help="Benchmark some program blocks")
@click.argument("run_file")
@cmd_option(common_options)
@cmd_option(run_options["common"])
def run(run_file: str, **kwargs):
    @click.group()
    @cmd_option(common_options)
    def _base_func(**kwargs):
        pass

    @_base_func.group(name="run", epilog="Benchmark some program blocks")
    @cmd_option(run_options["common"])
    def base_func(**kwargs):
        pass

    for driver in run_driver.RunDriverRegistry._register:
        cmd_name = run_file if run_file.endswith(".{}.yaml".format(driver)) else driver

        @base_func.command(run_file, short_help=run_driver.RunDriverRegistry._register[driver].__description__)
        @cmd_option(run_options["run_driver_specific"][driver])
        def func(**kwargs):
            Settings()["run/driver"] = driver
            Settings()["run/in"] = run_file
            try:
                RunProcessor().benchmark()
            except KeyboardInterrupt:
                logging.error("KeyboardInterrupt. Cleaned up everything.")

        break
    _base_func()


@cli.command(short_help=command_docs["exec"])
@cmd_option(misc_commands["exec"])
@cmd_option(run_options["run_driver_specific"]["exec"])
def exec(with_description: list = None, without_description: list = None, **kwargs):
    runs = []
    if with_description is not None:
        for (descr, cmd) in with_description:
            runs.append({
                "run_config": {
                    "run_cmds": [cmd]
                },
                "attributes": {
                    "description": descr
                }
            })
    if without_description is not None:
        for cmd in without_description:
            runs.append({"run_config": {
                    "run_cmds": [cmd]
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


@cli.group(short_help="Some init helpers")
@cmd_option(misc_commands["init"]["common"])
def init():
    pass


@init.command(short_help=misc_commands_description["init"]["settings"])
@cmd_option(misc_commands["init"]["sub_commands"]["settings"])
def settings(**kwargs):
    Settings().store_into_file("temci.yaml")


@cli.command(short_help=command_docs["build"])
@click.argument('build_file', type=click.Path(exists=True))
@cmd_option(common_options)
def build(build_file: str, **kwargs):
    Settings()["build/in"] = build_file
    BuildProcessor().build()

@cli.command(short_help=command_docs["exec"])
@cmd_option(common_options)
def clean():
    shutil.rmtree(Settings()["tmp_dir"])


@cli.group(short_help=command_docs["completion"])
def completion():
    pass


@completion.command(short_help="Creates a file /tmp/temci_zsh_completion for zsh completion support. ")
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
                strs.append('{option_str}\"[{descr}]: :()"'.format(
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

    #echo $words[2] > tmp_file

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
            (run)
                echo "run" $state > tmp_file
                _arguments "2: :_files -g '*\.({drivers})\.yaml'"\
            ;;
            (report)
                _arguments "2: :_files -g '*\.yaml' "\
            ;;
            (build)
                _arguments "2: :_files -g '*\.yaml' "\
            ;;
        esac
        ;;
        """.format(drivers="|".join(sorted(run_driver.RunDriverRegistry._register.keys())))
    ret_str +="""
    (options)
        local -a args
        args=(
        $common_opts
        )
        #echo "options" $words[@] > tmp_file


        case $words[1] in

        (run)
            #echo "sdf" $words[@] > tmp_file
            case $words[2] in
        """
    for driver in run_driver.RunDriverRegistry._register.keys():
        ret_str += """
                *.{driver}.yaml)
                    args=(
                        "1:: :echo 3"
                        $common_opts
                        {opts}
                    )
                    _arguments $args && ret=0
                    ;;
        """.format(driver=driver, opts=process_options(run_options["run_driver_specific"][driver]))
    ret_str +="""
            esac
        ;;
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

        echo $words[@] > tmp_file
        echo $sub_cmd >> tmp_file
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


    compdef _temci temci
    """
    with open("/tmp/temci_zsh_completion.sh", "w") as f:
        f.write(ret_str)
        print("\n".join("{:>3}: {}".format(i, s) for (i, s) in enumerate(ret_str.split("\n"))))
        f.flush()


@completion.command(short_help="Creates a file /tmp/temci_bash_completion for bash completion support. ")
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

    def process_run() -> str:
        """ Creates a case statement part for the run command and it's sub commands """
        run_driver_reg = run_driver.RunDriverRegistry._register
        ret_str = """
            case ${COMP_WORDS[COMP_CWORD-2]} in
            run)
                case $prev in
        """
        for driver in run_driver_reg:
            ret_str += """
                    *.{driver}.yaml)
                        args=(
                            $common_opts
                            $run_common_opts
                            {driver_ops}
                        )
                        COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                    ;;
            """.format(driver=driver, driver_ops=process_options(run_options["run_driver_specific"][driver]))
        ret_str += """
                esac
                ;;
            *)
            ;;
          esac
        """
        return ret_str

    def process_misc_commands():
        ret_str = ""
        for misc_cmd in misc_commands:
            if "sub_commands" not in misc_commands[misc_cmd]:
                continue
            ret_str += """
                case ${{COMP_WORDS[COMP_CWORD-2]}} in
                {misc_cmd})
                    case $prev in
            """.format(misc_cmd=misc_cmd)
            for sub_cmd in misc_commands[misc_cmd]["sub_commands"].keys():
                ret_str += """
                        {sub_cmd})
                            args=(
                                $common_opts
                                {common_opts}
                                {cmd_ops}
                            )
                            COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                        ;;
                """.format(sub_cmd=sub_cmd,
                           cmd_ops=process_options(misc_commands[misc_cmd]["sub_commands"][sub_cmd]),
                           common_opts=process_options(misc_commands[misc_cmd]["common"]))
            ret_str += """
                        *)
                            args=( )
                            COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
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

    file_structure = """
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

        {run_code}

        {misc_commands_code}

        case ${{COMP_WORDS[COMP_CWORD-2]}} in
            report)
                case $prev in
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
                case $prev in
                *.yaml)
                    args=(
                        $common_opts
                        $build_common_opts
                    )
                    COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) ) && return 0
                ;;
                esac
                ;;
            *)
            ;;
        esac

        case $prev in
            run)
                local IFS=$'\n'
                local LASTCHAR=' '
                COMPREPLY=($(compgen -o plusdirs -f -X '!*.@({run_drivers}).yaml' -- "${{COMP_WORDS[COMP_CWORD]}}"))

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
            report)
            build)
                local IFS=$'\n'
                local LASTCHAR=' '
                COMPREPLY=($(compgen -o plusdirs -o nospace -f -X '!*.yaml' \
                    -- "${{COMP_WORDS[COMP_CWORD]}}"))

                if [ ${{#COMPREPLY[@]}} = 1 ]; then
                    [ -d "$COMPREPLY" ] && LASTCHAR=/
                    COMPREPLY=$(printf %q%s "$COMPREPLY" "$LASTCHAR")
                else
                    for ((i=0; i < ${{#COMPREPLY[@]}}; i++)); do
                        [ -d "${{COMPREPLY[$i]}}" ] && COMPREPLY[$i]=${{COMPREPLY[$i]}}
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
               run_code=process_run(),
               run_drivers="|".join(run_options["run_driver_specific"].keys()),
               misc_commands_case_code=process_misc_commands_case(),
               misc_commands_code=process_misc_commands(),
               build_common_opts=process_options(build_options)
               )
    with open("/tmp/temci_bash_completion.sh", "w") as f:
        f.write(file_structure)
        print("\n".join("{>3}: {}".format(i, s) for (i, s) in enumerate(file_structure.split("\n"))))
        f.flush()


@cli.command(short_help="Wrapper around the gnu assembler")
@click.argument("call", type=str)
def assembler(call: str):
    call = call.split(" ")
    input_file = os.path.abspath(call[-1])
    config = json.loads(os.environ["RANDOMIZATION"]) if "RANDOMIZATION" in os.environ else {}
    as_tool = os.environ["USED_AS"] if "USED_AS" in os.environ else "/usr/bin/as"

    def exec(cmd):
        proc = subprocess.Popen(["/bin/bash", "-c", cmd], stdout=subprocess.PIPE,
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


@cli.command(short_help="Compile all needed binaries in the temci scripts folder")
def setup():
    from temci.setup.setup import make_scripts
    make_scripts()

if __name__ == "__main__":
    #sys.argv[1:] = ["exec", "-wd", "ls", "-wd", "ls ..", "-wd", "ls /tmp", "--min_runs", "5", "--max_runs", "5",
    #                "--out", "ls_100.yaml", "--stop_start"]
    #sys.argv[1:] = ["report", "run_output.yaml"]
    #sys.argv[1:] = ["init", "settings"]
    #sys.argv[1:] = ["completion", "zsh"]
    #sys.argv[1:] = ["assembler", "'dsafasdf sdaf'"]
    # default = Settings().type_scheme.get_default_yaml()
    # print(str(default))
    # print(yaml.load(default) == Settings().type_scheme.get_default())

    if len(sys.argv) == 1:
        sys.argv[1:] = ['build', os.path.join(os.path.abspath("."), 'build.yaml')]
        os.chdir(os.path.abspath("../../../test/hadori"))

    #print(repr(sys.argv))

    cli()
