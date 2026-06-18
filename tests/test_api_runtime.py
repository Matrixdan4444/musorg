from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from musorg.api.server import ApiRuntimeConfig, create_app


def _registered_paths(app) -> set[str]:
    """Collect every registered path in a FastAPI-version-agnostic way.

    Newer FastAPI wraps included routers in `_IncludedRouter` objects that have
    no `.path`, so iterating `app.routes` alone no longer exposes router paths.
    The OpenAPI schema carries the API paths; the static/catch-all routes are
    still top-level routes with a `.path`. Union both.
    """
    paths = set(app.openapi().get("paths", {}).keys())
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    return paths


class ApiRuntimeTests(unittest.TestCase):
    def test_create_app_exposes_expected_routes(self):
        app = create_app()

        routes = _registered_paths(app)

        self.assertIn("/health", routes)
        self.assertIn("/albums", routes)
        self.assertIn("/albums/{album_id}", routes)
        self.assertIn("/albums/{album_id}/cover", routes)
        self.assertIn("/albums/{album_id}/tracks", routes)
        self.assertIn("/albums/{album_id}/actions", routes)
        self.assertIn("/runs/{run_id}/albums", routes)
        self.assertIn("/runs/{run_id}/albums/{album_id}", routes)
        self.assertIn("/runs/{run_id}/albums/{album_id}/cover", routes)
        self.assertIn("/runs/{run_id}/albums/{album_id}/tracks", routes)
        self.assertIn("/settings/library", routes)
        self.assertIn("/settings/library/pick", routes)
        self.assertIn("/settings/cache/clear", routes)

    def test_create_app_mounts_frontend_when_dist_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir)
            assets = dist / "assets"
            assets.mkdir()
            (dist / "index.html").write_text("<html></html>", encoding="utf-8")

            app = create_app(ApiRuntimeConfig(frontend_dist=dist, allow_origins=[]))

        routes = _registered_paths(app)
        self.assertIn("/", routes)
        self.assertIn("/{full_path:path}", routes)
