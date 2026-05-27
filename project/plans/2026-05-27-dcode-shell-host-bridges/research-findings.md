# Research Findings — `dcode shell` host bridges

Scope: ways to extend `dcode shell` so it does more of what a VS Code integrated terminal does, without requiring VS Code to be open. Two related but independent topics:

1. **SSH agent socket forwarding** — make `git push` / `ssh` work inside `dcode shell` without "open VS Code first".
2. **VS Code `code` CLI bridge** — make `code <path>` inside `dcode shell` open the file in the already-connected VS Code window.

Both topics arose from the question "is `dcode shell` doing something like `python-socks`?" — clarified to mean the SSH agent socket detection in `find_ssh_socket` (`src/dcode/shell.py:389`).

## Current state (status quo)

- `find_ssh_socket(container_id)` in `src/dcode/shell.py:389` probes `docker inspect`'s `Config.Env` for `SSH_AUTH_SOCK`, then falls back to `ls -t /tmp/vscode-ssh-auth*.sock | head -1`. If found, dcode injects it via `docker exec -e SSH_AUTH_SOCK=...`.
- The relay socket only exists while a VS Code client is actively connected to the container — VS Code creates it on connect and it dies when VS Code disconnects.
- README (`README.md:65-68`) documents the "open VS Code first" expectation.
- No equivalent exists today for the `code` CLI shim — `code <file>` inside `dcode shell` is unset/broken.

---

## Topic 1: SSH agent socket forwarding without VS Code

### Why VS Code's design works

