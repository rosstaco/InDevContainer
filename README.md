# InDevContainer 🚀

Run code, shells, and the GitHub Copilot CLI inside VS Code devcontainers — straight from your terminal.

> Renamed from `dcode`. Same project, new name and a broader scope. The CLI binary is now `idc`.

## 📦 Install

```bash
uv tool install git+https://github.com/rosstaco/InDevContainer
```

If you have the old `dcode` tool installed, remove it first:

```bash
uv tool uninstall dcode
```

## 🔧 Quick start

```bash
# Open current folder in VS Code via its devcontainer (was: dcode .)
idc code .

# Open a specific path
idc code /path/to/project

# Use VS Code Insiders
idc code -i .

# Drop into an interactive shell inside the running devcontainer
idc shell

# Run the GitHub Copilot CLI inside the running devcontainer
idc copilot --yolo --resume
```

If the folder has no `.devcontainer/devcontainer.json`, `idc code` falls back to plain `code <path>`.

## 🛠 Commands

### `idc code [-i] <path>`

Open `<path>` (default: current directory) in VS Code via the configured devcontainer. Exit code is forwarded from the spawned editor.

### `idc shell <path>`

Open an interactive shell inside the project's running devcontainer.

```bash
idc shell                # current directory
idc shell ./my-project   # specific path
idc shell --shell zsh    # explicit shell executable (overrides settings)
idc shell -i             # resolve VS Code Insiders user settings
```

Shell selection priority (highest first):

1. `--shell` CLI flag (literal executable; no argument parsing)
2. Workspace `<workspace>/.vscode/settings.json`:
   `terminal.integrated.defaultProfile.linux` plus the matching
   `terminal.integrated.profiles.linux` entry
3. `devcontainer.json` `customizations.vscode.settings` with the same keys
4. Host user-level VS Code settings, such as `~/Library/Application Support/Code/User/settings.json`
   on macOS, `~/.config/Code/User/settings.json` on Linux, or Windows-side
   settings via the WSL bridge
5. Container login shell from `getent passwd <user>` (`nologin` and `false` are rejected)
6. Fallback: `/bin/bash`, then `/bin/sh`

`idc shell` always reads the `.linux` terminal settings because devcontainers
run Linux, even on macOS and WSL hosts. Profile `args` and `env` are honored;
if a profile `path` is a list, the first entry is used. `${...}` substitution in
profile values is not resolved in this version, so those values are passed
through verbatim with a warning.

SSH agent forwarding works automatically when VS Code is open and connected to
the devcontainer. `idc shell` detects the VS Code relay socket at
`/tmp/vscode-ssh-auth-*.sock` and sets `SSH_AUTH_SOCK` on `docker exec`. If no
socket is found, it prints a hint to open the project in VS Code first.

### `idc copilot [<path>] [copilot args...]`

Exec the GitHub Copilot CLI (`copilot`) inside the project's running devcontainer.
Shares container resolution with `idc shell` (auto-build, auto-start prompts).

```bash
idc copilot                          # current directory, no copilot args
idc copilot --yolo --resume          # cwd; --yolo and --resume go to copilot
idc copilot ./my-project --resume    # explicit path; --resume goes to copilot
idc copilot . -- --some-flag         # explicit `--` separator (rarely needed)
idc copilot -- weird-positional      # escape hatch: first forwarded arg
                                     # would otherwise be parsed as the path
```

The first non-flag argument (if any) is the project path; everything else is forwarded verbatim to `copilot` inside the container. Use `--` if the first forwarded token would otherwise look like a path.

`copilot` must be installed inside the container — `idc copilot` does a fast `command -v copilot` probe first and fails with a hint if it's missing. Add it via a devcontainer Feature, or install it inside the container (for example, `npm install -g @github/copilot`).

### Auto-build: starting a brand-new devcontainer

If you run `idc shell` (or `idc copilot`) in a project whose devcontainer has
never been built, `idc` will offer to build it for you so you don't have to
open VS Code first:

