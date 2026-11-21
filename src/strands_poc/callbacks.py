from typing import Any


# ANSI colour helpers — work on any terminal without extra dependencies
_RESET = "\033[0m"
_DIM = "\033[2m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_BOLD = "\033[1m"


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

    _OPEN = "<thinking>"
    _CLOSE = "</thinking>"
    # longest tag is </thinking> = 11 chars; hold back that many - 1 at the tail
    _GUARD = max(len(_OPEN), len(_CLOSE)) - 1

    def __init__(self) -> None:
        self._reset_state()

    def _reset_state(self) -> None:
        self._buf: str = ""
        self._in_tag_thinking = False
        self._thinking_printed = False
        self._answer_printed = False
        self._tool_count = 0

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

    def __call__(self, **kwargs: Any) -> None:
        reasoning: str | None = kwargs.get("reasoningText")
        if reasoning:
            self._emit_thinking(reasoning)
            return

        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if tool_use:
            self._tool_count += 1
            print(
                f"\n{_c(_BOLD, _CYAN)}⚙  Tool #{self._tool_count}: {tool_use['name']}{_RESET}",
                flush=True,
            )
            return

        data: str = kwargs.get("data", "")
        complete: bool = kwargs.get("complete", False)

        if data:
            self._buf += data
            self._drain(final=False)

        if complete:
            self._drain(final=True)
            if self._thinking_printed or self._answer_printed:
                print(flush=True)

    def reset(self) -> None:
        """Call before each new user turn."""
        self._reset_state()
