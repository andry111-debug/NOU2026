# -*- coding: utf-8 -*-
"""
D23: разбор Тома 5 ВПН-2020, таблица 1 «Национальный состав населения».

Вход: data/census/raw/Tom5_tab1_VPN-2020.xlsx (лист на каждый субъект).
Выход (в git): data/census/ethnic_composition_by_region.csv
    region_sheet, ethnicity, population  (блок «Городское и сельское население»,
    колонка «мужчины и женщины»; иерархия национальностей сохранена как есть).
Маппинг к каноническим субъектам панели и группировка национальностей — отдельным
шагом (совместно): здесь только нейтральные сырые данные переписи.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
RAW = APP / "data" / "census" / "raw" / "Tom5_tab1_VPN-2020.xlsx"
OUT = APP / "data" / "census" / "ethnic_composition_by_region.csv"


def log(*a):
    print(*a, flush=True)


def parse_sheet(xl: pd.ExcelFile, sheet: str) -> list[dict]:
    df = xl.parse(sheet, header=None)

    def txt(v):
        return "" if pd.isna(v) else str(v).strip()

    # данные начинаются со строки «Все население»; на части листов перед именами
    # стоит служебная OLAP-колонка, поэтому ищем метку в первых трёх колонках
    start = None
    name_col = None
    val_col = None
    for r in range(min(30, len(df))):
        for nc in range(min(3, df.shape[1])):
            if txt(df.iat[r, nc]).lower().startswith("все население"):
                start, name_col = r, nc
                for c in range(nc + 1, min(nc + 8, df.shape[1])):
                    v = df.iat[r, c]
                    if isinstance(v, (int, float)) and not pd.isna(v):
                        val_col = c
                        break
                break
        if start is not None:
            break
    if start is None or val_col is None:
        raise RuntimeError(f"{sheet}: data start not found")

    rows = []
    for r in range(start, len(df)):
        name = txt(df.iat[r, name_col])
        if not name:
            continue
        v = df.iat[r, val_col]
        if pd.isna(v):
            continue
        try:
            num = float(str(v).replace("\xa0", "").replace(" ", ""))
        except Exception:
            continue
        rows.append({"region_sheet": sheet.strip(), "ethnicity": name, "population": int(num)})
    return rows


def main() -> int:
    xl = pd.ExcelFile(RAW)
    all_rows: list[dict] = []
    ok = 0
    for sheet in xl.sheet_names:
        try:
            rows = parse_sheet(xl, sheet)
            all_rows.extend(rows)
            ok += 1
        except Exception as exc:
            log(f"  {sheet}: {exc}")
    out = pd.DataFrame(all_rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    n_reg = out["region_sheet"].nunique()
    log(f"sheets parsed: {ok}/{len(xl.sheet_names)}; regions={n_reg}; rows={len(out)}")
    log(f"saved: {OUT}")
    tot = out[out["ethnicity"].str.lower().str.startswith("все население")]
    log(f"sanity: 'Все население' rows={len(tot)}; "
        f"РФ total={tot[tot['region_sheet'].str.contains('Федерация')]['population'].sum():,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
