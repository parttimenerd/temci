from temci.run.run_processor import RunProcessor
from temci.utils.settings import Settings
from temci.tester.report_processor import ReportProcessor
import click, sys, yaml, logging
from temci.utils.typecheck import *
from temci.utils.click_helper import type_scheme_option, settings, settings_completion_dict

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
    "run": "Benchmark some program blocks",
    "report": "Generate a report from benchmarking result",
    "init": "Create a temci settings file in the current directory with the current settings",
    "_zsh_completion": "Creates a file /tmp/temci_zsh_completion for zsh completion support. "
                      "It can be used via adding the following to your .zshrc: "
                      "temci zsh_completion; source /tmp/temci_zsh_completion",
    "_fish_completion": "Creates a file /tmp/temci_fish_completion for fish completion support.",
    "_bash_completion": "Creates a file /tmp/temci_bash_completion for bash completion support."
}
misc_cmd_option_docs = {
    "run": {},
    "report": {},
    "init": {}
}


@cli.command(short_help="Benchmark some program blocks")
@type_scheme_option(Settings().type_scheme)
def run(**kwargs):
    settings(**kwargs)
    try:
        RunProcessor().benchmark()
    except KeyboardInterrupt:
        logging.error("KeyboardInterrupt. Cleaned up everything.")


@cli.command(short_help="Generate a report from benchmarking result")
@type_scheme_option(Settings().type_scheme)
def report(**kwargs):
    settings(**kwargs)
    ReportProcessor().report()


@cli.command(short_help="Create a temci settings file in the current directory with the current settings")
@type_scheme_option(Settings().type_scheme)
def init(**kwargs):
    settings(**kwargs)
    Settings().store_into_file(Settings().config_file_name)

@cli.command(short_help="Creates a file /tmp/temci_zsh_completion for zsh completion support. ")
@type_scheme_option(Settings().type_scheme)
def _zsh_completion(**kwargs):
    subcommands = "\n\t".join(['"{}:{}"'.format(cmd, command_docs[cmd])
                   for cmd in sorted(command_docs.keys())])

    def process_options(options: dict):
        typecheck(options, Dict(all_keys=False, key_type=Str(), value_type=Dict(all_keys=False)))
        strs = []
        for option in sorted(options.keys()):
            val = options[option]
            typecheck(val, Dict({
                "completion_hints": NonExistent() | Dict(all_keys=False, key_type=Str()),
                "description": NonExistent() | Str(),
                "default": Any()
            }))
            descr = "[{}]".format(val["description"]) if "description" in val else ""
            option_str = "--{}".format(option)
            if "short" in val:
                option_str = "{{-{},--{}}}".format(val["short"], option)
            if "completion_hints" in val and "zsh" in val["completion_hints"]:
                strs.append('"{option_str}{descr}: :{hint}"'.format(
                    option_str=option_str, descr=descr, hint=val["completion_hints"]["zsh"]
                ))
            else:
                strs.append('"{option_str}{descr}"'.format(
                    option_str=option_str, descr=descr
                ))
        return "\n\t".join(strs)

    def process_subcommand(cmd):
        return """
        {cmd})
            args+=(
                {ops}
            )
        ;;
        """.format(cmd=cmd, ops=process_options(misc_cmd_option_docs[cmd]))

    subcommand_code = "\n".join(process_subcommand(cmd) for cmd in misc_cmd_option_docs)

    common_ops = process_options(settings_completion_dict(**kwargs))

    file_structure = """
    #compdef temci
    _temci(){{
    local ret=1 state

    local -a common_ops
    common_ops=(
    {common_ops}
    )

    typeset -A opt_args
    _arguments \
    ':subcommand:->subcommand' \
    $common_ops \
    '*::options:->options' && ret=0

    case $state in
    subcommand)
        local -a subcommands
        subcommands=(
        {subcommands}
        )

        _describe -t subcommands 'temci subcommand' subcommands && ret=0
    ;;

    options)
        local -a args
        args=(
        $common_ops
        )

        case $words[1] in
        {subcommand_code}
        esac

        _arguments $args && ret=0
    ;;
    esac
    }}
    compdef _temci temci
    """.format(common_ops=common_ops, subcommands=subcommands, subcommand_code=subcommand_code)
    with open("/tmp/temci_zsh_completion.sh", "w") as f:
        f.write(file_structure)
        print(file_structure)
        f.flush()