```
idc: no devcontainer is running for /path/to/proj. Build & start it now? [Y/n]
```

This uses the official **`@devcontainers/cli`** (the same Node.js CLI VS Code's
Dev Containers extension drives under the hood) so the resulting container
carries the same `devcontainer.local_folder`, `devcontainer.config_file`, and
`devcontainer.metadata` labels VS Code expects — open the project in VS Code
later and it'll attach to the same container.

If the CLI isn't installed, `idc` will offer to install it:

```
idc: install the Dev Containers CLI now from
     https://raw.githubusercontent.com/devcontainers/cli/main/scripts/install.sh
     into ~/.devcontainers (no root needed)? [y/N]
```

This downloads a self-contained install (bundled Node.js runtime included), so
you don't need a host Node.js install. To install it manually:

```bash
# Self-contained install (recommended; bundles its own Node.js):
curl -fsSL https://raw.githubusercontent.com/devcontainers/cli/main/scripts/install.sh | sh

# Or, if you already have Node.js:
npm install -g @devcontainers/cli
```

Build progress (Docker layer pulls, feature installation, lifecycle hooks)
streams live above a pinned spinner so you can watch what the CLI is doing
without losing the loader UX. The same spinner shows briefly when `idc code`
launches VS Code so you always know `idc` is doing something.

If you decline the install, `idc` exits with a hint pointing at the
above commands and at `idc code <path>` (which opens VS Code, where the Dev
Containers extension can build the container instead). Auto-build always
prompts and never runs without an interactive TTY.

The shell runs as `remoteUser` from `devcontainer.json` when set, then
`containerUser`. When neither is set in `devcontainer.json`, `idc` reads the
container's `devcontainer.metadata` Docker label (written by the Dev Containers
extension / devcontainers/cli) and applies the same `remoteUser` →
`containerUser` resolution against the merged metadata layers, so users defined
by base images like `mcr.microsoft.com/devcontainers/javascript-node`
(`remoteUser: node`) are honored. If still nothing is set, the container
image's `USER` applies.

The working directory matches the URI logic: `<workspaceFolder>/<worktree-relative-path>`
for worktrees, otherwise `<workspaceFolder>`. The path is probed with `test -d`;
if it does not exist, `idc` falls back to the base `<workspaceFolder>`
with a warning, or omits `-w` entirely if that is missing too.

Limitations (apply to both `idc shell` and `idc copilot`):

- **GPG agent forwarding is not yet supported.** Commit signing inside the
  container will not work unless you've configured your own GPG forwarding via
  `containerEnv` and a bind mount.
- **`remoteEnv` is not applied.** The environment may differ from VS Code's
  integrated terminal; a warning is printed when `remoteEnv` is present in
  `devcontainer.json`.
- **Variable substitution** (`${env:VAR}`, `${localEnv:VAR}`) in terminal
  profile values is not resolved.
- **Devcontainer config inheritance** (`extends`, image-label metadata, Docker
  Compose service `user`) is not merged; only the raw `devcontainer.json` file
  is read. For complex setups, shell selection may differ from VS Code's
  resolved view.
- **Requires an interactive terminal.** Both `idc shell` and `idc copilot`
  exit with an error when stdin or stdout is not a TTY (e.g. piped or
  scripted contexts).

Common errors:

- No `devcontainer.json`: exits non-zero and points you at `idc doctor`.
- Container not running, in a non-interactive context (e.g. piped): no
  matching devcontainer was found and `idc` cannot prompt; run it
  interactively, or run `idc code <path>` first.
- Container stopped: `idc` will prompt to start it.
- Multiple matching containers: clean up the duplicate containers listed in the
  error.
- Docker not available: install/start Docker or Docker Desktop and try again.
- Dev Containers CLI not installed and user declined install: see the
  *Auto-build* section above for the curl/npm install commands.

### Naming-collision workaround

