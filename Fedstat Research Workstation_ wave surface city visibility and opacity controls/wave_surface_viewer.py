# -*- coding: utf-8 -*-
"""
Interactive inflation wave surface viewer for Fedstat Research Workstation N_106.

This window uses PySide6 QtWebEngine and Plotly/WebGL. It is launched as a
separate process from main.py so Tkinter and Qt event loops do not conflict.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import plotly.graph_objects as go
    import plotly.io as pio
except Exception as exc:  # pragma: no cover
    print("Plotly не установлен:", exc)
    print("Установите зависимости: pip install -r requirements.txt")
    raise

PYSIDE_IMPORT_ERROR = None
try:
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception as exc:  # pragma: no cover
    PYSIDE_IMPORT_ERROR = exc
    QUrl = Qt = QApplication = QMainWindow = QToolBar = QLabel = QWebEngineView = None

APP_DIR = Path(__file__).resolve().parent
WORK_DIR = Path.cwd()
SETTINGS_DIR = WORK_DIR / "settings"
GEO_SETTINGS_PATH = SETTINGS_DIR / "geo_settings.json"
BUILTIN_GEO_DIR = APP_DIR / "data" / "geo"
BUILTIN_RUSSIA_GEOJSON_PATH = BUILTIN_GEO_DIR / "russia_country_outline.geojson"
BUILTIN_REGION_REFERENCE_PATH = BUILTIN_GEO_DIR / "regions_reference.csv"


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


def load_values(path: str) -> Dict[str, float]:
    p = Path(path)
    if not p.exists():
        return {}
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
            if not region:
                continue
            try:
                result[region] = float(str(value).replace(",", "."))
            except Exception:
                continue
    return result


def read_region_reference(path: Path, values_by_region: Dict[str, float]) -> List[Dict[str, Any]]:
    norm_values = {normalize_key(k): float(v) for k, v in values_by_region.items()}
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = (row.get("fedstat_name") or row.get("region") or row.get("name") or "").strip()
            city = (row.get("capital_city") or row.get("city") or region).strip()
            if not region:
                continue
            key = normalize_key(region)
            if key not in norm_values:
                continue
            try:
                lat = float(str(row.get("capital_lat") or row.get("lat") or "").replace(",", "."))
                lon = float(str(row.get("capital_lon") or row.get("lon") or "").replace(",", "."))
            except Exception:
                continue
            rows.append({
                "region": region,
                "city": city,
                "lat": lat,
                "lon": lon,
                "value": norm_values[key],
            })
    return rows


def make_projector(reference_points: List[Dict[str, Any]]):
    if reference_points:
        mean_lat = sum(float(p["lat"]) for p in reference_points) / len(reference_points)
    else:
        mean_lat = 60.0
    k = math.cos(math.radians(mean_lat))
    if abs(k) < 0.25:
        k = 0.5

    def project(lon: float, lat: float) -> Tuple[float, float]:
        return lon * k, lat

    return project, mean_lat, k


def iter_geojson_exterior_rings(data: Any) -> Iterable[List[List[float]]]:
    if not isinstance(data, dict):
        return
    features = data.get("features")
    if not isinstance(features, list):
        features = [data]
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geom = feature.get("geometry") or feature
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if gtype == "Polygon" and isinstance(coords, list):
            if coords and isinstance(coords[0], list):
                yield coords[0]
        elif gtype == "MultiPolygon" and isinstance(coords, list):
            for poly in coords:
                if poly and isinstance(poly[0], list):
                    yield poly[0]


def count_ring_points(geojson_path: Path) -> int:
    data = _read_json(geojson_path)
    total = 0
    for ring in iter_geojson_exterior_rings(data):
        total += len(ring)
    return total


def load_projected_map_rings(geojson_path: Path, project, target_line_points: int = 90000, target_mesh_points: int = 22000) -> Tuple[List[List[Tuple[float, float]]], List[List[Tuple[float, float]]], Dict[str, Any]]:
    data = _read_json(geojson_path)
    raw_total = 0
    rings_raw = []
    for ring in iter_geojson_exterior_rings(data):
        clean = []
        for pt in ring:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    lon = float(pt[0]); lat = float(pt[1])
                except Exception:
                    continue
                clean.append((lon, lat))
        if len(clean) >= 3:
            raw_total += len(clean)
            rings_raw.append(clean)

    line_stride = max(1, raw_total // max(1, target_line_points))
    mesh_stride = max(1, raw_total // max(1, target_mesh_points))
    line_rings: List[List[Tuple[float, float]]] = []
    mesh_rings: List[List[Tuple[float, float]]] = []
    for ring in rings_raw:
        line_pts = [project(lon, lat) for idx, (lon, lat) in enumerate(ring) if idx % line_stride == 0]
        mesh_pts = [project(lon, lat) for idx, (lon, lat) in enumerate(ring) if idx % mesh_stride == 0]
        if len(line_pts) >= 2:
            if line_pts[0] != line_pts[-1]:
                line_pts.append(line_pts[0])
            line_rings.append(line_pts)
        if len(mesh_pts) >= 3:
            if mesh_pts[0] != mesh_pts[-1]:
                mesh_pts.append(mesh_pts[0])
            mesh_rings.append(mesh_pts)
    stats = {
        "raw_total": raw_total,
        "line_stride": line_stride,
        "mesh_stride": mesh_stride,
        "line_points": sum(len(r) for r in line_rings),
        "mesh_points": sum(len(r) for r in mesh_rings),
        "ring_count": len(rings_raw),
    }
    return line_rings, mesh_rings, stats


def point_in_ring(x: float, y: float, ring: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        if ((y1 > y) != (y2 > y)):
            xinters = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xinters:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def build_surface_grid(points: List[Dict[str, Any]], map_rings: List[List[Tuple[float, float]]], project, nx: int = 90, ny: int = 55) -> Tuple[List[List[float]], List[List[float]], List[List[Optional[float]]], float, float]:
    if np is None:
        raise RuntimeError("Не установлен numpy. Выполните: pip install -r requirements.txt")
    coords = []
    values = []
    for p in points:
        x, y = project(float(p["lon"]), float(p["lat"]))
        p["x"] = x
        p["y"] = y
        coords.append((x, y))
        values.append(float(p["value"]))
    if len(coords) < 3:
        raise RuntimeError("Для построения поверхности нужно минимум 3 сопоставленных региона с числовыми значениями.")

    all_x = [x for ring in map_rings for x, _ in ring] or [x for x, _ in coords]
    all_y = [y for ring in map_rings for _, y in ring] or [y for _, y in coords]
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    pad_x = (x_max - x_min) * 0.015
    pad_y = (y_max - y_min) * 0.015
    xs = np.linspace(x_min - pad_x, x_max + pad_x, nx)
    ys = np.linspace(y_min - pad_y, y_max + pad_y, ny)

    mean_value = sum(values) / len(values)
    deviations = [v - mean_value for v in values]
    # Use deviations around the mean so index values near 100 become visible as a wave.
    # Exact values remain in hover labels and point labels.
    z_grid: List[List[Optional[float]]] = []

    ring_boxes = []
    for ring in map_rings:
        if len(ring) >= 3:
            rx = [p[0] for p in ring]
            ry = [p[1] for p in ring]
            ring_boxes.append((min(rx), max(rx), min(ry), max(ry), ring))

    for gy in ys:
        row: List[Optional[float]] = []
        for gx in xs:
            inside = False
            # For performance, use simplified exterior rings and bounding boxes.
            for bx0, bx1, by0, by1, ring in ring_boxes:
                if gx < bx0 or gx > bx1 or gy < by0 or gy > by1:
                    continue
                if point_in_ring(float(gx), float(gy), ring):
                    inside = True
                    break
            if not inside:
                row.append(None)
                continue
            num = 0.0
            den = 0.0
            for (px, py), dz in zip(coords, deviations):
                d2 = (float(gx) - px) ** 2 + (float(gy) - py) ** 2
                w = 1.0 / max(d2, 0.06)
                num += dz * w
                den += w
            row.append(num / den if den else None)
        z_grid.append(row)
    return xs.tolist(), ys.tolist(), z_grid, mean_value, max(abs(d) for d in deviations) if deviations else 0.0


def add_map_traces(fig: go.Figure, line_rings: List[List[Tuple[float, float]]], mesh_rings: List[List[Tuple[float, float]]], map_trace_indices: List[int]) -> None:
    # Blue flat base from fan triangles. It is an analytical background plane,
    # not a legal/cartographic boundary product.
    mesh_x: List[float] = []
    mesh_y: List[float] = []
    mesh_z: List[float] = []
    ii: List[int] = []
    jj: List[int] = []
    kk: List[int] = []
    for ring in mesh_rings:
        if len(ring) < 4:
            continue
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        if len(pts) < 3:
            continue
        cx = sum(x for x, _ in pts) / len(pts)
        cy = sum(y for _, y in pts) / len(pts)
        center_idx = len(mesh_x)
        mesh_x.append(cx); mesh_y.append(cy); mesh_z.append(0.0)
        start = len(mesh_x)
        for x, y in pts:
            mesh_x.append(x); mesh_y.append(y); mesh_z.append(0.0)
        for n in range(len(pts)):
            ii.append(center_idx)
            jj.append(start + n)
            kk.append(start + ((n + 1) % len(pts)))
    if mesh_x and ii:
        map_trace_indices.append(len(fig.data))
        fig.add_trace(go.Mesh3d(
            x=mesh_x, y=mesh_y, z=mesh_z,
            i=ii, j=jj, k=kk,
            name="Карта РФ: синяя основа",
            color="rgba(74,163,223,0.62)",
            opacity=0.62,
            hoverinfo="skip",
            flatshading=True,
            showscale=False,
            lighting={"ambient": 0.8, "diffuse": 0.2, "roughness": 0.9},
        ))

    line_x: List[Optional[float]] = []
    line_y: List[Optional[float]] = []
    line_z: List[Optional[float]] = []
    for ring in line_rings:
        for x, y in ring:
            line_x.append(x); line_y.append(y); line_z.append(0.015)
        line_x.append(None); line_y.append(None); line_z.append(None)
    if line_x:
        map_trace_indices.append(len(fig.data))
        fig.add_trace(go.Scatter3d(
            x=line_x, y=line_y, z=line_z,
            mode="lines",
            name="Границы регионов",
            line={"color": "red", "width": 2},
            hoverinfo="skip",
            showlegend=True,
        ))


def build_figure(points: List[Dict[str, Any]], line_rings: List[List[Tuple[float, float]]], mesh_rings: List[List[Tuple[float, float]]], project, title: str, scale: float) -> Tuple[go.Figure, Dict[str, Any]]:
    grid_x, grid_y, raw_z_grid, mean_value, max_abs_dev = build_surface_grid(points, mesh_rings or line_rings, project)
    scale = scale if scale > 0 else 50.0
    scaled_z_grid = [[None if v is None else v * scale for v in row] for row in raw_z_grid]

    fig = go.Figure()
    raw_z_by_trace: Dict[str, Any] = {}
    map_trace_indices: List[int] = []
    surface_trace_indices: List[int] = []

    add_map_traces(fig, line_rings, mesh_rings, map_trace_indices)

    surface_idx = len(fig.data)
    surface_trace_indices.append(surface_idx)
    raw_z_by_trace[str(surface_idx)] = raw_z_grid
    fig.add_trace(go.Surface(
        x=grid_x,
        y=grid_y,
        z=scaled_z_grid,
        surfacecolor=raw_z_grid,
        colorscale="RdBu",
        reversescale=True,
        opacity=0.72,
        name="Волновая функция инфляции",
        colorbar={"title": "Отклонение от среднего"},
        hovertemplate="x=%{x:.2f}<br>y=%{y:.2f}<br>отклонение=%{surfacecolor:.3f}<br>высота=%{z:.3f}<extra></extra>",
        contours={"z": {"show": True, "usecolormap": True, "highlightcolor": "#333", "project_z": True}},
    ))

    px = [p["x"] for p in points]
    py = [p["y"] for p in points]
    raw_pz = [float(p["value"]) - mean_value for p in points]
    scaled_pz = [z * scale for z in raw_pz]
    hover_labels = [f"{p['city']}<br>{p['region']}<br>значение: {float(p['value']):.3f}<br>отклонение от среднего: {float(p['value']) - mean_value:+.3f}" for p in points]
    text_labels = [str(p["city"]) for p in points]

    columns_x: List[Optional[float]] = []
    columns_y: List[Optional[float]] = []
    columns_raw_z: List[Optional[float]] = []
    for x, y, rz in zip(px, py, raw_pz):
        columns_x.extend([x, x, None])
        columns_y.extend([y, y, None])
        columns_raw_z.extend([0.0, rz, None])
    columns_scaled_z = [None if v is None else v * scale for v in columns_raw_z]

    columns_idx = len(fig.data)
    raw_z_by_trace[str(columns_idx)] = columns_raw_z
    fig.add_trace(go.Scatter3d(
        x=columns_x, y=columns_y, z=columns_scaled_z,
        mode="lines",
        name="Вертикали к столицам",
        line={"color": "rgba(30,30,30,0.48)", "width": 2},
        hoverinfo="skip",
        showlegend=False,
    ))

    points_idx = len(fig.data)
    raw_z_by_trace[str(points_idx)] = raw_pz
    fig.add_trace(go.Scatter3d(
        x=px, y=py, z=scaled_pz,
        mode="markers+text",
        name="Столицы регионов",
        marker={"size": 4, "color": [p["value"] for p in points], "colorscale": "Turbo", "colorbar": {"title": "Значение"}, "line": {"color": "white", "width": 1}},
        text=text_labels,
        textposition="top center",
        customdata=hover_labels,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=True,
    ))

    city_points: List[Dict[str, Any]] = []
    for idx, p in enumerate(points):
        city_points.append({
            "idx": idx,
            "city": str(p["city"]),
            "region": str(p["region"]),
            "x": float(p["x"]),
            "y": float(p["y"]),
            "raw_z": float(raw_pz[idx]),
            "value": float(p["value"]),
            "label": hover_labels[idx],
            "text": text_labels[idx],
        })

    fig.update_layout(
        title={"text": title, "x": 0.5},
        scene={
            "xaxis": {"title": "X карты", "showspikes": False, "showticklabels": False},
            "yaxis": {"title": "Y карты", "showspikes": False, "showticklabels": False},
            "zaxis": {"title": "Высота = отклонение × коэффициент", "showspikes": False},
            "aspectmode": "manual",
            "aspectratio": {"x": 2.2, "y": 1.25, "z": 0.45},
            "camera": {"eye": {"x": 0.3, "y": -2.1, "z": 1.25}},
        },
        margin={"l": 0, "r": 0, "t": 70, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 0.0, "xanchor": "left", "x": 0.0},
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    metadata = {
        "raw_z_by_trace": raw_z_by_trace,
        "map_trace_indices": map_trace_indices,
        "surface_trace_indices": surface_trace_indices,
        "columns_trace_index": columns_idx,
        "points_trace_index": points_idx,
        "city_points": city_points,
        "initial_scale": scale,
        "mean_value": mean_value,
        "max_abs_deviation": max_abs_dev,
        "point_count": len(points),
        "initial_surface_opacity": 72,
        "initial_map_opacity": 62,
        "initial_city_opacity": 100,
    }
    return fig, metadata

def build_html(fig: go.Figure, metadata: Dict[str, Any], title: str) -> str:
    plot_id = "wave_plot"
    cities_json = json.dumps(metadata["city_points"], ensure_ascii=False)
    controls = f"""
