#!/usr/bin/env python3
"""Five-day forecasts of the atmosphere behind extreme rain, from two models, for the globe.

For the newest 00 or 12 UTC run of each model, every 12 hours out to 120 h:
  - integrated vapor transport (IVT), east and north components, integrated from the
    surface (or 1000 hPa) to 300 hPa
  - precipitable water (GFS) or total column water (AIFS, which also counts cloud water)
  - 850 hPa wind
  - rain in the 12 hours up to each time

Models (open data, no account needed):
  gfs   NOAA GFS, 0.25 degree, from NOAA Open Data Dissemination on AWS
  aifs  ECMWF AIFS Single, ECMWF's machine-learning model, 0.25 degree, from ECMWF open
        data on Google Cloud (the AWS copy throttles); CC BY 4.0, credit ECMWF

Writes data/forecast/<model>/ in the same format as data/recent/ (prepare_recent.py): the
global fields averaged to 1 degree plus a 0.25 degree detail box over North America, with
lead times as frames. A model whose newest run is already built is left as it is, so the
script can run every 6 hours and only downloads when a new run is out.
Needs numpy and eccodes.

    python prepare_forecast.py
    python prepare_forecast.py --models aifs
"""
import argparse, datetime as dt, json, os, re, sys, urllib.error
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from prepare_forecasts import decode, get
from prepare_now import to_one_degree
from prepare_recent import DETAIL, get_range, index as gfs_index, quantize

LEADS = list(range(12, 121, 12))           # hours after the run
LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300]  # hPa, available in both models
G = 9.80665
RANGES = {"ivtu": (-2000, 2000), "ivtv": (-2000, 2000), "pw": (0, 80), "rain12": (0, 150), "u850": (-60, 60), "v850": (-60, 60)}
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{r:%Y%m%d}/{r:%H}/atmos/gfs.t{r:%H}z.pgrb2.0p25.f{f:03d}"
AIFS = "https://storage.googleapis.com/ecmwf-open-data/{r:%Y%m%d}/{r:%H}z/aifs-single/0p25/oper/{r:%Y%m%d%H}0000-{f}h-oper-fc"
MODELS = {
    "gfs":  {"name": "NOAA GFS", "source": "NOAA GFS, 0.25 degree (NOAA Open Data Dissemination on AWS)", "pw": "Precipitable water"},
    "aifs": {"name": "ECMWF AIFS", "source": "ECMWF AIFS Single open data, 0.25 degree, CC BY 4.0", "pw": "Total column water"},
}


def to_180w(vals, lon0):
    """Columns from 180W like the other globe data (GFS grids start at 0E, ECMWF open data at 180W)."""
    lon0 = (lon0 + 180) % 360 - 180
    return np.roll(vals, -round((lon0 + 180) / 0.25), axis=1) if abs(lon0 + 180) > 1e-6 else vals


def grib(url, start, end):
    vals, d, lon0 = decode(get_range(url, start, end))
    assert abs(d - 0.25) < 1e-6, "expected a 0.25 degree grid"
    return to_180w(vals, lon0).astype(np.float32)


# ---------- GFS ----------
def gfs_fields(run, f):
    url = GFS.format(r=run, f=f)
    idx = gfs_index(url)
    acc = f"0-{f // 24} day acc fcst" if f % 24 == 0 else f"0-{f} hour acc fcst"
    keys = {(v, p): f"{n}:{p} mb:{f} hour fcst" for p in LEVELS for v, n in (("q", "SPFH"), ("u", "UGRD"), ("v", "VGRD"))}
    keys.update({"sp": f"PRES:surface:{f} hour fcst", "pw": f"PWAT:entire atmosphere (considered as a single layer):{f} hour fcst",
                 "tp": f"APCP:surface:{acc}"})
    with ThreadPoolExecutor(8) as ex:
        got = dict(zip(keys, ex.map(lambda k: grib(url, *idx[keys[k]]), keys)))
    return got  # sp in Pa, tp in mm (kg m-2) since the run started


# ---------- AIFS ----------
def aifs_fields(run, f):
    url = AIFS.format(r=run, f=f)
    recs = {}
    for line in get(url + ".index").decode().splitlines():
        r = json.loads(line)
        recs[(r["param"], r.get("levelist"))] = (r["_offset"], r["_offset"] + r["_length"] - 1)
    keys = {(v, p): (v, str(p)) for p in LEVELS for v in ("q", "u", "v")}
    keys.update({"sp": ("sp", None), "pw": ("tcw", None), "tp": ("tp", None)})
    with ThreadPoolExecutor(6) as ex:
        got = dict(zip(keys, ex.map(lambda k: grib(url + ".grib2", *recs[keys[k]]), keys)))
    return got  # tp is already in kg m-2 (mm) in AIFS output, unlike IFS (m); accumulated since the run started


