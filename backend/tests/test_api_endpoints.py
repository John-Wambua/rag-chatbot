"""The FastAPI layer: session latching, source serialization, error handling.

Uses the real app module with RAGSystem stubbed at import time, so the real
routes, middleware and pydantic models are exercised.
"""

import pytest


def test_query_creates_session_when_none_provided(api):
    client, fake = api
    fake.set_answer("an answer", [])

    response = client.post("/api/query", json={"query": "what is MCP?"})

    assert response.status_code == 200
    assert response.json()["session_id"] == "session_1"
    assert fake.query_calls == [{"query": "what is MCP?", "session_id": "session_1"}]


def test_query_reuses_provided_session_id(api):
    client, fake = api
    fake.set_answer("an answer", [])

    response = client.post(
        "/api/query", json={"query": "follow up", "session_id": "session_42"}
    )

    assert response.json()["session_id"] == "session_42"
    assert fake.query_calls[0]["session_id"] == "session_42"


def test_query_serializes_sources_with_optional_link(api):
    client, fake = api
    fake.set_answer(
        "an answer",
        [
            {"text": "Course A - Lesson 1", "link": "https://example.test/a/1"},
            {"text": "Course B", "link": None},
        ],
    )

    body = client.post("/api/query", json={"query": "q"}).json()

    assert body["sources"] == [
        {"text": "Course A - Lesson 1", "link": "https://example.test/a/1"},
        {"text": "Course B", "link": None},
    ]


def test_query_rejects_missing_query_field(api):
    client, _ = api
    assert client.post("/api/query", json={}).status_code == 422


def test_query_rag_exception_becomes_500(api):
    client, fake = api
    fake.set_error(RuntimeError("boom"))

    response = client.post("/api/query", json={"query": "q"})

    assert response.status_code == 500


def test_query_error_detail_does_not_leak_internals(api):
    """A raw exception string can carry filesystem paths or auth details."""
    client, fake = api
    fake.set_error(RuntimeError("/Users/someone/secret/path exploded"))

    response = client.post("/api/query", json={"query": "q"})

    assert response.status_code == 500
    assert "/Users/someone/secret" not in response.json()["detail"]


def test_courses_returns_total_and_titles(api):
    client, fake = api
    fake.set_analytics({"total_courses": 2, "course_titles": ["A", "B"]})

    body = client.get("/api/courses").json()

    assert body == {"total_courses": 2, "course_titles": ["A", "B"]}


def test_courses_exception_becomes_500(api):
    client, fake = api
    fake.set_analytics(raises=RuntimeError("chroma down"))
    assert client.get("/api/courses").status_code == 500


def test_delete_session_is_idempotent(api):
    client, _ = api
    response = client.delete("/api/session/session_does_not_exist")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"


def test_startup_ingest_not_triggered_by_testclient(api):
    """Guard: entering TestClient as a context manager would ingest real docs/."""
    client, fake = api
    fake.set_answer("a", [])
    client.post("/api/query", json={"query": "q"})
    assert fake.add_course_folder_calls == []
