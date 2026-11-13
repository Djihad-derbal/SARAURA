"""Chunk-level reader for NISAR GCOV and GUNW HDF5 files.

h5py is used once per file to read the grid description and the byte position
of every compressed chunk. After that, pixels are read by fetching chunks
directly over HTTP in parallel and decompressing them here, which is several
times faster than letting h5py read the remote file serially.
"""
import json
import threading
import zlib
from collections import OrderedDict
from concurrent.futures import Future

import h5py
import numpy as np

from . import cmr, config, remote

GRIDS = "science/LSAR/GCOV/grids"
TERMS = ("HHHH", "HVHV", "VVVV", "VHVH")
GUNW_UNW = "science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"
# Readable grids per product: grid key -> HDF5 group, and the datasets inside it.
LAYOUTS = {
    "GCOV": {"groups": {"A": f"{GRIDS}/frequencyA", "B": f"{GRIDS}/frequencyB"}, "terms": TERMS},
    "GUNW": {
        "groups": {"U": GUNW_UNW},  # 80 m unwrapped products
        "terms": ("HH/unwrappedPhase", "HH/coherenceMagnitude", "HH/connectedComponents", "HH/ionospherePhaseScreen"),
    },
}
DTYPES = {"float32": np.float32, "uint16": np.uint16, "uint32": np.uint32}


def product_of(granule_id: str) -> str:
    return "GUNW" if "_GUNW_" in granule_id else "GCOV"


def _tk(term: str) -> str:
    """Term name safe for archive and cache keys (GUNW terms contain a slash)."""
    return term.replace("/", "-")
_h5_lock = threading.Lock()
_index_locks: dict[str, threading.Lock] = {}
_indexes: dict[str, dict] = {}
_mem: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_mem_lock = threading.Lock()
_inflight: dict[tuple, Future] = {}


def _index_key(granule_id: str, name: str) -> str:
    return f"index/{granule_id}/{name}"


