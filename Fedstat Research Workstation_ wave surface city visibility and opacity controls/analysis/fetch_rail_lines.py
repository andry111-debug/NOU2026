# -*- coding: utf-8 -*-
"""
W_rail v2 (D17): матрица «регионы соединены прямой ЖД-магистралью».

Качаем из OSM магистральные пути (railway=rail, usage=main) с геометрией.
Для каждого way смотрим последовательные узлы: если соседние узлы лежат в
разных субъектах — магистраль пересекает границу, пара получает связь.
Вес пары = число пересекающих way'ев (прокси числа линий/путей).

Выход (в git): data/geo/rail_links_subjects.csv (subject_a, subject_b, n_ways)
Сырой JSON: data/geo/osm_rail_lines_raw.json (gitignored).
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.parse
import urllib.request as u
from collections import defaultdict
from pathlib import Path

import pandas as pd
from shapely.geometry import shape, Point
from shapely import STRtree

APP = Path(__file__).resolve().parent.parent
GEO = APP / "data" / "geo"
RAW_JSON = GEO / "osm_rail_lines_raw.json"
OUT_CSV = GEO / "rail_links_subjects.csv"
CODE_ALIAS = {"CHU": "Чукотский автономный округ"}

# Всероссийский запрос с геометрией не тянут зеркала Overpass (504) —
# режем на долготные полосы и склеиваем с дедупликацией по way id.
WAY_FILTER = '["railway"="rail"]["usage"="main"]'
LON_BANDS = [(19, 40), (40, 60), (60, 80), (80, 100), (100, 120),
             (120, 140), (140, 160), (160, 180), (-180, -168)]
LAT_MIN, LAT_MAX = 41.0, 82.0

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def log(*a):
    print(*a, flush=True)


def fetch() -> dict:
    import time as _t
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx))
    elements: dict[int, dict] = {}
    for lon0, lon1 in LON_BANDS:
        q = (f"[out:json][timeout:600];"
             f"way{WAY_FILTER}({LAT_MIN},{lon0},{LAT_MAX},{lon1});"
             f"out geom;")
        body = urllib.parse.urlencode({"data": q}).encode()
        got = None
        for ep in ENDPOINTS:
            for attempt in (1, 2):
                try:
                    log(f"POST band {lon0}..{lon1} -> {ep} (try {attempt})")
                    req = u.Request(ep, data=body, headers={"User-Agent": "nou2027-research/1.0"})
                    with op.open(req, timeout=900) as r:
                        got = json.loads(r.read().decode("utf-8"))
                    break
                except Exception as exc:
                    log(f"  failed: {type(exc).__name__}: {exc}")
                    _t.sleep(20)
            if got is not None:
                break
        if got is None:
            raise RuntimeError(f"band {lon0}..{lon1} failed on all endpoints")
        n_new = 0
        for el in got.get("elements", []):
            if el.get("type") == "way" and el["id"] not in elements:
                elements[el["id"]] = el
                n_new += 1
        log(f"  band ways: {len(got.get('elements', []))} (new {n_new}, total {len(elements)})")
        _t.sleep(10)
    return {"elements": list(elements.values())}


def main() -> int:
    if RAW_JSON.exists() and RAW_JSON.stat().st_size > 1000:
        log(f"reuse cached {RAW_JSON.name} ({RAW_JSON.stat().st_size/1e6:.0f} MB)")
        data = json.loads(RAW_JSON.read_text(encoding="utf-8"))
    else:
        data = fetch()
        RAW_JSON.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        log(f"raw saved: {RAW_JSON} ({RAW_JSON.stat().st_size/1e6:.0f} MB)")

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

    def region_of(lon: float, lat: float, cache: dict) -> str | None:
        key = (round(lon, 3), round(lat, 3))
        if key in cache:
            return cache[key]
        hit = tree.query(Point(lon, lat), predicate="intersects")
        res = names[int(hit[0])] if len(hit) else None
        cache[key] = res
        return res

    pair_ways: dict[tuple[str, str], set] = defaultdict(set)
    cache: dict = {}
    n_ways = 0
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        n_ways += 1
        prev = None
        for nd in el["geometry"]:
            reg = region_of(nd["lon"], nd["lat"], cache)
            if reg and prev and reg != prev:
                a, b = sorted((prev, reg))
                pair_ways[(a, b)].add(el["id"])
            if reg:
                prev = reg
    log(f"ways processed: {n_ways}; crossing pairs: {len(pair_ways)}")

    rows = [{"subject_a": a, "subject_b": b, "n_ways": len(w)}
            for (a, b), w in sorted(pair_ways.items())]
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT_CSV} links={len(rows)}")

    deg = defaultdict(int)
    for r in rows:
        deg[r["subject_a"]] += 1; deg[r["subject_b"]] += 1
    connected = len(deg)
    log(f"subjects with >=1 rail link: {connected}")
    top = sorted(rows, key=lambda r: -r["n_ways"])[:6]
    for r in top:
        log(f"  {r['subject_a']} — {r['subject_b']}: {r['n_ways']} ways")
    return 0


if __name__ == "__main__":
    sys.exit(main())
