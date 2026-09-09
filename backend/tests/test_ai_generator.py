"""Does ai_generator.py call the Anthropic API and the tools correctly?

Everything is asserted off the recorded kwargs of each messages.create call, so
the shape of the request is under test, not just the returned string.
"""

import pytest

from conftest import FakeMessage, TextBlock, ThinkingBlock, ToolUseBlock

TOOL_DEFS = [
    {"name": "search_course_content", "input_schema": {"type": "object"}},
    {"name": "get_course_outline", "input_schema": {"type": "object"}},
]


class RecordingToolManager:
    """Minimal tool_manager: records dispatches, returns canned text."""

    def __init__(self, *results):
        self.calls = []
        self._results = list(results) or ["tool output"]

    def execute_tool(self, name, **kwargs):
        self.calls.append({"name": name, "kwargs": kwargs})
        return self._results.pop(0) if len(self._results) > 1 else self._results[0]


# --------------------------------------------------------------------------
# Request shape
# --------------------------------------------------------------------------


def test_first_call_sends_tools_with_auto_choice(make_generator):
    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("q", tools=TOOL_DEFS, tool_manager=RecordingToolManager())
    assert client.messages.calls[0]["tools"] == TOOL_DEFS
    assert client.messages.calls[0]["tool_choice"] == {"type": "auto"}


def test_tools_key_absent_when_no_tools_passed(make_generator):
    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("q")
    assert "tools" not in client.messages.calls[0]
    assert "tool_choice" not in client.messages.calls[0]


def test_base_params_model_temperature_and_max_tokens(make_generator):
    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("q")
    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-4-20250514"
    assert call["temperature"] == 0
    assert call["max_tokens"] == 800


def test_query_is_the_single_user_message(make_generator):
    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("what is MCP?")
    assert client.messages.calls[0]["messages"] == [
        {"role": "user", "content": "what is MCP?"}
    ]


def test_system_prompt_used_verbatim_without_history(make_generator):
    from ai_generator import AIGenerator

    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("q")
    assert client.messages.calls[0]["system"] == AIGenerator.SYSTEM_PROMPT


def test_history_is_appended_to_system_prompt(make_generator):
    from ai_generator import AIGenerator

    gen, client = make_generator(FakeMessage([TextBlock("hi")]))
    gen.generate_response("q", conversation_history="User: hi\nAssistant: hello")
    system = client.messages.calls[0]["system"]
    assert system.startswith(AIGenerator.SYSTEM_PROMPT)
    assert "Previous conversation:\nUser: hi\nAssistant: hello" in system
    # history rides in the system prompt, not as extra turns
    assert len(client.messages.calls[0]["messages"]) == 1


# --------------------------------------------------------------------------
# No-tool path
# --------------------------------------------------------------------------


def test_end_turn_returns_text_and_makes_one_call(make_generator):
    manager = RecordingToolManager()
    gen, client = make_generator(FakeMessage([TextBlock("Paris.")]))
    answer = gen.generate_response("q", tools=TOOL_DEFS, tool_manager=manager)
    assert answer == "Paris."
    assert len(client.messages.calls) == 1
    assert manager.calls == []


# --------------------------------------------------------------------------
# Tool dispatch
# --------------------------------------------------------------------------


def test_tool_use_executes_tool_and_returns_final_text(make_generator):
    manager = RecordingToolManager("search results here")
    gen, client = make_generator(
        FakeMessage(
            [ToolUseBlock("search_course_content", {"query": "mcp", "lesson_number": 0})],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("MCP is a protocol.")]),
    )
    answer = gen.generate_response("q", tools=TOOL_DEFS, tool_manager=manager)
    assert answer == "MCP is a protocol."
    assert manager.calls == [
        {
            "name": "search_course_content",
            "kwargs": {"query": "mcp", "lesson_number": 0},
        }
    ]


def test_second_call_omits_tools_and_reuses_system(make_generator):
    """One round of tool use is intentional: round 2 must not carry tools."""
    gen, client = make_generator(
        FakeMessage([ToolUseBlock("search_course_content", {"query": "x"})],
                    stop_reason="tool_use"),
        FakeMessage([TextBlock("done")]),
    )
    gen.generate_response("q", tools=TOOL_DEFS, tool_manager=RecordingToolManager())
    assert "tools" not in client.messages.calls[1]
    assert "tool_choice" not in client.messages.calls[1]
    assert client.messages.calls[1]["system"] == client.messages.calls[0]["system"]


