# -*- coding: utf-8 -*-
"""
Климат D19 v1: месячные температурные АНОМАЛИИ по субъектам РФ из NOAA GHCN-M v4.

Источник: ghcnm.tavg.latest.qcf.tar.gz (QC-adjusted, без регистрации).
Станции РФ (код страны RS) -> точка-в-полигоне ADM1 -> средняя по станциям
региона -> аномалия = значение − нормаль региона за 1991-2020 для этого
календарного месяца.

Выход (в git): data/climate/temp_anomaly_by_region.csv
Сырой архив: data/climate/raw/ (gitignored).
"""
from __future__ import annotations

import io
import json
import ssl
import sys
import tarfile
import urllib.request as u
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape, Point
from shapely import STRtree

APP = Path(__file__).resolve().parent.parent
GEO = APP / "data" / "geo"
CLIM = APP / "data" / "climate"
RAW = CLIM / "raw"
OUT_CSV = CLIM / "temp_anomaly_by_region.csv"

URL = "https://www.ncei.noaa.gov/pub/data/ghcn/v4/ghcnm.tavg.latest.qcf.tar.gz"
CODE_ALIAS = {"CHU": "Чукотский автономный округ"}
BASE_Y0, BASE_Y1 = 1991, 2020        # климатическая нормаль
OUT_Y0, OUT_Y1 = 2014, 2026          # период выгрузки аномалий (с запасом на лаги)
MIN_BASE_YEARS = 8                   # минимум лет в нормали


def log(*a):
    print(*a, flush=True)


def download() -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dst = RAW / "ghcnm_tavg_qcf.tar.gz"
    if dst.exists() and dst.stat().st_size > 1_000_000:
        log(f"reuse cached {dst.name} ({dst.stat().st_size/1e6:.1f} MB)")
        return dst
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx))
    log(f"downloading {URL} ...")
    req = u.Request(URL, headers={"User-Agent": "nou2027-research/1.0"})
    with op.open(req, timeout=900) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    log(f"saved {dst.name} ({dst.stat().st_size/1e6:.1f} MB)")
    return dst


def read_members(tgz: Path) -> tuple[str, str]:
    with tarfile.open(tgz, "r:gz") as tf:
        inv_name = dat_name = None
        for m in tf.getmembers():
            if m.name.endswith(".inv"):
                inv_name = m.name
            elif m.name.endswith(".dat"):
                dat_name = m.name
        if not inv_name or not dat_name:
            raise RuntimeError("inv/dat not found in archive")
        inv = tf.extractfile(inv_name).read().decode("utf-8", "replace")
        dat = tf.extractfile(dat_name).read().decode("utf-8", "replace")
    log(f"members: {inv_name}, {dat_name}")
    return inv, dat


def main() -> int:
    tgz = download()
    inv_text, dat_text = read_members(tgz)

    # --- станции РФ ---
    stations: dict[str, tuple[float, float]] = {}
    for line in inv_text.splitlines():
        if not line.startswith("RSM"):
            continue
        sid = line[0:11]
        try:
            lat = float(line[12:20]); lon = float(line[21:30])
        except ValueError:
            continue
        stations[sid] = (lat, lon)
    log(f"RU stations in inventory: {len(stations)}")

    # --- полигоны ---
    harm = pd.read_csv(GEO / "fedstat_region_harmonization.csv", encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    code2subject = {c: s for c, s in zip(harm["region_code"], harm["canonical_region"])
                    if isinstance(c, str) and c}
    gj = json.loads((GEO / "custom_geoboundaries_rus_adm1.geojson").read_text(encoding="utf-8"))
    names, geoms = [], []
    for f in gj["features"]:
        iso = f["properties"].get("shapeISO", "")
        if not iso.startswith("RU-"):
            continue
        subj = code2subject.get(iso[3:]) or CODE_ALIAS.get(iso[3:])
        if not subj:
            continue
        g = shape(f["geometry"]).simplify(0.02, preserve_topology=True)
        if not g.is_valid:
            g = g.buffer(0)
        names.append(subj); geoms.append(g)
    tree = STRtree(geoms)

    st2region: dict[str, str] = {}
    for sid, (lat, lon) in stations.items():
        hit = tree.query(Point(lon, lat), predicate="intersects")
        if len(hit):
            st2region[sid] = names[int(hit[0])]
    log(f"stations matched to regions: {len(st2region)}")

    # --- разбор .dat: только станции РФ, годы >= BASE_Y0 ---
    # region -> (year, month) -> list of temps
    acc: dict[str, dict[tuple[int, int], list[float]]] = defaultdict(lambda: defaultdict(list))
    n_lines = 0
    for line in dat_text.splitlines():
        sid = line[0:11]
        reg = st2region.get(sid)
        if reg is None:
            continue
        if line[15:19] != "TAVG":
            continue
        try:
            year = int(line[11:15])
        except ValueError:
            continue
        if year < BASE_Y0 or year > OUT_Y1:
            continue
        n_lines += 1
        for m in range(12):
            v = line[19 + 8 * m: 24 + 8 * m]
            try:
                val = int(v)
            except ValueError:
                continue
            if val == -9999:
                continue
            acc[reg][(year, m + 1)].append(val / 100.0)
    log(f"station-year lines used: {n_lines}")

    # --- средняя по региону и аномалии ---
    rows = []
    regions_covered = 0
    for reg, series in acc.items():
        month_mean = {k: float(np.mean(v)) for k, v in series.items()}
        base: dict[int, list[float]] = defaultdict(list)
        for (y, m), t in month_mean.items():
            if BASE_Y0 <= y <= BASE_Y1:
                base[m].append(t)
        normal = {m: float(np.mean(v)) for m, v in base.items() if len(v) >= MIN_BASE_YEARS}
        if len(normal) < 12:
            log(f"  skip {reg}: normals only for {len(normal)} months")
            continue
        regions_covered += 1
        for (y, m), t in sorted(month_mean.items()):
            if OUT_Y0 <= y <= OUT_Y1:
                rows.append({
                    "region": reg,
                    "period": f"{y}-{m:02d}",
                    "t_anomaly": round(t - normal[m], 2),
                    "n_stations": len(series[(y, m)]),
                })
    log(f"regions with full normals: {regions_covered}")

    CLIM.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows).sort_values(["region", "period"])
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT_CSV} rows={len(out)} "
        f"period={out['period'].min()}..{out['period'].max()}")

    cover = out.groupby("region")["n_stations"].mean().sort_values()
    log("lowest station coverage (mean stations/month):")
    for reg, v in cover.head(6).items():
        log(f"  {reg}: {v:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
