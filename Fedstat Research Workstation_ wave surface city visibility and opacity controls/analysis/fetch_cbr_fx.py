# -*- coding: utf-8 -*-
"""
D14: валютный курс — месячные средние USD/RUB и EUR/RUB из открытого XML API ЦБ РФ.

Выход (в git): data/macro/fx_monthly.csv (period, usd_rub, eur_rub).
Общероссийский ряд: в панели с временными FE сам по себе поглощается,
использовать во взаимодействиях со средовыми характеристиками региона
(импортозависимость и т.п.).
"""
from __future__ import annotations

import ssl
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
import urllib.request as u

import pandas as pd

APP = Path(__file__).resolve().parent.parent
OUT_DIR = APP / "data" / "macro"
OUT_CSV = OUT_DIR / "fx_monthly.csv"

CURRENCIES = {"usd_rub": "R01235", "eur_rub": "R01239"}
DATE_FROM, DATE_TO = "01/01/2014", "01/08/2026"


def fetch(code: str) -> dict[str, float]:
    url = (f"https://www.cbr.ru/scripts/XML_dynamic.asp?"
           f"date_req1={DATE_FROM}&date_req2={DATE_TO}&VAL_NM_RQ={code}")
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx))
    req = u.Request(url, headers={"User-Agent": "nou2027-research/1.0"})
    with op.open(req, timeout=120) as r:
        xml = r.read().decode("windows-1251", "replace")
    root = ET.fromstring(xml)
    acc: dict[str, list[float]] = defaultdict(list)
    for rec in root.findall("Record"):
        date = rec.get("Date", "")            # DD.MM.YYYY
        nominal = float(rec.findtext("Nominal", "1").replace(",", "."))
        value = float(rec.findtext("Value", "nan").replace(",", "."))
        if len(date) == 10 and nominal:
            period = f"{date[6:10]}-{date[3:5]}"
            acc[period].append(value / nominal)
    return {p: sum(v) / len(v) for p, v in acc.items()}


def main() -> int:
    series = {}
    for name, code in CURRENCIES.items():
        series[name] = fetch(code)
        print(f"{name}: {len(series[name])} months", flush=True)
    periods = sorted(set().union(*[s.keys() for s in series.values()]))
    rows = [{"period": p, **{n: round(series[n].get(p, float("nan")), 4) for n in series}}
            for p in periods]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"saved: {OUT_CSV} rows={len(df)} range={df['period'].min()}..{df['period'].max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
