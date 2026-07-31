# -*- coding: utf-8 -*-
"""
MapLibre WebView map window for Fedstat Research Workstation N_101.

Launched by main.py as a separate PySide6 process. The map uses MapLibre GL JS
(WebGL) inside Qt WebEngine. N_101 adds permanent city labels and value-based
region coloring for parameter maps.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
WORK_DIR = Path.cwd()
SETTINGS_DIR = WORK_DIR / "settings"
GEO_SETTINGS_PATH = SETTINGS_DIR / "geo_settings.json"
BUILTIN_GEO_DIR = APP_DIR / "data" / "geo"
BUILTIN_RUSSIA_GEOJSON_PATH = BUILTIN_GEO_DIR / "russia_country_outline.geojson"
BUILTIN_REGION_REFERENCE_PATH = BUILTIN_GEO_DIR / "regions_reference.csv"
CACHE_DIR = APP_DIR / "data" / "geo" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception as exc:  # pragma: no cover
    print("PySide6/QtWebEngine не установлен:", exc)
    print("Установите зависимости: pip install -r requirements.txt")
    raise

# geoBoundaries / ISO 3166-2 code -> Fedstat Russian region name.
# This is necessary because geoBoundaries properties are usually English
# (shapeName: Altai Krai), while downloaded Fedstat tables use Russian names.
ISO_TO_FEDSTAT_REGION: Dict[str, str] = {
    "RU-AD": "Республика Адыгея",
    "RU-AL": "Республика Алтай",
    "RU-ALT": "Алтайский край",
    "RU-AMU": "Амурская область",
    "RU-ARK": "Архангельская область",
    "RU-AST": "Астраханская область",
    "RU-BA": "Республика Башкортостан",
    "RU-BEL": "Белгородская область",
    "RU-BRY": "Брянская область",
    "RU-BU": "Республика Бурятия",
    "RU-CE": "Чеченская Республика",
    "RU-CHE": "Челябинская область",
    "RU-CHU": "Чукотский автономный округ",
    "RU-CU": "Чувашская Республика",
    "RU-DA": "Республика Дагестан",
    "RU-IN": "Республика Ингушетия",
    "RU-IRK": "Иркутская область",
    "RU-IVA": "Ивановская область",
    "RU-YEV": "Еврейская автономная область",
    "RU-KB": "Кабардино-Балкарская Республика",
    "RU-KGD": "Калининградская область",
    "RU-KL": "Республика Калмыкия",
    "RU-KLU": "Калужская область",
    "RU-KAM": "Камчатский край",
    "RU-KC": "Карачаево-Черкесская Республика",
    "RU-KEM": "Кемеровская область",
    "RU-KHA": "Хабаровский край",
    "RU-KK": "Республика Хакасия",
    "RU-KHM": "Ханты-Мансийский автономный округ - Югра",
    "RU-KIR": "Кировская область",
    "RU-KO": "Республика Коми",
    "RU-KOS": "Костромская область",
    "RU-KDA": "Краснодарский край",
    "RU-KYA": "Красноярский край",
    "RU-KGN": "Курганская область",
    "RU-KRS": "Курская область",
    "RU-LEN": "Ленинградская область",
    "RU-LIP": "Липецкая область",
    "RU-MAG": "Магаданская область",
    "RU-ME": "Республика Марий Эл",
    "RU-MOW": "г. Москва",
    "RU-MOS": "Московская область",
    "RU-MUR": "Мурманская область",
    "RU-NEN": "Ненецкий автономный округ",
    "RU-NIZ": "Нижегородская область",
    "RU-SE": "Республика Северная Осетия - Алания",
    "RU-NGR": "Новгородская область",
    "RU-NVS": "Новосибирская область",
    "RU-OMS": "Омская область",
    "RU-ORE": "Оренбургская область",
    "RU-ORL": "Орловская область",
    "RU-PNZ": "Пензенская область",
    "RU-PER": "Пермский край",
    "RU-PRI": "Приморский край",
    "RU-PSK": "Псковская область",
    "RU-KR": "Республика Карелия",
    "RU-MO": "Республика Мордовия",
    "RU-ROS": "Ростовская область",
    "RU-RYA": "Рязанская область",
    "RU-SPE": "г. Санкт-Петербург",
    "RU-SA": "Республика Саха (Якутия)",
    "RU-SAK": "Сахалинская область",
    "RU-SAM": "Самарская область",
    "RU-SAR": "Саратовская область",
    "RU-SMO": "Смоленская область",
    "RU-STA": "Ставропольский край",
    "RU-SVE": "Свердловская область",
    "RU-TAM": "Тамбовская область",
    "RU-TA": "Республика Татарстан",
    "RU-TOM": "Томская область",
    "RU-TUL": "Тульская область",
    "RU-TY": "Республика Тыва",
    "RU-TVE": "Тверская область",
    "RU-TYU": "Тюменская область",
    "RU-UD": "Удмуртская Республика",
    "RU-ULY": "Ульяновская область",
    "RU-VLA": "Владимирская область",
    "RU-VGG": "Волгоградская область",
    "RU-VLG": "Вологодская область",
    "RU-VOR": "Воронежская область",
    "RU-YAN": "Ямало-Ненецкий автономный округ",
    "RU-YAR": "Ярославская область",
    "RU-ZAB": "Забайкальский край",
}

ENGLISH_NAME_TO_FEDSTAT_REGION: Dict[str, str] = {
    "adygea": "Республика Адыгея",
    "altai republic": "Республика Алтай",
    "altai krai": "Алтайский край",
    "amur oblast": "Амурская область",
    "arkhangelsk oblast": "Архангельская область",
    "astrakhan oblast": "Астраханская область",
    "bashkortostan": "Республика Башкортостан",
    "belgorod oblast": "Белгородская область",
    "bryansk oblast": "Брянская область",
    "buryatia": "Республика Бурятия",
    "chechnya": "Чеченская Республика",
    "chelyabinsk oblast": "Челябинская область",
    "chukotka autonomous okrug": "Чукотский автономный округ",
    "chuvashia": "Чувашская Республика",
    "dagestan": "Республика Дагестан",
    "ingushetia": "Республика Ингушетия",
    "irkutsk oblast": "Иркутская область",
    "ivanovo oblast": "Ивановская область",
    "jewish autonomous oblast": "Еврейская автономная область",
    "kabardino-balkaria": "Кабардино-Балкарская Республика",
    "kaliningrad": "Калининградская область",
    "kalmykia": "Республика Калмыкия",
    "kaluga oblast": "Калужская область",
    "kamchatka krai": "Камчатский край",
    "karachay-cherkessia": "Карачаево-Черкесская Республика",
    "kemerovo oblast": "Кемеровская область",
    "khabarovsk krai": "Хабаровский край",
    "khakassia": "Республика Хакасия",
    "khanty-mansiysk autonomous okrug – ugra": "Ханты-Мансийский автономный округ - Югра",
    "khanty-mansiysk autonomous okrug - ugra": "Ханты-Мансийский автономный округ - Югра",
    "kirov oblast": "Кировская область",
    "komi republic": "Республика Коми",
    "kostroma oblast": "Костромская область",
    "krasnodar krai": "Краснодарский край",
    "krasnoyarsk krai": "Красноярский край",
    "kurgan oblast": "Курганская область",
    "kursk oblast": "Курская область",
    "leningrad oblast": "Ленинградская область",
    "lipetsk oblast": "Липецкая область",
    "magadan oblast": "Магаданская область",
    "mari el": "Республика Марий Эл",
    "moscow": "г. Москва",
    "moscow oblast": "Московская область",
    "murmansk oblast": "Мурманская область",
    "nenets autonomous okrug": "Ненецкий автономный округ",
    "nizhny novgorod oblast": "Нижегородская область",
    "north ossetia–alania": "Республика Северная Осетия - Алания",
    "north ossetia-alania": "Республика Северная Осетия - Алания",
    "novgorod oblast": "Новгородская область",
    "novosibirsk oblast": "Новосибирская область",
    "omsk oblast": "Омская область",
    "orenburg oblast": "Оренбургская область",
    "oryol oblast": "Орловская область",
    "penza oblast": "Пензенская область",
    "perm krai": "Пермский край",
    "primorsky krai": "Приморский край",
    "pskov oblast": "Псковская область",
    "republic of karelia": "Республика Карелия",
    "republic of mordovia": "Республика Мордовия",
    "rostov oblast": "Ростовская область",
    "ryazan oblast": "Рязанская область",
    "saint petersburg": "г. Санкт-Петербург",
    "sakha republic": "Республика Саха (Якутия)",
    "sakhalin oblast": "Сахалинская область",
    "samara oblast": "Самарская область",
    "saratov oblast": "Саратовская область",
    "smolensk oblast": "Смоленская область",
    "stavropol krai": "Ставропольский край",
    "sverdlovsk oblast": "Свердловская область",
    "tambov oblast": "Тамбовская область",
    "tatarstan": "Республика Татарстан",
    "tomsk oblast": "Томская область",
    "tula oblast": "Тульская область",
    "tuva": "Республика Тыва",
    "tver oblast": "Тверская область",
    "tyumen oblast": "Тюменская область",
    "udmurtia": "Удмуртская Республика",
    "ulyanovsk oblast": "Ульяновская область",
    "vladimir oblast": "Владимирская область",
    "volgograd oblast": "Волгоградская область",
    "vologda oblast": "Вологодская область",
    "voronezh oblast": "Воронежская область",
    "yamalo-nenets autonomous okrug": "Ямало-Ненецкий автономный округ",
    "yaroslavl oblast": "Ярославская область",
    "zabaykalsky krai": "Забайкальский край",
}


def _read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_key(text: str) -> str:
    return " ".join(str(text).replace("–", "-").replace("ё", "е").lower().split())


def resolve_geo_paths() -> Tuple[Path, Path, str]:
    source = "builtin"
    geojson_path = BUILTIN_RUSSIA_GEOJSON_PATH
    reference_path = BUILTIN_REGION_REFERENCE_PATH
    if GEO_SETTINGS_PATH.exists():
        try:
            settings = _read_json(GEO_SETTINGS_PATH)
            if isinstance(settings, dict):
                source = str(settings.get("source") or source)
                candidate = Path(str(settings.get("geojson_path") or ""))
                if candidate.exists():
                    geojson_path = candidate
                ref_candidate = Path(str(settings.get("region_reference_path") or ""))
                if ref_candidate.exists():
                    reference_path = ref_candidate
        except Exception:
            pass
    return geojson_path, reference_path, source


def read_region_reference(path: Path, values_by_region: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    features: List[Dict[str, Any]] = []
    norm_values = {normalize_key(k): v for k, v in (values_by_region or {}).items()}
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = (row.get("fedstat_name") or row.get("region") or row.get("name") or "").strip()
            city = (row.get("capital_city") or row.get("city") or "").strip()
            district = (row.get("federal_district") or row.get("district") or "").strip()
            lat_s = row.get("capital_lat") or row.get("lat") or row.get("latitude") or ""
            lon_s = row.get("capital_lon") or row.get("lon") or row.get("longitude") or ""
            if not region or not lat_s or not lon_s:
                continue
            try:
                lat = float(str(lat_s).replace(",", "."))
                lon = float(str(lon_s).replace(",", "."))
            except Exception:
                continue
            props: Dict[str, Any] = {"region": region, "city": city or region, "district": district}
            key = normalize_key(region)
            if key in norm_values:
                props["value"] = norm_values[key]
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            })
    return {"type": "FeatureCollection", "features": features}


def load_values(path: Optional[str]) -> Dict[str, float]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = _read_json(p)
        result: Dict[str, float] = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    region = str(item.get("region") or item.get("name") or "").strip()
                    value = item.get("value")
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    region = str(item[0]).strip()
                    value = item[1]
                else:
                    continue
                if region:
                    try:
                        result[region] = float(str(value).replace(",", "."))
                    except Exception:
                        pass
        return result
    except Exception:
        return {}


def get_region_name_from_feature(feature: Dict[str, Any]) -> str:
    props = feature.get("properties") or {}
    for code_key in ("shapeISO", "iso_3166_2", "ISO3166-2", "region_code"):
        code = str(props.get(code_key) or "").strip()
        if code in ISO_TO_FEDSTAT_REGION:
            return ISO_TO_FEDSTAT_REGION[code]
    for name_key in ("fedstat_name", "region", "name_ru", "NAME_RU", "shapeName", "name", "NAME_1"):
        name = str(props.get(name_key) or "").strip()
        if not name:
            continue
        if normalize_key(name) in ENGLISH_NAME_TO_FEDSTAT_REGION:
            return ENGLISH_NAME_TO_FEDSTAT_REGION[normalize_key(name)]
        # If the active GeoJSON already stores Russian names, use them as-is.
        if any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in name):
            return name
    return ""


def write_runtime_region_geojson(geojson_path: Path, values_by_region: Dict[str, float]) -> Tuple[Path, int, Optional[float], Optional[float]]:
    if not values_by_region:
        return geojson_path, 0, None, None
    norm_values = {normalize_key(k): float(v) for k, v in values_by_region.items()}
    digest_source = str(geojson_path.resolve()) + "|" + json.dumps(norm_values, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(digest_source.encode("utf-8", errors="replace")).hexdigest()[:12]
    out = CACHE_DIR / f"webview_regions_values_{digest}.geojson"
    if out.exists():
        vals = list(norm_values.values())
        return out, len(vals), min(vals) if vals else None, max(vals) if vals else None

    data = _read_json(geojson_path)
    matched = 0
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        for feature in data["features"]:
            if not isinstance(feature, dict):
                continue
            props = feature.setdefault("properties", {})
            region_name = get_region_name_from_feature(feature)
            if region_name:
                props["fedstat_region"] = region_name
            key = normalize_key(region_name)
            if key in norm_values:
                props["value"] = norm_values[key]
                props["valueText"] = f"{norm_values[key]:.2f}"
                matched += 1
            else:
                props.pop("value", None)
                props.pop("valueText", None)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    vals = list(norm_values.values())
    return out, matched, min(vals) if vals else None, max(vals) if vals else None


def write_runtime_city_geojson(reference_path: Path, values_by_region: Dict[str, float]) -> Path:
    digest = hashlib.sha1(json.dumps(values_by_region, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    out = CACHE_DIR / f"webview_cities_runtime_{digest}.geojson"
    data = read_region_reference(reference_path, values_by_region or None)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return out


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def build_html(title: str, mode: str, value_count: int = 0, value_min: Optional[float] = None, value_max: Optional[float] = None, maplibre_version: str = "5.9.0") -> str:
    value_mode = mode == "value" and value_count > 0 and value_min is not None and value_max is not None
    if value_mode and value_min == value_max:
        value_min = value_min - 0.01
        value_max = value_max + 0.01
    mid = ((value_min or 0.0) + (value_max or 0.0)) / 2.0
    fill_color_expr = (
        f"['case', ['has', 'value'], ['interpolate', ['linear'], ['get', 'value'], {value_min}, '#d7efff', {mid}, '#4aa3df', {value_max}, '#08306b'], '#d6eaf8']"
        if value_mode else "'#4aa3df'"
    )
    status = (
        f"Карта параметра: сопоставлено регионов: {value_count}; минимум {value_min:.2f}; максимум {value_max:.2f}."
        if value_mode else
        "Карта загружена. Слои: синяя заливка регионов, красные границы регионов, черные точки и постоянные подписи городов."
    )
    legend = ""
    if value_mode:
        legend = f"""
  <div id="legend">
    <div><b>Значение параметра</b></div>
    <div class="bar"></div>
    <div class="legend-row"><span>{value_min:.2f}</span><span>{value_max:.2f}</span></div>
  </div>"""
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link href="https://unpkg.com/maplibre-gl@{maplibre_version}/dist/maplibre-gl.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@{maplibre_version}/dist/maplibre-gl.js"></script>
<style>
  html, body, #map {{ width: 100%; height: 100%; margin: 0; padding: 0; overflow: hidden; background: #ffffff; }}
  #panel {{ position: absolute; left: 10px; top: 10px; z-index: 10; background: rgba(255,255,255,0.92); border: 1px solid #ccc; border-radius: 6px; padding: 8px 10px; font: 13px Arial, sans-serif; max-width: 680px; }}
  #status {{ margin-top: 5px; color: #333; }}
  #legend {{ position: absolute; right: 10px; bottom: 36px; z-index: 10; background: rgba(255,255,255,0.92); border: 1px solid #ccc; border-radius: 6px; padding: 8px 10px; font: 12px Arial, sans-serif; min-width: 190px; }}
  #legend .bar {{ height: 12px; margin: 6px 0; background: linear-gradient(to right, #d7efff, #4aa3df, #08306b); border: 1px solid #777; }}
  .legend-row {{ display: flex; justify-content: space-between; gap: 10px; }}
  .maplibregl-popup-content {{ font: 13px Arial, sans-serif; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <b>{title}</b><br>
  <span>Движок: PySide6 WebView + MapLibre GL JS (WebGL). Колесо мыши — масштаб, левая кнопка — перемещение.</span>
  <div id="status">Загрузка геоосновы...</div>
</div>
{legend}
<script>
const statusEl = document.getElementById('status');
function setStatus(text) {{ statusEl.textContent = text; }}

const emptyStyle = {{
  version: 8,
  sources: {{}},
  layers: [{{ id: 'background', type: 'background', paint: {{ 'background-color': '#ffffff' }} }}]
}};

const map = new maplibregl.Map({{
  container: 'map',
  style: emptyStyle,
  center: [95, 62],
  zoom: 2.05,
  minZoom: 0.8,
  maxZoom: 9,
  attributionControl: false,
  renderWorldCopies: false,
  dragRotate: false,
  pitchWithRotate: false,
}});
map.addControl(new maplibregl.NavigationControl({{ showCompass: false }}), 'bottom-right');

map.on('load', () => {{
  map.addSource('regions', {{ type: 'geojson', data: '/geojson', tolerance: 0.15, buffer: 32, promoteId: 'shapeID' }});
  map.addLayer({{
    id: 'regions-fill',
    type: 'fill',
    source: 'regions',
    paint: {{
      'fill-color': {fill_color_expr},
      'fill-opacity': 0.94
    }}
  }});
  map.addLayer({{
    id: 'regions-border',
    type: 'line',
    source: 'regions',
    paint: {{
      'line-color': '#ff0000',
      'line-width': ['interpolate', ['linear'], ['zoom'], 1, 0.45, 4, 0.8, 7, 1.4],
      'line-opacity': 0.95
    }}
  }});
  map.addSource('cities', {{ type: 'geojson', data: '/cities' }});
  map.addLayer({{
    id: 'cities-dot',
    type: 'circle',
    source: 'cities',
    paint: {{
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 1, 2.2, 5, 4.3, 8, 6.5],
      'circle-color': '#000000',
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 0.8,
      'circle-opacity': 0.92
    }}
  }});
  map.addLayer({{
    id: 'cities-label',
    type: 'symbol',
    source: 'cities',
    layout: {{
      'text-field': ['get', 'city'],
      'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 1, 9, 5, 11, 8, 14],
      'text-offset': [0, 1.12],
      'text-anchor': 'top',
      'text-allow-overlap': true,
      'text-ignore-placement': true
    }},
    paint: {{
      'text-color': '#111111',
      'text-halo-color': '#ffffff',
      'text-halo-width': 1.5,
      'text-opacity': 0.95
    }}
  }});

  map.on('mouseenter', 'cities-dot', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
  map.on('mouseleave', 'cities-dot', () => {{ map.getCanvas().style.cursor = ''; }});
  map.on('click', 'cities-dot', (e) => {{
    if (!e.features || !e.features.length) return;
    const f = e.features[0];
    const p = f.properties || {{}};
    let text = '<b>' + (p.city || '') + '</b><br>' + (p.region || '');
    if (p.value !== undefined) text += '<br>Значение: ' + Number(p.value).toFixed(2);
    popup.setLngLat(f.geometry.coordinates.slice()).setHTML(text).addTo(map);
  }});
  map.on('click', 'regions-fill', (e) => {{
    if (!e.features || !e.features.length) return;
    const p = e.features[0].properties || {{}};
    const name = p.fedstat_region || p.shapeName || p.name || 'Регион';
    let text = '<b>' + name + '</b>';
    if (p.value !== undefined) text += '<br>Значение: ' + Number(p.value).toFixed(2);
    popup.setLngLat(e.lngLat).setHTML(text).addTo(map);
  }});
  setStatus('{status}');
}});
const popup = new maplibregl.Popup({{ closeButton: true, closeOnClick: true, offset: 12 }});
map.on('error', (e) => {{
  console.error(e.error || e);
  setStatus('Ошибка карты. Если карта пустая, проверьте подключение к интернету: MapLibre JS загружается из CDN.');
}});
</script>
</body>
</html>"""


