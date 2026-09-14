# devcontainer-images

[![License](https://img.shields.io/github/license/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](LICENSE.md)
[![GitHub issues](https://img.shields.io/github/issues-raw/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images/issues)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/ivan-pinatti?logo=Github&style=for-the-badge)](https://github.com/sponsors/ivan-pinatti)
[![GitHub Repo stars](https://img.shields.io/github/stars/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images)
[![GitHub forks](https://img.shields.io/github/forks/ivan-pinatti-labs/devcontainer-images?logo=Github&style=for-the-badge)](https://github.com/ivan-pinatti-labs/devcontainer-images/forks)
[![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/ivan-pinatti-labs/devcontainer-images?utm_source=oss&utm_medium=github&utm_campaign=ivan-pinatti-labs%2Fdevcontainer-images&labelColor=171717&color=FF570A&label=CodeRabbit+Reviews&style=for-the-badge)](https://coderabbit.ai)

Container images for developing and running the `ivan-pinatti-labs`
repositories. One shared base image carries the tooling common to all of
them, and a repository needing more adds a thin layer on top of it. The point
is that work on those repositories happens inside a container holding exactly
what it needs, rather than on the host.

## Status

Nothing is published yet. This repository currently carries the scaffolding
it was created with. The base image and its build pipeline land next, and
this README grows a real quickstart when they do.

## Requirements

- [Podman](https://podman.io/), rootless. It is the runtime these images are
  built and run with. Docker is compatible, but nothing here assumes a daemon
  or a mounted socket.
- [`pre-commit`](https://pre-commit.com/#install) and `git` for the local
  checks, which are the same ones CI runs.

## Usage

Images will be published to the GitHub Container Registry and consumed by
digest rather than by a floating tag, so a rebuild cannot change what a
repository builds against until someone bumps the pin:

```dockerfile
FROM ghcr.io/ivan-pinatti-labs/devcontainer-base@sha256:<digest>
```

## How images are built

Every published image is linted with hadolint, scanned for secrets and
vulnerabilities, signed, and ships a software bill of materials. A secret
found in a layer blocks the publish. Vulnerabilities are reported rather than
blocking, with one exception: a critical one carrying a fix blocks the base
image. Scheduled rebuilds pick up upstream security fixes and publish a new
digest without cutting a release.

## License

See [LICENSE.md](LICENSE.md) for full details.

## Contribute / Donate

If you use this project, entirely or partially, or get inspired by it,
consider buying me a coffee or a beer, I would really appreciate it:
[buymeacoffee.com/ivan.pinatti](https://www.buymeacoffee.com/ivan.pinatti).
