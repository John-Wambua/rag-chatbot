"""Integration tier: real ChromaDB, stub embedder.

Verifies that the `where` filters `_build_filter` produces are valid ChromaDB
queries and that `config.MAX_RESULTS` really reaches `n_results` — neither of
which a pure-mock suite can catch. Embeddings here are hashed bag-of-words, so
these tests assert filtering and plumbing, never relevance quality.
"""

import pytest

from conftest import COMPUTER_USE, MCP, UNTITLED, StubEmbeddingFunction

pytestmark = pytest.mark.integration


def test_config_limits_are_sane():
    """MAX_RESULTS flows straight into n_results with no validation."""
    from config import config

    assert config.MAX_RESULTS > 0, "n_results=0 makes every content query return nothing"
    assert config.CHUNK_OVERLAP < config.CHUNK_SIZE


def test_stub_embedder_is_in_use(real_store):
    assert isinstance(real_store.embedding_function, StubEmbeddingFunction)


def test_unfiltered_search_is_capped_at_max_results(populated_store):
    results = populated_store.search("protocol server")
    assert results.error is None
    assert len(results.documents) == 5  # all 5 seeded chunks, max_results=5

    populated_store.max_results = 2
    assert len(populated_store.search("protocol server").documents) == 2


def test_explicit_limit_overrides_max_results(populated_store):
    results = populated_store.search("protocol server", limit=1)
    assert len(results.documents) == 1


def test_course_name_fragment_resolves_to_full_title(populated_store):
    results = populated_store.search("protocol", course_name="MCP")
    assert results.documents
    assert {meta["course_title"] for meta in results.metadata} == {MCP}


def test_lesson_zero_filter_returns_only_lesson_zero(populated_store):
    """Proves _build_filter handles lesson 0 correctly.

    Pairs with the failing message test in test_search_tools.py to localise that
    defect to the message formatting, not the filtering.
    """
    results = populated_store.search("anything", lesson_number=0)
    assert results.documents
    assert all(meta["lesson_number"] == 0 for meta in results.metadata)


def test_course_and_lesson_filters_combine(populated_store):
    results = populated_store.search("fastmcp", course_name="MCP", lesson_number=2)
    assert len(results.documents) == 1
    assert results.metadata[0]["course_title"] == MCP
    assert results.metadata[0]["lesson_number"] == 2


def test_null_lesson_number_chunk_round_trips(populated_store):
    results = populated_store.search("orphan paragraph", course_name=UNTITLED)
    assert results.documents
    assert results.metadata[0].get("lesson_number") is None


def test_outline_is_sorted_from_lesson_zero_with_gaps(populated_store):
    outline = populated_store.get_course_outline("MCP")
    assert outline["title"] == MCP
    assert outline["instructor"] == "Elie Schoppik"
    assert outline["course_link"] == "https://example.test/mcp"
    assert [lesson["lesson_number"] for lesson in outline["lessons"]] == [0, 2]


def test_course_missing_link_and_instructor_can_be_ingested(real_store):
    """document_processor defaults course_link to None and instructor to None.

    A transcript without a "Course Link:" or "Course Instructor:" header hits
    this path, so ingest must not reject it.
    """
    from models import Course

    real_store.add_course_metadata(
        Course(title="Header-less Course", course_link=None, instructor=None, lessons=[])
    )
    assert real_store.get_course_count() == 1
    assert real_store.get_course_link("Header-less Course") is None


def test_chunk_without_a_lesson_number_can_be_ingested(real_store):
    """The no-lesson-markers fallback in document_processor emits these."""
    from models import Course, CourseChunk

    real_store.add_course_metadata(
        Course(title="Prose Only", course_link="https://example.test/p", instructor="A")
    )
    real_store.add_course_content(
        [CourseChunk(content="just prose, no lessons", course_title="Prose Only",
                     lesson_number=None, chunk_index=0)]
    )
    results = real_store.search("prose", course_name="Prose Only")
    assert results.documents == ["just prose, no lessons"]


def test_outline_of_unresolvable_course_on_empty_catalog(real_store):
    """The only path to None is an empty catalog; see the note in commit 8b51b26."""
    assert real_store.get_course_outline("anything at all") is None


def test_links_and_catalog_counts(populated_store):
    assert populated_store.get_lesson_link(COMPUTER_USE, 0) == "https://example.test/cu/l0"
    assert populated_store.get_lesson_link(MCP, 2) is None  # seeded as null
    assert populated_store.get_course_link(UNTITLED) is None
    assert populated_store.get_course_count() == 3
    assert set(populated_store.get_existing_course_titles()) == {
        COMPUTER_USE,
        MCP,
        UNTITLED,
    }


def test_clear_all_data_empties_both_collections(populated_store):
    populated_store.clear_all_data()
    assert populated_store.get_course_count() == 0
    assert populated_store.search("protocol").documents == []


def test_search_tool_end_to_end_over_real_chroma(populated_store):
    """The whole read path: fuzzy title -> filter -> chunks -> citations."""
    from search_tools import CourseSearchTool

    tool = CourseSearchTool(populated_store)
    result = tool.execute(query="protocol server transport", course_name="MCP")

    assert f"[{MCP} - Lesson 0]" in result
    assert tool.last_sources[0] == {
        "text": f"{MCP} - Lesson 0",
        "link": "https://example.test/mcp/l0",
    }
