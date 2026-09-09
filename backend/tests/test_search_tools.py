"""Output contracts for the two tools in search_tools.py.

These assert the exact text handed back to Claude and the exact citation dicts
handed to the frontend, since both are consumed by things that cannot be
type-checked: an LLM and a JS template.
"""

import pytest

COURSE = "Building Toward Computer Use with Anthropic"
MCP = "MCP: Build Rich-Context AI Apps"


# --------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------


def test_search_tool_definition_shape(search_tool):
    definition = search_tool.get_tool_definition()
    assert definition["name"] == "search_course_content"
    assert definition["input_schema"]["required"] == ["query"]
    assert set(definition["input_schema"]["properties"]) == {
        "query",
        "course_name",
        "lesson_number",
    }


def test_outline_tool_definition_shape(outline_tool):
    definition = outline_tool.get_tool_definition()
    assert definition["name"] == "get_course_outline"
    assert definition["input_schema"]["required"] == ["course_title"]
    assert set(definition["input_schema"]["properties"]) == {"course_title"}


# --------------------------------------------------------------------------
# CourseSearchTool.execute
# --------------------------------------------------------------------------


def test_execute_forwards_all_three_filters_to_store(search_tool, fake_store):
    fake_store.queue_empty()
    search_tool.execute(query="tool use", course_name="Computer Use", lesson_number=1)
    assert fake_store.search_calls == [
        {
            "query": "tool use",
            "course_name": "Computer Use",
            "lesson_number": 1,
            "limit": None,
        }
    ]


def test_results_formatted_with_course_and_lesson_header(search_tool, fake_store):
    fake_store.queue_hits(("chunk body text", {"course_title": COURSE, "lesson_number": 1}))
    result = search_tool.execute(query="q")
    assert result == f"[{COURSE} - Lesson 1]\nchunk body text"


def test_chunk_without_lesson_number_omits_lesson_from_header(search_tool, fake_store):
    fake_store.queue_hits(("orphan text", {"course_title": "Untitled Notes", "lesson_number": None}))
    result = search_tool.execute(query="q")
    assert result == "[Untitled Notes]\norphan text"
    assert "Lesson" not in result


def test_multiple_chunks_joined_by_blank_line(search_tool, fake_store):
    fake_store.queue_hits(
        ("first", {"course_title": COURSE, "lesson_number": 0}),
        ("second", {"course_title": COURSE, "lesson_number": 1}),
    )
    result = search_tool.execute(query="q")
    assert result == f"[{COURSE} - Lesson 0]\nfirst\n\n[{COURSE} - Lesson 1]\nsecond"


def test_store_error_is_returned_verbatim_as_text(search_tool, fake_store):
    """CLAUDE.md: search failures are tool text, never exceptions."""
    fake_store.queue_error("No course found matching 'nope'")
    assert search_tool.execute(query="q", course_name="nope") == (
        "No course found matching 'nope'"
    )


def test_empty_results_message_names_the_course_filter(search_tool, fake_store):
    fake_store.queue_empty()
    result = search_tool.execute(query="q", course_name="MCP")
    assert result == "No relevant content found in course 'MCP'."


def test_empty_results_message_includes_lesson_two(search_tool, fake_store):
    fake_store.queue_empty()
    result = search_tool.execute(query="q", course_name="MCP", lesson_number=2)
    assert "in lesson 2" in result


def test_empty_results_message_includes_lesson_zero(search_tool, fake_store):
    """Lesson 0 is the first lesson of every course in this corpus.

    Paired with the lesson-2 test above: if that one passes and this one fails,
    the cause is falsiness, not a missing feature.
    """
    fake_store.queue_empty()
    result = search_tool.execute(query="q", course_name="MCP", lesson_number=0)
    assert "in lesson 0" in result


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------


def test_last_sources_deduped_per_lesson_in_first_seen_order(search_tool, fake_store):
    fake_store.register_course(
        COURSE,
        course_link="https://example.test/cu",
        lessons=[(0, "Introduction", "https://example.test/cu/l0"),
                 (1, "Overview", "https://example.test/cu/l1")],
    )
    fake_store.queue_hits(
        ("a", {"course_title": COURSE, "lesson_number": 1}),
        ("b", {"course_title": COURSE, "lesson_number": 0}),
        ("c", {"course_title": COURSE, "lesson_number": 1}),
    )
    search_tool.execute(query="q")
    assert search_tool.last_sources == [
        {"text": f"{COURSE} - Lesson 1", "link": "https://example.test/cu/l1"},
        {"text": f"{COURSE} - Lesson 0", "link": "https://example.test/cu/l0"},
    ]


def test_last_sources_fall_back_to_course_link_without_lesson(search_tool, fake_store):
    fake_store.register_course("Untitled Notes", course_link="https://example.test/notes")
    fake_store.queue_hits(("orphan", {"course_title": "Untitled Notes", "lesson_number": None}))
    search_tool.execute(query="q")
    assert search_tool.last_sources == [
        {"text": "Untitled Notes", "link": "https://example.test/notes"}
    ]


