# -*- coding: utf-8 -*-
"""Headless Fedstat downloader for the index laboratory.

The script reuses the base workstation parser/payload logic from main.py, but
uses urllib from the standard library so it can run in the bundled Codex Python.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

import main as fedstat_base
from index_lab_core import (
    ROLE_BODY,
    ROLE_ENVIRONMENT,
    ROLE_TARGET,
    TRANSFORM_PERIOD_ZSCORE,
    FactorSpec,
    factors_from_dict,
    factors_to_dict,
    load_json,
    safe_id,
    save_json,
)


APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "data" / "fedstat_targets"
RAW_DIR = OUTPUT_DIR / "raw"
PROCESSED_DIR = OUTPUT_DIR / "processed"
SETTINGS_DIR = APP_DIR / "settings"
CATALOG_PATH = SETTINGS_DIR / "index_lab_factors.json"
MANIFEST_PATH = OUTPUT_DIR / "download_manifest.json"
INDICATOR_URL = "https://www.fedstat.ru/indicator/31074"
INDICATOR_ID = "31074"
DATASET_NAME = "ИПЦ целевые ряды D01-D04"

TARGET_SERIES = [
    {
        "need_id": "D01",
        "factor_id": "target_ipc_all",
        "title": "ИПЦ общий",
        "fedstat_value_id": "1707675",
        "fedstat_title": "Все товары и услуги",
    },
    {
        "need_id": "D02",
        "factor_id": "target_ipc_food",
        "title": "ИПЦ продовольственных товаров",
        "fedstat_value_id": "1748984",
        "fedstat_title": "Продовольственные товары",
    },
    {
        "need_id": "D03",
        "factor_id": "target_ipc_nonfood",
        "title": "ИПЦ непродовольственных товаров",
        "fedstat_value_id": "1744144",
        "fedstat_title": "Непродовольственные товары",
    },
    {
        "need_id": "D04",
        "factor_id": "target_ipc_services",
        "title": "ИПЦ услуг",
        "fedstat_value_id": "1744147",
        "fedstat_title": "Услуги",
    },
]

CANDIDATE_SERIES = [
    {
        "need_id": "D05",
        "factor_id": "body_ipc_food_no_alcohol",
        "title": "ИПЦ продовольственные товары без алкоголя",
        "fedstat_value_id": "1744145",
        "fedstat_title": "Продовольственные товары (без алкогольных напитков)",
        "role": ROLE_BODY,
        "subtype": "тело: продовольствие",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D05",
        "factor_id": "body_ipc_food_ex_optional",
        "title": "ИПЦ продовольственные товары без необязательных",
        "fedstat_value_id": "1790493",
        "fedstat_title": "Продовольственные товары (без товаров необязательного пользования)",
        "role": ROLE_BODY,
        "subtype": "тело: продовольствие",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D05",
        "factor_id": "body_ipc_food_optional",
        "title": "ИПЦ продовольственные товары необязательного пользования",
        "fedstat_value_id": "1790486",
        "fedstat_title": "Продовольственные товары необязательного пользования",
        "role": ROLE_BODY,
        "subtype": "тело: продовольствие",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D05",
        "factor_id": "body_ipc_food_ex_veg_pot_fruit",
        "title": "ИПЦ продовольствие без овощей, картофеля и фруктов",
        "fedstat_value_id": "1788726",
        "fedstat_title": "Продовольственные товары (без овощей, картофеля и фруктов)",
        "role": ROLE_BODY,
        "subtype": "тело: продовольствие",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D06",
        "factor_id": "body_ipc_nonfood_optional",
        "title": "ИПЦ непродовольственные товары необязательного пользования",
        "fedstat_value_id": "1790490",
        "fedstat_title": "Непродовольственные товары необязательного пользования",
        "role": ROLE_BODY,
        "subtype": "тело: непродовольственные товары",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D06",
        "factor_id": "body_ipc_nonfood_ex_optional",
        "title": "ИПЦ непродовольственные товары без необязательных",
        "fedstat_value_id": "1790489",
        "fedstat_title": "Непродовольственные товары (без товаров необязательного пользования)",
        "role": ROLE_BODY,
        "subtype": "тело: непродовольственные товары",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D07",
        "factor_id": "body_ipc_motor_fuel",
        "title": "ИПЦ моторное топливо",
        "fedstat_value_id": "1788720",
        "fedstat_title": "Топливо моторное",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: топливо",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D07",
        "factor_id": "body_ipc_gasoline",
        "title": "ИПЦ бензин автомобильный",
        "fedstat_value_id": "1755210",
        "fedstat_title": "Бензин автомобильный",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: топливо",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D07",
        "factor_id": "body_ipc_diesel",
        "title": "ИПЦ дизельное топливо",
        "fedstat_value_id": "1755196",
        "fedstat_title": "Дизельное топливо, л",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: топливо",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D08",
        "factor_id": "body_ipc_passenger_transport",
        "title": "ИПЦ услуги пассажирского транспорта",
        "fedstat_value_id": "1788843",
        "fedstat_title": "Услуги пассажирского транспорта",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: транспортные услуги",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D08",
        "factor_id": "body_ipc_rail_transport",
        "title": "ИПЦ железнодорожный транспорт",
        "fedstat_value_id": "1788769",
        "fedstat_title": "Железнодорожный транспорт",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: транспортные услуги",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
    {
        "need_id": "D08",
        "factor_id": "body_ipc_air_transport",
        "title": "ИПЦ воздушный транспорт",
        "fedstat_value_id": "1788760",
        "fedstat_title": "Воздушный транспорт",
        "role": ROLE_BODY,
        "subtype": "тело/транспорт: транспортные услуги",
        "expected_sign": "+",
        "allowed_lags": "0,1,2,3,6",
    },
]

ENVIRONMENT_SERIES = [
    {
        "need_id": "D25",
        "factor_id": "env_ipc_utilities",
        "title": "ИПЦ услуги ЖКХ",
        "fedstat_value_id": "1788763",
        "fedstat_title": "Услуги организаций ЖКХ, оказываемые населению",
        "role": ROLE_ENVIRONMENT,
        "subtype": "среда: тарифы ЖКХ",
        "expected_sign": "+/-",
        "allowed_lags": "0,1,2,3,6",
    },
]

DOWNLOAD_PACKAGES = {
    "targets_d01_d04": TARGET_SERIES,
    "candidates_d05_d08": CANDIDATE_SERIES,
    "env_d25_utilities": ENVIRONMENT_SERIES,
}

MONTH_ORDER = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def opener() -> urllib.request.OpenerDirector:
    # Fedstat currently returns an expired certificate in this environment.
    # The run manifest records this; remove the unverified context once the
    # server certificate chain is valid again.
    context = ssl._create_unverified_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(),
    )


def request_headers(referer: str = "") -> Dict[str, str]:
    headers = {
        "User-Agent": fedstat_base.DEFAULT_USER_AGENT,
        "Accept-Language": "ru,en;q=0.9",
        "Connection": "keep-alive",
    }
    if referer:
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.fedstat.ru",
            "Referer": referer,
            "Upgrade-Insecure-Requests": "1",
        })
    return headers


def fetch_indicator_page(client: urllib.request.OpenerDirector, timeout: int) -> str:
    req = urllib.request.Request(INDICATOR_URL, headers=request_headers())
    with client.open(req, timeout=timeout) as response:
        content = response.read()
    return content.decode("utf-8", errors="replace")


def set_checked(dimension: fedstat_base.FilterDimension, selected_ids: Iterable[str]) -> None:
    selected = {str(item) for item in selected_ids}
    for value in dimension.values:
        value.checked = value.value_id in selected


def configure_filters(
    dimensions: List[fedstat_base.FilterDimension],
    series_definitions: List[Dict[str, Any]],
    year_ids: List[str] | None = None,
) -> None:
    by_id = {dim.object_id: dim for dim in dimensions}
    for dim in dimensions:
        for value in dim.values:
            value.checked = False

    set_checked(by_id["0"], [INDICATOR_ID])
    set_checked(by_id["30611"], ["950473"])

    if year_ids is None:
        year_ids = [value.value_id for value in by_id["3"].values]
    set_checked(by_id["3"], year_ids)

    month_ids = [value.value_id for value in by_id["33560"].values if value.title.lower() in MONTH_ORDER]
    set_checked(by_id["33560"], month_ids)

    # Monthly change against previous month is the target signal we need first.
    set_checked(by_id["57937"], ["1704142"])
    set_checked(by_id["58273"], [item["fedstat_value_id"] for item in series_definitions])

    region_ids = []
    for value in by_id["57831"].values:
        title = value.title.lower()
        if "российская федерация" in title or "федеральный округ" in title:
            continue
        region_ids.append(value.value_id)
    set_checked(by_id["57831"], region_ids)

    by_id["0"].placement = "filter"
    by_id["30611"].placement = "filter"
    by_id["3"].placement = "column"
    by_id["33560"].placement = "column"
    by_id["57937"].placement = "column"
    by_id["58273"].placement = "row"
    by_id["57831"].placement = "row"


def configure_target_filters(dimensions: List[fedstat_base.FilterDimension]) -> None:
    configure_filters(dimensions, TARGET_SERIES)


def post_excel(
    client: urllib.request.OpenerDirector,
    payload: List[Tuple[str, str]],
    timeout: int,
) -> Tuple[bytes, Dict[str, Any]]:
    endpoint = "https://www.fedstat.ru/indicator/data.do?format=excel"
    body = urllib.parse.urlencode(payload, doseq=True).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=request_headers(INDICATOR_URL), method="POST")
    with client.open(req, timeout=timeout) as response:
        content = response.read()
        info = {
            "status": getattr(response, "status", None),
            "url": response.geturl(),
            "headers": dict(response.headers.items()),
            "size_bytes": len(content),
        }
    return content, info


def save_raw_download(
    content: bytes,
    payload: List[Tuple[str, str]],
    response_info: Dict[str, Any],
    package_id: str,
) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    ext, _, _ = fedstat_base.detect_file_type(
        content,
        str(response_info.get("headers", {}).get("Content-Type", "")),
        str(response_info.get("url", "")),
    )
    if ext not in {"xls", "xlsx", "xml", "csv", "html"}:
        ext = "bin"
    raw_path = RAW_DIR / f"fedstat_31074_{package_id}_{stamp}.{ext}"
    raw_path.write_bytes(content)
    (RAW_DIR / f"fedstat_31074_{package_id}_{stamp}_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RAW_DIR / f"fedstat_31074_{package_id}_{stamp}_response.json").write_text(
        json.dumps(response_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return raw_path


def nonempty_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_year_value(value: Any) -> str:
    text = nonempty_text(value)
    if not text:
        return ""
    match = re.search(r"(19|20)\d{2}", text)
    if match:
        return match.group(0)
    try:
        year = int(float(text.replace(" ", "").replace(",", ".")))
    except Exception:
        return ""
    if 1900 <= year <= 2100:
        return str(year)
    return ""


def detect_table_layout(df: pd.DataFrame, series_definitions: List[Dict[str, Any]]) -> Tuple[int, int, int, int]:
    target_titles = {item["fedstat_title"] for item in series_definitions}
    for row in range(min(40, len(df.index))):
        region = nonempty_text(df.iat[row, 0]) if df.shape[1] > 0 else ""
        series = nonempty_text(df.iat[row, 1]) if df.shape[1] > 1 else ""
        if region and series in target_titles and row >= 3:
            return row - 3, row - 2, row - 1, row
    raise RuntimeError("Не удалось распознать структуру таблицы Fedstat: не найдены строки данных D01-D04.")


def build_column_periods(df: pd.DataFrame, year_row: int, month_row: int) -> Dict[int, str]:
    column_periods: Dict[int, str] = {}
    current_year = ""
    for col in range(2, df.shape[1]):
        year = parse_year_value(df.iat[year_row, col])
        if year:
            current_year = year
        month = nonempty_text(df.iat[month_row, col]).lower()
        if current_year and month in MONTH_ORDER:
            column_periods[col] = f"{current_year}-{MONTH_ORDER[month]:02d}"
    if not column_periods:
        raise RuntimeError("Не удалось найти месячные колонки Fedstat в шапке Excel.")
    return column_periods


def normalize_raw_excel(raw_path: Path, series_definitions: List[Dict[str, Any]] | None = None) -> pd.DataFrame:
    series_definitions = series_definitions or TARGET_SERIES
    df = pd.read_excel(raw_path, header=None, dtype=object)
    year_row, month_row, _metric_row, data_start = detect_table_layout(df, series_definitions)
    column_periods = build_column_periods(df, year_row, month_row)
    target_titles = {item["fedstat_title"]: item for item in series_definitions}
    rows: List[Dict[str, Any]] = []
    for row in range(data_start, df.shape[0]):
        region = nonempty_text(df.iat[row, 0])
        fedstat_series = nonempty_text(df.iat[row, 1])
        if not region or fedstat_series not in target_titles:
            continue
        target = target_titles[fedstat_series]
        for col, period in column_periods.items():
            value = df.iat[row, col]
            if pd.isna(value):
                continue
            try:
                num = float(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))
            except Exception:
                continue
            rows.append({
                "need_id": target["need_id"],
                "factor_id": target["factor_id"],
                "series": target["title"],
                "fedstat_series": fedstat_series,
                "region": region,
                "period": period,
                "value": num,
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.drop_duplicates(["factor_id", "region", "period"], keep="last")
        out = out.sort_values(["factor_id", "region", "period"]).reset_index(drop=True)
    return out


def write_processed_files(
    frame: pd.DataFrame,
    package_id: str = "targets_d01_d04",
    series_definitions: List[Dict[str, Any]] | None = None,
) -> List[Path]:
    series_definitions = series_definitions or TARGET_SERIES
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    combined = PROCESSED_DIR / f"fedstat_31074_{package_id}_long.csv"
    frame.to_csv(combined, index=False, encoding="utf-8-sig")
    paths.append(combined)
    for item in series_definitions:
        part = frame[frame["factor_id"] == item["factor_id"]][["region", "period", "value"]].copy()
        path = PROCESSED_DIR / f"{item['factor_id']}.csv"
        part.to_csv(path, index=False, encoding="utf-8-sig")
        paths.append(path)
    return paths


def update_factor_catalog(
    processed_paths: List[Path],
    frame: pd.DataFrame | None = None,
    series_definitions: List[Dict[str, Any]] | None = None,
) -> None:
    series_definitions = series_definitions or TARGET_SERIES
    existing: List[FactorSpec] = []
    if CATALOG_PATH.exists():
        existing = factors_from_dict(load_json(CATALOG_PATH))
    by_id = {factor.factor_id: factor for factor in existing}
    existing_ids = [factor.factor_id for factor in existing]
    path_by_stem = {path.stem: path for path in processed_paths}
    period_bounds: Dict[str, Tuple[str, str]] = {}
    if frame is not None and not frame.empty:
        for factor_id, group in frame.groupby("factor_id"):
            period_bounds[str(factor_id)] = (str(group["period"].min()), str(group["period"].max()))
    for item in series_definitions:
        factor_id = item["factor_id"]
        path = path_by_stem.get(factor_id)
        if not path:
            continue
        role = item.get("role", ROLE_TARGET)
        factor = by_id.get(factor_id)
        if factor is None:
            factor = FactorSpec(
                factor_id=safe_id(factor_id, existing_ids),
                name=item["title"],
                role=role,
                source_path=str(path),
                region_column="region",
                period_column="period",
                value_column="value",
                transform=item.get("transform", TRANSFORM_PERIOD_ZSCORE),
                enabled=True,
            )
            existing.append(factor)
            by_id[factor.factor_id] = factor
            existing_ids.append(factor.factor_id)
        factor.name = item["title"]
        factor.role = role
        factor.source_path = str(path)
        factor.region_column = "region"
        factor.period_column = "period"
        factor.value_column = "value"
        factor.transform = item.get("transform", TRANSFORM_PERIOD_ZSCORE)
        factor.enabled = True
        factor.subtype = item.get("subtype", "целевая инфляция")
        factor.source_name = "Fedstat / Росстат, показатель 31074"
        factor.frequency = "месяц"
        factor.level = "регион"
        factor.units = "процент к предыдущему месяцу"
        factor.value_description = item["fedstat_title"]
        if factor_id in period_bounds:
            factor.period_start, factor.period_end = period_bounds[factor_id]
        factor.expected_sign = item.get("expected_sign", "цель")
        factor.allowed_lags = item.get("allowed_lags", "0" if role == ROLE_TARGET else "0,1,2,3,6")
        factor.quality_status = "скачано, требует проверки"
        factor.missing_policy = "не проверено"
        factor.passport_status = "готов к разведке"
        factor.note = f"{item['need_id']}; Fedstat value_id={item['fedstat_value_id']}"
    save_json(CATALOG_PATH, factors_to_dict(existing))


def download_package(
    client: urllib.request.OpenerDirector,
    page_html: str,
    package_id: str,
    series_definitions: List[Dict[str, Any]],
    timeout: int,
) -> Dict[str, Any]:
    dimensions, metadata = fedstat_base.parse_filters_from_html(page_html)
    by_id = {dim.object_id: dim for dim in dimensions}

    # Формат .xls ограничен 256 колонками, поэтому полный период (25 лет)
    # в одну выгрузку не помещается: сервер режет колонки на ~2023-01.
    # Качаем годы кусками по <=13 лет (<=158 колонок) и склеиваем.
    year_values = sorted(by_id["3"].values, key=lambda v: v.title)
    chunks = [year_values[i:i + 13] for i in range(0, len(year_values), 13)]

    frames: List[pd.DataFrame] = []
    raw_paths: List[str] = []
    chunk_errors: List[str] = []
    for chunk in chunks:
        label = f"{chunk[0].title}_{chunk[-1].title}"
        try:
            configure_filters(dimensions, series_definitions, [v.value_id for v in chunk])
            payload = fedstat_base.build_payload(
                INDICATOR_ID,
                metadata.get("title") or DATASET_NAME,
                dimensions,
            )
            print(f"POST {package_id} years {label}: payload fields {len(payload)}, "
                  f"series {len(series_definitions)}")
            content, response_info = post_excel(client, payload, timeout)
            raw_path = save_raw_download(content, payload, response_info, f"{package_id}_y{label}")
            raw_paths.append(str(raw_path))
            print(f"Raw response saved: {raw_path}")

            ext, ok, message = fedstat_base.detect_file_type(
                content,
                str(response_info.get("headers", {}).get("Content-Type", "")),
                str(response_info.get("url", "")),
            )
            if not ok or ext not in {"xlsx", "xls"}:
                preview_path = RAW_DIR / f"{raw_path.stem}_preview.txt"
                preview_path.write_text(content[:50000].decode("utf-8", errors="replace"), encoding="utf-8")
                raise RuntimeError(f"Fedstat did not return Excel data: {message}. Preview: {preview_path}")

            chunk_frame = normalize_raw_excel(raw_path, series_definitions)
            if chunk_frame.empty:
                print(f"  years {label}: no rows in this chunk")
            else:
                frames.append(chunk_frame)
        except Exception as exc:
            chunk_errors.append(f"{label}: {exc}")
            print(f"  years {label} failed: {exc}")

    if not frames:
        raise RuntimeError("All year chunks empty or failed: " + "; ".join(chunk_errors))

    frame = pd.concat(frames, ignore_index=True)
    frame = frame.drop_duplicates(["factor_id", "region", "period"], keep="last")
    frame = frame.sort_values(["factor_id", "region", "period"]).reset_index(drop=True)
    processed_paths = write_processed_files(frame, package_id, series_definitions)
    update_factor_catalog(processed_paths, frame, series_definitions)

    return {
        "status": "ok",
        "metadata": metadata,
        "raw_paths": raw_paths,
        "chunk_errors": chunk_errors,
        "processed_paths": [str(path) for path in processed_paths],
        "rows": int(len(frame)),
        "series": frame.groupby("factor_id").size().to_dict(),
        "period_min": str(frame["period"].min()),
        "period_max": str(frame["period"].max()),
        "regions": int(frame["region"].nunique()),
    }


def main(timeout: int = 240, only_package: str | None = None) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = opener()
    print("Loading Fedstat indicator page...")
    page_html = fetch_indicator_page(client, timeout)

    packages = DOWNLOAD_PACKAGES
    if only_package:
        packages = {k: v for k, v in DOWNLOAD_PACKAGES.items() if k == only_package}
        if not packages:
            raise SystemExit(f"Unknown package: {only_package}")

    package_results: Dict[str, Any] = {}
    for package_id, series_definitions in packages.items():
        try:
            package_results[package_id] = download_package(client, page_html, package_id, series_definitions, timeout)
        except Exception as exc:
            package_results[package_id] = {"status": "failed", "error": str(exc)}
            print(f"{package_id} failed: {exc}")

    # при фильтре пакетов не терять прежние записи манифеста
    if MANIFEST_PATH.exists():
        try:
            prev = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("packages", {})
            for k, v in prev.items():
                package_results.setdefault(k, v)
        except Exception:
            pass

    ok_packages = {key: value for key, value in package_results.items() if value.get("status") == "ok"}
    manifest = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "indicator_url": INDICATOR_URL,
        "indicator_id": INDICATOR_ID,
        "ssl_verification": "disabled because Fedstat certificate validation failed in this environment",
        "packages": package_results,
        "ok_package_count": len(ok_packages),
        "rows": sum(int(value.get("rows", 0)) for value in ok_packages.values()),
        "downloaded_need_ids": sorted({
            item["need_id"]
            for package_id, series_definitions in DOWNLOAD_PACKAGES.items()
            if package_results.get(package_id, {}).get("status") == "ok"
            for item in series_definitions
        }),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if ok_packages else 1


if __name__ == "__main__":
    timeout_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    package_arg = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(main(timeout_arg, package_arg))
