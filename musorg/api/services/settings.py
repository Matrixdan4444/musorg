from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import HTTPException

from musorg.api.schemas.music import LibraryPickerResponse, LibrarySettingsResponse
from musorg.filesystem.naming import (
    filename_compatibility_settings_to_api,
    normalize_filename_compatibility_settings,
    normalize_output_format_settings,
    output_format_settings_to_api,
)
from musorg.filesystem.tagging import normalize_metadata_preservation_settings
from musorg.core.smart_actions.action_rules import (
    duplicate_handling_settings_to_api,
    normalize_duplicate_handling_settings,
)


def _default_settings_dir() -> Path:
    return Path.home() / ".musorg"


def _settings_dir() -> Path:
    configured = (os.environ.get("MUSORG_SETTINGS_DIR") or "").strip()
    return Path(configured).expanduser().resolve(strict=False) if configured else _default_settings_dir()


def _settings_path() -> Path:
    configured = (os.environ.get("MUSORG_SETTINGS_PATH") or "").strip()
    return Path(configured).expanduser().resolve(strict=False) if configured else _settings_dir() / "settings.json"


def _settings_runtime_isolated() -> bool:
    return bool((os.environ.get("MUSORG_SETTINGS_PATH") or "").strip() or (os.environ.get("MUSORG_SETTINGS_DIR") or "").strip())


def _emit_settings_diagnostic(message: str) -> None:
    print(f"[DEV MODE] {message}")


def get_effective_library_root() -> str:
    env_override = (os.environ.get("MUSORG_LIBRARY_PATH") or "").strip()
    if env_override:
        return _normalize_path(env_override)

    settings = _read_settings()
    library_root = str(settings.get("library_root") or "").strip()
    return _normalize_path(library_root) if library_root else ""


def get_effective_output_root() -> str:
    settings = _read_settings()
    output_root = str(settings.get("output_root") or "").strip()
    return _normalize_path(output_root) if output_root else ""


def is_developer_mode_enabled() -> bool:
    settings = _read_settings()
    return bool(settings.get("developer_mode", False))


def get_language() -> str:
    settings = _read_settings()
    return _normalize_language(settings.get("language"))


def get_theme_mode() -> str:
    settings = _read_settings()
    theme_mode, _ = _resolve_theme_settings(settings)
    return theme_mode


def get_accent_color() -> str:
    settings = _read_settings()
    _, accent_color = _resolve_theme_settings(settings)
    return accent_color


def _has_meaningful_existing_setup(settings: dict[str, object], *, env_override_present: bool = False) -> bool:
    if env_override_present:
        return True
    if str(settings.get("library_root") or "").strip():
        return True
    if str(settings.get("output_root") or "").strip():
        return True
    return any(
        key in settings
        for key in (
            "duplicate_handling",
            "filename_compatibility",
            "output_format",
            "metadata_preservation",
        )
    )


def _resolve_onboarding_state(
    settings: dict[str, object],
    *,
    env_override_present: bool = False,
) -> tuple[bool, bool]:
    inferred_completed = _has_meaningful_existing_setup(settings, env_override_present=env_override_present)
    completed_raw = settings.get("onboarding_completed")
    dismissed_raw = settings.get("onboarding_dismissed")
    completed = completed_raw if isinstance(completed_raw, bool) else inferred_completed
    dismissed = dismissed_raw if isinstance(dismissed_raw, bool) else False
    if completed:
        return True, False
    return False, dismissed


