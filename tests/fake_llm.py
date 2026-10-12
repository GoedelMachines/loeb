"""A scripted LLM provider for driving Agent.run in tests without an API."""

from __future__ import annotations

from loeb.llm.base import CompletionResult, LLMProvider, ToolCall


class ScriptedProvider(LLMProvider):
    """Replays a list of turns. Each turn is a list of (tool_name, input) or "end"."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = 0
        self.tool_results: list[list[str]] = []

    async def complete(self, system, messages, tools, max_tokens, on_event=None):
        self.calls += 1
        turn = self.turns.pop(0) if self.turns else "end"
        if turn == "end":
            return CompletionResult("end_turn", [], "done", 1, 1)
        calls = [ToolCall(id=f"t{self.calls}_{i}", name=n, input=inp)
                 for i, (n, inp) in enumerate(turn)]
        return CompletionResult("tool_use", calls, "calling tools", 1, 1)

    def make_assistant_message(self, raw_content):
        return {"role": "assistant", "content": str(raw_content)}

    def make_tool_result_message(self, tool_calls, results):
        self.tool_results.append(list(results))
        return [{"role": "user", "content": r} for r in results]
