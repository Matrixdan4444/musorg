from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from musorg.desktop_webview.server import managed_runtime_server
from musorg.desktop_webview.window import launch_window, show_error_dialog


@dataclass(slots=True)
class RuntimeOptions:
    mode: str
    debug: bool


def parse_runtime_options(argv: list[str] | None = None) -> RuntimeOptions:
    parser = argparse.ArgumentParser(prog="musorg.desktop_webview")
    parser.add_argument("--dev", action="store_true", help="Run against the Vite dev server.")
    parser.add_argument("--embedded", action="store_true", help="Run against built frontend assets.")
    args = parser.parse_args(argv)

    env_mode = os.environ.get("MUSORG_DESKTOP_MODE", "").strip().lower()
    mode = "dev" if env_mode == "dev" else "embedded"
    if args.dev:
        mode = "dev"
    if args.embedded:
        mode = "embedded"

    return RuntimeOptions(
        mode=mode,
        debug=mode == "dev",
    )


def run_desktop_runtime(options: RuntimeOptions) -> int:
    try:
        with managed_runtime_server(options.mode) as (_, urls, _):
            launch_window(urls.frontend_url, debug=options.debug)
    except Exception as exc:
        show_error_dialog("Musorg failed to start", str(exc))
        return 1

    return 0
