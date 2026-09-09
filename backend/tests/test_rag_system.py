"""How RAGSystem handles content queries end to end.

The vector store and the Anthropic client are faked; ToolManager, both tools,
AIGenerator and SessionManager are the real objects, so tool registration order
and the citation lifecycle are genuinely under test.
"""

import pytest
from conftest import FakeMessage, TextBlock, ToolUseBlock, script

COURSE = "Building Toward Computer Use with Anthropic"
MCP = "MCP: Build Rich-Context AI Apps"


def _seed(store):
    store.register_course(
        COURSE,
        course_link="https://example.test/cu",
        instructor="Colt Steele",
        lessons=[(0, "Introduction", "https://example.test/cu/l0")],
    )
    store.register_course(
        MCP,
        course_link="https://example.test/mcp",
        instructor="Elie Schoppik",
        lessons=[(0, "Why MCP", "https://example.test/mcp/l0")],
    )


def test_both_tools_are_registered(rag):
    system, _, _ = rag
    names = [d["name"] for d in system.tool_manager.get_tool_definitions()]
    assert names == ["search_course_content", "get_course_outline"]


def test_query_wraps_question_and_offers_both_tools(rag):
    system, _, client = rag
    script(client, FakeMessage([TextBlock("Paris.")]))
    system.query("what is the capital of France?")

    call = client.messages.calls[0]
    assert call["messages"][0]["content"] == (
        "Answer this question about course materials: what is the capital of France?"
    )
    assert [t["name"] for t in call["tools"]] == [
        "search_course_content",
        "get_course_outline",
    ]


def test_content_query_returns_answer_and_search_citations(rag):
    system, store, client = rag
    _seed(store)
    store.queue_hits(
        ("chunk about tool use", {"course_title": COURSE, "lesson_number": 0})
    )
    script(
        client,
        FakeMessage(
            [ToolUseBlock("search_course_content", {"query": "tool use"})],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("Tool use lets Claude call functions.")]),
    )

    answer, sources = system.query("how does tool use work?")

    assert answer == "Tool use lets Claude call functions."
    assert sources == [
        {"text": f"{COURSE} - Lesson 0", "link": "https://example.test/cu/l0"}
    ]
    assert store.search_calls[0]["query"] == "tool use"


def test_general_knowledge_query_never_searches(rag):
    system, store, client = rag
    script(client, FakeMessage([TextBlock("Paris.")]))

    answer, sources = system.query("capital of France?")

    assert answer == "Paris."
    assert sources == []
    assert store.search_calls == []


def test_outline_query_returns_course_level_citation(rag):
    system, store, client = rag
    _seed(store)
    script(
        client,
        FakeMessage(
            [ToolUseBlock("get_course_outline", {"course_title": "MCP"})],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("The MCP course has 1 lesson.")]),
    )

    _, sources = system.query("what lessons are in the MCP course?")

    assert sources == [{"text": MCP, "link": "https://example.test/mcp"}]


def test_sources_are_reset_between_successive_queries(rag):
    system, store, client = rag
    _seed(store)
    store.queue_hits(("a", {"course_title": COURSE, "lesson_number": 0}))
    script(
        client,
        FakeMessage(
            [ToolUseBlock("search_course_content", {"query": "x"})],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("first")]),
        FakeMessage([TextBlock("second")]),
    )

    _, first_sources = system.query("q1")
    _, second_sources = system.query("q2")

    assert first_sources  # q1 searched
    assert second_sources == []  # q2 did not


def test_stale_sources_do_not_leak_after_a_failed_query(rag):
    """If the API fails after a tool ran, the next answer must not inherit its citations."""
    system, store, client = rag
    _seed(store)
    store.queue_hits(("secret chunk", {"course_title": COURSE, "lesson_number": 0}))
    script(
        client,
        FakeMessage(
            [ToolUseBlock("search_course_content", {"query": "secrets"})],
            stop_reason="tool_use",
        ),
        RuntimeError("overloaded"),
        FakeMessage([TextBlock("Paris is the capital.")]),
    )

    with pytest.raises(RuntimeError):
        system.query("q1")

    answer, sources = system.query("q2 about France")
    assert answer == "Paris is the capital."
    assert sources == []


def test_two_searches_in_one_round_yield_both_citations(rag):
    """A comparison question makes Claude search twice; cite both courses."""
    system, store, client = rag
    _seed(store)
    store.queue_hits(("a", {"course_title": COURSE, "lesson_number": 0}))
    store.queue_hits(("b", {"course_title": MCP, "lesson_number": 0}))
    script(
        client,
        FakeMessage(
            [
                ToolUseBlock(
                    "search_course_content",
                    {"query": "a", "course_name": COURSE},
                    id="toolu_01",
                ),
                ToolUseBlock(
                    "search_course_content",
                    {"query": "b", "course_name": MCP},
                    id="toolu_02",
                ),
            ],
            stop_reason="tool_use",
        ),
        FakeMessage([TextBlock("Both courses cover it.")]),
    )

    _, sources = system.query("compare the two courses")

    texts = [s["text"] for s in sources]
    assert texts == [f"{COURSE} - Lesson 0", f"{MCP} - Lesson 0"]


def test_history_absent_on_first_turn_and_present_on_second(rag):
    system, _, client = rag
    script(
        client,
        FakeMessage([TextBlock("first answer")]),
        FakeMessage([TextBlock("second answer")]),
    )
    session_id = system.session_manager.create_session()

    system.query("q1", session_id=session_id)
    assert "Previous conversation:" not in client.messages.calls[0]["system"]

    system.query("q2", session_id=session_id)
    system_prompt = client.messages.calls[1]["system"]
    assert "Previous conversation:" in system_prompt
    assert "User: q1" in system_prompt
    assert "Assistant: first answer" in system_prompt


def test_exchange_recorded_only_when_session_id_given(rag):
    system, _, client = rag
    script(
        client,
        FakeMessage([TextBlock("a")]),
        FakeMessage([TextBlock("b")]),
    )

    system.query("no session")
    assert system.session_manager.sessions == {}

    session_id = system.session_manager.create_session()
    system.query("with session", session_id=session_id)
    contents = [m.content for m in system.session_manager.sessions[session_id]]
    # the raw question is stored, not the wrapped prompt sent to the model
    assert contents == ["with session", "b"]


def test_history_window_holds_max_history_exchanges(rag):
    """MAX_HISTORY = 2, so 4 messages, starting with a user turn."""
    system, _, client = rag
    script(client, *[FakeMessage([TextBlock(f"a{i}")]) for i in range(3)])
    session_id = system.session_manager.create_session()

    for i in range(3):
        system.query(f"q{i}", session_id=session_id)

    messages = system.session_manager.sessions[session_id]
    assert len(messages) == 4
    assert messages[0].role == "user"
    assert messages[-1].role == "assistant"
    assert messages[0].content == "q1"  # q0's exchange has aged out


def test_get_course_analytics_shape(rag):
    system, store, _ = rag
    _seed(store)
    analytics = system.get_course_analytics()
    assert analytics["total_courses"] == 2
    assert set(analytics["course_titles"]) == {COURSE, MCP}
