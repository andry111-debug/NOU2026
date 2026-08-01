# -*- coding: utf-8 -*-
"""
Базовая spatial-lag модель межрегионального распространения продовольственной инфляции.
Соответствует задаче 4 концепции НОУ 2027 (минимальный обязательный набор).

Панель: субъект РФ x месяц, 2015-01..2023-01, 85 субъектов.
Модель (linearmodels PanelOLS, региональные + временные фикс-эффекты):

    infl[r,t] = a_r + d_t + Σ_L rho_L * incoming_W[r,t,L] + Σ_L beta_L * infl[r,t-L] + e

где incoming_W[r,t,L] = Σ_j W[r,j] * infl[j,t-L]  (W строчно-нормирована),
    infl[r,t] = value - 100  (месячная food-инфляция, % к предыдущему месяцу),
    a_r  — региональные FE (фиксированные региональные факторы, H4),
    d_t  — временные FE (общероссийские макрошоки, H4),
    infl[r,t-L] — собственные лаги (контроль внутренней инерции).

Варианты связей W (RQ3): общий федеральный округ; обратное расстояние между столицами.
Тестируется значимость транспортного (spatial-lag) члена против локального бейзлайна.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

APP = Path(__file__).resolve().parent.parent
DATA = APP / "data"
FOOD = DATA / "fedstat_targets" / "processed" / "target_ipc_food.csv"
HARM = DATA / "geo" / "fedstat_region_harmonization.csv"
ADJ = DATA / "geo" / "adjacency_subjects.csv"
RAIL = DATA / "geo" / "rail_stations_by_region.csv"
OUT = APP / "index_lab_output" / "base_model"
OUT.mkdir(parents=True, exist_ok=True)

START, END = "2015-01", "2025-12"  # основное окно концепции 2015-2025; данные есть до 2026-06
LAGS = [1, 2, 3, 6]


def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    food = pd.read_csv(FOOD, encoding="utf-8-sig")
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    keep = harm[harm["use_in_subject_panel"] == "yes"][
        ["fedstat_name", "canonical_region", "federal_district", "capital_lat", "capital_lon"]
    ].copy()
    df = food.merge(keep, left_on="region", right_on="fedstat_name", how="inner")
    df["subject"] = df["canonical_region"]
    df = df[(df["period"] >= START) & (df["period"] <= END)].copy()
    df["infl"] = df["value"].astype(float) - 100.0
    panel = (
        df.pivot_table(index="period", columns="subject", values="infl", aggfunc="mean")
        .sort_index()
    )
    meta = keep.drop_duplicates("canonical_region").set_index("canonical_region")
    meta = meta.reindex(panel.columns)
    return panel, meta


def haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    lat = np.radians(lat.astype(float))
    lon = np.radians(lon.astype(float))
    n = len(lat)
    d = np.zeros((n, n))
    R = 6371.0
    for i in range(n):
        dlat = lat - lat[i]
        dlon = lon - lon[i]
        a = np.sin(dlat / 2) ** 2 + np.cos(lat[i]) * np.cos(lat) * np.sin(dlon / 2) ** 2
        d[i] = 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return d


def rownorm(W: np.ndarray) -> np.ndarray:
    s = W.sum(axis=1, keepdims=True)
    s[s == 0] = 1.0
    return W / s


def build_weights(meta: pd.DataFrame) -> dict[str, np.ndarray]:
    subjects = list(meta.index)
    idx = {s: i for i, s in enumerate(subjects)}
    n = len(subjects)
    fd = meta["federal_district"].values
    W_fd = np.zeros((n, n))
    for i in range(n):
        same = (fd == fd[i])
        W_fd[i] = same.astype(float)
        W_fd[i, i] = 0.0
    dist = haversine_matrix(meta["capital_lat"].values, meta["capital_lon"].values)
    W_dist = np.zeros((n, n))
    mask = ~np.eye(n, dtype=bool)
    W_dist[mask] = 1.0 / dist[mask]
    np.fill_diagonal(W_dist, 0.0)
    # adjacency (shared border) from precomputed edge list
    W_adj = np.zeros((n, n))
    edges = pd.read_csv(ADJ, encoding="utf-8-sig")
    placed = 0
    for a, b in zip(edges["subject_a"], edges["subject_b"]):
        if a in idx and b in idx:
            W_adj[idx[a], idx[b]] = 1.0
            W_adj[idx[b], idx[a]] = 1.0
            placed += 1
    covered = int((W_adj.sum(axis=1) > 0).sum())
    print(f"adjacency: edges placed={placed}/{len(edges)}; "
          f"subjects with >=1 neighbour={covered}/{n}")
    out = {"fd": rownorm(W_fd), "dist": rownorm(W_dist), "adj": rownorm(W_adj)}
    # прямые ЖД-магистрали (D17 v2): вес = число пересекающих границу путей
    rail_links = DATA / "geo" / "rail_links_subjects.csv"
    if rail_links.exists():
        rl = pd.read_csv(rail_links, encoding="utf-8-sig")
        W_rl = np.zeros((n, n))
        for a, b, w in zip(rl["subject_a"], rl["subject_b"], rl["n_ways"]):
            if a in idx and b in idx:
                W_rl[idx[a], idx[b]] = float(w)
                W_rl[idx[b], idx[a]] = float(w)
        print(f"rail lines: links placed={int((W_rl > 0).sum() // 2)}, "
              f"subjects connected={int((W_rl.sum(axis=1) > 0).sum())}/{n}")
        out["railline"] = rownorm(W_rl)
    # дорожная пропускная способность границ (D16 v1): вес = суммарная полосность
    road_links = DATA / "geo" / "road_capacity_links.csv"
    if road_links.exists():
        rd = pd.read_csv(road_links, encoding="utf-8-sig")
        W_rd = np.zeros((n, n))
        for a, b, w in zip(rd["subject_a"], rd["subject_b"], rd["total_lanes"]):
            if a in idx and b in idx:
                W_rd[idx[a], idx[b]] = float(w)
                W_rd[idx[b], idx[a]] = float(w)
        print(f"road capacity: links placed={int((W_rd > 0).sum() // 2)}, "
              f"subjects connected={int((W_rd.sum(axis=1) > 0).sum())}/{n}")
        out["roadcap"] = rownorm(W_rd)
    # rail-weighted adjacency: сосед с крупным ЖД-узлом весит больше
    if RAIL.exists():
        rail = pd.read_csv(RAIL, encoding="utf-8-sig").set_index("subject")["rail_stations"]
        s = rail.reindex(subjects).fillna(0.0).to_numpy(dtype=float)
        W_rail = W_adj * np.sqrt(s)[None, :]
        print(f"rail weights: subjects with stations={int((s > 0).sum())}/{n}, "
              f"total stations={int(s.sum())}")
        out["railadj"] = rownorm(W_rail)
    else:
        print("rail weights: rail_stations_by_region.csv not found, variant skipped")
    return out


def transported(panel: pd.DataFrame, W: np.ndarray, lag: int) -> pd.DataFrame:
    # incoming[r,t] = Σ_j W[r,j] * infl[j,t-lag]  ==  (panel.shift(lag) @ W.T)
    vals = panel.shift(lag).values @ W.T
    return pd.DataFrame(vals, index=panel.index, columns=panel.columns)


def wide_to_long(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.stack()
    s.index = s.index.set_names(["period", "subject"])
    return s.rename(name)


def assemble(panel: pd.DataFrame, weights: dict[str, np.ndarray]) -> pd.DataFrame:
    cols = {"infl": wide_to_long(panel, "infl")}
    for L in LAGS:
        cols[f"own_l{L}"] = wide_to_long(panel.shift(L), f"own_l{L}")
    for key, W in weights.items():
        for L in LAGS:
            cols[f"{key}_l{L}"] = wide_to_long(transported(panel, W, L), f"{key}_l{L}")
    frame = pd.DataFrame(cols).dropna()
    # integer time index for PanelOLS time effects
    periods = sorted(frame.index.get_level_values("period").unique())
    tmap = {p: i for i, p in enumerate(periods)}
    frame = frame.reset_index()
    frame["t"] = frame["period"].map(tmap)
    frame = frame.set_index(["subject", "t"])
    return frame


def fit(frame: pd.DataFrame, regressors: list[str]):
    y = frame["infl"]
    X = frame[regressors]
    mod = PanelOLS(y, X, entity_effects=True, time_effects=True, drop_absorbed=True)
    return mod.fit(cov_type="clustered", cluster_entity=True)


def coef_table(res, names: list[str]) -> list[dict]:
    out = []
    for nm in names:
        if nm in res.params.index:
            out.append({
                "term": nm,
                "coef": round(float(res.params[nm]), 5),
                "se": round(float(res.std_errors[nm]), 5),
                "t": round(float(res.tstats[nm]), 3),
                "p": round(float(res.pvalues[nm]), 5),
            })
    return out


def main() -> int:
    panel, meta = load_panel()
    weights = build_weights(meta)
    frame = assemble(panel, weights)

    own = [f"own_l{L}" for L in LAGS]
    fd = [f"fd_l{L}" for L in LAGS]
    dist = [f"dist_l{L}" for L in LAGS]
    adj = [f"adj_l{L}" for L in LAGS]

    n_subj = frame.index.get_level_values("subject").nunique()
    n_per = frame.index.get_level_values("t").nunique()
    n_obs = len(frame)
    print(f"panel: subjects={n_subj} periods={n_per} obs={n_obs} "
          f"range={START}..{END}")

    models = {
        "M0_local":   own,
        "M1_fd":      own + fd,
        "M2_dist":    own + dist,
        "M3_adj":     own + adj,
    }
    if "railadj" in weights:
        models["M4_railadj"] = own + [f"railadj_l{L}" for L in LAGS]
    if "railline" in weights:
        models["M5_railline"] = own + [f"railline_l{L}" for L in LAGS]
    if "roadcap" in weights:
        models["M6_roadcap"] = own + [f"roadcap_l{L}" for L in LAGS]
    report = {"meta": {"subjects": n_subj, "periods": n_per, "obs": n_obs,
                       "start": START, "end": END, "lags": LAGS}, "models": {}}

    for name, regs in models.items():
        res = fit(frame, regs)
        transported_terms = [r for r in regs if r not in own]
        entry = {
            "regressors": regs,
            "rsq_within": round(float(res.rsquared_within), 5),
            "rsq_overall": round(float(res.rsquared_overall), 5),
            "nobs": int(res.nobs),
            "coefs": coef_table(res, regs),
        }
        # joint significance of transported terms
        if transported_terms:
            try:
                r = res.wald_test(formula=" = ".join(transported_terms) + " = 0")
                entry["joint_transported"] = {
                    "stat": round(float(r.stat), 3),
                    "pval": round(float(r.pval), 6),
                    "terms": transported_terms,
                }
            except Exception as exc:  # pragma: no cover
                entry["joint_transported"] = {"error": str(exc)}
        report["models"][name] = entry

        print(f"\n=== {name} === within-R2={entry['rsq_within']} nobs={entry['nobs']}")
        for c in entry["coefs"]:
            star = "***" if c["p"] < 0.01 else "**" if c["p"] < 0.05 else "*" if c["p"] < 0.1 else ""
            print(f"  {c['term']:10s} coef={c['coef']:+.4f} se={c['se']:.4f} "
                  f"t={c['t']:+.2f} p={c['p']:.4f} {star}")
        if transported_terms and "joint_transported" in entry and "pval" in entry["joint_transported"]:
            jt = entry["joint_transported"]
            print(f"  joint transported: chi2={jt['stat']} p={jt['pval']}")

    (OUT / "base_model_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # flat coef csv
    rows = []
    for mname, m in report["models"].items():
        for c in m["coefs"]:
            rows.append({"model": mname, **c})
    pd.DataFrame(rows).to_csv(OUT / "base_model_coefs.csv", index=False, encoding="utf-8-sig")
    print(f"\nsaved: {OUT/'base_model_report.json'}")
    print(f"saved: {OUT/'base_model_coefs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
