'''
@main.command(hidden=True)
@click.pass_context
def completion(ctx):
    """Generate bash completion script"""

    root = ctx.find_root()
    rootcmd = root.command

    main_parser = add_to_parser(rootcmd, argparse.ArgumentParser(prog=rootcmd.name))

    print(shtab.complete(main_parser))
'''
import argparse

import click

import shtab


def add_to_parser(command, parser):
    for param in command.params:
        if param.param_type_name == "option":
            spec = {}

            if param.is_flag:
                spec["action"] = "store_true"
            else:
                spec["nargs"] = param.nargs
                spec["required"] = param.required

            if isinstance(param.type, click.Choice):
                spec["choices"] = param.type.choices

            arg = parser.add_argument(*param.opts, **spec)

            if isinstance(param.type, click.File):
                arg.complete = shtab.FILE
            elif isinstance(param.type, click.Path):
                if param.type.file_okay and not param.type.dir_okay:
                    arg.complete = shtab.FILE
                elif not param.type.file_okay and param.type.dir_okay:
                    arg.complete = shtab.DIRECTORY

        elif param.param_type_name == "argument":
            spec = {}

            if param.nargs == -1:
                spec["nargs"] = "+" if param.required else "*"
            else:
                spec["nargs"] = param.nargs

            if isinstance(param.type, click.Choice):
                spec["choices"] = param.type.choices

            arg = parser.add_argument(param.name, **spec)

            if isinstance(param.type, click.File):
                arg.complete = shtab.FILE
            elif isinstance(param.type, click.Path):
                if param.type.file_okay and not param.type.dir_okay:
                    arg.complete = shtab.FILE
                elif not param.type.file_okay and param.type.dir_okay:
                    arg.complete = shtab.DIRECTORY

    if hasattr(command, "commands") and len(command.commands) > 0:
        subparsers = parser.add_subparsers()
        subparsers.required = True
        subparsers.dest = "subcommand"

        for name, subcmd in command.commands.items():
            if subcmd.hidden:
                continue

            # non-empty help necessary or argparse doesn't consider it an action??
            subparser = subparsers.add_parser(name, help=command.help)

            add_to_parser(subcmd, subparser)

    return parser