VS Code's Remote-Containers runs a small Node relay inside the container at `/tmp/vscode-ssh-auth-<id>.sock` and forwards the SSH agent protocol over the existing docker-exec stdio tunnel back to the local VS Code process — which is simultaneously the **only thing** with access to the host's `$SSH_AUTH_SOCK` on macOS/Windows (where the host socket is outside Docker Desktop's VM).

This is meaningfully better than the legacy devcontainer patterns:

- **Bind-mount `~/.ssh`** → leaks private keys into the container filesystem (any process can read them).
- **Bind-mount `$SSH_AUTH_SOCK`** → Linux-only; host sockets are not reachable through Docker Desktop's VM boundary on Mac/Windows.
- **Relay (VS Code's approach)** → cross-platform (rides existing docker-exec stdio), keys never leave the host, composes with hardware keys / 1Password / gpg-agent, dynamic (new keys immediately available).

### Why we can't borrow VS Code Server for this

Pre-installing or pre-starting VS Code Server **does not** make the SSH socket appear, because the socket is fundamentally a proxy that needs three live pieces:

1. A server in the container listening at the socket. ✓ (pre-startable)
2. A live tunnel between server and client. ✗ (needs VS Code connected)
3. A client process on the host that can reach `$SSH_AUTH_SOCK`. ✗ (only the local VS Code desktop process has that)

`code tunnel` (the official standalone CLI) has the same problem — its "clients" are browsers or remote VS Code instances, neither of which can reach the local host's SSH agent.

The only way to use VS Code Server as the in-container component would be to write a dcode-side client that connects to the Server and provides the host-side relay — i.e., reverse-engineer VS Code's private remote-server protocol. Not stable, not documented, breaks on VS Code updates. Not viable.

### Failure mode for "existing shell" if we pre-start the server

Walked through end-to-end:

1. `dcode shell` does `docker exec -e SSH_AUTH_SOCK=<value> -it ...`. The env var is fixed for the lifetime of the shell.
2. If VS Code is not yet connected, no working socket exists. Either `SSH_AUTH_SOCK` is unset (`git` has no agent), or set to a predicted path (`connect()` fails or hangs because there's no other end of the tunnel).
3. When VS Code later connects, the socket starts working — but only for shells started **after** the predicted path becomes live, and only while VS Code stays connected. As soon as VS Code disconnects, the tunnel dies and the shell breaks again.

So pre-starting VS Code Server gives at best **fragile, intermittently-working** SSH auth that flips based on whether VS Code is currently connected — worse UX than the current "open VS Code first, then `dcode shell` reuses the socket" pattern.

### Viable alternatives if we ever want to eliminate the VS Code dependency

| Approach | Works on | Cost | Notes |
|---|---|---|---|
| Bind-mount `$SSH_AUTH_SOCK` via `runArgs`/`mounts` | Linux host only | low | Needs container recreate; useless on Mac/Windows |
| Roll our own relay (`socat`) | All platforms | medium | Requires `socat` in container (missing in alpine/distroless); ~20 LOC orchestration in dcode |
| Roll our own relay (tiny Go binary, `docker cp` in) | All platforms | medium-high | Zero in-container deps; ~150 LOC Go + lifecycle code in dcode |
| Roll our own relay (Python + `paramiko.agent`) | Container with Python | medium | Most images have Python but not all |

The genuine difficulty in all "roll our own" options is **not** the bytes-mover (the SSH agent protocol is just opaque request/response blobs) — it's the **lifecycle**: start helper on first `dcode shell`, reuse on subsequent ones, detect container restart (stale socket), clean up on exit, surface failures, and handle the cross-platform host-side `$SSH_AUTH_SOCK` location (Windows named pipes vs Unix sockets).

### Ecosystem survey: existing libs/tools

- **Building blocks for the protocol**: `paramiko.agent` (Python), `asyncssh.SSHAgentClient` (Python), `golang.org/x/crypto/ssh/agent` (Go, standard). Mature, well-tested.
- **`socat`**: the de-facto runtime answer. Two-line recipe (host listener + docker-exec'd in-container counterpart). Needs socat installed inside the container.
- **VS Code Server / `code-server` (Coder) / `code tunnel`**: all bundled, none reusable as libraries.
- **Docker BuildKit `--ssh default`** and **`docker run --mount type=ssh`**: build-time only — does not help `docker exec`.
- **`devcontainers/cli` exec**: no relay; relies entirely on whatever `mounts:` the user wrote in `devcontainer.json`.
- **Standalone GitHub projects** (`docker-ssh-agent-forward` etc.): several exist, none well-maintained, none with meaningful adoption — all are `socat` wrappers or ~100 LOC of Go. Forking the code is safer than depending on them.
- **`gh codespace ssh`**: uses real SSH with `-A`; different connection model, not applicable to `docker exec`.

**Conclusion:** no off-the-shelf "agent-forward-into-docker" library exists that we'd want to depend on. The protocol part is trivial; the integration glue is environment-specific and would have to live in dcode regardless.

### Recommendation for topic 1

**Do not build this now.** The status quo (detect VS Code's socket, warn if missing) is ~40 lines and zero runtime cost. Replacing it is a real feature (~150–300 LOC + ongoing platform support) for a niche win: "you don't have to open VS Code first." Given dcode's positioning as a launcher into devcontainer-based VS Code workflows, that's a small benefit.

If we ever do build it, the cheap MVP path is **`socat` recipe with a clear error if socat is missing in the container**, gated behind a flag. The Go-binary path is the right long-term answer but is materially more work.

---

## Topic 2: VS Code `code` CLI bridge

This one is the opposite — **cheap, high-value, no lifecycle headaches**.

### How VS Code does it

When VS Code's terminal opens inside a remote container, it injects two things into the shell environment:

1. **`VSCODE_IPC_HOOK_CLI=/tmp/vscode-ipc-<uuid>.sock`** — a Unix socket the connected VS Code window is listening on.
2. **`PATH` prepended with `~/.vscode-server/bin/<sha>/bin/remote-cli/`** — which contains tiny `code` and `code-insiders` shell scripts.

The `code` script is a thin wrapper around VS Code's bundled Node binary that writes a JSON-RPC message to `VSCODE_IPC_HOOK_CLI` saying "please open this file/folder." VS Code on the host receives it and acts on it (opens a tab in the connected window, or a diff view, etc.).

For Insiders, the equivalents are `~/.vscode-server-insiders/` and `VSCODE_IPC_HOOK_CLI` points at a different socket.

### What dcode can do — same parasitic trick as SSH

Mirror `find_ssh_socket` with a `find_vscode_ipc()`-style helper:

```python
# Probe newest socket
ls -t /tmp/vscode-ipc-*.sock | head -1
# Probe newest remote-cli dir (handle stable + insiders)
ls -td ~/.vscode-server/bin/*/bin/remote-cli | head -1
ls -td ~/.vscode-server-insiders/bin/*/bin/remote-cli | head -1
```

Then in `run_shell` inject:

- `-e VSCODE_IPC_HOOK_CLI=<socket>`
- PATH prepend with the `remote-cli` dir

Note: `docker exec -e PATH=...` sets a literal value, so PATH-prepending needs a small wrapper — easiest is wrapping the shell invocation as `bash -c 'export PATH=<remote-cli>:$PATH; exec "$SHELL" -l'` (or similar) rather than relying on `-e`. Alternative: drop a `bashrc.d/` snippet. The wrapper approach is cleaner because it works regardless of user's shell.

### Caveats (mostly the same shape as SSH discovery)

- **Requires VS Code already connected.** No VS Code → no socket → `code` not available (or available-but-broken). Same "open VS Code first" expectation as today's SSH behavior. Intuitive failure: `code` is simply absent on PATH.
- **Multiple connected VS Code windows** to the same container: pick newest socket. `code .` opens in that window.
- **Version drift in `~/.vscode-server/bin/<sha>`**: usually only one dir; pick newest if multiple. The shim is self-contained per-commit, so just always grab the newest `remote-cli` from the same family (stable or insiders).
- **Stable vs Insiders**: `~/.vscode-server-insiders/` path. Pick based on `dcode shell --insiders` flag (mirror the existing flag plumbing).
- **Architecture**: not a concern — `remote-cli/code` is a shell script, the bundled `node` it invokes is architecture-matched at install time by VS Code itself.

### What this does NOT solve

- **`dcode <path>` from inside the container** — i.e., the full dcode pipeline (worktree resolution, devcontainer.json discovery, URI construction, auto-build). That would require a host-side relay listening for "run `dcode X`" requests from the container — same plumbing as the SSH-agent-relay discussion above. Out of scope.

| Inside `dcode shell` after this feature | Works? |
|---|---|
| `code .` (open current container folder in connected VS Code) | ✓ |
| `code path/to/file` | ✓ |
| `code --diff a.txt b.txt` | ✓ |
| `code` when no VS Code is open | ✗ (intuitive — shim is absent) |
| `dcode <path>` (full dcode pipeline from inside container) | ✗ (needs host-side relay) |

### Recommendation for topic 2

**Build this.** Small surface area (~30 LOC mirroring `find_ssh_socket`), no new deps, no lifecycle concerns (we're not standing up any helper processes — we're just pointing the shell at infrastructure VS Code already runs). Failure mode is intuitive (no VS Code → `code` is absent, same conceptual model as today's SSH behavior).

Open design questions if/when this becomes a task:

- PATH injection mechanism: `bash -c` wrapper vs `rcfile` drop-in vs accept that user must source something. **Wrapper is recommended** — works across shells, no on-disk state.
- Whether to also expose any other VS Code-injected env vars (`VSCODE_GIT_IPC_HANDLE` for the git extension, `BROWSER`, etc.). Probably no — `VSCODE_IPC_HOOK_CLI` + the `code` shim is the 95% case. Revisit if specific use cases come up.
- Whether `dcode shell` should print an informational hint when the IPC socket is detected ("`code` command available — opens in connected VS Code window"), mirroring the SSH warning style.

---

## Cross-topic summary

| Feature | Cost | Win | Lifecycle burden | Build now? |
|---|---|---|---|---|
| SSH agent forwarding without VS Code | High (~150–300 LOC + platform matrix) | Niche (skip "open VS Code first" for SSH) | Yes — long-lived helper, cleanup, platform-specific | **No** |
| `code` CLI bridge in `dcode shell` | Low (~30 LOC) | Material QoL inside shell | None — just env-var injection | **Yes** (when prioritized) |

Both topics share the same architectural insight: **VS Code's remote infrastructure is the right thing to piggyback on, not to replace.** Wherever VS Code already runs something useful in the container, dcode can detect it and inject the right env vars. Wherever VS Code does *not* run something, replacing it ourselves is a real engineering project, not a config tweak.
