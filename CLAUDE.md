# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                              # install dependencies
./run.sh                                             # start the app (chmod +x first if needed)
cd backend && uv run uvicorn app:app --reload --port 8000   # manual start, equivalent
```

Web UI at http://localhost:8000, OpenAPI docs at http://localhost:8000/docs.

Requires `ANTHROPIC_API_KEY` in a root `.env` (see `.env.example`). Python ≥3.13.

**Always use `uv`. Never use `pip`.** Run the server with `uv run uvicorn ...` (or `./run.sh`, which wraps it) — never a bare `uvicorn`, `python`, or `python -m`. Install and change dependencies with `uv sync` / `uv add`, never `pip install`. Dependencies are locked in `uv.lock`; `pip` bypasses that lock and the project venv.

There is no test suite, linter, or formatter configured. If you add tests, `uv add --dev pytest` first so the lockfile stays authoritative, and run them with `uv run pytest`.

**The server must run with `backend/` as the working directory.** Two paths depend on it: `CHROMA_PATH = "./chroma_db"` (`backend/config.py`) and the startup ingest of `"../docs"` (`backend/app.py`). Running uvicorn from the repo root silently creates a second, empty ChromaDB and loads no courses.

## Architecture

FastAPI + ChromaDB + Anthropic tool calling. `backend/rag_system.py` is the orchestrator; every other backend module is a component it owns.

### This is agentic RAG, not pipeline RAG

The backend does **not** retrieve context and stuff it into the prompt. It exposes a `search_course_content` tool and lets Claude decide whether to use it. Consequences worth internalizing before changing this flow:

- **Two Claude calls per searched query, one for general knowledge.** Call #1 (`ai_generator.py:80`) includes tools with `tool_choice: auto`. If `stop_reason != "tool_use"`, the text is returned immediately and no search ever happens. Otherwise `_handle_tool_execution` runs the tool and makes call #2.
- **Exactly one search round is possible by construction.** Call #2 (`ai_generator.py:128`) deliberately omits `tools`, and `SYSTEM_PROMPT` says "One search per query maximum". Multi-hop questions ("compare lesson 5 of X with lesson 2 of Y") cannot be served without turning that into a loop.
- **Search failures are text, not exceptions.** An unresolvable course name or a Chroma error becomes a `SearchResults.empty("...")` message that flows back as tool-result *text for Claude to read and paraphrase*. Users never see a 500 for a failed search. Don't "fix" this by raising.
- **Citations travel via mutable state, not return values.** `CourseSearchTool._format_results` sets `self.last_sources` (`search_tools.py:112`); `RAGSystem.query` harvests it afterwards via `ToolManager.get_last_sources()` and then calls `reset_sources()`. The single tool instance is shared across requests, so concurrent queries can cross-contaminate citations.

### Two ChromaDB collections, and why

`vector_store.py` maintains two collections, and `search()` queries them in sequence:

1. `course_catalog` — one document per course (the title), with instructor/links/lessons in metadata. Searched **first** to resolve a fuzzy user fragment ("MCP") to the exact stored title via `_resolve_course_name`.
2. `course_content` — the actual text chunks. Searched **second**, filtered by the resolved title and/or `lesson_number` via `_build_filter`.

Course **title is the primary key** everywhere — the Chroma document ID in `course_catalog`, the `course_title` metadata field on every chunk, and the dedupe key on ingest. Renaming a course orphans its chunks.

### Ingest

`app.py` startup calls `add_course_folder("../docs", clear_existing=False)`, which is idempotent: it parses each file but skips any course whose title is already in the catalog, so restarts don't re-embed. To force a rebuild, pass `clear_existing=True` or delete `backend/chroma_db/`.

`document_processor.py` expects a specific transcript format:

```
Course Title: ...
Course Link: ...
Course Instructor: ...

Lesson 0: <title>
Lesson Link: ...
<content...>
```

Chunking is sentence-aware with overlap (800 / 100, from `config.py`), and lesson/course context is prefixed onto chunk text to improve retrieval. Note the two chunk-emitting paths in `process_course_document` are inconsistent: the mid-document loop prefixes `"Lesson N content:"` onto only the first chunk of a lesson, while the final-lesson path prefixes `"Course <title> Lesson N content:"` onto every chunk.

### Session state

`session_manager.py` is an in-memory dict keyed `session_1`, `session_2`, … It resets on restart and will not work across multiple uvicorn workers. History is flattened to a `"User: ...\nAssistant: ..."` string and appended to the system prompt; only the last `MAX_HISTORY * 2 = 4` messages are kept.

### Frontend

`frontend/` is dependency-free vanilla JS, served as static files by the same FastAPI process (mounted at `/`, so `API_URL = '/api'` is relative and host-agnostic). Two endpoints only: `POST /api/query` and `GET /api/courses`. `session_id` is `null` on the first request and latched from the response thereafter. Assistant text is rendered through `marked.parse()`; user text through `escapeHtml()`.

Cache-busting is manual — `index.html` references `style.css?v=9` and `script.js?v=9`. Bump both when editing those files.

## Known dead code

Don't assume these are wired up: `vector_store.get_course_link`, `get_lesson_link`, and `get_all_courses_metadata` are never called — links are captured at ingest but never surfaced, and `sources` reach the UI as plain strings with no href. `app.py` defines `DevStaticFiles` but mounts plain `StaticFiles`. Root `main.py` is an unused stub.
