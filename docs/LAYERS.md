# The layers

How the images in this repository fit together, what each one is allowed to
see, and how to use them day to day.

<!-- cspell:words tinyproxy userns keepalive graphql initializeCommand -->

## Why layers

Everything a developer runs used to run in one development container: the
coding agents, the editor's extensions, git, and every pre-commit hook, test
and package install. That container also held the GitHub token and the ssh
agent socket, so any hook, any npm postinstall script and any extension could
read the token, reach the network and plant code that ran later (measured
2026-09-24: a test hook read the token, reached the internet, and set
`core.fsmonitor` in the repository's git config).

The layers separate what you trust from what you only run.

```text
host       podman, the VS Code desktop, podman secrets. Nothing else runs here.
 ├─ ssh-agent       holds the ssh key; the key never leaves it
 ├─ gh-broker       holds the GitHub token; runs allowlisted gh commands
 ├─ egress-proxy    the only way out to the network, by allowlist
 └─ workbench       you, the coding agents and the editor's extensions
       no GitHub token, no ssh key, no direct network
       └─ L2        hooks, tests, installs, throwaway binaries
                    no network, no credentials, only the working tree
```

| Layer | Runs | Can reach |
| --- | --- | --- |
| host | podman, the editor's window | everything, which is why nothing else runs here |
| ssh-agent | `ssh-agent` | nothing: no network, read only, no capabilities |
| gh-broker | `gh` with the token | GitHub, for the commands in its allowlist |
| egress-proxy | tinyproxy | the hosts in its allowlist |
| workbench | Claude Code, Codex, the VS Code server and its extensions, git | the proxy, the broker socket, the agent socket, the working tree |
| L2 | pre-commit hooks, tests, package installs, anything the agents run that executes project code | the working tree, and the proxy only when a run asks for network |

## Using it

Once, on the host:

```shell
podman secret create gh-devcontainer /path/to/a/file/holding/the/token
ssh-keygen -t ed25519 -C devcontainer -f ~/.ssh/devcontainer/id_ed25519
```

The token is a fine grained personal access token for the organization with
read and write access to pull requests and issues and read access to
actions, commit statuses and contents. The key's public half is added to
your GitHub account as an authentication key.

Each day, from the repository you are working on:

```shell
host/workbench up       # proxy, broker, ssh-agent and the workbench
host/workbench unlock   # type the key's passphrase; lasts 8 hours
host/workbench shell    # a terminal in the workbench
```

For the editor, attach VS Code to the running `workbench-<folder>` container
(**Dev Containers: Attach to Running Container**). The terminal and the editor
are two views of the same container.

The first time in a repository, inside the workbench:

```shell
l2-hooks-install        # git hooks that run pre-commit in L2
```

Then `git commit` works as it always has. Log the agents in once (`claude`,
`codex`); their logins live in `~/.local/share/workbench/`, not in your own
`~/.claude` or `~/.codex`.

## L2

`l2 COMMAND` runs a command in a throwaway container started from inside the
workbench, from the repository's L2 image (`.devcontainer/l2-image`, else the
workbench's default).

- No network. `l2 --net` gives it the egress proxy, for installs.
- No credentials and nothing from the workbench's environment.
- The working tree at its own path, read write (`l2 --ro` for read only).
- The git directory read write, because git needs its index, with
  `.git/config` and `.git/hooks` read only on top. Those are where a hook
  could plant code that later runs in the workbench. A fully read only git
  directory is not an option: pre-commit then fails to write `index.lock`
  (measured 2026-09-24).
- `.devcontainer`, `.vscode`, `.claude`, `.codex`, `Makefile` and `host`
  read only, because the workbench or the host execute them. A formatter hook
  that wants to fix one of these fails with "Read-only file system"; fix
  that file by hand.
- `/root` on a volume per repository, which is where pre-commit keeps its
  hook environments.

The git hooks `l2-hooks-install` writes first install or confirm the hook
environments (`l2 --net --ro`, a quick no-op once they exist), then run the
hooks with no network. Measured cost: 0.2 seconds for a small commit, the
same as running pre-commit directly.

### Container based hooks

A container cannot start another container from inside L2: the nested runtime
cannot set up a user namespace there (measured 2026-09-24). The linters that
upstream ships only as images (hadolint, actionlint, dotenv-linter) are
therefore copied out of their official images into the L2 image, and L2's
`docker` command runs them for the hooks that still call `docker run`. A
hook asking for a version the image does not carry fails and says so.

## The coding agents

Both agents run in the workbench, and both are held to the same policy by
files they cannot edit (root owned, read only):

- `/etc/claude-code/managed-settings.json`: a `PreToolUse` hook rewrites
  any command that runs project code (a language runtime, a package manager,
  a test runner, a script from the working tree) into `l2 ...`, so it runs in
  L2 without a prompt. `allowManagedHooksOnly` stops project or user settings
  removing it. Claude Code's own sandbox is on, in its nested mode, as an
  extra layer inside the workbench.
- `/etc/codex/requirements.toml`: Codex keeps its own sandbox and asks
  before acting, and the same hook refuses project code with the `l2` command
  line to use instead.

This is policy, not a boundary. Command matching can be defeated by a
determined agent (`sh -c` inside a script, for instance); what actually
protects the credentials is that the workbench does not hold the GitHub
token or the ssh key, and that L2 holds nothing at all.

## GitHub access

There is no `gh` binary and no token in the workbench. The `gh` command there
sends its arguments to the gh broker, which runs the real `gh` with the token
if the command is in `images/gh-broker/allowlist.json`, and returns the
output. Anything running in the workbench can use GitHub through it; nothing
can take the token away. Every request is logged: `podman logs gh-broker`.

Refused: anything outside the allowlist (including `gh auth token`, `repo
delete`, `secret`), repositories outside the organization, `gh api` with a
method other than GET, and GraphQL mutations. Interactive prompts are not
available, so pass the flags a prompt would ask for.

`git push` goes over ssh through the ssh-agent container, which signs the
login without ever handing over the key. `host/workbench unlock` adds the key
for eight hours at a time.

## Network

The workbench is on an internal podman network with no route and no DNS. Its
only way out is the egress proxy, which forwards HTTPS to the hosts in
`images/egress-proxy/allowlist` and answers everything else with `403
Filtered`. Measured 2026-09-24: GitHub, Anthropic, OpenAI and the Marketplace
connect; the kind of endpoints recent extension malware used (a blockchain
RPC endpoint, a calendar API, a paste site) do not; direct connections and
external DNS do not exist.

The proxy decides by host name without inspecting TLS, so it cannot stop
data leaving through a host it allows (a gist on github.com, for instance).
It stops what is not on the list; it does not make the list safe.

## Extensions

The editor's extensions run in the workbench with the same permissions as
the editor itself; VS Code has no sandbox for them. What limits them here:

- Only the extensions in `images/workbench/vscode/extensions.txt` exist,
  each pinned to an exact version released at least seven days earlier.
- They are baked into a root owned, read only directory. Neither an
  extension nor anything else in the workbench can install, update or replace
  one. Auto update is off.
- They find no GitHub token and no ssh key, and reach only the hosts on the
  proxy's allowlist.
- The coding agents' own logins are readable in the workbench, which the
  agent extensions need. That is accepted: the worst case is someone using
  that subscription, and it can be revoked.

Keep the extensions on the host's own VS Code to the Dev Containers extension:
anything installed there runs on the host.
