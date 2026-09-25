# The shared base image every ivan-pinatti-labs repository is developed and
# run inside.
#
# It carries only what is common to all of them: git, the handful of tools
# every repository's hooks reach for, the apt signing keys this organization
# trusts, the two coding agent command line tools every repository is worked
# on with, and a rootless container runtime for the repositories whose
# tooling starts containers of its own. Everything else a repository needs
# (github-cli, pre-commit, terraform and whatever it adds later) is installed
# with apt in a layer on top of this one, so this image never has to know
# which repositories exist or what they install.
#
# There is no version manager here. Tools come from signed package
# repositories, so what installs them is apt, and what vouches for them is a
# repository signature rather than a plugin's shell script. See
# docs/TOOL_SOURCES.md for where each tool comes from and what its
# provenance actually is.
#
# Ubuntu rather than debian:13-slim: measured 2026-09-14, ubuntu:24.04 is
# 80.7 MB and debian:13-slim is 81.1 MB, so the "slim" distinction costs
# nothing here (Ubuntu publishes no -slim variant at all), and Ubuntu is what
# this organization develops against. 26.04 is the current LTS, 31 MB larger
# than 24.04 and supported years longer.
#
# Pinned by digest as well as by tag. The tag moves with every point release,
# and a base image that changes underneath a build is exactly what pinning
# exists to prevent. Renovate updates the two halves together.
# renovate: datasource=docker depName=ubuntu
FROM docker.io/library/ubuntu:26.04@sha256:513c074113a871b51a8d16ab445c88779d6452d937a164fb5cc479f32668a41d

# apt otherwise stops to ask questions no one is there to answer.
ENV DEBIAN_FRONTEND=noninteractive

