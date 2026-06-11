from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re
from typing import Any


FIELD_LABELS = {
    "albumartist": "Album Artist",
    "artist": "Artist",
    "album": "Album",
    "date": "Year",
    "genre": "Genre",
    "cover": "Cover",
    "releasetype": "Release Type",
}

DEEZER_REASON_MESSAGES = {
    "no_candidates": "Deezer could not find any release candidates.",
    "no_acceptable_candidate": "Deezer candidates were rejected during release validation.",
    "search_unavailable": "Deezer search did not return a reliable response.",
    "album_details_unavailable": "Deezer album details could not be loaded.",
    "invalid_payload": "Deezer returned incomplete metadata for this release.",
    "partial_payload": "Deezer did not provide a complete release payload.",
    "track_count_mismatch": "Deezer release rejected because track counts did not match.",
    "validation_rejected": "Deezer release failed Musorg's validation checks.",
    "album_details_mismatch": "Deezer release details did not match the local album.",
    "unknown": "Deezer did not provide a reliable release.",
}

MANUAL_OVERRIDE_FIELDS = {
    "albumTitle": "album",
    "albumArtist": "albumartist",
    "genre": "genre",
    "year": "date",
    "metadataProvider": "provider",
    "yearSource": "date",
    "coverHandlingMode": "cover",
    "capitalizationMode": "album",
    "normalizeFeaturingArtists": "artist",
    "overwriteExistingTags": "album",
    "compilation": "album",
    "explicit": "album",
}

SUSPICIOUS_ISSUE_MAP = {
    "track-count-mismatch": ("Track count mismatch", "warning"),
    "provider-disagreement": ("Provider disagreement", "warning"),
    "conflicting-release-year": ("Conflicting release year", "warning"),
    "low-quality-artwork": ("Artwork could be higher quality", "warning"),
    "mixed-primary-artists": ("Different primary artists detected", "danger"),
    "runtime-mismatch": ("Release runtime mismatch", "warning"),
    "suspicious-release-title": ("Suspicious release title", "warning"),
    "unofficial-release": ("Release may be unofficial", "danger"),
    "duplicate-tracks": ("Duplicate tracks detected", "warning"),
    "broken-sequencing": ("Track sequencing looks broken", "warning"),
}

SUSPICIOUS_TITLE_PATTERN = re.compile(
    r"\b(greatest hits|best of|ultimate|collection|anthology|bootleg|fan[\s-]?upload|unofficial|promo|mixtape)\b",
    re.IGNORECASE,
)
RANGE_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}[_\-–](19|20)\d{2}\b")
VERSION_TITLE_PATTERN = re.compile(r"\b(remaster(?:ed)?|deluxe|expanded|bonus|anniversary)\b", re.IGNORECASE)


def metadata_snapshot(track: dict, *, fallback_album_artist: str | None = None, track_count: int | None = None) -> dict[str, Any]:
    return {
        "albumartist": _text(track.get("albumartist")) or _text(fallback_album_artist) or "Unknown artist",
        "artist": _text(track.get("artist")) or "Unknown artist",
        "album": _text(track.get("album")) or "Unknown album",
        "date": _track_year(track) or "Unknown",
        "genre": _genre_value(track),
        "cover": _cover_summary(track),
        "releasetype": _text(track.get("releasetype")) or "Unknown",
        "trackCount": track_count or 0,
    }


def build_metadata_intelligence(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    resolved: dict | None,
    override: dict | None,
    group_tracks: list[dict],
) -> dict[str, Any]:
    resolved = resolved or {}
    deezer = resolved.get("deezer")
    musicbrainz = resolved.get("musicbrainz")
    deezer_reason = _deezer_reason(resolved)
    metadata_provider = _metadata_provider(deezer, musicbrainz)
    artwork_provider = _artwork_provider(before, deezer, musicbrainz)
    suspicious = detect_suspicious_metadata(
        before=before,
        after=after,
        deezer=deezer,
        musicbrainz=musicbrainz,
        deezer_reason=deezer_reason,
        group_tracks=group_tracks,
    )

    diff = _diff_fields(before, after, override or {})
    cleanup_actions = _cleanup_actions(diff, override or {})
    if metadata_provider == "musicbrainz":
        cleanup_actions.append({
            "kind": "provider_selection",
            "label": "Used MusicBrainz because it provided a more complete release.",
            "source": "musicbrainz",
            "origin": "auto_fix",
        })
    elif metadata_provider == "deezer":
        cleanup_actions.append({
            "kind": "provider_selection",
            "label": "Trusted Deezer because it passed Musorg's release checks.",
            "source": "deezer",
            "origin": "auto_fix",
        })

    provider_decisions = {
        "metadataProvider": metadata_provider,
        "artworkProvider": artwork_provider,
        "winner": metadata_provider,
        "path": _text(resolved.get("path")) or "local-only",
        "rejectedProviders": _rejected_providers(deezer_reason),
    }

    confidence = _confidence_summary(
        before=before,
        after=after,
        deezer=deezer,
        musicbrainz=musicbrainz,
        deezer_reason=deezer_reason,
        metadata_provider=metadata_provider,
        suspicious=suspicious,
        group_tracks=group_tracks,
    )
    match_reasoning = _match_reasoning(
        confidence=confidence,
        before=before,
        after=after,
        deezer_reason=deezer_reason,
    )

    return {
        "before": before,
        "after": after,
        "diff": diff,
        "cleanupActions": cleanup_actions,
        "providerDecisions": provider_decisions,
        "matchReasoning": match_reasoning,
        "confidence": confidence,
        "suspiciousMetadata": suspicious,
        "autoFixDiagnostics": _auto_fix_diagnostics(
            before=before,
            after=after,
            provider_decisions=provider_decisions,
            confidence=confidence,
            suspicious=suspicious,
            cleanup_actions=cleanup_actions,
        ),
    }


def augment_metadata_intelligence(
    intelligence: dict[str, Any] | None,
    *,
    output_path: str | None = None,
    complete: bool = False,
) -> dict[str, Any] | None:
    if not intelligence:
        return None

    payload = deepcopy(intelligence)
    actions = list(payload.get("cleanupActions") or [])
    if complete and output_path and not any(action.get("kind") == "organized_folder" for action in actions):
        actions.append({
            "kind": "organized_folder",
            "label": "Organized album folder in the output library.",
            "source": "organize",
            "origin": "auto_fix",
        })
    payload["cleanupActions"] = actions
    return payload


