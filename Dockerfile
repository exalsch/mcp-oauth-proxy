FROM python:3.12-slim

# uv for fast installs and for `uvx mcp-obsidian` backend spawning
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# Persistent SQLite lives here (mount a volume)
ENV MCP_PROXY_DB_PATH=/data/proxy.db
VOLUME ["/data"]

EXPOSE 8000
CMD ["mcp-oauth-proxy"]
