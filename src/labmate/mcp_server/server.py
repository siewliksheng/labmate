"""Expose tools.py as a standalone MCP server so these tools are portable
across Claude Code, Claude Desktop, and this project's own harness.

Run with:  uv run python -m labmate.mcp_server.server
"""

from mcp.server.fastmcp import FastMCP

from labmate.mcp_server.tools import _HANDLERS, TOOL_SCHEMAS

mcp = FastMCP("labmate")

# NOTE: this registers the raw handlers directly, bypassing dispatch_tool's
# tracing/error-handling wrapper in tools.py -- calls made through this MCP
# server (e.g. from Claude Desktop) are not currently traced the way calls
# through agent.py's own loop are. Left as a known gap rather than silently
# assumed away; worth fixing if the MCP path becomes a primary entry point.
for schema in TOOL_SCHEMAS:
    name = schema["name"]
    handler = _HANDLERS[name]
    mcp.add_tool(handler, name=name, description=schema["description"])

if __name__ == "__main__":
    mcp.run()
