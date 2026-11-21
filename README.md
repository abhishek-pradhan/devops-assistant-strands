# DevOps Assistant

A conversational DevOps assistant built with the [Strands Agents SDK](https://strandsagents.com) and Amazon Bedrock. Ask it questions about your Linux system in plain English — it runs shell commands, reads log and config files, and hits HTTP endpoints to find answers.

## What it can do

- Check disk usage, memory, CPU load, and running processes
- Tail and summarise log files
- Inspect open ports and network connections
- Read config files and scripts from disk
- Hit internal health-check or metadata endpoints
- Follow up on previous answers — conversation history is kept across turns

It defaults to read-only operations and warns before anything with side-effects (restarts, writes, deletions).

## Project structure

```
strands-poc/
├── pyproject.toml               # project metadata and dependencies
├── uv.lock                      # locked dependency tree
├── README.md
└── src/strands_poc/
    └── agent.py                 # agent definition, model selection, REPL loop
```

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) 0.13+
- One of:
  - AWS credentials configured (`aws configure` or `AWS_*` env vars) for Bedrock
  - An [OpenRouter](https://openrouter.ai) API key for OpenRouter models

## Setup

```bash
git clone <repo>
cd strands-poc
uv sync
```

`uv sync` installs all dependencies into an isolated virtual environment. No manual `pip install` needed.

## Running

```bash
uv run devops-assistant
```

## Model providers

The agent supports two providers, selected via the `MODEL_PROVIDER` env var.

### Bedrock (default)

Uses Amazon Bedrock in `ap-south-1` with the APAC inference profile for Nova Pro. AWS credentials must be configured.

```bash
uv run devops-assistant
# or override the model:
BEDROCK_MODEL_ID=apac.anthropic.claude-3-7-sonnet-20250219-v1:0 
uv run devops-assistant
```

| Env var | Default | Description |
|---|---|---|
| `BEDROCK_MODEL_ID` | `apac.amazon.nova-pro-v1:0` | Any Bedrock inference profile ID available in your region |

### OpenRouter

Uses [LiteLLM](https://docs.litellm.ai) under the hood to route requests to OpenRouter. Set your API key and optionally pick a model.

```bash
export MODEL_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-xxxxxxx
export OPENROUTER_MODEL=mistralai/mistral-7b-instruct
uv run devops-assistant
```

| Env var | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required. Your OpenRouter API key |
| `OPENROUTER_MODEL` | `mistralai/mistral-7b-instruct` | Any model slug from [openrouter.ai/models](https://openrouter.ai/models) |

**Free models worth trying:**

| Model slug | Notes |
|---|---|
| `mistralai/mistral-7b-instruct` | Fast, good instruction following |
| `meta-llama/llama-3.1-8b-instruct` | Strong reasoning for its size |
| `google/gemma-3-4b-it` | Lightweight, quick responses |
| `deepseek/deepseek-r1-0528:free` | Strong reasoning, free tier |

Check [openrouter.ai/models?order=pricing-asc](https://openrouter.ai/models?order=pricing-asc) filtered to "Free" for the current list.

## Tools

| Tool | Source | Purpose |
|---|---|---|
| `shell` | `strands.vended_tools` | Run shell commands on the host |
| `read` | `strands.vended_tools` | Read files from disk |
| `http_request` | `strands.vended_tools` | Make HTTP requests to local or remote endpoints |

## Example prompts

```
How much disk space is left on each mount?
What processes are consuming the most memory?
Show me the last 50 lines of /var/log/syslog and summarise any errors.
Is anything listening on port 8080?
What's my kernel version and uptime?
```

## Dependencies

| Package | Purpose |
|---|---|
| `strands-agents` | Core agent SDK — model loop, tool dispatch, conversation history |
| `strands-agents-tools` | Community tool library |
| `strands-agents[litellm]` | LiteLLM provider for OpenRouter and other non-Bedrock models |
