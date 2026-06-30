# Plan — host-browser passthrough + `code` shim

See `research-findings.md` for the verified VS Code mechanism. Tier-1
(piggyback) only; the VS-Code-independent relay is explicitly out of scope.

## Goal

When a VS Code window is connected to the dev container, `idc shell` and
`idc copilot` reproduce VS Code's terminal env so host-browser OAuth works, and
`idc shell` additionally exposes the `code` CLI shim.

## Changes (all in `src/indevcontainer/`)

1. **`shell.py` — `find_vscode_bridges(container_id, exec_user)`**
   Returns `VSCodeBridges(ipc_sock, browser_helper, remote_cli_dir)` (each
   `str | None`). One combined `docker exec [-u user] sh -c '…'` probe that
   resolves `$HOME`, then `ls -t … | head -1` + `test`-validates each of the
   three paths, printing exactly three (possibly empty) lines. Mirrors
   `find_ssh_socket`'s structure and test style.

2. **`shell.py` — `ContainerExec`** gains `vscode_ipc`, `browser_helper`,
   `remote_cli_dir`. `prepare_container_exec` calls `find_vscode_bridges` and
   populates them. When the IPC socket isn't found, print a single concise
   stderr hint (passthrough/`code` need VS Code connected), styled like the
   existing SSH hint.

3. **`shell.py` — `run_shell`** injects `-e VSCODE_IPC_HOOK_CLI=…` and
   `-e BROWSER=…` when present, then wraps the shell via the shared
   `_path_wrapper_argv()` (POSIX `sh -c`) which prepends, in-container: an
   `xdg-open` shim (+ aliases) that `exec`s the browser helper — for tools that
   ignore `$BROWSER` like `acli` — and VS Code's `remote-cli` dir so `code`
   resolves. No bridges ⇒ argv identical to today.

4. **`copilot.py` — `run_copilot`** injects the same browser env and uses
   `_path_wrapper_argv(..., remote_cli_dir=None)` — it gets the `xdg-open` shim
   (browser logins from tools copilot runs reach the host) but not the
   shell-only `code` shim. No bridges ⇒ exec's `copilot` directly, preserving
   verbatim arg forwarding.

5. **`README.md`** — extend the SSH-forwarding section: host-browser
   passthrough + `code` shim, same "VS Code connected" caveat.

## Tests (`tests/test_shell.py`, `tests/test_copilot.py`)

- `TestFindVscodeBridges` mirroring `TestFindSshSocket`: all-found,
  partial (e.g. ipc only), none-found, `$HOME`-unset path. Mock
  `subprocess.run` with `_completed(0, "ipc\nbrowser\nremotecli\n", "")`.
- `run_shell`: assert `BROWSER=…` and `VSCODE_IPC_HOOK_CLI=…` in argv; assert
  the PATH wrapper appears when remote-cli found and is absent otherwise;
  assert argv unchanged when no bridges.
- `run_copilot`: assert browser env injected; assert no PATH wrapper.
- Hint-on-miss assertion via `capsys`.

## Acceptance criteria

- `uv run ruff check` and `uv run pytest` green.
- With VS Code connected: `BROWSER` + `VSCODE_IPC_HOOK_CLI` set in both
  subcommands; `code` resolves in `idc shell`.
- Without VS Code: no new env, argv unchanged, one concise hint printed.

## Out of scope

- VS-Code-independent host relay / port-callback proxy (future, flag-gated).
- `xdg-open` shimming for tools that ignore `$BROWSER` (VS Code doesn't either).
