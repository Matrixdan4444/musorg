from __future__ import annotations


def keep_primary_copy() -> tuple[str, str]:
    return "Keep Recommended", "Keep this as the primary version."


def archive_duplicate_copy() -> tuple[str, str]:
    return "Archive Recommended", "A stronger duplicate already exists in this family."


def replace_better_copy() -> tuple[str, str]:
    return "Better Version Available", "A stronger version already exists in this release family."


def minor_artwork_cleanup_copy() -> tuple[str, str]:
    return "Minor artwork cleanup", "Artwork resolution is missing or lower quality than another available source."


def minor_metadata_cleanup_copy() -> tuple[str, str]:
    return "Minor metadata cleanup", "Some album or artist tags were normalized, but metadata confidence is not fully settled."


def metadata_review_copy() -> tuple[str, str]:
    return "Metadata review", "Providers disagreed on important release details."


def sequencing_review_copy() -> tuple[str, str]:
    return "Sequencing review", "Track numbering or ordering appears inconsistent."


def release_structure_review_copy() -> tuple[str, str]:
    return "Release structure review", "Track structure differs from the expected release."


def release_quality_review_copy() -> tuple[str, str]:
    return "Release quality review", "Release details look inconsistent and should be reviewed."


def compound_cleanup_copy(categories: set[str], important: bool = False) -> tuple[str, str]:
    ordered_labels = [
        label
        for category, label in (
            ("metadata", "metadata"),
            ("artwork", "artwork"),
            ("sequencing", "track structure"),
            ("release_quality", "release details"),
        )
        if category in categories
    ]
    if len(ordered_labels) > 1:
        joined = ", ".join(ordered_labels[:-1]) + f" and {ordered_labels[-1]}"
    else:
        joined = ordered_labels[0] if ordered_labels else "release details"
    if important:
        return "Release review", f"{joined.capitalize()} need review before this version can be trusted."
    if categories == {"artwork"}:
        return minor_artwork_cleanup_copy()
    if categories == {"metadata"}:
        return minor_metadata_cleanup_copy()
    if categories == {"sequencing"}:
        return sequencing_review_copy()
    if categories == {"release_quality"}:
        return release_quality_review_copy()
    return "Minor release cleanup", f"{joined.capitalize()} still have follow-up cleanup available."


def processing_needed_copy(state: str | None) -> tuple[str, str]:
    if state == "failed":
        return "Retry Cleanup", "Cleanup failed and should be retried."
    if state == "missing_output":
        return "Processing Needed", "Processed output is missing and should be rebuilt."
    return "Processing Needed", "This album still needs cleanup processing."


def review_audio_copy(status: str) -> tuple[str, str]:
    if status == "suspicious":
        return "Audio Review Needed", "Audio provenance should be reviewed before trusting this release."
    if status == "likely":
        return "Audio Review Needed", "This release likely came from a lossy source and should be reviewed."
    return "Audio Review Needed", "This release may need audio review."


def review_duplicate_copy() -> tuple[str, str]:
    return "Duplicate Review", "This release looks close to another version and should be compared manually."


def family_duplicate_copy(count: int) -> tuple[str, str]:
    return "Family Cleanup Recommended", f"{count} lower-quality releases were detected in this family."


def collection_priority_copy(title: str, count: int) -> str:
    if count <= 1:
        return title
    return f"{title} ({count})"
