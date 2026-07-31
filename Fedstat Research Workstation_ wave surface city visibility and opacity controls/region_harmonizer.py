# -*- coding: utf-8 -*-
"""Download and build regional reference layers for the index laboratory."""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
GEO_DIR = APP_DIR / "data" / "geo"
SETTINGS_DIR = APP_DIR / "settings"
FEDSTAT_LONG_PATH = APP_DIR / "data" / "fedstat_targets" / "processed" / "fedstat_31074_targets_d01_d04_long.csv"
BUILTIN_REFERENCE_PATH = GEO_DIR / "regions_reference.csv"

GEODOWNLOAD_API = "https://www.geoboundaries.org/api/current/gbOpen/RUS/ADM1/"
DEEONE_REGION_CSV_URL = "https://deeone.dev/assets/data/ru-subjects.csv"

GEODOWNLOAD_PATH = GEO_DIR / "custom_geoboundaries_rus_adm1.geojson"
GEODOWNLOAD_METADATA_PATH = GEO_DIR / "custom_geoboundaries_metadata.json"
DEEONE_RAW_PATH = GEO_DIR / "internet_ru_subjects_deeone.csv"
DEEONE_REFERENCE_PATH = GEO_DIR / "regions_reference_internet.csv"
HARMONIZATION_PATH = GEO_DIR / "fedstat_region_harmonization.csv"
HARMONIZED_REFERENCE_PATH = GEO_DIR / "regions_reference_fedstat_harmonized.csv"
FEATURE_INDEX_PATH = GEO_DIR / "geoboundaries_feature_index.csv"
REPORT_PATH = GEO_DIR / "region_harmonization_report.json"
GEO_SETTINGS_PATH = SETTINGS_DIR / "geo_settings.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

FEDERAL_DISTRICT_FULL = {
    "ЦФО": "Центральный федеральный округ",
    "СЗФО": "Северо-Западный федеральный округ",
    "ЮФО": "Южный федеральный округ",
    "СКФО": "Северо-Кавказский федеральный округ",
    "ПФО": "Приволжский федеральный округ",
    "УФО": "Уральский федеральный округ",
    "СФО": "Сибирский федеральный округ",
    "ДФО": "Дальневосточный федеральный округ",
}

EXTERNAL_NAME_CANONICAL = {
    "Москва": "г. Москва",
    "Санкт-Петербург": "г. Санкт-Петербург",
    "Севастополь": "г. Севастополь",
    "Ненецкий АО": "Ненецкий автономный округ",
    "Ямало-Ненецкий АО": "Ямало-Ненецкий автономный округ",
    "Ханты-Мансийский АО — Югра": "Ханты-Мансийский автономный округ - Югра",
    "Ханты-Мансийский АО - Югра": "Ханты-Мансийский автономный округ - Югра",
    "Еврейская АО": "Еврейская автономная область",
    "Кемеровская область — Кузбасс": "Кемеровская область",
    "Кемеровская область - Кузбасс": "Кемеровская область",
    "Республика Северная Осетия — Алания": "Республика Северная Осетия - Алания",
    "Республика Северная Осетия - Алания": "Республика Северная Осетия - Алания",
}

NAME_VARIANTS = {
    "Город Москва столица Российской Федерации город федерального значения": "г. Москва",
    "Город Санкт-Петербург город федерального значения": "г. Санкт-Петербург",
    "Город федерального значения Севастополь": "г. Севастополь",
    "Республика Адыгея (Адыгея)": "Республика Адыгея",
    "Республика Татарстан (Татарстан)": "Республика Татарстан",
    "Республика Северная Осетия-Алания": "Республика Северная Осетия - Алания",
    "Чувашская Республика - Чувашия": "Чувашская Республика",
    "Кемеровская область - Кузбасс": "Кемеровская область",
    "Ненецкий автономный округ (Архангельская область)": "Ненецкий автономный округ",
    "Ханты-Мансийский автономный округ - Югра (Тюменская область)": "Ханты-Мансийский автономный округ - Югра",
    "Ямало-Ненецкий автономный округ (Тюменская область)": "Ямало-Ненецкий автономный округ",
}

HISTORICAL_SUBREGIONS = {
    "Агинский Бурятский округ (Забайкальский край)": "исторический округ внутри Забайкальского края",
    "Коми-Пермяцкий округ, входящий в состав Пермского края": "исторический округ внутри Пермского края",
    "Корякский округ, входящий в состав Камчатского края": "исторический округ внутри Камчатского края",
    "Таймырский (Долгано-Ненецкий) автономный округ (Красноярский край)": "исторический округ внутри Красноярского края",
    "Усть-Ордынский Бурятский округ": "исторический округ внутри Иркутской области",
    "Эвенкийский автономный округ (Красноярский край)": "исторический округ внутри Красноярского края",
}


def normalize_key(text: Any) -> str:
    value = str(text or "").replace("ё", "е").replace("–", "-").replace("—", "-").strip().lower()
    value = re.sub(r"\s*-\s*", "-", value)
    value = re.sub(r"\s+", " ", value)
    return value


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def first_present(row: Any, names: Iterable[str]) -> Any:
    for name in names:
        if name in row:
            value = row.get(name)
            if clean_cell(value):
                return value
    return ""


