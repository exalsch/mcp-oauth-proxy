from argon2 import PasswordHasher
from mcp_oauth_proxy.hash_cli import hash_cli_main


def test_hash_cli_prints_verifiable_hash(capsys):
    rc = hash_cli_main(["hunter2"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("$argon2")
    PasswordHasher().verify(out, "hunter2")  # does not raise
