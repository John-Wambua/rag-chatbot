"""Shared fixtures for the backend suite.

Two tiers of isolation:

* ``fake_store`` — a scriptable stand-in for VectorStore. No ChromaDB, no
  embeddings. Used by nearly every test.
* ``real_store`` / ``populated_store`` — a real VectorStore in ``tmp_path`` with
  the SentenceTransformer embedder swapped for a deterministic hash embedder, so
  the real ChromaDB ``where`` filters and ``n_results`` path are exercised
  without loading a model or touching the network.
"""

# Environment guards must run before anything imports vector_store, which pulls
# in sentence_transformers/torch. The suite never builds the real embedder, but
# an accidental future one would otherwise hang ~77s reaching for the HF hub.
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

# pyproject sets pythonpath = ["backend"]; this keeps the directory importable
# on its own if that block is ever lost.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from models import Course, CourseChunk, Lesson
from vector_store import SearchResults

# --------------------------------------------------------------------------
# Stub embedder for the integration tier
# --------------------------------------------------------------------------


class StubEmbeddingFunction(EmbeddingFunction[Documents]):
    """Deterministic hashed bag-of-words embedder. No model, no network.

    Shared tokens between a query and a document raise cosine similarity, so
    retrieval is discriminative and reproducible across processes.
    """

    def __init__(self, model_name: str = "stub", dim: int = 64, **kwargs):
        # Must tolerate VectorStore's call: (model_name=embedding_model)
        self.model_name = model_name
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        # The parameter must be named `input`: chromadb validates this signature
        # against the protocol.
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        vec[0] = 1e-3  # never emit a zero vector; cosine distance would be NaN
        for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
            # blake2b, not builtin hash() — that is salted per process.
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            vec[int.from_bytes(digest, "big") % self.dim] += 1.0
        return vec / float(np.linalg.norm(vec))

    @staticmethod
    def name() -> str:
        return "stub_hash"  # constant: compared against the persisted config

    def default_space(self):
        return "cosine"

    def supported_spaces(self):
        return ["cosine", "l2", "ip"]

    def get_config(self):
        return {"model_name": self.model_name, "dim": self.dim}

    @staticmethod
    def build_from_config(config):
        return StubEmbeddingFunction(model_name=config["model_name"], dim=config["dim"])


# --------------------------------------------------------------------------
# Fake vector store
# --------------------------------------------------------------------------


class FakeVectorStore:
    """Scriptable stand-in covering exactly the surface the two tools touch."""

    def __init__(self):
        self._queued = []  # FIFO of SearchResults
        self.default = SearchResults(documents=[], metadata=[], distances=[])
        self.search_calls = []
        self.outline_calls = []
        self._outlines = {}
        self._course_links = {}
        self._lesson_links = {}
        self.analytics_titles = []

    # ---- scripting -------------------------------------------------
    def queue_hits(self, *pairs):
        """pairs: (document_text, metadata_dict)"""
        docs = [d for d, _ in pairs]
        metas = [m for _, m in pairs]
        self._queued.append(
            SearchResults(documents=docs, metadata=metas, distances=[0.1] * len(docs))
        )
        return self

    def queue_empty(self):
        self._queued.append(SearchResults(documents=[], metadata=[], distances=[]))
        return self

    def queue_error(self, message):
        self._queued.append(SearchResults.empty(message))
        return self

    def register_course(self, title, course_link=None, instructor=None, lessons=()):
        """lessons: iterable of (lesson_number, lesson_title, lesson_link)"""
        self._course_links[title] = course_link
        lesson_dicts = []
        for num, ltitle, link in lessons:
            self._lesson_links[(title, num)] = link
            lesson_dicts.append(
                {"lesson_number": num, "lesson_title": ltitle, "lesson_link": link}
            )
        self._outlines[title] = {
            "title": title,
            "course_link": course_link,
            "instructor": instructor,
            "lessons": lesson_dicts,
        }
        self.analytics_titles.append(title)
        return self

    # ---- VectorStore surface ---------------------------------------
    def search(self, query, course_name=None, lesson_number=None, limit=None):
        self.search_calls.append(
            {
                "query": query,
                "course_name": course_name,
                "lesson_number": lesson_number,
                "limit": limit,
            }
        )
        return self._queued.pop(0) if self._queued else self.default

    def get_course_link(self, course_title):
        return self._course_links.get(course_title)

    def get_lesson_link(self, course_title, lesson_number):
        return self._lesson_links.get((course_title, lesson_number))

    def get_course_outline(self, course_name):
        self.outline_calls.append(course_name)
        if course_name in self._outlines:
            return self._outlines[course_name]
        needle = course_name.lower()  # fragment match, like _resolve_course_name
        for title, outline in self._outlines.items():
            if needle in title.lower():
                return outline
        return None

    def get_course_count(self):
        return len(self.analytics_titles)

    def get_existing_course_titles(self):
        return list(self.analytics_titles)