# Why each of these, since an unexplained package list grows forever:
#
#   ca-certificates  apt fetches every source below over https
#   curl             used by this organization's scripts and hooks
#   git              the point of the image
#   gnupg            verifies and dearmors the apt signing keys further down
#   jq               used by this organization's scripts and hooks
#   make             most of these repositories drive their tasks with it
#   openssh-client   git over ssh, and rsync-crypt's own test suite
#   pre-commit       the hook runner every repository in this organization
#                    uses, and the one tool the checklists cannot run without.
#                    Measured 2026-09-20: this image plus pre-commit runs 19
#                    of the 20 checklists pre-commit-checklists dogfoods,
#                    because pre-commit builds its own environment for every
#                    python, node and golang hook (it bootstraps a Go
#                    toolchain for checkmake on its own) and the container
#                    based hooks use the podman below. The exception is the
#                    terraform checklist, which invokes `terraform`, `tofu`
#                    and `tflint` by name; those stay in the one repository
#                    that uses them rather than adding their weight, and
#                    tofu's 253 vendored Go dependencies, to five containers
#                    that never call them.
#   procps           ps, which pre-commit and several scripts shell out to
#   python3          what pre-commit and its python hook environments run on
#   nodejs           the runtime both coding agent CLIs below are written for
#
# tar, unzip and xz-utils used to be here for the archive formats asdf
# plugins shipped in. Nothing unpacks a release archive any more, so they
# are gone; tar is an Essential package and stays present regardless.
#
# And the pieces that let containers run from inside this one.
#
# This is not only for a repository's own tooling (pre-commit hooks such as
# hadolint-docker and actionlint-docker, or the tflint image
# pre-commit-checklists runs its terraform checklist through). It is how this
# organization's standing rule holds once development happens in here:
# a binary that did not come from the distribution runs in a container, not
# directly on the machine. Inside a development container that means a nested
# container, so an unreviewed binary is isolated from the checkout, the agent
# credentials and the host alike. Nothing is meant to be run on the host at
# all.
#
# podman-compose is here for the same reason rather than for any one
# repository: a workload worth isolating is as likely to be a compose stack
# as a single image, and `podman compose` delegates to an external provider
# and fails without one ("looking up compose provider failed"). Installing it
# also answers `docker compose`, because podman-docker's shim maps that onto
# `podman compose`, so podman stays the runtime and docker remains only a
# fallback name for tools that hardcode it.
#
# podman-compose rather than docker-compose-v2, which Ubuntu also packages:
# the latter validates more strictly and rejects shapes the compose files in
# this organization actually use, such as an interpolated `depends_on` key
# inside an included file. Measured against docker-torrent-box-with-vpn's
# stack on 2026-09-20, where docker-compose-v2 refused what podman-compose
# parsed.
#
# These do nothing unless the development container is started with the opt
# in flags docs/IMAGES.md describes; without them, nesting fails and SELinux
# keeps confining the container.
#
#   podman           the nested runtime, rootless like the host's
#   podman-compose   the compose provider `podman compose` delegates to, so a
#                    nested workload can be a whole stack
#   podman-docker    a `docker` command that runs podman, because pre-commit's
#                    docker_image hooks call `docker` by name
#   crun catatonit   the OCI runtime podman uses, and the init it runs under
#   fuse-overlayfs   the nested storage driver (see containers/storage.conf)
#   passt            rootless container networking
#   nftables         the firewall rules netavark writes for a nested bridge
#                    network; unused unless a repository opts in to one
#   uidmap           newuidmap and newgidmap, which hand nested containers
#                    their range of user ids
#   libcap2-bin      setcap, used once below
#
# Package versions are deliberately unpinned (hadolint DL3008). Ubuntu ships
# security fixes by moving a package's version within a release, so pinning
# here would hold this image on the superseded build until someone edited
# the pin by hand, which is the opposite of what the scheduled rebuild is
# for. The digest pin above is what makes a build reproducible; the upgrade
# here is what makes a rebuild current.
# hadolint ignore=DL3008
RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    catatonit \
    crun \
    curl \
    fuse-overlayfs \
    git \
    gnupg \
    jq \
    libcap2-bin \
    make \
    nftables \
    openssh-client \
    passt \
    pre-commit \
    podman \
    podman-compose \
    podman-docker \
    procps \
    python3 \
    uidmap \
  && rm -rf /var/lib/apt/lists/*

# Ubuntu ships newuidmap and newgidmap setuid root, and inside a rootless
# container that is not enough: the kernel refuses the write ("newuidmap:
# write to uid_map failed: Operation not permitted", measured 2026-09-15).
# Fedora, and the official quay.io/podman/stable image, ship them with a file
# capability instead, which does work here. So the setuid bit comes off and
# the one capability each of them needs goes on.
RUN chmod 0755 /usr/bin/newuidmap /usr/bin/newgidmap \
  && setcap cap_setuid=ep /usr/bin/newuidmap \
  && setcap cap_setgid=ep /usr/bin/newgidmap

# The apt signing keys this organization trusts, and nothing else about
# those repositories.
#
# The keys are vendored under keyrings/ rather than downloaded here, so a
# key changing is a diff somebody reviews in a pull request instead of
# whatever the vendor served on the day of the build.
#
# Each file's set of primary certificates is compared against the list
# below, exactly: every expected fingerprint must be present and no
# unexpected one may be. Checking only that the expected fingerprint is
# somewhere in the file would be weaker than it looks, because `gpg
# --dearmor` installs every certificate the file holds and apt then accepts
# repository metadata signed by any of them. A vendor that quietly added a
# second certificate, or a tampered file that appended one, would install a
# signer nobody reviewed while the check still passed. CodeRabbit caught
# exactly that on this file's first version (pull request 10).
#
# github-cli genuinely ships two primary certificates, which is why the
# answer is an exact set rather than a single value: GitHub rotates by
# publishing the new certificate alongside the old one, and pinning only one
# of them would fail verification the day they switch.
#
# Subkeys are deliberately not listed. A subkey is bound to its primary by a
# signature gpg already verifies, so naming the primaries fixes the whole
# trust chain; listing subkeys too would only mean editing this file every
# time a vendor rotated a signing subkey under an unchanged primary.
#
# Installing a key grants nothing on its own: apt reads a keyring only when
# a sources.list entry names it with signed-by=. So this image trusts these
# three repositories in the sense that it has reviewed their keys, and pulls
# from none of them. A repository that wants github-cli, nodejs or terraform
# adds its own one line sources.list.d entry pointing at the keyring it
# needs, the same way nesting is opt in per repository rather than a default
# of the image. docs/TOOL_SOURCES.md has the exact lines.
#
# The comparison is a plain string equality on the last command rather than
# something guarded by pipefail: Podman's default OCI image format ignores
# SHELL entirely (it warns and carries on), so a pipefail guard would hold
# under Docker and quietly not under the runtime this organization actually
# builds with. Verified by swapping a vendored key for a freshly generated
# one, and again by appending an extra certificate, and watching the build
# stop both times.
COPY keyrings/ /tmp/keyrings/
# hadolint ignore=DL4006
RUN set -eu; \
  install -d -m 0755 /usr/share/keyrings; \
  for entry in \
      "github-cli:2C6106201985B60E6C7AC87323F3D4EA75716059,7F38BBB59D064DBCB3D84D725612B36462313325" \
      "nodesource:6F71F525282841EEDAF851B42F59B5F99B1BE0B4" \
      "hashicorp:D55C0D1AC78A8D8126CB631CFC9CA96ACA026560"; do \
    name="${entry%%:*}"; \
    want="${entry#*:}"; \
    got="$( \
      gpg --show-keys --with-colons "/tmp/keyrings/${name}.asc" \
        | awk -F: '$1=="pub"{p=1;next} $1=="fpr"&&p{print $10;p=0;next} {p=0}' \
        | sort \
        | paste -sd, - \
    )"; \
    if [ "${got}" != "${want}" ]; then \
      echo "${name}.asc: primary certificates ${got:-none} do not match the reviewed set ${want}" >&2; \
      exit 1; \
    fi; \
    gpg --dearmor < "/tmp/keyrings/${name}.asc" \
      > "/usr/share/keyrings/${name}.gpg"; \
    chmod 0644 "/usr/share/keyrings/${name}.gpg"; \
  done; \
  rm -rf /tmp/keyrings

# The one third party repository this image enables for itself, because it
# installs from it: NodeSource, for the Node.js the two coding agent CLIs
# below run on. Ubuntu's own nodejs is a major version behind what they
# expect.
#
# The other two keyrings stay inert here. A repository that wants github-cli
# or terraform adds its own source entry; see docs/TOOL_SOURCES.md.
# hadolint ignore=DL3008
RUN printf '%s\n' \
      'deb [arch=amd64 signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main' \
      > /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# The coding agent command line tools, and the reason this image carries
# Node.js at all. Both are worked with in every repository in this
# organization, so they belong here rather than in each one's own layer.
#
# Neither publishes an apt repository, from its vendor or any distribution,
# so this is the tflint situation again with a different answer: npm is the
# vendors' own distribution channel for both, and npm can actually be
# verified. `npm audit signatures` checks two separate things and this build
# fails closed on either.
#
#   registry signature   npm signs every tarball it serves with its own key,
#                        so the bytes installed are the bytes the publisher
#                        uploaded. Both packages have one.
#   build provenance     a SLSA attestation tying the tarball to the source
#                        commit and the workflow that built it. @openai/codex
#                        publishes one. @anthropic-ai/claude-code does not,
#                        measured 2026-09-19, so it carries the weaker of the
#                        two guarantees and docs/TOOL_SOURCES.md says so
#                        rather than letting "installed from npm" imply more
#                        than it is.
#
# Pinned, unlike the apt packages, and that difference is deliberate. An apt
# package is unpinned here because Ubuntu and these vendors ship security
# fixes by moving a version inside a release, with a distribution maintainer
# between upstream and this image. npm has no such gatekeeper: whatever the
# publisher pushed is what `npm install` resolves, seconds after they push
# it. A pin is what lets Renovate's seven day minimumReleaseAge and `Pin
# Only` stand between a fresh npm release and this image, which is the only
# defence that exists against a well formed malicious publish.
#
# The initial values are chosen to be at least seven days old at the time
# they are introduced, which Renovate's minimumReleaseAge does not do for
# them: that window governs updates Renovate proposes, not a version a person
# types into this file, so a pin added by hand the day it was published would
# walk straight past the control the pin exists to enable. CodeRabbit caught
# that on this file's first version (pull request 10).
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.276
# renovate: datasource=npm depName=@openai/codex
ARG CODEX_VERSION=0.155.0
WORKDIR /opt/agent-clis
# --ignore-scripts, and the ordering around it, is the point of this block.
#
# npm runs a package's lifecycle scripts during install by default, as root
# here, and it does that before `npm audit signatures` has had any chance to
# say whether the tarball is the one the publisher uploaded. A tampered
# package would therefore execute first and be rejected afterwards, which is
# the wrong way round. So nothing is executed until everything is verified:
# install with no scripts at all, verify, and only then run the postinstall
# of a package that has just passed. CodeRabbit raised this as CWE-494 on
# pull request 10.
#
# Only claude-code needs its script run. codex declares no lifecycle scripts
# at all, and claude-code's postinstall does not download anything: the
# native binary ships as a platform specific optionalDependency
# (@anthropic-ai/claude-code-linux-x64), which npm installs and
# `npm audit signatures` covers like any other package, and the postinstall
# only selects and links it. Verified by reading install.cjs, which contains
# no URL.
RUN set -eu; \
  npm init --yes >/dev/null; \
  npm install --ignore-scripts --no-audit --no-fund --save-exact \
    "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    "@openai/codex@${CODEX_VERSION}"; \
  npm audit signatures; \
  npm rebuild @anthropic-ai/claude-code; \
  ln -s /opt/agent-clis/node_modules/.bin/claude /usr/local/bin/claude; \
  ln -s /opt/agent-clis/node_modules/.bin/codex /usr/local/bin/codex; \
  npm cache clean --force >/dev/null 2>&1 || true; \
  claude --version; \
  codex --version

# Ubuntu's own image already ships an account at uid 1000, named 'ubuntu',
# so creating one there fails. Renaming it keeps uid and gid 1000, which is
# what makes a bind mounted working tree readable and writable under
# rootless Podman with --userns=keep-id, and gives the account a name that
# says what it is for.
RUN usermod --login dev --home /home/dev --move-home ubuntu \
  && groupmod --new-name dev ubuntu

# The nested runtime needs a range of subordinate ids for this account, and
# the range has to fit inside the user namespace this container itself runs
# in. Under rootless Podman that namespace is ids 0 to 65536, so the range is
# 1 to 65535, leaving out 1000: that is this account's own id, which a nested
# container's root is already mapped to.
#
# The 'ubuntu' lines go first. The rename above leaves them behind, naming an
# account that no longer exists and a range (100000 upwards) that no
# container of this image could use.
RUN sed -i '/^ubuntu:/d' /etc/subuid /etc/subgid \
  && usermod \
    --add-subuids 1-999 --add-subuids 1001-65535 \
    --add-subgids 1-999 --add-subgids 1001-65535 \
    dev

# Configuration for the nested runtime, plus the crun wrapper that lets it
# work in a confined SELinux domain; each file explains itself. The nodocker
# marker silences podman-docker's "Emulate Docker CLI using podman" notice,
# which it otherwise prints on every `docker` call, into the output of every
# hook that makes one.
COPY containers/ /tmp/containers/
RUN install -m 0644 /tmp/containers/containers.conf /tmp/containers/storage.conf /etc/containers/ \
  && install -D -m 0755 /tmp/containers/crun-without-masked-paths /usr/local/libexec/devcontainer/crun \
  && install -D -m 0644 /tmp/containers/containers-bridge-network.conf /usr/local/share/devcontainer/containers-bridge-network.conf \
  && install -d -o 1000 -g 1000 /home/dev/.config /home/dev/.config/containers \
  && install -m 0644 -o 1000 -g 1000 /tmp/containers/user-containers.conf /home/dev/.config/containers/containers.conf \
  && touch /etc/containers/nodocker \
  && rm -rf /tmp/containers

# Numeric rather than 'dev', which is the same account: hadolint's DL3066
# asks for a uid here because a name only means something to a runtime that
# reads this image's own /etc/passwd, while a uid is what the host actually
# sees on a bind mounted file. HOME is set explicitly for the same reason,
# rather than left to the runtime's passwd lookup.
USER 1000:1000

# Where a repository's checkout is expected to be mounted. Nothing is copied
# into the image: this is a development environment, not a build of any one
# project.
WORKDIR /workspace

# The sbin directories are listed explicitly: an image built FROM this one
# runs its own RUN steps with this PATH, and without them tools such as
# setcap and usermod are not found by name there.
ENV HOME=/home/dev \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LABEL org.opencontainers.image.source="https://github.com/ivan-pinatti-labs/devcontainer-images" \
      org.opencontainers.image.description="Base development image for the ivan-pinatti-labs repositories: git, the common command line tools, the Claude Code and Codex CLIs, this organization's trusted apt signing keys, and rootless Podman for nested containers." \
      org.opencontainers.image.licenses="Apache-2.0"

CMD ["/bin/bash"]
