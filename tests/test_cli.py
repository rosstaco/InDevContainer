"""Tests for the idc CLI entrypoint and package metadata."""

from pathlib import Path
from unittest.mock import patch

import pytest

import indevcontainer
from indevcontainer import cli


class TestVersion:
    def test_resolves_via_importlib_metadata(self):
        from importlib.metadata import version

        assert indevcontainer.__version__ == version("indevcontainer")


class TestNoSubcommand:
    def test_bare_idc_prints_help_and_exits_zero(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["idc"])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out.lower()
        # All five subcommands should appear in the help output.
        for cmd in ("code", "shell", "copilot", "doctor", "update"):
            assert cmd in out


class TestCodeDispatch:
    def test_code_no_args_opens_cwd(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "code"])
        with patch("indevcontainer.cli.run_code") as m_run:
            cli.main()
        m_run.assert_called_once_with(".", insiders=False)

    def test_code_with_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.argv", ["idc", "code", str(tmp_path)])
        with patch("indevcontainer.cli.run_code") as m_run:
            cli.main()
        m_run.assert_called_once_with(str(tmp_path), insiders=False)

    def test_code_insiders_flag_short(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.argv", ["idc", "code", "-i", str(tmp_path)])
        with patch("indevcontainer.cli.run_code") as m_run:
            cli.main()
        m_run.assert_called_once_with(str(tmp_path), insiders=True)

    def test_code_insiders_flag_long(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "code", "--insiders"])
        with patch("indevcontainer.cli.run_code") as m_run:
            cli.main()
        m_run.assert_called_once_with(".", insiders=True)

    def test_code_can_open_folder_named_like_subcommand(self, monkeypatch):
        # idc code ./shell opens a folder literally named "shell", not the
        # shell subcommand. This is the documented escape hatch.
        monkeypatch.setattr("sys.argv", ["idc", "code", "./shell"])
        with patch("indevcontainer.cli.run_code") as m_run:
            cli.main()
        m_run.assert_called_once_with("./shell", insiders=False)


