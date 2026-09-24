# The workbench: where you and the coding agents work.
#
# The terminal agents (Claude Code, Codex) and the VS Code server with its
# extensions all run in here, as two views of the same container. It is the
# only layer holding credentials, and even here the dangerous ones are kept
# out: the GitHub token stays in the gh broker, the ssh key in the ssh-agent
# container, and all traffic leaves through the egress proxy. Project code
# (hooks, tests, installs, throwaway binaries) does not run here at all; it
# goes to L2 through `l2`. docs/LAYERS.md has the whole picture.
ARG BASE_IMAGE=localhost/devcontainer-base:local

# The pinned VS Code extensions, installed in a stage of their own so the VS
# Code server used to install them never reaches the final image. The server
# the editor actually talks to is downloaded by the editor when it attaches,
# for whatever VS Code version you run; only the extensions are fixed here.
# hadolint ignore=DL3006
FROM ${BASE_IMAGE} AS extensions
# A build stage only; nothing from it runs, and only the extensions directory
# is copied out.
# hadolint ignore=DL3002
USER 0:0
# Any recent release installs extensions the same way; this one only has to
# exist and match its published checksum.
ARG VSCODE_COMMIT=7debcd0e2acdea1c52de81bf9ee1620444407dda
COPY vscode/extensions.txt /tmp/extensions.txt
# No pipefail (DL4006): Podman's default image format ignores SHELL, so it
# would not hold under the runtime this builds with. Each pipe below ends in a
# command that fails on its own when its input is wrong (sha256sum -c, diff).
# hadolint ignore=DL4006
RUN set -eu; \
  meta="$(curl -fsSL "https://update.code.visualstudio.com/api/versions/commit:${VSCODE_COMMIT}/server-linux-x64/stable")"; \
  url="$(printf '%s' "${meta}" | jq -r .url)"; \
  sum="$(printf '%s' "${meta}" | jq -r .sha256hash)"; \
  curl -fsSL -o /tmp/server.tgz "${url}"; \
  echo "${sum}  /tmp/server.tgz" | sha256sum -c -; \
  mkdir -p /tmp/server /opt/vscode-extensions; \
  tar -xzf /tmp/server.tgz -C /tmp/server --strip-components=1; \
  grep -vE '^\s*(#|$)' /tmp/extensions.txt | while read -r ext; do \
    /tmp/server/bin/code-server --accept-server-license-terms \
      --extensions-dir /opt/vscode-extensions --install-extension "${ext}" \
      || exit 1; \
  done; \
  /tmp/server/bin/code-server --accept-server-license-terms \
    --extensions-dir /opt/vscode-extensions --list-extensions --show-versions \
    | sort > /tmp/installed.txt; \
  grep -vE '^\s*(#|$)' /tmp/extensions.txt | sort | diff -u - /tmp/installed.txt; \
  chmod -R a-w,a+rX /opt/vscode-extensions

# hadolint ignore=DL3006
FROM ${BASE_IMAGE}
USER 0:0

