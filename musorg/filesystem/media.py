import os
import shutil
import subprocess
import sys
import tempfile


COVER_SIZE = 1000
MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}
LOSSLESS_EXTENSIONS = {".flac"}


def _bundled_executable(command_name: str) -> str | None:
    """Return a helper binary shipped inside the PyInstaller bundle, if present.

    We ship a static ffmpeg in the app bundle so non-FLAC sources transcode
    without the user having to install ffmpeg. Depending on the PyInstaller
    layout the binary may sit at ``sys._MEIPASS`` (Contents/Frameworks) or in a
    sibling of the launcher, so check the likely spots. Returns None in dev (not
    frozen) so the PATH lookup wins.
    """
    if not getattr(sys, "frozen", False):
        return None

    candidates: list[str] = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, command_name))
    exe_dir = os.path.dirname(sys.executable)  # .app/Contents/MacOS
    candidates.append(os.path.join(exe_dir, command_name))
    candidates.append(os.path.join(exe_dir, "..", "Frameworks", command_name))
    candidates.append(os.path.join(exe_dir, "..", "Resources", command_name))

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.realpath(candidate)
    return None


def resolve_executable(command_name: str, env_var_name: str) -> str | None:
    configured_path = (os.environ.get(env_var_name) or "").strip()
    if configured_path:
        return configured_path

    bundled = _bundled_executable(command_name)
    if bundled:
        return bundled

    return shutil.which(command_name)


def normalize_picture_data(data, mime_type):
    extension = MIME_EXTENSION.get((mime_type or "").lower(), ".jpg")
    sips_path = resolve_executable("sips", "MUSORG_SIPS_BIN")
    if not sips_path:
        return data, mime_type

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = os.path.join(temp_dir, f"cover-src{extension}")
        output_path = os.path.join(temp_dir, f"cover-out{extension}")

        with open(source_path, "wb") as source_file:
            source_file.write(data)

        try:
            subprocess.run(
                [
                    sips_path,
                    "-z",
                    str(COVER_SIZE),
                    str(COVER_SIZE),
                    source_path,
                    "--out",
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
        except Exception:
            return data, mime_type

        try:
            with open(output_path, "rb") as output_file:
                normalized_data = output_file.read()
        except OSError:
            return data, mime_type

    normalized_mime = mime_type or "image/jpeg"
    if extension == ".jpg":
        normalized_mime = "image/jpeg"
    elif extension == ".png":
        normalized_mime = "image/png"

    return normalized_data, normalized_mime


def create_flac_file(source_path, destination_path, start_seconds=None, end_seconds=None):
    source_ext = os.path.splitext(source_path)[1].lower()
    slicing = start_seconds is not None

    # A plain lossless FLAC can be copied verbatim — but only when we are taking
    # the whole file. For a cue slice (or any non-FLAC source) we must decode and
    # re-encode through ffmpeg.
    if source_ext in LOSSLESS_EXTENSIONS and not slicing:
        shutil.copy2(source_path, destination_path)
        return

    ffmpeg_path = resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN")
    if not ffmpeg_path:
        raise FileNotFoundError(
            "ffmpeg executable not found; install ffmpeg or set MUSORG_FFMPEG_BIN"
        )

    command = [ffmpeg_path, "-y", "-i", source_path]
    if slicing:
        # Accurate sample-precise seek for cue track boundaries (-ss/-to after -i).
        command += ["-ss", f"{float(start_seconds):.6f}"]
        if end_seconds is not None:
            command += ["-to", f"{float(end_seconds):.6f}"]
    command += ["-map_metadata", "-1", "-vn", "-c:a", "flac", destination_path]

    subprocess.run(command, check=True, capture_output=True)