def latest_run(model, now):
    """Newest 00/12 UTC run whose 120 h file is published."""
    r = now.replace(minute=0, second=0, microsecond=0, hour=12 if now.hour >= 12 else 0)
    for _ in range(6):
        url = (GFS if model == "gfs" else AIFS).format(r=r, f=120) + (".idx" if model == "gfs" else ".index")
        try:
            get(url, tries=2)
            return r
        except urllib.error.HTTPError:
            r -= dt.timedelta(hours=12)
    raise SystemExit(f"No {model} run found in the last three days")


def layers_at(got):
    ps = got["sp"] / 100.0
    ivtu = np.zeros_like(ps); ivtv = np.zeros_like(ps)
    for lo, hi in zip(LEVELS[:-1], LEVELS[1:]):  # trapezoid layers; skip layers below the ground
        w = (ps >= lo).astype(np.float32) * (lo - hi) * 100.0 / G / 2
        ivtu += w * (got[("q", lo)] * got[("u", lo)] + got[("q", hi)] * got[("u", hi)])
        ivtv += w * (got[("q", lo)] * got[("v", lo)] + got[("q", hi)] * got[("v", hi)])
    return {"ivtu": ivtu, "ivtv": ivtv, "pw": got["pw"], "u850": got[("u", 850)], "v850": got[("v", 850)], "tp": got["tp"]}


def build(model, run, out):
    fetch = gfs_fields if model == "gfs" else aifs_fields
    frames, prev_tp = [], 0.0
    for f in LEADS:
        lay = layers_at(fetch(run, f))
        lay["rain12"] = np.maximum(lay.pop("tp") - prev_tp, 0)
        prev_tp = lay["rain12"] + prev_tp
        frames.append(lay)
        print(f"  {model} +{f:3d} h", flush=True)

    r0, r1 = round((90 - DETAIL["lat0"]) * 4), round((90 - DETAIL["lat1"]) * 4)
    c0, c1 = round((DETAIL["lon0"] + 180) * 4), round((DETAIL["lon1"] + 180) * 4)
    os.makedirs(os.path.join(out, "detail"), exist_ok=True)
    layers, detail = {}, {}
    for name, (lo, hi) in RANGES.items():
        quantize(np.stack([to_one_degree(fr[name]) for fr in frames]), lo, hi).tofile(os.path.join(out, f"{name}.bin"))
        quantize(np.stack([fr[name][r0:r1 + 1, c0:c1 + 1] for fr in frames]), lo, hi).tofile(os.path.join(out, "detail", f"{name}.bin"))
        layers[name] = {"file": f"{name}.bin", "vmin": lo, "vmax": hi}
        detail[name] = {"file": f"detail/{name}.bin", "vmin": lo, "vmax": hi}
    meta = {
        "model": model, "name": MODELS[model]["name"], "pwName": MODELS[model]["pw"], "source": MODELS[model]["source"],
        "run": f"{run:%Y-%m-%dT%H:%M}", "created": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M"), "leads": LEADS,
        "grid": {"nlat": 181, "nlon": 360, "lat0": 90, "lon0": -180, "d": 1},
        "times": [f"{run + dt.timedelta(hours=f):%Y-%m-%dT%H:%M}" for f in LEADS],
        "layers": layers,
        "detail": {"grid": {"nlat": r1 - r0 + 1, "nlon": c1 - c0 + 1, "lat0": DETAIL["lat0"], "lon0": DETAIL["lon0"], "d": 0.25}, "layers": detail},
    }
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    rain = max(fr["rain12"].max() for fr in frames)
    ivt = max(np.hypot(fr["ivtu"], fr["ivtv"]).max() for fr in frames)
    print(f"Done: {model} run {meta['run']} UTC; max IVT {ivt:.0f} kg/m/s, max 12 h rain {rain:.0f} mm, "
          f"5-day rain total max {prev_tp.max():.0f} mm", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join("data", "forecast"))
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    args = ap.parse_args()
    now = dt.datetime.utcnow()
    failed = []
    for model in args.models:
        out = os.path.join(args.out, model)
        try:
            run = latest_run(model, now)
            try:
                have = json.load(open(os.path.join(out, "meta.json")))["run"]
            except (FileNotFoundError, KeyError, ValueError):
                have = None
            if have == f"{run:%Y-%m-%dT%H:%M}":
                print(f"{model}: run {have} UTC already built")
                continue
            print(f"{model}: building run {run:%Y-%m-%d %H} UTC", flush=True)
            build(model, run, out)
        except Exception as e:  # keep the other model and any earlier output
            print(f"{model}: failed ({e!r}); keeping what was there", flush=True)
            failed.append(model)
    return 1 if failed and len(failed) == len(args.models) else 0


if __name__ == "__main__":
    sys.exit(main())
