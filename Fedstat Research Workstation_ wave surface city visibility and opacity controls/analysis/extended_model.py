# -*- coding: utf-8 -*-
"""
Расширенная модель (задача 5 концепции, v1): среда как модераторы передачи.

Спецификации (региональные + временные FE, кластерные SE):
  E0: свои лаги + транспортированная инфляция соседей (W_adj) — бейзлайн на той же выборке;
  E1: E0 + контроль издержек ЖКХ (m/m, тек. и лаг 1);
  E2: E1 + взаимодействия adj_l1 × Z(туризм на душу) и adj_l1 × Z(доля старше
      трудоспособного). Ожидание: оба знака ПЛЮС (усилители восприимчивости).

Уровни статичных модераторов поглощаются региональными FE — идентифицируются
взаимодействия. Z-стандартизация делает коэффициенты сопоставимыми:
γ = изменение эффекта соседского импульса на +1 ст. отклонение модератора.
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
DATA = APP / "data"
UTIL = DATA / "fedstat_targets" / "processed" / "env_ipc_utilities.csv"
TOUR = DATA / "geo" / "tourism_poi_by_region.csv"
AGE = DATA / "emiss_downloads" / "D24_age_structure_subjects.csv"
HARM = DATA / "geo" / "fedstat_region_harmonization.csv"
OUT = APP / "index_lab_output" / "base_model"

INFL_LAGS = [1, 2, 3, 6]


def stack(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.stack()
    s.index = s.index.set_names(["period", "subject"])
    return s.rename(name)


def main() -> int:
    panel, meta = bsm.load_panel()
    weights = bsm.build_weights(meta)
    W = weights["adj"]

    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    cmap = dict(zip(harm["fedstat_name"], harm["canonical_region"]))
    cmap.update(dict(zip(harm["canonical_region"], harm["canonical_region"])))

    # --- ЖКХ: месячная панель (регион=сырые имена Fedstat -> канонические) ---
    util = pd.read_csv(UTIL, encoding="utf-8-sig")
    util["subject"] = util["region"].map(cmap)
    util = util.dropna(subset=["subject"])
    util_panel = (util.assign(v=util["value"].astype(float) - 100.0)
                  .pivot_table(index="period", columns="subject", values="v", aggfunc="mean")
                  .reindex(index=panel.index, columns=panel.columns))

    # --- возрастная структура: годовая доля старших -> на месяцы года ---
    age = pd.read_csv(AGE, encoding="utf-8-sig")
    age_map = {(r, str(p)): v for r, p, v in
               zip(age["region"], age["period"], age["share_older"])}
    older = pd.DataFrame(index=panel.index, columns=panel.columns, dtype=float)
    for per in panel.index:
        y = str(per)[:4]
        older.loc[per] = [age_map.get((s, y), np.nan) for s in panel.columns]

    # --- туризм на 100 тыс. населения (статично, население 2020) ---
    tour = pd.read_csv(TOUR, encoding="utf-8-sig").set_index("subject")
    pop2020 = {r: v for r, p, v in zip(age["region"], age["period"], age["total_pop"])
               if str(p) == "2020"}
    tour_pc = {}
    for s in panel.columns:
        if s in tour.index and s in pop2020 and pop2020[s] > 0:
            tour_pc[s] = (tour.loc[s, "hotels"] + tour.loc[s, "restaurants"]) / pop2020[s] * 1e5
    tour_pc = pd.Series(tour_pc)

    def z(x: pd.Series) -> pd.Series:
        return (x - x.mean()) / x.std()

    z_tour = z(tour_pc)

    # z для доли старших: по объединению регион-лет в окне модели
    older_window = older.loc[(older.index >= bsm.START) & (older.index <= bsm.END)]
    mu, sd = np.nanmean(older_window.values), np.nanstd(older_window.values)
    z_older = (older - mu) / sd

    cols: dict[str, pd.Series] = {"infl": stack(panel, "infl")}
    for L in INFL_LAGS:
        cols[f"own_l{L}"] = stack(panel.shift(L), f"own_l{L}")
        cols[f"adj_l{L}"] = stack(bsm.transported(panel, W, L), f"adj_l{L}")
    cols["util_l0"] = stack(util_panel, "util_l0")
    cols["util_l1"] = stack(util_panel.shift(1), "util_l1")

    adj1 = bsm.transported(panel, W, 1)
    inter_tour = adj1.mul(pd.Series(z_tour).reindex(panel.columns), axis=1)
    inter_older = adj1 * z_older
    cols["adjXtour"] = stack(inter_tour, "adjXtour")
    cols["adjXolder"] = stack(inter_older, "adjXolder")

    frame = pd.DataFrame(cols).dropna()
    periods = sorted(frame.index.get_level_values("period").unique())
    tmap = {p: i for i, p in enumerate(periods)}
    frame = frame.reset_index()
    frame["t"] = frame["period"].map(tmap)
    frame = frame.set_index(["subject", "t"])
    print(f"panel: subjects={frame.index.get_level_values('subject').nunique()} "
          f"obs={len(frame)} ({periods[0]}..{periods[-1]})")

    own = [f"own_l{L}" for L in INFL_LAGS]
    adj = [f"adj_l{L}" for L in INFL_LAGS]
    utils = ["util_l0", "util_l1"]
    inters = ["adjXtour", "adjXolder"]

    specs = {
        "E0_base": own + adj,
        "E1_utilities": own + adj + utils,
        "E2_moderators": own + adj + utils + inters,
    }
    report = {"meta": {"obs": int(len(frame)),
                       "period": f"{periods[0]}..{periods[-1]}"}, "models": {}}
    for name, regs in specs.items():
        res = PanelOLS(frame["infl"], frame[regs], entity_effects=True,
                       time_effects=True, drop_absorbed=True
                       ).fit(cov_type="clustered", cluster_entity=True)
        entry = {"rsq_within": round(float(res.rsquared_within), 5),
                 "nobs": int(res.nobs), "coefs": bsm.coef_table(res, regs)}
        for label, terms in (("joint_adj", adj), ("joint_util", utils), ("joint_inter", inters)):
            t_in = [t for t in terms if t in regs and t in res.params.index]
            if t_in:
                try:
                    r = res.wald_test(formula=" = ".join(t_in) + " = 0")
                    entry[label] = {"stat": round(float(r.stat), 3), "pval": round(float(r.pval), 6)}
                except Exception as exc:
                    entry[label] = {"error": str(exc)}
        report["models"][name] = entry
        print(f"\n=== {name} === within-R2={entry['rsq_within']} nobs={entry['nobs']}")
        for c in entry["coefs"]:
            star = "***" if c["p"] < 0.01 else "**" if c["p"] < 0.05 else "*" if c["p"] < 0.1 else ""
            print(f"  {c['term']:10s} coef={c['coef']:+.4f} se={c['se']:.4f} t={c['t']:+.2f} p={c['p']:.4f} {star}")
        for label in ("joint_adj", "joint_util", "joint_inter"):
            if label in entry and "pval" in entry[label]:
                print(f"  {label}: chi2={entry[label]['stat']} p={entry[label]['pval']}")

    (OUT / "extended_model_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for mname, m in report["models"].items():
        for c in m["coefs"]:
            rows.append({"model": mname, **c})
    pd.DataFrame(rows).to_csv(OUT / "extended_model_coefs.csv", index=False, encoding="utf-8-sig")
    print(f"\nsaved: {OUT/'extended_model_report.json'} | {OUT/'extended_model_coefs.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