<div id="controls">
  <div class="control-row">
    <b>Волновая функция инфляции</b>
    <label>Коэффициент высоты: <input id="scaleInput" type="number" value="{metadata['initial_scale']}" step="1" min="0.1" style="width:80px"></label>
    <button id="applyScale">Применить</button>
    <label><input id="showMap" type="checkbox" checked> карта</label>
    <label><input id="showSurface" type="checkbox" checked> поверхность</label>
    <label><input id="showCities" type="checkbox" checked> города</label>
  </div>
  <div class="control-row">
    <label>Прозрачность поверхности: <input id="surfaceOpacity" type="range" min="5" max="100" value="{metadata['initial_surface_opacity']}"><span id="surfaceOpacityValue">{metadata['initial_surface_opacity']}%</span></label>
    <label>Прозрачность карты: <input id="mapOpacity" type="range" min="0" max="100" value="{metadata['initial_map_opacity']}"><span id="mapOpacityValue">{metadata['initial_map_opacity']}%</span></label>
    <label>Прозрачность городов: <input id="cityOpacity" type="range" min="0" max="100" value="{metadata['initial_city_opacity']}"><span id="cityOpacityValue">{metadata['initial_city_opacity']}%</span></label>
  </div>
  <div class="control-row small">
    Точек: {metadata['point_count']}; среднее: {metadata['mean_value']:.3f}; max |отклонение|: {metadata['max_abs_deviation']:.3f}. Мышью можно вращать, колесом — масштабировать.
  </div>
