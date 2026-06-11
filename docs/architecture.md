# Musorg Architecture

Musorg now has one supported desktop architecture:

- React frontend in `frontend/`
- FastAPI transport layer in `musorg/api/`
- shared backend-safe logic in `musorg/core/`
- pywebview desktop shell in `musorg/desktop_webview/`

Canonical desktop runtime:

```bash
python -m musorg.desktop_webview
```

The legacy PySide6 runtime has been retired. Historical reference material, if
kept, lives under `docs/legacy/`.
