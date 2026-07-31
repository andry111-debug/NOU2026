# -*- coding: utf-8 -*-
"""
Fedstat Research Workstation
Version: N_106

Назначение:
- загрузка фильтров Fedstat/ЕМИСС из страницы показателя;
- сохранение и повторное использование набора фильтров;
- скачивание сформированной таблицы Fedstat по выбранным фильтрам;
- построение карты РФ и карты показателя через отдельное окно PySide6 WebView с MapLibre GL JS;
- отрисовка карты выполняется стандартным WebGL-движком, без Matplotlib Canvas.
"""

from __future__ import annotations

import csv
import datetime as _dt
import html
import hashlib
import json
import math
import os
import pickle
import subprocess
import re
import shutil
import sys
import threading
import traceback
import time
import urllib.parse
import webbrowser
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    import plotly.graph_objects as go
    import plotly.io as pio
except Exception:  # pragma: no cover
    go = None
    pio = None

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
    from mpl_toolkits.mplot3d import proj3d
except Exception:  # pragma: no cover
    Figure = None
    FigureCanvasTkAgg = None
    NavigationToolbar2Tk = None
    Poly3DCollection = None
    proj3d = None

APP_NAME = "Fedstat Research Workstation"
APP_VERSION = "N_106"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = Path.cwd() / "settings"
DEFAULT_FILTER_SCHEME_PATH = SETTINGS_DIR / "fedstat_saved_filters.json"
LAST_SETTINGS_PATH = SETTINGS_DIR / "last_settings.json"
GEO_SETTINGS_PATH = SETTINGS_DIR / "geo_settings.json"
GEO_BOUNDARY_CACHE_DIR = APP_DIR / "data" / "geo" / "cache"
BUILTIN_GEO_DIR = APP_DIR / "data" / "geo"
BUILTIN_RUSSIA_GEOJSON_PATH = BUILTIN_GEO_DIR / "russia_country_outline.geojson"
BUILTIN_REGION_REFERENCE_PATH = BUILTIN_GEO_DIR / "regions_reference.csv"
BUILTIN_GEO_METADATA_PATH = BUILTIN_GEO_DIR / "geo_metadata.json"

# Approximate coordinates of subjects / administrative centers.
# The built-in geometry is a practical analytical layer, not an official cartographic dataset.
REGION_COORDS: Dict[str, Tuple[float, float, str, str]] = {
    "Российская Федерация": (55.75, 37.62, "РФ", "Москва"),
    "Центральный федеральный округ": (55.75, 37.62, "ЦФО", "Москва"),
    "Белгородская область": (50.60, 36.59, "ЦФО", "Белгород"),
    "Брянская область": (53.25, 34.37, "ЦФО", "Брянск"),
    "Владимирская область": (56.13, 40.41, "ЦФО", "Владимир"),
    "Воронежская область": (51.66, 39.20, "ЦФО", "Воронеж"),
    "Ивановская область": (57.00, 40.97, "ЦФО", "Иваново"),
    "Калужская область": (54.51, 36.26, "ЦФО", "Калуга"),
    "Костромская область": (57.77, 40.93, "ЦФО", "Кострома"),
    "Курская область": (51.73, 36.19, "ЦФО", "Курск"),
    "Липецкая область": (52.61, 39.59, "ЦФО", "Липецк"),
    "Московская область": (55.75, 37.62, "ЦФО", "Москва"),
    "Орловская область": (52.97, 36.06, "ЦФО", "Орел"),
    "Рязанская область": (54.63, 39.74, "ЦФО", "Рязань"),
    "Смоленская область": (54.78, 32.04, "ЦФО", "Смоленск"),
    "Тамбовская область": (52.72, 41.45, "ЦФО", "Тамбов"),
    "Тверская область": (56.86, 35.92, "ЦФО", "Тверь"),
    "Тульская область": (54.20, 37.62, "ЦФО", "Тула"),
    "Ярославская область": (57.63, 39.87, "ЦФО", "Ярославль"),
    "г. Москва": (55.75, 37.62, "ЦФО", "Москва"),
    "Москва": (55.75, 37.62, "ЦФО", "Москва"),

    "Северо-Западный федеральный округ": (59.94, 30.31, "СЗФО", "Санкт-Петербург"),
    "Республика Карелия": (61.79, 34.36, "СЗФО", "Петрозаводск"),
    "Республика Коми": (61.67, 50.84, "СЗФО", "Сыктывкар"),
    "Архангельская область": (64.54, 40.54, "СЗФО", "Архангельск"),
    "Вологодская область": (59.22, 39.89, "СЗФО", "Вологда"),
    "Калининградская область": (54.71, 20.51, "СЗФО", "Калининград"),
    "Ленинградская область": (59.94, 30.31, "СЗФО", "Санкт-Петербург"),
    "Мурманская область": (68.97, 33.08, "СЗФО", "Мурманск"),
    "Новгородская область": (58.52, 31.28, "СЗФО", "Великий Новгород"),
    "Псковская область": (57.82, 28.33, "СЗФО", "Псков"),
    "г. Санкт-Петербург": (59.94, 30.31, "СЗФО", "Санкт-Петербург"),
    "Санкт-Петербург": (59.94, 30.31, "СЗФО", "Санкт-Петербург"),
    "Ненецкий автономный округ": (67.64, 53.01, "СЗФО", "Нарьян-Мар"),

    "Южный федеральный округ": (47.23, 39.72, "ЮФО", "Ростов-на-Дону"),
    "Республика Адыгея": (44.61, 40.10, "ЮФО", "Майкоп"),
    "Республика Калмыкия": (46.31, 44.27, "ЮФО", "Элиста"),
    "Республика Крым": (44.95, 34.10, "ЮФО", "Симферополь"),
    "Краснодарский край": (45.04, 38.98, "ЮФО", "Краснодар"),
    "Астраханская область": (46.35, 48.04, "ЮФО", "Астрахань"),
    "Волгоградская область": (48.71, 44.51, "ЮФО", "Волгоград"),
    "Ростовская область": (47.23, 39.72, "ЮФО", "Ростов-на-Дону"),
    "г. Севастополь": (44.62, 33.53, "ЮФО", "Севастополь"),

    "Северо-Кавказский федеральный округ": (44.05, 43.06, "СКФО", "Пятигорск"),
    "Республика Дагестан": (42.98, 47.50, "СКФО", "Махачкала"),
    "Республика Ингушетия": (43.17, 44.82, "СКФО", "Магас"),
    "Кабардино-Балкарская Республика": (43.49, 43.61, "СКФО", "Нальчик"),
    "Карачаево-Черкесская Республика": (44.23, 42.05, "СКФО", "Черкесск"),
    "Республика Северная Осетия - Алания": (43.02, 44.68, "СКФО", "Владикавказ"),
    "Чеченская Республика": (43.32, 45.70, "СКФО", "Грозный"),
    "Ставропольский край": (45.04, 41.97, "СКФО", "Ставрополь"),

    "Приволжский федеральный округ": (56.33, 44.01, "ПФО", "Нижний Новгород"),
    "Республика Башкортостан": (54.74, 55.97, "ПФО", "Уфа"),
    "Республика Марий Эл": (56.63, 47.89, "ПФО", "Йошкар-Ола"),
    "Республика Мордовия": (54.18, 45.18, "ПФО", "Саранск"),
    "Республика Татарстан": (55.79, 49.12, "ПФО", "Казань"),
    "Удмуртская Республика": (56.85, 53.20, "ПФО", "Ижевск"),
    "Чувашская Республика": (56.13, 47.25, "ПФО", "Чебоксары"),
    "Пермский край": (58.01, 56.25, "ПФО", "Пермь"),
    "Кировская область": (58.60, 49.67, "ПФО", "Киров"),
    "Нижегородская область": (56.33, 44.01, "ПФО", "Нижний Новгород"),
    "Оренбургская область": (51.77, 55.10, "ПФО", "Оренбург"),
    "Пензенская область": (53.20, 45.00, "ПФО", "Пенза"),
    "Самарская область": (53.20, 50.15, "ПФО", "Самара"),
    "Саратовская область": (51.53, 46.03, "ПФО", "Саратов"),
    "Ульяновская область": (54.31, 48.40, "ПФО", "Ульяновск"),

    "Уральский федеральный округ": (56.84, 60.61, "УФО", "Екатеринбург"),
    "Курганская область": (55.44, 65.34, "УФО", "Курган"),
    "Свердловская область": (56.84, 60.61, "УФО", "Екатеринбург"),
    "Тюменская область": (57.15, 65.53, "УФО", "Тюмень"),
    "Челябинская область": (55.16, 61.40, "УФО", "Челябинск"),
    "Ханты-Мансийский автономный округ - Югра": (61.00, 69.02, "УФО", "Ханты-Мансийск"),
    "Ямало-Ненецкий автономный округ": (66.53, 66.61, "УФО", "Салехард"),

    "Сибирский федеральный округ": (55.03, 82.92, "СФО", "Новосибирск"),
    "Республика Алтай": (51.96, 85.96, "СФО", "Горно-Алтайск"),
    "Республика Тыва": (51.72, 94.44, "СФО", "Кызыл"),
    "Республика Хакасия": (53.72, 91.44, "СФО", "Абакан"),
    "Алтайский край": (53.35, 83.76, "СФО", "Барнаул"),
    "Красноярский край": (56.01, 92.87, "СФО", "Красноярск"),
    "Иркутская область": (52.29, 104.28, "СФО", "Иркутск"),
    "Кемеровская область": (55.35, 86.09, "СФО", "Кемерово"),
    "Новосибирская область": (55.03, 82.92, "СФО", "Новосибирск"),
    "Омская область": (54.99, 73.37, "СФО", "Омск"),
    "Томская область": (56.48, 84.95, "СФО", "Томск"),

    "Дальневосточный федеральный округ": (43.12, 131.89, "ДФО", "Владивосток"),
    "Республика Бурятия": (51.83, 107.58, "ДФО", "Улан-Удэ"),
    "Республика Саха (Якутия)": (62.03, 129.73, "ДФО", "Якутск"),
    "Забайкальский край": (52.03, 113.50, "ДФО", "Чита"),
    "Камчатский край": (53.04, 158.65, "ДФО", "Петропавловск-Камчатский"),
    "Приморский край": (43.12, 131.89, "ДФО", "Владивосток"),
    "Хабаровский край": (48.48, 135.08, "ДФО", "Хабаровск"),
    "Амурская область": (50.29, 127.53, "ДФО", "Благовещенск"),
    "Магаданская область": (59.57, 150.80, "ДФО", "Магадан"),
    "Сахалинская область": (46.96, 142.73, "ДФО", "Южно-Сахалинск"),
    "Еврейская автономная область": (48.79, 132.92, "ДФО", "Биробиджан"),
    "Чукотский автономный округ": (64.73, 177.51, "ДФО", "Анадырь"),
}

FD_NAMES = {
    "ЦФО": "Центральный федеральный округ",
    "СЗФО": "Северо-Западный федеральный округ",
    "ЮФО": "Южный федеральный округ",
    "СКФО": "Северо-Кавказский федеральный округ",
    "ПФО": "Приволжский федеральный округ",
    "УФО": "Уральский федеральный округ",
    "СФО": "Сибирский федеральный округ",
    "ДФО": "Дальневосточный федеральный округ",
}


@dataclass
class FilterValue:
    value_id: str
    title: str
    order: int = 0
    checked: bool = False


@dataclass
class FilterDimension:
    object_id: str
    title: str
    values: List[FilterValue] = field(default_factory=list)
    all_flag: bool = False
    indicator: bool = False
    placement: str = "ignore"  # row, column, filter, ignore

    def selected_values(self) -> List[FilterValue]:
        return [v for v in self.values if v.checked]


@dataclass
class DownloadResult:
    file_path: Optional[str]
    response_info_path: Optional[str]
    preview_path: Optional[str]
    message: str
    is_statistics_file: bool
    content_type: str = ""
    status_code: Optional[int] = None
    final_url: str = ""


def safe_name(value: str, max_len: int = 80) -> str:
    value = value.strip() or "fedstat"
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value[:max_len] or "fedstat"


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


DATA_FILE_EXTENSIONS = {".xlsx", ".xls", ".csv", ".xml", ".sdmx"}
SERVICE_FILE_EXTENSIONS = {".html", ".htm", ".json", ".txt", ".log", ".zip"}
SERVICE_FILE_MARKERS = (
    "source_page",
    "preview",
    "response_info",
    "request_metadata",
    "selected_filters",
    "run_manifest",
    "run_log",
    "attempt",
    "request_body",
    "request_equivalent_curl",
    "README_",
)


