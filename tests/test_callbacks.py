import re

import pytest

from strands_poc.callbacks import DevOpsCallbackHandler


def _plain_text(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_handler_routes_split_thinking_and_answer_tags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handler = DevOpsCallbackHandler()

    handler(data="<thi", complete=False)
    handler(data="nking>reason</thi", complete=False)
    handler(data="nking>answer", complete=True)

    output = _plain_text(capsys.readouterr().out)

    assert "🤔 Thinking" in output
    assert "reason" in output
    assert "✅ Answer" in output
    assert "answer" in output


def test_handler_processes_native_reasoning(capsys: pytest.CaptureFixture[str]) -> None:
    handler = DevOpsCallbackHandler()

    handler(reasoningText="Inspecting the system")

    output = capsys.readouterr().out

    assert "🤔 Thinking" in output
    assert "Inspecting the system" in output


def test_handler_formats_tool_calls(capsys: pytest.CaptureFixture[str]) -> None:
    handler = DevOpsCallbackHandler()

    handler(event={"contentBlockStart": {"start": {"toolUse": {"name": "shell"}}}})

    output = capsys.readouterr().out

    assert "Tool #1: shell" in output
