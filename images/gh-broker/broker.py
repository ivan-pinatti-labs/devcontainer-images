"""gh broker: run allowlisted gh commands for the workbench, holding the token.

Listens on a unix socket. Each connection carries one JSON line:
{"argv": [...], "cwd": "...", "stdin": "..."}. The reply is one JSON object:
{"rc": int, "out": str, "err": str}. Every request is logged to stdout, so
`podman logs gh-broker` is the record of what the workbench did on GitHub.

The token comes from the GH_TOKEN environment variable, which the host
passes as a podman secret and which never leaves this container. Refused:
anything not in /etc/gh-broker/allowlist.json, any repository outside the
allowed owners, flags that read a file, and every `gh api` write except
replying to a review comment and the GraphQL mutations the allowlist names
(resolving a review thread).
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading

ALLOW = json.load(open("/etc/gh-broker/allowlist.json"))
COMMANDS = set(ALLOW["commands"])
OWNERS = tuple(o.lower() + "/" for o in ALLOW["owners"])
SOCK = os.environ.get("GH_BROKER_SOCK", "/run/gh-broker/gh.sock")
REPO_FLAGS = ("-R", "--repo")


URL = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/", re.I)


def repos_ok(argv):
    # gh takes full URLs for pull requests, issues and repositories too
    # (`gh pr comment https://github.com/<owner>/<repo>/pull/1`), which name
    # a repository without -R.
    for a in argv:
        for owner in URL.findall(a):
            if not (owner.lower() + "/").startswith(OWNERS):
                return False
    for i, a in enumerate(argv):
        value = None
        if a in REPO_FLAGS and i + 1 < len(argv):
            value = argv[i + 1]
        elif a.startswith("--repo="):
            value = a.split("=", 1)[1]
        if value is not None and not value.lower().startswith(OWNERS):
            return False
    return True


REPLY = re.compile(r"^repos/([^/]+)/[^/]+/pulls/\d+/comments/\d+/replies$", re.I)
MUTATIONS = frozenset(ALLOW["api"].get("graphql_mutations", []))


def mutation_fields(query):
    """The top level fields of a GraphQL mutation, the operations it runs.
    Aliases (`x: deleteRepository(...)`) are resolved to the real field, and
    string literals and argument lists are skipped. None when a fragment
    spread appears, which could hide an operation."""
    m = re.search(r"\bmutation\b[^{]*\{", query)
    names, depth, i, in_string = [], 1, m.end(), False
    token, alias_pending = "", False
    while i < len(query) and depth > 0:
        c = query[i]
        if in_string:
            if c == "\\":
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c in "{(":
            if depth == 1 and token:
                names.append(token)
            token, alias_pending = "", False
            depth += 1
        elif c in "})":
            if depth == 1 and token:
                names.append(token)
            token = ""
            depth -= 1
        elif depth == 1:
            if c.isalnum() or c == "_":
                token += c
            elif c == ":":
                token, alias_pending = "", True
            elif c == ".":
                return None
            elif token and not alias_pending:
                names.append(token)
                token = ""
            elif token and alias_pending:
                alias_pending = False
        i += 1
    return names


def api_ok(argv):
    rest = argv[1:]
    method = None
    path = None
    fields = []
    i = 0
    while i < len(rest):
        a = rest[i]
        # Nothing here needs another host, custom headers or a request body
        # read from a file.
        if a in ("--hostname", "-H", "--header", "--input") or a.startswith(
            ("--hostname=", "--header=", "--input=", "-H")
        ):
            return False
        # Combined short forms, -XPOST and -fbody=..., split into flag and value.
        if len(a) > 2 and a[:2] in ("-X", "-f", "-F") and not a.startswith("--"):
            rest = rest[:i] + [a[:2], a[2:]] + rest[i + 1:]
            a = rest[i]
        if a in ("-X", "--method"):
            method = rest[i + 1].upper() if i + 1 < len(rest) else ""
            i += 2
            continue
        if a.startswith("--method="):
            method = a.split("=", 1)[1].upper()
        elif a in ("-f", "-F", "--field", "--raw-field"):
            fields.append(rest[i + 1] if i + 1 < len(rest) else "")
            i += 2
            continue
        elif a.startswith(("--field=", "--raw-field=")):
            fields.append(a.split("=", 1)[1])
        elif path is None and not a.startswith("-"):
            path = a.lstrip("/")
        i += 1
    if path is None:
        return False
    # A field value of @file reads it from a file here, in the broker.
    if any("=@" in f or f.startswith("@") for f in fields):
        return False
    if path == "graphql":
        query = " ".join(fields)
        if not re.search(r"\bmutation\b", query):
            return True
        # One mutation, running exactly one allowed operation.
        if len(re.findall(r"\bmutation\b", query)) != 1:
            return False
        ops = mutation_fields(query)
        return ops is not None and len(ops) == 1 and ops[0] in MUTATIONS
    reply = REPLY.match(path)
    if reply:
        # A reply to a review comment: a POST (gh sends one whenever fields
        # are given) with an inline body and nothing else.
        return (
            (reply.group(1).lower() + "/").startswith(OWNERS)
            and method in (None, "POST")
            and fields != []
            and all(f.startswith("body=") for f in fields)
        )
    # Everything else is read only: GET, and no fields, since gh turns any
    # request with fields into a POST.
    return (
        method in (None, "GET")
        and not fields
        and path.lower().startswith(tuple("repos/" + o for o in OWNERS))
    )


# Flags that make gh read (or write) a file named by the caller. The file
# would be read here, in the broker, where /proc/self/environ holds the token
# and WORKBENCH_ROOT holds every workspace; a body posted from one is a body
# the caller can read back. Bodies come from stdin instead (`--body-file -`),
# which the workbench shim forwards.
FILE_FLAGS = ("--body-file", "-F", "--recover", "--notes-file")


def files_ok(argv):
    for i, a in enumerate(argv):
        if a in FILE_FLAGS:
            if i + 1 >= len(argv) or argv[i + 1] != "-":
                return False
        elif a.startswith(tuple(f + "=" for f in FILE_FLAGS if f.startswith("--"))):
            if a.split("=", 1)[1] != "-":
                return False
        elif a.startswith("-F") and len(a) > 2 and a[2:] != "-":
            return False
    return True


def allowed(argv):
    if not argv:
        return False
    if argv[0] == "api":
        return api_ok(argv)
    return " ".join(argv[:2]) in COMMANDS and repos_ok(argv) and files_ok(argv)


def serve(conn):
    with conn:
        try:
            req = json.loads(conn.makefile().readline())
            argv = [str(a) for a in req["argv"]]
        except (ValueError, KeyError, TypeError):
            conn.sendall(b'{"rc":2,"out":"","err":"gh-broker: malformed request\\n"}')
            return
        if not allowed(argv):
            print("REFUSE", json.dumps(argv), flush=True)
            msg = f"gh-broker: 'gh {' '.join(argv[:2])}' is not allowed from the workbench (images/gh-broker/allowlist.json)\n"
            conn.sendall(json.dumps({"rc": 126, "out": "", "err": msg}).encode())
            return
        print("RUN", json.dumps(argv), "in", req.get("cwd"), flush=True)
        cwd = req.get("cwd")
        cwd = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else "/"
        try:
            p = subprocess.run(["gh", *argv], cwd=cwd, input=req.get("stdin") or "",
                              capture_output=True, text=True, timeout=300)
            reply = {"rc": p.returncode, "out": p.stdout, "err": p.stderr}
        except subprocess.TimeoutExpired:
            reply = {"rc": 124, "out": "", "err": "gh-broker: timed out after 300s\n"}
        conn.sendall(json.dumps(reply).encode())


def main():
    if not os.environ.get("GH_TOKEN"):
        print("gh-broker: GH_TOKEN is not set; start it with the gh-devcontainer podman secret", file=sys.stderr)
        return 1
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    s = socket.socket(socket.AF_UNIX)
    s.bind(SOCK)
    os.chmod(SOCK, 0o660)
    s.listen()
    print("gh-broker: listening on", SOCK, flush=True)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
