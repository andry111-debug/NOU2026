# -*- coding: utf-8 -*-
"""
D24: возрастная структура субъектов из пирамиды 31548 (муж.) + 33459 (жен.).

Используем ОФИЦИАЛЬНЫЕ агрегатные строки показателя:
    «Всего», «Моложе трудоспособного», «Старше трудоспособного» —
ровно категории плана D24 (доли старше/моложе трудоспособного).
Фильтр: label_4 == «все население»; имена → канонические субъекты;
мужчины и женщины суммируются.

Выход (в git): data/emiss_downloads/D24_age_structure_subjects.csv
    region, period, total_pop, share_older, share_child
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
RAW = APP / "data" / "emiss_downloads" / "raw"
OUT = APP / "data" / "emiss_downloads" / "D24_age_structure_subjects.csv"
HARM = APP / "data" / "geo" / "fedstat_region_harmonization.csv"

FILES = ["D24_pyramid_male_31548.csv", "D24_pyramid_female_33459.csv"]
GROUPS = {"Всего": "total", "Моложе трудоспособного": "child",
          "Старше трудоспособного": "older"}


def log(*a):
    print(*a, flush=True)


def main() -> int:
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    cmap = dict(zip(harm["fedstat_name"], harm["canonical_region"]))
    cmap.update(dict(zip(harm["canonical_region"], harm["canonical_region"])))

    frames = []
    for f in FILES:
        df = pd.read_csv(RAW / f, encoding="utf-8-sig",
                         usecols=["label_0", "label_1", "label_4", "period", "value"])
        df = df[df["label_4"] == "все население"]
        df["grp"] = df["label_1"].astype(str).str.strip().map(GROUPS)
        df = df.dropna(subset=["grp"])
        df["region"] = df["label_0"].map(cmap)
        df = df.dropna(subset=["region"])
        frames.append(df[["region", "period", "grp", "value"]])
        log(f"{f}: aggregate rows kept {len(df)}")
    allsex = pd.concat(frames, ignore_index=True)
    pv = (allsex.groupby(["region", "period", "grp"])["value"].sum()
          .unstack("grp"))
    out = pd.DataFrame({
        "total_pop": pv["total"],
        "share_older": (pv["older"] / pv["total"]).round(5),
        "share_child": (pv["child"] / pv["total"]).round(5),
    }).reset_index().dropna(subset=["total_pop"]).sort_values(["region", "period"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT} rows={len(out)} regions={out['region'].nunique()} "
        f"period={out['period'].min()}..{out['period'].max()}")
    chk = out[(out["region"].str.contains("Москва")) & (out["period"].astype(str) == "2020")]
    log("sanity Москва 2020:", chk.to_dict("records"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