def looks_like_service_file(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() in SERVICE_FILE_EXTENSIONS:
        return True
    return any(marker.lower() in name for marker in SERVICE_FILE_MARKERS)


def is_data_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in DATA_FILE_EXTENSIONS and not looks_like_service_file(path)


def detect_file_type(content: bytes, content_type: str, final_url: str) -> Tuple[str, bool, str]:
    prefix = content[:512].lstrip()
    ct = (content_type or "").lower()
    url = (final_url or "").lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or b"<html" in prefix[:200].lower():
        return "html", False, "Сервер вернул HTML-страницу, это не файл статистики."
    if content.startswith(b"PK\x03\x04"):
        return "xlsx", True, "Сервер вернул ZIP/XLSX-совместимый бинарный файл."
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "xls", True, "Сервер вернул старый Excel-файл XLS."
    if prefix.startswith(b"<?xml") or prefix.startswith(b"<message") or prefix.startswith(b"<CompactData") or prefix.startswith(b"<GenericData"):
        return "xml", True, "Сервер вернул XML/SDMX-файл."
    if "spreadsheet" in ct or "excel" in ct or "vnd.ms-excel" in ct:
        return "xls", True, "Content-Type похож на Excel."
    if "officedocument.spreadsheetml" in ct:
        return "xlsx", True, "Content-Type похож на XLSX."
    if "xml" in ct or "sdmx" in ct:
        return "xml", True, "Content-Type похож на XML/SDMX."
    if "text/csv" in ct or url.endswith(".csv"):
        return "csv", True, "Content-Type похож на CSV."
    if "json" in ct:
        return "json", False, "Сервер вернул JSON. Нужно проверить содержимое."
    return "bin", False, "Тип ответа не распознан как файл статистики."


def decode_js_string(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        if raw[0] in ("'", '"'):
            quote = raw[0]
            inner = raw[1:-1] if raw.endswith(quote) else raw[1:]
            inner = inner.replace('\\\n', '\\n')
            if quote == "'":
                inner = inner.replace("\\'", "'").replace('"', '\\"')
            return html.unescape(json.loads('"' + inner + '"'))
    except Exception:
        pass
    try:
        return html.unescape(bytes(raw, "utf-8").decode("unicode_escape"))
    except Exception:
        return html.unescape(raw.strip("'\""))


def find_balanced(text: str, start_index: int, open_char: str = "{", close_char: str = "}") -> Tuple[int, int]:
    depth = 0
    in_str: Optional[str] = None
    esc = False
    start = -1
    for i in range(start_index, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch == open_char:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0 and start != -1:
                return start, i + 1
    raise ValueError("Не удалось найти сбалансированный блок.")


def split_top_level_object_items(obj_text: str) -> List[Tuple[str, str]]:
    s = obj_text.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    items: List[Tuple[str, str]] = []
    depth_curly = depth_square = depth_round = 0
    in_str: Optional[str] = None
    esc = False
    part_start = 0
    colon_pos: Optional[int] = None

    def add_part(end: int) -> None:
        nonlocal part_start, colon_pos
        raw_part = s[part_start:end].rstrip(",")
        if raw_part.strip() and colon_pos is not None:
            rel_colon = colon_pos - part_start
            key = raw_part[:rel_colon].strip().strip("'\"")
            val = raw_part[rel_colon + 1 :].strip()
            items.append((key, val))
        part_start = end + 1
        colon_pos = None

    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            continue
        if ch == "{":
            depth_curly += 1
        elif ch == "}":
            depth_curly -= 1
        elif ch == "[":
            depth_square += 1
        elif ch == "]":
            depth_square -= 1
        elif ch == "(":
            depth_round += 1
        elif ch == ")":
            depth_round -= 1
        elif ch == ":" and depth_curly == depth_square == depth_round == 0 and colon_pos is None:
            colon_pos = i
        elif ch == "," and depth_curly == depth_square == depth_round == 0:
            add_part(i)
    add_part(len(s))
    return items


def extract_property(obj_text: str, name: str) -> Optional[str]:
    m = re.search(r"(?<![\w$])" + re.escape(name) + r"\s*:\s*", obj_text)
    if not m:
        return None
    idx = m.end()
    rest = obj_text[idx:].lstrip()
    if not rest:
        return None
    if rest[0] in ("'", '"'):
        quote = rest[0]
        esc = False
        for j in range(1, len(rest)):
            if esc:
                esc = False
            elif rest[j] == "\\":
                esc = True
            elif rest[j] == quote:
                return rest[: j + 1]
        return rest
    if rest[0] == "{":
        st, en = find_balanced(rest, 0)
        return rest[st:en]
    if rest[0] == "[":
        st, en = find_balanced(rest, 0, "[", "]")
        return rest[st:en]
    m2 = re.match(r"[^,}\n]+", rest)
    return m2.group(0).strip() if m2 else None


def parse_bool(raw: Optional[str]) -> bool:
    return str(raw).strip().lower() == "true"


def parse_int(raw: Optional[str], default: int = 0) -> int:
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def parse_filters_from_html(page_html: str) -> Tuple[List[FilterDimension], Dict[str, Any]]:
    filters_idx = page_html.find("filters:")
    if filters_idx == -1:
        raise ValueError("На странице не найден блок filters:. Возможно, структура Fedstat изменилась или страница не загрузилась полностью.")
    brace_start = page_html.find("{", filters_idx)
    if brace_start == -1:
        raise ValueError("Найден filters:, но не найдено начало объекта фильтров.")
    filters_start, filters_end = find_balanced(page_html, brace_start)
    filters_obj = page_html[filters_start:filters_end]

    metadata: Dict[str, Any] = {}
    id_raw = extract_property(page_html[max(0, filters_idx - 2000): filters_idx + 200], "id")
    title_raw = extract_property(page_html[max(0, filters_idx - 2000): filters_idx + 2000], "title")
    unit_raw = extract_property(page_html[max(0, filters_idx - 2000): filters_idx + 2000], "unit")
    if id_raw:
        metadata["indicator_id"] = re.sub(r"\D+", "", id_raw) or id_raw
    if title_raw:
        metadata["title"] = decode_js_string(title_raw)
    if unit_raw:
        metadata["unit"] = decode_js_string(unit_raw)

    dimensions: List[FilterDimension] = []
    for key, dim_text in split_top_level_object_items(filters_obj):
        if not dim_text.strip().startswith("{"):
            continue
        title = decode_js_string(extract_property(dim_text, "title") or "''")
        all_flag = parse_bool(extract_property(dim_text, "all"))
        indicator = parse_bool(extract_property(dim_text, "indicator"))
        values_text = extract_property(dim_text, "values")
        values: List[FilterValue] = []
        if values_text and values_text.strip().startswith("{"):
            for val_id, val_text in split_top_level_object_items(values_text):
                if not val_text.strip().startswith("{"):
                    continue
                val_title = decode_js_string(extract_property(val_text, "title") or "''")
                order = parse_int(extract_property(val_text, "order"), 0)
                checked = parse_bool(extract_property(val_text, "checked"))
                values.append(FilterValue(str(val_id), val_title, order, checked))
        values.sort(key=lambda v: (v.order, v.title))
        dimensions.append(FilterDimension(str(key), title, values, all_flag, indicator))

    if not dimensions:
        raise ValueError("Блок filters найден, но значения фильтров не распознаны.")

    known_rows = {"57831", "58273"}
    known_cols = {"3", "33560", "57937"}
    known_filters = {"0", "30611"}
    for dim in dimensions:
        if dim.object_id in known_rows:
            dim.placement = "row"
        elif dim.object_id in known_cols:
            dim.placement = "column"
        elif dim.object_id in known_filters or dim.indicator:
            dim.placement = "filter"
        else:
            dim.placement = "filter" if dim.selected_values() else "ignore"
    return dimensions, metadata


class RunLogger:
    def __init__(self, log_path: Path, ui_callback=None):
        self.log_path = log_path
        self.ui_callback = ui_callback
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        line = f"[{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.ui_callback:
            self.ui_callback(line)




# -----------------------------------------------------------------------------
# Performance diagnostics for map drawing.
# -----------------------------------------------------------------------------
_CURRENT_PERF_LOGGER = None


class PerfSection:
    def __init__(self, logger, name: str):
        self.logger = logger
        self.name = name
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        if self.logger:
            self.logger.event(f"START {self.name}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.logger:
            elapsed = time.perf_counter() - self.started
            suffix = "" if exc_type is None else f"; ERROR={exc_type.__name__}: {exc}"
            self.logger.event(f"END {self.name}; elapsed={elapsed:.3f}s" + suffix)
        return False


class PerfLogger:
    def __init__(self, name: str, details: Optional[Dict[str, Any]] = None):
        self.name = re.sub(r"[^A-Za-z0-9_\-]+", "_", name)[:80] or "map"
        self.details = details or {}
        self.started = time.perf_counter()
        self.created_at = _dt.datetime.now()
        self.events: List[str] = []
        self.event("PERF LOG START")
        if self.details:
            self.event("DETAILS " + json.dumps(self.details, ensure_ascii=False, sort_keys=True))

    def event(self, message: str) -> None:
        elapsed = time.perf_counter() - self.started
        self.events.append(f"+{elapsed:9.3f}s | {message}")

    def section(self, name: str) -> PerfSection:
        return PerfSection(self, name)

    def save(self) -> Path:
        self.event("PERF LOG END")
        PERFORMANCE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = PERFORMANCE_LOG_DIR / f"map_perf_{self.created_at.strftime('%Y%m%d_%H%M%S')}_{self.name}.txt"
        lines = [
            f"Application: {APP_NAME}",
            f"Version: {APP_VERSION}",
            f"Created: {self.created_at.isoformat(timespec='seconds')}",
            f"Name: {self.name}",
            "",
        ]
        lines.extend(self.events)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def perf_event(message: str) -> None:
    global _CURRENT_PERF_LOGGER
    if _CURRENT_PERF_LOGGER is not None:
        _CURRENT_PERF_LOGGER.event(message)


def perf_section(name: str) -> PerfSection:
    global _CURRENT_PERF_LOGGER
    return PerfSection(_CURRENT_PERF_LOGGER, name)


class FedstatClient:
    def __init__(self, timeout: int = 300, user_agent: str = DEFAULT_USER_AGENT):
        if requests is None:
            raise RuntimeError("Не установлен пакет requests. Выполните: pip install -r requirements.txt")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Language": "ru,en;q=0.9",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate, br",
        })

    def load_indicator_page(self, url: str, timeout: Optional[int] = None) -> requests.Response:
        return self.session.get(url, timeout=timeout or self.timeout)

    def download_table(
        self,
        base_url: str,
        payload: List[Tuple[str, str]],
        fmt: str,
        referer: str,
        logger: RunLogger,
    ) -> requests.Response:
        endpoint = urllib.parse.urljoin(base_url, f"/indicator/data.do?format={urllib.parse.quote(fmt)}")
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url.rstrip("/"),
            "Referer": referer,
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }
        logger.log(f"POST: {endpoint}")
        logger.log(f"Количество параметров формы: {len(payload)}")
        return self.session.post(endpoint, data=payload, headers=headers, timeout=self.timeout, allow_redirects=True)


def ordered_dimensions(dimensions: List[FilterDimension], placement: str) -> List[FilterDimension]:
    order_maps = {
        "row": {"57831": 0, "58273": 1},
        "column": {"3": 0, "33560": 1, "57937": 2},
        "filter": {"0": 0, "30611": 1},
    }
    rank = order_maps.get(placement, {})
    indexed = [(i, d) for i, d in enumerate(dimensions) if d.placement == placement]
    indexed.sort(key=lambda item: (rank.get(item[1].object_id, 1000 + item[0]), item[0]))
    return [d for _, d in indexed]


def build_payload(indicator_id: str, title: str, dimensions: List[FilterDimension]) -> List[Tuple[str, str]]:
    payload: List[Tuple[str, str]] = []
    payload.append(("title", title or f"Fedstat indicator {indicator_id}"))
    payload.append(("id", indicator_id))
    for dim in ordered_dimensions(dimensions, "row"):
        payload.append(("lineObjectIds", dim.object_id))
    for dim in ordered_dimensions(dimensions, "column"):
        payload.append(("columnObjectIds", dim.object_id))
    for dim in ordered_dimensions(dimensions, "row") + ordered_dimensions(dimensions, "column") + ordered_dimensions(dimensions, "filter"):
        for val in dim.selected_values():
            payload.append(("selectedFilterIds", f"{dim.object_id}_{val.value_id}"))
    for dim in ordered_dimensions(dimensions, "filter"):
        payload.append(("filterObjectIds", dim.object_id))
    return payload


def form_payload_to_text(payload: List[Tuple[str, str]]) -> str:
    return urllib.parse.urlencode(payload, doseq=True)


def save_request_debug(run_dir: Path, endpoint: str, payload: List[Tuple[str, str]], referer: str) -> None:
    body = form_payload_to_text(payload)
    (run_dir / "request_body_form_urlencoded.txt").write_text(body, encoding="utf-8")
    curl_text = (
        f'curl "{endpoint}" ^\n'
        f'  -H "Content-Type: application/x-www-form-urlencoded" ^\n'
        f'  -H "Referer: {referer}" ^\n'
        f'  --data-raw "{body}"\n'
    )
    (run_dir / "request_equivalent_curl_without_cookies.txt").write_text(curl_text, encoding="utf-8")


def save_response(response: Any, run_dir: Path, dataset_name: str, logger: RunLogger) -> DownloadResult:
    content = response.content or b""
    content_type = response.headers.get("Content-Type", "")
    final_url = getattr(response, "url", "")
    ext, ok, msg = detect_file_type(content, content_type, final_url)
    base = safe_name(dataset_name or "fedstat_result") + "_" + now_stamp()
    file_path = run_dir / f"{base}.{ext}"
    with file_path.open("wb") as f:
        f.write(content)
    info = {
        "requested_url": getattr(response.request, "url", ""),
        "final_url": final_url,
        "status_code": response.status_code,
        "content_type": content_type,
        "size_bytes": len(content),
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "response_headers": dict(response.headers),
        "is_statistics_file": ok,
        "message": msg,
    }
    info_path = run_dir / f"{base}_response_info.json"
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    preview_path: Optional[Path] = None
    if ext in ("html", "xml", "json", "csv", "bin"):
        preview_path = run_dir / f"{base}_preview.txt"
        try:
            text = response.text
        except Exception:
            text = content[:5000].decode("utf-8", errors="replace")
        preview_path.write_text(text[:50000], encoding="utf-8", errors="replace")
    logger.log(f"Ответ сохранен: {file_path}")
    logger.log(f"Информация об ответе: {info_path}")
    if preview_path:
        logger.log(f"Текстовый просмотр ответа: {preview_path}")
    logger.log(msg)
    return DownloadResult(
        str(file_path),
        str(info_path),
        str(preview_path) if preview_path else None,
        msg,
        ok,
        content_type,
        response.status_code,
        final_url,
    )


def zip_run_dir(run_dir: Path) -> Path:
    zip_path = run_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in run_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(run_dir.parent))
    return zip_path


def open_path(path: Path) -> None:
    path = Path(path)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')


def read_table_any(path: Path, max_rows: int = 200) -> Any:
    if pd is None:
        raise RuntimeError("Не установлен pandas. Выполните: pip install -r requirements.txt")
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, header=None, nrows=max_rows)
    if ext == ".csv":
        try:
            return pd.read_csv(path, nrows=max_rows)
        except Exception:
            return pd.read_csv(path, sep=";", nrows=max_rows)
    if ext in (".html", ".htm"):
        tables = pd.read_html(path)
        if not tables:
            raise RuntimeError("В HTML не найдено таблиц.")
        return tables[0].head(max_rows)
    if ext in (".xml", ".sdmx"):
        return pd.DataFrame({"Файл": [path.name], "Примечание": ["XML/SDMX просмотр в таблице пока не разобран. Откройте файл как текст или используйте конвертер."]})
    return pd.DataFrame({"Файл": [path.name], "Примечание": ["Неподдерживаемый тип файла для табличного просмотра."]})


def normalize_region_name(text: str) -> Optional[str]:
    s = str(text).strip()
    if not s:
        return None
    s_lower = s.lower()
    for region in REGION_COORDS.keys():
        if region.lower() == s_lower:
            return region
    # Search as substring, preferring longer names.
    for region in sorted(REGION_COORDS.keys(), key=len, reverse=True):
        if region.lower() in s_lower:
            return region
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(value) if isinstance(value, float) else False:
            return None
        return float(value)
    s = str(value).strip().replace(" ", "").replace("\xa0", "")
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def extract_region_values_from_table(path: Path, date_query: str = "", value_query: str = "") -> List[Tuple[str, float]]:
    """Extract one numeric value per region from Fedstat-like wide tables.

    N_101: the parser now understands the common Fedstat layout where the
    first column is the region, the second column is the commodity/service
    group, and the period/metric are stored in multi-row column headers.
    The previous version found values, but could take the last repeated row for
    the same region and the WebView did not color regions by these values.
    """
    if pd is None:
        raise RuntimeError("Не установлен pandas.")
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=None)
    elif ext == ".csv":
        try:
            df = pd.read_csv(path, header=None)
        except Exception:
            df = pd.read_csv(path, sep=";", header=None)
    elif ext in (".html", ".htm"):
        tables = pd.read_html(path)
        if not tables:
            return []
        df = tables[0]
    else:
        return []

    dq = date_query.strip().lower()
    vq = value_query.strip().lower()
    default_row_key = "все товары"
    header_rows = min(12, len(df.index))
    col_context: Dict[int, str] = {}
    for col in range(df.shape[1]):
        parts = []
        for r in range(header_rows):
            val = df.iat[r, col]
            if pd.notna(val):
                parts.append(str(val))
        col_context[col] = " | ".join(parts).lower()

    def query_tokens(text: str) -> List[str]:
        return [t for t in re.split(r"[^0-9a-zа-яё]+", text.lower()) if t]

    dq_tokens = query_tokens(dq)
    vq_tokens = query_tokens(vq)

    values_by_region: Dict[str, Tuple[float, int]] = {}
    for r in range(df.shape[0]):
        row_values = list(df.iloc[r].values)
        region = None
        for cell in row_values[: min(6, len(row_values))]:
            if pd.notna(cell):
                found = normalize_region_name(str(cell))
                if found:
                    region = found
                    break
        if not region:
            continue

        row_context_parts = []
        for cell in row_values[: min(8, len(row_values))]:
            if pd.notna(cell):
                row_context_parts.append(str(cell))
        row_context = " | ".join(row_context_parts).lower()

        row_score = 0
        if vq_tokens and all(t in row_context for t in vq_tokens):
            row_score += 30
        elif not vq_tokens and default_row_key in row_context:
            row_score += 20
        elif vq_tokens and any(t in row_context for t in vq_tokens):
            row_score += 8
        elif not vq_tokens:
            row_score += 0
        else:
            row_score -= 20

        candidates: List[Tuple[int, float, int]] = []
        for c, cell in enumerate(row_values):
            num = to_float(cell)
            if num is None:
                continue
            ctx = col_context.get(c, "")
            score = row_score
            if dq_tokens:
                matched = sum(1 for t in dq_tokens if t in ctx)
                score += matched * 12
                if matched == 0:
                    score -= 18
            else:
                # Without a requested period, prefer the rightmost available
                # numeric column. This usually corresponds to the latest period
                # in Fedstat wide tables.
                score += min(c, 1000)
            if vq_tokens:
                matched_header = sum(1 for t in vq_tokens if t in ctx)
                score += matched_header * 6
            candidates.append((score, num, c))
        if not candidates:
            continue
        candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
        best_score, best_value, best_col = candidates[0]
        old = values_by_region.get(region)
        if old is None or best_score > old[1]:
            values_by_region[region] = (best_value, best_score)

    return sorted([(region, value_score[0]) for region, value_score in values_by_region.items()], key=lambda x: x[0])



def map_regions_for_drawing(europe_only: bool = False) -> Dict[str, Tuple[float, float, str, str]]:
    """Return subject centers used as the built-in cartographic layer.

    This is an analytical visualization layer. It intentionally avoids official
    boundary claims and uses administrative-center coordinates from the embedded
    dictionary. The visual rules follow the agreed infographic style: blue map,
    red district contours, white city dots, no visible labels.
    """
    result: Dict[str, Tuple[float, float, str, str]] = {}
    for region, item in REGION_COORDS.items():
        lat, lon, fd, city = item
        if region == "Российская Федерация" or "федеральный округ" in region.lower():
            continue
        if europe_only and lon > 65:
            continue
        result[region] = item
    return result


def convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Monotonic-chain convex hull for small point sets."""
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for pt in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], pt) <= 0:
            lower.pop()
        lower.append(pt)
    upper: List[Tuple[float, float]] = []
    for pt in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], pt) <= 0:
            upper.pop()
        upper.append(pt)
    return lower[:-1] + upper[:-1]


def point_in_poly(x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def fd_hulls(europe_only: bool = False) -> Dict[str, List[Tuple[float, float]]]:
    groups: Dict[str, List[Tuple[float, float]]] = {}
    for _, (lat, lon, fd, _) in map_regions_for_drawing(europe_only).items():
        if fd == "РФ":
            continue
        groups.setdefault(fd, []).append((lon, lat))
    hulls: Dict[str, List[Tuple[float, float]]] = {}
    for fd, pts in groups.items():
        if len(pts) == 1:
            x, y = pts[0]
            hulls[fd] = [(x - 0.8, y - 0.5), (x + 0.8, y - 0.5), (x + 0.8, y + 0.5), (x - 0.8, y + 0.5)]
        elif len(pts) == 2:
            (x1, y1), (x2, y2) = pts
            hulls[fd] = [(x1 - 0.8, y1 - 0.5), (x2 + 0.8, y2 - 0.5), (x2 + 0.8, y2 + 0.5), (x1 - 0.8, y1 + 0.5)]
        else:
            # Add a small outward buffer by using a centroid expansion. This gives
            # the stylized "map plate" visual rather than a thin point hull.
            h = convex_hull(pts)
            cx = sum(x for x, _ in h) / len(h)
            cy = sum(y for _, y in h) / len(h)
            expanded = []
            for x, y in h:
                expanded.append((cx + (x - cx) * 1.10, cy + (y - cy) * 1.12))
            hulls[fd] = expanded
    return hulls


def add_extruded_polygon(fig, polygon: List[Tuple[float, float]], name: str, top_z: float = 0.0, bottom_z: float = -0.55) -> None:
    """Add a blue extruded district plate."""
    if not polygon or go is None:
        return
    cx = sum(x for x, _ in polygon) / len(polygon)
    cy = sum(y for _, y in polygon) / len(polygon)
    xs = [cx] + [p[0] for p in polygon]
    ys = [cy] + [p[1] for p in polygon]
    zs = [top_z] * len(xs)
    i = []
    j = []
    k = []
    n = len(polygon)
    for idx in range(n):
        i.append(0)
        j.append(idx + 1)
        k.append(((idx + 1) % n) + 1)
    fig.add_trace(go.Mesh3d(
        x=xs,
        y=ys,
        z=zs,
        i=i,
        j=j,
        k=k,
        name=name,
        color="rgba(28, 109, 205, 0.88)",
        opacity=0.88,
        hoverinfo="name",
        showscale=False,
        showlegend=False,
    ))
    # Side walls: use one mesh with quads split into triangles.
    x2: List[float] = []
    y2: List[float] = []
    z2: List[float] = []
    for x, y in polygon:
        x2.extend([x, x])
        y2.extend([y, y])
        z2.extend([top_z, bottom_z])
    ii: List[int] = []
    jj: List[int] = []
    kk: List[int] = []
    for idx in range(n):
        a = 2 * idx
        b = 2 * ((idx + 1) % n)
        # top_i, bottom_i, top_next, bottom_next
        ii.extend([a, a + 1])
        jj.extend([b, b])
        kk.extend([a + 1, b + 1])
    fig.add_trace(go.Mesh3d(
        x=x2,
        y=y2,
        z=z2,
        i=ii,
        j=jj,
        k=kk,
        color="rgba(16, 73, 145, 0.65)",
        opacity=0.65,
        hoverinfo="skip",
        showscale=False,
        showlegend=False,
    ))


def add_agreed_base_layer(fig, europe_only: bool = False) -> Dict[str, List[Tuple[float, float]]]:
    """Draw the agreed visual style: blue 3D map plate, red contours, white city dots."""
    hulls = fd_hulls(europe_only)
    for fd, poly in hulls.items():
        add_extruded_polygon(fig, poly, FD_NAMES.get(fd, fd))
        xs = [x for x, _ in poly] + [poly[0][0]]
        ys = [y for _, y in poly] + [poly[0][1]]
        zs = [0.06] * len(xs)
        fig.add_trace(go.Scatter3d(
            x=xs,
            y=ys,
            z=zs,
            mode="lines",
            name=FD_NAMES.get(fd, fd),
            line=dict(color="rgba(220, 42, 42, 1.0)", width=5),
            hoverinfo="name",
            showlegend=False,
        ))
    # White city dots only, no visible text labels. Hover remains useful for checking.
    regs = map_regions_for_drawing(europe_only)
    fig.add_trace(go.Scatter3d(
        x=[lon for _, (lat, lon, _, _) in regs.items()],
        y=[lat for _, (lat, lon, _, _) in regs.items()],
        z=[0.18 for _ in regs],
        mode="markers",
        text=[f"{region}<br>{city}<br>{FD_NAMES.get(fd, fd)}" for region, (lat, lon, fd, city) in regs.items()],
        hoverinfo="text",
        name="Города",
        marker=dict(size=4, color="white", line=dict(color="rgba(50,50,50,0.65)", width=1)),
        showlegend=False,
    ))
    return hulls


def region_in_drawn_area(lon: float, lat: float, hulls: Dict[str, List[Tuple[float, float]]]) -> bool:
    return any(point_in_poly(lon, lat, poly) for poly in hulls.values())



# -----------------------------------------------------------------------------
# Built-in and replaceable GIS layer for Matplotlib Canvas maps.
#
# The map base is no longer built from a hand-made Russia silhouette. The program
# reads a GeoJSON geometry layer. The bundled layer is a real low-detail Natural
# Earth country outline of Russia; the menu "Геооснова" can replace it with a
# more detailed GeoJSON, for example subject-level boundaries from geoBoundaries.
# Region heights are anchored to an embedded reference table of administrative
# centers. Federal-district red lines are an analytical grouping overlay unless a
# custom district boundary layer is supplied in future versions.
# -----------------------------------------------------------------------------

GEO_DEFAULT_SOURCE = "builtin"
GEODOWNLOAD_DEFAULT_API = "https://www.geoboundaries.org/api/current/gbOpen/RUS/ADM1/"


def read_json_file(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_geo_settings() -> Dict[str, Any]:
    if GEO_SETTINGS_PATH.exists():
        try:
            data = read_json_file(GEO_SETTINGS_PATH)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"source": GEO_DEFAULT_SOURCE, "geojson_path": str(BUILTIN_RUSSIA_GEOJSON_PATH), "region_reference_path": str(BUILTIN_REGION_REFERENCE_PATH)}


def set_geo_settings(geojson_path: Optional[str] = None, region_reference_path: Optional[str] = None, source: str = "custom") -> None:
    current = get_geo_settings()
    if geojson_path:
        current["geojson_path"] = geojson_path
    if region_reference_path:
        current["region_reference_path"] = region_reference_path
    current["source"] = source
    write_json_file(GEO_SETTINGS_PATH, current)


def reset_geo_settings_to_builtin() -> None:
    write_json_file(GEO_SETTINGS_PATH, {"source": GEO_DEFAULT_SOURCE, "geojson_path": str(BUILTIN_RUSSIA_GEOJSON_PATH), "region_reference_path": str(BUILTIN_REGION_REFERENCE_PATH)})


def get_active_geojson_path() -> Path:
    settings = get_geo_settings()
    path = Path(settings.get("geojson_path") or BUILTIN_RUSSIA_GEOJSON_PATH)
    if not path.exists():
        return BUILTIN_RUSSIA_GEOJSON_PATH
    return path


def get_active_region_reference_path() -> Path:
    settings = get_geo_settings()
    path = Path(settings.get("region_reference_path") or BUILTIN_REGION_REFERENCE_PATH)
    if not path.exists():
        return BUILTIN_REGION_REFERENCE_PATH
    return path


def load_region_reference() -> Dict[str, Tuple[float, float, str, str]]:
    """Load region anchor points: region -> (lat, lon, federal_district, city)."""
    path = get_active_region_reference_path()
    result: Dict[str, Tuple[float, float, str, str]] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("fedstat_name") or row.get("region") or row.get("name") or "").strip()
                    if not name:
                        continue
                    lat_s = row.get("capital_lat") or row.get("lat") or row.get("latitude") or ""
                    lon_s = row.get("capital_lon") or row.get("lon") or row.get("longitude") or ""
                    try:
                        lat = float(str(lat_s).replace(",", "."))
                        lon = float(str(lon_s).replace(",", "."))
                    except Exception:
                        continue
                    fd = (row.get("federal_district") or row.get("fd") or "").strip() or "РФ"
                    city = (row.get("capital_city") or row.get("city") or "").strip() or name
                    result[name] = (lat, lon, fd, city)
        except Exception:
            result = {}
    # Fallback and alias enrichment from embedded dictionary.
    for k, v in REGION_COORDS.items():
        result.setdefault(k, v)
    return result


def map_regions_for_drawing(europe_only: bool = False) -> Dict[str, Tuple[float, float, str, str]]:
    result: Dict[str, Tuple[float, float, str, str]] = {}
    for region, item in load_region_reference().items():
        lat, lon, fd, city = item
        if region == "Российская Федерация" or "федеральный округ" in region.lower():
            continue
        if europe_only and lon > 65:
            continue
        result[region] = item
    return result


def normalize_russia_lon(lon: float) -> float:
    # Keep the Russian Far East continuous with European Russia for projection.
    # Natural Earth uses negative longitudes near the antimeridian; convert them
    # to 180..360 domain, then filter out accidental non-Russian wrap artifacts.
    if lon < 0:
        return lon + 360.0
    return lon


def albers_russia_project(lon: float, lat: float) -> Tuple[float, float]:
    """Albers equal-area style projection for Russia analytical maps."""
    lon = normalize_russia_lon(lon)
    phi = math.radians(lat)
    lam = math.radians(lon)
    phi1 = math.radians(50.0)
    phi2 = math.radians(70.0)
    phi0 = math.radians(52.0)
    lam0 = math.radians(95.0)
    n = 0.5 * (math.sin(phi1) + math.sin(phi2))
    C = math.cos(phi1) ** 2 + 2 * n * math.sin(phi1)
    rho = math.sqrt(max(0.0, C - 2 * n * math.sin(phi))) / n
    rho0 = math.sqrt(max(0.0, C - 2 * n * math.sin(phi0))) / n
    theta = n * (lam - lam0)
    x = rho * math.sin(theta) * 74.0
    y = (rho0 - rho * math.cos(theta)) * 74.0
    return x, y


def project_lonlat(lon: float, lat: float) -> Tuple[float, float]:
    return albers_russia_project(lon, lat)


# N_96: region-boundary line cache.
# The active ADM1 GeoJSON can contain millions of vertices. The map window
# stores sampled *rings* in a cache, draws those rings as connected red lines,
# and uses the same rings for blue map fill. This keeps the blue map and red
# regional borders in one coordinate source instead of mixing the built-in
# country outline with another regional layer.
_COUNTRY_OUTLINE_CACHE: Dict[Tuple[str, float, bool], List[List[Tuple[float, float]]]] = {}
_REGION_BORDER_LINE_CACHE: Dict[Tuple[str, float, bool, int], Tuple[List[List[Tuple[float, float]]], int, int]] = {}
# N_97: independent blue-base cache. The blue map base is built from the
# full active regional geometry and does not depend on the red-border draw step.
# Red regional borders are sampled separately and only overlaid on top.
_REGION_BLUE_BASE_CACHE: Dict[Tuple[str, float, bool], Tuple[List[List[Tuple[float, float]]], int, Tuple[float, float, float, float]]] = {}


def _iter_geometry_outer_rings(geometry: Dict[str, Any]):
    if not geometry:
        return
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if gtype == "Polygon":
        poly_list = [coords]
    elif gtype == "MultiPolygon":
        poly_list = coords
    else:
        return
    for poly in poly_list:
        if not poly:
            continue
        outer = poly[0]
        if outer:
            yield outer


def _ring_to_lonlat_points(outer: Any) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    for item in outer:
        if not item or len(item) < 2:
            continue
        lon = normalize_russia_lon(float(item[0]))
        lat = float(item[1])
        if 15.0 <= lon <= 205.0 and 35.0 <= lat <= 82.5:
            points.append((lon, lat))
    return points


def _read_geojson_features_from_data(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        return [f for f in data["features"] if isinstance(f, dict)]
    if isinstance(data, dict) and data.get("type") in {"Polygon", "MultiPolygon"}:
        return [{"type": "Feature", "properties": {"name": "Россия"}, "geometry": data}]
    return []


def _read_geojson_features(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = read_json_file(path)
    except Exception:
        return []
    return _read_geojson_features_from_data(data)


def load_country_outline_lonlat_polygons(europe_only: bool = False) -> List[List[Tuple[float, float]]]:
    path = APP_DIR / "data" / "geo" / "russia_country_outline.geojson"
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    key = (str(path), mtime, bool(europe_only))
    if key in _COUNTRY_OUTLINE_CACHE:
        return _COUNTRY_OUTLINE_CACHE[key]
    result: List[List[Tuple[float, float]]] = []
    for feature in _read_geojson_features(path):
        for outer in _iter_geometry_outer_rings(feature.get("geometry") or {}):
            pts = _ring_to_lonlat_points(outer)
            if len(pts) < 3:
                continue
            if europe_only:
                cx = sum(lon for lon, lat in pts) / len(pts)
                if cx > 75:
                    continue
            result.append(pts)
    _COUNTRY_OUTLINE_CACHE.clear()
    _COUNTRY_OUTLINE_CACHE[key] = result
    return result


def projected_country_outline_polygons(europe_only: bool = False) -> List[List[Tuple[float, float]]]:
    projected: List[List[Tuple[float, float]]] = []
    for poly in load_country_outline_lonlat_polygons(europe_only):
        pp = [project_lonlat(lon, lat) for lon, lat in poly]
        if len(pp) >= 3:
            projected.append(pp)
    return projected


def get_boundary_draw_step(value: Any) -> int:
    try:
        return max(1, min(10000, int(str(value).strip())))
    except Exception:
        return 10


def boundary_simplify_tolerance_from_step(step: int) -> float:
    """Convert UI step to geometric simplification tolerance in projected units.

    Step 1 means no simplification. Larger values mean a stronger Douglas-Peucker
    simplification for red boundary lines. This replaces the incorrect old logic
    of drawing every N-th point as a connected line.
    """
    step = get_boundary_draw_step(step)
    if step <= 1:
        return 0.0
    # Projection extent of Russia is about 90 x 50 units. These coefficients keep
    # step=10 close to detailed, step=50 medium, step=100+ preview-oriented.
    return min(3.0, max(0.002, step * 0.0025))


def _point_segment_distance_sq(p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    if t < 0.0:
        cx, cy = ax, ay
    elif t > 1.0:
        cx, cy = bx, by
    else:
        cx, cy = ax + t * dx, ay + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2


def douglas_peucker_line(points: List[Tuple[float, float]], tolerance: float) -> List[Tuple[float, float]]:
    """Simplify a projected polyline while preserving endpoints.

    This is used only for the red regional boundary overlay. It avoids the visual
    jumps produced by the former strategy: `points[::step]` connected as a line.
    """
    n = len(points)
    if n <= 2 or tolerance <= 0:
        return points[:]
    tol_sq = tolerance * tolerance
    keep = [False] * n
    keep[0] = True
    keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        a = points[start]
        b = points[end]
        max_dist = -1.0
        max_idx = None
        for idx in range(start + 1, end):
            d = _point_segment_distance_sq(points[idx], a, b)
            if d > max_dist:
                max_dist = d
                max_idx = idx
        if max_idx is not None and max_dist > tol_sq:
            keep[max_idx] = True
            stack.append((start, max_idx))
            stack.append((max_idx, end))
    return [pt for pt, flag in zip(points, keep) if flag]


def simplify_projected_ring_for_boundary(points: List[Tuple[float, float]], tolerance: float) -> List[Tuple[float, float]]:
    """Simplify one contour ring for red line drawing.

    Rings stay independent: no segment is ever drawn between different polygons,
    islands, or holes. The first and last vertex are preserved and the ring is
    closed again after simplification.
    """
    if len(points) < 2:
        return points[:]
    closed = points[0] == points[-1]
    body = points[:-1] if closed and len(points) > 2 else points[:]
    if len(body) <= 2 or tolerance <= 0:
        simplified = body
    else:
        simplified = douglas_peucker_line(body, tolerance)
    if len(simplified) >= 2 and simplified[-1] != simplified[0]:
        simplified = simplified + [simplified[0]]
    return simplified


def _boundary_cache_fingerprint(path: Path, europe_only: bool, step: int) -> Tuple[str, Dict[str, Any]]:
    try:
        st = path.stat()
        size = int(st.st_size)
        mtime_ns = int(st.st_mtime_ns)
    except Exception:
        size = 0
        mtime_ns = 0
    payload = {
        "version": "N_98_boundary_simplified_lines_v1",
        "path": str(path.resolve()) if path.exists() else str(path),
        "size": size,
        "mtime_ns": mtime_ns,
        "europe_only": bool(europe_only),
        "step": int(step),
        "projection": "albers_russia_v1",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:20], payload


def _boundary_cache_path(path: Path, europe_only: bool, step: int) -> Path:
    digest, _ = _boundary_cache_fingerprint(path, europe_only, step)
    return GEO_BOUNDARY_CACHE_DIR / f"region_boundary_points_{digest}.json"


def _read_text_file_with_progress(path: Path, progress_cb: Optional[Any] = None, start_pct: int = 5, end_pct: int = 35) -> str:
    size = path.stat().st_size if path.exists() else 0
    chunks: List[bytes] = []
    read_total = 0
    chunk_size = 1024 * 1024
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
            read_total += len(chunk)
            if progress_cb and size > 0:
                pct = start_pct + int((end_pct - start_pct) * min(read_total / size, 1.0))
                progress_cb(f"Первичное чтение GeoJSON: {read_total / (1024*1024):.1f} из {size / (1024*1024):.1f} МБ", pct)
    if progress_cb:
        progress_cb("GeoJSON прочитан. Разбираем JSON-структуру...", end_pct)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _load_boundary_cache(cache_path: Path, meta: Dict[str, Any]) -> Optional[Tuple[List[List[Tuple[float, float]]], int, int]]:
    if not cache_path.exists():
        return None
    try:
        data = read_json_file(cache_path)
        if data.get("meta") != meta:
            return None
        raw_lines = data.get("lines")
        if not isinstance(raw_lines, list):
            # Older point-only caches are intentionally ignored because N_96
            # needs connected rings for line drawing and map fill.
            return None
        lines: List[List[Tuple[float, float]]] = []
        for raw_line in raw_lines:
            if not isinstance(raw_line, list):
                continue
            line = []
            for item in raw_line:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    line.append((float(item[0]), float(item[1])))
            if len(line) >= 2:
                lines.append(line)
        displayed = int(data.get("displayed_point_count", sum(len(line) for line in lines)))
        return lines, int(data.get("source_point_count", 0)), displayed
    except Exception:
        return None


def prepare_projected_region_border_points_cache(
    europe_only: bool = False,
    draw_step: int = 10,
    progress_cb: Optional[Any] = None,
    log_fn: Optional[Any] = None,
) -> Tuple[List[List[Tuple[float, float]]], int, int]:
    """Prepare and load cached sampled boundary rings for ADM1 regional borders.

    N_96 keeps the sampled vertices grouped by contour ring. This allows the
    map to connect red boundary vertices with lines and use the same geometry
    as a blue map fill. The original GeoJSON is never modified.
    """
    with perf_section("boundary cache: resolve active geojson and step"):
        path = get_active_geojson_path()
        step = get_boundary_draw_step(draw_step)
        if not active_geojson_is_subject_level():
            return [], 0, 0
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    mem_key = (str(path), mtime, bool(europe_only), step)
    if mem_key in _REGION_BORDER_LINE_CACHE:
        return _REGION_BORDER_LINE_CACHE[mem_key]

    cache_path = _boundary_cache_path(path, europe_only, step)
    digest, meta = _boundary_cache_fingerprint(path, europe_only, step)
    with perf_section("boundary cache: load existing cache"):
        cached = _load_boundary_cache(cache_path, meta)
    if cached is not None:
        if log_fn:
            log_fn(f"Кэш красных линий границ найден: {cache_path}")
        perf_event(f"boundary line cache hit: {cache_path}; shown={cached[2]}; source={cached[1]}; lines={len(cached[0])}")
        _REGION_BORDER_LINE_CACHE.clear()
        _REGION_BORDER_LINE_CACHE[mem_key] = cached
        return cached

    GEO_BOUNDARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if progress_cb:
        progress_cb("Кэш красных линий границ не найден. Начинаем первичное чтение GeoJSON...", 3)
    if log_fn:
        log_fn(f"Кэш красных линий границ не найден. Исходный GeoJSON: {path}")
        try:
            log_fn(f"Размер GeoJSON: {path.stat().st_size / (1024*1024):.1f} МБ; уровень упрощения/шаг: {step}")
        except Exception:
            pass

    with perf_section("boundary cache: read source GeoJSON text"):
        text = _read_text_file_with_progress(path, progress_cb=progress_cb, start_pct=5, end_pct=35)
    with perf_section("boundary cache: json.loads full GeoJSON"):
        data = json.loads(text)
    del text
    with perf_section("boundary cache: get features"):
        features = _read_geojson_features_from_data(data)
    if progress_cb:
        progress_cb(f"JSON разобран. Обрабатываем регионы: 0 из {len(features)}", 45)

    projected_lines: List[List[Tuple[float, float]]] = []
    source_count = 0
    displayed_count = 0
    total_features = max(1, len(features))
    with perf_section("boundary cache: walk rings, project and simplify red lines"):
        for idx, feature in enumerate(features, start=1):
            for outer in _iter_geometry_outer_rings(feature.get("geometry") or {}):
                pts = _ring_to_lonlat_points(outer)
                if len(pts) < 3:
                    continue
                if europe_only:
                    cx = sum(lon for lon, lat in pts) / len(pts)
                    if cx > 75:
                        continue
                source_count += len(pts)
                tolerance = boundary_simplify_tolerance_from_step(step)
                projected_full: List[Tuple[float, float]] = []
                for lon, lat in pts:
                    x, y = project_lonlat(lon, lat)
                    projected_full.append((x, y))
                if step <= 1:
                    simplified_line = projected_full
                else:
                    simplified_line = simplify_projected_ring_for_boundary(projected_full, tolerance)
                line: List[Tuple[float, float]] = [(round(x, 6), round(y, 6)) for x, y in simplified_line]
                if len(line) >= 2:
                    projected_lines.append(line)
                    displayed_count += len(line)
            if progress_cb:
                pct = 45 + int(45 * idx / total_features)
                progress_cb(f"Обработка границ регионов: {idx} из {len(features)}; линий: {len(projected_lines)}; точек: {displayed_count}", pct)
    del data

    result = {
        "meta": meta,
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source_point_count": source_count,
        "displayed_point_count": displayed_count,
        "line_count": len(projected_lines),
        "lines": projected_lines,
    }
    if progress_cb:
        progress_cb("Сохраняем кэш красных линий границ...", 92)
    with perf_section("boundary cache: write sampled line cache JSON"):
        cache_path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if log_fn:
        log_fn(f"Кэш красных линий границ создан: {cache_path}")
        log_fn(f"Точек исходно: {source_count}; точек в кэше: {displayed_count}; линий: {len(projected_lines)}")

    prepared = (projected_lines, source_count, displayed_count)
    _REGION_BORDER_LINE_CACHE.clear()
    _REGION_BORDER_LINE_CACHE[mem_key] = prepared
    if progress_cb:
        progress_cb("Кэш линий границ готов.", 100)
    return prepared



def _base_cache_fingerprint(path: Path, europe_only: bool) -> Tuple[str, Dict[str, Any]]:
    try:
        st = path.stat()
        size = int(st.st_size)
        mtime_ns = int(st.st_mtime_ns)
    except Exception:
        size = 0
        mtime_ns = 0
    payload = {
        "version": "N_97_blue_base_full_geometry_v1",
        "path": str(path.resolve()) if path.exists() else str(path),
        "size": size,
        "mtime_ns": mtime_ns,
        "europe_only": bool(europe_only),
        "projection": "albers_russia_v1",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:20], payload


def _base_cache_path(path: Path, europe_only: bool) -> Path:
    digest, _ = _base_cache_fingerprint(path, europe_only)
    return GEO_BOUNDARY_CACHE_DIR / f"blue_country_base_full_{digest}.pkl"


def _load_blue_base_cache(cache_path: Path, meta: Dict[str, Any]) -> Optional[Tuple[List[List[Tuple[float, float]]], int, Tuple[float, float, float, float]]]:
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "rb") as f:
            data = pickle.load(f)
        if data.get("meta") != meta:
            return None
        raw_polys = data.get("polygons")
        bounds = data.get("bounds")
        if not isinstance(raw_polys, list) or not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            return None
        polygons: List[List[Tuple[float, float]]] = []
        for raw_poly in raw_polys:
            if not isinstance(raw_poly, list):
                continue
            poly: List[Tuple[float, float]] = []
            for item in raw_poly:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    poly.append((float(item[0]), float(item[1])))
            if len(poly) >= 3:
                polygons.append(poly)
        return polygons, int(data.get("source_point_count", 0)), (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    except Exception:
        return None


def prepare_projected_blue_base_cache(
    europe_only: bool = False,
    progress_cb: Optional[Any] = None,
    log_fn: Optional[Any] = None,
) -> Tuple[List[List[Tuple[float, float]]], int, Tuple[float, float, float, float]]:
    """Prepare a full blue map base independently from red border sampling.

    The base uses all vertices from the active ADM1 GeoJSON. It is cached once
    and reused. The red-border draw step never affects this blue base, so gaps
    cannot appear because of border sampling.
    """
    path = get_active_geojson_path()
    if not active_geojson_is_subject_level():
        polygons = projected_country_outline_polygons(europe_only)
        flat = _flatten_lines(polygons)
        if flat:
            bounds = (min(x for x, y in flat), max(x for x, y in flat), min(y for x, y in flat), max(y for x, y in flat))
        else:
            bounds = (0.0, 1.0, 0.0, 1.0)
        return polygons, sum(len(poly) for poly in polygons), bounds
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    mem_key = (str(path), mtime, bool(europe_only))
    if mem_key in _REGION_BLUE_BASE_CACHE:
        return _REGION_BLUE_BASE_CACHE[mem_key]
    cache_path = _base_cache_path(path, europe_only)
    digest, meta = _base_cache_fingerprint(path, europe_only)
    cached = _load_blue_base_cache(cache_path, meta)
    if cached is not None:
        if log_fn:
            log_fn(f"Кэш синей основы карты найден: {cache_path}")
        _REGION_BLUE_BASE_CACHE.clear()
        _REGION_BLUE_BASE_CACHE[mem_key] = cached
        return cached

    GEO_BOUNDARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if progress_cb:
        progress_cb("Кэш синей основы не найден. Читаем полный GeoJSON регионов...", 3)
    if log_fn:
        log_fn(f"Создаем кэш синей основы из полного GeoJSON: {path}")
    text = _read_text_file_with_progress(path, progress_cb=progress_cb, start_pct=5, end_pct=30)
    if progress_cb:
        progress_cb("Разбираем JSON для синей основы карты...", 32)
    data = json.loads(text)
    del text
    features = _read_geojson_features_from_data(data)
    polygons: List[List[Tuple[float, float]]] = []
    source_count = 0
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    total_features = max(1, len(features))
    for idx, feature in enumerate(features, start=1):
        for outer in _iter_geometry_outer_rings(feature.get("geometry") or {}):
            pts = _ring_to_lonlat_points(outer)
            if len(pts) < 3:
                continue
            if europe_only:
                cx = sum(lon for lon, lat in pts) / len(pts)
                if cx > 75:
                    continue
            source_count += len(pts)
            poly: List[Tuple[float, float]] = []
            for lon, lat in pts:
                x, y = project_lonlat(lon, lat)
                # Keep all vertices for the blue base, but store rounded floats
                # to reduce cache size and speed up later reads.
                x = round(x, 6); y = round(y, 6)
                poly.append((x, y))
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y
            if len(poly) >= 3:
                polygons.append(poly)
        if progress_cb:
            pct = 35 + int(55 * idx / total_features)
            progress_cb(f"Готовим синюю основу: {idx} из {len(features)}; полигонов: {len(polygons)}; точек: {source_count}", pct)
    del data
    if not polygons or not math.isfinite(min_x):
        polygons = projected_country_outline_polygons(europe_only)
        flat = _flatten_lines(polygons)
        if flat:
            bounds = (min(x for x, y in flat), max(x for x, y in flat), min(y for x, y in flat), max(y for x, y in flat))
        else:
            bounds = (0.0, 1.0, 0.0, 1.0)
    else:
        bounds = (min_x, max_x, min_y, max_y)
    result = {
        "meta": meta,
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source_point_count": source_count,
        "polygon_count": len(polygons),
        "bounds": bounds,
        "polygons": polygons,
    }
    if progress_cb:
        progress_cb("Сохраняем кэш синей основы карты...", 92)
    with open(cache_path, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    if log_fn:
        log_fn(f"Кэш синей основы создан: {cache_path}")
        log_fn(f"Синяя основа: полигонов {len(polygons)}, точек {source_count}")
    prepared = (polygons, source_count, bounds)
    _REGION_BLUE_BASE_CACHE.clear()
    _REGION_BLUE_BASE_CACHE[mem_key] = prepared
    if progress_cb:
        progress_cb("Кэш синей основы готов.", 100)
    return prepared


def projected_blue_base_polygons(europe_only: bool = False) -> Tuple[List[List[Tuple[float, float]]], int, Tuple[float, float, float, float]]:
    return prepare_projected_blue_base_cache(europe_only=europe_only)


def _add_blue_base_polygons(ax, polygons: List[List[Tuple[float, float]]], alpha: float = 0.74) -> None:
    if not polygons or Poly3DCollection is None:
        return
    faces = []
    for poly in polygons:
        if len(poly) >= 3:
            faces.append([(x, y, 0.0) for x, y in poly])
    if not faces:
        return
    coll = Poly3DCollection(
        faces,
        facecolor=(0.10, 0.53, 0.86, alpha),
        edgecolor=(0.04, 0.22, 0.42, 0.03),
        linewidths=0.01,
    )
    ax.add_collection3d(coll)


def projected_region_boundary_lines(europe_only: bool = False, draw_step: int = 10) -> Tuple[List[List[Tuple[float, float]]], int, int]:
    """Return sampled projected regional boundary rings from cache."""
    return prepare_projected_region_border_points_cache(europe_only=europe_only, draw_step=draw_step)


def projected_region_border_points(europe_only: bool = False, draw_step: int = 10) -> Tuple[List[Tuple[float, float]], int, int]:
    """Backward-compatible flat point list for older code paths."""
    lines, source_count, displayed_count = projected_region_boundary_lines(europe_only, draw_step)
    flat = [pt for line in lines for pt in line]
    return flat, source_count, displayed_count


def _flatten_lines(lines: List[List[Tuple[float, float]]]) -> List[Tuple[float, float]]:
    return [pt for line in lines for pt in line]


def _add_boundary_fill_from_lines(ax, lines: List[List[Tuple[float, float]]], alpha: float = 0.72) -> None:
    if not lines or Poly3DCollection is None:
        return
    faces = []
    for line in lines:
        if len(line) >= 3:
            faces.append([(x, y, 0.0) for x, y in line])
    if not faces:
        return
    poly = Poly3DCollection(
        faces,
        facecolor=(0.10, 0.53, 0.86, alpha),
        edgecolor=(0.05, 0.25, 0.45, 0.05),
        linewidths=0.02,
    )
    ax.add_collection3d(poly)


def _add_boundary_lines(ax, lines: List[List[Tuple[float, float]]], z: float = 0.13, color: str = "red", linewidth: float = 0.42) -> None:
    if not lines or Line3DCollection is None:
        return
    # Matplotlib 3D line collections are faster and more stable when each
    # segment has the same length. Build a collection of 2-point segments.
    segs = []
    for line in lines:
        if len(line) < 2:
            continue
        for idx in range(len(line) - 1):
            x1, y1 = line[idx]
            x2, y2 = line[idx + 1]
            segs.append([(x1, y1, z), (x2, y2, z)])
    if not segs:
        return
    coll = Line3DCollection(segs, colors=color, linewidths=linewidth, alpha=0.92)
    ax.add_collection3d(coll)


# N_92: performance-oriented boundary simplification.
# Detailed ADM1 GeoJSON files can contain tens or hundreds of thousands of
# coordinate vertices. Matplotlib 3D redraws those vertices very slowly,
# especially while processing mouse movement and zoom. The program now reduces
# each polygon before projection and drawing. The original downloaded GeoJSON is
# not modified; simplification is applied only to the drawing layer.
GEO_SIMPLIFY_TOLERANCE_DEG = 0.18
GEO_SIMPLIFY_MAX_POINTS_PER_POLYGON = 120
GEO_SIMPLIFY_MIN_POINTS_PER_POLYGON = 8


def _perpendicular_distance_2d(point: Tuple[float, float], start: Tuple[float, float], end: Tuple[float, float]) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _rdp_simplify(points: List[Tuple[float, float]], tolerance: float) -> List[Tuple[float, float]]:
    if len(points) <= 2:
        return points[:]
    start = points[0]
    end = points[-1]
    max_dist = -1.0
    max_idx = 0
    for idx in range(1, len(points) - 1):
        dist = _perpendicular_distance_2d(points[idx], start, end)
        if dist > max_dist:
            max_dist = dist
            max_idx = idx
    if max_dist > tolerance:
        left = _rdp_simplify(points[: max_idx + 1], tolerance)
        right = _rdp_simplify(points[max_idx:], tolerance)
        return left[:-1] + right
    return [start, end]


def simplify_lonlat_polygon(points: List[Tuple[float, float]], tolerance: float = GEO_SIMPLIFY_TOLERANCE_DEG, max_points: int = GEO_SIMPLIFY_MAX_POINTS_PER_POLYGON) -> List[Tuple[float, float]]:
    """Simplify one polygon ring for interactive drawing.

    The function preserves the first point and closes the ring implicitly in the
    drawing code. It intentionally keeps a bounded number of vertices per subject
    polygon to prevent slow mouse movement in the map window.
    """
    if len(points) <= max_points:
        return points
    closed = points[0] == points[-1]
    work = points[:-1] if closed else points[:]
    if len(work) <= max_points:
        return work
    simplified = _rdp_simplify(work + [work[0]], tolerance)[:-1]
    if len(simplified) < GEO_SIMPLIFY_MIN_POINTS_PER_POLYGON:
        # For very small shapes keep a coarse uniform sample instead of dropping
        # them to a triangle.
        step = max(1, len(work) // max(GEO_SIMPLIFY_MIN_POINTS_PER_POLYGON, 1))
        simplified = work[::step][:GEO_SIMPLIFY_MIN_POINTS_PER_POLYGON]
    if len(simplified) > max_points:
        step = max(1, math.ceil(len(simplified) / max_points))
        simplified = simplified[::step]
    if len(simplified) < 3:
        return work[:min(len(work), max_points)]
    return simplified


def geometry_to_lonlat_polygons(geometry: Dict[str, Any]) -> List[List[Tuple[float, float]]]:
    if not geometry:
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    polys: List[List[Tuple[float, float]]] = []
    if gtype == "Polygon":
        poly_list = [coords]
    elif gtype == "MultiPolygon":
        poly_list = coords
    else:
        return []
    for poly in poly_list:
        if not poly:
            continue
        outer = poly[0]
        points: List[Tuple[float, float]] = []
        for item in outer:
            if not item or len(item) < 2:
                continue
            lon = normalize_russia_lon(float(item[0]))
            lat = float(item[1])
            # Remove tiny wrap artifacts that sometimes appear in global outlines.
            if 15.0 <= lon <= 205.0 and 35.0 <= lat <= 82.5:
                points.append((lon, lat))
        if len(points) >= 3:
            points = simplify_lonlat_polygon(points)
            if len(points) >= 3:
                polys.append(points)
    return polys


def load_geojson_lonlat_polygons(europe_only: bool = False) -> List[List[Tuple[float, float]]]:
    path = get_active_geojson_path()
    if not path.exists():
        return []
    try:
        data = read_json_file(path)
    except Exception:
        return []
    features = data.get("features") if isinstance(data, dict) else None
    if not features and isinstance(data, dict) and data.get("type") in {"Polygon", "MultiPolygon"}:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    if not isinstance(features, list):
        return []
    result: List[List[Tuple[float, float]]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geom = feature.get("geometry") or {}
        for pts in geometry_to_lonlat_polygons(geom):
            if europe_only:
                cx = sum(lon for lon, lat in pts) / len(pts)
                if cx > 75:
                    continue
            result.append(pts)
    return result




def load_geojson_features_lonlat(europe_only: bool = False) -> List[Tuple[str, List[List[Tuple[float, float]]]]]:
    """Load GeoJSON as feature-level polygons.

    Returns [(feature_name, [polygon1, polygon2, ...])]. For ADM1 GeoJSON this is
    subject-level geometry; for the built-in country outline it is just one Russia
    outline feature. Keeping feature separation is important because red region
    borders are drawn from individual feature edges, not from a convex hull.
    """
    path = get_active_geojson_path()
    if not path.exists():
        return []
    try:
        data = read_json_file(path)
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        features = data["features"]
    elif isinstance(data, dict) and data.get("type") in {"Polygon", "MultiPolygon"}:
        features = [{"type": "Feature", "properties": {"name": "Россия"}, "geometry": data}]
    else:
        return []
    result: List[Tuple[str, List[List[Tuple[float, float]]]]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        name = (
            props.get("shapeName") or props.get("name") or props.get("NAME_1") or
            props.get("NAME") or props.get("region") or props.get("adm1_name") or "регион"
        )
        polys: List[List[Tuple[float, float]]] = []
        for pts in geometry_to_lonlat_polygons(feature.get("geometry") or {}):
            if europe_only:
                cx = sum(lon for lon, lat in pts) / len(pts)
                if cx > 75:
                    continue
            if len(pts) >= 3:
                polys.append(pts)
        if polys:
            result.append((str(name), polys))
    return result


_ACTIVE_GEOJSON_LEVEL_CACHE: Dict[Tuple[str, int, int, str], bool] = {}


def active_geojson_is_subject_level() -> bool:
    """Return True when the active GeoJSON appears to contain regional/ADM1 borders.

    N_95: this check must be cheap. Earlier versions parsed the full 50+ MB
    ADM1 GeoJSON during every map opening, which made the first draw slow even
    when a small boundary cache was already present. The common geoBoundaries
    ADM1 case is detected from settings/filename/size without parsing the file;
    JSON parsing is used only as a fallback for small or ambiguous files.
    """
    path = get_active_geojson_path()
    if not path.exists():
        return False
    try:
        if path.resolve() == BUILTIN_RUSSIA_GEOJSON_PATH.resolve():
            return False
    except Exception:
        pass
    settings = get_geo_settings()
    source = str(settings.get("source", "")).lower()
    filename = path.name.lower()
    if "adm1" in source or "geoboundaries" in source or "adm1" in filename or "geoboundaries" in filename:
        return True
    try:
        st = path.stat()
        # Detailed ADM1 files are large; country outlines bundled with the app are tiny.
        if st.st_size > 1024 * 1024:
            return True
        cache_key = (str(path.resolve()), int(st.st_size), int(st.st_mtime_ns), source)
    except Exception:
        cache_key = (str(path), 0, 0, source)
    if cache_key in _ACTIVE_GEOJSON_LEVEL_CACHE:
        return _ACTIVE_GEOJSON_LEVEL_CACHE[cache_key]
    with perf_section("active_geojson_is_subject_level: fallback JSON parse"):
        try:
            data = read_json_file(path)
        except Exception:
            _ACTIVE_GEOJSON_LEVEL_CACHE[cache_key] = False
            return False
        features = data.get("features") if isinstance(data, dict) else None
        result = isinstance(features, list) and len(features) >= 20
        _ACTIVE_GEOJSON_LEVEL_CACHE[cache_key] = result
        return result


def projected_feature_polygons(europe_only: bool = False) -> List[Tuple[str, List[List[Tuple[float, float]]]]]:
    features = load_geojson_features_lonlat(europe_only)
    result: List[Tuple[str, List[List[Tuple[float, float]]]]] = []
    for name, polys in features:
        projected_polys: List[List[Tuple[float, float]]] = []
        for poly in polys:
            pp = [project_lonlat(lon, lat) for lon, lat in poly]
            if len(pp) >= 3:
                projected_polys.append(pp)
        if projected_polys:
            result.append((name, projected_polys))
    return result

def projected_outline_polygons(europe_only: bool = False) -> List[List[Tuple[float, float]]]:
    lonlat_polys = load_geojson_lonlat_polygons(europe_only)
    projected: List[List[Tuple[float, float]]] = []
    for poly in lonlat_polys:
        pp = [project_lonlat(lon, lat) for lon, lat in poly]
        if len(pp) >= 3:
            projected.append(pp)
    if projected:
        return projected
    # Emergency fallback: use a bounding hull from real administrative centers.
    pts = []
    for _, (lat, lon, fd, city) in map_regions_for_drawing(europe_only).items():
        pts.append(project_lonlat(lon, lat))
    return [convex_hull(pts)] if pts else []


def point_in_any_projected_outline(x: float, y: float, europe_only: bool = False) -> bool:
    return any(point_in_poly(x, y, poly) for poly in projected_outline_polygons(europe_only))


def projected_region_points(europe_only: bool = False) -> Dict[str, Tuple[float, float, str, str, float, float]]:
    result: Dict[str, Tuple[float, float, str, str, float, float]] = {}
    for region, (lat, lon, fd, city) in map_regions_for_drawing(europe_only).items():
        x, y = project_lonlat(lon, lat)
        result[region] = (x, y, fd, city, lat, lon)
    return result




def should_draw_federal_district_overlay() -> bool:
    """Draw approximate district overlay only for custom detailed geo layers.

    The built-in layer is only a country-level outline; drawing district hulls over
    it produces diagonal artifacts. Once a detailed ADM1 layer is loaded, the
    overlay becomes useful as an analytical grouping aid.
    """
    settings = get_geo_settings()
    return str(settings.get("source", "builtin")).lower() != "builtin"


def fd_hulls_projected(europe_only: bool = False) -> Dict[str, List[Tuple[float, float]]]:
    """Approximate federal-district overlay by administrative-center hulls."""
    groups: Dict[str, List[Tuple[float, float]]] = {}
    for _, (x, y, fd, city, lat, lon) in projected_region_points(europe_only).items():
        if fd == "РФ":
            continue
        groups.setdefault(fd, []).append((x, y))
    hulls: Dict[str, List[Tuple[float, float]]] = {}
    for fd, pts in groups.items():
        if len(pts) < 3:
            hulls[fd] = pts
            continue
        h = convex_hull(pts)
        if len(h) < 3:
            continue
        cx = sum(x for x, _ in h) / len(h)
        cy = sum(y for _, y in h) / len(h)
        expanded = [(cx + (x - cx) * 1.04, cy + (y - cy) * 1.06) for x, y in h]
        hulls[fd] = expanded
    return hulls


def download_geoboundaries_adm1(output_dir: Path, log_fn: Optional[Any] = None) -> Path:
    """Download RUS ADM1 GeoJSON through geoBoundaries API on user's machine."""
    if requests is None:
        raise RuntimeError("Не установлен requests.")
    output_dir.mkdir(parents=True, exist_ok=True)
    if log_fn:
        log_fn(f"Запрос API geoBoundaries: {GEODOWNLOAD_DEFAULT_API}")
    r = requests.get(GEODOWNLOAD_DEFAULT_API, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=120)
    r.raise_for_status()
    meta = r.json()
    gj_url = meta.get("gjDownloadURL") or meta.get("simplifiedGeometryGeoJSON") or meta.get("dlPath")
    if not gj_url:
        raise RuntimeError("В ответе geoBoundaries не найден URL GeoJSON.")
    if log_fn:
        log_fn(f"Скачивание GeoJSON: {gj_url}")
    g = requests.get(gj_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=240)
    g.raise_for_status()
    path = output_dir / "custom_geoboundaries_rus_adm1.geojson"
    path.write_bytes(g.content)
    write_json_file(output_dir / "custom_geoboundaries_metadata.json", meta)
    return path

