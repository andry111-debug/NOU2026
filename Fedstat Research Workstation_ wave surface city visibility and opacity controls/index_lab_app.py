# -*- coding: utf-8 -*-
"""Standalone GUI for the inflation impulse index lab."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from index_lab_core import (
    ROLE_BODY,
    ROLE_ENVIRONMENT,
    ROLE_LABELS,
    ROLE_TARGET,
    TRANSFORM_LABELS,
    TRANSPORT_LABELS,
    FactorSpec,
    IndexRecipe,
    RecipeTerm,
    TransportTerm,
    auto_build_recipe,
    compute_index,
    factors_from_dict,
    factors_to_dict,
    load_json,
    preview_columns,
    recipe_from_dict,
    recipe_to_dict,
    safe_id,
    save_json,
)


APP_NAME = "Лаборатория индекса инфляционного импульса"
APP_VERSION = "N_001"
APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = APP_DIR / "settings"
DEFAULT_CATALOG_PATH = SETTINGS_DIR / "index_lab_factors.json"
DEFAULT_RECIPE_PATH = SETTINGS_DIR / "index_lab_recipe.json"
DEFAULT_OUTPUT_DIR = APP_DIR / "index_lab_output"
REGION_REFERENCE_PATH = APP_DIR / "data" / "geo" / "regions_reference.csv"

SCHEME_STEPS = [
    {
        "id": "data",
        "title": "1. Входные данные",
        "short": "Каталог факторов",
        "kind": "data",
        "detail": "Загружаем все ряды в единый каталог: товары, услуги, топливо, курс, региональные признаки и целевую инфляцию. Каждый фактор приводится к формату region / period / value.",
    },
    {
        "id": "target",
        "title": "2. Цель исследования",
        "short": "Y[r,t+h]",
        "kind": "data",
        "detail": "Выбираем, с чем сравниваем индекс: например, будущая продовольственная инфляция региона через 1, 2, 3 или 6 месяцев.",
    },
    {
        "id": "shocks",
        "title": "3. Преобразование в шоки",
        "short": "raw / diff / z-score",
        "kind": "process",
        "detail": "Сырые значения превращаются в исследовательские признаки: отклонение от среднего периода, z-score, месячное изменение или темп роста. Так индекс ловит импульс, а не общий фон.",
    },
    {
        "id": "body",
        "title": "4. Кандидаты тела",
        "short": "товары и цены",
        "kind": "body",
        "detail": "Формируем кандидаты тела индекса: продовольственные и непродовольственные товары, услуги, бензин, транспортные издержки, упаковка и другие ценовые ряды.",
    },
    {
        "id": "environment",
        "title": "5. Кандидаты среды",
        "short": "восприимчивость",
        "kind": "environment",
        "detail": "Среда описывает, насколько регион усиливает или гасит импульс: производство, зависимость от ввоза, доходы, сезонность, специализация, инфраструктурные ограничения.",
    },
    {
        "id": "transport",
        "title": "6. Кандидаты транспорта",
        "short": "граф связей",
        "kind": "transport",
        "detail": "Транспорт задаёт каналы распространения между регионами: расстояние, общий федеральный округ, соседство, а позже дороги, ЖД, авиа, порты, топливо и холодовые цепочки.",
    },
    {
        "id": "lags",
        "title": "7. Лаги распространения",
        "short": "0..6 месяцев",
        "kind": "process",
        "detail": "Для каждого фактора и транспортного слоя проверяются лаги. Так мы ищем не просто корреляцию, а временную последовательность распространения импульса.",
    },
    {
        "id": "scoring",
        "title": "8. Оценка кандидатов",
        "short": "корреляция / ошибка",
        "kind": "analysis",
        "detail": "Каждый кандидат проверяется отдельно и в комбинациях: корреляция с целью t+h, ошибка, точность направления, число наблюдений и устойчивость по периодам.",
    },
    {
        "id": "recipe",
        "title": "9. Сборка рецепта",
        "short": "единый индекс",
        "kind": "analysis",
        "detail": "Лучшие элементы собираются в единый рецепт. Этот рецепт одинаков для ручного режима и автоподбора: его можно редактировать, сохранять и снова проверять.",
    },
    {
        "id": "validation",
        "title": "10. Проверка устойчивости",
        "short": "train / test",
        "kind": "validation",
        "detail": "Проверяем индекс вне периода подбора: по годам, регионам, лагам и наборам факторов. Это защита от случайной подгонки.",
    },
    {
        "id": "output",
        "title": "11. Научный результат",
        "short": "рейтинг / карта / отчёт",
        "kind": "output",
        "detail": "На выходе получаем рецепт индекса, таблицу значений, метрики качества, сильные факторы, лаги, регионы-источники, регионы-получатели и карты распространения.",
    },
]


def open_path(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("Открытие", str(exc))


def _label_to_key(label: str, mapping: Dict[str, str], default: str) -> str:
    for key, value in mapping.items():
        if label == value or label == key:
            return key
    return default


def _key_to_label(key: str, mapping: Dict[str, str]) -> str:
    return mapping.get(key, key)


class IndexLabApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x820")
        self.minsize(1060, 700)

        self.factors: List[FactorSpec] = []
        self.recipe = IndexRecipe()
        self.last_result_frame: Any = None
        self.last_scoreboard: Any = None
        self.scheme_blocks: List[Dict[str, Any]] = []
        self.scheme_selected_id = "data"

        self.project_name_var = tk.StringVar(value="Исследование инфляционного импульса")
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.recipe_name_var = tk.StringVar(value=self.recipe.name)
        self.target_factor_var = tk.StringVar()
        self.horizon_var = tk.StringVar(value="1")

        self.factor_id_var = tk.StringVar()
        self.factor_name_var = tk.StringVar()
        self.factor_role_var = tk.StringVar(value=ROLE_LABELS[ROLE_BODY])
        self.factor_file_var = tk.StringVar()
        self.region_column_var = tk.StringVar(value="region")
        self.period_column_var = tk.StringVar(value="period")
        self.value_column_var = tk.StringVar(value="value")
        self.factor_transform_var = tk.StringVar(value=TRANSFORM_LABELS["period_zscore"])
        self.factor_enabled_var = tk.BooleanVar(value=True)
        self.factor_note_var = tk.StringVar()

        self.term_factor_var = tk.StringVar()
        self.term_weight_var = tk.StringVar(value="1.0")
        self.term_lag_var = tk.StringVar(value="0")
        self.term_transform_var = tk.StringVar(value="")

        self.transport_type_var = tk.StringVar(value=TRANSPORT_LABELS["distance_inverse"])
        self.transport_weight_var = tk.StringVar(value="0.3")
        self.transport_lag_var = tk.StringVar(value="1")
        self.transport_power_var = tk.StringVar(value="1.0")
        self.transport_max_distance_var = tk.StringVar(value="0")

        self.auto_max_lag_var = tk.StringVar(value="3")
        self.auto_max_terms_var = tk.StringVar(value="5")

        self._build_ui()
        self.load_catalog(silent=True)
        self.load_recipe(silent=True)
        self.refresh_all()
        self._log_ui("Лаборатория готова. Добавьте факторы, соберите рецепт индекса и запустите расчёт.")

    def _build_ui(self) -> None:
        self._build_menu()
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(root, text="Общие параметры")
        settings.pack(fill="x", padx=8, pady=6)
        row1 = ttk.Frame(settings)
        row1.pack(fill="x", padx=6, pady=3)
        ttk.Label(row1, text="Проект:").pack(side="left")
        ttk.Entry(row1, textvariable=self.project_name_var, width=36).pack(side="left", padx=5)
        ttk.Label(row1, text="Рецепт:").pack(side="left")
        ttk.Entry(row1, textvariable=self.recipe_name_var, width=42).pack(side="left", padx=5)
        ttk.Label(row1, text="Горизонт, мес.:").pack(side="left")
        ttk.Entry(row1, textvariable=self.horizon_var, width=6).pack(side="left", padx=5)

        row2 = ttk.Frame(settings)
        row2.pack(fill="x", padx=6, pady=3)
        ttk.Label(row2, text="Целевой фактор:").pack(side="left")
        self.target_combo = ttk.Combobox(row2, textvariable=self.target_factor_var, width=30, state="readonly")
        self.target_combo.pack(side="left", padx=5)
        ttk.Label(row2, text="Папка результатов:").pack(side="left")
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
        self._build_tab_factors()
        self._build_tab_recipe()
        self._build_tab_run()
        self._build_tab_results()
        self._build_tab_concept()

        log_frame = ttk.LabelFrame(root, text="Журнал")
        log_frame.pack(fill="both", padx=8, pady=6, expand=False)
        self.log_text = tk.Text(log_frame, height=8, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text.configure(state="disabled")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Сохранить каталог факторов", command=self.save_catalog)
        file_menu.add_command(label="Загрузить каталог факторов", command=lambda: self.load_catalog(silent=False))
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить рецепт", command=self.save_recipe)
        file_menu.add_command(label="Загрузить рецепт", command=lambda: self.load_recipe(silent=False))
        file_menu.add_separator()
        file_menu.add_command(label="Открыть папку результатов", command=lambda: open_path(Path(self.output_dir_var.get() or ".")))
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        run_menu = tk.Menu(menubar, tearoff=0)
        run_menu.add_command(label="Рассчитать ручной рецепт", command=self.calculate_manual_thread)
        run_menu.add_command(label="Автоподбор рецепта", command=self.auto_select_thread)
        menubar.add_cascade(label="Расчёт", menu=run_menu)
        self.config(menu=menubar)

    def _build_tab_factors(self) -> None:
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="1) Факторы")

        form = ttk.LabelFrame(tab, text="Добавление фактора")
        form.pack(fill="x", padx=8, pady=6)

        row1 = ttk.Frame(form)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="ID:").pack(side="left")
        ttk.Entry(row1, textvariable=self.factor_id_var, width=24).pack(side="left", padx=5)
        ttk.Label(row1, text="Название:").pack(side="left")
        ttk.Entry(row1, textvariable=self.factor_name_var, width=42).pack(side="left", padx=5)
        ttk.Label(row1, text="Роль:").pack(side="left")
        ttk.Combobox(row1, textvariable=self.factor_role_var, width=14, state="readonly", values=list(ROLE_LABELS.values())).pack(side="left", padx=5)
        ttk.Checkbutton(row1, text="включён", variable=self.factor_enabled_var).pack(side="left", padx=8)

        row2 = ttk.Frame(form)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Файл:").pack(side="left")
        ttk.Entry(row2, textvariable=self.factor_file_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row2, text="Выбрать...", command=self.choose_factor_file).pack(side="left", padx=4)
        ttk.Button(row2, text="Прочитать колонки", command=self.load_factor_columns).pack(side="left", padx=4)

        row3 = ttk.Frame(form)
        row3.pack(fill="x", padx=6, pady=4)
        ttk.Label(row3, text="Регион:").pack(side="left")
        self.region_col_combo = ttk.Combobox(row3, textvariable=self.region_column_var, width=22)
        self.region_col_combo.pack(side="left", padx=5)
        ttk.Label(row3, text="Период:").pack(side="left")
        self.period_col_combo = ttk.Combobox(row3, textvariable=self.period_column_var, width=22)
        self.period_col_combo.pack(side="left", padx=5)
        ttk.Label(row3, text="Значение:").pack(side="left")
        self.value_col_combo = ttk.Combobox(row3, textvariable=self.value_column_var, width=22)
        self.value_col_combo.pack(side="left", padx=5)
        ttk.Label(row3, text="Преобразование:").pack(side="left")
        ttk.Combobox(row3, textvariable=self.factor_transform_var, width=28, state="readonly", values=list(TRANSFORM_LABELS.values())).pack(side="left", padx=5)

        row4 = ttk.Frame(form)
        row4.pack(fill="x", padx=6, pady=4)
        ttk.Label(row4, text="Заметка:").pack(side="left")
        ttk.Entry(row4, textvariable=self.factor_note_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(row4, text="Добавить / обновить", command=self.add_or_update_factor).pack(side="left", padx=4)
        ttk.Button(row4, text="Удалить выбранный", command=self.delete_selected_factor).pack(side="left", padx=4)

        table_frame = ttk.LabelFrame(tab, text="Каталог факторов")
        table_frame.pack(fill="both", expand=True, padx=8, pady=6)
        cols = ("enabled", "factor_id", "name", "role", "transform", "source")
        self.factors_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=14)
        for col, title, width in [
            ("enabled", "✓", 42),
            ("factor_id", "ID", 150),
            ("name", "Название", 260),
            ("role", "Роль", 110),
            ("transform", "Преобразование", 210),
            ("source", "Файл", 420),
        ]:
            self.factors_tree.heading(col, text=title)
            self.factors_tree.column(col, width=width, stretch=(col == "source"))
        self.factors_tree.pack(fill="both", expand=True, padx=6, pady=4)
        self.factors_tree.bind("<<TreeviewSelect>>", lambda event: self.load_selected_factor_to_form())

    def _build_tab_recipe(self) -> None:
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="2) Рецепт индекса")

        top = ttk.LabelFrame(tab, text="Добавление элемента в рецепт")
        top.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(top)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="Фактор:").pack(side="left")
        self.term_factor_combo = ttk.Combobox(row, textvariable=self.term_factor_var, width=28, state="readonly")
        self.term_factor_combo.pack(side="left", padx=5)
        ttk.Label(row, text="Вес:").pack(side="left")
        ttk.Entry(row, textvariable=self.term_weight_var, width=8).pack(side="left", padx=5)
        ttk.Label(row, text="Лаг, мес.:").pack(side="left")
        ttk.Entry(row, textvariable=self.term_lag_var, width=6).pack(side="left", padx=5)
        ttk.Label(row, text="Преобразование:").pack(side="left")
        transform_values = ["по фактору"] + list(TRANSFORM_LABELS.values())
        ttk.Combobox(row, textvariable=self.term_transform_var, width=28, state="readonly", values=transform_values).pack(side="left", padx=5)
        ttk.Button(row, text="Добавить в тело", command=lambda: self.add_recipe_term(ROLE_BODY)).pack(side="left", padx=4)
        ttk.Button(row, text="Добавить в среду", command=lambda: self.add_recipe_term(ROLE_ENVIRONMENT)).pack(side="left", padx=4)

        middle = ttk.Frame(tab)
        middle.pack(fill="both", expand=True, padx=8, pady=6)
        body_frame = ttk.LabelFrame(middle, text="Тело индекса")
        body_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        env_frame = ttk.LabelFrame(middle, text="Среда")
        env_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self.body_tree = self._make_terms_tree(body_frame)
        self.environment_tree = self._make_terms_tree(env_frame)

        bottom = ttk.LabelFrame(tab, text="Транспорт импульса")
        bottom.pack(fill="x", padx=8, pady=6)
        trow = ttk.Frame(bottom)
        trow.pack(fill="x", padx=6, pady=4)
        ttk.Label(trow, text="Тип:").pack(side="left")
        ttk.Combobox(trow, textvariable=self.transport_type_var, width=26, state="readonly", values=list(TRANSPORT_LABELS.values())).pack(side="left", padx=5)
        ttk.Label(trow, text="Вес:").pack(side="left")
        ttk.Entry(trow, textvariable=self.transport_weight_var, width=8).pack(side="left", padx=5)
        ttk.Label(trow, text="Лаг:").pack(side="left")
        ttk.Entry(trow, textvariable=self.transport_lag_var, width=6).pack(side="left", padx=5)
        ttk.Label(trow, text="Степень расстояния:").pack(side="left")
        ttk.Entry(trow, textvariable=self.transport_power_var, width=6).pack(side="left", padx=5)
        ttk.Label(trow, text="Макс. км (0=все):").pack(side="left")
        ttk.Entry(trow, textvariable=self.transport_max_distance_var, width=8).pack(side="left", padx=5)
        ttk.Button(trow, text="Добавить транспорт", command=self.add_transport_term).pack(side="left", padx=4)
        ttk.Button(trow, text="Удалить выбранное", command=self.delete_selected_recipe_item).pack(side="left", padx=4)

        self.transport_tree = ttk.Treeview(bottom, columns=("type", "weight", "lag", "power", "max_distance"), show="headings", height=4)
        for col, title, width in [
            ("type", "Тип", 220),
            ("weight", "Вес", 80),
            ("lag", "Лаг", 70),
            ("power", "Степень", 90),
            ("max_distance", "Макс. км", 90),
        ]:
            self.transport_tree.heading(col, text=title)
            self.transport_tree.column(col, width=width)
        self.transport_tree.pack(fill="x", padx=6, pady=4)

    def _make_terms_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        cols = ("factor_id", "weight", "lag", "transform")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
        for col, title, width in [
            ("factor_id", "Фактор", 170),
            ("weight", "Вес", 80),
            ("lag", "Лаг", 70),
            ("transform", "Преобразование", 210),
        ]:
            tree.heading(col, text=title)
            tree.column(col, width=width, stretch=(col == "transform"))
        tree.pack(fill="both", expand=True, padx=6, pady=4)
        return tree

    def _build_tab_run(self) -> None:
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="3) Расчёт и автоподбор")

        actions = ttk.LabelFrame(tab, text="Расчёт")
        actions.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(actions)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Рассчитать ручной рецепт", command=self.calculate_manual_thread).pack(side="left", padx=4)
        ttk.Button(row, text="Автоподбор", command=self.auto_select_thread).pack(side="left", padx=4)
        ttk.Label(row, text="Макс. лаг:").pack(side="left", padx=(18, 2))
        ttk.Entry(row, textvariable=self.auto_max_lag_var, width=6).pack(side="left", padx=3)
        ttk.Label(row, text="Макс. факторов:").pack(side="left", padx=(12, 2))
        ttk.Entry(row, textvariable=self.auto_max_terms_var, width=6).pack(side="left", padx=3)

        metrics = ttk.LabelFrame(tab, text="Метрики текущего рецепта")
        metrics.pack(fill="x", padx=8, pady=6)
        self.metrics_text = tk.Text(metrics, height=6, wrap="word")
        self.metrics_text.pack(fill="x", padx=6, pady=4)
        self.metrics_text.configure(state="disabled")

        score_frame = ttk.LabelFrame(tab, text="Таблица кандидатов автоподбора")
        score_frame.pack(fill="both", expand=True, padx=8, pady=6)
        cols = ("candidate", "role", "lag", "transport", "correlation", "n_eval", "score")
        self.scoreboard_tree = ttk.Treeview(score_frame, columns=cols, show="headings", height=12)
        for col, title, width in [
            ("candidate", "Фактор", 180),
            ("role", "Роль", 90),
            ("lag", "Лаг", 60),
            ("transport", "Транспорт", 180),
            ("correlation", "Корреляция", 110),
            ("n_eval", "N", 70),
            ("score", "Score", 90),
        ]:
            self.scoreboard_tree.heading(col, text=title)
            self.scoreboard_tree.column(col, width=width, stretch=(col in ("candidate", "transport")))
        self.scoreboard_tree.pack(fill="both", expand=True, padx=6, pady=4)

    def _build_tab_results(self) -> None:
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="4) Результаты")

        actions = ttk.LabelFrame(tab, text="Результаты индекса")
        actions.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(actions)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Экспортировать CSV", command=self.export_result_csv).pack(side="left", padx=4)
        ttk.Button(row, text="Открыть папку результатов", command=lambda: open_path(Path(self.output_dir_var.get() or "."))).pack(side="left", padx=4)
        ttk.Label(row, text="В таблице показываются первые 1000 строк последнего расчёта.").pack(side="left", padx=12)

        table_frame = ttk.LabelFrame(tab, text="Панель индекса")
        table_frame.pack(fill="both", expand=True, padx=8, pady=6)
        cols = ("region", "period", "body", "environment", "transport", "index", "target_future")
        self.result_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=18)
        for col, title, width in [
            ("region", "Регион", 220),
            ("period", "Период", 90),
            ("body", "Тело", 90),
            ("environment", "Среда", 90),
            ("transport", "Транспорт", 100),
            ("index", "Индекс", 90),
            ("target_future", "Цель t+h", 100),
        ]:
            self.result_tree.heading(col, text=title)
            self.result_tree.column(col, width=width, stretch=(col == "region"))
        self.result_tree.pack(fill="both", expand=True, padx=6, pady=4)

    def _build_tab_concept(self) -> None:
        tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(tab, text="5) Схема")
        header = ttk.LabelFrame(tab, text="Блок-схема автоматического подбора и исследования индекса")
        header.pack(fill="x", padx=8, pady=6)
        ttk.Label(
            header,
            text=(
                "Схема показывает общий конвейер: от факторов и цели к шокам, кандидатам тела/среды/транспорта, "
                "оценке, сборке рецепта и научному результату. Блоки можно выбирать мышью."
            ),
            wraplength=1120,
        ).pack(fill="x", padx=6, pady=5)

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        canvas_frame = ttk.LabelFrame(body, text="Доска лаборатории")
        canvas_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.scheme_canvas = tk.Canvas(canvas_frame, bg="#f5f8fb", highlightthickness=0)
        self.scheme_canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.scheme_canvas.bind("<Configure>", lambda event: self.draw_scheme())
        self.scheme_canvas.bind("<Button-1>", self.on_scheme_click)

        detail = ttk.LabelFrame(body, text="Описание выбранного этапа")
        detail.pack(side="right", fill="y", padx=(6, 0))
        detail.configure(width=330)
        self.scheme_detail_title_var = tk.StringVar()
        ttk.Label(detail, textvariable=self.scheme_detail_title_var, font=("Segoe UI", 11, "bold"), wraplength=300).pack(fill="x", padx=8, pady=(8, 4))
        self.scheme_detail_text = tk.Text(detail, width=38, height=18, wrap="word")
        self.scheme_detail_text.pack(fill="both", expand=True, padx=8, pady=4)
        self.scheme_detail_text.configure(state="disabled")

        legend = ttk.LabelFrame(detail, text="Слои индекса")
        legend.pack(fill="x", padx=8, pady=8)
        for title, color in [
            ("Данные и цель", "#d8ebff"),
            ("Обработка", "#fff0c9"),
            ("Тело", "#dff3d8"),
            ("Среда", "#e5ddff"),
            ("Транспорт", "#d9f2ee"),
            ("Проверка", "#ffdede"),
            ("Результат", "#d7eef5"),
        ]:
            row = ttk.Frame(legend)
            row.pack(fill="x", padx=6, pady=2)
            sample = tk.Canvas(row, width=22, height=14, highlightthickness=0)
            sample.pack(side="left")
            sample.create_rectangle(1, 1, 21, 13, fill=color, outline="#9aa7b2")
            ttk.Label(row, text=title).pack(side="left", padx=6)

        self.update_scheme_detail("data")

    def scheme_counts(self) -> Dict[str, str]:
        enabled = [f for f in self.factors if f.enabled]
        body_count = len([f for f in enabled if f.role == ROLE_BODY])
        env_count = len([f for f in enabled if f.role == ROLE_ENVIRONMENT])
        target_count = len([f for f in enabled if f.role == ROLE_TARGET])
        return {
            "data": f"{len(enabled)} факторов",
            "target": self.target_factor_var.get().strip() or self.recipe.target_factor_id or f"{target_count} целей",
            "body": f"{body_count} в каталоге / {len(self.recipe.body_terms)} в рецепте",
            "environment": f"{env_count} в каталоге / {len(self.recipe.environment_terms)} в рецепте",
            "transport": f"{len(self.recipe.transport_terms)} слоёв",
            "recipe": f"{len(self.recipe.body_terms) + len(self.recipe.environment_terms)} факторов + {len(self.recipe.transport_terms)} транспорт",
            "output": "CSV / карта / отчёт",
        }

    def draw_scheme(self) -> None:
        if not hasattr(self, "scheme_canvas"):
            return
        canvas = self.scheme_canvas
        canvas.delete("all")
        width = max(900, canvas.winfo_width())
        height = max(520, canvas.winfo_height())
        self.scheme_blocks = []

        for x in range(0, width, 48):
            canvas.create_line(x, 0, x, height, fill="#e9eef4")
        for y in range(0, height, 48):
            canvas.create_line(0, y, width, y, fill="#e9eef4")

        title = "Конвейер подбора индекса инфляционного импульса"
        canvas.create_text(24, 18, text=title, anchor="w", fill="#1f2d3d", font=("Segoe UI", 15, "bold"))
        canvas.create_text(
            24,
            44,
            text="ручной рецепт и автоподбор используют одну и ту же структуру",
            anchor="w",
            fill="#52616f",
            font=("Segoe UI", 9),
        )

        block_w = 176
        block_h = 82
        row_y = [86, 220, 354]
        x0 = 32
        gap = max(24, (width - 2 * x0 - 5 * block_w) / 4)
        xs = [x0 + i * (block_w + gap) for i in range(5)]
        positions = {
            "data": (xs[0], row_y[0]),
            "target": (xs[1], row_y[0]),
            "shocks": (xs[2], row_y[0]),
            "lags": (xs[3], row_y[0]),
            "scoring": (xs[4], row_y[0]),
            "body": (xs[1] - block_w * 0.55, row_y[1]),
            "environment": (xs[2], row_y[1]),
            "transport": (xs[3] + block_w * 0.55, row_y[1]),
            "recipe": (xs[2], row_y[2]),
            "validation": (xs[3] + block_w * 0.4, row_y[2]),
            "output": (xs[4], row_y[2]),
        }
        counts = self.scheme_counts()
        colors = {
            "data": "#d8ebff",
            "process": "#fff0c9",
            "body": "#dff3d8",
            "environment": "#e5ddff",
            "transport": "#d9f2ee",
            "analysis": "#e7edf7",
            "validation": "#ffdede",
            "output": "#d7eef5",
        }

        links = [
            ("data", "shocks"),
            ("target", "scoring"),
            ("shocks", "body"),
            ("shocks", "environment"),
            ("shocks", "transport"),
            ("body", "lags"),
            ("transport", "lags"),
            ("environment", "scoring"),
            ("lags", "scoring"),
            ("scoring", "recipe"),
            ("recipe", "validation"),
            ("validation", "output"),
            ("recipe", "output"),
        ]
        for source, target in links:
            self.draw_scheme_arrow(canvas, positions[source], positions[target], block_w, block_h)

        for step in SCHEME_STEPS:
            x, y = positions[step["id"]]
            fill = colors.get(step["kind"], "#ffffff")
            selected = step["id"] == self.scheme_selected_id
            outline = "#2b6cb0" if selected else "#98a6b3"
            width_line = 3 if selected else 1
            canvas.create_rectangle(x + 3, y + 4, x + block_w + 3, y + block_h + 4, fill="#d5dde5", outline="")
            canvas.create_rectangle(x, y, x + block_w, y + block_h, fill=fill, outline=outline, width=width_line)
            canvas.create_text(x + 10, y + 10, text=step["title"], anchor="nw", width=block_w - 20, fill="#1f2d3d", font=("Segoe UI", 9, "bold"))
            canvas.create_text(x + 10, y + 40, text=step["short"], anchor="nw", width=block_w - 20, fill="#2f4050", font=("Segoe UI", 10))
            note = counts.get(step["id"], "")
            if note:
                canvas.create_text(x + 10, y + 62, text=note, anchor="nw", width=block_w - 20, fill="#667788", font=("Segoe UI", 8))
            self.scheme_blocks.append({"id": step["id"], "bbox": (x, y, x + block_w, y + block_h)})

        canvas.create_text(
            24,
            height - 28,
            text="MVP: индекс = тело + среда + транспортированный лаг тела. Дальше схема станет интерактивной лабораторной доской.",
            anchor="w",
            fill="#52616f",
            font=("Segoe UI", 9),
        )

    def draw_scheme_arrow(self, canvas: tk.Canvas, source: tuple[float, float], target: tuple[float, float], block_w: int, block_h: int) -> None:
        sx, sy = source
        tx, ty = target
        start_x = sx + block_w
        start_y = sy + block_h / 2
        end_x = tx
        end_y = ty + block_h / 2
        if abs(end_x - start_x) < 24:
            start_x = sx + block_w / 2
            start_y = sy + block_h
            end_x = tx + block_w / 2
            end_y = ty
        canvas.create_line(start_x, start_y, end_x, end_y, fill="#8a98a8", width=2, arrow="last", smooth=True)

    def on_scheme_click(self, event: Any) -> None:
        for block in self.scheme_blocks:
            x0, y0, x1, y1 = block["bbox"]
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self.update_scheme_detail(block["id"])
                self.draw_scheme()
                return

    def update_scheme_detail(self, step_id: str) -> None:
        self.scheme_selected_id = step_id
        step = next((item for item in SCHEME_STEPS if item["id"] == step_id), SCHEME_STEPS[0])
        if not hasattr(self, "scheme_detail_text"):
            return
        self.scheme_detail_title_var.set(step["title"])
        counts = self.scheme_counts()
        lines = [step["detail"]]
        if counts.get(step_id):
            lines.append("")
            lines.append(f"Текущее состояние: {counts[step_id]}")
        if step_id == "recipe":
            lines.append("")
            lines.append("Ручной режим: человек меняет этот рецепт.")
            lines.append("Автоматический режим: алгоритм записывает найденную версию в тот же рецепт.")
        self.scheme_detail_text.configure(state="normal")
        self.scheme_detail_text.delete("1.0", "end")
        self.scheme_detail_text.insert("1.0", "\n".join(lines))
        self.scheme_detail_text.configure(state="disabled")

    def redraw_scheme_if_ready(self) -> None:
        if hasattr(self, "scheme_canvas"):
            self.draw_scheme()
            self.update_scheme_detail(self.scheme_selected_id)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(APP_DIR))
        if path:
            self.output_dir_var.set(path)

    def choose_factor_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("All files", "*.*")])
        if not path:
            return
        self.factor_file_var.set(path)
        if not self.factor_name_var.get().strip():
            self.factor_name_var.set(Path(path).stem)
        if not self.factor_id_var.get().strip():
            self.factor_id_var.set(safe_id(Path(path).stem, [f.factor_id for f in self.factors]))
        self.load_factor_columns()

    def load_factor_columns(self) -> None:
        path = Path(self.factor_file_var.get().strip())
        if not path.exists():
            messagebox.showwarning("Фактор", "Выберите существующий CSV/XLSX-файл.")
            return
        try:
            columns = preview_columns(path)
            for combo in [self.region_col_combo, self.period_col_combo, self.value_col_combo]:
                combo.configure(values=columns)
            lower = {c.lower(): c for c in columns}
            for key in ["region", "регион", "subject", "fedstat_name"]:
                if key in lower:
                    self.region_column_var.set(lower[key])
                    break
            for key in ["period", "период", "date", "month", "месяц"]:
                if key in lower:
                    self.period_column_var.set(lower[key])
                    break
            for key in ["value", "значение", "index", "индекс"]:
                if key in lower:
                    self.value_column_var.set(lower[key])
                    break
            self.set_progress(f"Колонки прочитаны: {len(columns)}", 100)
        except Exception as exc:
            self._log_ui(traceback.format_exc())
            messagebox.showerror("Фактор", str(exc))

    def add_or_update_factor(self) -> None:
        factor_id = self.factor_id_var.get().strip()
        name = self.factor_name_var.get().strip()
        if not name:
            messagebox.showwarning("Фактор", "Укажите название фактора.")
            return
        if not factor_id:
            factor_id = safe_id(name, [f.factor_id for f in self.factors])
            self.factor_id_var.set(factor_id)
        role = _label_to_key(self.factor_role_var.get(), ROLE_LABELS, ROLE_BODY)
        transform = _label_to_key(self.factor_transform_var.get(), TRANSFORM_LABELS, "period_zscore")
        spec = FactorSpec(
            factor_id=factor_id,
            name=name,
            role=role,
            source_path=self.factor_file_var.get().strip(),
            region_column=self.region_column_var.get().strip(),
            period_column=self.period_column_var.get().strip(),
            value_column=self.value_column_var.get().strip(),
            transform=transform,
            enabled=self.factor_enabled_var.get(),
            note=self.factor_note_var.get().strip(),
        )
        for idx, existing in enumerate(self.factors):
            if existing.factor_id == factor_id:
                self.factors[idx] = spec
                break
        else:
            self.factors.append(spec)
        self.refresh_all()
        self._log_ui(f"Фактор сохранён в каталоге: {factor_id} ({ROLE_LABELS.get(role, role)})")

    def delete_selected_factor(self) -> None:
        selected = self.factors_tree.selection()
        if not selected:
            return
        ids = set(selected)
        self.factors = [f for f in self.factors if f.factor_id not in ids]
        self.recipe.body_terms = [t for t in self.recipe.body_terms if t.factor_id not in ids]
        self.recipe.environment_terms = [t for t in self.recipe.environment_terms if t.factor_id not in ids]
        if self.recipe.target_factor_id in ids:
            self.recipe.target_factor_id = ""
            self.target_factor_var.set("")
        self.refresh_all()

    def load_selected_factor_to_form(self) -> None:
        selected = self.factors_tree.selection()
        if not selected:
            return
        factor = next((f for f in self.factors if f.factor_id == selected[0]), None)
        if factor is None:
            return
        self.factor_id_var.set(factor.factor_id)
        self.factor_name_var.set(factor.name)
        self.factor_role_var.set(_key_to_label(factor.role, ROLE_LABELS))
        self.factor_file_var.set(factor.source_path)
        self.region_column_var.set(factor.region_column)
        self.period_column_var.set(factor.period_column)
        self.value_column_var.set(factor.value_column)
        self.factor_transform_var.set(_key_to_label(factor.transform, TRANSFORM_LABELS))
        self.factor_enabled_var.set(factor.enabled)
        self.factor_note_var.set(factor.note)

    def add_recipe_term(self, role: str) -> None:
        factor_id = self.term_factor_var.get().strip()
        if not factor_id:
            messagebox.showwarning("Рецепт", "Выберите фактор.")
            return
        try:
            weight = float(self.term_weight_var.get().replace(",", "."))
            lag = int(float(self.term_lag_var.get().replace(",", ".")))
        except Exception:
            messagebox.showwarning("Рецепт", "Вес и лаг должны быть числами.")
            return
        transform_label = self.term_transform_var.get().strip()
        transform = "" if transform_label in ("", "по фактору") else _label_to_key(transform_label, TRANSFORM_LABELS, "")
        term = RecipeTerm(factor_id=factor_id, role=role, weight=weight, lag=max(0, lag), transform=transform)
        if role == ROLE_ENVIRONMENT:
            self.recipe.environment_terms.append(term)
        else:
            self.recipe.body_terms.append(term)
        self.refresh_recipe_trees()

    def add_transport_term(self) -> None:
        try:
            term = TransportTerm(
                transport_type=_label_to_key(self.transport_type_var.get(), TRANSPORT_LABELS, "distance_inverse"),
                weight=float(self.transport_weight_var.get().replace(",", ".")),
                lag=max(0, int(float(self.transport_lag_var.get().replace(",", ".")))),
                power=float(self.transport_power_var.get().replace(",", ".")),
                max_distance_km=float(self.transport_max_distance_var.get().replace(",", ".")),
            )
        except Exception:
            messagebox.showwarning("Транспорт", "Параметры транспорта должны быть числами.")
            return
        self.recipe.transport_terms.append(term)
        self.refresh_recipe_trees()

    def delete_selected_recipe_item(self) -> None:
        for tree, terms in [
            (self.body_tree, self.recipe.body_terms),
            (self.environment_tree, self.recipe.environment_terms),
            (self.transport_tree, self.recipe.transport_terms),
        ]:
            selected = tree.selection()
            if selected:
                indexes = sorted([int(i) for i in selected], reverse=True)
                for idx in indexes:
                    if 0 <= idx < len(terms):
                        del terms[idx]
                self.refresh_recipe_trees()
                return

    def sync_recipe_from_vars(self) -> None:
        self.recipe.name = self.recipe_name_var.get().strip() or self.recipe.name
        self.recipe.target_factor_id = self.target_factor_var.get().strip()
        try:
            self.recipe.horizon = max(0, int(float(self.horizon_var.get().replace(",", "."))))
        except Exception:
            self.recipe.horizon = 1
            self.horizon_var.set("1")

    def calculate_manual_thread(self) -> None:
        threading.Thread(target=self.calculate_manual, daemon=True).start()

    def calculate_manual(self) -> None:
        try:
            self.set_progress("Расчёт ручного рецепта...", 10, "indeterminate")
            self.sync_recipe_from_vars()
            result = compute_index(self.recipe, self.factors, REGION_REFERENCE_PATH)
            self.last_result_frame = result.frame
            self.after(0, lambda: self.show_run_result(result.metrics, result.messages))
            self.after(0, self.refresh_result_tree)
            self.set_progress("Расчёт завершён.", 100, "determinate")
        except Exception as exc:
            self.set_progress("Ошибка расчёта.", 0, "determinate")
            self._log_ui(traceback.format_exc())
            self.after(0, lambda exc=exc: messagebox.showerror("Расчёт", str(exc)))

    def auto_select_thread(self) -> None:
        threading.Thread(target=self.auto_select, daemon=True).start()

    def auto_select(self) -> None:
        try:
            self.set_progress("Автоподбор рецепта...", 10, "indeterminate")
            self.sync_recipe_from_vars()
            max_lag = max(0, int(float(self.auto_max_lag_var.get().replace(",", "."))))
            max_terms = max(1, int(float(self.auto_max_terms_var.get().replace(",", "."))))
            recipe, scoreboard, metrics = auto_build_recipe(
                self.factors,
                self.recipe.target_factor_id,
                self.recipe.horizon,
                REGION_REFERENCE_PATH,
                max_lag=max_lag,
                max_terms=max_terms,
            )
            self.recipe = recipe
            self.recipe_name_var.set(recipe.name)
            self.target_factor_var.set(recipe.target_factor_id)
            self.horizon_var.set(str(recipe.horizon))
            self.last_scoreboard = scoreboard
            result = compute_index(self.recipe, self.factors, REGION_REFERENCE_PATH)
            self.last_result_frame = result.frame
            self.after(0, self.refresh_recipe_trees)
            self.after(0, self.refresh_scoreboard_tree)
            self.after(0, lambda: self.show_run_result(metrics, ["Автоподбор записан в обычный рецепт. Его можно редактировать вручную."]))
            self.after(0, self.refresh_result_tree)
            self.set_progress("Автоподбор завершён.", 100, "determinate")
        except Exception as exc:
            self.set_progress("Ошибка автоподбора.", 0, "determinate")
            self._log_ui(traceback.format_exc())
            self.after(0, lambda exc=exc: messagebox.showerror("Автоподбор", str(exc)))

    def show_run_result(self, metrics: Dict[str, Any], messages: Optional[List[str]] = None) -> None:
        lines = [
            f"Рецепт: {metrics.get('recipe', self.recipe.name)}",
            f"Строк индекса: {metrics.get('rows')}",
            f"N для проверки: {metrics.get('n_eval')}",
            f"Корреляция с целью t+h: {self._fmt(metrics.get('correlation'))}",
            f"RMSE по z-score: {self._fmt(metrics.get('rmse_z'))}",
            f"Точность направления: {self._fmt(metrics.get('direction_accuracy'))}",
        ]
        for msg in messages or []:
            lines.append(f"Примечание: {msg}")
        self.metrics_text.configure(state="normal")
        self.metrics_text.delete("1.0", "end")
        self.metrics_text.insert("1.0", "\n".join(lines))
        self.metrics_text.configure(state="disabled")
        self._log_ui(" | ".join(lines[:4]))

    def export_result_csv(self) -> None:
        if self.last_result_frame is None:
            messagebox.showinfo("Экспорт", "Сначала рассчитайте индекс.")
            return
        out_dir = Path(self.output_dir_var.get() or DEFAULT_OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "index_lab_result.csv"
        self.last_result_frame.to_csv(path, index=False, encoding="utf-8-sig")
        self._log_ui(f"Результат экспортирован: {path}")
        messagebox.showinfo("Экспорт", f"Результат сохранён:\n{path}")

    def save_catalog(self) -> None:
        try:
            save_json(DEFAULT_CATALOG_PATH, factors_to_dict(self.factors))
            self._log_ui(f"Каталог факторов сохранён: {DEFAULT_CATALOG_PATH}")
        except Exception as exc:
            messagebox.showerror("Каталог", str(exc))

    def load_catalog(self, silent: bool = False) -> None:
        path = DEFAULT_CATALOG_PATH
        if not path.exists():
            if not silent:
                messagebox.showinfo("Каталог", "Сохранённый каталог факторов не найден.")
            return
        try:
            self.factors = factors_from_dict(load_json(path))
            self.refresh_all()
            self._log_ui(f"Каталог факторов загружен: {path}")
        except Exception as exc:
            if not silent:
                messagebox.showerror("Каталог", str(exc))

    def save_recipe(self) -> None:
        self.sync_recipe_from_vars()
        try:
            save_json(DEFAULT_RECIPE_PATH, recipe_to_dict(self.recipe))
            self._log_ui(f"Рецепт сохранён: {DEFAULT_RECIPE_PATH}")
        except Exception as exc:
            messagebox.showerror("Рецепт", str(exc))

    def load_recipe(self, silent: bool = False) -> None:
        path = DEFAULT_RECIPE_PATH
        if not path.exists():
            if not silent:
                messagebox.showinfo("Рецепт", "Сохранённый рецепт не найден.")
            return
        try:
            self.recipe = recipe_from_dict(load_json(path))
            self.recipe_name_var.set(self.recipe.name)
            self.target_factor_var.set(self.recipe.target_factor_id)
            self.horizon_var.set(str(self.recipe.horizon))
            self.refresh_recipe_trees()
            self._log_ui(f"Рецепт загружен: {path}")
        except Exception as exc:
            if not silent:
                messagebox.showerror("Рецепт", str(exc))

    def refresh_all(self) -> None:
        self.refresh_factors_tree()
        self.refresh_factor_combos()
        self.refresh_recipe_trees()
        self.redraw_scheme_if_ready()

    def refresh_factor_combos(self) -> None:
        ids = [f.factor_id for f in self.factors if f.enabled]
        self.target_combo.configure(values=ids)
        self.term_factor_combo.configure(values=ids)
        if self.recipe.target_factor_id and self.recipe.target_factor_id in ids:
            self.target_factor_var.set(self.recipe.target_factor_id)

    def refresh_factors_tree(self) -> None:
        self.factors_tree.delete(*self.factors_tree.get_children())
        for factor in self.factors:
            self.factors_tree.insert(
                "",
                "end",
                iid=factor.factor_id,
                values=(
                    "☑" if factor.enabled else "☐",
                    factor.factor_id,
                    factor.name,
                    ROLE_LABELS.get(factor.role, factor.role),
                    TRANSFORM_LABELS.get(factor.transform, factor.transform),
                    factor.source_path,
                ),
            )

    def refresh_recipe_trees(self) -> None:
        self.body_tree.delete(*self.body_tree.get_children())
        self.environment_tree.delete(*self.environment_tree.get_children())
        self.transport_tree.delete(*self.transport_tree.get_children())
        for idx, term in enumerate(self.recipe.body_terms):
            self.body_tree.insert("", "end", iid=str(idx), values=(term.factor_id, term.weight, term.lag, TRANSFORM_LABELS.get(term.transform, "по фактору")))
        for idx, term in enumerate(self.recipe.environment_terms):
            self.environment_tree.insert("", "end", iid=str(idx), values=(term.factor_id, term.weight, term.lag, TRANSFORM_LABELS.get(term.transform, "по фактору")))
        for idx, term in enumerate(self.recipe.transport_terms):
            self.transport_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(TRANSPORT_LABELS.get(term.transport_type, term.transport_type), term.weight, term.lag, term.power, term.max_distance_km),
            )
        self.redraw_scheme_if_ready()

    def refresh_result_tree(self) -> None:
        self.result_tree.delete(*self.result_tree.get_children())
        if self.last_result_frame is None:
            return
        columns = ["region", "period", "body", "environment", "transport", "index", "target_future"]
        frame = self.last_result_frame.copy()
        for col in columns:
            if col not in frame.columns:
                frame[col] = ""
        for idx, row in frame.head(1000).iterrows():
            self.result_tree.insert("", "end", iid=str(idx), values=tuple(self._fmt(row.get(col)) for col in columns))

    def refresh_scoreboard_tree(self) -> None:
        self.scoreboard_tree.delete(*self.scoreboard_tree.get_children())
        if self.last_scoreboard is None:
            return
        for idx, row in self.last_scoreboard.head(1000).iterrows():
            self.scoreboard_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    row.get("candidate", ""),
                    row.get("role", ""),
                    row.get("lag", ""),
                    row.get("transport", ""),
                    self._fmt(row.get("correlation")),
                    row.get("n_eval", ""),
                    self._fmt(row.get("score")),
                ),
            )

    def set_progress(self, text: str, value: Optional[int] = None, mode: str = "determinate") -> None:
        self.after(0, self.stage_var.set, text)
        self.after(0, self.progress.configure, {"mode": mode})
        if value is not None:
            self.after(0, self.progress.configure, {"value": value})
        if mode == "indeterminate":
            self.after(0, self.progress.start, 12)
        else:
            self.after(0, self.progress.stop)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_ui(self, message: str) -> None:
        self.after(0, self._append_log, message)

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None:
            return ""
        try:
            if value != value:
                return ""
            if isinstance(value, float):
                return f"{value:.4f}"
        except Exception:
            pass
        return str(value)


def main() -> None:
    app = IndexLabApp()
    app.mainloop()


if __name__ == "__main__":
    main()
