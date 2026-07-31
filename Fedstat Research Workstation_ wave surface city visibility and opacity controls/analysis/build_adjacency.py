# -*- coding: utf-8 -*-
"""
Матрица СОСЕДСТВА субъектов РФ (общая граница) для spatial-lag модели.

Источник геометрии: data/geo/custom_geoboundaries_rus_adm1.geojson (geoBoundaries ADM1),
регионы помечены shapeISO вида 'RU-ALT'. Сопоставляем с 85 субъектами по region_code.

Для скорости геометрии упрощаются (tol град.), затем соседи ищутся через STRtree:
i~j, если buffer(EPS) региона i пересекает регион j  (т.е. расстояние между границами < EPS,
мостит мелкие зазоры упрощённых полигонов). Итог — отслеживаемый edge-list, не требующий
самого geojson на других станциях.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import shape
from shapely import STRtree

APP = Path(__file__).resolve().parent.parent
GEO = APP / "data" / "geo"
GJ = GEO / "custom_geoboundaries_rus_adm1.geojson"
# Гармонизация — ТОТ ЖЕ файл, что строит субъекты панели (canonical_region),
# чтобы имена соседства точно совпадали с именами субъектов в модели.
HARM = GEO / "fedstat_region_harmonization.csv"
OUT_EDGES = GEO / "adjacency_subjects.csv"

SIMP_TOL = 0.01   # градусы, упрощение геометрии (~1 км)
EPS = 0.05        # градусы, порог "почти касаются"

# geojson-код -> имя субъекта, когда region_code в справочнике пуст/иной.
# Чукотка: в справочнике region_code пуст, а в geoBoundaries это RU-CHU.
CODE_ALIAS = {"CHU": "Чукотский автономный округ"}
# Крым и Севастополь отсутствуют в geoBoundaries ADM1 (спорные территории) — геометрии нет.


def log(*a):
    print(*a, flush=True)


def load_geoms() -> dict[str, object]:
    gj = json.loads(GJ.read_text(encoding="utf-8"))
    geoms: dict[str, object] = {}
    for f in gj["features"]:
        iso = f["properties"].get("shapeISO", "")
        if not iso.startswith("RU-"):
            continue
        g = shape(f["geometry"]).simplify(SIMP_TOL, preserve_topology=True)
        if not g.is_valid:
            g = g.buffer(0)
        geoms[iso[3:]] = g
    return geoms


def neighbors_at(glist, tree, eps):
    edges = set()
    for i, gi in enumerate(glist):
        buf = gi.buffer(eps)
        for j in tree.query(buf, predicate="intersects"):
            j = int(j)
            if j != i:
                edges.add((min(i, j), max(i, j)))
    return edges


def main() -> int:
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    code2subject = {c: s for c, s in zip(harm["region_code"], harm["canonical_region"])
                    if isinstance(c, str) and c}
    subjects_all = set(harm["canonical_region"])

    log("loading + simplifying geometries...")
    geoms = load_geoms()
    log(f"geojson RU features: {len(geoms)}; subjects in reference: {len(subjects_all)}")

    def subj_for(code: str):
        if code in code2subject:
            return code2subject[code]
        return CODE_ALIAS.get(code)

    codes = [c for c in geoms if subj_for(c)]
    unmatched_geo = sorted(c for c in geoms if not subj_for(c))
    matched_subjects = {subj_for(c) for c in codes}
    subjects_no_geom = sorted(subjects_all - matched_subjects)
    log(f"matched: {len(codes)}; geojson codes w/o subject: {unmatched_geo}")
    log(f"subjects WITHOUT geometry: {subjects_no_geom}")

    names = [subj_for(c) for c in codes]
    glist = [geoms[c] for c in codes]
    tree = STRtree(glist)

    log("\n=== eps sweep (edges / degree min-med-max / isolated) ===")
    for eps in (0.02, 0.05, 0.1):
        edges = neighbors_at(glist, tree, eps)
        deg = [0] * len(glist)
        for a, b in edges:
            deg[a] += 1; deg[b] += 1
        iso = [names[k] for k in range(len(glist)) if deg[k] == 0]
        sdeg = sorted(deg)
        log(f"  eps={eps:<5} edges={len(edges):<4} deg={min(deg)}/{sdeg[len(sdeg)//2]}/{max(deg)} isolated={iso}")

    edges = neighbors_at(glist, tree, EPS)
    rows = [{"subject_a": names[a], "subject_b": names[b]} for a, b in sorted(edges)]
    pd.DataFrame(rows).to_csv(OUT_EDGES, index=False, encoding="utf-8-sig")
    log(f"\nEPS={EPS}: {len(rows)} undirected edges -> {OUT_EDGES}")

    neigh: dict[str, list[str]] = {n: [] for n in names}
    for a, b in edges:
        neigh[names[a]].append(names[b]); neigh[names[b]].append(names[a])
    for code in ("MOW", "MOS", "KGD", "SPE", "LEN"):
        if code in code2subject and code2subject[code] in neigh:
            s = code2subject[code]
            log(f"  {code} {s}: {len(neigh[s])} neighbours -> {sorted(neigh[s])[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
