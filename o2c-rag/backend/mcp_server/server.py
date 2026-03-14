"""MCP (Model Context Protocol) server exposing all O2C tools for external AI assistants."""

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.customer_tools import all_customer_tools
from tools.material_tools import all_material_tools
from tools.order_tools import all_order_tools
from tools.delivery_tools import all_delivery_tools
from tools.invoice_tools import all_invoice_tools
from tools.payment_tools import all_payment_tools
from tools.credit_memo_tools import all_credit_memo_tools
from tools.analytics_tools import all_analytics_tools
from tools.rag_tools import all_rag_tools

logger = logging.getLogger(__name__)

ALL_TOOLS = (
    all_customer_tools
    + all_material_tools
    + all_order_tools
    + all_delivery_tools
    + all_invoice_tools
    + all_payment_tools
    + all_credit_memo_tools
    + all_analytics_tools
    + all_rag_tools
)

# Build a lookup from tool name → LangChain tool object
_TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def _langchain_tool_to_mcp(lc_tool) -> Tool:
    """Convert a LangChain @tool to an MCP Tool definition."""
    schema = lc_tool.args_schema.schema() if lc_tool.args_schema else {}
    return Tool(
        name=lc_tool.name,
        description=lc_tool.description or "",
        inputSchema=schema,
    )


def create_mcp_server() -> Server:
    """Create an MCP server instance with all O2C tools registered."""
    server = Server("o2c-ai-suite")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [_langchain_tool_to_mcp(t) for t in ALL_TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        tool_fn = _TOOL_MAP.get(name)
        if not tool_fn:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = await tool_fn.ainvoke(arguments)
            return [TextContent(type="text", text=str(result))]
        except Exception as e:
            logger.exception(f"MCP tool error: {name}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    return server


async def run_mcp_server():
    """Run the MCP server over stdio (for use as a subprocess)."""
    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run_mcp_server())
