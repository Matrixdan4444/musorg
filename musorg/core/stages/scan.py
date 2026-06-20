import os

from musorg.filesystem.scanner import scan_files
from musorg.metadata.cue import detect_image_cue
from musorg.utils.debug import log


def scan_stage(context):
    files = scan_files(context.root_path)

    # Detect "image + cue" albums: one big audio file + a .cue sheet. The image
    # is excluded from the per-file list and expanded into per-track entries by
    # the metadata stage; the organize stage slices it into individual FLACs.
    cue_albums = []
    excluded_images: set[str] = set()
    folders = {os.path.dirname(file) for file in files}
    for folder in sorted(folders):
        detected = detect_image_cue(folder)
        if detected:
            image_path, sheet = detected
            cue_albums.append((image_path, sheet))
            excluded_images.add(os.path.normpath(image_path))

    context.files = [file for file in files if os.path.normpath(file) not in excluded_images]
    context.cue_albums = cue_albums

    if cue_albums:
        log(
            "Scan",
            f"Scanning music files... found {len(context.files)} audio files "
            f"and {len(cue_albums)} cue image album(s)",
            "🔎",
        )
    else:
        log("Scan", f"Scanning music files... found {len(context.files)} audio files", "🔎")
    return context
