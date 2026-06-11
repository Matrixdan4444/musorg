# Legacy PySide6 Audit

Canonical desktop runtime: `python -m musorg.desktop_webview`

This note records the dependency map that existed before the legacy
`musorg.desktop` package was removed.

## Former Module Classification

### Qt Runtime Only

- `musorg.desktop.app`
- `musorg.desktop.widgets`
- `musorg.desktop.theme`

### Shared Or Mixed-Coupling Modules Before Extraction

- `musorg.desktop.import_preview`
- `musorg.desktop.import_covers`
- `musorg.desktop.audit_client`
- `musorg.desktop.models`

## Former PySide6 Import Map

The following modules imported PySide6 before decommission:

- `musorg.desktop.app`
- `musorg.desktop.widgets`
- `musorg.desktop.import_covers`

## Historical Blockers

Before extraction, API/backend logic still depended on `musorg.desktop`
preview and cover helpers. Those dependencies were removed during the backend
extraction phase, which made the final PySide6 decommission possible.
