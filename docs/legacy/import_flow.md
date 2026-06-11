# Import Flow

Legacy reference: old PySide6 import screen

This document is archived historical context only. The canonical desktop
runtime is now `python -m musorg.desktop_webview`.

## Preview flow (NO file changes)

1. User selects folder OR drops folder
2. _apply_import_folder(path)
3. _load_preview(path)
4. ImportWorker scans folder
5. _handle_import_success(previews)

Rules:
- Preview must load immediately after folder selection
- Preview must REPLACE previous state
- No merging or appending
- Ignore folders ending with "_organized"
- Only albums inside selected folder are shown

## Clean flow (REAL pipeline)

1. User clicks "Clean My Albums"
2. run_pipeline(path, apply=True)
3. result.output_path is returned

Post-conditions:
- UI must switch to result.output_path
- Only cleaned albums are shown
- Original folder must not be displayed

## Constraints

- GUI is read-only layer
- Do not modify pipeline logic
- Do not duplicate scan logic
- This document describes the retired Qt flow only