def require_matplotlib() -> None:
    if Figure is None or FigureCanvasTkAgg is None or Poly3DCollection is None:
        raise RuntimeError("Не установлен matplotlib. Выполните: pip install -r requirements.txt")


def _set_axes_equalish(ax, regs: Dict[str, Tuple[float, float, str, str]], europe_only: bool = False, max_z: float = 8.0, extent_points: Optional[List[Tuple[float, float]]] = None) -> None:
    """Set a map-like 3D view. Uses active border geometry for the viewport when available."""
    pts: List[Tuple[float, float]] = list(extent_points or [])
    if not pts:
        outlines = projected_country_outline_polygons(europe_only)
        for poly in outlines:
            pts.extend(poly)
    for x, y, _, _, _, _ in projected_region_points(europe_only).values():
        pts.append((x, y))
    if not pts:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    pad_x = max(1.5, dx * 0.03)
    pad_y = max(1.0, dy * 0.04)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)
    ax.set_zlim(-0.35, max(1.5, max_z))
    try:
        ax.set_proj_type("ortho")
    except Exception:
        pass
    try:
        ax.set_box_aspect((max(dx + 2 * pad_x, 1.0), max(dy + 2 * pad_y, 1.0), max(3.0, max_z)))
    except Exception:
        pass
    ax.view_init(elev=68, azim=-90)
    ax.set_axis_off()
    try:
        ax.set_position([0.0, 0.0, 1.0, 1.0])
    except Exception:
        pass


