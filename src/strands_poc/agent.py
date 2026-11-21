"""
DevOps Assistant — a Strands agent that inspects and operates your local system.

Capabilities:
  - Run shell commands (via the built-in shell tool)
  - Read log files and config files
  - Answer questions about processes, disk, memory, and network
  - Summarise recent log errors in plain English
  - Extensible with any MCP server (stdio or HTTP)

Provider selection (set env vars before running):

  Bedrock (default):
    AWS credentials must be configured (aws configure / AWS_* env vars)
    uv run devops-assistant

  OpenRouter:
    export MODEL_PROVIDER=openrouter
    export OPENROUTER_API_KEY=sk-or-...
    export OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free   # any free OpenRouter model
    uv run devops-assistant

MCP servers (optional, see build_mcp_tools):
  - AWS Documentation MCP server (stdio via uvx): lets the agent look up AWS docs on demand
  - Filesystem MCP server (stdio via npx): structured, permission-scoped file system access
  - Any authenticated remote MCP server (HTTP)
"""

import os
from contextlib import ExitStack

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from strands import Agent
from strands.models import BedrockModel
from strands.models.litellm import LiteLLMModel
from strands.tools.mcp import MCPClient
from strands.vended_tools import shell, read, http_request

SYSTEM_PROMPT = """You are a senior DevOps engineer assistant running on a Linux system.
You help the operator understand and troubleshoot the system using shell commands and log files.

Guidelines:
- Prefer non-destructive, read-only commands unless the operator explicitly asks to change something.
- When asked about a problem, start with diagnostics before suggesting fixes.
- Keep output concise. For long command output, summarise and highlight anomalies.
- When you run a command, briefly explain why before running it.
- If a command might have side-effects (restarts, deletions, writes), warn the operator first.
"""


def build_model():
    provider = os.environ.get("MODEL_PROVIDER", "bedrock").lower()

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY env var is required when MODEL_PROVIDER=openrouter")
        model_id = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
        print(f"Using OpenRouter — model: {model_id}")
        return LiteLLMModel(
            client_args={"api_key": api_key},
            model_id=f"openrouter/{model_id}",
            params={"max_tokens": 4096},
        )

    # default: Bedrock
    model_id = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-pro-v1:0")
    print(f"Using Bedrock — model: {model_id}")
    return BedrockModel(
        model_id=model_id,
        max_tokens=4096,
    )


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
    # docs_client = MCPClient(
    #     transport_callable=lambda: stdio_client(
    #         StdioServerParameters(
    #             command="uvx",
    #             args=["awslabs.aws-documentation-mcp-server@latest"],
    #             env={
    #                 "FASTMCP_LOG_LEVEL": "ERROR",
    #                 "AWS_DOCUMENTATION_PARTITION": "aws",
    #             },
    #         )
    #     ),
    #     prefix="awsdocs",
    #     continue_on_error=True,
    # )
    # stack.enter_context(docs_client)
    # mcp_tools.extend(docs_client.list_tools_sync())
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


def build_agent(mcp_tools: list) -> Agent:
    return Agent(
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[shell, read, http_request] + mcp_tools,
    )


def main() -> None:
    with ExitStack() as stack:
        mcp_tools = build_mcp_tools(stack)
        agent = build_agent(mcp_tools)

        if mcp_tools:
            tool_names = [t.tool_name for t in mcp_tools]
            print(f"MCP tools loaded: {', '.join(tool_names)}")

        print("DevOps Assistant ready. Type 'exit' or 'quit' to stop.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                print("Bye.")
                break

            agent(user_input)
            print()


if __name__ == "__main__":
    main()
