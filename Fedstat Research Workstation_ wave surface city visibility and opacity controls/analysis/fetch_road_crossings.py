# -*- coding: utf-8 -*-
"""
D16 v1: дорожная пропускная способность границ (полосность).

Качаем из OSM федеральные магистрали (highway=motorway|trunk) с геометрией и
тегом lanes. Для каждого way: последовательные узлы в разных субъектах =
пересечение границы; вес пары += полосность way (lanes; по умолчанию 2).

Выход (в git): data/geo/road_capacity_links.csv
    (subject_a, subject_b, n_ways, total_lanes)
Сырой JSON: data/geo/osm_road_lines_raw.json (gitignored).
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
RAW_JSON = GEO / "osm_road_lines_raw.json"
OUT_CSV = GEO / "road_capacity_links.csv"
CODE_ALIAS = {"CHU": "Чукотский автономный округ"}

# Полосовое скачивание (как в fetch_rail_lines): всероссийский запрос
# с геометрией зеркала Overpass не тянут.
WAY_FILTER = '["highway"~"^(motorway|trunk)$"]'
LON_BANDS = [(19, 40), (40, 60), (60, 80), (80, 100), (100, 120),
             (120, 140), (140, 160), (160, 180), (-180, -168)]
LAT_MIN, LAT_MAX = 41.0, 82.0

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
DEFAULT_LANES = 2.0


def log(*a):
    print(*a, flush=True)


CACHE_DIR = GEO / "cache"


def fetch_band(op, lon0: float, lon1: float, depth: int = 0) -> list[dict] | None:
    """Одна полоса с кэшем на диске; при провале — деление пополам."""
    import time as _t
    cache = CACHE_DIR / f"road_band_{lon0}_{lon1}.json"
    if cache.exists() and cache.stat().st_size > 100:
        got = json.loads(cache.read_text(encoding="utf-8"))
        log(f"  band {lon0}..{lon1}: cached ({len(got)} ways)")
        return got
    q = (f"[out:json][timeout:600];"
         f"way{WAY_FILTER}({LAT_MIN},{lon0},{LAT_MAX},{lon1});"
         f"out geom;")
    body = urllib.parse.urlencode({"data": q}).encode()
    for ep in ENDPOINTS:
        for attempt in (1, 2):
            try:
                log(f"POST band {lon0}..{lon1} -> {ep} (try {attempt})")
                req = u.Request(ep, data=body, headers={"User-Agent": "nou2027-research/1.0"})
                with op.open(req, timeout=900) as r:
                    got = json.loads(r.read().decode("utf-8"))
                ways = [el for el in got.get("elements", []) if el.get("type") == "way"]
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(ways, ensure_ascii=False), encoding="utf-8")
                log(f"  band {lon0}..{lon1}: {len(ways)} ways (cached)")
                _t.sleep(10)
                return ways
            except Exception as exc:
                log(f"  failed: {type(exc).__name__}: {exc}")
                _t.sleep(30)
    if lon1 - lon0 > 5 and depth < 3:
        mid = (lon0 + lon1) / 2
        log(f"  band {lon0}..{lon1}: splitting at {mid}")
        left = fetch_band(op, lon0, mid, depth + 1)
        right = fetch_band(op, mid, lon1, depth + 1)
        if left is not None and right is not None:
            return left + right
    return None


def fetch() -> dict:
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx))
    elements: dict[int, dict] = {}
    failed = []
    for lon0, lon1 in LON_BANDS:
        ways = fetch_band(op, lon0, lon1)
        if ways is None:
            failed.append((lon0, lon1))
            continue
        for el in ways:
            elements.setdefault(el["id"], el)
        log(f"  total unique ways: {len(elements)}")
    if failed:
        raise RuntimeError(f"bands failed even after splitting: {failed}")
    return {"elements": list(elements.values())}


def lanes_of(tags: dict) -> float:
    try:
        return float(str(tags.get("lanes", "")).split(";")[0])
    except Exception:
        return DEFAULT_LANES


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
    pair_lanes: dict[tuple[str, str], float] = defaultdict(float)
    cache: dict = {}
    n_ways = 0
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        n_ways += 1
        ln = lanes_of(el.get("tags", {}))
        prev = None
        for nd in el["geometry"]:
            reg = region_of(nd["lon"], nd["lat"], cache)
            if reg and prev and reg != prev:
                a, b = sorted((prev, reg))
                if el["id"] not in pair_ways[(a, b)]:
                    pair_ways[(a, b)].add(el["id"])
                    pair_lanes[(a, b)] += ln
            if reg:
                prev = reg
    log(f"ways processed: {n_ways}; crossing pairs: {len(pair_ways)}")

    rows = [{"subject_a": a, "subject_b": b,
             "n_ways": len(w), "total_lanes": round(pair_lanes[(a, b)], 1)}
            for (a, b), w in sorted(pair_ways.items())]
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT_CSV} links={len(rows)}")
    top = sorted(rows, key=lambda r: -r["total_lanes"])[:6]
    for r in top:
        log(f"  {r['subject_a']} — {r['subject_b']}: lanes={r['total_lanes']} ways={r['n_ways']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
