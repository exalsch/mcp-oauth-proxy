"""mcp-oauth-proxy: OAuth 2.1 front end wrapping a stdio MCP server for claude.ai."""

__all__ = ["main"]


def main() -> None:
    from .app import run
    run()
