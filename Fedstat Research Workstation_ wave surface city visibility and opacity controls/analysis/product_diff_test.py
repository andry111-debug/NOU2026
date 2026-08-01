# -*- coding: utf-8 -*-
"""
Товарный дифференциальный тест механизма (D23 × H3).

Для каждого товара g строим панель ИПЦ (m/m − 100) и оцениваем:
    infl_g[r,t] ~ own лаги + incoming_g лаги + incoming_g_l1 × Z(share_no_pork[r]) + FE

Гипотеза товарного канала: для СВИНИНЫ и АЛКОГОЛЯ взаимодействие ОТРИЦАТЕЛЬНО
(шоки не заходят в регионы, где товар почти не потребляется); для говядины и
птицы — ноль (плацебо); для баранины — возможен плюс (обратный тест).
Если бы передача шла чисто информационно, знак не зависел бы от товара.

share_no_pork — из переписи (data/census/consumption_structure_by_region.csv,
черновой список групп). Имена переписи сопоставляются с каноническими субъектами.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_spatial_model as bsm

APP = Path(__file__).resolve().parent.parent
PROC = APP / "data" / "fedstat_targets" / "processed"
CENSUS = APP / "data" / "census" / "consumption_structure_by_region.csv"
HARM = APP / "data" / "geo" / "fedstat_region_harmonization.csv"
OUT = APP / "index_lab_output" / "base_model"

PRODUCTS = {
    "pork": ("body_ipc_pork.csv", "минус (товарный канал)"),
    "vodka": ("body_ipc_vodka.csv", "минус (товарный канал)"),
    "alcohol": ("body_ipc_alcohol.csv", "минус (товарный канал)"),
    "beef": ("body_ipc_beef.csv", "ноль (плацебо)"),
    "poultry": ("body_ipc_poultry.csv", "ноль (плацебо)"),
    "mutton": ("body_ipc_mutton.csv", "плюс (обратный тест)"),
}
LAGS = [1, 2, 3]


def norm(s: str) -> str:
    s = str(s).lower().replace("ё", "е")
    s = re.sub(r"[^а-яa-z ]", " ", s)
    return " ".join(s.split())


# сокращённые имена листов переписи -> подстрока канонического субъекта
SHEET_ALIAS = {
    "ХМАО": "Ханты-Мансийский",
    "ЯНАО": "Ямало-Ненецкий",
    "РСО-Алания": "Северная Осетия",
}


def masked_transported(panel: pd.DataFrame, W: np.ndarray, lag: int) -> pd.DataFrame:
    """Транспортированный член по ДОСТУПНЫМ соседям (пере-нормировка весов);
    NaN, если доступно < 50% веса соседей — иначе дыры коротких рядов
    заражают всю панель через матричное произведение."""
    A = panel.shift(lag)
    avail = (~A.isna()).astype(float).values
    num = np.nan_to_num(A.values) @ W.T
    den = avail @ W.T
    vals = np.where(den >= 0.5, num / np.where(den == 0, np.nan, den), np.nan)
    return pd.DataFrame(vals, index=panel.index, columns=panel.columns)


def census_share_map() -> dict[str, float]:
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    canon = sorted(set(harm["canonical_region"]))
    cen = pd.read_csv(CENSUS, encoding="utf-8-sig")
    cen = cen[~cen["region_sheet"].str.contains("Федерация")]

    result: dict[str, float] = {}
    unmatched = []
    canon_norm = {norm(c): c for c in canon}
    for sheet, share in zip(cen["region_sheet"], cen["share_no_pork_tradition"]):
        ns = norm(sheet)
        hit = canon_norm.get(ns)
        if hit is None:
            # частичное сопоставление: самый длинный общий вариант
            cands = [c for n, c in canon_norm.items() if ns in n or n in ns]
            if len(cands) == 1:
                hit = cands[0]
        if hit is None and sheet in SHEET_ALIAS:
            key = norm(SHEET_ALIAS[sheet])
            cands = [c for n, c in canon_norm.items() if key in n]
            if len(cands) == 1:
                hit = cands[0]
        if hit is not None:
            result[hit] = float(share)
        else:
            unmatched.append(sheet)
    print(f"census->canonical matched: {len(result)}; unmatched: {unmatched}")
    return result


def product_panel(fname: str, meta_index) -> pd.DataFrame | None:
    path = PROC / fname
    if not path.exists():
        return None
    df = pd.read_csv(path, encoding="utf-8-sig")
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    keep = harm[harm["use_in_subject_panel"] == "yes"][["fedstat_name", "canonical_region"]]
    df = df.merge(keep, left_on="region", right_on="fedstat_name", how="inner")
    df = df[(df["period"] >= bsm.START) & (df["period"] <= bsm.END)]
    df["infl"] = df["value"].astype(float) - 100.0
    return (df.pivot_table(index="period", columns="canonical_region",
                           values="infl", aggfunc="mean")
            .reindex(columns=meta_index).sort_index())


def stack(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.stack()
    s.index = s.index.set_names(["period", "subject"])
    return s.rename(name)


def main() -> int:
    food_panel, meta = bsm.load_panel()
    weights = bsm.build_weights(meta)
    W = weights["adj"]
    subjects = list(food_panel.columns)

    shares = census_share_map()
    z_share_vec = pd.Series({s: shares.get(s, np.nan) for s in subjects})
    z_share_vec = (z_share_vec - z_share_vec.mean()) / z_share_vec.std()

    report = {}
    for gname, (fname, expect) in PRODUCTS.items():
        panel = product_panel(fname, subjects)
        if panel is None or panel.dropna(how="all").empty:
            print(f"[{gname}] file missing/empty: {fname}")
            continue
        cols = {"infl": stack(panel, "infl")}
        for L in LAGS:
            cols[f"own_l{L}"] = stack(panel.shift(L), f"own_l{L}")
            cols[f"adj_l{L}"] = stack(masked_transported(panel, W, L), f"adj_l{L}")
        adj1 = masked_transported(panel, W, 1)
        cols["adjXshare"] = stack(adj1.mul(z_share_vec.reindex(subjects), axis=1), "adjXshare")
        frame = pd.DataFrame(cols).dropna()
        if len(frame) < 3000:
            print(f"[{gname}] too few obs: {len(frame)}")
            continue
        periods = sorted(frame.index.get_level_values("period").unique())
        tmap = {p: i for i, p in enumerate(periods)}
        frame = frame.reset_index()
        frame["t"] = frame["period"].map(tmap)
        frame = frame.set_index(["subject", "t"])
        regs = [f"own_l{L}" for L in LAGS] + [f"adj_l{L}" for L in LAGS] + ["adjXshare"]
        res = PanelOLS(frame["infl"], frame[regs], entity_effects=True,
                       time_effects=True, drop_absorbed=True
                       ).fit(cov_type="clustered", cluster_entity=True)
        c = res.params.get("adjXshare", np.nan)
        se = res.std_errors.get("adjXshare", np.nan)
        p = res.pvalues.get("adjXshare", np.nan)
        a1 = res.params.get("adj_l1", np.nan)
        report[gname] = {
            "expect": expect, "nobs": int(res.nobs),
            "adj_l1": round(float(a1), 4),
            "adjXshare": round(float(c), 4),
            "se": round(float(se), 4), "p": round(float(p), 5),
        }
        star = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
        print(f"[{gname:8s}] adj_l1={a1:+.3f} | adjXshare={c:+.4f} (se={se:.4f}, p={p:.4f}){star} "
              f"| ожидание: {expect} | nobs={res.nobs}")

    (OUT / "product_diff_test.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {OUT / 'product_diff_test.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
