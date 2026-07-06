import os
from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.secret_gate import hash_secret
from mcp_oauth_proxy.backend import build_backend_transport


def _settings(**over):
    base = dict(public_url="https://x", access_secret_hash=hash_secret("s"),
                backend_command="uvx", backend_args=["mcp-obsidian"],
                backend_env={"OBSIDIAN_API_KEY": "k", "OBSIDIAN_HOST": "100.64.0.2"})
    base.update(over)
    return Settings(**base)


def test_builds_transport_with_command_args_env():
    t = build_backend_transport(_settings())
    assert t.command == "uvx"
    assert t.args == ["mcp-obsidian"]
    assert t.env["OBSIDIAN_API_KEY"] == "k"
    assert t.env["OBSIDIAN_HOST"] == "100.64.0.2"
    assert t.keep_alive is True


def test_proxy_secret_env_not_leaked_to_child():
    os.environ["MCP_PROXY_ACCESS_SECRET_HASH"] = "leaky"
    try:
        t = build_backend_transport(_settings())
        assert "MCP_PROXY_ACCESS_SECRET_HASH" not in t.env
    finally:
        del os.environ["MCP_PROXY_ACCESS_SECRET_HASH"]


def test_path_is_forwarded():
    t = build_backend_transport(_settings())
    assert "PATH" in t.env
