"""Expose tools.py as a standalone MCP server so these tools are portable
across Claude Code, Claude Desktop, and this project's own harness.

Run with:  uv run python -m radreport_agent.mcp_server.server
"""

from mcp.server.fastmcp import FastMCP

from radreport_agent.mcp_server.tools import _HANDLERS, TOOL_SCHEMAS

mcp = FastMCP("radreport-agent")

for schema in TOOL_SCHEMAS:
    name = schema["name"]
    handler = _HANDLERS[name]
    mcp.add_tool(handler, name=name, description=schema["description"])

if __name__ == "__main__":
    mcp.run()
