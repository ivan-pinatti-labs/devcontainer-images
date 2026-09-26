# devcontainer-images

[![License](https://img.shields.io/github/license/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](LICENSE.md)
[![GitHub issues](https://img.shields.io/github/issues-raw/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images/issues)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/ivan-pinatti?logo=Github&style=for-the-badge)](https://github.com/sponsors/ivan-pinatti)
[![GitHub Repo stars](https://img.shields.io/github/stars/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images)
[![GitHub forks](https://img.shields.io/github/forks/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images/forks)
[![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/ivan-pinatti-labs/devcontainer-images?utm_source=oss&utm_medium=github&utm_campaign=ivan-pinatti-labs%2Fdevcontainer-images&labelColor=171717&color=FF570A&label=CodeRabbit+Reviews&style=for-the-badge)](https://coderabbit.ai)

Container images for developing the `ivan-pinatti-labs` repositories, split
into layers by what each one is trusted with. You and the coding agents work
in a workbench that holds no GitHub token and no ssh key; hooks, tests and
package installs run in L2 containers with no network and no credentials; a
GitHub broker, an ssh-agent and an egress proxy sit beside them, and nothing
runs on the host but podman. [docs/LAYERS.md](docs/LAYERS.md) explains the
layers and the daily routine.

## Status

The layered images are new and not published yet. The base image published
today is the previous, single container design;
[docs/IMAGES.md](docs/IMAGES.md) covers what each image carries and how the
build works.

## Requirements

- [Podman](https://podman.io/), rootless. It is the runtime these images are
  built and run with. Nothing here assumes a daemon or a mounted socket.
- An SELinux enforcing host is what this was built and measured on. Nothing
  here turns labelling off.

## Usage

```shell
make workbench-build    # every image, locally
make unlock             # the ssh key, for eight hours
make claude             # Claude Code in its workbench, started if needed (or: codex)
make claude-shell       # a terminal in that workbench (or: codex-shell)
```

Or attach VS Code to the running `workbench-claude-<folder>` or
`workbench-codex-<folder>` container, whichever agent's extension you want;
each agent has a workbench of its own and cannot read the other's login.
Published images are consumed by digest rather than by a floating tag, so a rebuild
cannot change what a repository builds against until someone bumps the pin.

## How images are built

`scripts/build-images.sh`, in CI and locally alike: base first, then every
other image on that exact base, each scanned before anything is published,
and what is published is the scanned manifest itself. A secret found in a
layer blocks the publish. Vulnerabilities are reported rather than blocking,
with one exception: a critical one carrying a fix blocks. Scheduled rebuilds
pick up upstream security fixes and publish new digests without cutting a
release.

## License

See [LICENSE.md](LICENSE.md) for full details.

## Contribute / Donate

If you use this project, entirely or partially, or get inspired by it,
consider buying me a coffee or a beer, I would really appreciate it:
[buymeacoffee.com/ivan.pinatti](https://www.buymeacoffee.com/ivan.pinatti).
