from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass(slots=True)
class WindowConfig:
    title: str = "Musorg"
    min_width: int = 1100
    min_height: int = 760
    width: int = 1440
    height: int = 920
    background_color: str = "#0b0f18"


def show_error_dialog(title: str, message: str) -> None:
    if sys.platform == "darwin":
        script = (
            f'display alert {json.dumps(title)} '
            f'message {json.dumps(message)} as critical'
        )
        subprocess.run(["osascript", "-e", script], check=False)
        return

    print(f"{title}: {message}", file=sys.stderr)


def _enable_macos_web_inspector() -> None:
    """Turn on the WKWebView Web Inspector on macOS 13.3+.

    pywebview's Cocoa backend only sets ``developerExtrasEnabled`` in debug mode,
    but newer macOS additionally gates the inspector behind the ``isInspectable``
    property (default off). Without this, right-click -> "Inspect Element" does
    nothing. Runs after the GUI loop starts, so the native webview already exists.
    """
    if sys.platform != "darwin":
        return
    try:
        from webview.platforms.cocoa import BrowserView
    except Exception:
        return
    for _ in range(20):
        instances = list(getattr(BrowserView, "instances", {}).values())
        for browser_view in instances:
            native_webview = getattr(browser_view, "webview", None)
            if native_webview is not None and native_webview.respondsToSelector_("setInspectable:"):
                native_webview.setInspectable_(True)
        if instances:
            return
        time.sleep(0.1)


def launch_window(url: str, *, debug: bool, config: WindowConfig | None = None) -> None:
    try:
        import webview
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pywebview is not installed. Install it before launching the desktop webview runtime."
        ) from exc

    resolved = config or WindowConfig()
    window = webview.create_window(
        resolved.title,
        url=url,
        min_size=(resolved.min_width, resolved.min_height),
        width=resolved.width,
        height=resolved.height,
        background_color=resolved.background_color,
        text_select=True,
    )
    webview.start(
        _enable_macos_web_inspector if debug else None,
        debug=debug,
        gui="cocoa" if sys.platform == "darwin" else None,
    )
    if window is None:
        raise RuntimeError("Failed to create the desktop window.")
