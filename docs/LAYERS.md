# The layers

How the images in this repository fit together, what each one is allowed to
see, and how to use them day to day.

<!-- cspell:words tinyproxy userns initializeCommand -->

## Why layers

Everything a developer runs used to run in one development container: the
coding agents, the editor's extensions, git, and every pre-commit hook, test
and package install. That container also held the GitHub token and the ssh
agent socket, so any hook, any npm postinstall script and any extension could
read the token, reach the network and plant code that ran later. Measured
2026-09-24: a test hook read the token, reached the internet, and set
`core.fsmonitor` in the repository's git config, which git would have run the
next time anyone used the repository.

The layers separate what you trust from what you only run.

```text
host         podman, the VS Code desktop, podman secrets. Nothing else runs here.
 ├─ ssh-agent        holds the ssh key; the key never leaves it
 ├─ gh-broker        holds the GitHub token; runs allowlisted gh commands
 ├─ egress-proxy     the only way out to the network, by allowlist
 ├─ workbench        you, the coding agents, the editor's extensions, git
 │                   no GitHub token, no ssh key, no direct network,
 │                   no container runtime
 └─ L2 engine        starts L2 containers; the workspace, nothing else
       └─ L2         hooks, tests, installs, throwaway binaries
                     no network, no credentials, only the working tree
```

| Layer | Runs | Can reach |
| --- | --- | --- |
| host | podman, the editor's window | everything, which is why nothing else runs here |
| ssh-agent | `ssh-agent` | nothing: no network, read only, no capabilities |
| gh-broker | `gh` with the token | GitHub, for the commands in its allowlist |
| egress-proxy | tinyproxy | the hosts in its allowlist |
| workbench | Claude Code, Codex, the VS Code server and its extensions, git | the proxy, the broker socket, the agent socket, the engine socket, the workspace |
| L2 engine | rootless podman | the proxy, the workspace |
| L2 | pre-commit hooks, tests, package installs, anything the agents run that executes project code | the working tree, and the proxy only when a run asks for network |

L2 containers run in the engine, not in the workbench, so they cannot see
the workbench's processes or connect to anything it listens on (measured
2026-09-24; when they ran nested in the workbench they could list its
processes, read their command lines and reach its localhost). The workbench
itself has no container runtime and no FUSE device; its `podman` is a client
of the engine's socket.

## Using it

Once, on the host:

```shell
podman secret create gh-devcontainer /path/to/a/file/holding/the/token
ssh-keygen -t ed25519 -C devcontainer -f ~/.ssh/devcontainer/id_ed25519
host/workbench build
```

The token is a fine grained personal access token for the organization with
read and write access to pull requests and issues and read access to
actions, commit statuses and contents. The key's public half is added to
your GitHub account as an authentication key.

Each day, from the repository you are working on:

```shell
host/workbench up        # proxy, broker, ssh-agent, L2 engine, workbench
host/workbench load-l2   # the first time: L2 images into the engine
host/workbench unlock    # type the key's passphrase; lasts 8 hours
host/workbench shell     # a terminal in the workbench
```

For the editor, attach VS Code to the running `workbench-<folder>` container
(**Dev Containers: Attach to Running Container**). The terminal and the editor
are two views of the same container.

The first time in a repository, inside the workbench:

```shell
l2-hooks-install         # git hooks that run pre-commit in L2
```

Then `git commit` and `git push` work as they always have. Hooks that were
installed before are kept as `<hook>.pre-l2` and still run when a commit is
made from outside the workbench. Log the agents in once (`claude`, `codex`);
their logins live in `~/.local/share/workbench/`, not in your own `~/.claude`
or `~/.codex`.

### Per repository

A repository adds what its hooks and tests need on top of the shared L2
image in `.devcontainer/l2/Dockerfile`, and names the result in
`.devcontainer/l2-image`. It opts in to more for its engine in
`.devcontainer/workbench-profile`, one name per line, from a fixed list
(`host/workbench --help`): `nested-network` for tests whose containers talk
to each other, `hooks-engine` for hooks that build or start containers,
`nested-devices` for FUSE or TUN inside those containers. Anything else in
that file stops `up`, so a repository cannot pass arbitrary flags to podman
on the host.

## L2

`l2 COMMAND` runs a command in a throwaway container, started by the engine
from the repository's L2 image.

- No network. `l2 --net` gives it the egress proxy, for installs.
- No credentials and nothing from the workbench's environment
  (`l2 --env NAME=VALUE` passes one variable on purpose).
- The working tree at its own path, read write (`l2 --ro` for read only).
- The git directory read write, because git needs its index, with
  `.git/config` and `.git/hooks` read only on top. Those are where a hook
  could plant code that later runs in the workbench. A fully read only git
  directory is not an option: pre-commit then fails to write `index.lock`
  (measured 2026-09-24).
