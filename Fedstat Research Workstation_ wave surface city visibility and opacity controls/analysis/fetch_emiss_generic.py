# -*- coding: utf-8 -*-
"""
Общий загрузчик показателей ЕМИСС/Fedstat по ID.

Для каждого показателя: парсим фильтры страницы (parse_filters_from_html из main.py),
классифицируем измерения (годы / периоды / регионы / прочие), выбираем ВСЕ значения,
раскладка: годы+периоды в колонки, регионы+прочие в строки; качаем Excel кусками
по <=13 лет (лимит 256 колонок .xls) и разбираем в длинный CSV.

Выход: data/emiss_downloads/{need}_{indicator_id}.csv
Колонки: region (или label_*), period_label, period, value.
Сырые файлы: data/emiss_downloads/raw/ (gitignored).
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request as u
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import main as fb  # noqa: E402

OUT_DIR = APP / "data" / "emiss_downloads"
RAW_DIR = OUT_DIR / "raw"

MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
QUARTERS = {"i квартал": "Q1", "ii квартал": "Q2", "iii квартал": "Q3", "iv квартал": "Q4"}

TARGETS = [
    ("D12", "57341", "unemployment"),
    ("D13", "31557", "population"),
    ("D22", "31606", "births"),
    ("D22", "31617", "deaths"),
    ("D11", "57039", "incomes"),
    ("D11", "56791", "wages"),
    ("D20", "58704", "ksr_guests"),
]


def log(*a):
    print(*a, flush=True)


def opener():
    ctx = ssl._create_unverified_context()
    return u.build_opener(u.HTTPSHandler(context=ctx), u.HTTPCookieProcessor())


def headers(referer: str = "") -> Dict[str, str]:
    h = {"User-Agent": fb.DEFAULT_USER_AGENT, "Accept-Language": "ru,en;q=0.9",
         "Connection": "keep-alive"}
    if referer:
        h.update({"Content-Type": "application/x-www-form-urlencoded",
                  "Origin": "https://www.fedstat.ru", "Referer": referer})
    return h


def classify(dims) -> Tuple[Any, Any, Any, list]:
    year_dim = month_dim = region_dim = None
    others = []
    for d in dims:
        if d.object_id == "0":
            continue
        titles = [v.title.strip().lower() for v in d.values]
        n = len(titles)
        if n == 0:
            continue
        years = sum(bool(re.fullmatch(r"(19|20)\d{2}", t)) for t in titles)
        monthish = sum(t in MONTHS or t in QUARTERS for t in titles)
        regionish = sum(bool(re.search(r"область|край|республик|округ|москва|петербург", t)) for t in titles)
        if years >= max(3, n * 0.7) and year_dim is None:
            year_dim = d
        elif monthish >= max(3, n * 0.5) and month_dim is None:
            month_dim = d
        elif n >= 40 and regionish >= n * 0.5 and region_dim is None:
            region_dim = d
        else:
            others.append(d)
    return year_dim, month_dim, region_dim, others


def set_all(dim, only_ids=None):
    sel = None if only_ids is None else {str(x) for x in only_ids}
    for v in dim.values:
        v.checked = (sel is None) or (v.value_id in sel)


def parse_period(year: str, label: str):
    lab = label.strip().lower()
    if lab in MONTHS:
        return f"{year}-{MONTHS[lab]:02d}"
    if lab in QUARTERS:
        return f"{year}-{QUARTERS[lab]}"
    return year


def normalize_excel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=None, dtype=object)

    def txt(v):
        return "" if pd.isna(v) else str(v).strip()

    year_row = None
    for r in range(min(30, len(df))):
        vals = [txt(df.iat[r, c]) for c in range(df.shape[1])]
        years = sum(bool(re.search(r"(19|20)\d{2}", v)) for v in vals)
        if years >= 2:
            year_row = r
            break
    if year_row is None:
        raise RuntimeError("year header row not found")

    label_row = year_row + 1
    # определяем, есть ли строка подписей периодов (месяцы/кварталы) под годами
    lab_vals = [txt(df.iat[label_row, c]).lower() for c in range(df.shape[1])] \
        if label_row < len(df) else []
    has_period_row = any(v in MONTHS or v in QUARTERS for v in lab_vals)

    col_period: Dict[int, Tuple[str, str]] = {}
    cur_year = ""
    for c in range(df.shape[1]):
        yv = txt(df.iat[year_row, c])
        m = re.search(r"(19|20)\d{2}", yv)
        if m:
            cur_year = m.group(0)
        if not cur_year:
            continue
        if has_period_row:
            lab = txt(df.iat[label_row, c])
            if lab:
                col_period[c] = (cur_year, lab)
        else:
            if m:
                col_period[c] = (cur_year, "")
    if not col_period:
        raise RuntimeError("no period columns")

    first_data_col = min(col_period)
    data_start = label_row + 1 if has_period_row else year_row + 1
    label_cols = list(range(first_data_col))

    rows = []
    last_labels = [""] * len(label_cols)
    for r in range(data_start, len(df)):
        labels = [txt(df.iat[r, c]) for c in label_cols]
        labels = [labels[i] or last_labels[i] for i in range(len(labels))]  # ffill merged cells
        if not any(labels):
            continue
        last_labels = labels
        got = False
        for c, (year, lab) in col_period.items():
            v = df.iat[r, c]
            if pd.isna(v):
                continue
            try:
                num = float(str(v).replace("\xa0", "").replace(" ", "").replace(",", "."))
            except Exception:
                continue
            rows.append({
                **{f"label_{i}": labels[i] for i in range(len(labels))},
                "period_label": lab, "period": parse_period(year, lab), "value": num,
            })
            got = True
        if not got:
            continue
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("normalization produced no rows")
    return out


def download_indicator(client, need: str, ind_id: str, slug: str, timeout: int = 400) -> Dict[str, Any]:
    url = f"https://www.fedstat.ru/indicator/{ind_id}"
    req = u.Request(url, headers=headers())
    with client.open(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "replace")
    dims, meta = fb.parse_filters_from_html(html)
    title = meta.get("title") or slug
    year_dim, month_dim, region_dim, others = classify(dims)
    log(f"[{ind_id}] {title[:80]}")
    log(f"  dims: year={year_dim.object_id if year_dim else None} "
        f"month={month_dim.object_id if month_dim else None} "
        f"region={(region_dim.object_id + '/' + str(len(region_dim.values))) if region_dim else None} "
        f"others={[(d.object_id, len(d.values)) for d in others]}")
    if year_dim is None:
        raise RuntimeError("year dimension not found")

    by_id = {d.object_id: d for d in dims}
    if "0" in by_id:
        set_all(by_id["0"], [ind_id])
        by_id["0"].placement = "filter"
    for d in dims:
        if d.object_id == "0":
            continue
        set_all(d)
    year_dim.placement = "column"
    if month_dim is not None:
        month_dim.placement = "column"
    if region_dim is not None:
        region_dim.placement = "row"
    for d in others:
        d.placement = "row"

    yvals = sorted(year_dim.values, key=lambda v: v.title)
    chunks = [yvals[i:i + 13] for i in range(0, len(yvals), 13)]
    frames = []
    for chunk in chunks:
        lbl = f"{chunk[0].title}_{chunk[-1].title}"
        set_all(year_dim, [v.value_id for v in chunk])
        payload = fb.build_payload(ind_id, title, dims)
        body = urllib.parse.urlencode(payload, doseq=True).encode()
        ep = "https://www.fedstat.ru/indicator/data.do?format=excel"
        req = u.Request(ep, data=body, headers=headers(url), method="POST")
        with client.open(req, timeout=timeout) as r:
            content = r.read()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        ext, ok, msg = fb.detect_file_type(content, "", "")
        raw = RAW_DIR / f"{slug}_{ind_id}_{lbl}.{ext if ok else 'bin'}"
        raw.write_bytes(content)
        log(f"  years {lbl}: {len(content)/1e3:.0f} KB -> {raw.name}")
        if not ok or ext not in {"xls", "xlsx"}:
            log(f"    not excel: {msg}; skipping chunk")
            continue
        try:
            frames.append(normalize_excel(raw))
        except Exception as exc:
            log(f"    parse failed: {exc}")
        time.sleep(1.0)
    if not frames:
        raise RuntimeError("no parsable chunks")
    out = pd.concat(frames, ignore_index=True).drop_duplicates()
    label_cols = [c for c in out.columns if c.startswith("label_")]
    if len(label_cols) == 1:
        out = out.rename(columns={label_cols[0]: "region"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUT_DIR / f"{need}_{slug}_{ind_id}.csv"
    out.to_csv(dst, index=False, encoding="utf-8-sig")
    pmin, pmax = out["period"].min(), out["period"].max()
    log(f"  saved {dst.name}: rows={len(out)} period={pmin}..{pmax}")
    return {"need": need, "indicator": ind_id, "rows": int(len(out)),
            "period": f"{pmin}..{pmax}", "file": dst.name, "title": title}


def main() -> int:
    client = opener()
    results = []
    for need, ind_id, slug in TARGETS:
        try:
            results.append(download_indicator(client, need, ind_id, slug))
        except Exception as exc:
            log(f"[{ind_id}] FAILED: {type(exc).__name__}: {exc}")
            results.append({"need": need, "indicator": ind_id, "error": str(exc)})
        time.sleep(2.0)
    (OUT_DIR / "download_summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if "rows" in r)
    log(f"\nDONE: {ok}/{len(results)} indicators")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
