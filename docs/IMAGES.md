# The images

## What is here

- **`base`**, built from
  [images/base/Dockerfile](../images/base/Dockerfile) and published as
  `ghcr.io/ivan-pinatti-labs/devcontainer-base`.

The base image carries what every repository in the organization needs and
nothing that only one of them needs: git, asdf, and the tools asdf's plugins
depend on to fetch and verify their releases.

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
Renovate cannot compute. A version bump has to bring a new checksum with it:

```shell
curl -fsSL https://github.com/asdf-vm/asdf/releases/download/v<version>/asdf-v<version>-linux-amd64.tar.gz \
  | sha256sum
```

The build verifies the archive against that value before executing anything
out of it, so a mismatched pair fails the build rather than shipping an
unverified binary.
