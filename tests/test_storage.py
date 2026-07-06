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


def test_singleton_created_once_and_reused(tmp_path):
    s = make_storage(tmp_path)
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return "val-1"

    assert s.get_or_create_singleton("salt", factory) == "val-1"
    assert s.get_or_create_singleton("salt", factory) == "val-1"
    assert calls["n"] == 1  # factory only ran once; second call reused stored value
