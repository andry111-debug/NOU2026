# -*- coding: utf-8 -*-
"""
Карта регионов-источников и получателей продовольственной инфляции (RQ4, задача 9).

Метод (объяснимый на защите):
1. Панель месячной food-инфляции 2015-2025, очищенная от региональных и
   временных средних (те же фикс-эффекты, что в модели).
2. Для каждой пары соседей (a,b): corr(a[t-1], b[t]) — «a ведёт b», и наоборот.
   Лаг 1 месяц — пик передачи по оценкам spatial-lag модели.
3. Регион: out = среднее «я веду соседей», in = среднее «соседи ведут меня»,
   net = out - in.
4. Классы: верхний квартиль net — источник; нижний — получатель; середина
   с активностью (out+in)/2 выше медианы — транзит; остальные — нейтральные.

Выходы: CSV оценок + 2 PNG-карты (net и классы).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_spatial_model as bsm

APP = Path(__file__).resolve().parent.parent
GEO = APP / "data" / "geo"
OUT = APP / "index_lab_output" / "base_model"
OUT.mkdir(parents=True, exist_ok=True)

CODE_ALIAS = {"CHU": "Чукотский автономный округ"}
LEAD_LAG = 1


def within_transform(panel: pd.DataFrame) -> pd.DataFrame:
    x = panel.copy()
    col_mean = x.mean(axis=0)
    row_mean = x.mean(axis=1)
    all_mean = float(np.nanmean(x.values))
    return x.sub(col_mean, axis=1).sub(row_mean, axis=0).add(all_mean)


def main() -> int:
    panel, meta = bsm.load_panel()
    w = within_transform(panel)
    edges = pd.read_csv(GEO / "adjacency_subjects.csv", encoding="utf-8-sig")

    lead: dict[str, list[float]] = {s: [] for s in panel.columns}
    follow: dict[str, list[float]] = {s: [] for s in panel.columns}
    used_pairs = 0
    for a, b in zip(edges["subject_a"], edges["subject_b"]):
        if a not in w.columns or b not in w.columns:
            continue
        ab = w[a].shift(LEAD_LAG).corr(w[b])   # a ведёт b
        ba = w[b].shift(LEAD_LAG).corr(w[a])   # b ведёт a
        if pd.isna(ab) or pd.isna(ba):
            continue
        lead[a].append(ab); follow[b].append(ab)
        lead[b].append(ba); follow[a].append(ba)
        used_pairs += 1
    print(f"pairs used: {used_pairs}/{len(edges)}")

    rows = []
    for s in panel.columns:
        out_r = float(np.mean(lead[s])) if lead[s] else np.nan
        in_r = float(np.mean(follow[s])) if follow[s] else np.nan
        rows.append({
            "subject": s,
            "n_neighbours": len(lead[s]),
            "out_influence": round(out_r, 4) if lead[s] else np.nan,
            "in_influence": round(in_r, 4) if follow[s] else np.nan,
            "net": round(out_r - in_r, 4) if lead[s] else np.nan,
            "activity": round((out_r + in_r) / 2, 4) if lead[s] else np.nan,
        })
    df = pd.DataFrame(rows)

    have = df["net"].notna()
    q75 = df.loc[have, "net"].quantile(0.75)
    q25 = df.loc[have, "net"].quantile(0.25)
    act_med = df.loc[have, "activity"].median()

    def classify(r):
        if pd.isna(r["net"]):
            return "нет соседей"
        if r["net"] >= q75:
            return "источник"
        if r["net"] <= q25:
            return "получатель"
        return "транзит" if r["activity"] >= act_med else "нейтральный"

    df["class"] = df.apply(classify, axis=1)
    df = df.sort_values("net", ascending=False)
    df.to_csv(OUT / "source_receiver_scores.csv", index=False, encoding="utf-8-sig")
    print("saved:", OUT / "source_receiver_scores.csv")
    print("\nТоп-8 источников:")
    for _, r in df.head(8).iterrows():
        print(f"  {r['subject']}: net={r['net']:+.3f} (out={r['out_influence']:.3f}, in={r['in_influence']:.3f})")
    print("Топ-8 получателей:")
    for _, r in df[df["net"].notna()].tail(8).iloc[::-1].iterrows():
        print(f"  {r['subject']}: net={r['net']:+.3f} (out={r['out_influence']:.3f}, in={r['in_influence']:.3f})")

    # --- геометрия для карт ---
    harm = pd.read_csv(GEO / "fedstat_region_harmonization.csv", encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    code2subject = {c: s for c, s in zip(harm["region_code"], harm["canonical_region"])
                    if isinstance(c, str) and c}
    gj = json.loads((GEO / "custom_geoboundaries_rus_adm1.geojson").read_text(encoding="utf-8"))
    geoms: dict[str, object] = {}
    for f in gj["features"]:
        iso = f["properties"].get("shapeISO", "")
        if not iso.startswith("RU-"):
            continue
        subj = code2subject.get(iso[3:]) or CODE_ALIAS.get(iso[3:])
        if subj:
            geoms[subj] = shape(f["geometry"]).simplify(0.02, preserve_topology=True)

    def draw_poly(ax, geom, color):
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            xs, ys = p.exterior.xy
            xs = [x + 360 if x < 0 else x for x in xs]
            ax.fill(xs, ys, color=color, linewidth=0.3, edgecolor="#555555")

    by_subject = df.set_index("subject")

    # Карта 1: непрерывный net
    fig, ax = plt.subplots(figsize=(16, 9))
    vmax = float(df.loc[have, "net"].abs().quantile(0.95))
    cmap = plt.get_cmap("RdBu_r")
    for subj, geom in geoms.items():
        if subj in by_subject.index and not pd.isna(by_subject.loc[subj, "net"]):
            v = float(by_subject.loc[subj, "net"])
            t = max(-1.0, min(1.0, v / vmax if vmax else 0.0))
            draw_poly(ax, geom, cmap(0.5 + t / 2))
        else:
            draw_poly(ax, geom, "#d9d9d9")
    ax.set_title("Чистое влияние региона в распространении продовольственной инфляции, 2015–2025\n"
                 "красный — источник (ведёт соседей), синий — получатель (следует за соседями)",
                 fontsize=13)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-vmax, vmax))
    fig.colorbar(sm, ax=ax, shrink=0.5, label="net = исходящее − входящее влияние (лаг 1 мес.)")
    ax.set_aspect(2.0); ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "source_receiver_net_map.png", dpi=200)
    plt.close(fig)

    # Карта 2: классы
    colors = {"источник": "#c0392b", "получатель": "#2980b9",
              "транзит": "#f39c12", "нейтральный": "#cccccc", "нет соседей": "#8d8d8d"}
    fig, ax = plt.subplots(figsize=(16, 9))
    for subj, geom in geoms.items():
        cls = by_subject.loc[subj, "class"] if subj in by_subject.index else "нет соседей"
        draw_poly(ax, geom, colors.get(cls, "#d9d9d9"))
    ax.set_title("Классификация регионов по роли в распространении продовольственной инфляции, 2015–2025",
                 fontsize=14)
    ax.legend(handles=[Patch(facecolor=c, label=l) for l, c in colors.items()],
              loc="lower left", fontsize=11)
    ax.set_aspect(2.0); ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / "source_receiver_class_map.png", dpi=200)
    plt.close(fig)
    print("maps saved:", OUT / "source_receiver_net_map.png", "|", OUT / "source_receiver_class_map.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