def _add_mpl_extruded_polygon(
    ax,
    polygon: List[Tuple[float, float]],
    name: str,
    top_z: float = 0.0,
    bottom_z: float = -0.45,
    facecolor=(0.10, 0.48, 0.84, 0.82),
    edgecolor=(0.86, 0.02, 0.02, 0.95),
    linewidth: float = 0.85,
    draw_sides: bool = True,
) -> None:
    if not polygon or Poly3DCollection is None:
        return
    top = [(x, y, top_z) for x, y in polygon]
    poly = Poly3DCollection([top], facecolor=facecolor, edgecolor=edgecolor, linewidths=linewidth)
    ax.add_collection3d(poly)
    if draw_sides:
        n = len(polygon)
        side_faces = []
        for idx in range(n):
            x1, y1 = polygon[idx]
            x2, y2 = polygon[(idx + 1) % n]
            side_faces.append([(x1, y1, bottom_z), (x2, y2, bottom_z), (x2, y2, top_z), (x1, y1, top_z)])
        side_poly = Poly3DCollection(
            side_faces,
            facecolor=(0.05, 0.24, 0.52, 0.22),
            edgecolor=(0.04, 0.16, 0.36, 0.08),
            linewidths=0.16,
        )
        ax.add_collection3d(side_poly)


def draw_base_map_on_axes(ax, europe_only: bool = False, boundary_step: int = 10) -> None:
    require_matplotlib()
    ax.clear()
    regs = map_regions_for_drawing(europe_only)
    subject_level = active_geojson_is_subject_level()
    step = get_boundary_draw_step(boundary_step)
    ax.set_title("")

    base_polygons: List[List[Tuple[float, float]]] = []
    base_src_count = 0
    base_bounds: Optional[Tuple[float, float, float, float]] = None
    boundary_lines: List[List[Tuple[float, float]]] = []
    src_count = 0
    shown_count = 0

    if subject_level:
        base_polygons, base_src_count, base_bounds = projected_blue_base_polygons(europe_only)
        _add_blue_base_polygons(ax, base_polygons, alpha=0.74)
        boundary_lines, src_count, shown_count = projected_region_boundary_lines(europe_only, step)
        _add_boundary_lines(ax, boundary_lines, z=0.13, color="red", linewidth=0.42)
    else:
        base_polygons = projected_country_outline_polygons(europe_only)
        base_src_count = sum(len(poly) for poly in base_polygons)
        _add_blue_base_polygons(ax, base_polygons, alpha=0.78)
        flat = _flatten_lines(base_polygons)
        if flat:
            base_bounds = (min(x for x, y in flat), max(x for x, y in flat), min(y for x, y in flat), max(y for x, y in flat))

    extent_points = []
    if base_bounds:
        min_x, max_x, min_y, max_y = base_bounds
        extent_points = [(min_x, min_y), (max_x, max_y)]
    elif base_polygons:
        extent_points = _flatten_lines(base_polygons)

    ax._boundary_stats = {
        "source_points": src_count,
        "shown_points": shown_count,
        "step": step,
        "subject_level": subject_level,
        "line_count": len(boundary_lines),
        "base_points": base_src_count,
    }

    pts = projected_region_points(europe_only)
    city_points = []
    if pts:
        xs = []
        ys = []
        zs = []
        for region, (x, y, fd, city, lat, lon) in pts.items():
            xs.append(x); ys.append(y); zs.append(0.32)
            city_points.append({"x": x, "y": y, "z": 0.32, "label": city or region, "region": region})
        ax.scatter(xs, ys, zs, c="black", s=18, edgecolors="white", linewidths=0.35, depthshade=False)
    ax._city_points = city_points
    ax._map_subject_level = subject_level
    _set_axes_equalish(ax, regs, europe_only=europe_only, max_z=4.0, extent_points=extent_points)


def draw_value_map_on_axes(ax, region_values: List[Tuple[str, float]], title: str, scale: float = 1.0, surface: bool = True, europe_only: bool = False, boundary_step: int = 10) -> None:
    require_matplotlib()
    ax.clear()
    regs = map_regions_for_drawing(europe_only)
    subject_level = active_geojson_is_subject_level()
    step = get_boundary_draw_step(boundary_step)

    base_polygons: List[List[Tuple[float, float]]] = []
    base_src_count = 0
    base_bounds: Optional[Tuple[float, float, float, float]] = None
    boundary_lines: List[List[Tuple[float, float]]] = []
    src_count = 0
    shown_count = 0
    if subject_level:
        base_polygons, base_src_count, base_bounds = projected_blue_base_polygons(europe_only)
        _add_blue_base_polygons(ax, base_polygons, alpha=0.48)
        boundary_lines, src_count, shown_count = projected_region_boundary_lines(europe_only, step)
        _add_boundary_lines(ax, boundary_lines, z=0.10, color="red", linewidth=0.36)
    else:
        base_polygons = projected_country_outline_polygons(europe_only)
        base_src_count = sum(len(poly) for poly in base_polygons)
        _add_blue_base_polygons(ax, base_polygons, alpha=0.55)
        flat = _flatten_lines(base_polygons)
        if flat:
            base_bounds = (min(x for x, y in flat), max(x for x, y in flat), min(y for x, y in flat), max(y for x, y in flat))
    ax._boundary_stats = {"source_points": src_count, "shown_points": shown_count, "step": step, "subject_level": subject_level, "line_count": len(boundary_lines), "base_points": base_src_count}

    coords = []
    ref_points = load_region_reference()
    for region, value in region_values:
        if region in ref_points:
            lat, lon, fd, city = ref_points[region]
            if europe_only and lon > 65:
                continue
            x, y = project_lonlat(lon, lat)
            coords.append((region, float(value), x, y, fd, city, lat, lon))
    if not coords:
        raise RuntimeError("В выбранном файле не удалось сопоставить значения с регионами РФ.")

    scale = scale if scale > 0 else 1.0
    raw_vals = [v for _, v, *_ in coords]
    min_v = min(raw_vals)
    max_v = max(raw_vals)
    spread = max(max_v - min_v, 1e-9)
    if scale == 1.0 and max(abs(v) for v in raw_vals) > 20:
        z_values = [0.35 + ((v - min_v) / spread) * 5.8 for v in raw_vals]
    else:
        z_values = [max(0.05, v * scale) for v in raw_vals]
    max_z = max(z_values) + 0.8

    outline_polys = base_polygons if base_polygons else (boundary_lines if boundary_lines else projected_country_outline_polygons(europe_only))

    city_points = []
    for idx, (region, value, x, y, fd, city, lat, lon) in enumerate(coords):
        z = z_values[idx]
        ax.plot([x, x], [y, y], [0.24, z], color="white", linewidth=1.7)
        ax.scatter([x], [y], [0.28], c="black", s=16, edgecolors="white", linewidths=0.35, depthshade=False)
        ax.scatter([x], [y], [z], c="white", s=24, edgecolors=(0.1, 0.1, 0.1, 0.75), linewidths=0.55, depthshade=False)
        city_points.append({"x": x, "y": y, "z": max(z, 0.28), "label": f"{city or region}: {value}", "region": region})

    if surface and len(coords) >= 3 and np is not None:
        all_outline_points = [pt for poly in outline_polys for pt in poly]
        if all_outline_points:
            x_min = min(x for x, y in all_outline_points) - 0.8
            x_max = max(x for x, y in all_outline_points) + 0.8
            y_min = min(y for x, y in all_outline_points) - 0.8
            y_max = max(y for x, y in all_outline_points) + 0.8
            grid_x = np.linspace(x_min, x_max, 70)
            grid_y = np.linspace(y_min, y_max, 38)
            X, Y = np.meshgrid(grid_x, grid_y)
            Z = np.full_like(X, np.nan, dtype=float)
            for row_idx in range(Y.shape[0]):
                for col_idx in range(X.shape[1]):
                    gx = float(X[row_idx, col_idx])
                    gy = float(Y[row_idx, col_idx])
                    if not any(point_in_poly(gx, gy, poly) for poly in outline_polys):
                        continue
                    num = 0.0
                    den = 0.0
                    for idx, (region, value, px, py, fd, city, lat, lon) in enumerate(coords):
                        d2 = (gx - px) ** 2 + (gy - py) ** 2
                        w = 1.0 / max(d2, 0.10)
                        num += z_values[idx] * w
                        den += w
                    Z[row_idx, col_idx] = num / den if den else np.nan
            ax.plot_surface(X, Y, Z, color=(0.0, 0.72, 1.0, 0.30), linewidth=0, antialiased=True, shade=False, alpha=0.30)

    ax._city_points = city_points
    ax._map_subject_level = subject_level
    ax.set_title("")
    
    extent_points = []
    if base_bounds:
        min_x, max_x, min_y, max_y = base_bounds
        extent_points = [(min_x, min_y), (max_x, max_y)]
    elif base_polygons:
        extent_points = _flatten_lines(base_polygons)
    elif boundary_lines:
        extent_points = _flatten_lines(boundary_lines)
    _set_axes_equalish(ax, regs, europe_only=europe_only, max_z=max_z, extent_points=extent_points)