def get_library_settings_state() -> LibrarySettingsResponse:
    env_override = (os.environ.get("MUSORG_LIBRARY_PATH") or "").strip()
    settings = _read_settings()
    output_root = get_effective_output_root()
    developer_mode = is_developer_mode_enabled()
    language = get_language()
    theme_mode = get_theme_mode()
    accent_color = get_accent_color()
    duplicate_handling = duplicate_handling_settings_to_api(_read_duplicate_handling())
    filename_compatibility = filename_compatibility_settings_to_api(_read_filename_compatibility())
    output_format = output_format_settings_to_api(_read_output_format())
    metadata_preservation = normalize_metadata_preservation_settings(_read_metadata_preservation())
    onboarding_completed, onboarding_dismissed = _resolve_onboarding_state(
        settings,
        env_override_present=bool(env_override),
    )

    if env_override:
        normalized = _normalize_path(env_override)
        error = _library_error(normalized)
        return LibrarySettingsResponse(
            libraryRoot=normalized,
            outputRoot=output_root,
            developerMode=developer_mode,
            language=language,
            themeMode=theme_mode,
            accentColor=accent_color,
            duplicateHandling=duplicate_handling,
            filenameCompatibility=filename_compatibility,
            outputFormat=output_format,
            metadataPreservation=metadata_preservation,
            onboardingCompleted=onboarding_completed,
            onboardingDismissed=onboarding_dismissed,
            isConfigured=True,
            isAvailable=error is None,
            source="environment",
            pickerAvailable=_native_picker_available(),
            message="Using MUSORG_LIBRARY_PATH override." if error is None else None,
            error=error,
        )

    library_root = str(settings.get("library_root") or "").strip()
    if not library_root:
        return LibrarySettingsResponse(
            libraryRoot="",
            outputRoot=output_root,
            developerMode=developer_mode,
            language=language,
            themeMode=theme_mode,
            accentColor=accent_color,
            duplicateHandling=duplicate_handling,
            filenameCompatibility=filename_compatibility,
            outputFormat=output_format,
            metadataPreservation=metadata_preservation,
            onboardingCompleted=onboarding_completed,
            onboardingDismissed=onboarding_dismissed,
            isConfigured=False,
            isAvailable=False,
            source="none",
            pickerAvailable=_native_picker_available(),
            message="Choose a music folder to start browsing your library.",
            error=None,
        )

    normalized = _normalize_path(library_root)
    error = _library_error(normalized)
    return LibrarySettingsResponse(
        libraryRoot=normalized,
        outputRoot=output_root,
        developerMode=developer_mode,
        language=language,
        themeMode=theme_mode,
        accentColor=accent_color,
        duplicateHandling=duplicate_handling,
        filenameCompatibility=filename_compatibility,
        outputFormat=output_format,
        metadataPreservation=metadata_preservation,
        onboardingCompleted=onboarding_completed,
        onboardingDismissed=onboarding_dismissed,
        isConfigured=True,
        isAvailable=error is None,
        source="settings",
        pickerAvailable=_native_picker_available(),
        message="Library connected." if error is None else "Saved library is currently unavailable.",
        error=error,
    )


def save_library_settings(
    library_root: str,
    output_root: str,
    developer_mode: bool = False,
    language: str = "en",
    theme_mode: str = "dark",
    accent_color: str = "violet",
    duplicate_handling: str = "keep_everything",
    filename_compatibility: str = "preserve_original",
    output_format: dict | None = None,
    metadata_preservation: dict | None = None,
    onboarding_completed: bool | None = None,
    onboarding_dismissed: bool | None = None,
) -> LibrarySettingsResponse:
    if str(library_root or "").strip():
        normalized_library = validate_library_root(library_root)
        normalized_output = validate_output_root(output_root)
    else:
        normalized_library = ""
        normalized_output = validate_output_root(output_root) if str(output_root or "").strip() else ""
    normalized_output_format = normalize_output_format_settings(output_format)
    normalized_metadata_preservation = normalize_metadata_preservation_settings(metadata_preservation)
    normalized_duplicate_handling = normalize_duplicate_handling_settings(duplicate_handling)
    normalized_filename_compatibility = normalize_filename_compatibility_settings(filename_compatibility)
    current_settings = _read_settings()
    current_onboarding_completed, current_onboarding_dismissed = _resolve_onboarding_state(current_settings)
    normalized_onboarding_completed = (
        current_onboarding_completed if onboarding_completed is None else bool(onboarding_completed)
    )
    normalized_onboarding_dismissed = (
        current_onboarding_dismissed if onboarding_dismissed is None else bool(onboarding_dismissed)
    )
    if normalized_onboarding_completed:
        normalized_onboarding_dismissed = False

    settings_dir = _settings_dir()
    settings_path = _settings_path()
    if _settings_runtime_isolated():
        _emit_settings_diagnostic(f"verification_runtime_isolated: {settings_path}")
        _emit_settings_diagnostic("settings_persistence_skipped: real user settings left untouched")

    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "library_root": normalized_library,
                "output_root": normalized_output,
                "developer_mode": bool(developer_mode),
                "language": _normalize_language(language),
                "theme_mode": _normalize_theme_mode(theme_mode),
                "accent_color": _normalize_accent_color(accent_color),
                "duplicate_handling": normalized_duplicate_handling,
                "filename_compatibility": normalized_filename_compatibility,
                "output_format": normalized_output_format,
                "metadata_preservation": normalized_metadata_preservation,
                "onboarding_completed": normalized_onboarding_completed,
                "onboarding_dismissed": normalized_onboarding_dismissed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return get_library_settings_state()


def validate_library_root(library_root: str) -> str:
    normalized = _normalize_path(library_root)
    error = _library_error(normalized)
    if error is not None:
        raise HTTPException(status_code=400, detail=error)
    return normalized


