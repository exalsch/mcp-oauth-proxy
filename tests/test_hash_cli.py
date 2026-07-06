import io
import sys

from argon2 import PasswordHasher
from mcp_oauth_proxy.hash_cli import hash_cli_main


def test_hash_cli_prints_verifiable_hash(capsys):
    rc = hash_cli_main(["hunter2"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("$argon2")
    PasswordHasher().verify(out, "hunter2")  # does not raise


def test_hash_cli_empty_stdin_returns_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    rc = hash_cli_main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err
