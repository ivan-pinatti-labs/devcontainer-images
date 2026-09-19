# Where the tools come from

<!-- cspell:words nodesource keyrings dearmor dearmored enarmor gpgv dpkg nodistro pkgs pipx -->

Every command line tool these repositories develop against, where it is
installed from, and what actually vouches for it.

## Why there is no version manager

asdf was removed from this organization on 2026-09-19. It installed tools by
running a plugin, and a plugin is a git repository of shell scripts that
downloads a release and puts it on PATH. Pinning the plugin to a reviewed
commit, which this organization did, fixes which scripts run; it does not
give the downloaded tool a signature, a build attestation or a maintainer
who ships security fixes for it. Nor does the image scanner see any of it: a
tool unpacked into a home directory carries no package metadata, so Trivy
reported nothing about the entire toolchain.

mise and aqua were considered and rejected. They are better version managers
than asdf, but the trust model is the same one: a manifest in a repository
somewhere decides what gets downloaded and executed.

Packages replaced it. A package comes from a repository whose index is
signed, is unpacked by apt rather than by a script, records itself in the
dpkg database where the scanner can see it, and has somebody upstream
issuing security updates for it.

## No version pins

Nothing here pins a package version, deliberately.

Ubuntu and the third party repositories below all ship security fixes by
moving a package's version inside a release. Pinning would hold an image on
the superseded build until somebody edited the pin by hand, which is the
opposite of what the scheduled rebuild exists for. The base image digest is
what makes a build reproducible; the apt upgrade on rebuild is what makes it
current.

What that costs is the seven day cooling window Renovate applies elsewhere:
there is no version for it to hold back. What replaces it is the
distribution's own review, and the fact that a rebuild is published as a new
digest that nothing consumes until a repository bumps its pin, with CI
building the development container and exercising its tools before that
bump can merge.

## The keys

The base image carries three third party apt signing keys, vendored under
`images/base/keyrings/` and verified against these fingerprints at build
time:

| Keyring | Fingerprint | Signs |
| --- | --- | --- |
| `github-cli.gpg` | `2C6106201985B60E6C7AC87323F3D4EA75716059` | GitHub CLI |
| `nodesource.gpg` | `6F71F525282841EEDAF851B42F59B5F99B1BE0B4` | NodeSource Node.js |
| `hashicorp.gpg` | `D55C0D1AC78A8D8126CB631CFC9CA96ACA026560` | HashiCorp Terraform |

They are vendored rather than downloaded during the build so that a key
changing is a diff somebody reviews in a pull request, not whatever the
vendor served on the day of the build. A file that does not match its
fingerprint fails the build, which was verified by swapping one for a freshly
generated key and watching the build stop.

**Installing a key grants nothing on its own.** apt reads a keyring only when
a `sources.list` entry names it with `signed-by=`. The base image ships the
keys and enables none of the repositories, the same way it ships rootless
Podman and leaves nesting opt in. A repository that wants one of these tools
adds its own source entry.

## Enabling a repository

In that repository's `.devcontainer/Dockerfile`, as root, before installing:

```dockerfile
RUN printf '%s\n' \
      'deb [arch=amd64 signed-by=/usr/share/keyrings/github-cli.gpg] https://cli.github.com/packages stable main' \
      > /etc/apt/sources.list.d/github-cli.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends gh \
  && rm -rf /var/lib/apt/lists/*
```

The other two source lines, where they are needed:

```text
deb [arch=amd64 signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main
deb [arch=amd64 signed-by=/usr/share/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com resolute main
```

`resolute` is Ubuntu 26.04's codename, which HashiCorp publishes a component
for. A base image moving to a new Ubuntu release has to check that the
component exists before the move, because apt fails closed on a missing one
rather than falling back.

`Pin Only` does not allow a dependency bot to touch any of these lines, or
any keyring file. Only a version and a digest normalize away; a source URL,
a keyring path or a package name changing has no counterpart on the other
side of the diff and the pull request waits for a person.

## Every tool

| Tool | Source | Provenance | Notes |
| --- | --- | --- | --- |
| git, curl, jq, make, python3, openssh-client, procps | Ubuntu | distribution repository signature | in the base image |
| podman, podman-docker, crun, catatonit, fuse-overlayfs, passt, nftables, uidmap, libcap2-bin | Ubuntu | distribution repository signature | in the base image, inert until a repository opts in to nesting |
| pre-commit | Ubuntu | distribution repository signature | 4.5.1 on 26.04, against the 4.6.2 the retired asdf pin named |
| shellcheck | Ubuntu | distribution repository signature | 0.11.0, the same version the retired asdf pin named |
| github-cli | `cli.github.com/packages stable main` | repository signature | 2.101.0, ahead of the retired pin |
| nodejs | `deb.nodesource.com/node_24.x nodistro main` | repository signature | 24.21.0, the same version the retired pin named |
| terraform | `apt.releases.hashicorp.com resolute main` | repository signature | 1.16.3, ahead of the retired pin |
| tflint | `ghcr.io/terraform-linters/tflint`, pinned by digest | container image published by the project | see below |

### tflint is the exception

tflint publishes no apt repository, from its own project or from any
distribution. The remaining options were a release download checked against a
checksum, which is what asdf was already doing and is the thing being
retired, or the project's own container image.

It runs from the image. The base image already carries rootless Podman, so a
wrapper on PATH runs the pinned image and the `gruntwork-io/pre-commit`
`tflint` hook, which invokes whatever `tflint` it finds, needs no change.

The honest limitation: a tool that runs from its own image is not installed
in this organization's images, so it does not appear in their SBOMs and is
not covered by their vulnerability scans. It is scanned by whoever publishes
it, not here. That is a real reduction in visibility, accepted because the
alternative kept an unsigned release download in the build.

## What the scanners see now

Measured 2026-09-19 against a development container built on this base,
with Trivy 0.74.0:

- `gh`, `nodejs`, `terraform`, `pre-commit` and `shellcheck` all appear as
  `os-pkgs` entries. Under asdf, none of them appeared at all.
- Trivy additionally unpacks the Go binaries behind `gh` and `terraform` and
  the Node.js module tree, reporting 16 vulnerabilities in their bundled
  dependencies that were previously invisible.
- Python packages installed with pip, pipx or into a virtual environment are
  detected too, as `lang-pkgs` / `python-pkg`, so the test dependency
  environments in the sibling repositories are covered.

---

See also: [IMAGES.md](IMAGES.md)