class MapRequestHandler(BaseHTTPRequestHandler):
    geojson_path: Path = BUILTIN_RUSSIA_GEOJSON_PATH
    cities_path: Path = CACHE_DIR / "webview_cities_runtime.geojson"
    html_text: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/map.html"):
            self._send_bytes(self.html_text.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/geojson":
            try:
                self._send_bytes(self.geojson_path.read_bytes(), "application/geo+json; charset=utf-8")
            except Exception as exc:
                self.send_error(500, str(exc))
            return
        if parsed.path == "/cities":
            try:
                self._send_bytes(self.cities_path.read_bytes(), "application/geo+json; charset=utf-8")
            except Exception as exc:
                self.send_error(500, str(exc))
            return
        self.send_error(404, "Not found")


class LocalMapServer:
    def __init__(self, geojson_path: Path, cities_path: Path, html_text: str):
        self.port = find_free_port()
        handler_cls = type("RuntimeMapRequestHandler", (MapRequestHandler,), {})
        handler_cls.geojson_path = geojson_path
        handler_cls.cities_path = cities_path
        handler_cls.html_text = html_text
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler_cls)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
        except Exception:
            pass


class MapWindow(QMainWindow):
    def __init__(self, url: str, title: str, server: LocalMapServer, geojson_path: Path, source: str):
        super().__init__()
        self.server = server
        self.setWindowTitle(title)
        self.resize(1400, 900)
        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)
        tb = QToolBar("Карта")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.info_label = QLabel(f"Геооснова: {geojson_path} | источник: {source}")
        tb.addWidget(self.info_label)
        self.view.load(QUrl(url))

    def closeEvent(self, event) -> None:  # noqa: N802
        self.server.stop()
        super().closeEvent(event)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fedstat MapLibre WebView map")
    parser.add_argument("--mode", default="base", choices=["base", "value"])
    parser.add_argument("--values-json", default="")
    parser.add_argument("--title", default="Карта РФ")
    args = parser.parse_args()

    geojson_path, reference_path, source = resolve_geo_paths()
    values_by_region = load_values(args.values_json)
    if args.mode == "value" and values_by_region:
        geojson_path, value_count, value_min, value_max = write_runtime_region_geojson(geojson_path, values_by_region)
    else:
        value_count, value_min, value_max = 0, None, None
    cities_path = write_runtime_city_geojson(reference_path, values_by_region)
    html_text = build_html(args.title, args.mode, value_count=value_count, value_min=value_min, value_max=value_max)
    server = LocalMapServer(geojson_path, cities_path, html_text)
    server.start()
    app = QApplication(sys.argv)
    win = MapWindow(f"http://127.0.0.1:{server.port}/map.html", args.title, server, geojson_path, source)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