class FilterTab:
    def __init__(self, parent: ttk.Notebook, dim: FilterDimension, on_change=None):
        self.dim = dim
        self.on_change = on_change
        self.frame = ttk.Frame(parent)
        parent.add(self.frame, text=f"{dim.object_id} {dim.title[:24]}")
        self.search_var = tk.StringVar()
        self.placement_var = tk.StringVar(value=dim.placement)
        self._build()
        self.refresh_list()

    def _build(self):
        top = ttk.Frame(self.frame)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Размещение:").pack(side="left")
        cmb = ttk.Combobox(top, textvariable=self.placement_var, width=16, state="readonly", values=["row", "column", "filter", "ignore"])
        cmb.pack(side="left", padx=5)
        cmb.bind("<<ComboboxSelected>>", self._placement_changed)
        ttk.Label(top, text="row=строки, column=колонки, filter=скрытый фильтр, ignore=не использовать").pack(side="left", padx=8)

        search = ttk.Frame(self.frame)
        search.pack(fill="x", padx=6, pady=4)
        ttk.Label(search, text="Поиск:").pack(side="left")
        ent = ttk.Entry(search, textvariable=self.search_var)
        ent.pack(side="left", fill="x", expand=True, padx=5)
        ent.bind("<KeyRelease>", lambda e: self.refresh_list())
        ttk.Button(search, text="Выбрать найденные", command=self.select_visible).pack(side="left", padx=2)
        ttk.Button(search, text="Выбрать всё", command=self.select_all).pack(side="left", padx=2)
        ttk.Button(search, text="Снять найденные", command=self.clear_visible).pack(side="left", padx=2)
        ttk.Button(search, text="Снять все", command=self.clear_all).pack(side="left", padx=2)

        cols = ("checked", "value_id", "title")
        self.tree = ttk.Treeview(self.frame, columns=cols, show="headings", height=15)
        self.tree.heading("checked", text="✓")
        self.tree.heading("value_id", text="ID")
        self.tree.heading("title", text="Значение фильтра")
        self.tree.column("checked", width=42, stretch=False, anchor="center")
        self.tree.column("value_id", width=110, stretch=False)
        self.tree.column("title", width=720, stretch=True)
        self.tree.pack(fill="both", expand=True, padx=6, pady=4)
        self.tree.bind("<Double-1>", self.toggle_selected)
        self.tree.bind("<Button-1>", self._single_click)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", padx=6, pady=4)
        self.count_label = ttk.Label(bottom, text="")
        self.count_label.pack(side="left")

    def _placement_changed(self, event=None):
        self.dim.placement = self.placement_var.get()
        if self.on_change:
            self.on_change()

    def filtered_values(self) -> List[FilterValue]:
        q = self.search_var.get().strip().lower()
        if not q:
            return self.dim.values
        return [v for v in self.dim.values if q in v.title.lower() or q in v.value_id.lower()]

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for v in self.filtered_values():
            self.tree.insert("", "end", iid=v.value_id, values=("☑" if v.checked else "☐", v.value_id, v.title))
        total = len(self.dim.values)
        selected = len(self.dim.selected_values())
        visible = len(self.filtered_values())
        self.count_label.config(text=f"Выбрано: {selected}; всего: {total}; показано: {visible}")

    def _single_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        col = self.tree.identify_column(event.x)
        if region == "cell" and col == "#1":
            self.toggle_selected()

    def toggle_selected(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        ids = set(selected)
        for v in self.dim.values:
            if v.value_id in ids:
                v.checked = not v.checked
        self.refresh_list()
        if self.on_change:
            self.on_change()

    def select_visible(self):
        vis = {v.value_id for v in self.filtered_values()}
        for v in self.dim.values:
            if v.value_id in vis:
                v.checked = True
        self.refresh_list()
        if self.on_change:
            self.on_change()

    def select_all(self):
        for v in self.dim.values:
            v.checked = True
        self.refresh_list()
        if self.on_change:
            self.on_change()

    def clear_visible(self):
        vis = {v.value_id for v in self.filtered_values()}
        for v in self.dim.values:
            if v.value_id in vis:
                v.checked = False
        self.refresh_list()
        if self.on_change:
            self.on_change()

    def clear_all(self):
        for v in self.dim.values:
            v.checked = False
        self.refresh_list()
        if self.on_change:
            self.on_change()


class FilterWindow(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Фильтры Fedstat")
        self.geometry("1120x760")
        self.minsize(900, 620)
        self.filter_tabs: List[FilterTab] = []
        self._build()
        self.rebuild_tabs()

    def _build(self):
        controls = ttk.LabelFrame(self, text="Источник фильтров")
        controls.pack(fill="x", padx=8, pady=6)
        row1 = ttk.Frame(controls)
        row1.pack(fill="x", padx=6, pady=3)
        ttk.Label(row1, text="Страница показателя:").pack(side="left")
        ttk.Entry(row1, textvariable=self.app.url_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row1, text="Прогрузить фильтры", command=self.app.load_filters_thread).pack(side="left", padx=4)
        ttk.Button(row1, text="Сохранить", command=self.app.save_default_filter_scheme).pack(side="left", padx=4)
        ttk.Button(row1, text="Сохранить как...", command=self.app.save_filter_scheme_as).pack(side="left", padx=4)
        ttk.Button(row1, text="Загрузить из файла...", command=self.app.load_filter_scheme_from_dialog).pack(side="left", padx=4)

        row2 = ttk.Frame(controls)
        row2.pack(fill="x", padx=6, pady=3)
        self.summary_label = ttk.Label(row2, textvariable=self.app.filters_summary_var)
        self.summary_label.pack(side="left", fill="x", expand=True)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=6)
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=6)
        ttk.Button(bottom, text="Сохранить и закрыть", command=self._save_and_close).pack(side="right", padx=4)
        ttk.Button(bottom, text="Закрыть", command=self.withdraw).pack(side="right", padx=4)

    def _save_and_close(self):
        self.app.save_default_filter_scheme()
        self.withdraw()

    def rebuild_tabs(self):
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        self.filter_tabs = []
        for dim in self.app.dimensions:
            self.filter_tabs.append(FilterTab(self.notebook, dim, on_change=self.app.update_summary))
        self.app.update_summary()