# Why each of these:
#
#   nodejs           the runtime the coding agent CLIs are written for
#   openssh-client   git over ssh, through the ssh-agent container's socket
#   make             most repositories drive their tasks with it
#   podman, crun, catatonit, fuse-overlayfs, passt, uidmap, libcap2-bin
#                    the nested runtime that starts L2 containers
#                    (docs/IMAGES.md, "Running containers inside it")
#   podman-compose   a workload worth isolating can be a whole stack
#   nftables         a nested bridge network, for repositories that opt in
#   bubblewrap, socat, ripgrep
#                    Claude Code's own sandbox for the commands it runs
#
# There is no gh here: bin/gh sends every gh command to the gh broker, which
# holds the token. There is no pre-commit either: hooks run in L2.
# hadolint ignore=DL3008
RUN printf '%s\n' \
      'deb [arch=amd64 signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main' \
      > /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
    bubblewrap \
    catatonit \
    crun \
    fuse-overlayfs \
    libcap2-bin \
    make \
    nftables \
    nodejs \
    openssh-client \
    passt \
    podman \
    podman-compose \
    ripgrep \
    socat \
    uidmap \
  && rm -rf /var/lib/apt/lists/*

# Ubuntu ships newuidmap and newgidmap setuid root, and inside a rootless
# container the kernel refuses that write (measured 2026-09-15). A file
# capability works, as Fedora and quay.io/podman/stable ship them.
RUN chmod 0755 /usr/bin/newuidmap /usr/bin/newgidmap \
  && setcap cap_setuid=ep /usr/bin/newuidmap \
  && setcap cap_setgid=ep /usr/bin/newgidmap \
  && usermod \
    --add-subuids 1-999 --add-subuids 1001-65535 \
    --add-subgids 1-999 --add-subgids 1001-65535 \
    dev

# The coding agent CLIs, pinned, installed with lifecycle scripts off, checked
# with `npm audit signatures`, and only then allowed to run the one
# postinstall that is needed. See docs/TOOL_SOURCES.md for why npm, why
# pinned, and what each package's signature does and does not prove.
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.274
# renovate: datasource=npm depName=@openai/codex
ARG CODEX_VERSION=0.154.0
WORKDIR /opt/agent-clis
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

# The nested runtime's configuration and the crun wrapper; each file explains
# itself.
COPY containers/ /tmp/containers/
RUN install -m 0644 /tmp/containers/containers.conf /tmp/containers/storage.conf /etc/containers/ \
  && install -D -m 0755 /tmp/containers/crun-without-masked-paths /usr/local/libexec/devcontainer/crun \
  && install -D -m 0644 /tmp/containers/containers-bridge-network.conf /usr/local/share/devcontainer/containers-bridge-network.conf \
  && install -d -o 1000 -g 1000 /home/dev/.config /home/dev/.config/containers \
  && install -m 0644 -o 1000 -g 1000 /tmp/containers/user-containers.conf /home/dev/.config/containers/containers.conf \
  && rm -rf /tmp/containers

# The workbench's own tools, and the policies neither agent can edit: root
# owned and read only to the dev account.
COPY bin/l2 bin/l2-hooks-install bin/l2-pre-commit bin/gh /usr/local/bin/
COPY bin/route-to-l2 /usr/local/libexec/workbench/route-to-l2
COPY share/git-hook /usr/local/share/workbench/git-hook
COPY claude/managed-settings.json /etc/claude-code/managed-settings.json
COPY codex/requirements.toml /etc/codex/requirements.toml

# The extensions, read only. The editor's server looks for them under
# ~/.vscode-server/extensions, which is a link to this root owned directory,
# so neither an extension nor anything else running here can add, update or
# replace one. Auto update is off in the server's machine settings.
COPY --from=extensions --chown=0:0 /opt/vscode-extensions /opt/vscode-extensions
COPY vscode/machine-settings.json /home/dev/.vscode-server/data/Machine/settings.json
RUN ln -s /opt/vscode-extensions /home/dev/.vscode-server/extensions \
  && install -d -o 1000 -g 1000 \
    /home/dev/.claude /home/dev/.codex /home/dev/.local /home/dev/.local/share \
    /home/dev/.local/share/containers \
  && chown -R 1000:1000 /home/dev/.vscode-server \
  && chown -h 1000:1000 /home/dev/.vscode-server/extensions

USER 1000:1000
WORKDIR /workspace

# Agent configuration lives in the directories the workbench mounts for it,
# never in the host's own ~/.claude or ~/.codex. The CLIs are pinned by this
# image, so their own updaters are off. NODE_USE_ENV_PROXY makes Node's fetch
# honour the egress proxy variables the workbench is started with.
ENV CLAUDE_CONFIG_DIR=/home/dev/.claude \
    CODEX_HOME=/home/dev/.codex \
    DISABLE_AUTOUPDATER=1 \
    NODE_USE_ENV_PROXY=1 \
    GH_BROKER_SOCK=/run/gh-broker/gh.sock \
    L2_IMAGE=localhost/devcontainer-l2:local

LABEL org.opencontainers.image.source="https://github.com/ivan-pinatti-labs/devcontainer-images" \
      org.opencontainers.image.description="The ivan-pinatti-labs workbench: Claude Code, Codex, the VS Code server's pinned extensions and the nested runtime that starts L2. Holds no GitHub token and no ssh key." \
      org.opencontainers.image.licenses="Apache-2.0"

CMD ["/bin/bash"]
