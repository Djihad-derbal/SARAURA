import sys, json, time, h5py, numpy as np
sys.path.insert(0, sys.argv[3])
from rangefile import RangeFile, load_token
tok = load_token(sys.argv[1]); rows = json.load(open(sys.argv[2]))
R0, C0, N = 14848, 17920, 2048
out = {}
for day in ("20260820", "20260901"):
    row = [r for r in rows if "_109_D_070_" in r["ur"] and day + "T" in r["ur"]][0]
    url = [u for u in row["urls"] if u.startswith("https") and u.endswith("_001.h5")][0]
    t0 = time.time(); f = RangeFile(url, tok, block=2 * 1024 * 1024); h = h5py.File(f, "r")
    g = h["science/LSAR/GCOV/grids/frequencyA"]
    x = g["xCoordinates"][:]; y = g["yCoordinates"][:]
    if day == "20260820":
        x_ref, y_ref = x[C0], y[R0]; r0, c0 = R0, C0
    else:
        c0 = int(round((x_ref - x[0]) / 10.0)); r0 = int(round((y[0] - y_ref) / 10.0))
    t1 = time.time(); q0 = f.n_req; b0 = f.n_bytes
    hv = g["HVHV"][r0:r0 + N, c0:c0 + N]
    t2 = time.time(); q1 = f.n_req; b1 = f.n_bytes
    hh = g["HHHH"][r0:r0 + N, c0:c0 + N]
    t3 = time.time()
    print("%s shape=%s origin row=%d col=%d x=%.0f y=%.0f | open+coords %.1fs | HV window %.1fs (%d requests, %.1f MB) | HH window %.1fs | total MB %.1f"
          % (day, g["HVHV"].shape, r0, c0, x[c0], y[r0], t1 - t0, t2 - t1, q1 - q0, (b1 - b0) / 1e6, t3 - t2, f.n_bytes / 1e6))
    out[day] = (hv, hh)
    if day == "20260901" and "frequencyB" in h["science/LSAR/GCOV/grids"]:
        gb = h["science/LSAR/GCOV/grids/frequencyB"]
        print("frequencyB: shape=%s spacing=%s" % (gb["HVHV"].shape, gb["xCoordinateSpacing"][()]))
np.savez_compressed(sys.argv[3] + "/window.npz", hv_pre=out["20260820"][0], hh_pre=out["20260820"][1], hv_post=out["20260901"][0], hh_post=out["20260901"][1], x0=x_ref, y0=y_ref)
for k, (hv, hh) in out.items():
    v = 10 * np.log10(hv[np.isfinite(hv) & (hv > 0)]); w = 10 * np.log10(hh[np.isfinite(hh) & (hh > 0)])
    print(k, "valid %.1f%%  HV dB median %.1f (p5 %.1f, p95 %.1f)  HH dB median %.1f" % (100 * np.isfinite(hv).mean(), np.median(v), np.percentile(v, 5), np.percentile(v, 95), np.median(w)))
