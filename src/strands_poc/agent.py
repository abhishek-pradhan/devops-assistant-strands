"""
DevOps Assistant — a Strands agent that inspects and operates your local system.

Capabilities:
  - Run shell commands (via the built-in shell tool)
  - Read log files and config files
  - Answer questions about processes, disk, memory, and network
  - Summarise recent log errors in plain English

Provider selection (set env vars before running):

  Bedrock (default):
    AWS credentials must be configured (aws configure / AWS_* env vars)
    uv run devops-assistant

  OpenRouter:
    export MODEL_PROVIDER=openrouter
    export OPENROUTER_API_KEY=sk-or-...
    export OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free   # any free OpenRouter model
    uv run devops-assistant
"""

import os

from strands import Agent
from strands.models import BedrockModel
from strands.models.litellm import LiteLLMModel
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


def build_agent() -> Agent:
    return Agent(
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[shell, read, http_request],
    )


def main() -> None:
    agent = build_agent()

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
