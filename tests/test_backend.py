import json
import os

from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.secret_gate import hash_secret
from mcp_oauth_proxy.backend import build_backend_config


def _settings(**over):
    base = dict(public_url="https://x", access_secret_hash=hash_secret("s"),
                backend_command="uvx", backend_args=["mcp-obsidian"],
                backend_env={"OBSIDIAN_API_KEY": "k", "OBSIDIAN_HOST": "100.64.0.2"})
    base.update(over)
    return Settings(**base)


def test_legacy_single_backend_becomes_one_server():
    cfg = build_backend_config(_settings())
    servers = cfg["mcpServers"]
    assert len(servers) == 1
    (name, spec), = servers.items()
    assert spec["command"] == "uvx"
    assert spec["args"] == ["mcp-obsidian"]
    assert spec["env"]["OBSIDIAN_API_KEY"] == "k"
    assert spec["env"]["OBSIDIAN_HOST"] == "100.64.0.2"
    assert spec["keep_alive"] is True


def test_secret_env_not_leaked_to_any_child():
    os.environ["MCP_PROXY_ACCESS_SECRET_HASH"] = "leaky"
    try:
        cfg = build_backend_config(_settings())
        for spec in cfg["mcpServers"].values():
            assert "MCP_PROXY_ACCESS_SECRET_HASH" not in spec["env"]
    finally:
        del os.environ["MCP_PROXY_ACCESS_SECRET_HASH"]


def test_path_forwarded_to_each_child():
    cfg = build_backend_config(_settings())
    for spec in cfg["mcpServers"].values():
        assert "PATH" in spec["env"]


def test_servers_config_file_multi_server(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {
        "obsidian": {"command": "uvx", "args": ["mcp-obsidian"], "env": {"OBSIDIAN_API_KEY": "k"}},
        "github": {"command": "uvx", "args": ["mcp-github"], "env": {"GITHUB_TOKEN": "g"}},
    }}))
    cfg = build_backend_config(_settings(servers_config_path=str(servers_file)))
    servers = cfg["mcpServers"]
    assert set(servers) == {"obsidian", "github"}
    assert servers["github"]["args"] == ["mcp-github"]
    assert servers["github"]["env"]["GITHUB_TOKEN"] == "g"
    # env allowlist applied per server so each child inherits PATH
    assert "PATH" in servers["obsidian"]["env"]
    assert "PATH" in servers["github"]["env"]


def test_servers_config_file_bare_mapping(tmp_path):
    servers_file = tmp_path / "servers.json"
    # no "mcpServers" wrapper -> the whole object is treated as the servers map
    servers_file.write_text(json.dumps({
        "a": {"command": "cmdA", "args": []},
        "b": {"command": "cmdB", "args": ["x"]},
    }))
    cfg = build_backend_config(_settings(servers_config_path=str(servers_file)))
    assert set(cfg["mcpServers"]) == {"a", "b"}


def test_servers_config_file_env_merges_allowlist_without_secret(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {
        "only": {"command": "c", "args": [], "env": {"FOO": "bar"}},
    }}))
    os.environ["MCP_PROXY_ACCESS_SECRET_HASH"] = "leaky"
    try:
        cfg = build_backend_config(_settings(servers_config_path=str(servers_file)))
        env = cfg["mcpServers"]["only"]["env"]
        assert env["FOO"] == "bar"
        assert "PATH" in env
        assert "MCP_PROXY_ACCESS_SECRET_HASH" not in env
    finally:
        del os.environ["MCP_PROXY_ACCESS_SECRET_HASH"]


def test_servers_config_empty_raises(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {}}))
    try:
        build_backend_config(_settings(servers_config_path=str(servers_file)))
        assert False, "expected ValueError for empty server map"
    except ValueError:
        pass


def test_servers_config_invalid_json_raises_with_path(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text("{ not valid json")
    try:
        build_backend_config(_settings(servers_config_path=str(servers_file)))
        assert False, "expected ValueError for malformed JSON"
    except ValueError as exc:
        assert str(servers_file) in str(exc)


def test_servers_config_non_object_entry_names_server(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {"bad": "not-an-object"}}))
    try:
        build_backend_config(_settings(servers_config_path=str(servers_file)))
        assert False, "expected ValueError for non-object server entry"
    except ValueError as exc:
        assert "bad" in str(exc)
