"""``idc copilot``: exec the GitHub Copilot CLI inside a devcontainer.

Shares container-resolution logic with ``idc shell`` via
:func:`indevcontainer.shell.prepare_container_exec` — the only difference is
the command we ``docker exec`` (and a fast-fail check that ``copilot`` is
actually installed in the target container).
"""

from __future__ import annotations

import os
import subprocess
import sys

from indevcontainer.shell import prepare_container_exec


def _copilot_installed(container_id: str, exec_user: str | None) -> bool:
    """Return True if the ``copilot`` binary is on PATH inside the container.

    Runs ``command -v copilot`` via ``sh -c`` (using the same user we'll
    ``docker exec`` as) so the PATH and login-environment match what the
    real exec will see.
    """
    argv = ["docker", "exec"]
    if exec_user:
        argv.extend(["-u", exec_user])
    argv.extend([container_id, "sh", "-c", "command -v copilot"])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def run_copilot(path: str, *, extra_args: list[str] | None = None) -> int:
    """Exec the GitHub Copilot CLI inside the devcontainer for ``path``.

    Resolves the running container exactly like ``idc shell`` (auto-building
    or prompting to start when needed), then ``os.execvp``s
    ``docker exec -it ... copilot <extra_args>``. ``extra_args`` is the
    pass-through argv from ``idc copilot <path> -- <copilot args>``.

    Returns an exit code suitable for ``sys.exit``. On success, replaces
    the process via ``os.execvp`` (the explicit ``return 0`` is only
    reachable when ``execvp`` is mocked in tests).
    """
    ctx = prepare_container_exec(path)
    if ctx is None:
        return 1

    if not _copilot_installed(ctx.container_id, ctx.exec_user):
        print(
            "idc: `copilot` is not installed in this devcontainer. "
            "Add it via a devcontainer Feature or install it inside the "
            "container (e.g. `npm install -g @github/copilot`), then re-run.",
            file=sys.stderr,
        )
        return 127

    argv: list[str] = ["docker", "exec", "-it"]
    if ctx.exec_user:
        argv.extend(["-u", ctx.exec_user])
    if ctx.workdir:
        argv.extend(["-w", ctx.workdir])
    if ctx.ssh_sock:
        argv.extend(["-e", f"SSH_AUTH_SOCK={ctx.ssh_sock}"])
    argv.append(ctx.container_id)
    argv.append("copilot")
    if extra_args:
        argv.extend(extra_args)

    try:
        os.execvp("docker", argv)
    except OSError as exc:
        print(f"idc: failed to exec docker: {exc}", file=sys.stderr)
        return 127

    return 0  # only reached when os.execvp is mocked in tests
