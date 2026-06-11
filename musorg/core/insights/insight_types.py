from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InsightCategory = Literal["quality", "duplicate", "suspicious_audio", "collection", "recommendation"]
InsightSeverity = Literal["danger", "warning", "success", "neutral"]
InsightScope = Literal["album", "family"]


@dataclass(frozen=True)
class InsightItem:
    id: str
    category: InsightCategory
    severity: InsightSeverity
    title: str
    message: str
    reasoning: tuple[str, ...]
    confidence: int
    related_paths: tuple[str, ...]
    actionable: bool
    recommendation_type: str | None
    generated_at: str | None
    scope: InsightScope
    priority: int
    dedupe_key: str


@dataclass(frozen=True)
class InsightRegistry:
    summaries_by_path: dict[str, dict]
    payloads_by_path: dict[str, dict]
