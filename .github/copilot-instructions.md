# Copilot Instructions for InDevContainer

## Build & Test

```bash
# Run all tests
uv run pytest

# Run a single test by name
uv run pytest -k test_resolves_worktree_with_relative_gitdir

# Run a test class
uv run pytest -k TestResolveWorktree
```

Linting is via `ruff` (`uv run ruff check`). Versioning is automated: `hatch-vcs` derives the version from the latest git tag, and [release-please](https://github.com/googleapis/release-please) manages tags + the changelog from [Conventional Commits](https://www.conventionalcommits.org/). **Do not** edit a version field in `pyproject.toml` or `src/indevcontainer/__init__.py` — both are derived from the git tag at install/build time via `importlib.metadata`.

## Architecture

InDevContainer is a Python CLI installed as the `idc` binary (package
`indevcontainer`). It constructs `vscode-remote://dev-container+<hex-encoded-host-path><workspace-folder>` URIs and launches VS Code with `--folder-uri`, or shells/copilot directly into running containers via `docker exec`. The entrypoint is `indevcontainer.cli:main`.

The CLI is subcommand-only — no top-level positional. Subcommands:

* `idc code [-i] <path>` — `indevcontainer.core.run_code`. Constructs the
  devcontainer URI and launches VS Code (or VS Code Insiders).
* `idc shell <path> [--shell EXE] [-i]` — `indevcontainer.shell.run_shell`.
  `docker exec -it`s into the project's running container with the resolved
  terminal profile.
* `idc copilot [<path>] [copilot-args...]` —
  `indevcontainer.copilot.run_copilot`. Same container resolution as
  `idc shell`, but execs `copilot` inside the container. **This subcommand
  bypasses argparse** (see `_split_copilot_args` in `cli.py`) so that
  arbitrary flags like `--yolo` / `--resume` forward to `copilot` without
  requiring a `--` separator. The first non-flag arg is the project path;
  `--` is honored as an optional explicit separator.
* `idc doctor [path]` — `indevcontainer.doctor.run_doctor`.
* `idc update [--check]` — `indevcontainer.update.{run_update, run_update_check}`.

Bare `idc` (no subcommand) prints `--help` and exits 0.

The container-resolution logic shared by `idc shell` and `idc copilot` lives
in `indevcontainer.shell.prepare_container_exec()`, which returns a
`ContainerExec` dataclass (container_id, exec_user, workdir, ssh_sock,
workspace_folder, devcontainer_cfg, main_repo, rel_path) or `None` on error
(after printing a hint to stderr).

The core flow in `run_code()`:

1. **Worktree detection** — `resolve_worktree()` checks if `.git` is a file (not directory), parses the `gitdir:` pointer, and validates the path structure to distinguish worktrees from submodules. When the gitdir contains an absolute path from a different environment (e.g. a container), it falls back to walking ancestor directories for the real `.git` dir.
2. **Config lookup** — `find_devcontainer()` searches for `.devcontainer/devcontainer.json` or `.devcontainer.json` in the target (or main repo for worktrees).
3. **URI construction** — Two codepaths: `build_uri()` for native systems (hex-encodes the host path directly) and `build_uri_wsl()` for WSL (wraps a Windows UNC path in a JSON payload). For worktrees, the host path is always the main repo root so all worktrees share one container.

## Conventions

- `json5` is used to parse `devcontainer.json` (supports JSONC comments and trailing commas).
- All user-facing messages go to `sys.stderr` and are prefixed with `idc:`. Stdout is reserved for machine output.
- Tests use `tmp_path` fixtures with mock filesystem layouts (fake `.git` files/dirs) — no real git repos needed. `subprocess.run` is always patched in integration tests.
- The helper `_make_worktree(tmp_path, name)` in the test file creates a complete fake main-repo + worktree layout for test reuse.
- The CLI binary is `idc`; the Python package is `indevcontainer`. They differ on purpose: the short binary is for users, the longer package name is for `importlib.metadata` and `uv tool` (which use the project name from `pyproject.toml`).
