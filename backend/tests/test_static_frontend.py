"""The static mount at ``/`` — the only route the browser hits for the UI.

Everything in test_api_endpoints.py covers the JSON API. This file covers the
other half of the contract: that the SPA shell and its two assets are actually
delivered, that the catch-all mount does not swallow ``/api/*``, and that the
hand-maintained pieces of frontend wiring (cache-bust versions, element ids,
script order) still line up. Those last ones are pure static analysis of
frontend/, but they live here because a break in them is indistinguishable
from a broken page.
"""

import re

import pytest

pytestmark = pytest.mark.frontend

# Local assets referenced from index.html, e.g. href="style.css?v=13".
LOCAL_ASSET_REF = re.compile(r'(?:href|src)="(?!https?://|//)([^"?#]+)(\?v=(\d+))?"')


def local_asset_refs(html):
    """(path, full_ref, version_or_None) for each same-origin href/src."""
    return [
        (m.group(1), m.group(0).split('"')[1], m.group(3))
        for m in LOCAL_ASSET_REF.finditer(html)
    ]


# --------------------------------------------------------------------------
# Serving
# --------------------------------------------------------------------------


def test_root_serves_the_index_document(frontend_client):
    response = frontend_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Course Materials Assistant</title>" in response.text


def test_index_html_is_reachable_by_name_too(frontend_client):
    """html=True maps / to index.html; the explicit path must work as well."""
    assert frontend_client.get("/index.html").status_code == 200


@pytest.mark.parametrize(
    "path,content_type",
    [("/style.css", "text/css"), ("/script.js", "javascript")],
)
def test_frontend_assets_are_served(frontend_client, path, content_type):
    response = frontend_client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.content, f"{path} served empty"


def test_cache_busted_asset_urls_resolve(frontend_client, index_html):
    """The browser requests style.css?v=13, not style.css. Both must 200."""
    refs = [ref for _, ref, version in local_asset_refs(index_html) if version]

    assert refs, "expected at least one ?v= cache-busted asset in index.html"
    for ref in refs:
        assert frontend_client.get(f"/{ref}").status_code == 200, ref


def test_unknown_asset_returns_404_not_the_index(frontend_client):
    """html=True must not turn a typo'd asset path into a 200 HTML page."""
    response = frontend_client.get("/does-not-exist.js")

    assert response.status_code == 404


def test_static_mount_does_not_shadow_the_api(frontend_client):
    """The mount is at "/", so route order is load-bearing."""
    assert frontend_client.get("/api/courses").status_code == 200
    assert frontend_client.post("/api/query", json={"query": "q"}).status_code == 200


def test_static_mount_does_not_serve_files_outside_frontend(frontend_client):
    """A traversal out of frontend/ would expose .env and the chroma_db."""
    for path in ("/../.env", "/..%2f.env", "/%2e%2e/config.py"):
        assert frontend_client.get(path).status_code in (
            403,
            404,
        ), f"{path} was served"


# --------------------------------------------------------------------------
# Hand-maintained wiring (CLAUDE.md: cache-busting is manual)
# --------------------------------------------------------------------------


def test_all_cache_bust_versions_move_together(index_html):
    """style.css?v=N and script.js?v=N must share N.

    Bumping one and not the other ships a stale half of the pair to every
    browser that already has the old file cached.
    """
    versions = {version for _, _, version in local_asset_refs(index_html) if version}

    assert len(versions) == 1, f"mismatched cache-bust versions: {sorted(versions)}"


def test_every_local_asset_ref_exists_on_disk(frontend_dir, index_html):
    for path, _, _ in local_asset_refs(index_html):
        assert (frontend_dir / path).is_file(), f"index.html references missing {path}"


def test_element_ids_queried_by_script_exist_in_the_markup(index_html, script_js):
    """getElementById on a missing id yields null and the handler dies silently."""
    ids = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", script_js))

    assert ids, "no getElementById calls found; did script.js change shape?"
    missing = [i for i in ids if f'id="{i}"' not in index_html]
    assert not missing, f"script.js queries ids absent from index.html: {missing}"


def test_marked_loads_before_script_js(index_html):
    """script.js calls marked.parse() on assistant text at message time."""
    marked_at = index_html.find("marked.min.js")
    script_at = index_html.find("script.js")

    assert marked_at != -1, "marked.min.js is no longer loaded"
    assert marked_at < script_at, "script.js is loaded before marked"


def test_frontend_calls_the_api_on_a_relative_path(script_js):
    """An absolute host here breaks the single-process static+API deployment."""
    match = re.search(r"""const API_URL = ['"]([^'"]+)['"]""", script_js)

    assert match, "API_URL declaration not found in script.js"
    assert match.group(1) == "/api"


def test_every_endpoint_the_frontend_calls_is_routed(app_module, script_js):
    """fetch() targets in script.js vs. the routes app.py actually declares."""
    declared = {
        (route.path, method)
        for route in app_module.app.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }

    assert ("/api/query", "POST") in declared
    assert ("/api/courses", "GET") in declared
    assert ("/api/session/{session_id}", "DELETE") in declared
    # And the frontend still calls all three.
    for fragment in ("/query", "/courses", "/session/"):
        assert f"${{API_URL}}{fragment}" in script_js, fragment
