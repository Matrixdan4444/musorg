from __future__ import annotations

from collections.abc import Iterable, Mapping


def summarize_actionable_issue_items(
    issues: Iterable[Mapping[str, object]] | None,
    *,
    success_when_clean: bool = True,
) -> dict[str, int]:
    danger = 0
    warning = 0
    for issue in issues or ():
        severity = str(issue.get("severity") or "").strip().lower()
        if severity == "danger":
            danger += 1
        elif severity == "warning":
            warning += 1
    return {
        "danger": danger,
        "warning": warning,
        "success": 1 if success_when_clean and danger == 0 and warning == 0 else 0,
    }