def test_last_sources_tolerate_a_missing_link(search_tool, fake_store):
    """The frontend renders link=None as plain text, so None must survive."""
    fake_store.register_course(MCP, course_link=None, lessons=[(2, "Creating a server", None)])
    fake_store.queue_hits(("x", {"course_title": MCP, "lesson_number": 2}))
    search_tool.execute(query="q")
    assert search_tool.last_sources == [{"text": f"{MCP} - Lesson 2", "link": None}]


def test_two_searches_accumulate_citations(search_tool, fake_store):
    """Claude may call one tool twice in a single round; both answers are cited.

    ToolManager.get_last_sources' own docstring promises not to drop any tool's
    citations, and SYSTEM_PROMPT invites several calls per round.
    """
    fake_store.register_course(COURSE, course_link="https://example.test/cu",
                               lessons=[(0, "Introduction", "https://example.test/cu/l0")])
    fake_store.register_course(MCP, course_link="https://example.test/mcp",
                               lessons=[(0, "Why MCP", "https://example.test/mcp/l0")])
    fake_store.queue_hits(("a", {"course_title": COURSE, "lesson_number": 0}))
    fake_store.queue_hits(("b", {"course_title": MCP, "lesson_number": 0}))

    search_tool.execute(query="first", course_name=COURSE)
    search_tool.execute(query="second", course_name=MCP)

    texts = [source["text"] for source in search_tool.last_sources]
    assert texts == [f"{COURSE} - Lesson 0", f"{MCP} - Lesson 0"]


def test_error_path_adds_no_citation_but_keeps_earlier_ones(search_tool, fake_store):
    """A hit then an error in the same round: cite the hit, invent nothing.

    Citations accumulate across calls within one round; ToolManager.reset_sources
    clears them between rounds.
    """
    fake_store.register_course(COURSE, course_link="https://example.test/cu",
                               lessons=[(0, "Introduction", "https://example.test/cu/l0")])
    fake_store.queue_hits(("a", {"course_title": COURSE, "lesson_number": 0}))
    fake_store.queue_error("Search error: boom")

    search_tool.execute(query="first")
    search_tool.execute(query="second")

    assert search_tool.last_sources == [
        {"text": f"{COURSE} - Lesson 0", "link": "https://example.test/cu/l0"}
    ]


# --------------------------------------------------------------------------
# CourseOutlineTool.execute
# --------------------------------------------------------------------------


def test_outline_lists_every_lesson_including_lesson_zero(outline_tool, fake_store):
    fake_store.register_course(
        MCP,
        course_link="https://example.test/mcp",
        instructor="Elie Schoppik",
        lessons=[(0, "Why MCP", "https://example.test/mcp/l0"),
                 (2, "Creating a server", None)],
    )
    result = outline_tool.execute(course_title="MCP")
    assert result == (
        f"Course: {MCP}\n"
        "Course link: https://example.test/mcp\n"
        "Instructor: Elie Schoppik\n"
        "Lessons (2):\n"
        "Lesson 0: Why MCP\n"
        "Lesson 2: Creating a server"
    )


def test_outline_omits_instructor_line_when_absent(outline_tool, fake_store):
    fake_store.register_course("Untitled Notes", course_link=None, instructor=None,
                               lessons=[(0, "Only lesson", None)])
    result = outline_tool.execute(course_title="Untitled Notes")
    assert "Instructor:" not in result
    assert "Course link: not available" in result


def test_outline_cites_the_course_page(outline_tool, fake_store):
    fake_store.register_course(MCP, course_link="https://example.test/mcp",
                               lessons=[(0, "Why MCP", None)])
    outline_tool.execute(course_title="MCP")
    assert outline_tool.last_sources == [
        {"text": MCP, "link": "https://example.test/mcp"}
    ]


def test_outline_miss_returns_text_and_sets_no_source(outline_tool, fake_store):
    result = outline_tool.execute(course_title="Underwater Basket Weaving")
    assert result == "No course found matching 'Underwater Basket Weaving'."
    assert outline_tool.last_sources == []


def test_outline_of_course_without_lessons(outline_tool, fake_store):
    fake_store.register_course("Untitled Notes", course_link=None, lessons=[])
    result = outline_tool.execute(course_title="Untitled Notes")
    assert result == "Course: Untitled Notes\nNo lessons are recorded for this course."


def test_outline_miss_after_a_hit_keeps_the_hit_citation(outline_tool, fake_store):
    """A miss adds no citation and does not erase the successful lookup's."""
    fake_store.register_course(MCP, course_link="https://example.test/mcp",
                               lessons=[(0, "Why MCP", None)])
    outline_tool.execute(course_title="MCP")
    outline_tool.execute(course_title="Underwater Basket Weaving")
    assert outline_tool.last_sources == [
        {"text": MCP, "link": "https://example.test/mcp"}
    ]
