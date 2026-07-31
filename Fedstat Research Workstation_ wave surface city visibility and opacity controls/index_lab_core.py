# -*- coding: utf-8 -*-
"""Core objects and calculations for the inflation impulse index lab.

The GUI can build recipes manually, while automatic selection writes into the
same recipe structure. This keeps manual and automatic workflows compatible.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


ROLE_BODY = "body"
ROLE_ENVIRONMENT = "environment"
ROLE_TARGET = "target"

ROLE_LABELS = {
    ROLE_BODY: "Тело",
    ROLE_ENVIRONMENT: "Среда",
    ROLE_TARGET: "Цель",
}

TRANSFORM_RAW = "raw"
TRANSFORM_PERIOD_CENTERED = "period_centered"
TRANSFORM_PERIOD_ZSCORE = "period_zscore"
TRANSFORM_REGION_DIFF = "region_diff"
TRANSFORM_REGION_PCT = "region_pct"

TRANSFORM_LABELS = {
    TRANSFORM_RAW: "Без преобразования",
    TRANSFORM_PERIOD_CENTERED: "Отклонение от среднего периода",
    TRANSFORM_PERIOD_ZSCORE: "Z-score внутри периода",
    TRANSFORM_REGION_DIFF: "Месячное изменение",
    TRANSFORM_REGION_PCT: "Месячный темп, %",
}

TRANSPORT_DISTANCE = "distance_inverse"
TRANSPORT_SAME_FD = "same_federal_district"
TRANSPORT_DISTANCE_BAND = "distance_band_800"

TRANSPORT_LABELS = {
    TRANSPORT_DISTANCE: "Обратное расстояние",
    TRANSPORT_SAME_FD: "Один федеральный округ",
    TRANSPORT_DISTANCE_BAND: "Близкие регионы до 800 км",
}

APP_DIR = Path(__file__).resolve().parent
REGION_HARMONIZATION_PATH = APP_DIR / "data" / "geo" / "fedstat_region_harmonization.csv"

RU_MONTHS = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}


@dataclass
class FactorSpec:
    factor_id: str
    name: str
    role: str = ROLE_BODY
    source_path: str = ""
    region_column: str = "region"
    period_column: str = "period"
    value_column: str = "value"
    transform: str = TRANSFORM_PERIOD_ZSCORE
    enabled: bool = True
    subtype: str = ""
    source_name: str = ""
    frequency: str = "месяц"
    level: str = "регион"
    units: str = ""
    value_description: str = ""
    period_start: str = ""
    period_end: str = ""
    expected_sign: str = "не задан"
    allowed_lags: str = "0,1,2,3,6"
    quality_status: str = "черновик"
    missing_policy: str = "не проверено"
    passport_status: str = "требует заполнения"
    note: str = ""


@dataclass
class RecipeTerm:
    factor_id: str
    role: str = ROLE_BODY
    weight: float = 1.0
    lag: int = 0
    transform: str = ""


@dataclass
class TransportTerm:
    transport_type: str = TRANSPORT_DISTANCE
    weight: float = 0.3
    lag: int = 1
    power: float = 1.0
    max_distance_km: float = 0.0


@dataclass
class IndexRecipe:
    name: str = "Базовый индекс инфляционного импульса"
    target_factor_id: str = ""
    horizon: int = 1
    body_terms: List[RecipeTerm] = field(default_factory=list)
    environment_terms: List[RecipeTerm] = field(default_factory=list)
    transport_terms: List[TransportTerm] = field(default_factory=list)
    notes: str = ""


@dataclass
class IndexRunResult:
    frame: Any
    metrics: Dict[str, Any]
    messages: List[str] = field(default_factory=list)


def require_pandas() -> None:
    if pd is None:
        raise RuntimeError("Для лаборатории индекса нужен pandas. Установите зависимости из requirements.txt.")


def safe_id(text: str, existing: Iterable[str] = ()) -> str:
    value = str(text or "factor").strip().lower()
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    })
    value = value.translate(table)
    value = re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_") or "factor"
    used = set(existing)
    candidate = value
    idx = 2
    while candidate in used:
        candidate = f"{value}_{idx}"
        idx += 1
    return candidate


def read_csv_table(path: Path) -> Any:
    require_pandas()
    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            return pd.read_csv(path, encoding="utf-8-sig")


def clean_table_columns(df: Any) -> Any:
    df = df.copy()
    df.columns = [str(column).lstrip("\ufeff").strip() for column in df.columns]
    return df


def read_table(path: Path) -> Any:
    require_pandas()
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        return clean_table_columns(pd.read_excel(path))
    return clean_table_columns(read_csv_table(path))


def preview_columns(path: Path) -> List[str]:
    df = read_table(path)
    return [str(c) for c in df.columns]


def normalize_period(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"(\d{4})[-./](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    match = re.search(r"(\d{1,2})[-./](\d{4})", text)
    if match:
        return f"{int(match.group(2)):04d}-{int(match.group(1)):02d}"
    lower = text.lower()
    year_match = re.search(r"(20\d{2}|19\d{2})", lower)
    if year_match:
        year = int(year_match.group(1))
        for name, month in RU_MONTHS.items():
            if name in lower:
                return f"{year:04d}-{month:02d}"
    if pd is not None:
        try:
            parsed = pd.to_datetime(text, errors="raise", dayfirst=True)
            return f"{int(parsed.year):04d}-{int(parsed.month):02d}"
        except Exception:
            pass
    return text


def normalize_region(text: Any) -> str:
    return " ".join(str(text).replace("ё", "е").strip().split())


def region_match_key(text: Any) -> str:
    value = normalize_region(text).replace("–", "-").replace("—", "-").lower()
    value = re.sub(r"\s*-\s*", "-", value)
    return re.sub(r"\s+", " ", value).strip()


def load_region_harmonization() -> Tuple[Dict[str, str], set[str]]:
    mapping: Dict[str, str] = {}
    excluded: set[str] = set()
    if not REGION_HARMONIZATION_PATH.exists():
        return mapping, excluded
    with open(REGION_HARMONIZATION_PATH, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            fedstat_name = normalize_region(row.get("fedstat_name") or "")
            if not fedstat_name:
                continue
            key = region_match_key(fedstat_name)
            include = str(row.get("use_in_subject_panel") or "").strip().lower() in {"yes", "true", "1", "да"}
            canonical = normalize_region(row.get("canonical_region") or "")
            if include and canonical:
                mapping[key] = canonical
            else:
                excluded.add(key)
    return mapping, excluded


def apply_region_harmonization(df: Any) -> Any:
    mapping, excluded = load_region_harmonization()
    if not mapping and not excluded:
        return df
    out = df.copy()
    out["_region_key"] = out["region"].map(region_match_key)
    if excluded:
        out = out[~out["_region_key"].isin(excluded)].copy()
    if mapping:
        out["region"] = out.apply(lambda row: mapping.get(row["_region_key"], row["region"]), axis=1)
    return out.drop(columns=["_region_key"])


def load_factor_frame(factor: FactorSpec) -> Any:
    require_pandas()
    path = Path(factor.source_path)
    if not path.exists():
        raise RuntimeError(f"Файл фактора не найден: {path}")
    df = read_table(path)
    missing = [c for c in [factor.region_column, factor.period_column, factor.value_column] if c not in df.columns]
    if missing:
        raise RuntimeError(f"В факторе {factor.factor_id} нет колонок: {', '.join(missing)}")
    out = df[[factor.region_column, factor.period_column, factor.value_column]].copy()
    out.columns = ["region", "period", "value"]
    out["region"] = out["region"].map(normalize_region)
    out["period"] = out["period"].map(normalize_period)
    out["value"] = pd.to_numeric(out["value"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    out = out.dropna(subset=["region", "period", "value"])
    out = out[out["period"].astype(str).str.len() > 0]
    out = apply_region_harmonization(out)
    out["factor_id"] = factor.factor_id
    out = out.groupby(["region", "period", "factor_id"], as_index=False)["value"].mean()
    out = out[["region", "period", "factor_id", "value"]]
    return out


def build_panel(factors: List[FactorSpec]) -> Any:
    require_pandas()
    frames = [load_factor_frame(f) for f in factors if f.enabled]
    if not frames:
        return pd.DataFrame(columns=["region", "period", "factor_id", "value"])
    return pd.concat(frames, ignore_index=True)


def sort_panel(df: Any) -> Any:
    return df.sort_values(["region", "period"]).reset_index(drop=True)


def transform_values(df: Any, transform: str) -> Any:
    require_pandas()
    out = sort_panel(df.copy())
    transform = transform or TRANSFORM_RAW
    if transform == TRANSFORM_RAW:
        return out
    if transform == TRANSFORM_PERIOD_CENTERED:
        out["value"] = out["value"] - out.groupby("period")["value"].transform("mean")
        return out
    if transform == TRANSFORM_PERIOD_ZSCORE:
        mean = out.groupby("period")["value"].transform("mean")
        std = out.groupby("period")["value"].transform("std").replace(0, np.nan if np is not None else None)
        out["value"] = (out["value"] - mean) / std
        return out.dropna(subset=["value"])
    if transform == TRANSFORM_REGION_DIFF:
        out["value"] = out.groupby("region")["value"].diff()
        return out.dropna(subset=["value"])
    if transform == TRANSFORM_REGION_PCT:
        out["value"] = out.groupby("region")["value"].pct_change() * 100.0
        return out.replace([float("inf"), float("-inf")], float("nan")).dropna(subset=["value"])
    return out


def apply_lag(df: Any, lag: int) -> Any:
    out = sort_panel(df.copy())
    lag = max(0, int(lag or 0))
    if lag:
        out["value"] = out.groupby("region")["value"].shift(lag)
    return out.dropna(subset=["value"])


def term_series(panel: Any, factors_by_id: Dict[str, FactorSpec], term: RecipeTerm) -> Any:
    require_pandas()
    factor = factors_by_id.get(term.factor_id)
    if factor is None:
        raise RuntimeError(f"Фактор не найден в каталоге: {term.factor_id}")
    df = panel[panel["factor_id"] == term.factor_id][["region", "period", "value"]].copy()
    if df.empty:
        return pd.DataFrame(columns=["region", "period", "value"])
    df = transform_values(df, term.transform or factor.transform)
    df = apply_lag(df, term.lag)
    df["value"] = df["value"] * float(term.weight)
    return df


def combine_terms(panel: Any, factors_by_id: Dict[str, FactorSpec], terms: List[RecipeTerm], component_name: str) -> Any:
    require_pandas()
    rows = []
    for term in terms:
        df = term_series(panel, factors_by_id, term)
        if not df.empty:
            rows.append(df)
    if not rows:
        return pd.DataFrame(columns=["region", "period", component_name])
    combined = pd.concat(rows, ignore_index=True)
    return combined.groupby(["region", "period"], as_index=False)["value"].sum().rename(columns={"value": component_name})


def read_region_reference(path: Path) -> Any:
    require_pandas()
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            region = normalize_region(row.get("canonical_region") or row.get("geo_name") or row.get("fedstat_name") or row.get("region") or row.get("name") or "")
            if not region or "федеральный округ" in region.lower() or region == "Российская Федерация":
                continue
            try:
                lat = float(str(row.get("capital_lat") or row.get("lat") or "").replace(",", "."))
                lon = float(str(row.get("capital_lon") or row.get("lon") or "").replace(",", "."))
            except Exception:
                continue
            rows.append({
                "region": region,
                "federal_district": row.get("federal_district") or "",
                "lat": lat,
                "lon": lon,
            })
    return pd.DataFrame(rows).drop_duplicates(["region"], keep="first")


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    lon1_r, lat1_r, lon2_r, lat2_r = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2_r - lon1_r
    dlat = lat2_r - lat1_r
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(a))


def build_transport_matrix(region_reference: Any, term: TransportTerm) -> Any:
    require_pandas()
    rows: List[Dict[str, Any]] = []
    refs = region_reference.to_dict("records")
    max_distance = float(term.max_distance_km or 0.0)
    power = max(0.1, float(term.power or 1.0))
    for target in refs:
        weights: List[Tuple[str, float]] = []
        for source in refs:
            if source["region"] == target["region"]:
                continue
            dist = haversine_km(source["lon"], source["lat"], target["lon"], target["lat"])
            weight = 0.0
            if term.transport_type == TRANSPORT_DISTANCE:
                if max_distance <= 0 or dist <= max_distance:
                    weight = 1.0 / max(dist, 1.0) ** power
            elif term.transport_type == TRANSPORT_SAME_FD:
                if source.get("federal_district") and source.get("federal_district") == target.get("federal_district"):
                    weight = 1.0
            elif term.transport_type == TRANSPORT_DISTANCE_BAND:
                limit = max_distance or 800.0
                if dist <= limit:
                    weight = 1.0
            if weight > 0:
                weights.append((source["region"], weight))
        total = sum(w for _, w in weights)
        if total <= 0:
            continue
        for source_region, weight in weights:
            rows.append({
                "source_region": source_region,
                "target_region": target["region"],
                "weight": weight / total,
            })
    return pd.DataFrame(rows)


def spatial_lag(signal: Any, matrix: Any, term: TransportTerm) -> Any:
    require_pandas()
    if signal.empty or matrix.empty:
        return pd.DataFrame(columns=["region", "period", "value"])
    shifted = signal[["region", "period", "value"]].copy()
    shifted = apply_lag(shifted, term.lag)
    shifted = shifted.rename(columns={"region": "source_region", "value": "source_value"})
    merged = matrix.merge(shifted, on="source_region", how="inner")
    merged["value"] = merged["source_value"] * merged["weight"] * float(term.weight)
    return merged.groupby(["target_region", "period"], as_index=False)["value"].sum().rename(columns={"target_region": "region"})


def _merge_component(base: Any, component: Any, column: str) -> Any:
    require_pandas()
    if component.empty:
        base[column] = 0.0
        return base
    if base.empty:
        out = component.copy()
    else:
        out = base.merge(component, on=["region", "period"], how="outer")
    out[column] = out[column].fillna(0.0)
    return out


def compute_index(recipe: IndexRecipe, factors: List[FactorSpec], region_reference_path: Path) -> IndexRunResult:
    require_pandas()
    enabled = [f for f in factors if f.enabled]
    factors_by_id = {f.factor_id: f for f in enabled}
    messages: List[str] = []
    panel = build_panel(enabled)
    if panel.empty:
        raise RuntimeError("Нет загруженных факторов. Добавьте хотя бы один CSV/XLSX-фактор.")

    body = combine_terms(panel, factors_by_id, recipe.body_terms, "body")
    environment = combine_terms(panel, factors_by_id, recipe.environment_terms, "environment")
    frame = pd.DataFrame(columns=["region", "period"])
    frame = _merge_component(frame, body, "body")
    frame = _merge_component(frame, environment, "environment")

    transport_total = pd.DataFrame(columns=["region", "period", "transport"])
    if recipe.transport_terms and not body.empty:
        region_reference = read_region_reference(region_reference_path)
        for term in recipe.transport_terms:
            matrix = build_transport_matrix(region_reference, term)
            transported = spatial_lag(body.rename(columns={"body": "value"}), matrix, term)
            if transported.empty:
                continue
            transported = transported.rename(columns={"value": "transport"})
            transport_total = pd.concat([transport_total, transported], ignore_index=True)
        if not transport_total.empty:
            transport_total = transport_total.groupby(["region", "period"], as_index=False)["transport"].sum()
    frame = _merge_component(frame, transport_total, "transport")
    for col in ["body", "environment", "transport"]:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = frame[col].fillna(0.0)
    frame["index"] = frame["body"] + frame["environment"] + frame["transport"]

    metrics: Dict[str, Any] = {
        "recipe": recipe.name,
        "rows": int(len(frame)),
        "correlation": None,
        "rmse_z": None,
        "direction_accuracy": None,
        "n_eval": 0,
    }

    if recipe.target_factor_id:
        target_factor = factors_by_id.get(recipe.target_factor_id)
        if target_factor is None:
            messages.append(f"Целевой фактор не найден или отключен: {recipe.target_factor_id}")
        else:
            target = panel[panel["factor_id"] == recipe.target_factor_id][["region", "period", "value"]].copy()
            target = transform_values(target, target_factor.transform)
            target = sort_panel(target)
            horizon = max(0, int(recipe.horizon or 0))
            if horizon:
                target["target_future"] = target.groupby("region")["value"].shift(-horizon)
            else:
                target["target_future"] = target["value"]
            target = target.dropna(subset=["target_future"])[["region", "period", "target_future"]]
            frame = frame.merge(target, on=["region", "period"], how="left")
            eval_df = frame.dropna(subset=["index", "target_future"])
            metrics["n_eval"] = int(len(eval_df))
            if len(eval_df) >= 3:
                corr = float(eval_df["index"].corr(eval_df["target_future"]))
                x = eval_df["index"]
                y = eval_df["target_future"]
                x_std = x.std()
                y_std = y.std()
                if x_std and y_std:
                    xz = (x - x.mean()) / x_std
                    yz = (y - y.mean()) / y_std
                    metrics["rmse_z"] = float(((xz - yz) ** 2).mean() ** 0.5)
                metrics["correlation"] = corr
                metrics["direction_accuracy"] = float((np.sign(x) == np.sign(y)).mean()) if np is not None else None
    return IndexRunResult(sort_panel(frame), metrics, messages)


def recipe_to_dict(recipe: IndexRecipe) -> Dict[str, Any]:
    return asdict(recipe)


def recipe_from_dict(data: Dict[str, Any]) -> IndexRecipe:
    return IndexRecipe(
        name=data.get("name", "Базовый индекс инфляционного импульса"),
        target_factor_id=data.get("target_factor_id", ""),
        horizon=int(data.get("horizon", 1) or 1),
        body_terms=[RecipeTerm(**x) for x in data.get("body_terms", [])],
        environment_terms=[RecipeTerm(**x) for x in data.get("environment_terms", [])],
        transport_terms=[TransportTerm(**x) for x in data.get("transport_terms", [])],
        notes=data.get("notes", ""),
    )


def factors_to_dict(factors: List[FactorSpec]) -> List[Dict[str, Any]]:
    return [asdict(f) for f in factors]


def factors_from_dict(data: List[Dict[str, Any]]) -> List[FactorSpec]:
    allowed = {item.name for item in fields(FactorSpec)}
    return [FactorSpec(**{key: value for key, value in item.items() if key in allowed}) for item in data]


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def auto_build_recipe(
    factors: List[FactorSpec],
    target_factor_id: str,
    horizon: int,
    region_reference_path: Path,
    max_lag: int = 6,
    max_terms: int = 5,
) -> Tuple[IndexRecipe, Any, Dict[str, Any]]:
    require_pandas()
    if not target_factor_id:
        raise RuntimeError("Для автоподбора нужно выбрать целевой фактор.")
    target_factor = next((factor for factor in factors if factor.factor_id == target_factor_id and factor.enabled), None)
    target_source = str(Path(target_factor.source_path)).replace("\\", "/").casefold() if target_factor else ""

    scoreboard_rows: List[Dict[str, Any]] = []
    candidate_terms: List[Tuple[float, RecipeTerm, Dict[str, Any]]] = []
    for factor in factors:
        if not factor.enabled or factor.factor_id == target_factor_id or factor.role == ROLE_TARGET:
            continue
        if target_source and str(Path(factor.source_path)).replace("\\", "/").casefold() == target_source:
            continue
        role = ROLE_ENVIRONMENT if factor.role == ROLE_ENVIRONMENT else ROLE_BODY
        for lag in range(0, max_lag + 1):
            term = RecipeTerm(factor_id=factor.factor_id, role=role, weight=1.0, lag=lag, transform=factor.transform)
            recipe = IndexRecipe(
                name=f"Тест: {factor.factor_id}, lag={lag}",
                target_factor_id=target_factor_id,
                horizon=horizon,
                body_terms=[term] if role == ROLE_BODY else [],
                environment_terms=[term] if role == ROLE_ENVIRONMENT else [],
            )
            try:
                result = compute_index(recipe, factors, region_reference_path)
            except Exception:
                continue
            corr = result.metrics.get("correlation")
            score = abs(float(corr)) if corr is not None else 0.0
            row = {
                "candidate": factor.factor_id,
                "role": role,
                "lag": lag,
                "transport": "",
                "correlation": corr,
                "n_eval": result.metrics.get("n_eval", 0),
                "score": score,
            }
            scoreboard_rows.append(row)
            if score > 0:
                candidate_terms.append((score, term, result.metrics))

    candidate_terms.sort(key=lambda x: x[0], reverse=True)
    selected = candidate_terms[: max(1, int(max_terms or 1))]
    max_score = selected[0][0] if selected else 1.0
    body_terms: List[RecipeTerm] = []
    environment_terms: List[RecipeTerm] = []
    for score, term, metrics in selected:
        corr = metrics.get("correlation") or 0.0
        signed_weight = float(corr) / max_score if max_score else float(corr)
        selected_term = RecipeTerm(
            factor_id=term.factor_id,
            role=term.role,
            weight=round(signed_weight, 4),
            lag=term.lag,
            transform=term.transform,
        )
        if selected_term.role == ROLE_ENVIRONMENT:
            environment_terms.append(selected_term)
        else:
            body_terms.append(selected_term)

    recipe = IndexRecipe(
        name="Автоподбор индекса инфляционного импульса",
        target_factor_id=target_factor_id,
        horizon=horizon,
        body_terms=body_terms,
        environment_terms=environment_terms,
    )
    best_result = compute_index(recipe, factors, region_reference_path)
    best_score = abs(best_result.metrics.get("correlation") or 0.0)

    for transport_type in [TRANSPORT_DISTANCE, TRANSPORT_SAME_FD, TRANSPORT_DISTANCE_BAND]:
        for lag in range(1, max_lag + 1):
            candidate = recipe_from_dict(recipe_to_dict(recipe))
            candidate.transport_terms.append(TransportTerm(transport_type=transport_type, weight=0.35, lag=lag))
            try:
                result = compute_index(candidate, factors, region_reference_path)
            except Exception:
                continue
            corr = result.metrics.get("correlation")
            score = abs(float(corr)) if corr is not None else 0.0
            scoreboard_rows.append({
                "candidate": "recipe_plus_transport",
                "role": "transport",
                "lag": lag,
                "transport": transport_type,
                "correlation": corr,
                "n_eval": result.metrics.get("n_eval", 0),
                "score": score,
            })
            if score > best_score:
                recipe = candidate
                best_result = result
                best_score = score

    scoreboard = pd.DataFrame(scoreboard_rows).sort_values("score", ascending=False) if scoreboard_rows else pd.DataFrame()
    return recipe, scoreboard, best_result.metrics
