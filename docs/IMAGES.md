# The images

## What is here

- **`base`**, built from
  [images/base/Dockerfile](../images/base/Dockerfile) and published as
  `ghcr.io/ivan-pinatti-labs/devcontainer-base`.

The base image carries what every repository in the organization needs and
nothing that only one of them needs: git, the common command line tools, the
apt signing keys this organization trusts, and rootless Podman for the
repositories whose tooling starts containers of its own (see "Running
containers inside it" below).

There is **no version manager** in it. Tools come from signed package
repositories, installed with apt; `TOOL_SOURCES.md` is the reference for
where each one comes from and what vouches for it.

It deliberately does **not** carry github-cli, pre-commit, nodejs or
terraform, even though nearly every repository uses one of them. Installing
them here would rebuild the base image every time any single repository
changed what it needs. It carries their signing keys instead, which is the
part that is genuinely common, and enables none of those repositories
itself: a keyring does nothing until a `sources.list` entry names it.

## How a repository uses it

Install what that repository needs on top of the base:

```dockerfile
FROM ghcr.io/ivan-pinatti-labs/devcontainer-base@sha256:<digest>

USER 0:0
RUN printf '%s\n' \
      'deb [arch=amd64 signed-by=/usr/share/keyrings/github-cli.gpg] https://cli.github.com/packages stable main' \
      > /etc/apt/sources.list.d/github-cli.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends gh pre-commit \
  && rm -rf /var/lib/apt/lists/*
USER 1000:1000
```

By digest, never by a floating tag. A tag would let a rebuild change the
toolchain under a checkout with no commit saying so, which is the failure the
digest pin exists to prevent. Renovate can keep the digest current, and its
pull request is then the record that the environment changed.

Package versions are deliberately not pinned; `TOOL_SOURCES.md` says why.

## Running containers inside it

Most of these repositories start containers from inside their development
container: pre-commit's `hadolint-docker` and `actionlint-docker` hooks,
pre-commit-checklists' tflint, and docker-torrent-box-with-vpn's whole
stack. The image carries rootless Podman
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
- **Nested containers share the development container's network namespace
  by default** (`images/base/containers/containers.conf`). That is enough for
  hooks and for test suites whose containers do not talk to each other. A
  repository that needs more opts in to it; see "Nested containers with a
  network of their own" below.
- **Anything a development container connects to over a socket runs in the
  same domain and SELinux category.** A process in `container_engine_t` could
  not connect to an ssh-agent running in `container_t`, and could connect to
  one in `container_engine_t` at the same category.

Verified with rootless Podman on the host, with and without
`--userns=keep-id`: a nested container runs through the `docker` command, a
hadolint run shaped like pre-commit's own (a bind mounted working tree and
`--user` passed through) lints its file, and the same nested run without the
flags fails.

### Nested containers with a network of their own

Some tooling needs nested containers that reach each other by address:
rsync-crypt's test suite starts an sshd container and connects to its IP, and
a compose stack has networks of its own. A repository that needs that adds
two more run arguments:

```shell
--device /dev/net/tun --security-opt unmask=/proc/sys
```

and makes a bridge network the nested default, in its devcontainer.json:

```json
"containerEnv": {
  "CONTAINERS_CONF_OVERRIDE": "/usr/local/share/devcontainer/containers-bridge-network.conf"
}
```

Measured on 2026-09-15:

- With the default shared namespace, a nested container has no address of
  its own (`podman inspect` reports none).
- `--network=bridge` without the two arguments fails in turn: silently
  without `/dev/net/tun`, which pasta needs to set up rootless networking;
  then with `netavark: set sysctl net/ipv4/ip_forward: Read-only file system`,
  because the runtime mounts `/proc/sys` read only and netavark writes the
  setting even when it already holds the right value, so `--sysctl` on the
  development container does not help; then with
  `unable to execute "nft"`, which is why the image carries nftables.
- With both arguments, a nested container got an address on the bridge,
  a second nested container reached it there, and both reached the internet.

What `unmask=/proc/sys` exposes, measured as root of the dev account's user
namespace (where nested podman runs): every `kernel`, `vm` and `fs` setting is
still refused, and so are the network settings of the development
container's own namespace. Only the network settings inside a namespace that
user created itself can be written, which is what netavark needs and all it
gets.

### Devices for nested containers

A FUSE mount inside a nested container (rsync-crypt's gocryptfs and sshfs)
and a VPN client (a TUN device) need the device passed on to that container.
The development container holds both devices and may use them, but host
policy refuses bind mounting either one into a nested container:
`crun: set propagation for dev/fuse: Permission denied`, logged as
`denied { mounton }` for `container_engine_t` on `fuse_device_t`
(`tun_tap_device_t` for TUN). `label=disable` on the nested container does
not change that, because the refusal is the host's.

[host/selinux/devcontainer_nested_devices.te](../host/selinux/devcontainer_nested_devices.te)
allows exactly that one permission, for `container_engine_t`, on those two
device types. It is host setup, installed once by someone with root on that
machine:

```shell
checkmodule -M -m -o devcontainer_nested_devices.mod host/selinux/devcontainer_nested_devices.te
semodule_package -o devcontainer_nested_devices.pp -m devcontainer_nested_devices.mod
sudo semodule -i devcontainer_nested_devices.pp
```

`sudo semodule -r devcontainer_nested_devices` removes it again. The
`container_use_devices` boolean is not the alternative: it grants every
container domain, including the ordinary `container_t` every other container
on the machine runs in, access to every device node.

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

## Changing a signing key

The three third party apt keys are vendored under `images/base/keyrings/`
and checked against the fingerprints listed in `TOOL_SOURCES.md` before the
build dearmors them. A key that does not match its fingerprint fails the
build.

Rotating one is a deliberate, reviewed change: replace the armored file, put
the new fingerprint in the Dockerfile and in `TOOL_SOURCES.md`, and say in
the pull request where the new key came from and how it was checked.
Renovate does not touch these files and `Pin Only` refuses any diff that
does, so no dependency bot can rotate a key unattended.