- `.devcontainer`, `.vscode`, `.claude`, `.codex`, `Makefile` and `host`
  read only, because the workbench or the host execute them.
- `/root` on a volume per repository, which is where pre-commit keeps its
  hook environments.
- An `l2` round trip costs about 90 milliseconds.

### pre-commit

`l2-pre-commit` is pre-commit run in L2, and what the git hooks
`l2-hooks-install` writes call. Before each run the hook environments are
installed or confirmed (`l2 --net --ro -- l2-prepare-hooks`, a quick no-op
once they exist, which also installs what the pre-commit-checklists hooks run
in their own nested pre-commit). Then the hooks run with no network.

Formatters open files for writing even when they change nothing, so during a
pre-commit run the protected paths above are writable. They are compared
before and after instead, and a run in which a hook actually changed one
fails, naming the files. Measured 2026-09-24 with a hostile test hook: its
rewrite of `.devcontainer/devcontainer.json` was caught, its write to
`.git/config` refused, and it saw no token.

Hooks that only work with the open internet (`markdown-link-check`,
`lychee`) are skipped in local runs and left to CI. `L2_SKIP_HOOKS`
overrides that list.

### Tests

A test suite runs in L2 like any other command. A step that needs GitHub (a
fixture fetched with `gh`) runs in the workbench first, through the broker;
L2 never gets the broker, because that would hand GitHub access to the code
under test.

A suite that builds images and starts containers of its own runs with
`l2 --engine`: that run gets the engine's socket (its `docker` and `podman`
talk to the engine), and a scratch directory as `TMPDIR` that the containers
it starts can mount at the same path. Those containers are L2 as well; the
engine holds no credentials.

Measured 2026-09-24, all in L2:

| Repository | What | Result |
| --- | --- | --- |
| devcontainer-images | every commit on this branch | all hooks, through the git hooks |
| gh-actions | 44 hooks over every file; the pytest suite | 4 seconds; 261 passed, 94% coverage, in 18 seconds |
| pre-commit-checklists | its own self-test suite (`l2 --net`) | 160 of 160 assertions |
| rsync-crypt | the suite, which builds the image and starts sshd and gocryptfs containers (`l2 --engine`) | 311 passed in 20 seconds |
| rsync-crypt | the pre-push trivy image scan (`hooks-engine`) | passed |

### Container based hooks

L2 cannot start containers on its own. The linters that upstream ships only
as images (hadolint, actionlint, dotenv-linter) are copied out of their
official images into the L2 image, and L2's `docker` command runs them for
the hooks that call `docker run`. A hook asking for a version the image does
not carry fails and says so. In an `--engine` run, anything else `docker` is
asked to do goes to the engine.

actionlint runs as an account of its own inside L2. v1.7.12 deadlocks when a
`run:` script is larger than the pipe capacity left to the calling uid
(upstream rhysd/actionlint#702), and L2 runs as your host uid, which usually
has little left: on gh-actions it hung past 60 seconds as that uid and
finished at once as nobody. That is why L2 keeps the `setuid` and `setgid`
capabilities, which act only inside its own user namespace.

## The coding agents

Both agents run in the workbench, and both are held to the same policy by
files they cannot edit (root owned, read only):

- `/etc/claude-code/managed-settings.json`: a `PreToolUse` hook rewrites
  any command that runs project code (a language runtime, a package manager,
  a test runner, a script from the working tree) into `l2 ...`, and
  `pre-commit ...` into `l2-pre-commit ...`, so it runs in L2 without a
  prompt. `allowManagedHooksOnly` stops project or user settings removing
  it. Claude Code's own sandbox is on, in its nested mode, as an extra layer
  inside the workbench.
- `/etc/codex/requirements.toml`: Codex keeps its own sandbox (measured
  working inside the workbench: read only, no network) and asks before
  acting, and the same hook refuses project code with the `l2` command line
  to use instead.

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
login without ever handing over the key. The connection runs to
`ssh.github.com` on port 443 through the egress proxy, and GitHub's host key
is checked against keys fetched from GitHub's own API. `host/workbench
unlock` adds the key for eight hours at a time.

## Network

The workbench and the engine are on an internal podman network with no route
and no DNS. Their only way out is the egress proxy, which forwards HTTPS to
the hosts in `images/egress-proxy/allowlist` and answers everything else with
`403 Filtered`. Measured 2026-09-24: GitHub, Anthropic, OpenAI, the
Marketplace and the package registries connect; the kind of endpoints recent
extension malware used (a blockchain RPC endpoint, a calendar API, a paste
site) do not; direct connections and external DNS do not exist. `podman logs
egress-proxy` shows what was refused, which is the first place to look when a
tool fails to download something.

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
