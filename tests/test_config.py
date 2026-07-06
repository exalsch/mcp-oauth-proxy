import pytest
from mcp_oauth_proxy.config import load_settings, Settings


def _base_env():
    return {
        "MCP_PROXY_PUBLIC_URL": "https://mcp.example.tld",
        "MCP_PROXY_ACCESS_SECRET_HASH": "$argon2id$v=19$m=65536,t=3,p=4$abc$def",
    }


def test_loads_required_and_defaults():
    s = load_settings(_base_env())
    assert isinstance(s, Settings)
    assert s.public_url == "https://mcp.example.tld"
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.access_token_ttl == 3600
    assert s.refresh_token_ttl == 2592000
    assert s.backend_command == "uvx"
    assert s.backend_args == ["mcp-obsidian"]
    assert s.backend_env == {}


def test_public_url_trailing_slash_stripped():
    env = _base_env() | {"MCP_PROXY_PUBLIC_URL": "https://mcp.example.tld/"}
    assert load_settings(env).public_url == "https://mcp.example.tld"


def test_backend_env_passthrough_prefix():
    env = _base_env() | {
        "MCP_BACKEND_ENV_OBSIDIAN_API_KEY": "k123",
        "MCP_BACKEND_ENV_OBSIDIAN_HOST": "100.64.0.2",
    }
    s = load_settings(env)
    assert s.backend_env == {"OBSIDIAN_API_KEY": "k123", "OBSIDIAN_HOST": "100.64.0.2"}


def test_backend_command_and_args_override():
    env = _base_env() | {"MCP_BACKEND_COMMAND": "python", "MCP_BACKEND_ARGS": "-m my.server --flag"}
    s = load_settings(env)
    assert s.backend_command == "python"
    assert s.backend_args == ["-m", "my.server", "--flag"]


def test_missing_required_raises():
    with pytest.raises(ValueError, match="MCP_PROXY_PUBLIC_URL"):
        load_settings({"MCP_PROXY_ACCESS_SECRET_HASH": "x"})
    with pytest.raises(ValueError, match="MCP_PROXY_ACCESS_SECRET_HASH"):
        load_settings({"MCP_PROXY_PUBLIC_URL": "https://x"})