def metadata_intelligence_issues(metadata_intelligence: dict[str, Any] | None) -> list[dict[str, str]]:
    if not metadata_intelligence:
        return []

    issues = []
    seen = set()
    for item in metadata_intelligence.get("suspiciousMetadata") or []:
        issue_id = _text(item.get("id"))
        if not issue_id or issue_id in seen:
            continue
        seen.add(issue_id)
        label, severity = SUSPICIOUS_ISSUE_MAP.get(
            issue_id,
            (_text(item.get("label")) or issue_id.replace("-", " ").title(), _text(item.get("severity")) or "warning"),
        )
        issues.append({
            "id": issue_id,
            "label": label,
            "severity": severity,
        })
    return issues


def _diff_fields(before: dict[str, Any], after: dict[str, Any], override: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    manual_targets = {MANUAL_OVERRIDE_FIELDS[key] for key, value in override.items() if value not in (None, "", False)}
    for field, label in FIELD_LABELS.items():
        before_value = _text(before.get(field)) or "—"
        after_value = _text(after.get(field)) or "—"
        if before_value == after_value:
            continue
        rows.append({
            "id": field,
            "label": label,
            "before": before_value,
            "after": after_value,
            "origin": "manual_override" if field in manual_targets else "auto_fix",
        })
    return rows


def _cleanup_actions(diff: list[dict[str, Any]], override: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    labels = {
        "albumartist": "Fixed album artist.",
        "artist": "Cleaned track artist credits.",
        "album": "Normalized album title.",
        "date": "Resolved release year.",
        "genre": "Updated genre tags.",
        "cover": "Updated album artwork.",
        "releasetype": "Corrected release type.",
    }
    for item in diff:
        actions.append({
            "kind": item["id"],
            "label": labels.get(item["id"], f"Updated {item['label'].lower()}."),
            "source": "cleanup",
            "origin": item["origin"],
        })
    if override:
        for field, value in override.items():
            if value in (None, "", False):
                continue
            if field not in MANUAL_OVERRIDE_FIELDS:
                continue
            target = MANUAL_OVERRIDE_FIELDS[field]
            if any(action["kind"] == target and action["origin"] == "manual_override" for action in actions):
                continue
            actions.append({
                "kind": target,
                "label": "Applied a staged manual override.",
                "source": field,
                "origin": "manual_override",
            })
    return actions


def detect_suspicious_metadata(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    deezer: dict | None,
    musicbrainz: dict | None,
    deezer_reason: str | None,
    group_tracks: list[dict],
) -> list[dict[str, Any]]:
    suspicious = []
    seen = set()
    musicbrainz_date_only = _is_date_only_provider_metadata(musicbrainz)

    def add(item: dict[str, Any]) -> None:
        issue_id = _text(item.get("id"))
        if not issue_id or issue_id in seen:
            return
        seen.add(issue_id)
        suspicious.append(item)

    if deezer_reason == "track_count_mismatch":
        track_count_details: dict[str, Any] = {}
        if before.get("trackCount"):
            track_count_details["localTrackCount"] = int(before.get("trackCount") or 0)
        if deezer and isinstance(deezer.get("tracks"), list):
            track_count_details["providerTrackCount"] = len(deezer.get("tracks") or [])
        add({
            "id": "track-count-mismatch",
            "label": "Track count mismatch",
            "severity": "warning",
            "message": "Deezer was rejected because the local album and Deezer release had different track counts.",
            "details": track_count_details,
        })

    deezer_year = _year_from_metadata(deezer)
    musicbrainz_year = _year_from_metadata(musicbrainz)
    if (
        deezer
        and musicbrainz
        and not musicbrainz_date_only
        and deezer_year
        and musicbrainz_year
        and deezer_year != musicbrainz_year
    ):
        add({
            "id": "conflicting-release-year",
            "label": "Conflicting release year",
            "severity": "warning",
            "message": f"Deezer suggested {deezer_year}, but MusicBrainz suggested {musicbrainz_year}.",
            "details": {"deezerYear": deezer_year, "musicbrainzYear": musicbrainz_year},
        })

    if (
        deezer
        and musicbrainz
        and not musicbrainz_date_only
        and not _providers_substantially_agree(deezer, musicbrainz, before.get("trackCount"))
    ):
        add({
            "id": "provider-disagreement",
            "label": "Provider disagreement",
            "severity": "warning",
            "message": "Providers suggested different release metadata for this album.",
            "details": {
                "localTrackCount": int(before.get("trackCount") or 0) if before.get("trackCount") else None,
                "deezerTrackCount": len(deezer.get("tracks") or []) if isinstance(deezer.get("tracks"), list) else None,
                "musicbrainzTrackCount": len(musicbrainz.get("tracks") or []) if isinstance(musicbrainz.get("tracks"), list) else None,
            },
        })

    if before.get("cover") == "Local low-quality cover" and after.get("cover") == "Local low-quality cover":
        add({
            "id": "low-quality-artwork",
            "label": "Artwork could be higher quality",
            "severity": "warning",
            "message": "The album still uses a low-quality local cover image.",
        })

    artists = {
        _text(track.get("albumartist")) or _text(track.get("artist"))
        for track in group_tracks
        if _text(track.get("albumartist")) or _text(track.get("artist"))
    }
    if len(artists) > 1:
        add({
            "id": "mixed-primary-artists",
            "label": "Different primary artists detected",
            "severity": "danger",
            "message": "Multiple primary artists were detected inside one album group.",
            "details": {"artists": sorted(artist for artist in artists if artist)},
        })

    release_title = _text(after.get("album")) or _text(deezer.get("album") if deezer else None) or _text(musicbrainz.get("album") if musicbrainz else None) or ""
    if RANGE_YEAR_PATTERN.search(release_title) or SUSPICIOUS_TITLE_PATTERN.search(release_title):
        add({
            "id": "suspicious-release-title",
            "label": "Suspicious release title",
            "severity": "warning",
            "message": "The selected release title looks noisy or compilation-like.",
        })
    if "bootleg" in release_title.lower() or "unofficial" in release_title.lower():
        add({
            "id": "unofficial-release",
            "label": "Release may be unofficial",
            "severity": "danger",
            "message": "The selected release looks unofficial or user-uploaded.",
        })

    duplicate_track_details = _duplicate_track_diagnostics(
        group_tracks,
        deezer=deezer,
        musicbrainz=musicbrainz,
    )
    if duplicate_track_details:
        add({
            "id": "duplicate-tracks",
            "label": "Duplicate tracks detected",
            "severity": "warning",
            "message": "Multiple local tracks look duplicated inside this album.",
            "details": duplicate_track_details,
        })

    sequencing_details = _sequencing_diagnostics(
        group_tracks,
        deezer=deezer,
        musicbrainz=musicbrainz,
    )
    if sequencing_details:
        add({
            "id": "broken-sequencing",
            "label": "Track sequencing looks broken",
            "severity": "warning",
            "message": "Track numbering or ordering in the local album looks inconsistent.",
            "details": sequencing_details,
        })

    return suspicious


def _match_reasoning(
    *,
    confidence: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    deezer_reason: str | None,
) -> list[dict[str, str]]:
    reasons = []
    for signal in confidence.get("signals") or []:
        provider = _text(signal.get("provider")) or "metadata"
        status = _text(signal.get("status")) or "info"
        message = _text(signal.get("message"))
        if not message:
            continue
        reasons.append({
            "provider": provider,
            "status": status,
            "message": message,
        })

    if deezer_reason and not any(reason["provider"] == "deezer" and reason["status"] == "rejected" for reason in reasons):
        reasons.append({
            "provider": "deezer",
            "status": "rejected",
            "message": DEEZER_REASON_MESSAGES.get(deezer_reason, "Deezer release was rejected during validation."),
        })

    if before.get("cover") != after.get("cover"):
        reasons.append({
            "provider": "artwork",
            "status": "accepted",
            "message": f"Artwork upgraded from {before.get('cover')} to {after.get('cover')}.",
        })

    return reasons


def _confidence_summary(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    deezer: dict | None,
    musicbrainz: dict | None,
    deezer_reason: str | None,
    metadata_provider: str | None,
    suspicious: list[dict[str, Any]],
    group_tracks: list[dict],
) -> dict[str, Any]:
    winner = deezer if metadata_provider == "deezer" else musicbrainz if metadata_provider == "musicbrainz" else None
    local_titles = _local_track_titles(group_tracks)
    signals = [
        _artist_signal(after, winner, metadata_provider),
        _album_title_signal(after, winner, metadata_provider),
        _track_count_signal(before, winner, metadata_provider),
        _track_title_signal(local_titles, winner, metadata_provider),
        _duration_signal(group_tracks, winner, metadata_provider),
        _year_signal(after, winner, metadata_provider),
        _provider_agreement_signal(before, deezer, musicbrainz, metadata_provider, deezer_reason),
        _release_quality_signal(suspicious, metadata_provider, deezer_reason),
    ]
    filtered_signals = [signal for signal in signals if signal]
    score = max(0, min(100, sum(int(signal["scoreImpact"]) for signal in filtered_signals)))
    suspicious_ids = {_text(item.get("id")) or "" for item in suspicious}
    severe_suspicious_ids = {
        "unofficial-release",
        "suspicious-release-title",
        "mixed-primary-artists",
    }
    structural_suspicious_ids = {
        "duplicate-tracks",
        "broken-sequencing",
        "provider-disagreement",
    }
    if (
        "unofficial-release" in suspicious_ids
        or (suspicious_ids & severe_suspicious_ids and score < 75)
        or (suspicious_ids & structural_suspicious_ids and len(suspicious_ids) >= 2 and score < 60)
    ):
        level = "suspicious"
    elif score >= 90:
        level = "high"
    elif score >= 65:
        level = "medium"
    else:
        level = "low"

    reasons = [_text(signal.get("message")) for signal in filtered_signals if _text(signal.get("message"))]
    if metadata_provider == "musicbrainz" and deezer_reason:
        reasons.append(DEEZER_REASON_MESSAGES.get(deezer_reason, "Fallback was required during provider validation."))
    if not reasons:
        reasons.append("Musorg relied on the strongest available metadata evidence for this release.")

    label = {
        "high": "High confidence",
        "medium": "Medium confidence",
        "low": "Low confidence",
        "suspicious": "Suspicious release",
    }[level]
    return {
        "score": score,
        "level": level,
        "label": label,
        "reasons": reasons,
        "signals": filtered_signals,
    }


def _artist_signal(before: dict[str, Any], winner: dict | None, metadata_provider: str | None) -> dict[str, Any]:
    provider_artist = _provider_artist(winner)
    local_artist = _text(before.get("albumartist")) or _text(before.get("artist"))
    if not provider_artist or not local_artist:
        return {
            "id": "artist-similarity",
            "label": "Artist similarity",
            "provider": metadata_provider or "local",
            "status": "info",
            "scoreImpact": 10 if metadata_provider else 0,
            "message": "Artist comparison relied on the best available metadata.",
        }
    classification = _classify_text_similarity(local_artist, provider_artist)
    impacts = {"exact": 20, "normalized": 16, "fuzzy": 10, "mismatch": 0}
    messages = {
        "exact": "Artist names match exactly.",
        "normalized": "Artist names match after normalization.",
        "fuzzy": "Artist names required fuzzy matching but still align closely.",
        "mismatch": "Artist names do not align cleanly and may need review.",
    }
    return {
        "id": "artist-similarity",
        "label": "Artist similarity",
        "provider": metadata_provider or "local",
        "status": "accepted" if classification in {"exact", "normalized"} else "warning" if classification == "fuzzy" else "rejected",
        "scoreImpact": impacts[classification],
        "message": messages[classification],
    }


def _album_title_signal(before: dict[str, Any], winner: dict | None, metadata_provider: str | None) -> dict[str, Any]:
    provider_title = _provider_title(winner)
    local_title = _text(before.get("album"))
    if not provider_title or not local_title:
        return {
            "id": "album-title-similarity",
            "label": "Album title similarity",
            "provider": metadata_provider or "local",
            "status": "info",
            "scoreImpact": 4 if metadata_provider else 0,
            "message": "Album title comparison used the strongest available metadata.",
        }
    classification = _classify_text_similarity(local_title, provider_title)
    impacts = {"exact": 20, "normalized": 16, "fuzzy": 10, "mismatch": 0}
    messages = {
        "exact": "Album titles match exactly.",
        "normalized": "Album titles match after normalization.",
        "fuzzy": "Album title required fuzzy matching but still aligns closely.",
        "mismatch": "Album title similarity is weak and may indicate a wrong release.",
    }
    return {
        "id": "album-title-similarity",
        "label": "Album title similarity",
        "provider": metadata_provider or "local",
        "status": "accepted" if classification in {"exact", "normalized"} else "warning" if classification == "fuzzy" else "rejected",
        "scoreImpact": impacts[classification],
        "message": messages[classification],
    }


def _track_count_signal(before: dict[str, Any], winner: dict | None, metadata_provider: str | None) -> dict[str, Any]:
    local_count = _int_value(before.get("trackCount"))
    provider_count = len((winner or {}).get("tracks") or [])
    if not local_count or not provider_count:
        return {
            "id": "track-count-agreement",
            "label": "Track count agreement",
            "provider": metadata_provider or "local",
            "status": "info",
            "scoreImpact": 8 if metadata_provider else 0,
            "message": "Track count evidence was incomplete.",
        }
    delta = abs(local_count - provider_count)
    if delta == 0:
        return {
            "id": "track-count-agreement",
            "label": "Track count agreement",
            "provider": metadata_provider or "local",
            "status": "accepted",
            "scoreImpact": 15,
            "message": "Track count matches exactly.",
        }
    if delta == 1:
        return {
            "id": "track-count-agreement",
            "label": "Track count agreement",
            "provider": metadata_provider or "local",
            "status": "warning",
            "scoreImpact": 8,
            "message": "Track count is close but differs by one track.",
        }
    return {
        "id": "track-count-agreement",
        "label": "Track count agreement",
        "provider": metadata_provider or "local",
        "status": "rejected",
        "scoreImpact": 0,
        "message": "Track count does not match the local album.",
    }


def _track_title_signal(local_titles: list[str], winner: dict | None, metadata_provider: str | None) -> dict[str, Any] | None:
    provider_titles = [_text(track.get("title")) or "" for track in (winner or {}).get("tracks") or []]
    score = _sequence_similarity(local_titles, provider_titles)
    if score is None:
        return None
    if score >= 98:
        status = "accepted"
        impact = 15
        message = "Track titles match the local album exactly."
    elif score >= 90:
        status = "accepted"
        impact = 12
        message = "Track titles align strongly with the local album."
    elif score >= 78:
        status = "warning"
        impact = 8
        message = "Track titles required fuzzy matching across the release."
    elif score >= 60:
        status = "warning"
        impact = 4
        message = "Track titles align only partially with the local album."
    else:
        status = "rejected"
        impact = 0
        message = "Track titles do not align well with the local album."
    return {
        "id": "track-title-agreement",
        "label": "Track title agreement",
        "provider": metadata_provider or "local",
        "status": status,
        "scoreImpact": impact,
        "message": message,
    }


def _duration_signal(group_tracks: list[dict], winner: dict | None, metadata_provider: str | None) -> dict[str, Any] | None:
    local_durations = [_float_value(track.get("duration_seconds")) for track in group_tracks]
    provider_durations = [_float_value(track.get("duration_seconds")) for track in (winner or {}).get("tracks") or []]
    if not local_durations or not provider_durations or any(value is None for value in local_durations + provider_durations):
        return None
    local_values = [value for value in local_durations if value is not None]
    provider_values = [value for value in provider_durations if value is not None]
    if len(local_values) != len(provider_values) or not local_values:
        return None
    total_delta = abs(sum(local_values) - sum(provider_values))
    per_track_delta = sum(abs(left - right) for left, right in zip(local_values, provider_values)) / len(local_values)
    if total_delta <= 8 and per_track_delta <= 2:
        status = "accepted"
        impact = 10
        message = "Track durations align closely with the local album."
    elif total_delta <= 20 and per_track_delta <= 5:
        status = "warning"
        impact = 5
        message = "Track durations are close, but not exact."
    else:
        status = "rejected"
        impact = 0
        message = "Track durations differ noticeably from the local album."
    return {
        "id": "duration-agreement",
        "label": "Duration agreement",
        "provider": metadata_provider or "local",
        "status": status,
        "scoreImpact": impact,
        "message": message,
    }


def _year_signal(before: dict[str, Any], winner: dict | None, metadata_provider: str | None) -> dict[str, Any]:
    local_year = _year_to_int(before.get("date"))
    provider_year = _year_from_metadata(winner)
    provider_year_int = _year_to_int(provider_year)
    if not provider_year_int:
        return {
            "id": "year-consistency",
            "label": "Release year consistency",
            "provider": metadata_provider or "local",
            "status": "info",
            "scoreImpact": 0,
            "message": "Release year evidence was limited.",
        }
    if not local_year:
        return {
            "id": "year-consistency",
            "label": "Release year consistency",
            "provider": metadata_provider or "local",
            "status": "accepted",
            "scoreImpact": 6,
            "message": "A release year was resolved from provider metadata.",
        }
    delta = abs(local_year - provider_year_int)
    if delta == 0:
        return {
            "id": "year-consistency",
            "label": "Release year consistency",
            "provider": metadata_provider or "local",
            "status": "accepted",
            "scoreImpact": 10,
            "message": "Release year matches exactly.",
        }
    if delta == 1:
        return {
            "id": "year-consistency",
            "label": "Release year consistency",
            "provider": metadata_provider or "local",
            "status": "warning",
            "scoreImpact": 6,
            "message": "Release year differs by one year.",
        }
    return {
        "id": "year-consistency",
        "label": "Release year consistency",
        "provider": metadata_provider or "local",
        "status": "warning",
        "scoreImpact": 2,
        "message": "Release year conflicts with the local metadata.",
    }


def _provider_agreement_signal(
    before: dict[str, Any],
    deezer: dict | None,
    musicbrainz: dict | None,
    metadata_provider: str | None,
    deezer_reason: str | None,
) -> dict[str, Any]:
    local_track_count = _int_value(before.get("trackCount"))
    if deezer and musicbrainz:
        if _is_date_only_provider_metadata(musicbrainz):
            return {
                "id": "provider-agreement",
                "label": "Provider agreement",
                "provider": "providers",
                "status": "accepted",
                "scoreImpact": 10,
                "message": "Deezer matched the release and MusicBrainz verified the original release date.",
            }
        if _providers_substantially_agree(deezer, musicbrainz, local_track_count):
            return {
                "id": "provider-agreement",
                "label": "Provider agreement",
                "provider": "providers",
                "status": "accepted",
                "scoreImpact": 10,
                "message": "Deezer and MusicBrainz agree on the matched release.",
            }
        return {
            "id": "provider-agreement",
            "label": "Provider agreement",
            "provider": "providers",
            "status": "warning",
            "scoreImpact": 2,
            "message": "Providers disagree on important release details.",
        }
    if metadata_provider == "deezer":
        return {
            "id": "provider-agreement",
            "label": "Provider agreement",
            "provider": "deezer",
            "status": "accepted",
            "scoreImpact": 8,
            "message": "Deezer supplied the strongest complete release match.",
        }
    if metadata_provider == "musicbrainz":
        return {
            "id": "provider-agreement",
            "label": "Provider agreement",
            "provider": "musicbrainz",
            "status": "warning" if deezer_reason else "accepted",
            "scoreImpact": 12 if deezer_reason else 6,
            "message": "MusicBrainz provided the best available release after provider checks.",
        }
    return {
        "id": "provider-agreement",
        "label": "Provider agreement",
        "provider": "local",
        "status": "warning",
        "scoreImpact": 0,
        "message": "Musorg relied on local metadata because no provider fully matched.",
    }


def _release_quality_signal(
    suspicious: list[dict[str, Any]],
    metadata_provider: str | None,
    deezer_reason: str | None,
) -> dict[str, Any]:
    suspicious_ids = {_text(item.get("id")) or "" for item in suspicious}
    penalty = 0
    if "provider-disagreement" in suspicious_ids:
        penalty += 4
    if "suspicious-release-title" in suspicious_ids:
        penalty += 6
    if "unofficial-release" in suspicious_ids:
        penalty += 10
    if "duplicate-tracks" in suspicious_ids:
        penalty += 4
    if "broken-sequencing" in suspicious_ids:
        penalty += 4
    if "mixed-primary-artists" in suspicious_ids:
        penalty += 6
    if deezer_reason in {"invalid_payload", "partial_payload"}:
        penalty += 4
    impact = max(0, 10 - penalty)
    if penalty == 0:
        status = "accepted"
        message = "Release quality signals look clean."
    elif penalty <= 6:
        status = "warning"
        message = "Some release-quality signals still need review."
    else:
        status = "rejected"
        message = "Release quality signals look suspicious."
    return {
        "id": "release-quality",
        "label": "Release quality heuristics",
        "provider": metadata_provider or "local",
        "status": status,
        "scoreImpact": impact,
        "message": message,
    }


def _providers_substantially_agree(deezer: dict | None, musicbrainz: dict | None, local_track_count: int | None) -> bool:
    if not deezer or not musicbrainz:
        return False
    if _is_date_only_provider_metadata(musicbrainz):
        return True
    artist_match = _classify_text_similarity(_provider_artist(deezer), _provider_artist(musicbrainz)) in {"exact", "normalized"}
    title_match = _classify_text_similarity(_provider_title(deezer), _provider_title(musicbrainz)) in {"exact", "normalized"}
    deezer_year = _year_to_int(_year_from_metadata(deezer))
    musicbrainz_year = _year_to_int(_year_from_metadata(musicbrainz))
    year_match = not deezer_year or not musicbrainz_year or abs(deezer_year - musicbrainz_year) <= 1
    deezer_count = len(deezer.get("tracks") or [])
    musicbrainz_count = len(musicbrainz.get("tracks") or [])
    count_match = deezer_count == musicbrainz_count and (not local_track_count or deezer_count == local_track_count)
    return artist_match and title_match and year_match and count_match


def _provider_artist(metadata: dict | None) -> str | None:
    return _text((metadata or {}).get("albumartist")) or _text((metadata or {}).get("artist"))


def _provider_title(metadata: dict | None) -> str | None:
    return _text((metadata or {}).get("album"))


def _is_date_only_provider_metadata(metadata: dict | None) -> bool:
    if not isinstance(metadata, dict) or not metadata:
        return False
    if not (_text(metadata.get("date_iso")) or _text(metadata.get("date"))):
        return False

    non_date_fields = (
        _text(metadata.get("albumartist")),
        _text(metadata.get("artist")),
        _text(metadata.get("album")),
        _text(metadata.get("cover")),
        _text(metadata.get("releasetype")),
    )
    if any(non_date_fields):
        return False

    tracks = metadata.get("tracks")
    if isinstance(tracks, list) and tracks:
        return False

    return True


def _local_track_titles(group_tracks: list[dict]) -> list[str]:
    ordered = sorted(
        group_tracks,
        key=lambda track: (
            _int_value(track.get("discnumber")),
            _int_value(track.get("tracknumber")),
            _text(track.get("title")) or "",
        ),
    )
    return [_text(track.get("title")) or "" for track in ordered if _text(track.get("title"))]


def _sequence_similarity(left_titles: list[str], right_titles: list[str]) -> float | None:
    left = [_normalize_lookup_text(title) for title in left_titles if _normalize_lookup_text(title)]
    right = [_normalize_lookup_text(title) for title in right_titles if _normalize_lookup_text(title)]
    if not left or not right or len(left) != len(right):
        return None
    ratios = [int(round(SequenceMatcher(None, l, r).ratio() * 100)) for l, r in zip(left, right)]
    return sum(ratios) / len(ratios)


def _classify_text_similarity(left: str | None, right: str | None) -> str:
    if not left or not right:
        return "mismatch"
    left_text = left.strip()
    right_text = right.strip()
    if left_text == right_text:
        return "exact"
    normalized_left = _normalize_lookup_text(left_text)
    normalized_right = _normalize_lookup_text(right_text)
    if normalized_left and normalized_left == normalized_right:
        return "normalized"
    ratio = int(round(SequenceMatcher(None, normalized_left, normalized_right).ratio() * 100))
    if ratio >= 88:
        return "fuzzy"
    return "mismatch"


def _normalize_lookup_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join("".join(char.lower() if char.isalnum() else " " for char in str(value)).split())


def _provider_duplicate_title_signatures(*providers: dict | None) -> set[str]:
    duplicate_titles: set[str] = set()
    for provider in providers:
        provider_tracks = (provider or {}).get("tracks") or []
        counts: dict[str, int] = {}
        for track in provider_tracks:
            if not isinstance(track, dict):
                continue
            normalized = _normalize_lookup_text(track.get("title"))
            if not normalized:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
        duplicate_titles.update(title for title, count in counts.items() if count > 1)
    return duplicate_titles


def _best_provider_sequence_score(group_tracks: list[dict], *providers: dict | None) -> float | None:
    local_titles = _local_track_titles(group_tracks)
    scores = []
    for provider in providers:
        provider_titles = [
            _text(track.get("title")) or ""
            for track in (provider or {}).get("tracks") or []
            if isinstance(track, dict)
        ]
        score = _sequence_similarity(local_titles, provider_titles)
        if score is not None:
            scores.append(score)
    return max(scores) if scores else None


def _duplicate_track_diagnostics(
    group_tracks: list[dict],
    *,
    deezer: dict | None = None,
    musicbrainz: dict | None = None,
) -> dict[str, Any] | None:
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    provider_duplicate_titles = _provider_duplicate_title_signatures(deezer, musicbrainz)
    for index, track in enumerate(group_tracks, start=1):
        normalized = _normalize_lookup_text(track.get("title"))
        if not normalized:
            continue
        bucket = seen.setdefault(normalized, {
            "title": _text(track.get("title")) or normalized,
            "positions": [],
            "slots": [],
        })
        bucket["positions"].append(index)
        bucket["slots"].append((
            _int_value(track.get("discnumber")) or 1,
            _int_value(track.get("tracknumber")) or 0,
        ))
    for normalized, bucket in seen.items():
        positions = bucket["positions"]
        if len(positions) < 2:
            continue
        slots = [slot for slot in bucket["slots"] if slot[1] > 0]
        has_duplicate_slot = len(slots) > len(set(slots))
        if not has_duplicate_slot:
            continue
        if normalized in provider_duplicate_titles:
            continue
        duplicates.append({
            "title": bucket["title"],
            "positions": positions,
            "reason": "duplicate_slot",
        })
    if not duplicates:
        return None
    return {"duplicateTitles": duplicates[:3]}


def _sequencing_diagnostics(
    group_tracks: list[dict],
    *,
    deezer: dict | None = None,
    musicbrainz: dict | None = None,
) -> dict[str, Any] | None:
    details: dict[str, Any] = {}
    ordered_tracks = list(group_tracks)
    canonical_tracks = _canonical_sequencing_rows(group_tracks)
    provider_sequence_score = _best_provider_sequence_score(group_tracks, deezer, musicbrainz)
    provider_supports_soft_warning = provider_sequence_score is not None and provider_sequence_score < 98
    missing_numbers = [
        index
        for index, track in enumerate(ordered_tracks, start=1)
        if not _int_value(track.get("tracknumber"))
    ]
    if missing_numbers and provider_supports_soft_warning:
        details["missingTrackNumbers"] = missing_numbers[:4]

    invalid_disc_numbers = [
        row["position"]
        for row in canonical_tracks
        if row["rawDiscText"] and row["discnumber"] <= 0
    ]
    if invalid_disc_numbers:
        details["invalidDiscNumbers"] = invalid_disc_numbers[:4]

    multi_disc_expected = _multi_disc_expected(canonical_tracks, deezer=deezer, musicbrainz=musicbrainz)
    missing_disc_numbers = [
        row["position"]
        for row in canonical_tracks
        if multi_disc_expected and not row["hasDiscNumber"]
    ]
    if missing_disc_numbers:
        details["missingDiscNumbers"] = missing_disc_numbers[:4]

    duplicate_numbers: list[dict[str, Any]] = []
    by_disc_and_track: dict[tuple[int, int], list[int]] = {}
    for row in canonical_tracks:
        track_number = row["tracknumber"]
        if not track_number:
            continue
        disc_number = row["discnumber"] or 1
        by_disc_and_track.setdefault((disc_number, track_number), []).append(row["position"])
    for (disc_number, track_number), positions in by_disc_and_track.items():
        if len(positions) < 2:
            continue
        duplicate_numbers.append({
            "disc": disc_number,
            "track": track_number,
            "positions": positions[:4],
        })
    if duplicate_numbers:
        details["duplicateTrackNumbers"] = duplicate_numbers[:3]

    first_jump: dict[str, Any] | None = None
    first_reverse: dict[str, Any] | None = None
    disc_sequences: dict[int, list[tuple[int, int]]] = {}
    for row in canonical_tracks:
        disc_number = row["discnumber"] or 1
        track_number = row["tracknumber"]
        if track_number:
            disc_sequences.setdefault(disc_number, []).append((row["position"], track_number))
    for disc_number, values in sorted(disc_sequences.items()):
        previous_track: int | None = None
        previous_index: int | None = None
        for index, track_number in values:
            if previous_track is None:
                previous_track = track_number
                previous_index = index
                continue
            if track_number == previous_track:
                previous_track = track_number
                previous_index = index
                continue
            if track_number < previous_track and first_reverse is None:
                first_reverse = {
                    "disc": disc_number,
                    "previousTrack": previous_track,
                    "currentTrack": track_number,
                    "position": index,
                    "previousPosition": previous_index,
                }
            elif track_number > previous_track + 1 and first_jump is None:
                first_jump = {
                    "disc": disc_number,
                    "from": previous_track,
                    "to": track_number,
                    "position": index,
                }
            previous_track = track_number
            previous_index = index
    if first_jump and provider_supports_soft_warning:
        details["firstSequenceJump"] = first_jump
    if first_reverse and provider_supports_soft_warning:
        details["firstOutOfOrderPair"] = first_reverse

    normalized_discs = [row["discnumber"] for row in canonical_tracks if row["discnumber"] > 0]
    unique_discs = sorted(set(normalized_discs))
    disc_structure_invalid = (
        bool(invalid_disc_numbers)
        or bool(missing_disc_numbers)
        or bool(duplicate_numbers)
        or (bool(unique_discs) and unique_discs != list(range(1, len(unique_discs) + 1)))
    )
    if disc_structure_invalid:
        details["discNumbers"] = unique_discs

    affected_positions = _sequencing_affected_positions(
        missing_numbers=missing_numbers if provider_supports_soft_warning else [],
        invalid_disc_numbers=invalid_disc_numbers,
        missing_disc_numbers=missing_disc_numbers,
        duplicate_numbers=duplicate_numbers,
        first_jump=first_jump if provider_supports_soft_warning else None,
        first_reverse=first_reverse if provider_supports_soft_warning else None,
        unique_discs=unique_discs,
        canonical_tracks=canonical_tracks,
    )
    failing_rule = _sequencing_failing_rule(
        invalid_disc_numbers=invalid_disc_numbers,
        missing_disc_numbers=missing_disc_numbers,
        duplicate_numbers=duplicate_numbers,
        missing_numbers=missing_numbers if provider_supports_soft_warning else [],
        first_jump=first_jump if provider_supports_soft_warning else None,
        first_reverse=first_reverse if provider_supports_soft_warning else None,
        unique_discs=unique_discs,
    )
    if failing_rule:
        details["failingRule"] = failing_rule

    if affected_positions:
        details["affectedTracks"] = _affected_track_details(
            canonical_tracks,
            affected_positions,
            deezer=deezer,
            musicbrainz=musicbrainz,
        )

    if (failing_rule or affected_positions) and canonical_tracks:
        details["canonicalOrder"] = [
            {
                "position": row["position"],
                "disc": row["discnumber"] or 1,
                "track": row["tracknumber"] or None,
                "title": row["title"],
                "path": row["path"],
            }
            for row in canonical_tracks[:12]
        ]

    actionable_keys = {
        "missingTrackNumbers",
        "invalidDiscNumbers",
        "missingDiscNumbers",
        "duplicateTrackNumbers",
        "firstSequenceJump",
        "firstOutOfOrderPair",
        "discNumbers",
        "failingRule",
    }
    return details if actionable_keys & set(details) else None


def _canonical_sequencing_rows(group_tracks: list[dict]) -> list[dict[str, Any]]:
    rows = []
    for position, track in enumerate(group_tracks, start=1):
        raw_disc = _text(track.get("discnumber"))
        raw_track = _text(track.get("tracknumber"))
        discnumber = _int_value(track.get("discnumber"))
        tracknumber = _int_value(track.get("tracknumber"))
        rows.append({
            "position": position,
            "discnumber": discnumber,
            "tracknumber": tracknumber,
            "hasDiscNumber": bool(raw_disc and discnumber > 0),
            "hasTrackNumber": bool(raw_track and tracknumber > 0),
            "rawDiscText": raw_disc,
            "rawTrackText": raw_track,
            "title": _text(track.get("title")) or f"Track {position}",
            "path": _text(track.get("path")) or "",
        })

    return sorted(
        rows,
        key=lambda row: (
            row["discnumber"] if row["discnumber"] > 0 else 1,
            0 if row["tracknumber"] > 0 else 1,
            row["tracknumber"] if row["tracknumber"] > 0 else 10**9,
            _normalize_lookup_text(row["title"]),
            row["path"].lower(),
            row["position"],
        ),
    )


def _multi_disc_expected(
    canonical_tracks: list[dict[str, Any]],
    *,
    deezer: dict | None,
    musicbrainz: dict | None,
) -> bool:
    if any(row["discnumber"] > 1 for row in canonical_tracks):
        return True
    for metadata in (deezer, musicbrainz):
        provider_tracks = (metadata or {}).get("tracks") or []
        if any(_int_value(track.get("discnumber")) > 1 for track in provider_tracks if isinstance(track, dict)):
            return True
    return False


def _sequencing_failing_rule(
    *,
    invalid_disc_numbers: list[int],
    missing_disc_numbers: list[int],
    duplicate_numbers: list[dict[str, Any]],
    missing_numbers: list[int],
    first_jump: dict[str, Any] | None,
    first_reverse: dict[str, Any] | None,
    unique_discs: list[int],
) -> str | None:
    if invalid_disc_numbers:
        return "invalid_disc_numbers"
    if missing_disc_numbers:
        return "missing_disc_numbers"
    if duplicate_numbers:
        return "duplicate_disc_track_pair"
    if missing_numbers:
        return "missing_track_numbers"
    if first_reverse:
        return "track_order_reverse"
    if first_jump:
        return "track_sequence_jump"
    if unique_discs and unique_discs != list(range(1, len(unique_discs) + 1)):
        return "non_contiguous_disc_numbers"
    return None


def _sequencing_affected_positions(
    *,
    missing_numbers: list[int],
    invalid_disc_numbers: list[int],
    missing_disc_numbers: list[int],
    duplicate_numbers: list[dict[str, Any]],
    first_jump: dict[str, Any] | None,
    first_reverse: dict[str, Any] | None,
    unique_discs: list[int],
    canonical_tracks: list[dict[str, Any]],
) -> list[int]:
    affected = [
        *missing_numbers[:4],
        *invalid_disc_numbers[:4],
        *missing_disc_numbers[:4],
    ]
    for duplicate in duplicate_numbers[:2]:
        positions = duplicate.get("positions") or []
        if isinstance(positions, list):
            affected.extend(int(position) for position in positions[:4] if position)
    if first_jump and first_jump.get("position"):
        affected.append(int(first_jump["position"]))
    if first_reverse:
        if first_reverse.get("previousPosition"):
            affected.append(int(first_reverse["previousPosition"]))
        if first_reverse.get("position"):
            affected.append(int(first_reverse["position"]))
    if unique_discs and unique_discs != list(range(1, len(unique_discs) + 1)):
        affected.extend(row["position"] for row in canonical_tracks[: min(len(canonical_tracks), 4)])
    return sorted({position for position in affected if position > 0})[:6]


def _affected_track_details(
    canonical_tracks: list[dict[str, Any]],
    positions: list[int],
    *,
    deezer: dict | None,
    musicbrainz: dict | None,
) -> list[dict[str, Any]]:
    rows_by_position = {row["position"]: row for row in canonical_tracks}
    return [
        {
            "position": position,
            "title": rows_by_position[position]["title"],
            "path": rows_by_position[position]["path"],
            "local": {
                "disc": rows_by_position[position]["discnumber"] or None,
                "track": rows_by_position[position]["tracknumber"] or None,
            },
            "providerValues": _provider_values_for_row(rows_by_position[position], deezer=deezer, musicbrainz=musicbrainz),
        }
        for position in positions
        if position in rows_by_position
    ]


def _provider_values_for_row(
    row: dict[str, Any],
    *,
    deezer: dict | None,
    musicbrainz: dict | None,
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for provider_name, metadata in (("deezer", deezer), ("musicbrainz", musicbrainz)):
        provider_track = _match_provider_track(row, metadata)
        if not provider_track:
            continue
        values[provider_name] = {
            "disc": _int_value(provider_track.get("discnumber")) or None,
            "track": _int_value(provider_track.get("tracknumber")) or None,
            "title": _text(provider_track.get("title")),
        }
    return values


def _match_provider_track(row: dict[str, Any], metadata: dict | None) -> dict[str, Any] | None:
    provider_tracks = (metadata or {}).get("tracks") or []
    if not isinstance(provider_tracks, list):
        return None
    normalized_title = _normalize_lookup_text(row["title"])
    if not normalized_title:
        return None
    title_matches = [
        track
        for track in provider_tracks
        if isinstance(track, dict) and _normalize_lookup_text(_text(track.get("title"))) == normalized_title
    ]
    if len(title_matches) == 1:
        return title_matches[0]
    if len(title_matches) > 1:
        for track in title_matches:
            if (
                _int_value(track.get("discnumber")) == row["discnumber"]
                and _int_value(track.get("tracknumber")) == row["tracknumber"]
            ):
                return track
        for track in title_matches:
            if _int_value(track.get("tracknumber")) == row["tracknumber"]:
                return track
        return title_matches[0]
    return None


def _rejected_providers(deezer_reason: str | None) -> list[dict[str, str]]:
    if not deezer_reason:
        return []
    return [{
        "provider": "deezer",
        "reason": deezer_reason,
        "message": DEEZER_REASON_MESSAGES.get(deezer_reason, "Deezer release was rejected."),
    }]


def _auto_fix_diagnostics(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    provider_decisions: dict[str, Any],
    confidence: dict[str, Any],
    suspicious: list[dict[str, Any]],
    cleanup_actions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    suspicious_by_id = {
        _text(item.get("id")) or "": item
        for item in suspicious
        if _text(item.get("id"))
    }
    suspicious_ids = set(suspicious_by_id)
    provider = _text(provider_decisions.get("metadataProvider"))
    confidence_level = _text(confidence.get("level")) or "low"
    diagnostics: dict[str, dict[str, Any]] = {}

    if "broken-sequencing" in suspicious_ids or "duplicate-tracks" in suspicious_ids or "track-count-mismatch" in suspicious_ids:
        skip_reason = None
        blocking_signals: list[str] = []
        trusted_inputs = False
        if "provider-disagreement" in suspicious_ids:
            skip_reason = "provider_conflict"
            blocking_signals.extend(_provider_disagreement_signals(suspicious_by_id.get("provider-disagreement")))
        elif "track-count-mismatch" in suspicious_ids:
            skip_reason = "release_structure_mismatch"
            blocking_signals.extend(_track_count_blocking_signals(suspicious_by_id.get("track-count-mismatch")))
        elif confidence_level in {"low", "suspicious"}:
            skip_reason = "confidence_too_low"
            blocking_signals.append(f"Metadata confidence: {confidence_level}.")
        elif not provider:
            skip_reason = "provider_data_unavailable"
            blocking_signals.append("No trusted metadata provider won release selection.")
            blocking_signals.extend(_provider_rejection_signals(provider_decisions))
        else:
            trusted_inputs = True

        diagnostics["sequencing"] = {
            "issueSignature": _issue_signature(
                "sequencing",
                suspicious_by_id.get("broken-sequencing"),
                suspicious_by_id.get("duplicate-tracks"),
                suspicious_by_id.get("track-count-mismatch"),
                {"provider": provider, "confidence": confidence_level},
            ),
            "trustedProviderInputsAvailable": trusted_inputs,
            "skipReason": skip_reason,
            "blockingSignals": blocking_signals[:4],
        }

    if "low-quality-artwork" in suspicious_ids:
        diagnostics["artwork"] = {
            "issueSignature": _issue_signature("artwork", {"before": before.get("cover"), "after": after.get("cover")}),
            "trustedProviderInputsAvailable": bool(provider),
            "skipReason": None,
            "blockingSignals": [],
        }

    metadata_issue_ids = suspicious_ids & {"provider-disagreement", "conflicting-release-year", "suspicious-release-title", "runtime-mismatch"}
    if metadata_issue_ids or any(action.get("kind") in {"artist", "albumartist", "album", "date", "genre"} for action in cleanup_actions):
        skip_reason = "confidence_too_low" if confidence_level in {"low", "suspicious"} else "provider_conflict" if "provider-disagreement" in suspicious_ids else None
        blocking_signals: list[str] = []
        if skip_reason == "provider_conflict":
            blocking_signals.extend(_provider_disagreement_signals(suspicious_by_id.get("provider-disagreement")))
        elif skip_reason == "confidence_too_low":
            blocking_signals.append(f"Metadata confidence: {confidence_level}.")
        diagnostics["metadata"] = {
            "issueSignature": _issue_signature("metadata", sorted(metadata_issue_ids), {"confidence": confidence_level}, cleanup_actions),
            "trustedProviderInputsAvailable": bool(provider and confidence_level in {"high", "medium"}),
            "skipReason": skip_reason,
            "blockingSignals": blocking_signals[:4],
        }

    return diagnostics


def _issue_signature(category: str, *parts: Any) -> str:
    normalized = [_stable_signature_value(part) for part in parts]
    return f"{category}:{'|'.join(normalized)}"


def _stable_signature_value(value: Any) -> str:
    if isinstance(value, dict):
        return ",".join(f"{key}={_stable_signature_value(value[key])}" for key in sorted(value))
    if isinstance(value, list):
        return "[" + ",".join(_stable_signature_value(item) for item in value) + "]"
    return str(value or "")


def _provider_disagreement_signals(item: dict[str, Any] | None) -> list[str]:
    details = (item or {}).get("details") if isinstance(item, dict) else {}
    if not isinstance(details, dict):
        return []
    signals: list[str] = []
    local = details.get("localTrackCount")
    deezer = details.get("deezerTrackCount")
    musicbrainz = details.get("musicbrainzTrackCount")
    if musicbrainz not in (None, ""):
        signals.append(f"MusicBrainz track count: {musicbrainz}")
    if deezer not in (None, ""):
        signals.append(f"Deezer track count: {deezer}")
    if local not in (None, ""):
        signals.append(f"Local track count: {local}")
    if signals:
        signals.append("Provider disagreement prevents safe renumbering.")
    return signals[:4]


def _track_count_blocking_signals(item: dict[str, Any] | None) -> list[str]:
    details = (item or {}).get("details") if isinstance(item, dict) else {}
    if not isinstance(details, dict):
        return []
    signals: list[str] = []
    if details.get("providerTrackCount") not in (None, ""):
        signals.append(f"Provider track count: {details.get('providerTrackCount')}")
    if details.get("localTrackCount") not in (None, ""):
        signals.append(f"Local track count: {details.get('localTrackCount')}")
    if signals:
        signals.append("Release structure mismatch prevents safe renumbering.")
    return signals[:4]


def _provider_rejection_signals(provider_decisions: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for item in provider_decisions.get("rejectedProviders") or []:
        if not isinstance(item, dict):
            continue
        provider = _text(item.get("provider")) or "Provider"
        message = _text(item.get("message")) or _text(item.get("reason"))
        if message:
            signals.append(f"{provider}: {message}")
        if len(signals) >= 3:
            break
    return signals


def _deezer_reason(resolved: dict[str, Any]) -> str | None:
    deezer_result = resolved.get("deezer_result")
    if isinstance(deezer_result, dict) and not deezer_result.get("success", True):
        return _text(deezer_result.get("reason"))
    return None


def _metadata_provider(deezer: dict | None, musicbrainz: dict | None) -> str | None:
    if deezer:
        return "deezer"
    if musicbrainz:
        return "musicbrainz"
    return None


def _artwork_provider(before: dict[str, Any], deezer: dict | None, musicbrainz: dict | None) -> str | None:
    if deezer and _text(deezer.get("cover")):
        return "deezer"
    if musicbrainz and _text(musicbrainz.get("cover")):
        return "musicbrainz"
    if before.get("cover") not in ("No cover", "Local low-quality cover"):
        return "local"
    return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _track_year(track: dict) -> str:
    date_iso = _text(track.get("release_date_iso"))
    if date_iso and len(date_iso) >= 4 and date_iso[:4].isdigit():
        return date_iso[:4]
    date = _text(track.get("date"))
    if date and len(date) >= 4:
        if date[:4].isdigit():
            return date[:4]
        if date[-4:].isdigit():
            return date[-4:]
    return ""


def _year_to_int(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        return None
    return int(match.group(0))


def _year_from_metadata(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    date_iso = _text(metadata.get("date_iso"))
    if date_iso and len(date_iso) >= 4 and date_iso[:4].isdigit():
        return date_iso[:4]
    date = _text(metadata.get("date"))
    if date and len(date) >= 4 and date[-4:].isdigit():
        return date[-4:]
    return None


def _cover_summary(track: dict) -> str:
    cover = _text(track.get("cover"))
    if not cover:
        return "No cover"
    if cover.startswith("http"):
        return "Provider artwork"

    width = _int_value(track.get("cover_width"))
    height = _int_value(track.get("cover_height"))
    if width and height and min(width, height) < 1000:
        return "Local low-quality cover"
    return "Local cover"


def _genre_value(track: dict) -> str:
    genre = _text(track.get("genre"))
    return genre or "Unknown"
