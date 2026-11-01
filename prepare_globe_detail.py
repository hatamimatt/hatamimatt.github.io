#!/usr/bin/env python3
"""0.25 degree detail for the globe's Helene view, from the viewer's data (prepare_event.py).

The globe's Helene dataset (data/globe/, prepare_globe.py) is global at 1 degree. This
converts the viewer's 0.25 degree ERA5 fields over the Southeast (data/helene/) to the
globe's binary format at the globe's 6-hourly times, so the globe can show full detail
when zoomed in:
  ivtu, ivtv, pw   the viewer's 3-hourly fields at each 6-hourly time
  rain6            the two 3-hour rain totals ending at each time

Writes data/globe/detail/<layer>.bin (rows north to south) and adds a "detail" entry to
data/globe/meta.json. Needs numpy.

    python prepare_globe_detail.py
"""
import base64, datetime as dt, json, os, sys

import numpy as np

SRC, DST = os.path.join("data", "helene"), os.path.join("data", "globe")
LAYERS = {"ivtu": "ivtu", "ivtv": "ivtv", "pw": "pw", "rain6": "precip3"}


def frames(name, nt, ny, nx):
    """Viewer layer -> (nt, ny, nx) float array, rows south to north as stored."""
    d = json.load(open(os.path.join(SRC, f"{name}.json")))
    q = np.frombuffer(base64.b64decode(d["data"]), np.uint8).reshape(nt, ny, nx).astype(np.float32)
    return np.where(q == 255, np.nan, d["vmin"] + q / 254 * (d["vmax"] - d["vmin"]))


def main():
    src = json.load(open(os.path.join(SRC, "meta.json")))
    meta = json.load(open(os.path.join(DST, "meta.json")))
    g = src["grid"]; ny, nx = g["ny"], g["nx"]
    stimes = src["times"]
    idx = {t: k for k, t in enumerate(stimes)}
    missing = [t for t in meta["times"] if t not in idx]
    assert not missing, f"viewer data lacks globe times {missing[:3]}"
    step = (dt.datetime.fromisoformat(stimes[1]) - dt.datetime.fromisoformat(stimes[0])).seconds // 3600
    assert step == 3, "expected 3-hourly viewer data"

    os.makedirs(os.path.join(DST, "detail"), exist_ok=True)
    detail = {}
    for name, srcname in LAYERS.items():
        f = frames(srcname, len(stimes), ny, nx)
        if name == "rain6":  # 6 h total = this 3 h total plus the previous one (zero before the first)
            prev = np.concatenate([np.zeros_like(f[:1]), f[:-1]])
            f = f + prev
        out = np.stack([f[idx[t]] for t in meta["times"]])[:, ::-1]  # rows north to south
        lo, hi = meta["layers"][name]["vmin"], meta["layers"][name]["vmax"]  # same scale as the global layer
        q = np.where(np.isfinite(out), np.clip(np.round((out - lo) / (hi - lo) * 254), 0, 254), 255).astype(np.uint8)
        q.tofile(os.path.join(DST, "detail", f"{name}.bin"))
        detail[name] = {"file": f"detail/{name}.bin", "vmin": lo, "vmax": hi}
    meta["detail"] = {"grid": {"nlat": ny, "nlon": nx, "lat0": g["lat0"] + (ny - 1) * g["dlat"], "lon0": g["lon0"], "d": g["dlat"]},
                      "layers": detail, "source": "ERA5 at 0.25 degree, from data/helene (prepare_event.py)"}
    with open(os.path.join(DST, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(f"Done: data/globe/detail, {ny}x{nx} at {g['dlat']} degree, {len(meta['times'])} times")


if __name__ == "__main__":
    sys.exit(main())
