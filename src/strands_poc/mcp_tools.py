from contextlib import ExitStack
from typing import cast

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands.tools.mcp import MCPClient, MCPTransport


def _stdio_transport(
    parameters: StdioServerParameters,
) -> MCPTransport:
    return cast(MCPTransport, stdio_client(parameters))


def build_mcp_tools(stack: ExitStack) -> list:
    """
    Connect to MCP servers and return their tools.

    MCPClient supports two transport types:

    1. stdio — spawns a local process (uvx/npx MCP packages)
    2. HTTP  — connects to a remote MCP server over streamable HTTP

    Each client must be entered via the ExitStack so it is cleaned up on exit.
    Set continue_on_error=True so a missing server doesn't crash the agent.

    To add a new MCP server:
      1. Pick the transport (stdio for local packages, url= for remote servers).
      2. Instantiate MCPClient, pass it to stack.enter_context().
      3. Call list_tools_sync() and extend mcp_tools with the result.
    """
    mcp_tools = []

    # -------------------------------------------------------------------------
    # Example 1: stdio — AWS Documentation MCP server
    # Lets the agent search and read AWS docs on demand.
    # Runs as a local subprocess via uvx — no separate install needed.
    #
    docs_client = MCPClient(
        transport_callable=lambda: _stdio_transport(
            parameters=StdioServerParameters(
                command="uvx",
                args=["awslabs.aws-documentation-mcp-server@latest"],
                env={
                    "FASTMCP_LOG_LEVEL": "ERROR",
                    "AWS_DOCUMENTATION_PARTITION": "aws",
                },
            )
        ),
        prefix="awsdocs",
        continue_on_error=True,
    )
    stack.enter_context(docs_client)
    mcp_tools.extend(docs_client.list_tools_sync())
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Example 2: stdio — Filesystem MCP server
    # Gives the agent structured, permission-scoped file system access.
    # Requires Node.js: npm install -g @modelcontextprotocol/server-filesystem
    #
    # fs_client = MCPClient(
    #     transport_callable=lambda: stdio_client(
    #         StdioServerParameters(
    #             command="npx",
    #             args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    #         )
    #     ),
    #     prefix="fs",                # tool names become fs__read_file, fs__list_dir, etc.
    #     continue_on_error=True,
    # )
    # stack.enter_context(fs_client)
    # mcp_tools.extend(fs_client.list_tools_sync())
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Example 3: HTTP with auth — any authenticated remote MCP server
    #
    # authed_client = MCPClient(
    #     url="https://your-mcp-server.example.com/mcp",
    #     headers={"Authorization": f"Bearer {os.environ['MCP_API_KEY']}"},
    #     prefix="myserver",
    #     continue_on_error=True,
    # )
    # stack.enter_context(authed_client)
    # mcp_tools.extend(authed_client.list_tools_sync())
    # -------------------------------------------------------------------------

    return mcp_tools
