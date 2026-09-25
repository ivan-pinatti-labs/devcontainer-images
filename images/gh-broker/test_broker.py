"""Allow and refuse cases for the gh broker, run when its image is built, so
an allowlist or parser change that reopens one fails the build."""
import sys
src = open("/usr/local/libexec/gh-broker/broker.py").read()
ns = {"__name__": "broker"}; exec(compile(src, "broker.py", "exec"), ns)
allowed = ns["allowed"]
cases = [
  (True,  "pr list"), (True, "pr view 25 -R ivan-pinatti-labs/devcontainer-images"),
  (True,  "pr comment https://github.com/ivan-pinatti-labs/gh-actions/pull/1 --body hi"),
  (True,  "api repos/ivan-pinatti-labs/gh-actions"), (True, "api graphql -f query={viewer{login}}"),
  (False, "pr comment https://github.com/someone-else/repo/pull/1 --body spam"),
  (False, "pr view github.com/evil/x/pull/2"), (False, "pr list -R evil.com/ivan-pinatti-labs/x"),
  (False, "api -XPOST repos/ivan-pinatti-labs/gh-actions/issues"), (False, "api -X DELETE repos/ivan-pinatti-labs/x"),
  (False, "api graphql -F query=@m.graphql"), (False, "api graphql -Fquery=@m.graphql"),
  (False, "api graphql -f query=mutation{x}"), (False, "api --hostname evil.com repos/ivan-pinatti-labs/x"),
  (False, "api -H X-HTTP-Method-Override:DELETE repos/ivan-pinatti-labs/x"), (False, "api --input f repos/ivan-pinatti-labs/x"),
  (False, "auth token"), (False, "repo delete ivan-pinatti-labs/x --yes"), (False, "secret list"), (False, "api user"),
]
bad = [(exp, c) for exp, c in cases if allowed(c.split()) != exp]
for exp, c in bad: print("WRONG", "expected", "allow" if exp else "refuse", ":", c)
print(f"{len(cases)-len(bad)}/{len(cases)} cases as expected")
sys.exit(1 if bad else 0)
