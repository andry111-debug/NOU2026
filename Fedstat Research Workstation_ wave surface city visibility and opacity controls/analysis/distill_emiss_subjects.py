# -*- coding: utf-8 -*-
"""
Дистилляция сырых выгрузок ЕМИСС до субъектных панелей region/period/value.

- births 31606 / deaths 31617: фильтр «Оба пола» × «все население».
- population 31557: субъектный уровень = строки «Муниципальные образования X»
  (свежие годы) плюс строки раздела без муниципального разреза (ранние годы).
Имена регионов приводятся к каноническим субъектам через
data/geo/fedstat_region_harmonization.csv; агрегаты (РФ, федokruга) отбрасываются.

Выход (в git): data/emiss_downloads/D22_births_subjects.csv,
D22_deaths_subjects.csv, D13_population_subjects.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
RAW = APP / "data" / "emiss_downloads" / "raw"
OUT = APP / "data" / "emiss_downloads"
HARM = APP / "data" / "geo" / "fedstat_region_harmonization.csv"


def log(*a):
    print(*a, flush=True)


def canon_map() -> dict[str, str]:
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    m = dict(zip(harm["fedstat_name"], harm["canonical_region"]))
    m.update(dict(zip(harm["canonical_region"], harm["canonical_region"])))
    return m


def harmonize(df: pd.DataFrame, name_col: str, cmap: dict[str, str]) -> pd.DataFrame:
    df = df.copy()
    df["region"] = df[name_col].map(cmap)
    unmatched = sorted(df.loc[df["region"].isna(), name_col].unique())
    keep_unmatched = [u for u in unmatched
                     if not any(k in str(u).lower() for k in
                                ("федерация", "федеральный округ", "район", "автономия"))]
    if keep_unmatched:
        log(f"  unmatched subject-like names: {keep_unmatched[:6]}")
    return df.dropna(subset=["region"])


def distill_vital(src: str, dst: str, cmap: dict[str, str]) -> None:
    df = pd.read_csv(RAW / src, encoding="utf-8-sig")
    sel = df[(df["label_3"] == "Оба пола") & (df["label_4"] == "все население")]
    sel = harmonize(sel, "label_0", cmap)
    out = (sel.groupby(["region", "period"], as_index=False)["value"].mean()
           .sort_values(["region", "period"]))
    out.to_csv(OUT / dst, index=False, encoding="utf-8-sig")
    log(f"{dst}: rows={len(out)} regions={out['region'].nunique()} "
        f"period={out['period'].min()}..{out['period'].max()}")


def distill_population(cmap: dict[str, str]) -> None:
    df = pd.read_csv(RAW / "D13_population_31557.csv", encoding="utf-8-sig")
    total = df[df["label_4"] == "все население"].copy()
    l1 = total["label_1"].astype(str)
    muni_agg = total[l1.str.startswith("Муниципальные образования")]
    section = total[l1.str.startswith("Раздел")]
    both = pd.concat([muni_agg, section], ignore_index=True)
    both = harmonize(both, "label_0", cmap)
    # предпочитаем муниципальный агрегат, если на (region, period) есть оба
    both["prio"] = both["label_1"].astype(str).str.startswith("Муниципальные образования").astype(int)
    both = (both.sort_values("prio", ascending=False)
            .drop_duplicates(["region", "period"], keep="first"))
    out = both[["region", "period", "value"]].sort_values(["region", "period"])
    out.to_csv(OUT / "D13_population_subjects.csv", index=False, encoding="utf-8-sig")
    log(f"D13_population_subjects.csv: rows={len(out)} regions={out['region'].nunique()} "
        f"period={out['period'].min()}..{out['period'].max()}")


def main() -> int:
    cmap = canon_map()
    distill_vital("D22_births_31606.csv", "D22_births_subjects.csv", cmap)
    distill_vital("D22_deaths_31617.csv", "D22_deaths_subjects.csv", cmap)
    distill_population(cmap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
