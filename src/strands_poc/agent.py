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
import sys
from contextlib import ExitStack
from typing import Any

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

# ANSI colour helpers — work on any terminal without extra dependencies
_RESET  = "\033[0m"
_DIM    = "\033[2m"
_YELLOW = "\033[33m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_BOLD   = "\033[1m"


def _c(*codes: str) -> str:
    """Combine ANSI codes."""
    return "".join(codes)


class DevOpsCallbackHandler:
    """
    Formats agent output into three visually distinct sections:

      🤔 Thinking   — dimmed yellow; model reasoning before it acts
      ⚙  Tool call  — cyan;          which tool is being invoked
      ✅ Answer      — bold green header, plain text body

    Handles three reasoning sources:
      1. Native `reasoningText` kwarg  — Claude extended thinking / DeepSeek-R1 on OpenRouter
      2. `<thinking>…</thinking>` tags — Nova Pro streams these token-by-token inside `data`
      3. No reasoning                   — model goes straight to answer (most free models)

    For case 2 the handler accumulates a small lookahead buffer so that tags
    split across chunk boundaries (e.g. "<think" … "ing>") are detected reliably.
    """

    _OPEN  = "<thinking>"
    _CLOSE = "</thinking>"
    # longest tag is </thinking> = 11 chars; hold back that many - 1 at the tail
    _GUARD = max(len(_OPEN), len(_CLOSE)) - 1

    def __init__(self) -> None:
        self._reset_state()

    def _reset_state(self) -> None:
        self._buf: str = ""          # lookahead buffer for tag detection
        self._in_tag_thinking = False  # currently inside <thinking>…</thinking>
        self._thinking_printed = False # header already printed this turn
        self._answer_printed   = False # header already printed this turn
        self._tool_count       = 0

    # ------------------------------------------------------------------
    # Printing helpers
    # ------------------------------------------------------------------

    def _print_thinking_header(self) -> None:
        if not self._thinking_printed:
            print(f"\n{_c(_BOLD, _YELLOW)}🤔 Thinking{_RESET}", flush=True)
            self._thinking_printed = True

    def _print_answer_header(self) -> None:
        if not self._answer_printed:
            print(f"\n{_c(_BOLD, _GREEN)}✅ Answer{_RESET}", flush=True)
            self._answer_printed = True

    def _emit_thinking(self, text: str) -> None:
        if not text:
            return
        self._print_thinking_header()
        print(_c(_DIM, _YELLOW) + text + _RESET, end="", flush=True)

    def _emit_answer(self, text: str) -> None:
        if not text:
            return
        self._print_answer_header()
        print(text, end="", flush=True)

    # ------------------------------------------------------------------
    # Tag-aware buffer drain
    # ------------------------------------------------------------------

    def _drain(self, final: bool = False) -> None:
        """
        Parse self._buf routing content between <thinking>…</thinking> to
        _emit_thinking and everything else to _emit_answer.

        When final=True the entire buffer is flushed regardless of partial tags.
        """
        buf = self._buf

        while buf:
            if self._in_tag_thinking:
                close = buf.find(self._CLOSE)
                if close == -1:
                    # Close tag not yet complete — keep last _GUARD chars unless final
                    if final:
                        self._emit_thinking(buf)
                        buf = ""
                    else:
                        safe = max(0, len(buf) - self._GUARD)
                        self._emit_thinking(buf[:safe])
                        buf = buf[safe:]
                    break
                else:
                    self._emit_thinking(buf[:close])
                    self._in_tag_thinking = False
                    buf = buf[close + len(self._CLOSE):]

            else:
                open_ = buf.find(self._OPEN)
                if open_ == -1:
                    # No open tag — keep last _GUARD chars unless final
                    if final:
                        self._emit_answer(buf)
                        buf = ""
                    else:
                        safe = max(0, len(buf) - self._GUARD)
                        self._emit_answer(buf[:safe])
                        buf = buf[safe:]
                    break
                else:
                    self._emit_answer(buf[:open_])
                    self._in_tag_thinking = True
                    buf = buf[open_ + len(self._OPEN):]

        self._buf = buf

    # ------------------------------------------------------------------
    # Strands callback entry point
    # ------------------------------------------------------------------

    def __call__(self, **kwargs: Any) -> None:
        # 1. Native reasoning event (Claude extended thinking / DeepSeek-R1)
        reasoning: str | None = kwargs.get("reasoningText")
        if reasoning:
            self._emit_thinking(reasoning)
            return

        # 2. Tool call starting
        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if tool_use:
            self._tool_count += 1
            print(
                f"\n{_c(_BOLD, _CYAN)}⚙  Tool #{self._tool_count}: {tool_use['name']}{_RESET}",
                flush=True,
            )
            return

        # 3. Streamed data token (may contain <thinking> tags — Nova Pro pattern)
        data: str = kwargs.get("data", "")
        complete: bool = kwargs.get("complete", False)

        if data:
            self._buf += data
            self._drain(final=False)

        if complete:
            self._drain(final=True)
            # Ensure cursor lands on a fresh line
            if self._thinking_printed or self._answer_printed:
                print(flush=True)

    def reset(self) -> None:
        """Call before each new user turn."""
        self._reset_state()


def build_model():
    provider = os.environ.get("MODEL_PROVIDER", "bedrock").lower()

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY env var is required when MODEL_PROVIDER=openrouter")
        model_id = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
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
    docs_client = MCPClient(
        transport_callable=lambda: stdio_client(
            StdioServerParameters(
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

            handler.reset()
            agent(user_input)
            print()


if __name__ == "__main__":
    main()
