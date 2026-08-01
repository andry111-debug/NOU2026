# -*- coding: utf-8 -*-
"""
D23 (ЧЕРНОВИК на утверждение): доли этнокультурных групп с традиционным
исключением свинины из рациона — для дифференциального теста товарного канала
(шоки цен свинины/алкоголя не должны передаваться в регионы, где эти товары
почти не потребляются, если механизм товарный).

Источник: data/census/ethnic_composition_by_region.csv (ВПН-2020, Том 5, табл. 1).
Список групп NO_PORK_GROUPS — редактируемая аналитическая константа; сопоставление
по вхождению ключа в название национальности (названия переписи содержат
самоназвания в скобках). Доля считается от «Указавшие национальную принадлежность».

Выход: data/census/consumption_structure_by_region.csv
    region_sheet, total_indicated, no_pork_population, share_no_pork_tradition
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
SRC = APP / "data" / "census" / "ethnic_composition_by_region.csv"
OUT = APP / "data" / "census" / "consumption_structure_by_region.csv"

# Крупнейшие народы РФ, в чьей традиционной кухне свинина отсутствует
# (мусульманская культурная традиция). Ключ — подстрока названия в переписи.
NO_PORK_GROUPS = [
    "Татары", "Башкиры", "Чеченцы", "Ингуши",
    "Аварцы", "Даргинцы", "Кумыки", "Лезгины", "Лакцы", "Табасараны",
    "Рутульцы", "Агулы", "Цахуры", "Ногайцы",
    "Кабардинцы", "Балкарцы", "Карачаевцы", "Черкесы", "Адыгейцы", "Абазины",
    "Азербайджанцы", "Казахи", "Узбеки", "Таджики", "Киргизы", "Туркмены",
    "Турки", "Крымские татары", "Абхазы",
    # дагестанские малые народы учитываются через аварцев/даргинцев в переписи
]
# Сознательно НЕ включены: Осетины (преимущественно христианская традиция),
# Калмыки, Буряты, Тувинцы (буддийская традиция — свинина не исключена).

TOTAL_ROW = "Указавшие национальную принадлежность"


def main() -> int:
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    rows = []
    for region, grp in df.groupby("region_sheet"):
        total = grp.loc[grp["ethnicity"].str.startswith(TOTAL_ROW), "population"]
        if total.empty:
            continue
        total = float(total.iloc[0])
        mask = pd.Series(False, index=grp.index)
        for key in NO_PORK_GROUPS:
            mask |= grp["ethnicity"].str.startswith(key)
        no_pork = float(grp.loc[mask, "population"].sum())
        rows.append({
            "region_sheet": region,
            "total_indicated": int(total),
            "no_pork_population": int(no_pork),
            "share_no_pork_tradition": round(no_pork / total, 5) if total else None,
        })
    out = pd.DataFrame(rows).sort_values("share_no_pork_tradition", ascending=False)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"saved: {OUT} regions={len(out)}")
    print("top-8:")
    for _, r in out.head(8).iterrows():
        print(f"  {r['region_sheet']}: {r['share_no_pork_tradition']:.1%}")
    rf = out[out["region_sheet"].str.contains("Федерация")]
    if not rf.empty:
        print(f"РФ в целом: {float(rf['share_no_pork_tradition'].iloc[0]):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
