# The workbench

You are running in the ivan-pinatti-labs workbench, a container, not on the
host. What that means for the commands you run (docs/LAYERS.md in
devcontainer-images has the full picture):

- Commands that run project code (language runtimes, package managers, test
  runners, pre-commit, scripts from the working tree) are rewritten by a
  managed hook to run in L2: a throwaway container with no network, no
  credentials, and only the working tree mounted. When a tool is "not found"
  there, the repository's L2 image lacks it (`.devcontainer/l2/Dockerfile`);
  it says nothing about the host or the workbench.
- `l2 --net -- ...` gives an L2 run the egress proxy, for installs.
  `l2 --engine -- ...` is for test suites that build or start containers.
- `gh` works through a broker that holds the token and runs an allowlist of
  commands; interactive prompts are not available, so pass the flags a
  prompt would ask for. A refusal names the allowlist.
- `git push` works over ssh through an agent that holds the key.
- Network access leaves through an allowlist proxy. A "403 Filtered" means
  the host is not on it; say so rather than working around it.
- Your settings and logins here are separate from anything on the host.
