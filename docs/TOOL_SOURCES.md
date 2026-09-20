# Where the tools come from

<!-- cspell:words nodesource keyrings dearmor dearmored enarmor gpgv -->
<!-- cspell:words dpkg nodistro pkgs pipx subkey subkeys userns SLSA -->

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
opposite of what the scheduled rebuild exists for.

The digest pins what an image builds *on*, not what apt resolves on top, so
two builds of the same Dockerfile weeks apart can and should install
different package builds. This layer is deliberately rolling, not
reproducible, and the two should not be confused: reproducing an exact
container means keeping the image, not re-running the build. Rebuilding is
what makes it current, which is the property being chosen here.

What that costs is the seven day cooling window Renovate applies elsewhere:
there is no version for it to hold back. What replaces it is the
distribution's own review, and the fact that a rebuild is published as a new
digest that nothing consumes until a repository bumps its pin, with CI
building the development container and exercising its tools before that
bump can merge.

## The keys

The base image carries three third party apt signing keys, vendored under
`images/base/keyrings/`. Each file's set of **primary** certificates is
compared against this list at build time, exactly: every fingerprint here
must be present and no other may be.

| Keyring | Primary certificates | Signs |
| --- | --- | --- |
| `github-cli.gpg` | `2C6106201985B60E6C7AC87323F3D4EA75716059`, `7F38BBB59D064DBCB3D84D725612B36462313325` | GitHub CLI |
| `nodesource.gpg` | `6F71F525282841EEDAF851B42F59B5F99B1BE0B4` | NodeSource Node.js |
| `hashicorp.gpg` | `D55C0D1AC78A8D8126CB631CFC9CA96ACA026560` | HashiCorp Terraform |

github-cli carries two because GitHub rotates by publishing the new
certificate alongside the old one. Pinning only one of them would fail
verification the day they switch, which is why the check is an exact set
rather than a single value.

Subkeys are deliberately not listed. A subkey is bound to its primary by a
signature gpg already verifies, so naming the primaries fixes the whole
trust chain, and listing subkeys as well would mean editing this file every
time a vendor rotated a signing subkey under an unchanged primary.

An exact set, rather than "the expected fingerprint appears somewhere in the
file", because `gpg --dearmor` installs every certificate a file holds and
apt then accepts repository metadata signed by any of them. A vendor quietly
adding a second certificate, or a tampered file with one appended, would
otherwise install a signer nobody reviewed while the check still passed.
CodeRabbit caught precisely that on the first version of this change.

They are vendored rather than downloaded during the build so that a key
changing is a diff somebody reviews in a pull request, not whatever the
vendor served on the day of the build. Three failure modes were confirmed
against a real build: replacing a key with a freshly generated one, adding a
rogue certificate to an otherwise correct file, and removing one of the two
reviewed GitHub certificates. All three stop the build.

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
| nodejs | `deb.nodesource.com/node_24.x nodistro main` | repository signature | 24.21.0, the same version the retired pin named; in the base image, because both agent CLIs run on it |
| terraform | `apt.releases.hashicorp.com resolute main` | repository signature | 1.16.3, ahead of the retired pin |
| tflint | `ghcr.io/terraform-linters/tflint`, pinned by digest | container image published by the project | see below |
| claude (Claude Code) | npm `@anthropic-ai/claude-code`, version pinned | npm registry signature only, **no build provenance** | in the base image, see below |
| codex (Codex CLI) | npm `@openai/codex`, version pinned | npm registry signature **and** SLSA build provenance | in the base image, see below |

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

### The two coding agent CLIs

Neither Claude Code nor Codex publishes an apt repository, from its vendor or
from any distribution, so neither can follow the rule the rest of this
document sets out. npm is the vendors' own distribution channel for both, and
unlike a bare download it can actually be verified, so that is what the build
does and what it checks.

`npm audit signatures` runs as a build step and the build fails closed on it.
It checks two different things, and the two packages do not both get both:

| | Claude Code | Codex |
| --- | --- | --- |
| npm registry signature | yes | yes |
| SLSA build provenance attestation | **no** | yes |

The registry signature means the bytes installed are the bytes the publisher
uploaded, verifiable against npm's own public key. The SLSA attestation goes
further and ties the tarball to the source commit and the workflow that built
it. Measured 2026-09-19 against the registry: `@openai/codex` publishes one
and `@anthropic-ai/claude-code` does not. "Installed from npm" is therefore a
weaker statement for Claude Code than for Codex, and this table exists so
that difference is visible rather than implied.

Nothing is executed before it is verified. npm runs a package's lifecycle
scripts during install by default, as root in a build like this one, and it
does that before `npm audit signatures` has had any chance to say whether
the tarball is genuine. A tampered package would run first and be rejected
afterwards, which is the wrong way round. So the build installs with
`--ignore-scripts`, verifies, and only then runs the postinstall of a
package that has just passed.

Only Claude Code needs that postinstall. Codex declares no lifecycle scripts
at all. Claude Code's does not download anything either, which is worth
stating because a wrapper package that fetches a binary at install time
would put that binary outside everything described above: the native
executable ships as a platform specific `optionalDependency`
(`@anthropic-ai/claude-code-linux-x64`), which npm installs and
`npm audit signatures` covers like any other package, and the postinstall
only selects and links it.

These two are **version pinned**, which nothing installed with apt is. The
difference is deliberate. An apt package is unpinned because Ubuntu and these
vendors ship security fixes by moving a version inside a release, with a
distribution maintainer sitting between upstream and this image. npm has no
such gatekeeper: whatever a publisher pushes is what `npm install` resolves
seconds later. The pin is what lets Renovate's seven day `minimumReleaseAge`
and `Pin Only` stand between a fresh npm release and this image, and it is
the only defence that works against a release that is well formed and
malicious.

That window covers updates Renovate proposes, and nothing else. A version
typed into the Dockerfile by hand never passes through it, so an initial pin
added on the day it was published would walk straight past the control the
pin exists to enable. Initial values are therefore chosen to be at least
seven days old when they are introduced, and the same applies to anyone
changing one by hand rather than letting Renovate do it.

## Getting a shell without an IDE

Every repository with a development container carries a `make shell` target,
so the container is usable from an ordinary terminal and nothing here
requires an editor. The target builds the container and runs it with the
repository mounted at `/workspace`, plus the two agent configuration
directories bind mounted from the host:

The target builds the container, then runs it roughly like this:

```shell
podman run --rm -it --userns=keep-id \
  -v "${PWD}:/workspace:rw,Z" \
  -v "${HOME}/.claude:/home/dev/.claude:rw,z" \
  -v "${HOME}/.codex:/home/dev/.codex:rw,z" \
  -w /workspace "${DEV_IMAGE}" bash
```

The authoritative version is the `shell` target in each repository's own
`Makefile`, not this sketch.

Sessions, transcripts and credentials therefore live on the host and survive
the container, and the same history is visible whether an agent is run from
this shell or from the host.

Two things about those two mounts specifically:

- **Lowercase `z`, not uppercase `Z`.** `Z` labels a mount private to one
  container, and applying it to a directory the host's own agents also use
  would take that directory away from them and from every other repository's
  container. `z` is the shared label, which is what a directory used by more
  than one consumer needs.
- **`SHELL_EXTRA_MOUNTS` exists for symlinks that leave the tree.** A bind
  mount carries a symlink as a symlink, so if anything under `~/.claude`
  points outside `~/.claude`, it dangles inside the container until its
  target is mounted too. That is a per machine detail, so it is a variable
  rather than a hard coded path.

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