class TestUpdateDispatch:
    def test_update_calls_run_update(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "update"])
        with (
            patch("indevcontainer.cli.run_update", return_value=0) as m_upd,
            patch("indevcontainer.cli.run_update_check") as m_chk,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 0
        m_upd.assert_called_once_with()
        m_chk.assert_not_called()

    def test_update_check(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "update", "--check"])
        with (
            patch("indevcontainer.cli.run_update_check", return_value=1) as m_chk,
            patch("indevcontainer.cli.run_update") as m_upd,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 1
        m_chk.assert_called_once_with()
        m_upd.assert_not_called()

    def test_update_exit_code_forwarded(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "update"])
        with (
            patch("indevcontainer.cli.run_update", return_value=42),
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 42


class TestDoctorDispatch:
    def test_doctor_no_args(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["idc", "doctor"])
        with (
            patch("indevcontainer.cli.run_doctor", return_value=0) as m_doc,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 0
        m_doc.assert_called_once_with(Path.cwd())

    def test_doctor_with_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.argv", ["idc", "doctor", str(tmp_path)])
        with (
            patch("indevcontainer.cli.run_doctor", return_value=0) as m_doc,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_doc.assert_called_once_with(Path(str(tmp_path)))

    def test_doctor_exit_code_forwarded(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "doctor"])
        with (
            patch("indevcontainer.cli.run_doctor", return_value=1),
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 1


class TestShellDispatch:
    """Dispatch tests for ``idc shell``.

    ``run_shell`` is lazy-imported inside ``cli.main()`` via
    ``from indevcontainer.shell import run_shell``, so it MUST be patched
    at ``indevcontainer.shell.run_shell``.
    """

    def test_shell_no_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 0
        m_run.assert_called_once_with(".", insiders=False, shell_override=None)

    def test_shell_with_path(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "./project"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(
            "./project", insiders=False, shell_override=None
        )

    def test_shell_with_shell_override(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "--shell", "zsh"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(".", insiders=False, shell_override="zsh")

    def test_shell_with_path_and_shell_override(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv", ["idc", "shell", "./path", "--shell", "bash"]
        )
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(
            "./path", insiders=False, shell_override="bash"
        )

    def test_shell_insiders_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "-i"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(".", insiders=True, shell_override=None)

    def test_shell_insiders_long_form(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "--insiders"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(".", insiders=True, shell_override=None)

    def test_shell_override_with_internal_whitespace_rejected(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "--shell", "bash -l"])
        with (
            patch("indevcontainer.shell.run_shell") as m_run,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "single executable" in err or "whitespace" in err.lower()
        m_run.assert_not_called()

    def test_shell_override_with_leading_whitespace_rejected(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "--shell", " zsh"])
        with (
            patch("indevcontainer.shell.run_shell") as m_run,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "single executable" in err or "whitespace" in err.lower()
        m_run.assert_not_called()

    def test_shell_exit_code_forwarded(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "shell"])
        with (
            patch("indevcontainer.shell.run_shell", return_value=127),
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 127

    def test_shell_subcommand_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["idc", "shell", "--help"])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--shell" in out
        assert "devcontainer" in out.lower()


class TestCopilotDispatch:
    """Dispatch tests for ``idc copilot``.

    ``run_copilot`` is lazy-imported inside ``cli.main()``, so it MUST be
    patched at ``indevcontainer.copilot.run_copilot``. Note: ``idc copilot``
    bypasses argparse so that arbitrary flags (``--yolo``, ``--resume``,
    etc.) forward to copilot without requiring a ``--`` separator.
    """

    def test_copilot_no_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "copilot"])
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 0
        m_run.assert_called_once_with(".", extra_args=[])

    def test_copilot_with_path(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "copilot", "./project"])
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with("./project", extra_args=[])

    def test_copilot_inline_flags_without_path(self, monkeypatch):
        # Primary new behavior: `idc copilot --yolo --resume` forwards
        # both flags to copilot, with path defaulting to ".".
        monkeypatch.setattr(
            "sys.argv", ["idc", "copilot", "--yolo", "--resume"]
        )
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(".", extra_args=["--yolo", "--resume"])

    def test_copilot_path_then_inline_flags(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv", ["idc", "copilot", "./proj", "--yolo", "--resume"]
        )
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(
            "./proj", extra_args=["--yolo", "--resume"]
        )

    def test_copilot_with_double_dash_separator(self, monkeypatch):
        # The `--` escape hatch still works for the rare case where the
        # first forwarded arg would otherwise be parsed as the path.
        monkeypatch.setattr(
            "sys.argv", ["idc", "copilot", ".", "--", "--resume"]
        )
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(".", extra_args=["--resume"])

    def test_copilot_double_dash_first_forwards_all(self, monkeypatch):
        # `idc copilot -- weird-positional --flag` forces "." as the path
        # and forwards everything else verbatim.
        monkeypatch.setattr(
            "sys.argv",
            ["idc", "copilot", "--", "weird-positional", "--flag"],
        )
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(
            ".", extra_args=["weird-positional", "--flag"]
        )

    def test_copilot_with_multiple_passthrough_args(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv",
            ["idc", "copilot", "./proj", "--allow-tool", "shell"],
        )
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=0) as m_run,
            pytest.raises(SystemExit),
        ):
            cli.main()
        m_run.assert_called_once_with(
            "./proj", extra_args=["--allow-tool", "shell"]
        )

    def test_copilot_exit_code_forwarded(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["idc", "copilot"])
        with (
            patch("indevcontainer.copilot.run_copilot", return_value=127),
            pytest.raises(SystemExit) as exc,
        ):
            cli.main()
        assert exc.value.code == 127

    def test_copilot_subcommand_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["idc", "copilot", "--help"])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "copilot" in out.lower()
        assert "devcontainer" in out.lower()

    def test_copilot_short_help_flag(self, monkeypatch, capsys):
        # `-h` should also trigger help and NOT be forwarded.
        monkeypatch.setattr("sys.argv", ["idc", "copilot", "-h"])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out.lower()


class TestSplitCopilotArgs:
    def test_empty(self):
        assert cli._split_copilot_args([]) == (".", [])

    def test_only_double_dash(self):
        assert cli._split_copilot_args(["--"]) == (".", [])

    def test_leading_double_dash_forwards_all(self):
        assert cli._split_copilot_args(["--", "--help"]) == (".", ["--help"])

    def test_first_flag_no_path(self):
        assert cli._split_copilot_args(["--yolo", "--resume"]) == (
            ".",
            ["--yolo", "--resume"],
        )

    def test_first_short_flag_no_path(self):
        assert cli._split_copilot_args(["-v"]) == (".", ["-v"])

    def test_first_token_is_path(self):
        assert cli._split_copilot_args(["./proj"]) == ("./proj", [])

    def test_path_then_flags(self):
        assert cli._split_copilot_args(["./proj", "--yolo"]) == (
            "./proj",
            ["--yolo"],
        )

    def test_path_then_double_dash_then_flags(self):
        assert cli._split_copilot_args(["./proj", "--", "--yolo"]) == (
            "./proj",
            ["--yolo"],
        )

    def test_path_then_double_dash_only(self):
        assert cli._split_copilot_args(["./proj", "--"]) == ("./proj", [])