@cli.command(short_help="Creates a file /tmp/temci_fish_completion for fish completion support. ")
@type_scheme_option(Settings().type_scheme)
def _fish_completion(**kwargs):

    def process_subcommand(cmd: str) -> list:
        strs = ["# sub command {}".format(cmd)]
        strs.append("complete -f -c temci -n '__temci_needs_command' -a {cmd} -d \"{descr}\"".format(
            cmd=cmd, descr=command_docs[cmd]
        ))
        if cmd in misc_cmd_option_docs and len(misc_cmd_option_docs[cmd]) > 0:
            strs.append(process_options(misc_cmd_option_docs[cmd], cmd))
        return strs

    def process_options(options: dict, sub_command: str = None) -> list:
        typecheck(options, Dict(all_keys=False, key_type=Str(), value_type=Dict({
            "completion_hints": NonExistent() | Dict(all_keys=False, key_type=Str()),
            "description": NonExistent() | Str(),
            "default": Any(),
            "short": NonExistent() | Str()
        })))
        strs = []
        n_option = ""
        if sub_command is not None:
            n_option = "-n '__temci_using_command {cmd}'".format(cmd=sub_command)
        for cmd in sorted(options.keys()):
            val  = options[cmd]
            descr = "-d \"{}\"".format(val["description"]) if "description" in val else ""
            hint = ""
            files_str = "--no-files"
            if "completion_hints" in val and "fish" in val["completion_hints"]:
                hint_val = val["completion_hints"]["fish"]
                typecheck(hint_val, Dict({
                    "hint": List() | NonExistent(),
                    "files": (Bool() | NonExistent()) // Default(False), # allow files as argument
                    # --authoritative implies that there may be no more options than the ones specified,
                    # and that fish should assume that options not listed are spelling errors.
                    "authorative": (Bool() | NonExistent()) // Default(True)
                }))
                if "files" in hint_val and hint_val["files"]:
                    files_str = ""
                authoritative_sir = "" if "authorative" in hint_val and not hint_val["authorative"] else "-A"
                hint_str = ""
                if "hint" in hint_val:
                    hint_str = "-a \"{}\"".format(" ".join(repr(s) for s in hint_val["hint"]))
                hint = "-r {a} {h}".format(a=authoritative_sir, h=hint_str)
            short = "-s {}" if "short" in val else ""
            strs.append("complete -c temci {n} {s} -l {cmd} -r {f} {h} {d}".format(
                n=n_option, cmd=cmd, h=hint, d=descr, s=short, f=files_str
            ))
        return strs

    common_options = ["# common options"]
    common_options.extend(process_options(settings_completion_dict(**kwargs)))

    code = common_options
    for cmd in command_docs:
        code.append("")
        code.extend(process_subcommand(cmd))
    print(code)
    file_structure = """
function __temci_needs_command
  set cmd (commandline -opc)
  if [ (count $cmd) -eq 1 -a $cmd[1] = 'temci' ]
    return 0
  end
  return 1
end

function __temci_using_command
  set cmd (commandline -opc)
  if [ (count $cmd) -gt 1 ]
    if [ $argv[1] = $cmd[2] ]
      return 0
    end
  end
  return 1
end

{code}
    """.format(code="\n".join(code))
    with open("/tmp/temci_fish_completion.fish", "w") as f:
        f.write(file_structure)
        print(file_structure)
        f.flush()


@cli.command(short_help="Creates a file /tmp/temci_bash_completion for bash completion support. ")
@type_scheme_option(Settings().type_scheme)
def _bash_completion(**kwargs):
    subcommands = "\n\t".join(sorted(command_docs.keys()))

    def process_args(arguments: dict):
        typecheck(arguments, Dict(all_keys=False, key_type=Str()))
        strs = ["--" + key for key in sorted(arguments.keys())]
        return "\n\t".join(strs)

    def process_subcommand(cmd):
        return """
        {cmd})
            args=(
                {ops}
                $common_ops
            )
        ;;
        """.format(cmd=cmd, ops=process_args(misc_cmd_option_docs[cmd]))

    subcommand_code = "\n".join(process_subcommand(cmd) for cmd in misc_cmd_option_docs)

    common_ops = process_args(settings_completion_dict(**kwargs))

    file_structure = """
    _temci(){{
        local cur=${{COMP_WORDS[COMP_CWORD]}}
        local prev=${{COMP_WORDS[COMP_CWORD-1]}}]
        local common_ops=(
            {common_ops}
        )
        local args=(
            {common_ops}
        )
        case $prev in
            {subcommand_code}
            --help)
              ;;
            *)
              args+=({subcommands})
              ;;
        esac
        COMPREPLY=( $(compgen -W "${{args[*]}}" -- $cur) )
    }}
    complete -o default -F _temci temci
    """.format(common_ops=common_ops, subcommands=subcommands, subcommand_code=subcommand_code)
    with open("/tmp/temci_bash_completion.sh", "w") as f:
        f.write(file_structure)
        print(file_structure)
        f.flush()

#sys.argv[1:] = ["_fish_completion"]
#    sys.argv[1:] = []

#default = Settings().type_scheme.get_default_yaml()
#print(str(default))
#print(yaml.load(default) == Settings().type_scheme.get_default())

cli()