class MapCanvasWindow(tk.Toplevel):
    """Separate resizable map viewport with wheel zoom, border step and city hover labels."""
    def __init__(self, app: "App", title: str, draw_func, save_prefix: str = "rf_map"):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.geometry("1180x760")
        self.minsize(900, 560)
        self.save_prefix = save_prefix
        self.draw_func = draw_func

        topbar = ttk.Frame(self)
        topbar.pack(fill="x", padx=6, pady=4)
        ttk.Label(topbar, text="Уровень упрощения границ регионов:").pack(side="left")
        self.boundary_step_var = tk.StringVar(value=str(get_boundary_draw_step(self.app.region_boundary_step_var.get())))
        self.step_spin = ttk.Spinbox(topbar, from_=1, to=10000, increment=1, width=8, textvariable=self.boundary_step_var)
        self.step_spin.pack(side="left", padx=5)
        ttk.Label(topbar, text="1 = все точки, больше = сильнее упрощение").pack(side="left", padx=6)
        ttk.Button(topbar, text="Перерисовать", command=self.redraw_with_current_step).pack(side="left", padx=6)
        ttk.Button(topbar, text="Сохранить PNG", command=self.save_png).pack(side="right", padx=4)
        self.stats_var = tk.StringVar(value="")
        ttk.Label(topbar, textvariable=self.stats_var).pack(side="right", padx=8)

        self.figure = Figure(figsize=(12, 7), dpi=100)
        try:
            self.figure.subplots_adjust(left=0, right=1, top=1, bottom=0)
        except Exception:
            pass
        self.ax = self.figure.add_subplot(111, projection="3d")
        try:
            self.ax.set_position([0.0, 0.0, 1.0, 1.0])
        except Exception:
            pass
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self)
        self.toolbar.update()
        self._annot = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="white", ec="black", alpha=0.90),
            fontsize=9,
        )
        self._annot.set_visible(False)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_press_event", self._hide_annot)
        self.redraw_with_current_step()

    def _apply_full_viewport_layout(self):
        try:
            self.figure.subplots_adjust(left=0, right=1, top=1, bottom=0)
            self.ax.set_position([0.0, 0.0, 1.0, 1.0])
            self.ax.set_axis_off()
            self.ax.set_title("")
        except Exception:
            pass

    def redraw_with_current_step(self):
        global _CURRENT_PERF_LOGGER
        step = get_boundary_draw_step(self.boundary_step_var.get())
        self.boundary_step_var.set(str(step))
        self.app.region_boundary_step_var.set(str(step))
        old_perf = _CURRENT_PERF_LOGGER
        _CURRENT_PERF_LOGGER = None
        try:
            self.draw_func(self.ax)
            self._apply_full_viewport_layout()
            stats = getattr(self.ax, "_boundary_stats", {}) or {}
            if stats.get("subject_level"):
                self.stats_var.set(
                    (
                        f"Основа: {stats.get('base_points', 0):,} точек; "
                        f"красные линии: {stats.get('shown_points', 0):,} из {stats.get('source_points', 0):,} точек"
                    ).replace(",", " ")
                )
                self.app._log_ui(
                    f"Карта: синяя основа строится отдельно от шага; красные границы — упрощение {step}, показано {stats.get('shown_points', 0)} из {stats.get('source_points', 0)} точек."
                )
            else:
                self.stats_var.set("Границы регионов не активны")
            self.canvas.draw_idle()
        except Exception as exc:
            self.app._log_ui(f"Ошибка перерисовки карты: {exc}")
            messagebox.showerror("Карта", str(exc))
        finally:
            _CURRENT_PERF_LOGGER = old_perf

    def _hide_annot(self, event=None):
        if self._annot.get_visible():
            self._annot.set_visible(False)
            self.canvas.draw_idle()

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        factor = 0.82 if event.button == "up" else 1.22
        for get_lim, set_lim in ((self.ax.get_xlim3d, self.ax.set_xlim3d), (self.ax.get_ylim3d, self.ax.set_ylim3d)):
            lo, hi = get_lim()
            mid = (lo + hi) / 2.0
            half = (hi - lo) * factor / 2.0
            set_lim(mid - half, mid + half)
        zlo, zhi = self.ax.get_zlim3d()
        zmid = (zlo + zhi) / 2.0
        zhalf = (zhi - zlo) * factor / 2.0
        self.ax.set_zlim3d(zmid - zhalf, zmid + zhalf)
        self.canvas.draw_idle()

    def _on_motion(self, event):
        if event.inaxes != self.ax or proj3d is None:
            self._hide_annot()
            return
        city_points = getattr(self.ax, "_city_points", []) or []
        if not city_points:
            self._hide_annot()
            return
        best = None
        best_dist2 = 14.0 ** 2
        for item in city_points:
            x2, y2, _ = proj3d.proj_transform(item["x"], item["y"], item["z"], self.ax.get_proj())
            xp, yp = self.ax.transData.transform((x2, y2))
            d2 = (xp - event.x) ** 2 + (yp - event.y) ** 2
            if d2 < best_dist2:
                best_dist2 = d2
                best = (item, x2, y2)
        if best is None:
            self._hide_annot()
            return
        item, x2, y2 = best
        self._annot.xy = (x2, y2)
        self._annot.set_text(item.get("label") or item.get("region") or "")
        self._annot.set_visible(True)
        self.canvas.draw_idle()

    def save_png(self):
        out_dir = Path(self.app.output_dir_var.get() or "downloads") / "maps"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{self.save_prefix}_{now_stamp()}.png"
        self.figure.savefig(out_path, dpi=180, bbox_inches="tight")
        self.app._log_ui(f"Карта сохранена: {out_path}")
        messagebox.showinfo("Карта", f"Карта сохранена:\n{out_path}")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x820")
        self.minsize(1060, 700)
        self.dimensions: List[FilterDimension] = []
        self.metadata: Dict[str, Any] = {}
        self.last_run_dir: Optional[Path] = None
        self.last_zip_path: Optional[Path] = None
        self.session_page_html: str = ""
        self.client: Optional[FedstatClient] = None
        self.loaded_indicator_url: str = ""
        self.filter_window: Optional[FilterWindow] = None
        self.last_map_path: Optional[Path] = None
        self.base_map_window: Optional[MapCanvasWindow] = None
        self.value_map_window: Optional[MapCanvasWindow] = None
        self.url_var = tk.StringVar(value="https://www.fedstat.ru/indicator/31074")
        self.indicator_id_var = tk.StringVar(value="31074")
        self.dataset_name_var = tk.StringVar(value="ИПЦ по регионам")
        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "downloads"))
        self.timeout_var = tk.StringVar(value="300")
        self.format_var = tk.StringVar(value="excel")
        self.reuse_loaded_session_var = tk.BooleanVar(value=True)
        self.filters_summary_var = tk.StringVar(value="Фильтры пока не загружены.")
        self.data_file_var = tk.StringVar()
        self.date_query_var = tk.StringVar(value="январь")
        self.value_query_var = tk.StringVar(value="")
        self.value_scale_var = tk.StringVar(value="50")
        self.surface_var = tk.BooleanVar(value=True)
        self.map_europe_only_var = tk.BooleanVar(value=False)
        self.region_boundary_step_var = tk.StringVar(value="10")
        self._build_ui()
        self.load_last_settings()
        self.load_default_filter_scheme(silent=True)
        self._log_ui("Программа готова. Карта открывается в отдельном окне PySide6 WebView. Фильтры открываются через меню: Фильтры -> Открыть окно фильтров.")

    def _build_ui(self):
        self._build_menu()
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)
        settings = ttk.LabelFrame(root, text="Общие параметры")
        settings.pack(fill="x", padx=8, pady=6)
        row1 = ttk.Frame(settings)
        row1.pack(fill="x", padx=6, pady=3)
        ttk.Label(row1, text="Страница показателя:").pack(side="left")
        ttk.Entry(row1, textvariable=self.url_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(row1, text="ID:").pack(side="left")
        ttk.Entry(row1, textvariable=self.indicator_id_var, width=10).pack(side="left", padx=5)
        ttk.Label(row1, text="Формат:").pack(side="left")
        ttk.Combobox(row1, textvariable=self.format_var, width=10, values=["excel", "sdmx"], state="readonly").pack(side="left", padx=5)
        ttk.Label(row1, text="Timeout:").pack(side="left")
        ttk.Entry(row1, textvariable=self.timeout_var, width=7).pack(side="left", padx=5)

        row2 = ttk.Frame(settings)
        row2.pack(fill="x", padx=6, pady=3)
        ttk.Label(row2, text="Название выгрузки:").pack(side="left")
        ttk.Entry(row2, textvariable=self.dataset_name_var, width=38).pack(side="left", padx=5)
        ttk.Label(row2, text="Папка данных:").pack(side="left")
        ttk.Entry(row2, textvariable=self.output_dir_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row2, text="...", width=3, command=self.choose_output_dir).pack(side="left")

        progress = ttk.LabelFrame(root, text="Ход выполнения")
        progress.pack(fill="x", padx=8, pady=3)
        self.stage_var = tk.StringVar(value="Ожидание действия.")
        ttk.Label(progress, textvariable=self.stage_var).pack(fill="x", padx=6, pady=2)
        self.progress = ttk.Progressbar(progress, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=6, pady=4)

        self.main_notebook = ttk.Notebook(root)
        self.main_notebook.pack(fill="both", expand=True, padx=8, pady=6)
        self._build_tab_download()
        self._build_tab_map_base()

        log_frame = ttk.LabelFrame(root, text="Журнал")
        log_frame.pack(fill="both", padx=8, pady=6, expand=False)
        self.log_text = tk.Text(log_frame, height=8, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text.configure(state="disabled")

    def _build_menu(self):
        menubar = tk.Menu(self)
        filters_menu = tk.Menu(menubar, tearoff=0)
        filters_menu.add_command(label="Открыть окно фильтров", command=self.open_filter_window)
        filters_menu.add_command(label="Прогрузить фильтры с сайта", command=self.load_filters_thread)
        filters_menu.add_separator()
        filters_menu.add_command(label="Сохранить текущие фильтры", command=self.save_default_filter_scheme)
        filters_menu.add_command(label="Сохранить фильтры как...", command=self.save_filter_scheme_as)
        filters_menu.add_command(label="Загрузить фильтры из файла...", command=self.load_filter_scheme_from_dialog)
        menubar.add_cascade(label="Фильтры", menu=filters_menu)
        geo_menu = tk.Menu(menubar, tearoff=0)
        geo_menu.add_command(label="Открыть настройки геоосновы", command=self.open_geo_settings_window)
        geo_menu.add_command(label="Скачать границы субъектов geoBoundaries", command=self.download_geoboundaries_thread)
        geo_menu.add_command(label="Подготовить кэш границ для текущего шага", command=self.prepare_boundary_cache_thread)
        geo_menu.add_separator()
        geo_menu.add_command(label="Вернуться к встроенной геооснове", command=self.reset_geo_to_builtin)
        menubar.add_cascade(label="Геооснова", menu=geo_menu)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Открыть папку данных", command=lambda: open_path(Path(self.output_dir_var.get() or ".")))
        file_menu.add_command(label="Открыть папку последнего запуска", command=self.open_last_run_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self.config(menu=menubar)

    def _build_tab_download(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="1) Загрузка данных")
        top = ttk.LabelFrame(tab, text="Скачивание")
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, textvariable=self.filters_summary_var).pack(fill="x", padx=6, pady=3)
        row = ttk.Frame(top)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Button(row, text="Скачать и сохранить файл по текущим фильтрам", command=self.download_thread).pack(side="left", padx=4)
        ttk.Checkbutton(row, text="Использовать уже загруженную сессию", variable=self.reuse_loaded_session_var).pack(side="left", padx=8)

        middle = ttk.Frame(tab)
        middle.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.LabelFrame(middle, text="Файлы данных")
        left.pack(fill="both", expand=True)
        cols = ("name", "type", "size", "modified", "path")
        self.files_tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        for c, t, w in [("name", "Файл", 250), ("type", "Тип", 70), ("size", "Размер", 90), ("modified", "Изменен", 140), ("path", "Путь", 350)]:
            self.files_tree.heading(c, text=t)
            self.files_tree.column(c, width=w, stretch=(c == "path"))
        self.files_tree.pack(fill="both", expand=True, padx=6, pady=4)
        self.files_tree.bind("<Double-1>", lambda e: self.open_selected_file())
        self.files_tree.bind("<Button-3>", self.show_files_context_menu)
        self.files_tree.bind("<Control-Button-1>", self.show_files_context_menu)
        self.files_context_menu = tk.Menu(self, tearoff=0)
        self.files_context_menu.add_command(label="Построить", command=self.build_from_selected_file_context_menu)
        self.files_context_menu.add_separator()
        self.files_context_menu.add_command(label="Открыть папку файла", command=self.open_selected_file_folder)
        self.refresh_files()

    def _build_tab_map_base(self):
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="2) Карта")

        actions = ttk.LabelFrame(tab, text="Карта")
        actions.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(actions)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Открыть только карту", command=self.build_base_map_thread).pack(side="left", padx=4)
        ttk.Button(row, text="Открыть карту с параметрами", command=self.build_value_map_thread).pack(side="left", padx=4)
        ttk.Button(row, text="Построить волновую функцию инфляции", command=self.build_wave_surface_thread).pack(side="left", padx=4)

        params = ttk.LabelFrame(tab, text="Параметры карты с параметрами")
        params.pack(fill="x", padx=8, pady=6)

        row1 = ttk.Frame(params)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="Файл данных:").pack(side="left")
        ttk.Entry(row1, textvariable=self.data_file_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row1, text="Выбрать...", command=self.choose_data_file_for_map).pack(side="left", padx=4)
        ttk.Button(row1, text="Взять из списка загрузок", command=self.use_selected_file_for_map).pack(side="left", padx=4)

        row2 = ttk.Frame(params)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Дата/период в заголовке:").pack(side="left")
        ttk.Entry(row2, textvariable=self.date_query_var, width=18).pack(side="left", padx=5)
        ttk.Label(row2, text="Показатель/ключ в заголовке:").pack(side="left")
        ttk.Entry(row2, textvariable=self.value_query_var, width=24).pack(side="left", padx=5)
        ttk.Label(row2, text="Масштаб:").pack(side="left")
        ttk.Entry(row2, textvariable=self.value_scale_var, width=8).pack(side="left", padx=5)
        ttk.Checkbutton(row2, text="Европейская часть", variable=self.map_europe_only_var).pack(side="left", padx=8)

        ttk.Label(
            params,
            text="Для карты с параметрами выберите файл XLS/XLSX/CSV/XML/SDMX или возьмите файл из списка загрузок. Если период или ключ не указаны, программа выберет подходящие значения автоматически."
        ).pack(fill="x", padx=6, pady=5)

    def _append_log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_ui(self, message: str):
        self.after(0, lambda: self._append_log(message))

    def set_progress(self, text: str, value: Optional[int] = None, mode: str = "determinate"):
        def apply():
            self.stage_var.set(text)
            if mode == "indeterminate":
                self.progress.config(mode="indeterminate")
                self.progress.start(10)
            else:
                self.progress.stop()
                self.progress.config(mode="determinate")
                if value is not None:
                    self.progress["value"] = value
        self.after(0, apply)

    def choose_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if path:
            self.output_dir_var.set(path)
            self.save_last_settings()
            self.refresh_files()

    def base_url(self) -> str:
        parsed = urllib.parse.urlparse(self.url_var.get().strip())
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else "https://www.fedstat.ru"

    def normalize_indicator_id(self):
        url = self.url_var.get().strip()
        m = re.search(r"/indicator/(\d+)", url)
        if m:
            self.indicator_id_var.set(m.group(1))

    def timeout_value(self) -> int:
        try:
            return max(5, int(self.timeout_var.get().strip()))
        except Exception:
            return 300

    def open_filter_window(self):
        if self.filter_window is None or not self.filter_window.winfo_exists():
            self.filter_window = FilterWindow(self)
        else:
            self.filter_window.deiconify()
            self.filter_window.lift()

    def open_geo_settings_window(self):
        """Open the geo base settings window.

        N_89 referenced this method from the menu but did not define it, so the
        program crashed at startup. N_90 restores the full menu workflow.
        """
        win = tk.Toplevel(self)
        win.title("Геооснова")
        win.geometry("860x430")
        win.minsize(760, 360)

        source_var = tk.StringVar()
        geojson_var = tk.StringVar()
        reference_var = tk.StringVar()
        status_var = tk.StringVar()

        def refresh():
            settings = get_geo_settings()
            source_var.set(str(settings.get("source", "builtin")))
            geojson_path = get_active_geojson_path()
            reference_path = get_active_region_reference_path()
            geojson_var.set(str(geojson_path))
            reference_var.set(str(reference_path))
            status = []
            status.append("Источник: " + source_var.get())
            status.append("GeoJSON найден: " + ("да" if geojson_path.exists() else "нет"))
            status.append("Справочник регионов найден: " + ("да" if reference_path.exists() else "нет"))
            try:
                regs = load_region_reference()
                status.append(f"Точек административных центров: {len(regs)}")
            except Exception as exc:
                status.append(f"Ошибка чтения справочника регионов: {exc}")
            status_var.set("; ".join(status))

        def choose_geojson():
            path = filedialog.askopenfilename(
                title="Выберите GeoJSON с границами",
                filetypes=[("GeoJSON / JSON", "*.geojson *.json"), ("Все файлы", "*.*")],
            )
            if not path:
                return
            set_geo_settings(geojson_path=path, source="custom")
            self._log_ui(f"Подключена пользовательская геооснова: {path}")
            refresh()

        def choose_reference():
            path = filedialog.askopenfilename(
                title="Выберите CSV справочник регионов",
                filetypes=[("CSV", "*.csv"), ("Все файлы", "*.*")],
            )
            if not path:
                return
            set_geo_settings(region_reference_path=path, source="custom")
            self._log_ui(f"Подключен пользовательский справочник регионов: {path}")
            refresh()

        def reset_builtin():
            reset_geo_settings_to_builtin()
            self._log_ui("Геооснова сброшена к встроенной.")
            refresh()

        top = ttk.LabelFrame(win, text="Текущая геооснова")
        top.pack(fill="x", padx=8, pady=6)

        row0 = ttk.Frame(top)
        row0.pack(fill="x", padx=6, pady=4)
        ttk.Label(row0, text="Источник:", width=20).pack(side="left")
        ttk.Entry(row0, textvariable=source_var, state="readonly").pack(side="left", fill="x", expand=True)

        row1 = ttk.Frame(top)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="GeoJSON:", width=20).pack(side="left")
        ttk.Entry(row1, textvariable=geojson_var, state="readonly").pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row1, text="Заменить...", command=choose_geojson).pack(side="left")

        row2 = ttk.Frame(top)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Справочник регионов:", width=20).pack(side="left")
        ttk.Entry(row2, textvariable=reference_var, state="readonly").pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row2, text="Заменить...", command=choose_reference).pack(side="left")

        mid = ttk.LabelFrame(win, text="Действия")
        mid.pack(fill="x", padx=8, pady=6)
        ttk.Button(mid, text="Скачать границы субъектов geoBoundaries", command=self.download_geoboundaries_thread).pack(side="left", padx=6, pady=6)
        ttk.Button(mid, text="Вернуться к встроенной геооснове", command=reset_builtin).pack(side="left", padx=6, pady=6)
        ttk.Button(mid, text="Открыть папку встроенной геоосновы", command=lambda: open_path(BUILTIN_GEO_DIR)).pack(side="left", padx=6, pady=6)
        ttk.Button(mid, text="Обновить", command=refresh).pack(side="left", padx=6, pady=6)

        info = ttk.LabelFrame(win, text="Проверка")
        info.pack(fill="both", expand=True, padx=8, pady=6)
        ttk.Label(info, textvariable=status_var, wraplength=800, justify="left").pack(fill="x", padx=6, pady=6)
        ttk.Label(
            info,
            text=(
                "Встроенная геооснова нужна для запуска программы без подготовки. "
                "Для более точной карты субъектов скачайте границы geoBoundaries или подключите свой GeoJSON. "
                "Высоты показателя ставятся по административным центрам из CSV справочника."
            ),
            wraplength=800,
            justify="left",
        ).pack(fill="x", padx=6, pady=6)

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=8, pady=6)
        ttk.Button(bottom, text="Закрыть", command=win.destroy).pack(side="right")

        refresh()

    def download_geoboundaries_thread(self):
        threading.Thread(target=self.download_geoboundaries, daemon=True).start()

    def download_geoboundaries(self):
        try:
            self.set_progress("Скачивание границ субъектов geoBoundaries...", 10, "indeterminate")
            base_output = Path(self.output_dir_var.get() or (Path.cwd() / "downloads"))
            geo_output = base_output / "geo"
            self._log_ui("Начато скачивание границ субъектов РФ через geoBoundaries.")
            path = download_geoboundaries_adm1(geo_output, log_fn=self._log_ui)
            set_geo_settings(geojson_path=str(path), source="geoBoundaries ADM1")
            self._log_ui(f"Границы субъектов скачаны и подключены: {path}")
            self.set_progress("Границы субъектов скачаны и подключены.", 100)
            self.after(0, lambda: messagebox.showinfo("Геооснова", f"Границы субъектов скачаны и подключены:\n{path}"))
        except Exception as exc:
            self._log_ui(f"Ошибка скачивания geoBoundaries: {exc}")
            self._log_ui(traceback.format_exc())
            self.set_progress("Ошибка скачивания геоосновы.", 0)
            self.after(0, lambda exc=exc: messagebox.showerror("Геооснова", f"Ошибка скачивания geoBoundaries:\n{exc}"))

    def reset_geo_to_builtin(self):
        reset_geo_settings_to_builtin()
        self._log_ui("Геооснова сброшена к встроенной.")
        self.set_progress("Геооснова сброшена к встроенной.", 100)
        messagebox.showinfo("Геооснова", "Используется встроенная геооснова программы.")

    def load_filters_thread(self):
        threading.Thread(target=self.load_filters, daemon=True).start()

    def load_filters(self):
        try:
            self.normalize_indicator_id()
            url = self.url_var.get().strip()
            self.set_progress("Загрузка страницы показателя Fedstat...", 5, "indeterminate")
            self._log_ui(f"Загрузка страницы показателя: {url}")
            client = FedstatClient(timeout=self.timeout_value())
            response = client.load_indicator_page(url)
            self._log_ui(f"Ответ страницы: HTTP {response.status_code}; тип {response.headers.get('Content-Type','')}; размер {len(response.content)} байт")
            response.raise_for_status()
            self.set_progress("Разбор фильтров из кода страницы...", 60)
            dimensions, metadata = parse_filters_from_html(response.text)
            self.client = client
            self.loaded_indicator_url = url
            self.session_page_html = response.text
            self.dimensions = dimensions
            self.metadata = metadata
            if metadata.get("indicator_id"):
                self.indicator_id_var.set(str(metadata["indicator_id"]))
            if metadata.get("title"):
                self.dataset_name_var.set(metadata["title"])
            self.after(0, self.rebuild_filter_window_tabs)
            self.update_summary()
            self.save_last_settings()
            self.set_progress(f"Фильтры загружены: {len(dimensions)} измерений.", 100)
            self._log_ui(f"Фильтры загружены: {len(dimensions)} измерений.")
        except Exception as e:
            self.set_progress("Ошибка загрузки фильтров.", 0)
            self._log_ui("Ошибка загрузки фильтров: " + str(e))
            self._log_ui(traceback.format_exc())
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось загрузить фильтры:\n{e}"))

    def rebuild_filter_window_tabs(self):
        if self.filter_window and self.filter_window.winfo_exists():
            self.filter_window.rebuild_tabs()

    def update_summary(self):
        if not self.dimensions:
            self.filters_summary_var.set("Фильтры пока не загружены.")
            return
        selected = sum(len(d.selected_values()) for d in self.dimensions)
        rows = [d.title for d in self.dimensions if d.placement == "row"]
        cols = [d.title for d in self.dimensions if d.placement == "column"]
        filts = [d.title for d in self.dimensions if d.placement == "filter"]
        self.filters_summary_var.set(
            f"Измерений: {len(self.dimensions)}; выбранных значений: {selected}; строки: {len(rows)}; колонки: {len(cols)}; скрытые фильтры: {len(filts)}."
        )
        self.save_last_settings()

    def validate_before_download(self) -> bool:
        if not self.dimensions:
            messagebox.showwarning("Нет фильтров", "Сначала откройте меню 'Фильтры' и прогрузите или загрузите фильтры.")
            return False
        if not self.indicator_id_var.get().strip():
            messagebox.showwarning("Нет ID", "Не указан ID показателя.")
            return False
        used = [d for d in self.dimensions if d.placement in ("row", "column", "filter")]
        if not used:
            messagebox.showwarning("Нет размещения", "Нужно выбрать хотя бы одно измерение для строк, колонок или скрытого фильтра.")
            return False
        no_values = [d.title for d in used if not d.selected_values()]
        if no_values:
            return messagebox.askyesno(
                "Есть измерения без выбранных значений",
                "У некоторых используемых измерений не выбрано ни одного значения:\n\n"
                + "\n".join(no_values[:10])
                + "\n\nПродолжить?"
            )
        return True

    def make_run_dir(self) -> Path:
        base = Path(self.output_dir_var.get().strip() or "downloads")
        dataset = safe_name(self.dataset_name_var.get() or f"indicator_{self.indicator_id_var.get()}")
        run_dir = base / "Fedstat" / dataset / f"run_{now_stamp()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        self.last_run_dir = run_dir
        return run_dir

    def download_thread(self):
        if not self.validate_before_download():
            return
        threading.Thread(target=self.download, daemon=True).start()

    def download(self):
        run_dir = self.make_run_dir()
        logger = RunLogger(run_dir / "run_log.txt", ui_callback=self._log_ui)
        try:
            self.set_progress("Подготовка запроса Fedstat...", 5)
            logger.log("=" * 80)
            logger.log(f"Запуск {APP_NAME} {APP_VERSION}")
            logger.log(f"Папка запуска: {run_dir}")
            url = self.url_var.get().strip()
            indicator_id = self.indicator_id_var.get().strip()
            fmt = self.format_var.get().strip() or "excel"
            title = self.dataset_name_var.get().strip() or self.metadata.get("title") or f"Fedstat {indicator_id}"
            payload = build_payload(indicator_id, title, self.dimensions)
            sanitized = {
                "app": APP_NAME,
                "version": APP_VERSION,
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "indicator_url": url,
                "indicator_id": indicator_id,
                "format": fmt,
                "dataset_name": title,
                "dimensions": [
                    {
                        "object_id": d.object_id,
                        "title": d.title,
                        "placement": d.placement,
                        "selected_count": len(d.selected_values()),
                        "selected_values": [asdict(v) for v in d.selected_values()],
                    }
                    for d in self.dimensions
                ],
                "payload_preview": payload,
            }
            (run_dir / "selected_filters_and_payload.json").write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
            endpoint = urllib.parse.urljoin(self.base_url(), f"/indicator/data.do?format={urllib.parse.quote(fmt)}")
            save_request_debug(run_dir, endpoint, payload, url)
            logger.log("Файлы selected_filters_and_payload.json, request_body_form_urlencoded.txt и request_equivalent_curl_without_cookies.txt сохранены.")

            client: FedstatClient
            if self.reuse_loaded_session_var.get() and self.client is not None and self.loaded_indicator_url == url:
                client = self.client
                logger.log("Используем сессию, в которой уже были загружены фильтры. Повторно страницу не открываем.")
                if self.session_page_html:
                    (run_dir / "source_page_from_loaded_filters.html").write_text(self.session_page_html, encoding="utf-8", errors="replace")
            else:
                client = FedstatClient(timeout=self.timeout_value())
                logger.log("Текущей сессии нет. Создаем новую сессию и сразу выполняем POST выгрузки без повторного разбора фильтров.")
            self.set_progress("Отправка POST-запроса выгрузки. Ожидаем ответ сервера...", 35, "indeterminate")
            response = client.download_table(self.base_url(), payload, fmt, url, logger)
            self.set_progress("Ответ получен. Сохраняем файл и служебные данные...", 80)
            logger.log(f"Ответ выгрузки: HTTP {response.status_code}; тип {response.headers.get('Content-Type','')}; размер {len(response.content)} байт")
            result = save_response(response, run_dir, title, logger)
            manifest = {
                "app": APP_NAME,
                "version": APP_VERSION,
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "run_dir": str(run_dir),
                "statistics_file_downloaded": result.is_statistics_file,
                "result": asdict(result),
                "what_to_send": "Передайте ZIP этой папки запуска, если нужно проверить результат.",
            }
            (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "README_ЧТО_ПЕРЕДАТЬ.txt").write_text(
                "Передайте файл ZIP, созданный рядом с этой папкой запуска.\n"
                "Внутри ZIP есть run_log.txt, run_manifest.json, selected_filters_and_payload.json, ответ сервера и preview-файлы.\n",
                encoding="utf-8",
            )
            zip_path = zip_run_dir(run_dir)
            self.last_zip_path = zip_path
            logger.log(f"ZIP папки запуска создан: {zip_path}")
            logger.log("Итог: " + ("файл статистики получен." if result.is_statistics_file else "файл статистики не получен, сохранен ответ сервера для анализа."))
            logger.log("=" * 80)
            self.set_progress("Загрузка завершена.", 100)
            self.after(0, self.refresh_files)
            msg = "Файл статистики получен." if result.is_statistics_file else "Статистика не получена; сохранен ответ сервера."
            self.after(0, lambda: messagebox.showinfo("Готово", f"{msg}\n\nZIP запуска:\n{zip_path}"))
        except Exception as e:
            self.set_progress("Ошибка скачивания.", 0)
            logger.log("Ошибка выполнения: " + str(e))
            logger.log(traceback.format_exc())
            try:
                zip_path = zip_run_dir(run_dir)
                self.last_zip_path = zip_path
                logger.log(f"ZIP папки запуска создан после ошибки: {zip_path}")
            except Exception:
                pass
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка скачивания:\n{e}"))

    def save_last_settings(self):
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "indicator_url": self.url_var.get(),
            "indicator_id": self.indicator_id_var.get(),
            "dataset_name": self.dataset_name_var.get(),
            "format": self.format_var.get(),
            "timeout": self.timeout_var.get(),
            "output_dir": self.output_dir_var.get(),
            "region_boundary_step": self.region_boundary_step_var.get(),
        }
        LAST_SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_last_settings(self):
        if not LAST_SETTINGS_PATH.exists():
            return
        try:
            data = json.loads(LAST_SETTINGS_PATH.read_text(encoding="utf-8"))
            self.url_var.set(data.get("indicator_url", self.url_var.get()))
            self.indicator_id_var.set(data.get("indicator_id", self.indicator_id_var.get()))
            self.dataset_name_var.set(data.get("dataset_name", self.dataset_name_var.get()))
            self.format_var.set(data.get("format", self.format_var.get()))
            self.timeout_var.set(str(data.get("timeout", self.timeout_var.get())))
            self.output_dir_var.set(data.get("output_dir", self.output_dir_var.get()))
            self.region_boundary_step_var.set(str(data.get("region_boundary_step", self.region_boundary_step_var.get())))
        except Exception:
            pass

    def scheme_data(self) -> Dict[str, Any]:
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "indicator_url": self.url_var.get(),
            "indicator_id": self.indicator_id_var.get(),
            "dataset_name": self.dataset_name_var.get(),
            "format": self.format_var.get(),
            "dimensions": [asdict(d) for d in self.dimensions],
        }

    def save_default_filter_scheme(self):
        if not self.dimensions:
            messagebox.showwarning("Нет фильтров", "Фильтры ещё не загружены.")
            return
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_FILTER_SCHEME_PATH.write_text(json.dumps(self.scheme_data(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.save_last_settings()
        self._log_ui(f"Фильтры сохранены: {DEFAULT_FILTER_SCHEME_PATH}")
        messagebox.showinfo("Сохранено", f"Фильтры сохранены:\n{DEFAULT_FILTER_SCHEME_PATH}")

    def save_filter_scheme_as(self):
        if not self.dimensions:
            messagebox.showwarning("Нет фильтров", "Фильтры ещё не загружены.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="fedstat_filter_scheme.json")
        if not path:
            return
        Path(path).write_text(json.dumps(self.scheme_data(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._log_ui(f"Фильтры сохранены: {path}")

    def apply_scheme_data(self, data: Dict[str, Any]):
        self.url_var.set(data.get("indicator_url", self.url_var.get()))
        self.indicator_id_var.set(data.get("indicator_id", self.indicator_id_var.get()))
        self.dataset_name_var.set(data.get("dataset_name", self.dataset_name_var.get()))
        self.format_var.set(data.get("format", self.format_var.get()))
        dims = []
        for d in data.get("dimensions", []):
            vals = [FilterValue(**v) for v in d.get("values", [])]
            dims.append(FilterDimension(
                object_id=str(d.get("object_id", "")),
                title=d.get("title", ""),
                values=vals,
                all_flag=bool(d.get("all_flag", False)),
                indicator=bool(d.get("indicator", False)),
                placement=d.get("placement", "ignore"),
            ))
        self.dimensions = dims
        self.update_summary()
        self.rebuild_filter_window_tabs()

    def load_default_filter_scheme(self, silent: bool = False):
        if not DEFAULT_FILTER_SCHEME_PATH.exists():
            if not silent:
                messagebox.showinfo("Нет сохраненных фильтров", "Сохраненная схема фильтров не найдена.")
            return
        try:
            data = json.loads(DEFAULT_FILTER_SCHEME_PATH.read_text(encoding="utf-8"))
            self.apply_scheme_data(data)
            self._log_ui(f"Загружены сохраненные фильтры: {DEFAULT_FILTER_SCHEME_PATH}")
        except Exception as e:
            if not silent:
                messagebox.showerror("Ошибка", f"Не удалось загрузить фильтры:\n{e}")

    def load_filter_scheme_from_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.apply_scheme_data(data)
            self._log_ui(f"Схема фильтров загружена: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить схему:\n{e}")

    def refresh_files(self):
        try:
            base = Path(self.output_dir_var.get() or "downloads")
            files = []
            hidden_count = 0
            if base.exists():
                for p in base.rglob("*"):
                    if not p.is_file():
                        continue
                    if is_data_file(p):
                        st = p.stat()
                        files.append((p, st.st_size, _dt.datetime.fromtimestamp(st.st_mtime)))
                    elif p.suffix.lower() in DATA_FILE_EXTENSIONS or looks_like_service_file(p):
                        hidden_count += 1
            files.sort(key=lambda x: x[2], reverse=True)
            self.files_tree.delete(*self.files_tree.get_children())
            for idx, (p, size, mtime) in enumerate(files[:500]):
                self.files_tree.insert("", "end", iid=str(idx), values=(p.name, p.suffix.lower(), f"{size/1024:.1f} КБ", mtime.strftime("%Y-%m-%d %H:%M"), str(p)))
            self._log_ui(f"Список файлов данных обновлен: найдено {len(files)} файлов данных; служебные файлы скрыты: {hidden_count}.")
        except Exception as e:
            self._log_ui("Ошибка обновления списка файлов: " + str(e))

    def get_selected_file_path(self) -> Optional[Path]:
        sel = self.files_tree.selection()
        if not sel:
            return None
        vals = self.files_tree.item(sel[0], "values")
        if not vals:
            return None
        return Path(vals[4])

    def preview_selected_file(self):
        path = self.get_selected_file_path()
        if not path:
            messagebox.showinfo("Файл не выбран", "Выберите файл в списке.")
            return
        threading.Thread(target=lambda: self._preview_file(path), daemon=True).start()

    def _preview_file(self, path: Path):
        try:
            self.set_progress(f"Чтение файла: {path.name}", 10, "indeterminate")
            df = read_table_any(path, max_rows=200)
            self.after(0, lambda: self.show_dataframe_preview(df))
            self.set_progress(f"Файл открыт для просмотра: {path.name}", 100)
        except Exception as e:
            self.set_progress("Ошибка просмотра файла.", 0)
            self._log_ui("Ошибка просмотра файла: " + str(e))
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}"))

    def show_dataframe_preview(self, df):
        for col in self.preview_tree["columns"]:
            self.preview_tree.heading(col, text="")
        self.preview_tree.delete(*self.preview_tree.get_children())
        columns = [str(c) for c in list(df.columns)[:30]]
        self.preview_tree["columns"] = columns
        self.preview_tree["show"] = "headings"
        for c in columns:
            self.preview_tree.heading(c, text=c)
            self.preview_tree.column(c, width=120, stretch=True)
        for _, row in df.head(200).iterrows():
            vals = ["" if pd.isna(row[c]) else str(row[c]) for c in list(df.columns)[:30]] if pd is not None else []
            self.preview_tree.insert("", "end", values=vals)

    def open_selected_file(self):
        path = self.get_selected_file_path()
        if not path:
            messagebox.showinfo("Файл не выбран", "Выберите файл в списке.")
            return
        open_path(path)

    def open_selected_file_folder(self):
        path = self.get_selected_file_path()
        if not path:
            messagebox.showinfo("Файл не выбран", "Выберите файл в списке.")
            return
        open_path(path.parent)

    def show_files_context_menu(self, event):
        row_id = self.files_tree.identify_row(event.y)
        if not row_id:
            return
        self.files_tree.selection_set(row_id)
        self.files_tree.focus(row_id)
        try:
            self.files_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.files_context_menu.grab_release()

    def use_selected_file_for_map(self):
        path = self.get_selected_file_path()
        if not path:
            messagebox.showinfo("Файл не выбран", "Выберите файл в списке загрузок.")
            return
        self.set_selected_file_as_map_source(path)

    def build_from_selected_file_context_menu(self):
        path = self.get_selected_file_path()
        if not path:
            messagebox.showinfo("Файл не выбран", "Выберите файл в списке загрузок.")
            return
        self.set_selected_file_as_map_source(path)

    def set_selected_file_as_map_source(self, path: Path):
        self.data_file_var.set(str(path))
        self.main_notebook.select(1)
        self.set_progress(f"Файл выбран как источник данных карты: {path.name}", 100)
        self._log_ui(f"Файл выбран как источник данных карты: {path}")

    def choose_data_file_for_map(self):
        path = filedialog.askopenfilename(filetypes=[("Data files", "*.xlsx *.xls *.csv *.xml *.sdmx"), ("All files", "*.*")])
        if path:
            self.data_file_var.set(path)

    def prepare_boundary_cache_thread(self):
        threading.Thread(target=self.prepare_boundary_cache_for_current_step, daemon=True).start()

    def prepare_boundary_cache_for_current_step(self):
        try:
            self.set_progress("Подготовка кэша границ...", 5, "determinate")
            self.ensure_subject_borders_loaded()
            step = get_boundary_draw_step(self.region_boundary_step_var.get())
            if not active_geojson_is_subject_level():
                self.set_progress("Границы регионов не активны. Кэш не требуется.", 100)
                return
            base_polys, base_src, _base_bounds = prepare_projected_blue_base_cache(
                europe_only=self.map_europe_only_var.get(),
                progress_cb=lambda msg, pct: self.set_progress(msg, pct, "determinate"),
                log_fn=self._log_ui,
            )
            pts, src, shown = prepare_projected_region_border_points_cache(
                europe_only=self.map_europe_only_var.get(),
                draw_step=step,
                progress_cb=lambda msg, pct: self.set_progress(msg, pct, "determinate"),
                log_fn=self._log_ui,
            )
            self.set_progress(f"Кэш карты готов: основа {base_src} точек; границы {shown} из {src} точек.", 100)
            self._log_ui(f"Кэш карты готов: синяя основа {base_src} точек; красные границы при упрощении {step}: показано {shown} из {src} точек.")
        except Exception as exc:
            self.set_progress("Ошибка подготовки кэша границ.", 0)
            self._log_ui("Ошибка подготовки кэша границ: " + str(exc))
            self._log_ui(traceback.format_exc())
            self.after(0, lambda exc=exc: messagebox.showerror("Кэш границ", str(exc)))

    def launch_pyside_webview_map(self, mode: str = "base", title: str = "Карта РФ", values_json: Optional[Path] = None):
        """Launch a separate PySide6 WebView process with MapLibre GL JS map rendering."""
        script = APP_DIR / "map_webview.py"
        if not script.exists():
            raise RuntimeError(f"Не найден файл окна карты: {script}")
        args = [sys.executable, str(script), "--mode", mode, "--title", title]
        if values_json is not None:
            args.extend(["--values-json", str(values_json)])
        # Start as a separate process so Tkinter and Qt event loops do not conflict.
        subprocess.Popen(args, cwd=str(Path.cwd()))

    def build_base_map_thread(self):
        threading.Thread(target=self.build_base_map_prepare, daemon=True).start()

    def ensure_subject_borders_loaded(self) -> bool:
        """Ensure subject/ADM1 GeoJSON is available before map drawing."""
        if active_geojson_is_subject_level():
            return True
        self._log_ui("Границы регионов не загружены. Начинаю загрузку границ субъектов РФ через geoBoundaries.")
        self.set_progress("Границы регионов не загружены. Скачиваем геооснову субъектов РФ...", 10, "indeterminate")
        try:
            geo_output = Path(self.output_dir_var.get() or "downloads") / "geo"
            path = download_geoboundaries_adm1(geo_output, log_fn=self._log_ui)
            set_geo_settings(geojson_path=str(path), source="geoBoundaries ADM1")
            self._log_ui(f"Границы регионов загружены и подключены: {path}")
            self.after(0, lambda: messagebox.showinfo("Геооснова", f"Границы регионов были не загружены.\nПрограмма скачала и подключила их:\n{path}"))
            return True
        except Exception as exc:
            self._log_ui(f"Не удалось загрузить границы регионов: {exc}")
            self.after(0, lambda exc=exc: messagebox.showwarning("Геооснова", f"Границы регионов не были загружены и автоматически скачать их не удалось.\nБудет показан только встроенный контур РФ.\n\nОшибка:\n{exc}"))
            return False

    def build_base_map_prepare(self):
        try:
            self.set_progress("Подготовка окна карты PySide6 WebView...", 10, "determinate")
            self.ensure_subject_borders_loaded()
            self.set_progress("Открываем карту в отдельном WebView-окне...", 75, "determinate")
            self.after(0, self.open_base_map_window)
        except Exception as exc:
            self._log_ui(f"Ошибка открытия карты: {exc}")
            self.after(0, lambda: messagebox.showerror("Карта", str(exc)))
            self.set_progress("Ошибка открытия карты.", 0)

    def open_base_map_window(self):
        try:
            self.launch_pyside_webview_map(mode="base", title="Карта РФ — MapLibre WebView")
            self.set_progress("Карта РФ открыта в отдельном PySide6 WebView-окне.", 100)
            self._log_ui("Карта РФ открыта через PySide6 WebView + MapLibre GL JS. Панорамирование, масштаб и hover обрабатываются WebGL-движком, без перерисовки Matplotlib.")
        except Exception as exc:
            self._log_ui(f"Ошибка открытия окна карты: {exc}")
            messagebox.showerror("Карта", str(exc))
            self.set_progress("Ошибка открытия окна карты.", 0)

    def build_value_map_thread(self):
        threading.Thread(target=self.build_value_map_prepare, daemon=True).start()

    def build_value_map_prepare(self):
        try:
            self.set_progress("Подготовка геоосновы карты параметра...", 5, "determinate")
            self.ensure_subject_borders_loaded()
            path = Path(self.data_file_var.get().strip())
            if not path.exists():
                self.after(0, lambda: messagebox.showwarning("Нет файла", "Выберите существующий файл данных."))
                return
            self.set_progress("Чтение файла и извлечение значений по регионам...", 30, "indeterminate")
            values = extract_region_values_from_table(path, self.date_query_var.get(), self.value_query_var.get())
            if not values:
                raise RuntimeError("Не удалось извлечь значения по регионам. Попробуйте уточнить дату/период или выбрать другой файл.")
            title = f"Карта параметра — {path.name}; период: {self.date_query_var.get() or 'авто'}"
            self.set_progress(f"Найдено региональных значений: {len(values)}. Открываем WebView-карту...", 75, "determinate")
            self.after(0, lambda: self.draw_value_map(values, title, 1.0))
        except Exception as e:
            self.set_progress("Ошибка построения карты параметра.", 0)
            self._log_ui("Ошибка построения карты параметра: " + str(e))
            self._log_ui(traceback.format_exc())
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось построить карту параметра:\n{e}"))

    def draw_value_map(self, values: List[Tuple[str, float]], title: str, scale: float):
        try:
            out_dir = Path(self.output_dir_var.get() or "downloads") / "maps"
            out_dir.mkdir(parents=True, exist_ok=True)
            values_json = out_dir / f"webview_map_values_{now_stamp()}.json"
            with open(values_json, "w", encoding="utf-8") as f:
                json.dump([{"region": r, "value": float(v)} for r, v in values], f, ensure_ascii=False, indent=2)
            self.launch_pyside_webview_map(mode="value", title=title, values_json=values_json)
            self.set_progress("Карта параметра открыта в отдельном PySide6 WebView-окне.", 100)
            self._log_ui(f"Карта параметра открыта через PySide6 WebView + MapLibre GL JS. Значения сохранены: {values_json}")
        except Exception as exc:
            self._log_ui(f"Ошибка отображения карты параметра: {exc}")
            messagebox.showerror("Карта", str(exc))
            self.set_progress("Ошибка отображения карты параметра.", 0)


    def launch_pyside_wave_surface(self, title: str, values_json: Path, scale: str = "50"):
        """Launch a separate PySide6 WebView process with Plotly/WebGL wave surface."""
        script = APP_DIR / "wave_surface_viewer.py"
        if not script.exists():
            raise RuntimeError(f"Не найден файл окна волновой функции: {script}")
        args = [
            sys.executable,
            str(script),
            "--values-json", str(values_json),
            "--title", title,
            "--scale", str(scale or "50"),
        ]
        subprocess.Popen(args, cwd=str(Path.cwd()))

    def build_wave_surface_thread(self):
        threading.Thread(target=self.build_wave_surface_prepare, daemon=True).start()

    def build_wave_surface_prepare(self):
        try:
            self.set_progress("Подготовка волновой функции инфляции...", 5, "determinate")
            self.ensure_subject_borders_loaded()
            path = Path(self.data_file_var.get().strip())
            if not path.exists():
                self.after(0, lambda: messagebox.showwarning("Нет файла", "Выберите существующий файл данных для построения волновой функции."))
                return
            self.set_progress("Чтение файла и извлечение значений по регионам...", 25, "indeterminate")
            values = extract_region_values_from_table(path, self.date_query_var.get(), self.value_query_var.get())
            if not values:
                raise RuntimeError("Не удалось извлечь значения по регионам. Попробуйте уточнить дату/период или выбрать другой файл.")
            title = f"Волновая функция инфляции — {path.name}; период: {self.date_query_var.get() or 'авто'}"
            self.set_progress(f"Найдено региональных значений: {len(values)}. Открываем 3D-окно...", 75, "determinate")
            self.after(0, lambda: self.draw_wave_surface(values, title))
        except Exception as e:
            self.set_progress("Ошибка построения волновой функции.", 0)
            self._log_ui("Ошибка построения волновой функции: " + str(e))
            self._log_ui(traceback.format_exc())
            self.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось построить волновую функцию инфляции:\n{e}"))

    def draw_wave_surface(self, values: List[Tuple[str, float]], title: str):
        try:
            out_dir = Path(self.output_dir_var.get() or "downloads") / "maps"
            out_dir.mkdir(parents=True, exist_ok=True)
            values_json = out_dir / f"wave_surface_values_{now_stamp()}.json"
            with open(values_json, "w", encoding="utf-8") as f:
                json.dump([{"region": r, "value": float(v)} for r, v in values], f, ensure_ascii=False, indent=2)
            scale_text = self.value_scale_var.get().strip() or "50"
            self.launch_pyside_wave_surface(title=title, values_json=values_json, scale=scale_text)
            self.set_progress("Волновая функция инфляции открыта в отдельном PySide6 WebView-окне.", 100)
            self._log_ui(f"Волновая функция инфляции открыта через PySide6 WebView + Plotly/WebGL. Значения сохранены: {values_json}")
        except Exception as exc:
            self._log_ui(f"Ошибка отображения волновой функции: {exc}")
            messagebox.showerror("Волновая функция", str(exc))
            self.set_progress("Ошибка отображения волновой функции.", 0)

    def save_base_map_png(self):
        try:
            if self.base_fig is None:
                raise RuntimeError("Карта еще не построена.")
            out_dir = Path(self.output_dir_var.get() or "downloads") / "maps"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"rf_3d_map_{now_stamp()}.png"
            self.base_fig.savefig(out_path, dpi=180, bbox_inches="tight")
            self._log_ui(f"PNG базовой карты сохранен: {out_path}")
            messagebox.showinfo("Сохранено", f"PNG сохранен:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PNG:\n{e}")

    def save_value_map_png(self):
        try:
            if self.value_fig is None:
                raise RuntimeError("Карта еще не построена.")
            out_dir = Path(self.output_dir_var.get() or "downloads") / "maps"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"rf_3d_value_map_{now_stamp()}.png"
            self.value_fig.savefig(out_path, dpi=180, bbox_inches="tight")
            self._log_ui(f"PNG карты параметра сохранен: {out_path}")
            messagebox.showinfo("Сохранено", f"PNG сохранен:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PNG:\n{e}")

    def open_last_map(self):
        messagebox.showinfo("Карта в окне", "В этой версии карта строится прямо в окне программы. Используйте кнопку 'Сохранить PNG', если нужен файл изображения.")

    def open_last_run_dir(self):
        if not self.last_run_dir or not self.last_run_dir.exists():
            messagebox.showinfo("Нет папки", "Пока нет папки последнего запуска.")
            return
        open_path(self.last_run_dir)


if __name__ == "__main__":
    app = App()
    app.mainloop()