# --------------------------------------------------------------------------
# Fake Anthropic client
# --------------------------------------------------------------------------
# Deliberately dataclasses, not MagicMock: MagicMock().text auto-vivifies, which
# would make the content[0].text defects silently pass.


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    name: str
    input: dict
    id: str = "toolu_01"
    type: str = "tool_use"
    # No `.text` attribute — this is what makes content[0].text raise.


@dataclass
class ThinkingBlock:
    thinking: str = "let me consider"
    signature: str = "sig"
    type: str = "thinking"
    # No `.text` attribute either.


@dataclass
class FakeMessage:
    content: list
    stop_reason: str = "end_turn"
    id: str = "msg_01"
    role: str = "assistant"
    model: str = "claude-sonnet-4-20250514"


class RecordingMessages:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = []  # every kwargs dict, in order

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._scripted:
            raise AssertionError(
                f"messages.create called {len(self.calls)} times; only "
                f"{len(self.calls) - 1} responses were scripted"
            )
        nxt = self._scripted.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class FakeAnthropicClient:
    def __init__(self, *scripted):
        self.messages = RecordingMessages(scripted)


def script(client, *responses):
    """Queue more responses onto an already-constructed fake client."""
    client.messages._scripted.extend(responses)


# --------------------------------------------------------------------------
# Fake RAGSystem for the API tier
# --------------------------------------------------------------------------


class FakeRAGSystem:
    def __init__(self, config=None):
        from session_manager import SessionManager

        self.session_manager = SessionManager(2)
        self.query_calls = []
        self.add_course_folder_calls = []
        self._answer = ("stub answer", [])
        self._raises = None
        self._analytics = {"total_courses": 0, "course_titles": []}
        self._analytics_raises = None

    def set_answer(self, answer, sources):
        self._answer = (answer, sources)

    def set_error(self, exc):
        self._raises = exc

    def set_analytics(self, analytics=None, raises=None):
        if analytics is not None:
            self._analytics = analytics
        self._analytics_raises = raises

    def query(self, query, session_id=None):
        self.query_calls.append({"query": query, "session_id": session_id})
        if self._raises is not None:
            raise self._raises
        return self._answer

    def get_course_analytics(self):
        if self._analytics_raises is not None:
            raise self._analytics_raises
        return self._analytics

    def add_course_folder(self, folder_path, clear_existing=False):
        self.add_course_folder_calls.append((folder_path, clear_existing))
        return 0, 0


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def fake_store():
    return FakeVectorStore()


@pytest.fixture
def search_tool(fake_store):
    from search_tools import CourseSearchTool

    return CourseSearchTool(fake_store)


@pytest.fixture
def outline_tool(fake_store):
    from search_tools import CourseOutlineTool

    return CourseOutlineTool(fake_store)


@pytest.fixture
def tool_manager(fake_store):
    """A ToolManager wired exactly like RAGSystem wires it."""
    from search_tools import CourseOutlineTool, CourseSearchTool, ToolManager

    manager = ToolManager()
    manager.register_tool(CourseSearchTool(fake_store))
    manager.register_tool(CourseOutlineTool(fake_store))
    return manager


@pytest.fixture
def make_generator():
    """Build a real AIGenerator with a scripted fake client attached."""
    from ai_generator import AIGenerator

    def _make(*scripted):
        gen = AIGenerator(api_key="test-key-not-real", model="claude-sonnet-4-20250514")
        client = FakeAnthropicClient(*scripted)
        gen.client = client  # real __init__ ran, so base_params is the real thing
        return gen, client

    return _make


@pytest.fixture
def rag(monkeypatch, tmp_path, fake_store):
    """Real RAGSystem wiring with the vector store and Anthropic client faked."""
    import dataclasses

    import rag_system as rag_module
    from config import config as real_config

    cfg = dataclasses.replace(
        real_config,
        CHROMA_PATH=str(tmp_path / "chroma"),
        ANTHROPIC_API_KEY="test-key-not-real",
    )
    monkeypatch.setattr(
        rag_module, "VectorStore", lambda path, model, max_results: fake_store
    )
    system = rag_module.RAGSystem(cfg)
    client = FakeAnthropicClient()
    system.ai_generator.client = client
    return system, fake_store, client


