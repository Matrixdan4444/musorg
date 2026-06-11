import threading


_LOG_SINK = None
_LOG_OBSERVERS = []
_LOG_OBSERVERS_LOCK = threading.Lock()
_LOG_CONSOLE_ENABLED = True


def set_log_sink(sink) -> None:
    global _LOG_SINK
    _LOG_SINK = sink


def clear_log_sink() -> None:
    global _LOG_SINK
    _LOG_SINK = None


def add_log_observer(observer) -> None:
    with _LOG_OBSERVERS_LOCK:
        if observer not in _LOG_OBSERVERS:
            _LOG_OBSERVERS.append(observer)


def remove_log_observer(observer) -> None:
    with _LOG_OBSERVERS_LOCK:
        if observer in _LOG_OBSERVERS:
            _LOG_OBSERVERS.remove(observer)


def set_log_console_enabled(enabled: bool) -> bool:
    global _LOG_CONSOLE_ENABLED
    previous = _LOG_CONSOLE_ENABLED
    _LOG_CONSOLE_ENABLED = bool(enabled)
    return previous


def _emit(level: str, stage: str, message: str, emoji: str) -> None:
    if _LOG_CONSOLE_ENABLED:
        print(f"{emoji} {stage}: {message}")
    with _LOG_OBSERVERS_LOCK:
        observers = tuple(_LOG_OBSERVERS)
    if _LOG_SINK:
        _LOG_SINK({
            "level": level,
            "stage": stage,
            "message": message,
            "emoji": emoji,
        })
    for observer in observers:
        observer({
            "level": level,
            "stage": stage,
            "message": message,
            "emoji": emoji,
        })


def log(stage: str, message: str, emoji: str = "•") -> None:
    _emit("info", stage, message, emoji)


def success(stage: str, message: str) -> None:
    _emit("success", stage, message, "✅")


def warning(stage: str, message: str) -> None:
    _emit("warning", stage, message, "⚠️")


def error(stage: str, message: str) -> None:
    _emit("error", stage, message, "❌")