def validate_output_root(output_root: str) -> str:
    normalized = _normalize_path(output_root)
    error = _output_error(normalized)
    if error is not None:
        raise HTTPException(status_code=400, detail=error)
    return normalized


def pick_library_root() -> LibraryPickerResponse:
    return pick_folder("Choose Music Folder")


def pick_output_root() -> LibraryPickerResponse:
    return pick_folder("Choose Output Folder")


def pick_folder(prompt: str) -> LibraryPickerResponse:
    if not _native_picker_available():
        return LibraryPickerResponse(
            libraryRoot=None,
            canceled=False,
            pickerAvailable=False,
            error="Native folder picker is unavailable on this platform.",
        )

    script = (
        "try\n"
        f'POSIX path of (choose folder with prompt "{prompt}")\n'
        "on error number -128\n"
        'return ""\n'
        "end try"
    )
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return LibraryPickerResponse(
            libraryRoot=None,
            canceled=False,
            pickerAvailable=True,
            error=completed.stderr.strip() or "Failed to open the folder picker.",
        )

    chosen = completed.stdout.strip()
    if not chosen:
        return LibraryPickerResponse(
            libraryRoot=None,
            canceled=True,
            pickerAvailable=True,
            error=None,
        )

    return LibraryPickerResponse(
        libraryRoot=_normalize_path(chosen),
        canceled=False,
        pickerAvailable=True,
        error=None,
    )


def _read_settings() -> dict[str, object]:
    settings_path = _settings_path()
    if not settings_path.exists():
        return {}

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _read_output_format() -> dict[str, object]:
    settings = _read_settings()
    payload = settings.get("output_format")
    if isinstance(payload, dict):
        return normalize_output_format_settings(payload)
    return normalize_output_format_settings(None)


def _read_duplicate_handling() -> str:
    settings = _read_settings()
    return normalize_duplicate_handling_settings(settings.get("duplicate_handling"))


def _read_filename_compatibility() -> str:
    settings = _read_settings()
    return normalize_filename_compatibility_settings(settings.get("filename_compatibility"))


def _read_metadata_preservation() -> dict[str, object]:
    settings = _read_settings()
    payload = settings.get("metadata_preservation")
    if isinstance(payload, dict):
        return normalize_metadata_preservation_settings(payload)
    return normalize_metadata_preservation_settings(None)


def _normalize_path(raw_path: str) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def _normalize_language(language: object) -> str:
    value = str(language or "").strip().lower()
    return value if value in {"en", "ru"} else "en"


def _normalize_theme_mode(theme_mode: object) -> str:
    value = str(theme_mode or "").strip().lower()
    return value if value in {"light", "dark"} else "dark"


def _normalize_accent_color(accent_color: object) -> str:
    value = str(accent_color or "").strip().lower()
    if value == "cyan":
        return "sky"
    return value if value in {"violet", "indigo", "blue", "teal", "sky", "emerald", "amber", "rose"} else "violet"


def _resolve_theme_settings(settings: dict[str, object]) -> tuple[str, str]:
    raw_theme_mode = settings.get("theme_mode")
    raw_accent_color = settings.get("accent_color")
    has_new_theme_mode = raw_theme_mode is not None
    has_new_accent_color = raw_accent_color is not None

    if has_new_theme_mode or has_new_accent_color:
        return (
            _normalize_theme_mode(raw_theme_mode),
            _normalize_accent_color(raw_accent_color),
        )

    legacy_theme = str(settings.get("theme") or "").strip().lower()
    return {
        "light": ("light", "violet"),
        "dark": ("dark", "violet"),
        "dark_teal": ("dark", "teal"),
        "dark_blue": ("dark", "blue"),
    }.get(legacy_theme, ("dark", "violet"))


def _library_error(library_root: str) -> str | None:
    if not library_root:
        return "Library path is required."

    path = Path(library_root).expanduser()
    if not path.exists():
        return "Saved library folder could not be found."
    if not path.is_dir():
        return "Library path must be a directory."
    if not os.access(path, os.R_OK | os.X_OK):
        return "Library folder is not readable."
    return None


def _output_error(output_root: str) -> str | None:
    if not output_root:
        return "Output folder path is required."

    path = Path(output_root).expanduser()
    if not path.exists():
        return "Output folder could not be found."
    if not path.is_dir():
        return "Output path must be a directory."
    if not os.access(path, os.R_OK | os.X_OK | os.W_OK):
        return "Output folder must be readable and writable."
    return None


def _native_picker_available() -> bool:
    return sys.platform == "darwin"
