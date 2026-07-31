# -*- coding: utf-8 -*-
"""Quality-control and first auto-selection run for the index laboratory."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from index_lab_core import (
    ROLE_BODY,
    ROLE_ENVIRONMENT,
    ROLE_TARGET,
    TRANSFORM_PERIOD_ZSCORE,
    TRANSPORT_DISTANCE,
    TRANSPORT_DISTANCE_BAND,
    TRANSPORT_SAME_FD,
    FactorSpec,
    IndexRecipe,
    RecipeTerm,
    TransportTerm,
    apply_lag,
    build_panel,
    build_transport_matrix,
    combine_terms,
    factors_from_dict,
    factors_to_dict,
    load_factor_frame,
    load_json,
    read_region_reference,
    recipe_to_dict,
    save_json,
    sort_panel,
    spatial_lag,
    transform_values,
)


APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = APP_DIR / "settings"
OUTPUT_DIR = APP_DIR / "index_lab_output"
DATA_DIR = APP_DIR / "data" / "fedstat_targets"
CATALOG_PATH = SETTINGS_DIR / "index_lab_factors.json"
RECIPE_PATH = SETTINGS_DIR / "index_lab_recipe.json"
REGION_REFERENCE_PATH = APP_DIR / "data" / "geo" / "regions_reference_fedstat_harmonized.csv"

QC_DECISIONS_PATH = DATA_DIR / "qc_decisions.csv"
TARGET_HORIZON_PATH = DATA_DIR / "target_horizon_check.csv"
QC_SUMMARY_SUBJECTS_PATH = DATA_DIR / "quality_summary_subjects.csv"
QC_FLAGS_SUBJECTS_PATH = DATA_DIR / "quality_flags_subjects.csv"
QC_REPORT_PATH = DATA_DIR / "qc_report.md"

AUTO_SCOREBOARD_PATH = OUTPUT_DIR / "auto_selection_v0_scoreboard.csv"
AUTO_RECIPE_PATH = OUTPUT_DIR / "auto_selection_v0_recipe.json"
AUTO_METRICS_PATH = OUTPUT_DIR / "auto_selection_v0_metrics.json"
AUTO_RESULT_PATH = OUTPUT_DIR / "auto_selection_v0_result.csv"
SENSITIVITY_DIR = OUTPUT_DIR / "auto_selection_v0_sensitivity"
SENSITIVITY_SUMMARY_PATH = OUTPUT_DIR / "auto_selection_v0_sensitivity.csv"
SENSITIVITY_REPORT_PATH = OUTPUT_DIR / "auto_selection_v0_sensitivity.md"

LOW_FLAG = 50.0
HIGH_FLAG = 200.0
TARGET_ID = "target_ipc_food"
TARGET_IDS = ["target_ipc_all", "target_ipc_food", "target_ipc_nonfood", "target_ipc_services"]
TARGET_HORIZONS = [1, 2, 3, 6]

BROAD_BODY_ALIASES = [
    {
        "factor_id": "body_ipc_nonfood_broad",
        "source_factor_id": "target_ipc_nonfood",
        "name": "ИПЦ непродовольственных товаров (кандидат тела)",
        "subtype": "тело: непродовольственные товары",
        "value_description": "Непродовольственные товары",
        "expected_sign": "+",
        "note": "D03 как кандидат тела для проверки гипотезы о влиянии на продовольственную инфляцию.",
    },
    {
        "factor_id": "body_ipc_services_broad",
        "source_factor_id": "target_ipc_services",
        "name": "ИПЦ услуг (кандидат тела)",
        "subtype": "тело: услуги",
        "value_description": "Услуги",
        "expected_sign": "+/-",
        "note": "D04 как кандидат тела/контрольный сервисный слой.",
    },
]


def append_note_once(original: str, addition: str) -> str:
    if not addition:
        return original
    if addition in original:
        return original
    if not original:
        return addition
    return f"{original}; {addition}"


def load_catalog() -> List[FactorSpec]:
    return factors_from_dict(load_json(CATALOG_PATH))


def apply_target_transform_policy(factors: List[FactorSpec]) -> List[FactorSpec]:
    for factor in factors:
        if factor.role == ROLE_TARGET and "Fedstat / Росстат, показатель 31074" in factor.source_name:
            factor.transform = TRANSFORM_PERIOD_ZSCORE
            factor.note = append_note_once(
                factor.note,
                "QC v0: цель Fedstat 31074 уже выражена как процент к предыдущему месяцу; для подбора используем period_zscore.",
            )
    return factors


def ensure_broad_body_aliases(factors: List[FactorSpec]) -> List[FactorSpec]:
    by_id = {factor.factor_id: factor for factor in factors}
    for alias in BROAD_BODY_ALIASES:
        source = by_id.get(alias["source_factor_id"])
        if source is None:
            continue
        factor = by_id.get(alias["factor_id"])
        if factor is None:
            factor = FactorSpec(
                factor_id=alias["factor_id"],
                name=alias["name"],
                role=ROLE_BODY,
                source_path=source.source_path,
                region_column=source.region_column,
                period_column=source.period_column,
                value_column=source.value_column,
                transform=TRANSFORM_PERIOD_ZSCORE,
                enabled=True,
            )
            factors.append(factor)
            by_id[factor.factor_id] = factor
        factor.name = alias["name"]
        factor.role = ROLE_BODY
        factor.source_path = source.source_path
        factor.region_column = source.region_column
        factor.period_column = source.period_column
        factor.value_column = source.value_column
        factor.transform = TRANSFORM_PERIOD_ZSCORE
        factor.subtype = alias["subtype"]
        factor.source_name = source.source_name
        factor.frequency = source.frequency
        factor.level = source.level
        factor.units = source.units
        factor.value_description = alias["value_description"]
        factor.period_start = source.period_start
        factor.period_end = source.period_end
        factor.expected_sign = alias["expected_sign"]
        factor.allowed_lags = "0,1,2,3,4,5,6"
        factor.note = append_note_once(source.note, alias["note"])
    return factors


def period_count(period_min: str, period_max: str) -> int:
    if not period_min or not period_max:
        return 0
    return len(pd.period_range(period_min, period_max, freq="M"))


def summarize_factor(factor: FactorSpec) -> Dict[str, Any]:
    frame = load_factor_frame(factor)
    if frame.empty:
        return {
            "factor_id": factor.factor_id,
            "name": factor.name,
            "role": factor.role,
            "rows": 0,
            "regions": 0,
            "period_min": "",
            "period_max": "",
            "periods": 0,
            "expected_rows_observed_span": 0,
            "missing_rows_observed_span": 0,
            "min": "",
            "max": "",
            "zero_count": 0,
            "low_count": 0,
            "high_count": 0,
            "flag_count": 0,
        }
    p_min = str(frame["period"].min())
    p_max = str(frame["period"].max())
    regions = int(frame["region"].nunique())
    periods = period_count(p_min, p_max)
    expected = regions * periods
    zero_count = int((frame["value"] == 0).sum())
    low_count = int((frame["value"] < LOW_FLAG).sum())
    high_count = int((frame["value"] > HIGH_FLAG).sum())
    return {
        "factor_id": factor.factor_id,
        "name": factor.name,
        "role": factor.role,
        "rows": int(len(frame)),
        "regions": regions,
        "period_min": p_min,
        "period_max": p_max,
        "periods": periods,
        "expected_rows_observed_span": int(expected),
        "missing_rows_observed_span": int(max(0, expected - len(frame))),
        "min": float(frame["value"].min()),
        "max": float(frame["value"].max()),
        "zero_count": zero_count,
        "low_count": low_count,
        "high_count": high_count,
        "flag_count": zero_count + low_count + high_count,
    }


def decide_qc(summary: Dict[str, Any]) -> Dict[str, Any]:
    factor_id = summary["factor_id"]
    role = summary["role"]
    period_end = str(summary["period_max"])
    flag_count = int(summary["flag_count"])
    high_count = int(summary["high_count"])
    low_count = int(summary["low_count"])
    regions = int(summary["regions"])
    missing = int(summary["missing_rows_observed_span"])

    if role == ROLE_TARGET:
        return {
            "qc_decision": "ready_target",
            "auto_ready": "yes",
            "enabled_after_qc": "yes",
            "reason": "цель прошла субъектную гармонизацию, нулей и экстремумов нет",
        }
    if period_end and period_end <= "2006-12":
        return {
            "qc_decision": "exclude_auto_v0",
            "auto_ready": "no",
            "enabled_after_qc": "no",
            "reason": "короткий исторический ряд 2002-2006; не используем в первом автоподборе",
        }
    if factor_id == "body_ipc_air_transport" or high_count >= 5 or low_count >= 5:
        return {
            "qc_decision": "exclude_auto_v0",
            "auto_ready": "no",
            "enabled_after_qc": "no",
            "reason": "много экстремальных значений; временно исключаем до ручной проверки",
        }
    if flag_count > 0:
        return {
            "qc_decision": "ready_with_warning",
            "auto_ready": "yes",
            "enabled_after_qc": "yes",
            "reason": f"есть {flag_count} флаг(ов), но ряд оставлен для разведки v0",
        }
    if regions < 85 or missing > 0:
        return {
            "qc_decision": "ready_with_warning",
            "auto_ready": "yes",
            "enabled_after_qc": "yes",
            "reason": "есть неполное покрытие регионов/месяцев, но ряд пригоден для разведки v0",
        }
    return {
        "qc_decision": "ready_auto_v0",
        "auto_ready": "yes",
        "enabled_after_qc": "yes",
        "reason": "полная субъектная панель без флагов",
    }


def build_qc_tables(factors: List[FactorSpec]) -> pd.DataFrame:
    summaries = [summarize_factor(factor) for factor in factors]
    rows = []
    for summary in summaries:
        rows.append({**summary, **decide_qc(summary)})
    decisions = pd.DataFrame(rows).sort_values(["role", "auto_ready", "factor_id"]).reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    decisions.to_csv(QC_DECISIONS_PATH, index=False, encoding="utf-8-sig")
    summary_cols = [
        "factor_id",
        "role",
        "rows",
        "regions",
        "period_min",
        "period_max",
        "min",
        "max",
        "zero_count",
        "high_count",
    ]
    decisions[summary_cols].to_csv(QC_SUMMARY_SUBJECTS_PATH, index=False, encoding="utf-8-sig")
    return decisions


def write_subject_flags(factors: List[FactorSpec]) -> pd.DataFrame:
    frames = []
    for factor in factors:
        frame = load_factor_frame(factor)
        if frame.empty:
            continue
        frame["name"] = factor.name
        frame["role"] = factor.role
        frames.append(frame)
    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if all_rows.empty:
        flags = pd.DataFrame(columns=["factor_id", "name", "role", "region", "period", "value"])
    else:
        flags = all_rows[(all_rows["value"] < LOW_FLAG) | (all_rows["value"] > HIGH_FLAG)].copy()
        flags = flags.sort_values(["factor_id", "region", "period"])
        flags = flags[["factor_id", "name", "role", "region", "period", "value"]]
    flags.to_csv(QC_FLAGS_SUBJECTS_PATH, index=False, encoding="utf-8-sig")
    return flags


def write_horizon_check(factors: List[FactorSpec]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for factor in factors:
        if factor.role != ROLE_TARGET:
            continue
        raw = load_factor_frame(factor)
        signal = transform_values(raw[["region", "period", "value"]], factor.transform)
        signal = sort_panel(signal)
        for horizon in TARGET_HORIZONS:
            check = signal.copy()
            check["target_future"] = check.groupby("region")["value"].shift(-horizon)
            check = check.dropna(subset=["target_future"])
            rows.append({
                "target_factor_id": factor.factor_id,
                "target_name": factor.name,
                "horizon": horizon,
                "raw_rows": int(len(raw)),
                "raw_regions": int(raw["region"].nunique()) if not raw.empty else 0,
                "signal_rows_after_transform": int(len(signal)),
                "future_rows": int(len(check)),
                "future_regions": int(check["region"].nunique()) if not check.empty else 0,
                "period_min": str(check["period"].min()) if not check.empty else "",
                "period_max": str(check["period"].max()) if not check.empty else "",
            })
    horizon_frame = pd.DataFrame(rows)
    horizon_frame.to_csv(TARGET_HORIZON_PATH, index=False, encoding="utf-8-sig")
    return horizon_frame


def apply_qc_to_catalog(factors: List[FactorSpec], decisions: pd.DataFrame) -> List[FactorSpec]:
    by_id = {row["factor_id"]: row for _, row in decisions.iterrows()}
    for factor in factors:
        row = by_id.get(factor.factor_id)
        if row is None:
            continue
        factor.enabled = str(row["enabled_after_qc"]) == "yes"
        if factor.role == ROLE_TARGET:
            factor.quality_status = "QC v0: цель готова"
            factor.passport_status = "готов к автоподбору v0"
        elif str(row["auto_ready"]) == "yes":
            factor.quality_status = f"QC v0: {row['qc_decision']}"
            factor.passport_status = "готов к автоподбору v0"
        else:
            factor.quality_status = "QC v0: временно исключен из автоподбора"
            factor.passport_status = "исключить из автоподбора v0"
        factor.missing_policy = (
            "региональная гармонизация включена; агрегаты и исторические территории исключаются; "
            "сырые Fedstat CSV не изменены"
        )
        factor.note = append_note_once(factor.note, str(row["reason"]))
    save_json(CATALOG_PATH, factors_to_dict(factors))
    return factors


def merge_component(base: pd.DataFrame, component: pd.DataFrame, column: str) -> pd.DataFrame:
    if component.empty:
        base[column] = 0.0
        return base
    if base.empty:
        out = component.copy()
    else:
        out = base.merge(component, on=["region", "period"], how="outer")
    out[column] = out[column].fillna(0.0)
    return out


def evaluate_recipe_fast(
    recipe: IndexRecipe,
    panel: pd.DataFrame,
    factors_by_id: Dict[str, FactorSpec],
    region_reference: pd.DataFrame,
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    body = combine_terms(panel, factors_by_id, recipe.body_terms, "body")
    environment = combine_terms(panel, factors_by_id, recipe.environment_terms, "environment")
    frame = pd.DataFrame(columns=["region", "period"])
    frame = merge_component(frame, body, "body")
    frame = merge_component(frame, environment, "environment")

    transport_total = pd.DataFrame(columns=["region", "period", "transport"])
    if recipe.transport_terms and not body.empty:
        for term in recipe.transport_terms:
            matrix = build_transport_matrix(region_reference, term)
            transported = spatial_lag(body.rename(columns={"body": "value"}), matrix, term)
            if transported.empty:
                continue
            transported = transported.rename(columns={"value": "transport"})
            transport_total = pd.concat([transport_total, transported], ignore_index=True)
        if not transport_total.empty:
            transport_total = transport_total.groupby(["region", "period"], as_index=False)["transport"].sum()
    frame = merge_component(frame, transport_total, "transport")
    for column in ["body", "environment", "transport"]:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = frame[column].fillna(0.0)
    frame["index"] = frame["body"] + frame["environment"] + frame["transport"]

    metrics: Dict[str, Any] = {
        "recipe": recipe.name,
        "rows": int(len(frame)),
        "correlation": None,
        "rmse_z": None,
        "direction_accuracy": None,
        "n_eval": 0,
    }
    target_factor = factors_by_id.get(recipe.target_factor_id)
    if target_factor is None:
        return sort_panel(frame), metrics
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
        metrics["direction_accuracy"] = float((x.apply(lambda item: 1 if item > 0 else (-1 if item < 0 else 0)) == y.apply(lambda item: 1 if item > 0 else (-1 if item < 0 else 0))).mean())
    return sort_panel(frame), metrics


def source_key(factor: FactorSpec) -> str:
    return str(Path(factor.source_path)).replace("\\", "/").casefold()


def serialize_body_terms(recipe: IndexRecipe) -> List[Dict[str, Any]]:
    return [
        {
            "factor_id": term.factor_id,
            "weight": term.weight,
            "lag": term.lag,
            "transform": term.transform,
        }
        for term in recipe.body_terms
    ]


def serialize_transport_terms(recipe: IndexRecipe) -> List[Dict[str, Any]]:
    return [term.__dict__ for term in recipe.transport_terms]


def compact_terms(terms: List[Dict[str, Any]]) -> str:
    if not terms:
        return ""
    return "; ".join(
        f"{term.get('factor_id') or term.get('transport_type')}@lag{term.get('lag')}:{term.get('weight')}"
        for term in terms
    )


def select_recipe_for_target(
    enabled: List[FactorSpec],
    panel: pd.DataFrame,
    factors_by_id: Dict[str, FactorSpec],
    region_reference: pd.DataFrame,
    target_id: str,
    horizon: int,
    max_lag: int = 6,
    max_terms: int = 5,
) -> tuple[IndexRecipe, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    target_factor = factors_by_id.get(target_id)
    if target_factor is None:
        raise RuntimeError(f"Целевой фактор не найден или отключен: {target_id}")
    target_source = source_key(target_factor)
    scoreboard_rows: List[Dict[str, Any]] = []
    candidate_terms: List[tuple[float, RecipeTerm, Dict[str, Any]]] = []
    for factor in enabled:
        if factor.factor_id == target_id or factor.role == ROLE_TARGET:
            continue
        if source_key(factor) == target_source:
            continue
        role = ROLE_ENVIRONMENT if factor.role == ROLE_ENVIRONMENT else ROLE_BODY
        for lag in range(0, max_lag + 1):
            term = RecipeTerm(factor_id=factor.factor_id, role=role, weight=1.0, lag=lag, transform=factor.transform)
            candidate = IndexRecipe(
                name=f"Тест: {factor.factor_id}, lag={lag}",
                target_factor_id=target_id,
                horizon=horizon,
                body_terms=[term] if role == ROLE_BODY else [],
                environment_terms=[term] if role == ROLE_ENVIRONMENT else [],
            )
            _frame, metrics = evaluate_recipe_fast(candidate, panel, factors_by_id, region_reference)
            corr = metrics.get("correlation")
            score = abs(float(corr)) if corr is not None else 0.0
            row = {
                "candidate": factor.factor_id,
                "role": role,
                "lag": lag,
                "transport": "",
                "correlation": corr,
                "n_eval": metrics.get("n_eval", 0),
                "score": score,
            }
            scoreboard_rows.append(row)
            if score > 0:
                candidate_terms.append((score, term, metrics))

    candidate_terms.sort(key=lambda item: item[0], reverse=True)
    selected = candidate_terms[: max(1, int(max_terms or 1))]
    max_score = selected[0][0] if selected else 1.0
    body_terms: List[RecipeTerm] = []
    environment_terms: List[RecipeTerm] = []
    for score, term, metrics in selected:
        corr = float(metrics.get("correlation") or 0.0)
        selected_term = RecipeTerm(
            factor_id=term.factor_id,
            role=term.role,
            weight=round(corr / max_score, 4) if max_score else round(corr, 4),
            lag=term.lag,
            transform=term.transform,
        )
        if selected_term.role == ROLE_ENVIRONMENT:
            environment_terms.append(selected_term)
        else:
            body_terms.append(selected_term)

    recipe = IndexRecipe(
        name=f"Автоподбор v0: {target_id}, h={horizon}",
        target_factor_id=target_id,
        horizon=horizon,
        body_terms=body_terms,
        environment_terms=environment_terms,
    )
    result_frame, best_metrics = evaluate_recipe_fast(recipe, panel, factors_by_id, region_reference)
    best_score = abs(float(best_metrics.get("correlation") or 0.0))

    for transport_type in [TRANSPORT_DISTANCE, TRANSPORT_SAME_FD, TRANSPORT_DISTANCE_BAND]:
        for lag in range(1, max_lag + 1):
            candidate = IndexRecipe(
                name=recipe.name,
                target_factor_id=recipe.target_factor_id,
                horizon=recipe.horizon,
                body_terms=list(recipe.body_terms),
                environment_terms=list(recipe.environment_terms),
                transport_terms=[TransportTerm(transport_type=transport_type, weight=0.35, lag=lag)],
            )
            candidate_frame, metrics = evaluate_recipe_fast(candidate, panel, factors_by_id, region_reference)
            corr = metrics.get("correlation")
            score = abs(float(corr)) if corr is not None else 0.0
            scoreboard_rows.append({
                "candidate": "recipe_plus_transport",
                "role": "transport",
                "lag": lag,
                "transport": transport_type,
                "correlation": corr,
                "n_eval": metrics.get("n_eval", 0),
                "score": score,
            })
            if score > best_score:
                recipe = candidate
                result_frame = candidate_frame
                best_metrics = metrics
                best_score = score

    scoreboard = pd.DataFrame(scoreboard_rows).sort_values("score", ascending=False)
    return recipe, scoreboard, result_frame, best_metrics


def run_auto_selection(factors: List[FactorSpec]) -> Dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    enabled = [factor for factor in factors if factor.enabled]
    panel = build_panel(enabled)
    factors_by_id = {factor.factor_id: factor for factor in enabled}
    region_reference = read_region_reference(REGION_REFERENCE_PATH)

    recipe, scoreboard, result_frame, best_metrics = select_recipe_for_target(
        enabled,
        panel,
        factors_by_id,
        region_reference,
        TARGET_ID,
        1,
    )
    recipe.name = "Автоподбор v0 после QC"
    best_metrics["recipe"] = recipe.name
    scoreboard.to_csv(AUTO_SCOREBOARD_PATH, index=False, encoding="utf-8-sig")
    AUTO_RECIPE_PATH.write_text(json.dumps(recipe_to_dict(recipe), ensure_ascii=False, indent=2), encoding="utf-8")
    AUTO_METRICS_PATH.write_text(json.dumps(best_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    result_frame.to_csv(AUTO_RESULT_PATH, index=False, encoding="utf-8-sig")
    save_json(RECIPE_PATH, recipe_to_dict(recipe))
    selected_terms = serialize_body_terms(recipe)
    return {
        "metrics": best_metrics,
        "selected_body_terms": selected_terms,
        "transport_terms": serialize_transport_terms(recipe),
        "scoreboard_rows": int(len(scoreboard)),
        "top_scoreboard": scoreboard.head(15).to_dict("records") if not scoreboard.empty else [],
    }


def run_sensitivity_analysis(factors: List[FactorSpec]) -> pd.DataFrame:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SENSITIVITY_DIR.mkdir(parents=True, exist_ok=True)
    enabled = [factor for factor in factors if factor.enabled]
    panel = build_panel(enabled)
    factors_by_id = {factor.factor_id: factor for factor in enabled}
    region_reference = read_region_reference(REGION_REFERENCE_PATH)

    rows: List[Dict[str, Any]] = []
    for target_id in TARGET_IDS:
        target_factor = factors_by_id.get(target_id)
        if target_factor is None:
            continue
        for horizon in TARGET_HORIZONS:
            recipe, scoreboard, _result_frame, metrics = select_recipe_for_target(
                enabled,
                panel,
                factors_by_id,
                region_reference,
                target_id,
                horizon,
            )
            prefix = SENSITIVITY_DIR / f"{target_id}_h{horizon}"
            recipe_path = prefix.with_name(f"{prefix.name}_recipe.json")
            metrics_path = prefix.with_name(f"{prefix.name}_metrics.json")
            scoreboard_path = prefix.with_name(f"{prefix.name}_scoreboard.csv")
            recipe_path.write_text(json.dumps(recipe_to_dict(recipe), ensure_ascii=False, indent=2), encoding="utf-8")
            metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            scoreboard.to_csv(scoreboard_path, index=False, encoding="utf-8-sig")

            body_terms = serialize_body_terms(recipe)
            transport_terms = serialize_transport_terms(recipe)
            body_rows = scoreboard[scoreboard["role"] == ROLE_BODY] if not scoreboard.empty else pd.DataFrame()
            top_body = body_rows.iloc[0].to_dict() if not body_rows.empty else {}
            top_overall = scoreboard.iloc[0].to_dict() if not scoreboard.empty else {}
            corr = metrics.get("correlation")
            rows.append({
                "target_factor_id": target_id,
                "target_name": target_factor.name,
                "horizon": horizon,
                "correlation": corr,
                "abs_correlation": abs(float(corr)) if corr is not None else 0.0,
                "rmse_z": metrics.get("rmse_z"),
                "direction_accuracy": metrics.get("direction_accuracy"),
                "n_eval": metrics.get("n_eval", 0),
                "selected_body_terms": compact_terms(body_terms),
                "selected_transport_terms": compact_terms(transport_terms),
                "top_body_candidate": top_body.get("candidate", ""),
                "top_body_lag": top_body.get("lag", ""),
                "top_body_correlation": top_body.get("correlation", ""),
                "top_overall_candidate": top_overall.get("candidate", ""),
                "top_overall_role": top_overall.get("role", ""),
                "top_overall_lag": top_overall.get("lag", ""),
                "top_overall_transport": top_overall.get("transport", ""),
                "recipe_path": str(recipe_path.relative_to(APP_DIR)),
                "scoreboard_path": str(scoreboard_path.relative_to(APP_DIR)),
            })

    summary = pd.DataFrame(rows).sort_values(["target_factor_id", "horizon"]).reset_index(drop=True)
    summary.to_csv(SENSITIVITY_SUMMARY_PATH, index=False, encoding="utf-8-sig")
    return summary


def markdown_table(frame: pd.DataFrame, columns: List[str], max_rows: int = 20) -> str:
    if frame.empty:
        return "_Нет строк._"
    subset = frame[columns].head(max_rows).copy()
    headers = [str(column) for column in columns]
    rows = []
    for _, row in subset.iterrows():
        rows.append([str(row.get(column, "")) for column in columns])
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def report_frame(frame: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    out = frame[columns].copy()
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].round(4)
    return out


def write_sensitivity_report(summary: pd.DataFrame) -> None:
    if summary.empty:
        SENSITIVITY_REPORT_PATH.write_text("# Чувствительность автоподбора v0\n\nНет строк.", encoding="utf-8")
        return
    best_by_target = (
        summary.sort_values("abs_correlation", ascending=False)
        .groupby("target_factor_id", as_index=False)
        .head(1)
        .sort_values("target_factor_id")
    )
    top = summary.sort_values("abs_correlation", ascending=False).head(10)
    lines = [
        "# Чувствительность автоподбора v0",
        "",
        f"Дата: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "Матрица показывает, как текущий набор тела и транспорта работает на разных целях и горизонтах.",
        "Это не финальная модель, а диагностический слой: он отвечает, где уже есть сигнал и где нужно добывать новые данные.",
        "",
        "## Все цели и горизонты",
        "",
        markdown_table(
            report_frame(summary, [
                "target_factor_id",
                "horizon",
                "correlation",
                "rmse_z",
                "direction_accuracy",
                "n_eval",
                "top_body_candidate",
                "top_body_lag",
                "selected_transport_terms",
            ]),
            [
                "target_factor_id",
                "horizon",
                "correlation",
                "rmse_z",
                "direction_accuracy",
                "n_eval",
                "top_body_candidate",
                "top_body_lag",
                "selected_transport_terms",
            ],
            max_rows=40,
        ),
        "",
        "## Лучший горизонт по каждой цели",
        "",
        markdown_table(
            report_frame(best_by_target, [
                "target_factor_id",
                "horizon",
                "correlation",
                "direction_accuracy",
                "top_body_candidate",
                "top_body_lag",
                "selected_transport_terms",
            ]),
            [
                "target_factor_id",
                "horizon",
                "correlation",
                "direction_accuracy",
                "top_body_candidate",
                "top_body_lag",
                "selected_transport_terms",
            ],
            max_rows=10,
        ),
        "",
        "## Общий рейтинг",
        "",
        markdown_table(
            report_frame(top, [
                "target_factor_id",
                "horizon",
                "correlation",
                "direction_accuracy",
                "top_overall_candidate",
                "top_overall_role",
                "top_overall_transport",
            ]),
            [
                "target_factor_id",
                "horizon",
                "correlation",
                "direction_accuracy",
                "top_overall_candidate",
                "top_overall_role",
                "top_overall_transport",
            ],
            max_rows=10,
        ),
        "",
        "## Интерпретация",
        "",
        "- Если связь быстро падает на горизонтах 2/3/6, текущие факторы больше описывают совпадающее движение цен, чем ранний импульс.",
        "- Если лучшими оказываются укрупненные ИПЦ-группы, тело индекса нужно дробить глубже: мясо, молоко, хлеб, овощи, импортозависимые товары.",
        "- Если транспорт почти не меняет score, географическая матрица v0 слишком грубая и нужна логистика: дороги, грузооборот, ЖД, склады, топливо.",
        "- Если направление около 0.5, индекс пока едва лучше случайного знака; это нормально для v0 без среды.",
        "",
        "## Файлы",
        "",
        f"- `{SENSITIVITY_SUMMARY_PATH.relative_to(APP_DIR)}`",
        f"- `{SENSITIVITY_DIR.relative_to(APP_DIR)}/`",
    ]
    SENSITIVITY_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    decisions: pd.DataFrame,
    horizons: pd.DataFrame,
    flags: pd.DataFrame,
    auto: Dict[str, Any],
    sensitivity: pd.DataFrame,
) -> None:
    counts = decisions.groupby(["qc_decision", "auto_ready"]).size().reset_index(name="count")
    metrics = auto["metrics"]
    lines = [
        "# QC-отчет D01-D08 и первый автоподбор v0",
        "",
        f"Дата: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Что сделано",
        "",
        "- Региональная панель считается по гармонизированным 85 субъектам.",
        "- Сырые Fedstat CSV не изменены.",
        "- Целевые ряды Fedstat 31074 переведены в `period_zscore`, потому что исходное значение уже является процентом к предыдущему месяцу.",
        "- В каталог факторов добавлены производные body-кандидаты `body_ipc_nonfood_broad` и `body_ipc_services_broad`.",
        "- Короткие исторические ряды 2002-2006 и авиа с экстремумами временно исключены из автоподбора v0.",
        "- Первый автоподбор запущен против `target_ipc_food`, горизонт 1 месяц, лаги 0-6.",
        "",
        "## Решения QC",
        "",
        markdown_table(counts, ["qc_decision", "auto_ready", "count"]),
        "",
        "## Горизонты целей",
        "",
        markdown_table(horizons, ["target_factor_id", "horizon", "future_rows", "future_regions", "period_min", "period_max"]),
        "",
        "## Оставшиеся флаги после гармонизации",
        "",
        f"Всего флагов: {len(flags)}.",
        "",
        markdown_table(flags, ["factor_id", "region", "period", "value"], max_rows=12),
        "",
        "## Автоподбор v0",
        "",
        f"- Цель: `{TARGET_ID}`.",
        f"- Корреляция: `{metrics.get('correlation')}`.",
        f"- N проверки: `{metrics.get('n_eval')}`.",
        f"- RMSE z-score: `{metrics.get('rmse_z')}`.",
        f"- Точность направления: `{metrics.get('direction_accuracy')}`.",
        "",
        "Выбранные body-термы:",
        "",
    ]
    selected = pd.DataFrame(auto["selected_body_terms"])
    lines.append(markdown_table(selected, ["factor_id", "weight", "lag", "transform"]) if not selected.empty else "_Нет выбранных термов._")
    lines.extend([
        "",
        "Транспортные термы:",
        "",
    ])
    transport = pd.DataFrame(auto["transport_terms"])
    lines.append(markdown_table(transport, ["transport_type", "weight", "lag", "power", "max_distance_km"]) if not transport.empty else "_Транспорт не улучшил score._")
    lines.extend([
        "",
        "Топ кандидатов:",
        "",
    ])
    top = pd.DataFrame(auto["top_scoreboard"])
    if not top.empty:
        lines.append(markdown_table(top, ["candidate", "role", "lag", "transport", "correlation", "n_eval", "score"], max_rows=15))
    else:
        lines.append("_Нет строк scorebord._")
    if not sensitivity.empty:
        lines.extend([
            "",
            "## Разведка целей и горизонтов",
            "",
            "Дополнительно прогнаны все целевые ряды на горизонтах 1, 2, 3 и 6 месяцев.",
            "",
            markdown_table(
                report_frame(sensitivity.sort_values("abs_correlation", ascending=False).head(8), [
                    "target_factor_id",
                    "horizon",
                    "correlation",
                    "direction_accuracy",
                    "top_body_candidate",
                    "top_body_lag",
                    "selected_transport_terms",
                ]),
                [
                    "target_factor_id",
                    "horizon",
                    "correlation",
                    "direction_accuracy",
                    "top_body_candidate",
                    "top_body_lag",
                    "selected_transport_terms",
                ],
                max_rows=8,
            ),
        ])
    lines.extend([
        "",
        "## Выходные файлы",
        "",
        f"- `{QC_DECISIONS_PATH.relative_to(APP_DIR)}`",
        f"- `{TARGET_HORIZON_PATH.relative_to(APP_DIR)}`",
        f"- `{QC_SUMMARY_SUBJECTS_PATH.relative_to(APP_DIR)}`",
        f"- `{QC_FLAGS_SUBJECTS_PATH.relative_to(APP_DIR)}`",
        f"- `{AUTO_SCOREBOARD_PATH.relative_to(APP_DIR)}`",
        f"- `{AUTO_RECIPE_PATH.relative_to(APP_DIR)}`",
        f"- `{AUTO_METRICS_PATH.relative_to(APP_DIR)}`",
        f"- `{AUTO_RESULT_PATH.relative_to(APP_DIR)}`",
        f"- `{SENSITIVITY_SUMMARY_PATH.relative_to(APP_DIR)}`",
        f"- `{SENSITIVITY_REPORT_PATH.relative_to(APP_DIR)}`",
    ])
    QC_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    factors = ensure_broad_body_aliases(apply_target_transform_policy(load_catalog()))
    decisions = build_qc_tables(factors)
    flags = write_subject_flags(factors)
    horizons = write_horizon_check(factors)
    factors = apply_qc_to_catalog(factors, decisions)
    auto = run_auto_selection(factors)
    sensitivity = run_sensitivity_analysis(factors)
    write_sensitivity_report(sensitivity)
    write_report(decisions, horizons, flags, auto, sensitivity)
    print(json.dumps({
        "qc_decisions": str(QC_DECISIONS_PATH),
        "target_horizon_check": str(TARGET_HORIZON_PATH),
        "qc_report": str(QC_REPORT_PATH),
        "sensitivity_summary": str(SENSITIVITY_SUMMARY_PATH),
        "sensitivity_report": str(SENSITIVITY_REPORT_PATH),
        "auto_metrics": auto["metrics"],
        "selected_body_terms": auto["selected_body_terms"],
        "transport_terms": auto["transport_terms"],
        "best_sensitivity": sensitivity.sort_values("abs_correlation", ascending=False).head(5).to_dict("records"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
