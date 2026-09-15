# The shared base image every ivan-pinatti-labs repository is developed and
# run inside.
#
# It carries only what is common to all of them: git, the handful of tools
# asdf's own plugins need, asdf itself, and a rootless container runtime for
# the repositories whose tooling starts containers of its own. Everything a
# repository actually pins (github-cli, pre-commit, nodejs and whatever it
# adds later) is installed from that repository's own .tool-versions in a
# layer on top of this one, so this image never has to know which
# repositories exist or what they pin.
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
#   ca-certificates  every download below and every plugin's own downloads
#   curl             how asdf plugins fetch their releases
#   git              the point of the image, and how asdf installs plugins
#   gnupg            asdf-nodejs verifies release signatures with it
#   jq               used by this organization's scripts and hooks
#   make             most of these repositories drive their tasks with it
#   openssh-client   git over ssh, and rsync-crypt's own test suite
#   procps           ps, which pre-commit and several scripts shell out to
#   python3          pre-commit runs on it
#   tar unzip xz-utils   the archive formats asdf plugins ship in
#
# And the pieces that let a repository's own tooling start containers from
# inside this one: pre-commit hooks such as hadolint-docker and
# actionlint-docker, and a compose stack. They do nothing unless the
# development container is started with the opt in flags docs/IMAGES.md
# describes; without them, nesting fails and SELinux keeps confining the
# container.
#
#   podman           the nested runtime, rootless like the host's
#   podman-docker    a `docker` command that runs podman, because pre-commit's
#                    docker_image hooks call `docker` by name
#   crun catatonit   the OCI runtime podman uses, and the init it runs under
#   fuse-overlayfs   the nested storage driver (see containers/storage.conf)
#   passt            rootless container networking
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
    openssh-client \
    passt \
    podman \
    podman-docker \
    procps \
    python3 \
    tar \
    uidmap \
    unzip \
    xz-utils \
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

# asdf has been a single Go binary since 0.16, so it installs by download
# rather than by cloning a shell repository the way older documentation
# describes.
#
# ASDF_SHA256 is not a value Renovate can derive, so a version bump has to
# carry a new one. Recompute it with:
#
#   curl -fsSL https://github.com/asdf-vm/asdf/releases/download/v<version>/asdf-v<version>-linux-amd64.tar.gz \
#     | sha256sum
#
# The archive is verified before anything out of it is executed.
# renovate: datasource=github-releases depName=asdf-vm/asdf
ARG ASDF_VERSION=0.20.0
ARG ASDF_SHA256=9c25e1af7cc4c9d59ff3736eba14fd000480c32929258f80d8c5a8b290ebee14
# The checksum is written to a file and checked from it rather than piped
# into sha256sum. A pipe would need `SHELL ["/bin/bash", "-o", "pipefail",
# "-c"]` to avoid masking a failure on its left-hand side, and Podman's
# default OCI image format ignores SHELL entirely (it warns and carries on),
# so the guard would hold under Docker and quietly not under Podman, which
# is the runtime this organization actually builds with.
RUN curl -fsSL -o /tmp/asdf.tar.gz \
    "https://github.com/asdf-vm/asdf/releases/download/v${ASDF_VERSION}/asdf-v${ASDF_VERSION}-linux-amd64.tar.gz" \
  && printf '%s  %s\n' "${ASDF_SHA256}" /tmp/asdf.tar.gz > /tmp/asdf.sha256 \
  && sha256sum --check --strict /tmp/asdf.sha256 \
  && tar -xzf /tmp/asdf.tar.gz -C /usr/local/bin asdf \
  && rm /tmp/asdf.tar.gz /tmp/asdf.sha256 \
  && asdf version

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

# asdf resolves tools through its shims directory, which has to be on PATH
# before anything a repository pins can be found. The sbin directories are
# listed too: an image built FROM this one runs its own RUN steps with this
# PATH, and without them tools such as setcap and usermod are not found by
# name there.
ENV HOME=/home/dev \
    ASDF_DATA_DIR=/home/dev/.asdf \
    PATH=/home/dev/.asdf/shims:/home/dev/.asdf/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN mkdir -p "${ASDF_DATA_DIR}"

LABEL org.opencontainers.image.source="https://github.com/ivan-pinatti-labs/devcontainer-images" \
      org.opencontainers.image.description="Base development image for the ivan-pinatti-labs repositories: git, asdf, the tools its plugins need, and rootless Podman for nested containers." \
      org.opencontainers.image.licenses="Apache-2.0"

CMD ["/bin/bash"]
