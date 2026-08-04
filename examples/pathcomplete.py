#!/usr/bin/env python
"""
`argparse`-based CLI app with file/dir tab completion.

Uses `add_argument().complete = shtab.(FILE|DIR|glob(...)|cmd(...))`.
See `customcomplete.py` for a more advanced version.
"""
import argparse

import shtab  # for completion magic


def get_main_parser():
    parser = argparse.ArgumentParser(prog="pathcomplete")
    shtab.add_argument_to(parser, ["-s", "--print-completion"]) # magic!

    # file & directory tab complete
    parser.add_argument("file", nargs="?").complete = shtab.FILE
    parser.add_argument("--dir", default=".").complete = shtab.DIRECTORY
    parser.add_argument("--config").complete = shtab.glob('*.toml', '*.yml', '*.yaml', '*.json')
    # WARNING: shtab.cmd is (re)run by your shell on each tab press, so could be slow
    parser.add_argument("--branch",
                        help="git branch from current workdir").complete = shtab.cmd("git branch")
    return parser


if __name__ == "__main__":
    parser = get_main_parser()
    args = parser.parse_args()
    print(f"received <file>={args.file} --dir={args.dir}"
          f" --config={args.config} --branch={args.branch}")
