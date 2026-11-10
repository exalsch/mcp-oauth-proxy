FROM python:3.12-slim

# uv for fast installs and for `uvx mcp-obsidian` backend spawning
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install the exact, hash-verified versions from uv.lock, then the project itself
# without re-resolving. A plain `uv pip install .` would pull whatever is newest
# within pyproject's ranges at build time, so rebuilds were not reproducible.
# `--locked` fails the build if uv.lock is out of sync with pyproject.toml.
RUN uv export --locked --no-dev --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps . \
    && rm /tmp/requirements.txt

# Persistent SQLite lives here (mount a volume)
ENV MCP_PROXY_DB_PATH=/data/proxy.db
VOLUME ["/data"]

# Run as a non-root user; a fresh named volume inherits /data's ownership
RUN useradd -m -u 10001 appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser

EXPOSE 8000
CMD ["mcp-oauth-proxy"]