def fetch_bytes(url: str, timeout: int = 240, allow_unverified_ssl: bool = False) -> Tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl._create_unverified_context() if allow_unverified_ssl else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            return response.read(), response.geturl()
    except Exception:
        if allow_unverified_ssl:
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as response:
            return response.read(), response.geturl()


def download_geoboundaries() -> Dict[str, Any]:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    content, final_url = fetch_bytes(GEODOWNLOAD_API, timeout=120)
    metadata = json.loads(content.decode("utf-8"))
    geojson_url = metadata.get("gjDownloadURL") or metadata.get("simplifiedGeometryGeoJSON") or metadata.get("dlPath")
    if not geojson_url:
        raise RuntimeError("В ответе geoBoundaries нет ссылки на GeoJSON.")
    geojson_content, geojson_final_url = fetch_bytes(str(geojson_url), timeout=300)
    GEODOWNLOAD_PATH.write_bytes(geojson_content)
    metadata["api_url"] = GEODOWNLOAD_API
    metadata["api_final_url"] = final_url
    metadata["geojson_final_url"] = geojson_final_url
    metadata["downloaded_at"] = dt.datetime.now().isoformat(timespec="seconds")
    GEODOWNLOAD_METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def download_deeone_reference() -> pd.DataFrame:
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    content, final_url = fetch_bytes(DEEONE_REGION_CSV_URL, timeout=120)
    DEEONE_RAW_PATH.write_bytes(content)
    frame = pd.read_csv(DEEONE_RAW_PATH, sep=";", encoding="utf-8-sig")
    frame.attrs["source_url"] = final_url
    return frame


