from __future__ import annotations

from musorg.desktop_webview.runtime import parse_runtime_options, run_desktop_runtime


def main(argv: list[str] | None = None) -> int:
    options = parse_runtime_options(argv)
    return run_desktop_runtime(options)
