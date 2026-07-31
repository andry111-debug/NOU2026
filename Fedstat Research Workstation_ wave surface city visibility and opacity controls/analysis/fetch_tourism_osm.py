# -*- coding: utf-8 -*-
"""
D20 v1: туристическая инфраструктура из OSM — отели и рестораны по субъектам РФ.

Выход (в git): data/geo/tourism_poi_by_region.csv (subject, hotels, restaurants).
Сырой JSON: data/geo/osm_tourism_raw.json (gitignored).
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
RAW_JSON = GEO / "osm_tourism_raw.json"
OUT_CSV = GEO / "tourism_poi_by_region.csv"
CODE_ALIAS = {"CHU": "Чукотский автономный округ"}

QUERY = """
[out:json][timeout:600];
area(3600060189)->.ru;
(
  node["tourism"="hotel"](area.ru);
  way["tourism"="hotel"](area.ru);
  node["amenity"="restaurant"](area.ru);
  way["amenity"="restaurant"](area.ru);
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
            with op.open(req, timeout=900) as r:
                data = json.loads(r.read().decode("utf-8"))
            log(f"  got {len(data.get('elements', []))} elements")
            return data
        except Exception as exc:
            last = exc
            log(f"  failed: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"All Overpass endpoints failed: {last}")


def main() -> int:
    if RAW_JSON.exists() and RAW_JSON.stat().st_size > 1000:
        log(f"reuse cached {RAW_JSON.name}")
        data = json.loads(RAW_JSON.read_text(encoding="utf-8"))
    else:
        data = fetch()
        RAW_JSON.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log(f"raw saved: {RAW_JSON}")

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
    log(f"polygons: {len(geoms)}")

    counts = {n: {"hotels": 0, "restaurants": 0} for n in names}
    outside = 0
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if tags.get("tourism") == "hotel":
            kind = "hotels"
        elif tags.get("amenity") == "restaurant":
            kind = "restaurants"
        else:
            continue
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None:
            continue
        hit = tree.query(Point(lon, lat), predicate="intersects")
        if len(hit):
            counts[names[int(hit[0])]][kind] += 1
        else:
            outside += 1
    log(f"points outside polygons: {outside}")

    out = pd.DataFrame(
        [{"subject": n, **v} for n, v in sorted(counts.items())]
    )
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    tot_h, tot_r = out["hotels"].sum(), out["restaurants"].sum()
    log(f"saved: {OUT_CSV} (hotels={tot_h}, restaurants={tot_r})")
    top = out.assign(total=out["hotels"] + out["restaurants"]).sort_values("total", ascending=False)
    for _, r in top.head(8).iterrows():
        log(f"  {r['subject']}: hotels={r['hotels']} restaurants={r['restaurants']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