def _build_index(granule: dict) -> None:
    meta = {"id": granule["id"], "freqs": {}}
    arrays = {}
    f = remote.RangeFile(granule["h5_url"])  # network warm-up happens outside the HDF5 lock
    with _h5_lock:
        with h5py.File(f, "r") as h:
            layout = LAYOUTS[product_of(granule["id"])]
            for freq, path in layout["groups"].items():
                if path not in h:
                    continue
                g = h[path]
                x, y = g["xCoordinates"][:], g["yCoordinates"][:]
                terms = [t for t in layout["terms"] if t in g]
                first = g[terms[0]]
                meta["freqs"][freq] = {
                    "epsg": int(g["projection"][()]),
                    "x0": float(x[0]),
                    "y0": float(y[0]),
                    "dx": float(g["xCoordinateSpacing"][()]),
                    "dy": float(g["yCoordinateSpacing"][()]),
                    "shape": list(first.shape),
                    "chunks": list(first.chunks),
                    "terms": terms,
                }
                for t in terms:
                    ds = g[t]
                    if ds.compression != "gzip" or str(ds.dtype) not in DTYPES or ds.scaleoffset or ds.fletcher32:
                        raise NotImplementedError(f"Unexpected storage for {t}: {ds.compression} {ds.dtype}")
                    nr = -(-ds.shape[0] // ds.chunks[0])
                    nc = -(-ds.shape[1] // ds.chunks[1])
                    off = np.full((nr, nc), -1, np.int64)
                    size = np.zeros((nr, nc), np.int64)
                    mask = np.zeros((nr, nc), np.int64)

                    def visit(info, off=off, size=size, mask=mask, ch=ds.chunks):
                        r, c = info.chunk_offset[0] // ch[0], info.chunk_offset[1] // ch[1]
                        off[r, c], size[r, c], mask[r, c] = info.byte_offset, info.size, info.filter_mask

                    ds.id.chunk_iter(visit)
                    k = f"{freq}_{_tk(t)}"
                    arrays[f"{k}_off"], arrays[f"{k}_size"], arrays[f"{k}_mask"] = off, size, mask
                    meta["freqs"][freq][f"shuffle_{t}"] = bool(ds.shuffle)
                    meta["freqs"][freq][f"dtype_{t}"] = str(ds.dtype)
    np.savez_compressed(config.cache.local_path(_index_key(granule["id"], "chunks.npz")), **arrays)
    config.cache.write_text(_index_key(granule["id"], "meta.json"), json.dumps(meta))


def index(granule_id: str) -> dict:
    """Grid description and chunk table for a Granule; built on first use (about 10 s)."""
    if granule_id in _indexes:
        return _indexes[granule_id]
    lock = _index_locks.setdefault(granule_id, threading.Lock())
    with lock:
        if granule_id in _indexes:
            return _indexes[granule_id]
        if not config.cache.exists(_index_key(granule_id, "meta.json")):
            _build_index(cmr.get(granule_id))
        idx = json.loads(config.cache.read_text(_index_key(granule_id, "meta.json")))
        idx["tables"] = dict(np.load(config.cache.local_path(_index_key(granule_id, "chunks.npz"))))
        idx["url"] = cmr.get(granule_id)["h5_url"]
        _indexes[granule_id] = idx
        return idx


def is_indexed(granule_id: str) -> bool:
    return granule_id in _indexes or config.cache.exists(_index_key(granule_id, "meta.json"))


def _decode(raw: bytes, filter_mask: int, shuffle: bool, shape, dtype=np.float32) -> np.ndarray:
    """Chunk bytes -> float32 array. Integer layers (e.g. connected components) are converted to float32."""
    # Filter pipeline on write is [shuffle,] gzip; undo in reverse. A set bit
    # in filter_mask means that filter was skipped for this chunk.
    gzip_bit = 1 if shuffle else 0
    data = raw if filter_mask & (1 << gzip_bit) else zlib.decompress(raw)
    size = np.dtype(dtype).itemsize
    if shuffle and not filter_mask & 1:
        data = np.frombuffer(data, np.uint8).reshape(size, -1).T.tobytes()
    return np.frombuffer(data, dtype).reshape(shape).astype(np.float32, copy=False)


def _load_chunk(idx: dict, freq: str, term: str, r: int, c: int) -> np.ndarray:
    fm = idx["freqs"][freq]
    t = idx["tables"]
    k = f"{freq}_{_tk(term)}"
    off = int(t[f"{k}_off"][r, c])
    if off < 0:
        return np.full(fm["chunks"], np.nan, np.float32)
    size = int(t[f"{k}_size"][r, c])
    key = f"chunks/{idx['id']}/{k}_{r}_{c}.bin"
    if config.cache.exists(key):
        raw = config.cache.read_bytes(key)
    else:
        raw = remote.get_range(idx["url"], off, off + size - 1)
        config.cache.write_bytes(key, raw)
    dtype = DTYPES[fm.get(f"dtype_{term}", "float32")]
    return _decode(raw, int(t[f"{k}_mask"][r, c]), fm[f"shuffle_{term}"], fm["chunks"], dtype)


def _chunk_future(idx: dict, freq: str, term: str, r: int, c: int) -> Future:
    key = (idx["id"], freq, term, r, c)
    with _mem_lock:
        if key in _mem:
            _mem.move_to_end(key)
            done = Future()
            done.set_result(_mem[key])
            return done
        if key in _inflight:
            return _inflight[key]
        fut = remote.pool.submit(_load_chunk, idx, freq, term, r, c)
        _inflight[key] = fut

    def finish(f, key=key):
        with _mem_lock:
            _inflight.pop(key, None)
            if not f.exception():
                _mem[key] = f.result()
                while len(_mem) > config.MEMORY_CHUNKS:
                    _mem.popitem(last=False)

    fut.add_done_callback(finish)
    return fut


def read_window(granule_id: str, freq: str, term: str, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
    """Values of one layer for rows r0..r1 and columns c0..c1 (end exclusive), as float32. NaN where there is no data.

    GCOV terms are linear backscatter; GUNW terms are phase (rad), coherence (0-1) or component labels."""
    idx = index(granule_id)
    fm = idx["freqs"][freq]
    if term not in fm["terms"]:
        raise KeyError(f"{term} not in this Granule; available: {fm['terms']}")
    rows, cols = fm["shape"]
    ch_r, ch_c = fm["chunks"]
    out = np.full((r1 - r0, c1 - c0), np.nan, np.float32)
    a0, a1, b0, b1 = max(r0, 0), min(r1, rows), max(c0, 0), min(c1, cols)
    if a0 >= a1 or b0 >= b1:
        return out
    futures = {
        (r, c): _chunk_future(idx, freq, term, r, c)
        for r in range(a0 // ch_r, (a1 - 1) // ch_r + 1)
        for c in range(b0 // ch_c, (b1 - 1) // ch_c + 1)
    }
    for (r, c), fut in futures.items():
        chunk = fut.result()
        rr0, cc0 = r * ch_r, c * ch_c
        s0, s1 = max(a0, rr0), min(a1, rr0 + ch_r)
        t0, t1 = max(b0, cc0), min(b1, cc0 + ch_c)
        out[s0 - r0 : s1 - r0, t0 - c0 : t1 - c0] = chunk[s0 - rr0 : s1 - rr0, t0 - cc0 : t1 - cc0]
    return out