def convert_deeone_reference(frame: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        raw_name = clean_cell(first_present(row, ["name", "Полное имя"]))
        name = EXTERNAL_NAME_CANONICAL.get(raw_name, raw_name)
        if not name:
            continue
        fo = clean_cell(first_present(row, ["fo", "Федеральный округ"]))
        rows.append({
            "fedstat_name": name,
            "geo_name": name,
            "federal_district": FEDERAL_DISTRICT_FULL.get(fo, fo),
            "capital_city": clean_cell(first_present(row, ["capital", "Столица"])),
            "capital_lat": first_present(row, ["lat", "Широта столицы"]),
            "capital_lon": first_present(row, ["lon", "Долгота столицы"]),
            "region_code": clean_cell(first_present(row, ["iso", "ISO 3166-2"])),
            "name_short": clean_cell(first_present(row, ["name_short", "Краткое имя"])),
            "source": "DEEONE ru-subjects.csv",
        })
    out = pd.DataFrame(rows)
    out.to_csv(DEEONE_REFERENCE_PATH, index=False, encoding="utf-8-sig")
    return out


def load_builtin_reference() -> pd.DataFrame:
    return pd.read_csv(BUILTIN_REFERENCE_PATH, encoding="utf-8-sig")


def merge_reference(external: pd.DataFrame, builtin: pd.DataFrame) -> pd.DataFrame:
    rows: Dict[str, Dict[str, Any]] = {}
    for _, row in builtin.iterrows():
        name = str(row.get("fedstat_name") or "").strip()
        if not name or "федеральный округ" in name.lower() or name == "Российская Федерация":
            continue
        rows[normalize_key(name)] = dict(row)
        rows[normalize_key(str(row.get("geo_name") or name))] = dict(row)
    for _, row in external.iterrows():
        name = str(row.get("fedstat_name") or "").strip()
        if not name:
            continue
        clean = dict(row)
        key = normalize_key(name)
        rows[key] = {**rows.get(key, {}), **clean}
    return pd.DataFrame(list({normalize_key(v.get("fedstat_name")): v for v in rows.values()}.values()))


def read_fedstat_regions() -> List[str]:
    frame = pd.read_csv(FEDSTAT_LONG_PATH, encoding="utf-8-sig", usecols=["region"])
    return sorted(str(item).strip() for item in frame["region"].dropna().unique())


def reference_lookup(reference: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in reference.iterrows():
        data = dict(row)
        for column in ["fedstat_name", "geo_name", "name_short"]:
            value = str(data.get(column) or "").strip()
            if value:
                lookup[normalize_key(value)] = data
    return lookup


def classify_region(name: str, reference: pd.DataFrame, lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    key = normalize_key(name)
    if "экономический район" in key:
        return make_mapping_row(name, "", "", "economic_region", "exclude_aggregate", "экономический район, не субъект РФ", False)
    if "кроме" in key:
        return make_mapping_row(name, "", "", "partial_parent_region", "exclude_partial_region", "часть субъекта, не полный регион", False)
    if name in HISTORICAL_SUBREGIONS:
        return make_mapping_row(name, "", "", "historical_subregion", "exclude_historical_subregion", HISTORICAL_SUBREGIONS[name], False)
    canonical = NAME_VARIANTS.get(name)
    if canonical:
        info = lookup.get(normalize_key(canonical), {})
        return make_mapping_row(name, canonical, info, "subject_name_variant", "map_to_canonical", "вариант имени Fedstat", True)
    if key in lookup:
        info = lookup[key]
        canonical_name = str(info.get("fedstat_name") or name).strip()
        return make_mapping_row(name, canonical_name, info, "subject", "keep", "совпало со справочником", True)
    for _, row in reference.iterrows():
        candidate = str(row.get("fedstat_name") or "").strip()
        candidate_key = normalize_key(candidate)
        if candidate_key and (candidate_key in key or key in candidate_key):
            return make_mapping_row(name, candidate, dict(row), "subject_fuzzy", "map_to_canonical", "сопоставлено по вхождению имени", True)
    return make_mapping_row(name, "", "", "unmatched", "manual_review", "не найдено автоматическое сопоставление", False)


def make_mapping_row(
    fedstat_name: str,
    canonical_region: str,
    info: Dict[str, Any] | str,
    region_type: str,
    action: str,
    note: str,
    use_in_subject_panel: bool,
) -> Dict[str, Any]:
    data = info if isinstance(info, dict) else {}
    return {
        "fedstat_name": fedstat_name,
        "canonical_region": canonical_region,
        "region_type": region_type,
        "action": action,
        "use_in_subject_panel": "yes" if use_in_subject_panel else "no",
        "federal_district": clean_cell(data.get("federal_district")),
        "capital_city": clean_cell(data.get("capital_city")),
        "capital_lat": data.get("capital_lat", ""),
        "capital_lon": data.get("capital_lon", ""),
        "region_code": clean_cell(data.get("region_code")),
        "note": note,
    }


def write_feature_index() -> int:
    data = json.loads(GEODOWNLOAD_PATH.read_text(encoding="utf-8"))
    features = data.get("features") if isinstance(data, dict) else []
    rows = []
    for feature in features or []:
        props = feature.get("properties") or {}
        rows.append({
            "shape_id": props.get("shapeID", ""),
            "shape_iso": props.get("shapeISO", ""),
            "shape_name": props.get("shapeName", ""),
            "shape_type": props.get("shapeType", ""),
        })
    pd.DataFrame(rows).to_csv(FEATURE_INDEX_PATH, index=False, encoding="utf-8-sig")
    return len(rows)


def write_harmonization() -> pd.DataFrame:
    external = convert_deeone_reference(download_deeone_reference())
    builtin = load_builtin_reference()
    reference = merge_reference(external, builtin)
    lookup = reference_lookup(reference)
    rows = [classify_region(region, reference, lookup) for region in read_fedstat_regions()]
    mapping = pd.DataFrame(rows)
    mapping.to_csv(HARMONIZATION_PATH, index=False, encoding="utf-8-sig")

    keep = mapping[mapping["use_in_subject_panel"] == "yes"].copy()
    keep = keep[[
        "fedstat_name",
        "canonical_region",
        "federal_district",
        "capital_city",
        "capital_lat",
        "capital_lon",
        "region_code",
        "region_type",
        "action",
        "note",
    ]]
    keep = keep.rename(columns={"canonical_region": "geo_name"})
    keep.to_csv(HARMONIZED_REFERENCE_PATH, index=False, encoding="utf-8-sig")
    return mapping


def write_settings() -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    settings = {
        "source": "geoBoundaries ADM1 + DEEONE ru-subjects + Fedstat harmonization",
        "geojson_path": str(GEODOWNLOAD_PATH),
        "region_reference_path": str(HARMONIZED_REFERENCE_PATH),
    }
    GEO_SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def counts_by(values: Iterable[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return dict(sorted(result.items()))


def main() -> int:
    metadata = download_geoboundaries()
    feature_count = write_feature_index()
    mapping = write_harmonization()
    write_settings()
    report = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "geoboundaries_api": GEODOWNLOAD_API,
        "geoboundaries_boundary_id": metadata.get("boundaryID"),
        "geoboundaries_boundary_year": metadata.get("boundaryYearRepresented"),
        "geoboundaries_adm_unit_count": metadata.get("admUnitCount"),
        "geoboundaries_feature_count": feature_count,
        "deeone_csv_url": DEEONE_REGION_CSV_URL,
        "fedstat_region_count": int(len(mapping)),
        "subject_panel_region_count": int((mapping["use_in_subject_panel"] == "yes").sum()),
        "counts_by_region_type": counts_by(mapping["region_type"]),
        "counts_by_action": counts_by(mapping["action"]),
        "outputs": {
            "geojson": str(GEODOWNLOAD_PATH),
            "geoboundaries_metadata": str(GEODOWNLOAD_METADATA_PATH),
            "deeone_raw": str(DEEONE_RAW_PATH),
            "deeone_reference": str(DEEONE_REFERENCE_PATH),
            "feature_index": str(FEATURE_INDEX_PATH),
            "harmonization": str(HARMONIZATION_PATH),
            "harmonized_reference": str(HARMONIZED_REFERENCE_PATH),
            "geo_settings": str(GEO_SETTINGS_PATH),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