</div>
<div id="cityPanel">
  <div class="city-panel-title">Города на поверхности</div>
  <div class="city-buttons"><button id="selectAllCities">Все</button><button id="clearCities">Скрыть все</button></div>
  <div id="cityList"></div>
</div>
"""
    post_script = f"""
(function() {{
  const plotId = '{plot_id}';
  const rawZByTrace = {json.dumps(metadata['raw_z_by_trace'], ensure_ascii=False)};
  const mapTraceIndices = {json.dumps(metadata['map_trace_indices'])};
  const surfaceTraceIndices = {json.dumps(metadata['surface_trace_indices'])};
  const columnsTraceIndex = {json.dumps(metadata['columns_trace_index'])};
  const pointsTraceIndex = {json.dumps(metadata['points_trace_index'])};
  const cityPoints = {cities_json};
  let currentScale = parseFloat(String(document.getElementById('scaleInput').value).replace(',', '.')) || 1.0;
  let cityVisible = cityPoints.map(function() {{ return true; }});
  let showCities = true;

  function scaleAny(v, scale) {{
    if (v === null || v === undefined) return null;
    if (Array.isArray(v)) return v.map(function(x) {{ return scaleAny(x, scale); }});
    return v * scale;
  }}

  function setVisible(indices, visible) {{
    indices.forEach(function(idx) {{ Plotly.restyle(plotId, {{visible: visible}}, [idx]); }});
  }}

  function selectedCityPoints() {{
    if (!showCities) return [];
    return cityPoints.filter(function(p, i) {{ return cityVisible[i]; }});
  }}

  function updateCities() {{
    const pts = selectedCityPoints();
    const x = pts.map(function(p) {{ return p.x; }});
    const y = pts.map(function(p) {{ return p.y; }});
    const z = pts.map(function(p) {{ return p.raw_z * currentScale; }});
    const val = pts.map(function(p) {{ return p.value; }});
    const txt = pts.map(function(p) {{ return p.text; }});
    const labels = pts.map(function(p) {{ return p.label; }});
    const colX = [];
    const colY = [];
    const colZ = [];
    pts.forEach(function(p) {{
      colX.push(p.x); colX.push(p.x); colX.push(null);
      colY.push(p.y); colY.push(p.y); colY.push(null);
      colZ.push(0); colZ.push(p.raw_z * currentScale); colZ.push(null);
    }});
    Plotly.restyle(plotId, {{x: [colX], y: [colY], z: [colZ]}}, [columnsTraceIndex]);
    Plotly.restyle(plotId, {{x: [x], y: [y], z: [z], text: [txt], customdata: [labels], 'marker.color': [val]}}, [pointsTraceIndex]);
  }}

  function applyScale() {{
    const el = document.getElementById('scaleInput');
    let scale = parseFloat(String(el.value).replace(',', '.'));
    if (!isFinite(scale) || scale <= 0) scale = 1.0;
    currentScale = scale;
    surfaceTraceIndices.forEach(function(idx) {{
      const z = scaleAny(rawZByTrace[String(idx)], scale);
      Plotly.restyle(plotId, {{z: [z]}}, [parseInt(idx)]);
    }});
    updateCities();
  }}

  function setSurfaceOpacity(percent) {{
    const value = Math.max(0, Math.min(1, Number(percent) / 100));
    document.getElementById('surfaceOpacityValue').textContent = String(percent) + '%';
    surfaceTraceIndices.forEach(function(idx) {{ Plotly.restyle(plotId, {{opacity: value}}, [idx]); }});
  }}

  function setMapOpacity(percent) {{
    const value = Math.max(0, Math.min(1, Number(percent) / 100));
    document.getElementById('mapOpacityValue').textContent = String(percent) + '%';
    mapTraceIndices.forEach(function(idx) {{ Plotly.restyle(plotId, {{opacity: value}}, [idx]); }});
  }}

  function setCityOpacity(percent) {{
    const value = Math.max(0, Math.min(1, Number(percent) / 100));
    document.getElementById('cityOpacityValue').textContent = String(percent) + '%';
    Plotly.restyle(plotId, {{opacity: value}}, [columnsTraceIndex, pointsTraceIndex]);
  }}

  function renderCityList() {{
    const list = document.getElementById('cityList');
    list.innerHTML = '';
    cityPoints.forEach(function(p, i) {{
      const row = document.createElement('label');
      row.className = 'city-row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = cityVisible[i];
      cb.addEventListener('change', function() {{
        cityVisible[i] = cb.checked;
        updateCities();
      }});
      const text = document.createElement('span');
      text.textContent = p.city + ' — ' + p.value.toFixed(3);
      row.appendChild(cb);
      row.appendChild(text);
      list.appendChild(row);
    }});
  }}

  document.getElementById('applyScale').addEventListener('click', applyScale);
  document.getElementById('scaleInput').addEventListener('keydown', function(e) {{ if (e.key === 'Enter') applyScale(); }});
  document.getElementById('showMap').addEventListener('change', function(e) {{ setVisible(mapTraceIndices, e.target.checked ? true : 'legendonly'); }});
  document.getElementById('showSurface').addEventListener('change', function(e) {{ setVisible(surfaceTraceIndices, e.target.checked ? true : 'legendonly'); }});
  document.getElementById('showCities').addEventListener('change', function(e) {{
    showCities = e.target.checked;
    Plotly.restyle(plotId, {{visible: showCities ? true : 'legendonly'}}, [columnsTraceIndex, pointsTraceIndex]);
    updateCities();
  }});
  document.getElementById('surfaceOpacity').addEventListener('input', function(e) {{ setSurfaceOpacity(e.target.value); }});
  document.getElementById('mapOpacity').addEventListener('input', function(e) {{ setMapOpacity(e.target.value); }});
  document.getElementById('cityOpacity').addEventListener('input', function(e) {{ setCityOpacity(e.target.value); }});
  document.getElementById('selectAllCities').addEventListener('click', function() {{
    cityVisible = cityVisible.map(function() {{ return true; }});
    renderCityList();
    updateCities();
  }});
  document.getElementById('clearCities').addEventListener('click', function() {{
    cityVisible = cityVisible.map(function() {{ return false; }});
    renderCityList();
    updateCities();
  }});

  renderCityList();
}})();
"""
    body = pio.to_html(fig, include_plotlyjs=True, full_html=False, div_id=plot_id, post_script=post_script, config={"responsive": True, "displaylogo": False})
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; font-family:Arial, sans-serif; }}
  #controls {{ position:absolute; left:10px; top:10px; right:300px; z-index:1000; background:rgba(255,255,255,0.94); border:1px solid #bdbdbd; border-radius:6px; padding:8px 10px; font-size:13px; display:flex; flex-direction:column; gap:5px; }}
  .control-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; }}
  .control-row.small {{ color:#333; font-size:12px; }}
  #controls button, #cityPanel button {{ padding:3px 10px; }}
  #cityPanel {{ position:absolute; right:10px; top:10px; bottom:10px; width:270px; z-index:1001; background:rgba(255,255,255,0.95); border:1px solid #bdbdbd; border-radius:6px; padding:8px; font-size:12px; display:flex; flex-direction:column; }}
  .city-panel-title {{ font-weight:bold; margin-bottom:6px; }}
  .city-buttons {{ display:flex; gap:6px; margin-bottom:6px; }}
  #cityList {{ overflow:auto; flex:1; border-top:1px solid #ddd; padding-top:5px; }}
  .city-row {{ display:flex; gap:5px; align-items:flex-start; padding:2px 0; cursor:pointer; }}
  .city-row span {{ line-height:1.2; }}
  #{plot_id} {{ width:100vw; height:100vh; }}
</style>
</head>
<body>
{controls}
{body}
</body>
</html>"""


