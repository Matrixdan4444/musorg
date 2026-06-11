from __future__ import annotations

import json
import subprocess
import sys
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
    webview.start(debug=debug, gui="cocoa" if sys.platform == "darwin" else None)
    if window is None:
        raise RuntimeError("Failed to create the desktop window.")
