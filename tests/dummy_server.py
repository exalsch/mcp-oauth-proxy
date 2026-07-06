from fastmcp import FastMCP

mcp = FastMCP("dummy")


@mcp.tool
def echo(text: str) -> str:
    return text


if __name__ == "__main__":
    mcp.run()
