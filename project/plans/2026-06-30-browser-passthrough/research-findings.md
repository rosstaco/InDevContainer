# Research Findings — host-browser passthrough for `idc shell` / `idc copilot`

Scope: make CLIs that "spawn the host browser" for OAuth (`az`, `gh`, `glab`,
`snowflake`, …) work inside `idc shell` / `idc copilot` the way they do in a
VS Code integrated terminal.

This is the same architectural pattern as the 2026-05-27 `dcode-shell-host-bridges`
research: **piggyback on VS Code's live remote infrastructure, don't replace
it.** Browser passthrough and the `code` CLI shim both fall out of the same
discovery.

## How VS Code does it (verified against `microsoft/vscode`)

When a VS Code window is connected to the dev container, its terminal env
contains:

- `BROWSER=<server>/bin/helpers/browser-linux.sh`
- `VSCODE_IPC_HOOK_CLI=/tmp/vscode-ipc-<uuid>.sock`
- `PATH` prepended with `<server>/bin/remote-cli/` (the `code` / `code-insiders`
  shims)

`browser-linux.sh` (from `resources/server/bin/helpers/`) is just:

```sh
ROOT="$(dirname "$(dirname "$(dirname "$(readlink -f "$0")")")")"
"$ROOT/node" "$ROOT/out/server-cli.js" <app> <ver> <commit> <exec> --openExternal "$@"
```

`server-cli.js` connects to `VSCODE_IPC_HOOK_CLI` and asks the connected VS
Code (on the host) to open the URL. VS Code **also** auto-forwards container
`localhost:<port>` to the host, so redirect-style OAuth
(browser → `http://localhost:<port>/callback` → the CLI's in-container
listener) completes. Both halves — browser-open and port-forward — are handled
for free **when VS Code is connected**.

`<server>` is `~/.vscode-server` (stable) or `~/.vscode-server-insiders`.
Older builds named the helper `browser.sh`; newer ones use
`browser-{linux,darwin}.sh` + `browser.cmd`.

## CLI compatibility

Most relevant CLIs honor `$BROWSER`, so matching VS Code's `$BROWSER` reaches
parity:

- `az`, `snowflake` — Python `webbrowser`, honors `$BROWSER`.
- `gh`, `glab` — `cli/browser` / `pkg/browser`, checks `$BROWSER` first.

### Tools that ignore `$BROWSER` (e.g. Atlassian `acli`) — verified from binaries

Some CLIs call `xdg-open` directly and never consult `$BROWSER`. Proven by
inspecting both `acli` binaries (macOS + `acli_linux_amd64`):

- `acli` is Go; opens via its own `atlassian.com/cli/pkg/utils.OpenBrowser`
  (no standard browser lib).
- macOS build → `open <url>`; Linux build → bare `xdg-open <url>`.
- **Zero** `$BROWSER` references; no fallback chain (no gio/x-www-browser/…).

VS Code only sets `$BROWSER` and does **not** shim `xdg-open`, so these tools
fail even in a plain VS Code terminal — and our `$BROWSER`-only Tier-1 wouldn't
catch them either. Symptom: works on the Mac host, silent no-op in the
container.

**Fix (implemented):** because `acli` calls *bare* `xdg-open` (PATH-resolved),
`idc` materializes an `xdg-open` shim (plus `x-www-browser` / `gnome-open` /
`gnome-www-browser` / `sensible-browser` / `www-browser` aliases) in a per-user
temp dir at process start and prepends it to `PATH`; each shim `exec`s the VS
Code browser helper. This makes `idc` strictly better than a plain VS Code
terminal for such tools. Verified end-to-end by executing the generated wrapper
with a real shell. See `_path_wrapper_argv` in `src/indevcontainer/shell.py`.

## What `idc` must do — same parasitic trick as `find_ssh_socket`

`find_ssh_socket` (`src/indevcontainer/shell.py`) already discovers VS Code's
relay socket and injects it via `docker exec -e SSH_AUTH_SOCK=...`. Mirror it:

1. **IPC socket** — newest `/tmp/vscode-ipc-*.sock`, confirmed with `test -S`.
2. **Browser helper** — newest
   `$HOME/.vscode-server*/bin/*/bin/helpers/browser-linux.sh` (fallback
   `browser.sh`), confirmed `-x`.
3. **remote-cli dir** — newest `$HOME/.vscode-server*/bin/*/bin/remote-cli`,
   confirmed `-d`.

`$HOME` may be unset under `docker exec -u`, so resolve it inside the probe:
`h="${HOME:-$(getent passwd "$(id -u)" | cut -d: -f6)}"`.

Inject:

- `-e VSCODE_IPC_HOOK_CLI=<sock>` and `-e BROWSER=<helper>` (both subcommands).
- For `idc shell` only, prepend remote-cli to PATH so `code` resolves. A fresh
  `docker exec` does **not** inherit VS Code's terminal PATH, and the shell runs
  interactive-non-login (no `/etc/profile`), so wrap the exec:
  `<shell> -c 'export PATH="<remote-cli>:$PATH"; exec <shell> <args>'`
  (`$PATH` expands in-container; `shlex.quote` the parts). `idc copilot`
  forwards args verbatim, so it gets the browser env only — no wrapper.

## Caveats / non-goals

- **Requires VS Code connected.** No connected window → no IPC socket → no
  passthrough and no `code`. Same UX as today's SSH forwarding; emit a one-line
  stderr hint.
- **No VS-Code-independent relay in this change.** A host opener server +
  `host.docker.internal` shim + dynamic callback-port proxy is feasible but a
  real engineering project (host process lifecycle, cross-platform reachability
  — Docker Desktop reaches host `127.0.0.1`, Linux needs the gateway IP and a
  bridge-bound, token-gated listener — plus host→container port forwarding for
  redirect OAuth). Deferred, exactly as the 2026-05-27 doc deferred the
  equivalent SSH relay. Device-code flows would need only the opener.
