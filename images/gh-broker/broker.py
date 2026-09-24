"""gh broker: run allowlisted gh commands for the workbench, holding the token.

Listens on a unix socket. Each connection carries one JSON line:
{"argv": [...], "cwd": "...", "stdin": "..."}. The reply is one JSON object:
{"rc": int, "out": str, "err": str}. Every request is logged to stdout, so
`podman logs gh-broker` is the record of what the workbench did on GitHub.

The token comes from the GH_TOKEN environment variable, which the host
passes as a podman secret and which never leaves this container. Refused:
anything not in /etc/gh-broker/allowlist.json, `api` with a method other than
GET or with fields, GraphQL mutations, and any repository outside the
allowed owners.
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


def repos_ok(argv):
    for i, a in enumerate(argv):
        value = None
        if a in REPO_FLAGS and i + 1 < len(argv):
            value = argv[i + 1]
        elif a.startswith("--repo="):
            value = a.split("=", 1)[1]
        if value is not None and not value.lower().startswith(OWNERS):
            return False
    return True


def api_ok(argv):
    rest = argv[1:]
    method = "GET"
    path = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-X", "--method"):
            method = rest[i + 1].upper() if i + 1 < len(rest) else ""
            i += 2
            continue
        if a.startswith("--method="):
            method = a.split("=", 1)[1].upper()
        elif a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("--field=", "--raw-field=", "--input=")):
            if not (path == "graphql" and a in ("-f", "-F", "--raw-field", "--field")):
                return False
        elif path is None and not a.startswith("-"):
            path = a.lstrip("/")
        i += 1
    if path == "graphql":
        query = " ".join(rest)
        return not re.search(r"\bmutation\b", query)
    return method in ALLOW["api"]["methods"] and path is not None and path.lower().startswith(tuple("repos/" + o for o in OWNERS))


def allowed(argv):
    if not argv:
        return False
    if argv[0] == "api":
        return api_ok(argv)
    return " ".join(argv[:2]) in COMMANDS and repos_ok(argv)


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