def test_second_call_message_sequence_and_tool_use_id_echo(make_generator):
    block = ToolUseBlock("search_course_content", {"query": "x"}, id="toolu_99")
    manager = RecordingToolManager("the tool text")
    gen, client = make_generator(
        FakeMessage([block], stop_reason="tool_use"),
        FakeMessage([TextBlock("done")]),
    )
    gen.generate_response("q", tools=TOOL_DEFS, tool_manager=manager)

    messages = client.messages.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"] == [block]
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_99", "content": "the tool text"}
    ]


def test_all_tool_use_blocks_in_one_round_are_executed(make_generator):
    """SYSTEM_PROMPT invites calling both tools in the single round."""
    manager = RecordingToolManager("outline text", "search text")
    gen, client = make_generator(
        FakeMessage(
            [
                ToolUseBlock("get_course_outline", {"course_title": "MCP"}, id="toolu_01"),
                ToolUseBlock("search_course_content", {"query": "x"}, id="toolu_02"),
            ],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("combined")]),
    )
    gen.generate_response("q", tools=TOOL_DEFS, tool_manager=manager)

    assert [c["name"] for c in manager.calls] == [
        "get_course_outline",
        "search_course_content",
    ]
    results = client.messages.calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_01", "toolu_02"]


# --------------------------------------------------------------------------
# Response-block handling
# --------------------------------------------------------------------------


def test_thinking_block_before_text_on_first_call(make_generator):
    """content[0] is not guaranteed to be the text block."""
    gen, _ = make_generator(
        FakeMessage([ThinkingBlock(), TextBlock("the real answer")])
    )
    assert gen.generate_response("q") == "the real answer"


def test_thinking_block_before_text_on_final_call(make_generator):
    gen, _ = make_generator(
        FakeMessage([ToolUseBlock("search_course_content", {"query": "x"})],
                    stop_reason="tool_use"),
        FakeMessage([ThinkingBlock(), TextBlock("final answer")]),
    )
    answer = gen.generate_response("q", tools=TOOL_DEFS, tool_manager=RecordingToolManager())
    assert answer == "final answer"


def test_tool_use_without_tool_manager_does_not_crash(make_generator):
    """Passing tools without a manager is a caller error, not an AttributeError."""
    gen, _ = make_generator(
        FakeMessage([ToolUseBlock("search_course_content", {"query": "x"})],
                    stop_reason="tool_use")
    )
    result = gen.generate_response("q", tools=TOOL_DEFS, tool_manager=None)
    assert isinstance(result, str)


def test_tool_use_stop_reason_with_no_tool_use_blocks_makes_one_call(make_generator):
    """No tool_use block means nothing to send back; a second call would 400.

    The real API rejects a request whose last message is from the assistant.
    """
    gen, client = make_generator(FakeMessage([TextBlock("hmm")], stop_reason="tool_use"))
    answer = gen.generate_response("q", tools=TOOL_DEFS, tool_manager=RecordingToolManager())
    assert len(client.messages.calls) == 1
    assert answer == "hmm"


def test_max_tokens_stop_reason_is_surfaced(make_generator):
    """A truncated answer must be distinguishable from a complete one."""
    gen, _ = make_generator(
        FakeMessage([TextBlock("The lessons are: 1. Intro 2. Over")],
                    stop_reason="max_tokens")
    )
    answer = gen.generate_response("q")
    assert answer != "The lessons are: 1. Intro 2. Over", (
        "truncation is silently indistinguishable from a complete answer"
    )


def test_response_with_no_text_block_returns_a_string(make_generator):
    """A refusal stop_reason can yield content with no text block at all."""
    gen, _ = make_generator(FakeMessage([], stop_reason="refusal"))
    assert isinstance(gen.generate_response("q"), str)


def test_api_exception_propagates_to_caller(make_generator):
    """API transport errors are not swallowed here; app.py turns them into 500s."""
    gen, _ = make_generator(RuntimeError("overloaded"))
    with pytest.raises(RuntimeError, match="overloaded"):
        gen.generate_response("q")
