# -*- coding: utf-8 -*-
"""
D10: дистилляция пищевой базы региона до субъектных панелей.

- 43337 «Продукция сельского хозяйства» (млн руб., год): фильтр «Хозяйства всех
  категорий» -> D10_agri_subjects.csv (region, period, value_mln_rub).
- 57807 «Индекс производства (ОКВЭД2)» (% к пред. году): фильтр
  «Производство пищевых продуктов» -> D10_food_index_subjects.csv.
Имена -> канонические субъекты; агрегаты (РФ/ФО) отбрасываются.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
DL = APP / "data" / "emiss_downloads"
HARM = APP / "data" / "geo" / "fedstat_region_harmonization.csv"


def log(*a):
    print(*a, flush=True)


def cmap() -> dict[str, str]:
    harm = pd.read_csv(HARM, encoding="utf-8-sig")
    harm = harm[harm["use_in_subject_panel"] == "yes"]
    m = dict(zip(harm["fedstat_name"], harm["canonical_region"]))
    m.update(dict(zip(harm["canonical_region"], harm["canonical_region"])))
    return m


def main() -> int:
    m = cmap()

    agri = pd.read_csv(DL / "D10_agri_output_43337.csv", encoding="utf-8-sig")
    agri = agri[agri["label_1"] == "Хозяйства всех категорий"].copy()
    agri["region"] = agri["label_0"].map(m)
    agri = agri.dropna(subset=["region"])
    out = (agri.groupby(["region", "period"], as_index=False)["value"].mean()
           .rename(columns={"value": "value_mln_rub"})
           .sort_values(["region", "period"]))
    out.to_csv(DL / "D10_agri_subjects.csv", index=False, encoding="utf-8-sig")
    log(f"D10_agri_subjects.csv: rows={len(out)} regions={out['region'].nunique()} "
        f"period={out['period'].min()}..{out['period'].max()}")

    idx = pd.read_csv(DL / "D10_prod_index_okved_57807.csv", encoding="utf-8-sig")
    idx = idx[idx["label_1"] == "Производство пищевых продуктов"].copy()
    idx["region"] = idx["label_0"].map(m)
    idx = idx.dropna(subset=["region"])
    out2 = (idx.groupby(["region", "period"], as_index=False)["value"].mean()
            .rename(columns={"value": "index_pct"})
            .sort_values(["region", "period"]))
    out2.to_csv(DL / "D10_food_index_subjects.csv", index=False, encoding="utf-8-sig")
    log(f"D10_food_index_subjects.csv: rows={len(out2)} regions={out2['region'].nunique()} "
        f"period={out2['period'].min()}..{out2['period'].max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
