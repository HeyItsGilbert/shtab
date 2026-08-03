#!/usr/bin/env python
"""
`argparse`-based CLI app with custom file completion as well as subparsers.

See `pathcomplete.py` for a more basic version.
"""
import argparse

import shtab  # for completion magic

# WARNING: (re)run by your shell on each tab press, so could be slow
_complete_token_cmd = "head -c5 /dev/random | base32"
COMPLETE_TOKEN = {
    "bash": "_shtab_greeter_compgen_PYModules", "zsh": f"($({_complete_token_cmd}))",
    "tcsh": f"`{_complete_token_cmd}`", "fish": f"({_complete_token_cmd})", "preamble": {
        "bash": f"""
# $1=COMP_WORDS[1]
_shtab_greeter_compgen_PYModules() {{
  compgen -W "$({_complete_token_cmd})" -- $1
}}
"""}}


def process(args):
    print(f"received <token>={args.token} [<suffix>={args.suffix}]"
          f" --input-file={args.input_file} --output-name={args.output_name}"
          f" --compose-file={args.compose_file} --hidden-opt={args.hidden_opt}")


def get_main_parser():
    main_parser = argparse.ArgumentParser(prog="customcomplete")
    subparsers = main_parser.add_subparsers()
    # make required (py3.7 API change); vis. https://bugs.python.org/issue16308
    subparsers.required = True
    subparsers.dest = "subcommand"

    parser = subparsers.add_parser("completion", help="print tab completion")
    shtab.add_argument_to(parser, "shell", parent=main_parser) # magic!

    parser = subparsers.add_parser("process", help="parse files")
    # dynamic command tab completion builtin shortcut
    parser.add_argument("token").complete = COMPLETE_TOKEN
    # file tab completion builtin shortcut
    parser.add_argument("-i", "--input-file").complete = shtab.FILE
    # directory tab completion builtin shortcut
    parser.add_argument(
        "-o",
        "--output-name",
        help=("output file name. Completes directory names to avoid users"
              " accidentally overwriting existing files."),
    ).complete = shtab.DIRECTORY
    # glob pattern tab completion builtin shortcut
    parser.add_argument("--compose-file").complete = shtab.glob("docker-compose*.yml",
                                                                "docker-compose*.yaml")
    parser.add_argument("suffix", choices=['json', 'csv'], default='json', nargs='?',
                        help="Output format")
    # help=None or argparse.SUPPRESS to exclude from CLI --help & completions
    parser.add_argument("--hidden-opt", action='store_true', help=argparse.SUPPRESS)
    parser.set_defaults(func=process)
    return main_parser


if __name__ == "__main__":
    parser = get_main_parser()
    args = parser.parse_args()
    args.func(args)
