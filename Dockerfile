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

# Run as a non-root user; a fresh named volume inherits /data's ownership
RUN useradd -m -u 10001 appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

EXPOSE 8000
CMD ["mcp-oauth-proxy"]
