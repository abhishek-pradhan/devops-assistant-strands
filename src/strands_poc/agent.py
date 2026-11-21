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
    export OPENROUTER_MODEL=particle-ai/particle-1:free   # any free OpenRouter model
    uv run devops-assistant
"""

from contextlib import ExitStack

from strands import Agent
from strands.vended_tools import http_request, read, shell

from strands_poc.callbacks import DevOpsCallbackHandler
from strands_poc.mcp_tools import build_mcp_tools
from strands_poc.models import build_model
from strands_poc.prompts import SYSTEM_PROMPT


def build_agent(mcp_tools: list, handler: DevOpsCallbackHandler) -> Agent:
    return Agent(
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[shell, read, http_request] + mcp_tools,
        callback_handler=handler,
    )


def main() -> None:
    handler = DevOpsCallbackHandler()

    with ExitStack() as stack:
        mcp_tools = build_mcp_tools(stack)
        agent = build_agent(mcp_tools, handler)

        if mcp_tools:
            tool_names = [tool.tool_name for tool in mcp_tools]
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

            handler.reset()
            agent(user_input)
            print()


if __name__ == "__main__":
    main()
