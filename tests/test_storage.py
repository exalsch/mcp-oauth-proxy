import time
from mcp_oauth_proxy.storage import Storage


def make_storage(tmp_path):
    return Storage(str(tmp_path / "t.db"))


def test_client_roundtrip(tmp_path):
    s = make_storage(tmp_path)
    assert s.get_client("c1") is None
    s.upsert_client("c1", '{"a":1}')
    assert s.get_client("c1") == '{"a":1}'
    s.upsert_client("c1", '{"a":2}')
    assert s.get_client("c1") == '{"a":2}'


def test_txn_pop_is_delete_on_read(tmp_path):
    s = make_storage(tmp_path)
    s.save_txn("t1", '{"x":1}', time.time() + 100)
    assert s.pop_txn("t1") == '{"x":1}'
    assert s.pop_txn("t1") is None


def test_expired_txn_not_returned(tmp_path):
    s = make_storage(tmp_path)
    s.save_txn("t2", "{}", time.time() - 1)
    assert s.pop_txn("t2") is None


def test_auth_code_pop(tmp_path):
    s = make_storage(tmp_path)
    s.save_auth_code("code1", "clientA", '{"scopes":[]}', time.time() + 100)
    got = s.pop_auth_code("code1")
    assert got == ("clientA", '{"scopes":[]}')
    assert s.pop_auth_code("code1") is None


def test_access_token_roundtrip_and_delete(tmp_path):
    s = make_storage(tmp_path)
    exp = time.time() + 100
    s.save_access_token("at1", "clientA", "read write", exp)
    got = s.get_access_token("at1")
    assert got[0] == "clientA" and got[1] == "read write"
    s.delete_access_token("at1")
    assert s.get_access_token("at1") is None


def test_refresh_token_nullable_expiry(tmp_path):
    s = make_storage(tmp_path)
    s.save_refresh_token("rt1", "clientA", "", None)
    got = s.get_refresh_token("rt1")
    assert got[0] == "clientA" and got[2] is None


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "p.db")
    Storage(path).upsert_client("c9", '{"k":9}')
    assert Storage(path).get_client("c9") == '{"k":9}'


def test_expired_auth_code_not_returned(tmp_path):
    s = make_storage(tmp_path)
    s.save_auth_code("codeX", "clientA", "{}", time.time() - 1)
    assert s.pop_auth_code("codeX") is None


def test_tokens_stored_hashed_not_plaintext(tmp_path):
    # A leak of the DB file must not hand out usable credentials: the raw token
    # is never the stored key; only its SHA-256 (64 hex chars) is persisted.
    s = make_storage(tmp_path)
    s.save_access_token("plain-access-token", "clientA", "read", time.time() + 100)
    s.save_refresh_token("plain-refresh-token", "clientA", "read", None)
    s.save_auth_code("plain-code", "clientA", "{}", time.time() + 100)
    s.save_txn("plain-txn", "{}", time.time() + 100)

    # lookups by the raw value still work transparently
    assert s.get_access_token("plain-access-token")[0] == "clientA"
    assert s.get_refresh_token("plain-refresh-token")[0] == "clientA"

    for table, col, raw in (
        ("access_tokens", "token", "plain-access-token"),
        ("refresh_tokens", "token", "plain-refresh-token"),
        ("auth_codes", "code", "plain-code"),
        ("txns", "txn_id", "plain-txn"),
    ):
        keys = [r[0] for r in s._conn.execute(f"SELECT {col} FROM {table}").fetchall()]
        assert raw not in keys
        assert all(len(k) == 64 for k in keys)


def test_delete_expired_purges_stale_rows(tmp_path):
    s = make_storage(tmp_path)
    now = time.time()
    s.save_txn("t_old", "{}", now - 10)
    s.save_auth_code("c_old", "cli", "{}", now - 10)
    s.save_access_token("at_old", "cli", "", now - 10)
    s.save_refresh_token("rt_old", "cli", "", now - 10)
    s.save_refresh_token("rt_keep", "cli", "", None)      # never expires
    s.save_access_token("at_new", "cli", "", now + 100)

    s.delete_expired()

    assert s.get_access_token("at_old") is None
    assert s.get_refresh_token("rt_old") is None
    assert s.get_access_token("at_new") is not None       # still valid, kept
    assert s.get_refresh_token("rt_keep") is not None      # null expiry, kept
    for table in ("txns", "auth_codes"):
        assert s._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_get_txn_peeks_without_consuming(tmp_path):
    s = make_storage(tmp_path)
    s.save_txn("t1", '{"x":1}', time.time() + 100)
    assert s.get_txn("t1") == '{"x":1}'
    assert s.get_txn("t1") == '{"x":1}'   # still there
    assert s.pop_txn("t1") == '{"x":1}'   # pop still consumes


def test_get_txn_expired_returns_none(tmp_path):
    s = make_storage(tmp_path)
    s.save_txn("t2", "{}", time.time() - 1)
    assert s.get_txn("t2") is None
