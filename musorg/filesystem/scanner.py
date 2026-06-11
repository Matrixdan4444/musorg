import os

from musorg.filesystem.naming import normalize_filesystem_text

SUPPORTED_FORMATS = (".flac", ".wav", ".aiff", ".m4a")

def scan_files(root_path):
    files = []
    for root, dirnames, filenames in os.walk(root_path):
        dirnames.sort(key=normalize_filesystem_text)
        for file in sorted(filenames, key=normalize_filesystem_text):
            if file.startswith("._"):
                continue
            if file.lower().endswith(SUPPORTED_FORMATS):
                files.append(os.path.join(root, file))

    return files
