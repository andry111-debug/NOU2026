# -*- coding: utf-8 -*-
"""
ЖД-слой v1 (D17): вокзалы/станции из OSM -> счётчик по субъектам РФ.

Качает railway=station по России из Overpass, фильтрует метро/лёгкое метро,
привязывает точки к полигонам ADM1 (те же геометрии, что в build_adjacency)
и пишет отслеживаемый data/geo/rail_stations_by_region.csv.

Сырой JSON сохраняется в data/geo/osm_rail_stations_raw.json (gitignored).
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.parse
import urllib.request as u
from pathlib import Path

import pandas as pd
from shapely.geometry import shape, Point
from shapely import STRtree

APP = Path(__file__).resolve().parent.parent
GEO = APP / "data" / "geo"
GJ = GEO / "custom_geoboundaries_rus_adm1.geojson"
HARM = GEO / "fedstat_region_harmonization.csv"
RAW_JSON = GEO / "osm_rail_stations_raw.json"
OUT_CSV = GEO / "rail_stations_by_region.csv"

CODE_ALIAS = {"CHU": "Чукотский автономный округ"}
EXCLUDE_STATION = {"subway", "light_rail", "monorail", "funicular"}

QUERY = """
[out:json][timeout:300];
area(3600060189)->.ru;
(
  node["railway"="station"](area.ru);
  way["railway"="station"](area.ru);
  relation["railway"="station"](area.ru);
);
out center tags;
"""

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def log(*a):
    print(*a, flush=True)


def fetch() -> dict:
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx))
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    last = None
    for ep in ENDPOINTS:
        try:
            log(f"POST {ep} ...")
            req = u.Request(ep, data=body, headers={"User-Agent": "nou2027-research/1.0"})
            with op.open(req, timeout=600) as r:
                data = json.loads(r.read().decode("utf-8"))
            log(f"  got {len(data.get('elements', []))} elements")
            return data
        except Exception as exc:
            last = exc
            log(f"  failed: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"All Overpass endpoints failed: {last}")


def main() -> int:
    if RAW_JSON.exists():
        log(f"reuse cached {RAW_JSON.name}")
        data = json.loads(RAW_JSON.read_text(encoding="utf-8"))
    else:
        data = fetch()
        RAW_JSON.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log(f"raw saved: {RAW_JSON}")

    pts = []
    skipped = 0
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if tags.get("railway") != "station":
            continue
        if tags.get("station", "") in EXCLUDE_STATION:
            skipped += 1
            continue
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        pts.append((lon, lat))
    log(f"stations kept: {len(pts)}; excluded (metro etc.): {skipped}")

    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    code2subject = {c: s for c, s in zip(harm["region_code"], harm["canonical_region"])
                    if isinstance(c, str) and c}

    gj = json.loads(GJ.read_text(encoding="utf-8"))
    names, geoms = [], []
    for f in gj["features"]:
        iso = f["properties"].get("shapeISO", "")
        if not iso.startswith("RU-"):
            continue
        code = iso[3:]
        subj = code2subject.get(code) or CODE_ALIAS.get(code)
        if not subj:
            continue
        g = shape(f["geometry"]).simplify(0.01, preserve_topology=True)
        if not g.is_valid:
            g = g.buffer(0)
        names.append(subj)
        geoms.append(g)
    log(f"polygons: {len(geoms)}")

    tree = STRtree(geoms)
    counts = {n: 0 for n in names}
    unmatched = 0
    for lon, lat in pts:
        p = Point(lon, lat)
        hit = tree.query(p, predicate="intersects")
        if len(hit):
            counts[names[int(hit[0])]] += 1
        else:
            unmatched += 1
    log(f"points outside polygons: {unmatched}")

    out = pd.DataFrame(sorted(counts.items()), columns=["subject", "rail_stations"])
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT_CSV}")

    top = out.sort_values("rail_stations", ascending=False)
    log("top-10:")
    for _, r in top.head(10).iterrows():
        log(f"  {r['subject']}: {r['rail_stations']}")
    log("zero-station subjects:")
    log("  " + "; ".join(top[top["rail_stations"] == 0]["subject"].tolist()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
