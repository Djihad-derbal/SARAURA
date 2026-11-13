"""Storage interface for everything the app writes: Showcase Site data, Analysis results, caches.

Code addresses files by key ("<site_id>/layers/hv_db_2026-09-01.tif"), never by
absolute path, so the local-disk backend can later be swapped for object storage
(S3) by configuration alone. See docs/adr/0003-local-first-storage-interface.md.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterator, Protocol


class Storage(Protocol):
    def exists(self, key: str) -> bool: ...
    def read_bytes(self, key: str) -> bytes: ...
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def read_text(self, key: str) -> str: ...
    def write_text(self, key: str, text: str) -> None: ...
    def list(self, prefix: str = "") -> Iterator[str]: ...
    def delete(self, key: str) -> None: ...
    def local_path(self, key: str) -> Path:
        """A filesystem path for libraries that need one (h5py, rasterio, numpy.savez)."""
        ...


def _clean(key: str) -> str:
    key = key.replace("\\", "/").lstrip("/")
    if not key or any(part in ("", ".", "..") for part in key.split("/")):
        raise ValueError(f"Invalid storage key: {key!r}")
    return key


class LocalStorage:
    """Files under one root directory. Writes are atomic (temp file + rename)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _clean(key)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def read_text(self, key: str) -> str:
        return self.read_bytes(key).decode("utf-8")

    def write_text(self, key: str, text: str) -> None:
        self.write_bytes(key, text.encode("utf-8"))

    def list(self, prefix: str = "") -> Iterator[str]:
        base = self.root / _clean(prefix) if prefix else self.root
        if not base.exists():
            return
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.name.endswith(".tmp"):
                yield p.relative_to(self.root).as_posix()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def local_path(self, key: str) -> Path:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def from_url(url: str) -> Storage:
    """Build a storage backend from a URL-like setting. Only local paths for now; s3:// comes with hosting."""
    if url.startswith("s3://"):
        raise NotImplementedError("Object storage is not wired yet (ADR-0003: local first).")
    return LocalStorage(url.removeprefix("file://"))
