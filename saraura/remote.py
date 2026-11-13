"""Authenticated byte-range access to NISAR files in Earthdata Cloud.

ASF answers a request carrying an Earthdata bearer token with a redirect to a
short-lived signed URL. We resolve that once per file, reuse it for every
range request, and resolve again when it is about to expire.
"""
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import requests

from . import config

_local = threading.local()
_signed: dict[str, tuple[str, float]] = {}
_signed_lock = threading.Lock()
pool = ThreadPoolExecutor(max_workers=config.FETCH_THREADS, thread_name_prefix="fetch")

stats = {"requests": 0, "bytes": 0}


def session() -> requests.Session:
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s


def _resolve(url: str, force: bool = False) -> str:
    with _signed_lock:
        hit = _signed.get(url)
        if hit and not force and hit[1] - time.time() > 120:
            return hit[0]
    r = session().get(
        url,
        headers={"Authorization": "Bearer " + config.earthdata_token()},
        allow_redirects=False,
        timeout=60,
    )
    if r.status_code not in (301, 302, 303, 307):
        raise PermissionError(f"Earthdata refused {url.rsplit('/', 1)[-1]}: HTTP {r.status_code} {r.text[:200]}")
    signed = r.headers["location"]
    try:
        expires = float(parse_qs(urlparse(signed).query)["Expires"][0])
    except (KeyError, ValueError):
        expires = time.time() + 900
    with _signed_lock:
        _signed[url] = (signed, expires)
    return signed


def get_range(url: str, start: int, end: int) -> bytes:
    """Bytes start..end inclusive."""
    headers = {"Range": f"bytes={start}-{end}"}
    for attempt in range(3):
        r = session().get(_resolve(url, force=attempt > 0), headers=headers, timeout=180)
        if r.status_code in (200, 206):
            stats["requests"] += 1
            stats["bytes"] += len(r.content)
            return r.content
        if r.status_code not in (401, 403):
            r.raise_for_status()
    raise PermissionError(f"Range request failed for {url.rsplit('/', 1)[-1]}: HTTP {r.status_code}")


def get_text(url: str) -> str:
    """Small login-protected sidecar file (for example a KML)."""
    r = session().get(_resolve(url), timeout=60)
    r.raise_for_status()
    return r.text


def file_size(url: str) -> int:
    r = session().get(_resolve(url), headers={"Range": "bytes=0-0"}, timeout=60)
    return int(r.headers["Content-Range"].split("/")[1])


class RangeFile(io.RawIOBase):
    """Read-only file object over HTTP ranges, for h5py metadata reads.

    The first `warm` bytes are fetched in parallel up front, because NISAR
    files keep their metadata at the front.
    """

    def __init__(self, url: str, block: int = 2 * 1024 * 1024, warm: int = 32 * 1024 * 1024):
        self.url, self.block, self.pos = url, block, 0
        self.size = file_size(url)
        self.cache: dict[int, bytes] = {}
        n = min(warm, self.size) // block
        for i, data in zip(range(n), pool.map(self._fetch, range(n))):
            self.cache[i] = data

    def _fetch(self, i: int) -> bytes:
        a = i * self.block
        return get_range(self.url, a, min(self.size, a + self.block) - 1)

    def _block(self, i: int) -> bytes:
        if i not in self.cache:
            self.cache[i] = self._fetch(i)
        return self.cache[i]

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        out = bytearray()
        p = self.pos
        while len(out) < n:
            i = p // self.block
            o = p - i * self.block
            take = self._block(i)[o : o + (n - len(out))]
            out += take
            p += len(take)
        buf[:n] = out
        self.pos += n
        return n
