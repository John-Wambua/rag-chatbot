"""ToolManager dispatch and the citation lifecycle it owns."""

import pytest

COURSE = "Building Toward Computer Use with Anthropic"
MCP = "MCP: Build Rich-Context AI Apps"


def test_definitions_returned_in_registration_order(tool_manager):
    names = [definition["name"] for definition in tool_manager.get_tool_definitions()]
    assert names == ["search_course_content", "get_course_outline"]


def test_registering_a_tool_without_a_name_raises():
    from search_tools import Tool, ToolManager

    class Nameless(Tool):
        def get_tool_definition(self):
            return {"description": "no name"}

        def execute(self, **kwargs):
            return ""

    with pytest.raises(ValueError):
        ToolManager().register_tool(Nameless())


def test_unknown_tool_name_returns_text(tool_manager):
    assert tool_manager.execute_tool("nope", query="x") == "Tool 'nope' not found"


def test_unexpected_argument_name_returns_text(tool_manager):
    """Claude authors the tool input; a hallucinated key must not 500.

    CLAUDE.md: "Search failures are text, not exceptions." That invariant has to
    hold in the dispatcher too, not only inside each tool.
    """
    result = tool_manager.execute_tool("search_course_content", topic="pelicans")
    assert isinstance(result, str)
    assert "topic" in result


def test_missing_required_argument_returns_text(tool_manager):
    result = tool_manager.execute_tool("get_course_outline")
    assert isinstance(result, str)
    assert result  # some explanatory text, not an empty string


def test_tool_internal_exception_returns_text():
    from search_tools import Tool, ToolManager

    class Exploding(Tool):
        def get_tool_definition(self):
            return {"name": "exploding", "input_schema": {}}

        def execute(self, **kwargs):
            raise RuntimeError("chroma segfaulted")

    manager = ToolManager()
    manager.register_tool(Exploding())
    result = manager.execute_tool("exploding")
    assert isinstance(result, str)
    assert "chroma segfaulted" in result


def test_get_last_sources_merges_search_and_outline_tools(tool_manager, fake_store):
    fake_store.register_course(
        COURSE,
        course_link="https://example.test/cu",
        lessons=[(0, "Introduction", "https://example.test/cu/l0")],
    )
    fake_store.register_course(
        MCP, course_link="https://example.test/mcp", lessons=[(0, "Why MCP", None)]
    )
    fake_store.queue_hits(("a", {"course_title": COURSE, "lesson_number": 0}))

    tool_manager.execute_tool("search_course_content", query="q")
    tool_manager.execute_tool("get_course_outline", course_title="MCP")

    texts = [source["text"] for source in tool_manager.get_last_sources()]
    assert texts == [f"{COURSE} - Lesson 0", MCP]


def test_reset_sources_clears_every_tool(tool_manager, fake_store):
    fake_store.register_course(
        MCP, course_link="https://example.test/mcp", lessons=[(0, "Why MCP", None)]
    )
    tool_manager.execute_tool("get_course_outline", course_title="MCP")
    assert tool_manager.get_last_sources()

    tool_manager.reset_sources()
    assert tool_manager.get_last_sources() == []