if QMainWindow is not None:
    class WaveSurfaceWindow(QMainWindow):
        def __init__(self, html_path: Path, title: str, info_text: str):
            super().__init__()
            self.setWindowTitle(title)
            self.resize(1500, 930)
            self.view = QWebEngineView(self)
            self.setCentralWidget(self.view)
            tb = QToolBar("Волновая функция")
            tb.setMovable(False)
            self.addToolBar(Qt.TopToolBarArea, tb)
            tb.addWidget(QLabel(info_text))
            self.view.load(QUrl.fromLocalFile(str(html_path.resolve())))
else:  # pragma: no cover
    class WaveSurfaceWindow:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(f"PySide6/QtWebEngine не установлен: {PYSIDE_IMPORT_ERROR}. Установите зависимости: pip install -r requirements.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fedstat inflation wave surface viewer")
    parser.add_argument("--values-json", required=True)
    parser.add_argument("--title", default="Волновая функция инфляции")
    parser.add_argument("--scale", default="50")
    args = parser.parse_args()

    values_by_region = load_values(args.values_json)
    if not values_by_region:
        raise RuntimeError("Нет значений по регионам для построения волновой функции.")
    geojson_path, reference_path, source = resolve_geo_paths()
    points = read_region_reference(reference_path, values_by_region)
    if len(points) < 3:
        raise RuntimeError("Недостаточно сопоставленных регионов для построения поверхности.")
    project, _mean_lat, _k = make_projector(points)
    line_rings, mesh_rings, stats = load_projected_map_rings(geojson_path, project)
    try:
        scale = float(str(args.scale).replace(",", "."))
    except Exception:
        scale = 50.0
    fig, metadata = build_figure(points, line_rings, mesh_rings, project, args.title, scale)
    html_text = build_html(fig, metadata, args.title)
    tmp_dir = Path(tempfile.gettempdir()) / "fedstat_wave_surface"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    html_path = tmp_dir / "wave_surface.html"
    html_path.write_text(html_text, encoding="utf-8")

    if QApplication is None:
        raise RuntimeError(f"PySide6/QtWebEngine не установлен: {PYSIDE_IMPORT_ERROR}. Установите зависимости: pip install -r requirements.txt")
    app = QApplication(sys.argv)
    info = f"Геооснова: {geojson_path} | источник: {source} | регионов: {len(points)} | границы: {stats.get('line_points', 0)} точек"
    win = WaveSurfaceWindow(html_path, args.title, info)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
