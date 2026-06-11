from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
from fastapi import FastAPI

from musorg.api.server import ApiRuntimeConfig, create_app


@dataclass(slots=True)
class RuntimeUrls:
    api_origin: str
    frontend_origin: str
    frontend_url: str


class EmbeddedApiServer:
    def __init__(self, app: FastAPI, host: str = "127.0.0.1", port: int | None = None) -> None:
        self.host = host
        self.port = port or find_free_port(host)
        self._config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(self._config)
        self._thread = threading.Thread(target=self._server.run, name="musorg-api", daemon=True)

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, timeout: float = 10.0) -> None:
        self._thread.start()
        if not wait_for_url(f"{self.origin}/health", timeout=timeout):
            raise RuntimeError("Embedded FastAPI server did not become ready in time.")

    def stop(self, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)


class ManagedViteProcess:
    def __init__(self, process: subprocess.Popen[str], host: str, port: int) -> None:
        self.process = process
        self.host = host
        self.port = port

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self, timeout: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)


def create_embedded_app(frontend_dist: Path) -> FastAPI:
    runtime_config = ApiRuntimeConfig(
        mode="embedded",
        allow_origins=[],
        frontend_dist=frontend_dist,
    )
    return create_app(runtime_config)


def create_dev_app(vite_origin: str) -> FastAPI:
    runtime_config = ApiRuntimeConfig(
        mode="dev",
        allow_origins=[
            vite_origin,
            vite_origin.replace("127.0.0.1", "localhost"),
        ],
        frontend_dist=None,
    )
    return create_app(runtime_config)


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def wait_for_url(url: str, timeout: float = 10.0, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 500:
                    return True
        except URLError:
            time.sleep(interval)
        except OSError:
            time.sleep(interval)
    return False


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root)
    return repo_root()


def frontend_root() -> Path:
    root = runtime_root()
    candidate = root / "frontend"
    if candidate.exists():
        return candidate
    return repo_root() / "frontend"


def frontend_dist_dir() -> Path:
    return frontend_root() / "dist"


def vite_dev_origin(default_port: int = 5173) -> str:
    configured = os.environ.get("MUSORG_VITE_ORIGIN", "").strip()
    if configured:
        return configured
    return f"http://127.0.0.1:{default_port}"


def ensure_frontend_dist_exists() -> Path:
    dist = frontend_dist_dir()
    index_path = dist / "index.html"
    if not index_path.exists():
        raise RuntimeError(
            f"Built frontend was not found at {index_path}. Run `npm run build` in frontend/ first."
        )
    return dist


def attach_or_spawn_vite() -> tuple[str, ManagedViteProcess | None]:
    existing_origin = vite_dev_origin()
    if wait_for_url(existing_origin, timeout=1.0):
        return existing_origin, None

    port = find_free_port()
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=frontend_root(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    managed = ManagedViteProcess(process=process, host="127.0.0.1", port=port)
    if not wait_for_url(origin, timeout=15.0):
        managed.stop()
        raise RuntimeError("Vite dev server did not become ready in time.")
    return origin, managed


@contextlib.contextmanager
def managed_runtime_server(mode: str) -> tuple[EmbeddedApiServer, RuntimeUrls, ManagedViteProcess | None]:
    if mode == "dev":
        vite_origin, vite_process = attach_or_spawn_vite()
        api_server = EmbeddedApiServer(create_dev_app(vite_origin))
        api_server.start()
        urls = RuntimeUrls(
            api_origin=api_server.origin,
            frontend_origin=vite_origin,
            frontend_url=build_frontend_url(vite_origin, api_server.origin, "dev"),
        )
    else:
        frontend_dist = ensure_frontend_dist_exists()
        api_server = EmbeddedApiServer(create_embedded_app(frontend_dist))
        api_server.start()
        urls = RuntimeUrls(
            api_origin=api_server.origin,
            frontend_origin=api_server.origin,
            frontend_url=build_frontend_url(api_server.origin, api_server.origin, "embedded"),
        )
        vite_process = None

    try:
        yield api_server, urls, vite_process
    finally:
        api_server.stop()
        if vite_process is not None:
            vite_process.stop()


def build_frontend_url(frontend_origin: str, api_origin: str, runtime_mode: str) -> str:
    return (
        f"{frontend_origin}/?api_origin={api_origin}"
        f"&runtime_mode={runtime_mode}"
        "&host_kind=pywebview"
    )
