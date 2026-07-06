import json
import sys

from fastmcp import Client
from fastmcp.server import create_proxy

from mcp_oauth_proxy.backend import build_backend_config
from mcp_oauth_proxy.config import Settings
from mcp_oauth_proxy.secret_gate import hash_secret


async def test_multi_server_tools_are_prefixed(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {
        "alpha": {"command": sys.executable, "args": ["tests/dummy_server.py"]},
        "beta": {"command": sys.executable, "args": ["tests/dummy_server.py"]},
    }}))
    settings = Settings(
        public_url="http://x",
        access_secret_hash=hash_secret("s"),
        servers_config_path=str(servers_file),
    )
    proxy = create_proxy(build_backend_config(settings), name="multi")
    async with Client(proxy) as client:
        tools = sorted(t.name for t in await client.list_tools())
    # each backend's tools are namespaced by its config key
    assert tools == ["alpha_echo", "beta_echo"]


async def test_single_server_tools_are_not_prefixed(tmp_path):
    servers_file = tmp_path / "servers.json"
    servers_file.write_text(json.dumps({"mcpServers": {
        "solo": {"command": sys.executable, "args": ["tests/dummy_server.py"]},
    }}))
    settings = Settings(
        public_url="http://x",
        access_secret_hash=hash_secret("s"),
        servers_config_path=str(servers_file),
    )
    proxy = create_proxy(build_backend_config(settings), name="one")
    async with Client(proxy) as client:
        tools = sorted(t.name for t in await client.list_tools())
    # a single backend is mounted unprefixed (backward compatible)
    assert tools == ["echo"]
