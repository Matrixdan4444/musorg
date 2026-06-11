from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from musorg.api.server import ApiRuntimeConfig, create_app


class ApiRuntimeTests(unittest.TestCase):
    def test_create_app_exposes_expected_routes(self):
        app = create_app()

        routes = {route.path for route in app.routes}

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

        routes = {route.path for route in app.routes}
        self.assertIn("/", routes)
        self.assertIn("/{full_path:path}", routes)
