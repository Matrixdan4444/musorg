from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from musorg.desktop_webview.runtime import parse_runtime_options
from musorg.desktop_webview.server import build_frontend_url


class DesktopWebviewRuntimeTests(unittest.TestCase):
    def test_parse_runtime_options_defaults_to_embedded(self):
        with patch.dict(os.environ, {}, clear=False):
            options = parse_runtime_options([])

        self.assertEqual(options.mode, "embedded")
        self.assertFalse(options.debug)

    def test_parse_runtime_options_honors_dev_flag(self):
        options = parse_runtime_options(["--dev"])

        self.assertEqual(options.mode, "dev")
        self.assertTrue(options.debug)

    def test_build_frontend_url_includes_runtime_metadata(self):
        url = build_frontend_url("http://127.0.0.1:5173", "http://127.0.0.1:8000", "dev")

        self.assertIn("api_origin=http://127.0.0.1:8000", url)
        self.assertIn("runtime_mode=dev", url)
        self.assertIn("host_kind=pywebview", url)
