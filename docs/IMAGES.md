# The images

## What is here

- **`base`**, built from
  [images/base/Dockerfile](../images/base/Dockerfile) and published as
  `ghcr.io/ivan-pinatti-labs/devcontainer-base`.

The base image carries what every repository in the organization needs and
nothing that only one of them needs: git, asdf, the tools asdf's plugins
depend on to fetch and verify their releases, and rootless Podman for the
repositories whose tooling starts containers of its own (see "Running
containers inside it" below).

It deliberately does **not** carry github-cli, pre-commit or nodejs, even
though nearly every repository pins those. They belong to a repository's own
`.tool-versions`, and installing them here would mean two places to bump a
version and a base image rebuild every time any repository moved a pin.

## How a repository uses it

Install that repository's pins on top of the base:

```dockerfile
FROM ghcr.io/ivan-pinatti-labs/devcontainer-base@sha256:<digest>

COPY .tool-versions .
RUN asdf install
```

By digest, never by a floating tag. A tag would let a rebuild change the
toolchain under a checkout with no commit saying so, which is the failure the
digest pin exists to prevent. Renovate can keep the digest current, and its
pull request is then the record that the environment changed.

## Running containers inside it

Most of these repositories start containers from inside their development
container: pre-commit's `hadolint-docker` and `actionlint-docker` hooks, and
docker-torrent-box-with-vpn's whole stack. The image carries rootless Podman
for that, plus a `docker` command that runs it, because pre-commit's
`docker_image` hooks call `docker` by name.

It works when the development container runs in `container_engine_t`, the
confined SELinux domain meant for running a container engine inside a
container:

```shell
--security-opt label=type:container_engine_t --device /dev/fuse
```

**SELinux stays enforcing.** This is not `label=disable`: the development
container is still confined, cannot see host paths that are not mounted into
it, and the host still masks its `/proc` and `/sys`. Without these flags the
container runs in the default `container_t` domain and nesting fails, so a
repository whose tooling never starts a container keeps the stricter default.
A repository that needs nesting adds the flags to its own devcontainer.json.

Why each piece, all measured on 2026-09-15 on an SELinux enforcing host:

- **`container_engine_t`, not the default `container_t`.** `container_t`
  refuses the mounts a nested runtime makes (a new devpts, then mount
  propagation on `/dev/null`). `label=nested` leaves the domain unchanged, so
  it fails the same way.
- **The crun wrapper** (`images/base/containers/crun-without-masked-paths`).
  `container_engine_t` allows those mounts but refuses the tmpfs mounts podman
  uses to mask directories such as `/proc/acpi`, and no podman option can
  unmask all of them. The wrapper removes masked paths from each nested
  container's spec. A nested container then sees the same `/proc` and `/sys`
  as the development container, which the host has already masked, and
  nothing more.
- **`/dev/fuse`** is what fuse-overlayfs, the nested storage driver, needs.
- **Nested containers share the development container's network namespace**
  (`images/base/containers/containers.conf`). That is enough for hooks and
  test suites; a stack with its own networks and a VPN is still to be proven.
- **Anything a development container connects to over a socket runs in the
  same domain and SELinux category.** A process in `container_engine_t` could
  not connect to an ssh-agent running in `container_t`, and could connect to
  one in `container_engine_t` at the same category.

Verified with rootless Podman on the host, with and without
`--userns=keep-id`: a nested container runs through the `docker` command, a
hadolint run shaped like pre-commit's own (a bind mounted working tree and
`--user` passed through) lints its file, and the same nested run without the
flags fails.

## What the build does

`.github/workflows/build-base-image.yml` runs on a pull request touching
`images/**`, on a push to `main`, weekly on a schedule, and on demand.

1. Builds the image for `linux/amd64`, loading it locally rather than
   pushing.
2. Scans it for secrets. A finding **fails the build**: a credential baked
   into a layer is not something to report and move on from.
3. Scans it for vulnerabilities and uploads the result to code scanning.
   Findings are reported rather than blocking, so an upstream CVE with no fix
   available cannot wedge the pipeline.
4. Fails on a **critical** vulnerability that has a fix available, and only
   then. That is the one class where blocking is actionable: the fix is a
   rebuild away.
5. Publishes to the GitHub Container Registry, with an SBOM and provenance
   attached, and only from `main`. The gate is the branch rather than "not a
   pull request": `workflow_dispatch` runs against whatever ref it is
   launched from, so a weaker condition would let a feature branch publish.

The weekly rebuild exists because step 4's "a rebuild away" has to actually
happen. It publishes a new digest and cuts no release, so nothing consumes it
until a repository bumps its pin.

## Bumping asdf

`ASDF_VERSION` in the Dockerfile carries a matching `ASDF_SHA256`, which
Renovate cannot compute: a checksum is not a version, and no datasource
publishes it as one. Renovate still proposes the version bump, with a note in
the pull request saying the checksum is missing, and that pull request is
never automerged. Finish it by recomputing the checksum and pushing it:

```shell
curl -fsSL https://github.com/asdf-vm/asdf/releases/download/v<version>/asdf-v<version>-linux-amd64.tar.gz \
  | sha256sum
```

The build verifies the archive against that value before executing anything
out of it, so a mismatched pair fails the build rather than shipping an
unverified binary.
