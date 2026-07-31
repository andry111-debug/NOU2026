# -*- coding: utf-8 -*-
"""
Климат в spatial-lag модели (D19 v1).

Спецификации (все: региональные + временные FE, кластерные SE по региону):
  C0: базовая — свои лаги инфляции + транспортированная инфляция соседей (W_adj);
  C1: C0 + собственные температурные аномалии региона (t, t-1);
  C2: C1 + аномалии СОСЕДЕЙ (W_adj @ t_anom, лаги 1, 2).

Смысл C2: если погода соседей двигает местную food-инфляцию при контроле
собственной погоды и собственной динамики — передача идёт через товарные
потоки, а не через общий фон (тот съеден FE) и не через локальный урожай.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_spatial_model as bsm

APP = Path(__file__).resolve().parent.parent
CLIM_CSV = APP / "data" / "climate" / "temp_anomaly_by_region.csv"
OUT = APP / "index_lab_output" / "base_model"
OUT.mkdir(parents=True, exist_ok=True)

INFL_LAGS = [1, 2, 3, 6]
W_KEY = "adj"


def wide(df: pd.DataFrame, value: str) -> pd.DataFrame:
    return df.pivot_table(index="period", columns="region", values=value, aggfunc="mean").sort_index()


def stack(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.stack()
    s.index = s.index.set_names(["period", "subject"])
    return s.rename(name)


def main() -> int:
    panel, meta = bsm.load_panel()
    weights = bsm.build_weights(meta)
    W = weights[W_KEY]

    clim = pd.read_csv(CLIM_CSV, encoding="utf-8-sig")
    anom = wide(clim, "t_anomaly")
    common = [s for s in panel.columns if s in anom.columns]
    dropped = [s for s in panel.columns if s not in anom.columns]
    print(f"subjects: panel={panel.shape[1]}, climate={anom.shape[1]}, common={len(common)}")
    print(f"dropped (no climate): {dropped}")

    # сужаем панель и W до общих субъектов; W пере-нормируем построчно,
    # иначе NaN-колонки без климата заражают матричное произведение (0*NaN=NaN)
    all_subjects = list(panel.columns)
    idx = [all_subjects.index(s) for s in common]
    W = bsm.rownorm(W[np.ix_(idx, idx)])
    panel = panel[common]
    anom = anom.reindex(index=panel.index, columns=common)

    cols: dict[str, pd.Series] = {"infl": stack(panel, "infl")}
    for L in INFL_LAGS:
        cols[f"own_l{L}"] = stack(panel.shift(L), f"own_l{L}")
        cols[f"adj_l{L}"] = stack(bsm.transported(panel, W, L), f"adj_l{L}")
    cols["wx_l0"] = stack(anom, "wx_l0")
    cols["wx_l1"] = stack(anom.shift(1), "wx_l1")
    # masked transported weather: среднее по ДОСТУПНЫМ соседям с пере-нормировкой
    # весов; требуем >=50% веса соседей, иначе NaN. Без этого одна дыра у одного
    # соседа глушит наблюдение целиком и панель схлопывается.
    for L in (1, 2):
        A = anom.shift(L)
        avail = (~A.isna()).astype(float).values
        A0 = np.nan_to_num(A.values)
        num = A0 @ W.T
        den = avail @ W.T
        vals = np.where(den >= 0.5, num / np.where(den == 0, np.nan, den), np.nan)
        cols[f"nbwx_l{L}"] = stack(pd.DataFrame(vals, index=anom.index, columns=anom.columns), f"nbwx_l{L}")

    frame = pd.DataFrame(cols).dropna()
    periods = sorted(frame.index.get_level_values("period").unique())
    tmap = {p: i for i, p in enumerate(periods)}
    frame = frame.reset_index()
    frame["t"] = frame["period"].map(tmap)
    frame = frame.set_index(["subject", "t"])
    n_subj = frame.index.get_level_values("subject").nunique()
    print(f"estimation panel: subjects={n_subj} obs={len(frame)} "
          f"({periods[0]}..{periods[-1]})")

    own = [f"own_l{L}" for L in INFL_LAGS]
    adj = [f"adj_l{L}" for L in INFL_LAGS]
    wx = ["wx_l0", "wx_l1"]
    nbwx = ["nbwx_l1", "nbwx_l2"]

    specs = {
        "C0_base": own + adj,
        "C1_own_weather": own + adj + wx,
        "C2_neighbor_weather": own + adj + wx + nbwx,
    }

    report = {"meta": {"subjects": n_subj, "obs": int(len(frame)),
                       "period": f"{periods[0]}..{periods[-1]}", "w": W_KEY}, "models": {}}
    for name, regs in specs.items():
        res = PanelOLS(frame["infl"], frame[regs], entity_effects=True,
                       time_effects=True, drop_absorbed=True
                       ).fit(cov_type="clustered", cluster_entity=True)
        entry = {
            "rsq_within": round(float(res.rsquared_within), 5),
            "nobs": int(res.nobs),
            "coefs": bsm.coef_table(res, regs),
        }
        for label, terms in (("joint_adj", adj), ("joint_wx", wx), ("joint_nbwx", nbwx)):
            terms_in = [t for t in terms if t in regs and t in res.params.index]
            if terms_in:
                try:
                    r = res.wald_test(formula=" = ".join(terms_in) + " = 0")
                    entry[label] = {"stat": round(float(r.stat), 3), "pval": round(float(r.pval), 6)}
                except Exception as exc:
                    entry[label] = {"error": str(exc)}
        report["models"][name] = entry

        print(f"\n=== {name} === within-R2={entry['rsq_within']} nobs={entry['nobs']}")
        for c in entry["coefs"]:
            star = "***" if c["p"] < 0.01 else "**" if c["p"] < 0.05 else "*" if c["p"] < 0.1 else ""
            print(f"  {c['term']:10s} coef={c['coef']:+.4f} se={c['se']:.4f} t={c['t']:+.2f} p={c['p']:.4f} {star}")
        for label in ("joint_adj", "joint_wx", "joint_nbwx"):
            if label in entry and "pval" in entry[label]:
                print(f"  {label}: chi2={entry[label]['stat']} p={entry[label]['pval']}")

    (OUT / "climate_model_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for mname, m in report["models"].items():
        for c in m["coefs"]:
            rows.append({"model": mname, **c})
    pd.DataFrame(rows).to_csv(OUT / "climate_model_coefs.csv", index=False, encoding="utf-8-sig")
    print(f"\nsaved: {OUT/'climate_model_report.json'} | {OUT/'climate_model_coefs.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
