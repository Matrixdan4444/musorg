from __future__ import annotations


def suspicious_audio_copy(status: str) -> tuple[str, str]:
    if status == "likely":
        return ("Likely lossy source", "Likely sourced from lossy material.")
    if status == "suspicious":
        return ("Suspicious audio", "Lossless encoding is present, but the audio profile needs a closer review.")
    return ("Possible lossy source", "Possibly sourced from lossy material.")


def best_version_copy() -> tuple[str, str]:
    return ("Best version", "Recommended as primary version.")


def better_version_copy() -> tuple[str, str]:
    return ("Better version available", "A stronger version already exists in this release family.")


def exact_duplicate_copy() -> tuple[str, str]:
    return ("Exact duplicate", "This version duplicates another owned copy.")


def near_duplicate_copy() -> tuple[str, str]:
    return ("Near duplicate", "This version is very close to another owned copy.")


def possible_related_copy() -> tuple[str, str]:
    return ("Possible related release", "This release looks related, but the match stays below the merge threshold.")


def metadata_complete_copy() -> tuple[str, str]:
    return ("Metadata complete", "Metadata appears complete.")


def edition_variant_copy(label: str) -> tuple[str, str]:
    return ("Edition variant", f"This appears to be a {label.lower()} variant.")


def multiple_variants_copy(count: int) -> tuple[str, str]:
    return ("Multiple variants", f"You own {count} variants in this release family.")


def remaster_family_copy() -> tuple[str, str]:
    return ("Remaster variants", "This release family includes both remaster and non-remaster versions.")


def lossy_lossless_family_copy() -> tuple[str, str]:
    return ("Lossy and lossless copies", "Lossy and lossless copies coexist in this release family.")
