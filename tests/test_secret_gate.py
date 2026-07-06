import pytest
from mcp_oauth_proxy.secret_gate import SecretGate, LockedOut, hash_secret


def make_gate(secret="hunter2", max_attempts=3, lockout=60, clock=None):
    return SecretGate(
        secret_hash=hash_secret(secret),
        max_attempts=max_attempts,
        lockout_seconds=lockout,
        now=clock or (lambda: 0.0),
    )


def test_correct_secret_verifies():
    gate = make_gate()
    assert gate.verify("ip1", "hunter2") is True


def test_wrong_secret_returns_false():
    gate = make_gate()
    assert gate.verify("ip1", "nope") is False


def test_lockout_after_max_attempts():
    gate = make_gate(max_attempts=3, lockout=60)
    for _ in range(3):
        assert gate.verify("ip1", "wrong") is False
    with pytest.raises(LockedOut) as exc:
        gate.verify("ip1", "hunter2")  # correct, but locked
    assert exc.value.retry_after == 60


def test_lockout_is_per_client_key():
    gate = make_gate(max_attempts=1)
    assert gate.verify("ipA", "wrong") is False
    with pytest.raises(LockedOut):
        gate.verify("ipA", "hunter2")
    # different key is unaffected
    assert gate.verify("ipB", "hunter2") is True


def test_lockout_expires_over_time():
    t = {"v": 0.0}
    gate = make_gate(max_attempts=1, lockout=60, clock=lambda: t["v"])
    assert gate.verify("ip1", "wrong") is False
    with pytest.raises(LockedOut):
        gate.verify("ip1", "hunter2")
    t["v"] = 61.0
    assert gate.verify("ip1", "hunter2") is True


def test_success_resets_counter():
    gate = make_gate(max_attempts=2)
    assert gate.verify("ip1", "wrong") is False
    assert gate.verify("ip1", "hunter2") is True
    # counter reset: one more wrong should not lock
    assert gate.verify("ip1", "wrong") is False
