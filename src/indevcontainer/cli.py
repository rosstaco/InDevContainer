"""``idc`` CLI entrypoint.

Five subcommands; no top-level positional, so naming-collision workarounds
aren't needed any more (every command name is a literal first argv token).

* ``idc code [-i] <path>`` — open *path* in VS Code via its devcontainer.
* ``idc shell <path> [--shell EXE] [-i]`` — exec an interactive shell in
  the running devcontainer.
* ``idc copilot <path> [-- copilot args...]`` — exec the GitHub Copilot
  CLI inside the running devcontainer.
* ``idc doctor [<path>]`` — diagnose the local environment.
* ``idc update [--check]`` — upgrade idc via ``uv tool``.

Bare ``idc`` prints help and exits 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from indevcontainer.core import run_code
from indevcontainer.doctor import run_doctor
from indevcontainer.update import run_update, run_update_check


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="idc",
        description=(
            "Run code, shells, and the Copilot CLI in a VS Code devcontainer.\n"
            "\n"
            "All actions are subcommands. To open a folder literally named "
            "'code', 'shell', 'copilot', 'doctor', or 'update', run "
            "`idc code ./<name>`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    p_code = subparsers.add_parser(
        "code",
        help="open a folder in VS Code via its devcontainer",
        description=(
            "Open `path` (default: current directory) in VS Code via the "
            "configured devcontainer. Falls back to plain `code <path>` "
            "when no devcontainer.json is found. Exit code is forwarded "
            "from the spawned editor."
        ),
    )
    p_code.add_argument(
        "-i",
        "--insiders",
        action="store_true",
        help="use VS Code Insiders",
    )
    p_code.add_argument(
        "code_path",
        nargs="?",
        default=".",
        metavar="path",
        help="folder to open (default: current directory)",
    )

    p_shell = subparsers.add_parser(
        "shell",
        help="open a shell in the project's running devcontainer",
        description=(
            "Open an interactive shell inside the running devcontainer for "
            "the project at `path`. Mirrors VS Code's integrated terminal: "
            "respects terminal profile settings (workspace > devcontainer > "
            "user), forwards the SSH agent socket when available, runs as "
            "`remoteUser`/`containerUser` from devcontainer.json. Requires "
            "an interactive terminal. To open a folder literally named "
            "'shell', use `idc code ./shell`."
        ),
    )
    p_shell.add_argument(
        "shell_path",
        nargs="?",
        default=".",
        metavar="path",
        help="project folder (default: current directory)",
    )
    p_shell.add_argument(
        "-i",
        "--insiders",
        action="store_true",
        help="resolve VS Code Insiders user settings for terminal profile lookup",
    )
    p_shell.add_argument(
        "--shell",
        default=None,
        dest="shell_override",
        metavar="EXECUTABLE",
        help=(
            "literal shell executable to use (overrides VS Code settings); "
            "no shell-style argument splitting"
        ),
    )

    p_copilot = subparsers.add_parser(
        "copilot",
        help="run the GitHub Copilot CLI inside the project's devcontainer",
        description=(
            "Exec the GitHub Copilot CLI (`copilot`) inside the running "
            "devcontainer for the project at `path`. Shares container "
            "resolution with `idc shell` (auto-build & prompt to start).\n"
            "\n"
            "Usage:\n"
            "  idc copilot                       # cwd, no copilot args\n"
            "  idc copilot --yolo --resume       # cwd; flags forward to copilot\n"
            "  idc copilot ./proj --resume       # explicit path; flags forward\n"
            "  idc copilot -- --weird-flag       # escape hatch when the first\n"
            "                                    # forwarded arg would otherwise\n"
            "                                    # be parsed as the path\n"
            "  idc copilot ./proj -- --resume    # `--` between path and args is\n"
            "                                    # always allowed\n"
            "\n"
            "The first non-flag argument (if any) is the project path; "
            "everything else is forwarded verbatim to `copilot` inside the "
            "container. Use `--` to disambiguate when needed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_copilot.add_argument(
        "copilot_path",
        nargs="?",
        default=".",
        metavar="path",
        help="project folder (default: current directory)",
    )
    p_copilot.add_argument(
        "copilot_args",
        nargs=argparse.REMAINDER,
        metavar="-- copilot args...",
        help="arguments forwarded verbatim to `copilot` inside the container",
    )

    p_doctor = subparsers.add_parser(
        "doctor",
        help="diagnose the local environment for idc",
        description="Diagnose the local environment for idc and report issues.",
    )
    p_doctor.add_argument(
        "doctor_path",
        nargs="?",
        default=None,
        metavar="path",
        help="directory to inspect (default: current directory)",
    )

    p_update = subparsers.add_parser(
        "update",
        help="upgrade idc via 'uv tool upgrade indevcontainer'",
        description=(
            "Upgrade the installed idc tool via "
            "'uv tool upgrade indevcontainer'."
        ),
    )
    p_update.add_argument(
        "--check",
        action="store_true",
        help="check for an available update without installing it",
    )

    return parser


def _split_copilot_args(args: list[str]) -> tuple[str, list[str]]:
    """Split raw ``idc copilot`` argv into ``(path, forwarded_args)``.

    The first non-flag token (if any) is treated as the project path;
    everything else is forwarded verbatim to ``copilot`` inside the
    container. A literal ``--`` separator is honored both at the start
    (when the user wants to forward a leading non-flag arg that would
    otherwise be parsed as the path) and between the path and the
    forwarded args. The separator is stripped from the forwarded list.
    """
    if not args:
        return (".", [])
    if args[0] == "--":
        return (".", args[1:])
    if not args[0].startswith("-"):
        path = args[0]
        rest = args[1:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        return (path, rest)
    return (".", list(args))


def main() -> None:
    raw = sys.argv[1:]

    # Special-case `idc copilot` so flags like `--yolo` / `--resume` forward
    # to the in-container `copilot` invocation without requiring an explicit
    # `--` separator. argparse would otherwise reject unknown flags.
    if raw[:1] == ["copilot"]:
        copilot_argv = raw[1:]
        if copilot_argv and copilot_argv[0] in ("-h", "--help"):
            # Defer to argparse for help rendering so it stays in sync with
            # the subparser definition. parse_args() exits via SystemExit.
            _build_parser().parse_args(["copilot", "-h"])
            return

        from indevcontainer.copilot import run_copilot

        path, extra_args = _split_copilot_args(copilot_argv)
        sys.exit(run_copilot(path, extra_args=extra_args))

    parser = _build_parser()
    args = parser.parse_args(raw)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "code":
        run_code(args.code_path, insiders=args.insiders)
        return

    if args.command == "shell":
        shell_override = args.shell_override
        if shell_override is not None and (
            shell_override.strip() != shell_override or any(c.isspace() for c in shell_override)
        ):
            parser.error(
                "--shell must be a single executable path or name (no arguments); "
                "use VS Code terminal profile args for that"
            )
        from indevcontainer.shell import run_shell

        sys.exit(
            run_shell(
                args.shell_path,
                insiders=args.insiders,
                shell_override=shell_override,
            )
        )

    if args.command == "doctor":
        path = Path(args.doctor_path) if args.doctor_path else Path.cwd()
        sys.exit(run_doctor(path))

    if args.command == "update":
        if args.check:
            sys.exit(run_update_check())
        sys.exit(run_update())
