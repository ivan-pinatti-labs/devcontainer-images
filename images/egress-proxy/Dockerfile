# The egress proxy: the workbench's only way out to the network.
#
# The workbench sits on an internal podman network with no route and no DNS
# of its own. This container is on that network and on an ordinary one, and
# forwards HTTPS only to the hosts in allowlist, refusing the rest with "403
# Filtered". An extension or a package that tries to reach anything else
# fails to connect. docs/LAYERS.md, "Network".
ARG BASE_IMAGE=localhost/devcontainer-base:local
# hadolint ignore=DL3006
FROM ${BASE_IMAGE}
USER 0:0
# hadolint ignore=DL3008
RUN apt-get update \
  && apt-get install -y --no-install-recommends tinyproxy \
  && rm -rf /var/lib/apt/lists/*
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY allowlist /etc/tinyproxy/allowlist
USER 1000:1000
LABEL org.opencontainers.image.source="https://github.com/ivan-pinatti-labs/devcontainer-images" \
      org.opencontainers.image.description="Allowlist egress proxy for the ivan-pinatti-labs workbench." \
      org.opencontainers.image.licenses="Apache-2.0"
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
