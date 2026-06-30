"""Tests for indevcontainer.copilot."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from indevcontainer.copilot import _copilot_installed, run_copilot
from indevcontainer.shell import ContainerExec


def _completed(rc: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


def _make_ctx(
    *,
    container_id: str = "abc123",
    exec_user: str | None = "node",
    workdir: str | None = "/workspaces/proj",
    ssh_sock: str | None = "/tmp/vscode-ssh-auth.sock",
    vscode_ipc: str | None = None,
    browser_helper: str | None = None,
    remote_cli_dir: str | None = None,
) -> ContainerExec:
    return ContainerExec(
        container_id=container_id,
        exec_user=exec_user,
        workdir=workdir,
        ssh_sock=ssh_sock,
        workspace_folder="/workspaces/proj",
        devcontainer_cfg={},
        main_repo=Path("/tmp/proj"),
        rel_path=None,
        vscode_ipc=vscode_ipc,
        browser_helper=browser_helper,
        remote_cli_dir=remote_cli_dir,
    )


# ---------------------------------------------------------------------------
# _copilot_installed
# ---------------------------------------------------------------------------


class TestCopilotInstalled:
    def test_returns_true_when_command_v_succeeds(self):
        ok = _completed(rc=0, stdout="/usr/local/bin/copilot\n")
        with patch("indevcontainer.copilot.subprocess.run", return_value=ok) as run:
            assert _copilot_installed("abc123", "node") is True
        args = run.call_args[0][0]
        assert args[:5] == ["docker", "exec", "-u", "node", "abc123"]
        # The probe always invokes a shell so PATH is resolved.
        assert args[-3:] == ["sh", "-c", "command -v copilot"]

    def test_returns_false_when_exit_nonzero(self):
        not_found = _completed(rc=1, stdout="")
        with patch("indevcontainer.copilot.subprocess.run", return_value=not_found):
            assert _copilot_installed("abc123", "node") is False

    def test_returns_false_when_stdout_empty(self):
        # Some shells print nothing but exit 0 when the command is missing.
        empty_ok = _completed(rc=0, stdout="\n")
        with patch("indevcontainer.copilot.subprocess.run", return_value=empty_ok):
            assert _copilot_installed("abc123", "node") is False

    def test_returns_false_when_docker_missing(self):
        with patch(
            "indevcontainer.copilot.subprocess.run",
            side_effect=FileNotFoundError("no docker"),
        ):
            assert _copilot_installed("abc123", "node") is False

    def test_omits_user_flag_when_no_exec_user(self):
        ok = _completed(rc=0, stdout="/bin/copilot\n")
        with patch("indevcontainer.copilot.subprocess.run", return_value=ok) as run:
            assert _copilot_installed("abc123", None) is True
        args = run.call_args[0][0]
        assert args[:3] == ["docker", "exec", "abc123"]
        assert "-u" not in args


# ---------------------------------------------------------------------------
# run_copilot
# ---------------------------------------------------------------------------


class TestRunCopilot:
    def test_returns_1_when_prepare_fails(self):
        with patch("indevcontainer.copilot.prepare_container_exec", return_value=None):
            assert run_copilot(".") == 1

    def test_fails_with_helpful_message_when_copilot_missing(self, capsys):
        ctx = _make_ctx()
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=False),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            rc = run_copilot(".")
        assert rc == 127
        execvp.assert_not_called()
        err = capsys.readouterr().err
        assert "idc:" in err
        assert "copilot" in err
        assert "not installed" in err

    def test_execs_docker_exec_copilot(self):
        ctx = _make_ctx()
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            rc = run_copilot(".")
        # 0 is only reached when execvp is mocked.
        assert rc == 0
        execvp.assert_called_once()
        prog, argv = execvp.call_args[0]
        assert prog == "docker"
        assert argv[:3] == ["docker", "exec", "-it"]
        assert "-u" in argv and "node" in argv
        assert "-w" in argv and "/workspaces/proj" in argv
        assert "-e" in argv
        assert "SSH_AUTH_SOCK=/tmp/vscode-ssh-auth.sock" in argv
        # container id comes before the command.
        assert "abc123" in argv
        assert argv[-1] == "copilot"

    def test_forwards_extra_args_to_copilot(self):
        ctx = _make_ctx(exec_user=None, workdir=None, ssh_sock=None)
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            run_copilot(".", extra_args=["--resume", "--allow-tool", "shell"])
        _, argv = execvp.call_args[0]
        assert argv == [
            "docker",
            "exec",
            "-it",
            "abc123",
            "copilot",
            "--resume",
            "--allow-tool",
            "shell",
        ]

    def test_omits_optional_flags_when_unset(self):
        ctx = _make_ctx(exec_user=None, workdir=None, ssh_sock=None)
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            run_copilot(".")
        _, argv = execvp.call_args[0]
        assert "-u" not in argv
        assert "-w" not in argv
        assert "-e" not in argv
        assert argv == ["docker", "exec", "-it", "abc123", "copilot"]

    def test_browser_env_forwarded(self):
        ctx = _make_ctx(
            exec_user=None,
            workdir=None,
            ssh_sock=None,
            vscode_ipc="/tmp/vscode-ipc-2.sock",
            browser_helper="/srv/helpers/browser-linux.sh",
        )
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            run_copilot(".", extra_args=["--resume"])
        _, argv = execvp.call_args[0]
        assert "VSCODE_IPC_HOOK_CLI=/tmp/vscode-ipc-2.sock" in argv
        assert "BROWSER=/srv/helpers/browser-linux.sh" in argv
        # A browser helper triggers the xdg-open shim wrapper; copilot is
        # exec'd inside it with its args forwarded verbatim.
        assert argv[-3] == "sh"
        assert argv[-2] == "-c"
        inner = argv[-1]
        assert "/srv/helpers/browser-linux.sh" in inner
        assert 'xdg-open' in inner
        assert inner.endswith("exec copilot --resume")

    def test_browser_shim_aliases_present(self):
        ctx = _make_ctx(
            exec_user=None,
            workdir=None,
            ssh_sock=None,
            browser_helper="/srv/browser-linux.sh",
        )
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            run_copilot(".")
        inner = execvp.call_args[0][1][-1]
        for alias in ("x-www-browser", "gnome-open", "sensible-browser"):
            assert alias in inner

    def test_remote_cli_dir_does_not_wrap_copilot(self):
        # The `code` PATH wrapper is a shell-only feature; copilot must exec
        # directly so its verbatim arg forwarding is preserved.
        ctx = _make_ctx(
            exec_user=None,
            workdir=None,
            ssh_sock=None,
            remote_cli_dir="/srv/remote-cli",
        )
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch("indevcontainer.copilot.os.execvp") as execvp,
        ):
            run_copilot(".")
        _, argv = execvp.call_args[0]
        assert argv == ["docker", "exec", "-it", "abc123", "copilot"]
        assert "sh" not in argv

    def test_returns_127_when_execvp_fails(self, capsys):
        ctx = _make_ctx()
        with (
            patch("indevcontainer.copilot.prepare_container_exec", return_value=ctx),
            patch("indevcontainer.copilot._copilot_installed", return_value=True),
            patch(
                "indevcontainer.copilot.os.execvp",
                side_effect=OSError("docker not found"),
            ),
        ):
            rc = run_copilot(".")
        assert rc == 127
        err = capsys.readouterr().err
        assert "idc:" in err
        assert "failed to exec docker" in err
