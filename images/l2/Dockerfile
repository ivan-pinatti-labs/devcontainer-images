# L2: where hooks, tests, installs and throwaway binaries run.
#
# The workbench starts one of these for every hook run and every command an
# agent sends through `l2`, with no network (unless a run asks for it and goes
# through the egress proxy), no credentials, no home directory from anywhere,
# and only the working tree mounted. docs/LAYERS.md has the whole picture.
#
# This is the shared L2 image. A repository that needs more (terraform, a test
# framework) builds a thin layer on top of it and names that image in its
# .devcontainer/l2-image.
ARG BASE_IMAGE=localhost/devcontainer-base:local

# Linters that upstream only ships as container images, and that pre-commit
# hooks used to run with `docker run`. A container cannot start another
# container from inside L2 (measured 2026-09-24: the nested runtime cannot set
# up a user namespace there), so their binaries are copied out of the
# official images, pinned by digest, and bin/docker below answers the hooks
# that still call `docker run` for them.
FROM ghcr.io/hadolint/hadolint:v2.15.1-debian@sha256:aacf4eda44e40057051f5c5b02546e3ada7e8b84d4bbf9312c89524a7e9a0b51 AS hadolint
FROM docker.io/rhysd/actionlint:1.7.12@sha256:9d36088643581e728c969f35141f88139fec77280b2be23c1f66f8e40e1025e7 AS actionlint
FROM docker.io/dotenvlinter/dotenv-linter:4.0.0@sha256:815fbc7bdd429f5182c349c5772d1d4e0e9135cfb6bb324f1d52258b105ea09d AS dotenv-linter

# hadolint ignore=DL3006
FROM ${BASE_IMAGE}

USER 0:0

# Why each of these:
#
#   pre-commit       the hook runner; Ubuntu's build, for provenance
#   python3-venv     pre-commit builds a virtual environment per python hook
#   nodejs           node hooks (cspell, markdownlint) use it instead of
#                    downloading a runtime of their own through nodeenv
#   golang-go        golang hooks (checkmake) likewise, instead of pre-commit
#                    fetching a Go toolchain
#   shellcheck       actionlint runs it over `run:` blocks
#   make             most repositories drive their tests through it
#
# hadolint ignore=DL3008
RUN printf '%s\n' \
      'deb [arch=amd64 signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main' \
      > /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
    golang-go \
    make \
    nodejs \
    pre-commit \
    python3-venv \
    shellcheck \
  && rm -rf /var/lib/apt/lists/*

COPY --from=hadolint /bin/hadolint /usr/local/bin/hadolint
COPY --from=actionlint /usr/local/bin/actionlint /usr/local/bin/actionlint
COPY --from=dotenv-linter /dotenv-linter /usr/local/bin/dotenv-linter

# Which image version each baked binary stands in for. bin/docker refuses a
# hook asking for a different version, so a hook bump that this image has not
# caught up with fails loudly instead of linting with the wrong release.
ENV L2_BAKED_IMAGES="ghcr.io/hadolint/hadolint=v2.15.1 docker.io/rhysd/actionlint=1.7.12 docker.io/dotenvlinter/dotenv-linter=4.0.0"

COPY bin/docker bin/l2-prepare-hooks /usr/local/bin/

# The L2 wrapper runs everything here as uid 0 (--user 0:0, overriding the
# USER below), which inside the workbench's
# nested user namespace is the workbench's own dev account: files a hook writes
# into the working tree stay owned by you. /root is where pre-commit keeps its
# environments, on a volume the wrapper mounts per repository.
USER 1000:1000
WORKDIR /workspace
ENV HOME=/root

LABEL org.opencontainers.image.source="https://github.com/ivan-pinatti-labs/devcontainer-images" \
      org.opencontainers.image.description="L2 of the ivan-pinatti-labs images: pre-commit, language runtimes and baked linters, run with no network and no credentials." \
      org.opencontainers.image.licenses="Apache-2.0"
