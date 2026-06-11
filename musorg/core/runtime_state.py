from __future__ import annotations

from contextlib import contextmanager
import threading


_THREAD_LOCAL = threading.local()
_UNSET = object()


def is_developer_mode() -> bool:
    return bool(getattr(_THREAD_LOCAL, "developer_mode", False))


@contextmanager
def runtime_options(*, developer_mode: bool = False):
    previous = getattr(_THREAD_LOCAL, "developer_mode", _UNSET)
    _THREAD_LOCAL.developer_mode = bool(developer_mode)
    try:
        yield
    finally:
        if previous is _UNSET:
            if hasattr(_THREAD_LOCAL, "developer_mode"):
                delattr(_THREAD_LOCAL, "developer_mode")
        else:
            _THREAD_LOCAL.developer_mode = previous
