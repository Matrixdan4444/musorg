import os
import shutil
import subprocess
import tempfile


COVER_SIZE = 1000
MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}
LOSSLESS_EXTENSIONS = {".flac"}


def resolve_executable(command_name: str, env_var_name: str) -> str | None:
    configured_path = (os.environ.get(env_var_name) or "").strip()
    if configured_path:
        return configured_path

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


def create_flac_file(source_path, destination_path):
    source_ext = os.path.splitext(source_path)[1].lower()
    if source_ext in LOSSLESS_EXTENSIONS:
        shutil.copy2(source_path, destination_path)
        return

    ffmpeg_path = resolve_executable("ffmpeg", "MUSORG_FFMPEG_BIN")
    if not ffmpeg_path:
        raise FileNotFoundError(
            "ffmpeg executable not found; install ffmpeg or set MUSORG_FFMPEG_BIN"
        )

    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            source_path,
            "-map_metadata",
            "-1",
            "-vn",
            "-c:a",
            "flac",
            destination_path,
        ],
        check=True,
        capture_output=True,
    )