@pytest.fixture
def real_store(monkeypatch, tmp_path):
    """A real VectorStore over real ChromaDB, with a stub embedder."""
    import chromadb.utils.embedding_functions as ef_mod

    monkeypatch.setattr(
        ef_mod, "SentenceTransformerEmbeddingFunction", StubEmbeddingFunction
    )
    from vector_store import VectorStore

    return VectorStore(str(tmp_path / "chroma"), "stub-model", max_results=5)


COMPUTER_USE = "Building Toward Computer Use with Anthropic"
MCP = "MCP: Build Rich-Context AI Apps"
UNTITLED = "Untitled Notes"


@pytest.fixture
def populated_store(real_store):
    """Three synthetic courses ingested directly, bypassing document_processor."""
    courses = [
        Course(
            title=COMPUTER_USE,
            course_link="https://example.test/computer-use",
            instructor="Colt Steele",
            lessons=[
                Lesson(
                    lesson_number=0,
                    title="Introduction",
                    lesson_link="https://example.test/cu/l0",
                ),
                Lesson(
                    lesson_number=1,
                    title="Overview",
                    lesson_link="https://example.test/cu/l1",
                ),
            ],
        ),
        Course(
            title=MCP,
            course_link="https://example.test/mcp",
            instructor="Elie Schoppik",
            lessons=[
                Lesson(
                    lesson_number=0,
                    title="Why MCP",
                    lesson_link="https://example.test/mcp/l0",
                ),
                # lesson 1 is deliberately missing, and this link is null
                Lesson(lesson_number=2, title="Creating a server", lesson_link=None),
            ],
        ),
        # No lessons, no links, no instructor
        Course(title=UNTITLED, course_link=None, instructor=None, lessons=[]),
    ]
    chunks = [
        CourseChunk(
            content="screenshot mouse keystroke virtual machine loop",
            course_title=COMPUTER_USE,
            lesson_number=0,
            chunk_index=0,
        ),
        CourseChunk(
            content="tool definition schema anthropic sdk beta header",
            course_title=COMPUTER_USE,
            lesson_number=1,
            chunk_index=1,
        ),
        CourseChunk(
            content="protocol server transport stdio resources prompts",
            course_title=MCP,
            lesson_number=0,
            chunk_index=0,
        ),
        CourseChunk(
            content="fastmcp decorator register handler capability",
            course_title=MCP,
            lesson_number=2,
            chunk_index=1,
        ),
        CourseChunk(
            content="orphan paragraph with no lesson marker at all",
            course_title=UNTITLED,
            lesson_number=None,
            chunk_index=0,
        ),
    ]
    for course in courses:
        real_store.add_course_metadata(course)
    real_store.add_course_content(chunks)
    return real_store


@pytest.fixture(scope="session")
def app_module():
    """Import the real backend/app.py with RAGSystem construction neutered.

    app.py builds RAGSystem(config) at module scope and StaticFiles("../frontend")
    at line 133. The former would load the embedding model and write to the
    developer's real chroma_db; the latter raises unless cwd is backend/.
    """
    import types

    saved_rag = sys.modules.get("rag_system")
    saved_app = sys.modules.pop("app", None)
    stub = types.ModuleType("rag_system")
    stub.RAGSystem = FakeRAGSystem
    sys.modules["rag_system"] = stub

    cwd = os.getcwd()
    os.chdir(BACKEND)
    try:
        import app as app_mod
    finally:
        os.chdir(cwd)
        # Don't leave the stub shadowing the real module for other test files.
        if saved_rag is None:
            del sys.modules["rag_system"]
        else:
            sys.modules["rag_system"] = saved_rag

    yield app_mod

    sys.modules.pop("app", None)
    if saved_app is not None:
        sys.modules["app"] = saved_app


@pytest.fixture
def api(app_module, monkeypatch):
    """(client, fake_rag). Bare TestClient, so @on_event("startup") never fires."""
    from starlette.testclient import TestClient

    fake = FakeRAGSystem()
    monkeypatch.setattr(app_module, "rag_system", fake)
    return TestClient(app_module.app), fake
