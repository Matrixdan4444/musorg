from musorg.filesystem.scanner import scan_files
from musorg.utils.debug import log

def scan_stage(context):
    context.files = scan_files(context.root_path)
    log("Scan", f"Scanning music files... found {len(context.files)} audio files", "🔎")
    return context
