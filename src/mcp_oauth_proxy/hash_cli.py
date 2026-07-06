from __future__ import annotations

import sys

from .secret_gate import hash_secret


def hash_cli_main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    secret = argv[0] if argv else sys.stdin.readline().rstrip("\n")
    if not secret:
        print("usage: mcp-oauth-proxy-hash <secret>", file=sys.stderr)
        return 2
    print(hash_secret(secret))
    return 0
