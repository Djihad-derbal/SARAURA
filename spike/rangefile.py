"""Minimal read-only HTTP range file for h5py, with block cache. Auth: Earthdata bearer token."""
import io, re, time, requests

def load_token(env_path):
    return re.search(r"^EARTHDATA_TOKEN=(.*)$", open(env_path).read(), re.M).group(1).strip()

class RangeFile(io.RawIOBase):
    def __init__(self, url, token, block=4 * 1024 * 1024, max_blocks=64):
        self.url, self.token, self.block, self.max_blocks = url, token, block, max_blocks
        self.s = requests.Session(); self.pos = 0; self.cache = {}; self.order = []
        self.n_req = 0; self.n_bytes = 0; self.t_net = 0.0
        self._resolve()
        r = self.s.get(self.signed, headers={"Range": "bytes=0-0"}, timeout=120)
        self.size = int(r.headers["Content-Range"].split("/")[1])
    def _resolve(self):
        r = self.s.get(self.url, headers={"Authorization": "Bearer " + self.token}, allow_redirects=False, timeout=120)
        if r.status_code not in (301, 302, 303, 307):
            raise IOError("auth/redirect failed: HTTP %s %s" % (r.status_code, r.text[:300]))
        self.signed = r.headers["location"]
    def _get_block(self, i):
        if i in self.cache: return self.cache[i]
        a = i * self.block; b = min(self.size, a + self.block) - 1
        t = time.time()
        r = self.s.get(self.signed, headers={"Range": "bytes=%d-%d" % (a, b)}, timeout=300)
        if r.status_code == 403:
            self._resolve(); r = self.s.get(self.signed, headers={"Range": "bytes=%d-%d" % (a, b)}, timeout=300)
        r.raise_for_status()
        self.t_net += time.time() - t; self.n_req += 1; self.n_bytes += len(r.content)
        self.cache[i] = r.content; self.order.append(i)
        if len(self.order) > self.max_blocks: self.cache.pop(self.order.pop(0), None)
        return r.content
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0: return 0
        out = bytearray(); p = self.pos
        while len(out) < n:
            i = p // self.block; blk = self._get_block(i); o = p - i * self.block
            take = blk[o:o + (n - len(out))]; out += take; p += len(take)
        buf[:n] = out; self.pos += n; return n