`code`, `shell`, `copilot`, `doctor`, and `update` are subcommands, so
`idc code`, `idc shell`, etc. always invoke them. To open a folder literally
named `shell`, `doctor`, or `update`, prefix the path with `./`:

```bash
idc code ./shell
idc code ./doctor
idc code "$(pwd)/update"
```

### `idc doctor [path]`

Diagnose the local environment for `idc` and print a "what would `idc code <path>` do here?"
plan summary. Read-only — never patches `settings.json` or spawns the editor.

Checks: VS Code editor on PATH, Dev Containers extension, Docker daemon,
Dev Containers CLI on PATH (used by `idc shell`/`idc copilot` to auto-build a missing
devcontainer), git, WSL setup (distro, Windows-side `settings.json`,
`dev.containers.executeInWSL`), devcontainer discovery + parse, worktree
sanity, `idc` version vs latest GitHub release, install method.

```bash
idc doctor              # inspect current directory
idc doctor /some/path   # inspect a specific path
```

Exit codes:

- `0` — no failing checks (warnings allowed)
- `1` — one or more failing checks

### `idc update`

Upgrade the installed `idc` tool via `uv tool upgrade indevcontainer`. Exit code is forwarded
from `uv`. Returns `1` if `uv` is not on PATH or if `idc` was not installed via
`uv tool`.

### `idc update --check`

Check for an available update without installing it. Prints local version, latest
GitHub release, and the release URL.

Exit codes:

- `0` — up to date (or local version is ahead, e.g. a dev build)
- `1` — a newer release is available
- `2` — network or GitHub API error

## 🌳 Git worktrees

When you run `idc code .` inside a git worktree, it automatically detects the main repo, finds the devcontainer config there, and opens the worktree folder inside the same container. This means all worktrees share a single devcontainer instance — same extensions, same Copilot context, multiple VS Code windows. 🪟🪟🪟

```bash
cd ~/repos/my-project
git worktree add .worktrees/pr-42 pr-42

# Opens pr-42 in the devcontainer defined in my-project
idc code .worktrees/pr-42

# Opens pr-99 in the SAME container, different window
git worktree add .worktrees/pr-99 pr-99
idc code .worktrees/pr-99
```

> ⚠️ The worktree must live inside the main repo directory tree (e.g. `.worktrees/`) so it's accessible from the container's mounted volume.

## 🧠 How it works

`idc code` constructs a `vscode-remote://dev-container+<hex-path>/workspaces/<name>` URI and launches VS Code with `--folder-uri`. VS Code handles the container lifecycle automatically.

For worktrees, the hex-encoded path points to the main repo (so all worktrees resolve to the same container), while the workspace folder is adjusted to open the worktree subfolder inside the container.

`idc shell` and `idc copilot` skip the VS Code URI dance and `docker exec -it` directly into the container that VS Code (or the Dev Containers CLI auto-build) already created — sharing user, workdir, and SSH agent socket so the inner process behaves like VS Code's integrated terminal.

## 🐧 WSL behavior

When `idc code` runs inside WSL, it:

1. Builds the URI using a Windows UNC path (`\\wsl.localhost\<distro>\…`) so VS Code on Windows can resolve the folder.
2. Auto-edits your **Windows** VS Code `settings.json` (under `%APPDATA%\Code\User\` or `Code - Insiders`) to set:
   - `"dev.containers.executeInWSL": true`
   - `"dev.containers.executeInWSLDistro": "<your-distro>"`

   This is required so the Dev Containers extension talks to Docker inside WSL instead of `docker.exe` on Windows. Comments and trailing commas in your `settings.json` are preserved (in-place patching, not a rewrite).

To opt out, pre-set those keys to whatever values you want — `idc` only writes them when they're missing or differ from the desired values.

## 🤝 Contributing

This project uses [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`, etc.). Releases are automated by [release-please](https://github.com/googleapis/release-please) — merging a `feat:` or `fix:` commit to `main` opens/updates a release PR, and merging that PR creates the tag + GitHub Release.
