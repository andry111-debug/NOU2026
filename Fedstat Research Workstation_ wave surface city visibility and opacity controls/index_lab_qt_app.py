# -*- coding: utf-8 -*-
"""PySide6 index laboratory UI styled after Fedstat Research Workstation 2.0."""

from __future__ import annotations

import csv
import math
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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


APP_NAME = "Fedstat Research Workstation 2.0"
APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = APP_DIR / "settings"
DEFAULT_CATALOG_PATH = SETTINGS_DIR / "index_lab_factors.json"
DEFAULT_RECIPE_PATH = SETTINGS_DIR / "index_lab_recipe.json"
DEFAULT_OUTPUT_DIR = APP_DIR / "index_lab_output"
AUTO_SCOREBOARD_PATH = DEFAULT_OUTPUT_DIR / "auto_selection_v0_scoreboard.csv"
AUTO_METRICS_PATH = DEFAULT_OUTPUT_DIR / "auto_selection_v0_metrics.json"
AUTO_SENSITIVITY_PATH = DEFAULT_OUTPUT_DIR / "auto_selection_v0_sensitivity.csv"
DEFAULT_REGION_REFERENCE_PATH = APP_DIR / "data" / "geo" / "regions_reference.csv"
HARMONIZED_REGION_REFERENCE_PATH = APP_DIR / "data" / "geo" / "regions_reference_fedstat_harmonized.csv"
REGION_REFERENCE_PATH = HARMONIZED_REGION_REFERENCE_PATH if HARMONIZED_REGION_REFERENCE_PATH.exists() else DEFAULT_REGION_REFERENCE_PATH

PINK = "#c24b82"
PINK_DARK = "#9f3f69"
PINK_LIGHT = "#f8e4ef"
PANEL = "#fff7fb"
BORDER = "#efc9db"
TEXT = "#2f2030"
MUTED = "#9a6c82"

SCHEME_STEPS = [
    ("data", "Входные данные", "Каталог факторов", "Собираем товары, услуги, топливо, курс, среду и целевую инфляцию в формат region / period / value.", "#dff0ff"),
    ("target", "Цель", "Y[r,t+h]", "Выбираем будущую инфляцию, с которой сравниваем индекс: горизонт 1, 2, 3 или 6 месяцев.", "#dff0ff"),
    ("shocks", "Шоки", "raw / diff / z-score", "Преобразуем ряды в импульсы: отклонение от среднего, z-score, месячное изменение или темп роста.", "#fff1c9"),
    ("body", "Тело", "товары и цены", "Подбираем товарные и ценовые элементы: продовольствие, непродовольственные товары, услуги, топливо, логистические издержки.", "#dff3d8"),
    ("environment", "Среда", "восприимчивость", "Добавляем региональные условия, которые усиливают или гасят импульс: производство, доходы, сезонность, зависимость от ввоза.", "#e7ddff"),
    ("transport", "Транспорт", "граф связей", "Строим каналы распространения: расстояние, общий федеральный округ, соседство, будущие дороги, ЖД, порты и холодовые цепочки.", "#d9f2ee"),
    ("lags", "Лаги", "0..6 месяцев", "Проверяем, через сколько месяцев фактор или входящий импульс связан с целевой инфляцией.", "#fff1c9"),
    ("scoring", "Оценка", "корреляция / ошибка", "Сравниваем кандидатов по корреляции, ошибке, направлению изменения и числу наблюдений.", "#e8eef8"),
    ("recipe", "Рецепт", "единый индекс", "Собираем единый рецепт. Ручной режим и автоподбор используют одну структуру, которую можно редактировать.", "#e8eef8"),
    ("validation", "Проверка", "устойчивость", "Проверяем рецепт вне периода подбора: по годам, регионам, лагам и наборам факторов.", "#ffdddd"),
    ("output", "Результат", "карта / отчёт", "Получаем значения индекса, сильные факторы, найденные лаги, регионы-источники и регионы-получатели.", "#d7eef5"),
]

SCHEME_DETAILS = {
    "data": {
        "input": "CSV/XLSX/Fedstat-выгрузки, внешние справочники, ручные таблицы.",
        "work": "Привести каждый ряд к единому виду: region / period / value, назначить роль фактора.",
        "output": "Каталог факторов: тело, среда, цель; позже отдельные транспортные справочники.",
    },
    "target": {
        "input": "Фактор, который считаем целевой инфляцией.",
        "work": "Задать горизонт h: индекс в t проверяется против цели в t+h.",
        "output": "Целевая панель Y[r,t+h] для проверки рецепта.",
    },
    "shocks": {
        "input": "Сырые значения факторов.",
        "work": "Построить варианты сигнала: raw, месячное изменение, z-score, отклонение от среднего периода.",
        "output": "Набор сопоставимых шоков, очищенных от части общего фона.",
    },
    "body": {
        "input": "Товарные, ценовые и сервисные факторы.",
        "work": "Перебрать фактор x преобразование x лаг; оставить кандидатов, связанных с будущей инфляцией.",
        "output": "Список элементов тела индекса с весами и лагами.",
    },
    "environment": {
        "input": "Региональные признаки и условия восприимчивости.",
        "work": "Проверить, какие признаки усиливают или гасят импульс региона.",
        "output": "Слой среды: региональные усилители и демпферы индекса.",
    },
    "transport": {
        "input": "География, расстояния, федеральные округа; позже дороги, ЖД, топливо и холодовые цепочки.",
        "work": "Построить W[j,r] и посчитать входящий импульс из связанных регионов.",
        "output": "Транспортированный сигнал: incoming[r,t] = sum W[j,r] x impulse[j,t-lag].",
    },
    "lags": {
        "input": "Кандидаты тела, среды и транспорта.",
        "work": "Проверить лаги 0, 1, 2, 3, 6 месяцев и найти временной профиль передачи.",
        "output": "Лучшие лаги для факторов и каналов распространения.",
    },
    "scoring": {
        "input": "Все кандидаты и целевая панель.",
        "work": "Оценить корреляцию, ошибку, точность направления, количество наблюдений и устойчивость.",
        "output": "Таблица кандидатов с оценками качества.",
    },
    "recipe": {
        "input": "Отобранные элементы тела, среды, транспорта и лагов.",
        "work": "Собрать единый рецепт индекса. Ручной и автоматический режимы работают с одним форматом.",
        "output": "Редактируемый рецепт индекса.",
    },
    "validation": {
        "input": "Готовый рецепт и панель данных.",
        "work": "Проверить рецепт по годам, периодам, регионам и вне обучающего окна.",
        "output": "Оценка устойчивости: что реально работает, а что было подгонкой.",
    },
    "output": {
        "input": "Проверенный рецепт и рассчитанная панель индекса.",
        "work": "Сформировать таблицы, карты, рейтинги источников/получателей и текстовые выводы.",
        "output": "Научный и прикладной результат исследования.",
    },
}

SCHEME_LINKS = [
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

ROADMAP_ITEMS = [
    {
        "stage": "M0",
        "title": "Концепция и каркас лаборатории",
        "goal": "Зафиксировать идею индекса как тела, среды и транспорта.",
        "work": "Собрать отдельное приложение, единую структуру рецепта, схему алгоритма и первый расчётный контур.",
        "ready": "Есть лаборатория, схема, ручной рецепт, автоподбор v0 и расчёт индекса.",
        "status": "готово",
    },
    {
        "stage": "M1",
        "title": "Паспорт данных",
        "goal": "Сделать управляемый каталог факторов, чтобы каждый ряд был понятен до расчёта.",
        "work": "Для каждого фактора описать слой, источник, частоту, единицы, региональность, период, пропуски, ожидаемый знак и лаги.",
        "ready": "Есть таблица-паспорт факторов и правило, какие ряды допускаются в подбор.",
        "status": "паспорт v0 заполнен",
    },
    {
        "stage": "M2",
        "title": "Целевая инфляция",
        "goal": "Собрать Y, с которым индекс будет сравниваться во времени.",
        "work": "Подготовить общий ИПЦ, продовольственную, непродовольственную инфляцию и услуги по регионам и месяцам.",
        "ready": "Целевые ряды загружены, нормализованы и проверены для горизонтов 1, 2, 3 и 6 месяцев.",
        "status": "QC v0 готов",
    },
    {
        "stage": "M3",
        "title": "Тело индекса",
        "goal": "Наполнить тело товарами, услугами и ценовыми сигналами.",
        "work": "Добавить продовольствие, непродовольственные товары, услуги, топливо, тарифы, цены производителей и оптовые сигналы.",
        "ready": "Есть стартовый набор факторов тела, который даёт ненулевую и интерпретируемую связь с целью.",
        "status": "автоподбор v0 выполнен",
    },
    {
        "stage": "M4",
        "title": "Среда распространения",
        "goal": "Описать, почему один и тот же импульс по-разному действует в регионах.",
        "work": "Добавить производство, мощности, доходы, занятость, импортозависимость, сезонность и региональные ограничения.",
        "ready": "Средовые факторы работают как усилители или гасители импульса, а не просто как ещё один список рядов.",
        "status": "следующий сбор данных",
    },
    {
        "stage": "M5",
        "title": "Транспорт и логистика",
        "goal": "Собрать каналы, по которым импульс переходит между регионами.",
        "work": "Расширить расстояния дорогами, ЖД, портами, аэропортами, топливом, грузооборотом, складами и холодовыми цепочками.",
        "ready": "Есть несколько транспортных матриц, которые можно сравнивать в автоподборе.",
        "status": "матрицы v0 проверены",
    },
    {
        "stage": "M6",
        "title": "Автоподбор v1",
        "goal": "Перейти от разведочной корреляции к устойчивому подбору рецепта.",
        "work": "Перебирать факторы, преобразования, лаги, веса и транспортные слои; штрафовать переусложнение и плохую устойчивость.",
        "ready": "Автоподбор выдаёт рецепт, таблицу кандидатов, объяснение выбора и предупреждения о рисках.",
        "status": "матрица горизонтов v0 готова",
    },
    {
        "stage": "M7",
        "title": "Валидация",
        "goal": "Проверить, что индекс не является подгонкой под один период.",
        "work": "Сделать rolling-window, train/test по времени, проверку по группам регионов, стресс-периодам и альтернативным целям.",
        "ready": "Для рецепта есть паспорт качества: где он работает, где ломается и насколько устойчив.",
        "status": "после v1",
    },
    {
        "stage": "M8",
        "title": "Интерпретация и научный результат",
        "goal": "Превратить расчёт в исследовательский вывод.",
        "work": "Показать вклад факторов, карты распространения, регионы-источники, регионы-получатели и текстовое объяснение механизма.",
        "ready": "Есть отчёт, таблицы, графики и материал для научной работы.",
        "status": "финал",
    },
]

PASSPORT_COLUMNS = [
    ("factor_id", "ID"),
    ("name", "Название"),
    ("role", "Слой"),
    ("subtype", "Подтип"),
    ("source_name", "Источник"),
    ("frequency", "Частота"),
    ("level", "Уровень"),
    ("period_start", "Период с"),
    ("period_end", "Период по"),
    ("units", "Единицы"),
    ("value_description", "Что означает value"),
    ("expected_sign", "Ожидаемый знак"),
    ("allowed_lags", "Лаги"),
    ("quality_status", "Качество"),
    ("missing_policy", "Пропуски"),
    ("passport_status", "Статус"),
    ("note", "Комментарий"),
]

DATA_NEEDS_COLUMNS = [
    ("need_id", "ID"),
    ("priority", "Приоритет"),
    ("stage", "Этап"),
    ("layer", "Слой"),
    ("dataset", "Набор данных"),
    ("source", "Где искать"),
    ("frequency", "Частота"),
    ("geography", "География"),
    ("format", "Нужный формат"),
    ("why", "Зачем нужен"),
    ("next_action", "Следующее действие"),
    ("status", "Статус"),
]

DATA_NEEDS_ITEMS = [
    {
        "need_id": "D01",
        "priority": "1",
        "stage": "M2",
        "layer": "цель",
        "dataset": "ИПЦ общий",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Главная цель для проверки общего инфляционного давления.",
        "next_action": "QC v0 готов; использовать как альтернативную цель при проверке устойчивости.",
        "status": "QC v0 готов",
    },
    {
        "need_id": "D02",
        "priority": "1",
        "stage": "M2",
        "layer": "цель",
        "dataset": "ИПЦ продовольственных товаров",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Основная целевая переменная для продовольственного импульса.",
        "next_action": "QC v0 готов; основная цель автоподбора v0, горизонт 1 месяц.",
        "status": "QC v0 готов",
    },
    {
        "need_id": "D03",
        "priority": "1",
        "stage": "M2",
        "layer": "цель",
        "dataset": "ИПЦ непродовольственных товаров",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Нужен для проверки, может ли непродовольственный блок вести продовольственную инфляцию.",
        "next_action": "QC v0 готов; добавлен укрупнённый кандидат тела body_ipc_nonfood_broad.",
        "status": "QC v0 готов",
    },
    {
        "need_id": "D04",
        "priority": "1",
        "stage": "M2",
        "layer": "цель",
        "dataset": "ИПЦ услуг",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Отделяет сервисную инфляцию от товарного импульса.",
        "next_action": "QC v0 готов; добавлен укрупнённый кандидат тела body_ipc_services_broad.",
        "status": "QC v0 готов",
    },
    {
        "need_id": "D05",
        "priority": "2",
        "stage": "M3",
        "layer": "тело",
        "dataset": "ИПЦ по группам продовольственных товаров",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value + group",
        "why": "Базовое тело продовольственного индекса.",
        "next_action": "Два длинных ряда допущены в автоподбор v0; короткие 2002-2006 пока исключены. Дальше дробить товарные группы.",
        "status": "частично в автоподборе v0",
    },
    {
        "need_id": "D06",
        "priority": "2",
        "stage": "M3",
        "layer": "тело",
        "dataset": "ИПЦ по группам непродовольственных товаров",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value + group",
        "why": "Проверяем, подстёгивают ли непродовольственные цены продовольственную инфляцию.",
        "next_action": "Короткие подгруппы 2002-2006 исключены; укрупнённый D03-кандидат тела включён. Нужна детализация.",
        "status": "частично в автоподборе v0",
    },
    {
        "need_id": "D07",
        "priority": "2",
        "stage": "M3/M5",
        "layer": "тело/транспорт",
        "dataset": "Бензин, дизель, моторное топливо",
        "source": "Fedstat / Росстат",
        "frequency": "месяц",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Топливо может быть и ценовым фактором, и стоимостью распространения импульса.",
        "next_action": "QC v0 готов; ряды допущены как ценовые и транспортно-топливные кандидаты.",
        "status": "допущено v0",
    },
    {
        "need_id": "D08",
        "priority": "2",
        "stage": "M3/M5",
        "layer": "тело/транспорт",
        "dataset": "Транспортные услуги и тарифы",
        "source": "Fedstat / Росстат",
        "frequency": "месяц/квартал",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Показывает стоимость перемещения товаров и может влиять на лаг передачи цен.",
        "next_action": "Пассажирский и ЖД транспорт допущены; авиа временно исключена из-за экстремальных значений.",
        "status": "частично допущено v0",
    },
    {
        "need_id": "D09",
        "priority": "3",
        "stage": "M3",
        "layer": "тело",
        "dataset": "Цены производителей и оптовые цены",
        "source": "Fedstat / Росстат",
        "frequency": "месяц/квартал",
        "geography": "регион/РФ",
        "format": "region / period / value",
        "why": "Ранний сигнал до потребительских цен.",
        "next_action": "Следующий кандидат для усиления тела: проверить региональность и доступность по отраслям.",
        "status": "следующий поиск",
    },
    {
        "need_id": "D10",
        "priority": "3",
        "stage": "M4",
        "layer": "среда",
        "dataset": "Производство пищевых продуктов и сельхозпроизводство",
        "source": "Fedstat / Росстат",
        "frequency": "месяц/квартал/год",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Показывает собственную производственную базу региона.",
        "next_action": "Следующий кандидат среды: разделить на пищевую промышленность и сельское хозяйство.",
        "status": "следующий поиск",
    },
    {
        "need_id": "D11",
        "priority": "3",
        "stage": "M4",
        "layer": "среда",
        "dataset": "Доходы населения и зарплаты",
        "source": "Fedstat / Росстат",
        "frequency": "месяц/квартал",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Описывает платежеспособный спрос и восприимчивость региона к росту цен.",
        "next_action": "Собрать реальные доходы и среднемесячную зарплату после первой интерпретации v0.",
        "status": "очередь M4",
    },
    {
        "need_id": "D12",
        "priority": "3",
        "stage": "M4",
        "layer": "среда",
        "dataset": "Безработица и занятость",
        "source": "Fedstat / Росстат",
        "frequency": "месяц/квартал",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Дополнительная характеристика спроса и устойчивости региона.",
        "next_action": "Проверить частоту и сопоставимость с месячной инфляцией после D10-D11.",
        "status": "очередь M4",
    },
    {
        "need_id": "D13",
        "priority": "3",
        "stage": "M4",
        "layer": "среда",
        "dataset": "Население, урбанизация, плотность",
        "source": "Росстат / справочники",
        "frequency": "год",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Медленный структурный слой среды.",
        "next_action": "Собрать годовой ряд и решить правило переноса на месяцы.",
        "status": "очередь M4",
    },
    {
        "need_id": "D14",
        "priority": "3",
        "stage": "M4",
        "layer": "среда",
        "dataset": "Валютный курс",
        "source": "Банк России",
        "frequency": "день/месяц",
        "geography": "РФ",
        "format": "period / value",
        "why": "Общий внешний шок, который может по-разному проявляться в регионах через среду.",
        "next_action": "Собрать месячный средний курс и правило тиражирования на регионы.",
        "status": "очередь M4",
    },
    {
        "need_id": "D15",
        "priority": "1",
        "stage": "M5",
        "layer": "транспорт",
        "dataset": "Координаты регионов и федеральные округа",
        "source": "локальный справочник",
        "frequency": "статично",
        "geography": "регион",
        "format": "region / lat / lon / federal_district",
        "why": "Уже даёт первые транспортные матрицы: расстояние и общий федеральный округ.",
        "next_action": "Скачано: geoBoundaries ADM1 и справочник 89 субъектов; маппинг Fedstat готов.",
        "status": "скачано и гармонизировано v0",
    },
    {
        "need_id": "D16",
        "priority": "4",
        "stage": "M5",
        "layer": "транспорт",
        "dataset": "Автодороги и время в пути между регионами",
        "source": "открытые геоданные / ручная матрица",
        "frequency": "статично/год",
        "geography": "регион-регион",
        "format": "source_region / target_region / weight",
        "why": "Лучше описывает реальную передачу импульса, чем расстояние по прямой.",
        "next_action": "Решить источник и формат матрицы.",
        "status": "позже",
    },
    {
        "need_id": "D17",
        "priority": "4",
        "stage": "M5",
        "layer": "транспорт",
        "dataset": "ЖД, порты, аэропорты, грузооборот",
        "source": "Росстат / отраслевые источники",
        "frequency": "год/квартал",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Описывает мощность и направления логистики.",
        "next_action": "Начать с грузооборота по видам транспорта.",
        "status": "позже",
    },
    {
        "need_id": "D18",
        "priority": "4",
        "stage": "M5",
        "layer": "транспорт",
        "dataset": "Склады и холодовые цепочки",
        "source": "отраслевые справочники / ручная сборка",
        "frequency": "статично/год",
        "geography": "регион",
        "format": "region / period / value",
        "why": "Критично для продовольственных товаров, где важны хранение и охлаждение.",
        "next_action": "Сначала определить, есть ли открытый источник.",
        "status": "позже",
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
        QMessageBox.warning(None, "Открытие", str(exc))


def label_to_key(label: str, mapping: Dict[str, str], default: str) -> str:
    for key, value in mapping.items():
        if label == value or label == key:
            return key
    return default


def key_to_label(key: str, mapping: Dict[str, str]) -> str:
    return mapping.get(key, key)


class BackgroundWidget(QWidget):
    """Light patterned workspace background like the 2.0 workstation shell."""

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fffafd"))
        painter.setPen(Qt.NoPen)

        for x in range(90, self.width() + 160, 260):
            for y in range(44, self.height() + 180, 230):
                self.draw_flower(painter, x, y, QColor(250, 226, 238, 85), QColor(246, 208, 48, 90))

        for x in range(190, self.width() + 180, 390):
            for y in range(18, self.height() + 240, 260):
                self.draw_bow(painter, x, y, QColor(236, 143, 183, 70))

        painter.setBrush(QColor(239, 184, 211, 140))
        step = 18
        for x in range(0, self.width() + step, step):
            painter.drawEllipse(QPointF(x, 93), 5.4, 5.4)

    @staticmethod
    def draw_flower(painter: QPainter, x: int, y: int, petal: QColor, center: QColor) -> None:
        painter.setBrush(petal)
        for angle in range(0, 360, 60):
            rad = math.radians(angle)
            painter.drawEllipse(QPointF(x + math.cos(rad) * 12, y + math.sin(rad) * 12), 8, 12)
        painter.setBrush(center)
        painter.drawEllipse(QPointF(x, y), 5, 5)

    @staticmethod
    def draw_bow(painter: QPainter, x: int, y: int, color: QColor) -> None:
        painter.setBrush(color)
        painter.drawEllipse(QPointF(x - 12, y), 17, 9)
        painter.drawEllipse(QPointF(x + 12, y), 17, 9)
        painter.drawEllipse(QPointF(x, y), 5, 5)
        painter.drawPolygon([QPointF(x - 5, y + 6), QPointF(x - 13, y + 26), QPointF(x - 1, y + 15)])
        painter.drawPolygon([QPointF(x + 5, y + 6), QPointF(x + 13, y + 26), QPointF(x + 1, y + 15)])


class FlowArrowItem(QGraphicsPathItem):
    def __init__(self, source: "FlowBlockItem", target: "FlowBlockItem") -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.head = QGraphicsPolygonItem(self)
        self.setZValue(-10)
        self.setPen(QPen(QColor("#b987a0"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.head.setBrush(QBrush(QColor("#b987a0")))
        self.head.setPen(Qt.NoPen)
        source.arrows.append(self)
        target.arrows.append(self)
        self.update_position()

    @staticmethod
    def anchor(source_rect: QRectF, target_rect: QRectF) -> QPointF:
        source = source_rect.center()
        target = target_rect.center()
        dx = target.x() - source.x()
        dy = target.y() - source.y()
        if abs(dx) / max(source_rect.width(), 1) > abs(dy) / max(source_rect.height(), 1):
            x = source_rect.right() if dx >= 0 else source_rect.left()
            return QPointF(x, source.y())
        y = source_rect.bottom() if dy >= 0 else source_rect.top()
        return QPointF(source.x(), y)

    def update_position(self) -> None:
        s_rect = self.source.sceneBoundingRect()
        t_rect = self.target.sceneBoundingRect()
        start = self.anchor(s_rect, t_rect)
        end = self.anchor(t_rect, s_rect)
        dx = max(80.0, abs(end.x() - start.x()) * 0.45)
        path = QPainterPath(start)
        if abs(end.x() - start.x()) >= abs(end.y() - start.y()):
            c1 = QPointF(start.x() + dx if end.x() >= start.x() else start.x() - dx, start.y())
            c2 = QPointF(end.x() - dx if end.x() >= start.x() else end.x() + dx, end.y())
        else:
            dy = max(60.0, abs(end.y() - start.y()) * 0.45)
            c1 = QPointF(start.x(), start.y() + dy if end.y() >= start.y() else start.y() - dy)
            c2 = QPointF(end.x(), end.y() - dy if end.y() >= start.y() else end.y() + dy)
        path.cubicTo(c1, c2, end)
        self.setPath(path)
        angle = math.atan2(end.y() - c2.y(), end.x() - c2.x())
        size = 10
        p1 = QPointF(end.x() - math.cos(angle - 0.45) * size, end.y() - math.sin(angle - 0.45) * size)
        p2 = QPointF(end.x() - math.cos(angle + 0.45) * size, end.y() - math.sin(angle + 0.45) * size)
        self.head.setPolygon(QPolygonF([end, p1, p2]))


class FlowBlockItem(QGraphicsRectItem):
    def __init__(self, step: tuple[str, str, str, str, str], counts: Dict[str, str], on_select=None, on_open=None) -> None:
        super().__init__(0, 0, 215, 108)
        self.step = step
        self.step_id = step[0]
        self.counts = counts
        self.on_select = on_select
        self.on_open = on_open
        self.arrows: List[FlowArrowItem] = []
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setToolTip("Двойной щелчок открывает содержание блока. Блок можно перемещать мышью.")
        self.setBrush(QBrush(QColor(step[4])))
        self.setPen(QPen(QColor(BORDER), 1.2))

        self.title = QGraphicsTextItem(step[1], self)
        self.title.setDefaultTextColor(QColor(TEXT))
        self.title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.title.setTextWidth(190)
        self.title.setPos(12, 8)

        self.short = QGraphicsTextItem(step[2], self)
        self.short.setDefaultTextColor(QColor(TEXT))
        self.short.setFont(QFont("Segoe UI", 10))
        self.short.setTextWidth(190)
        self.short.setPos(12, 40)

        self.note = QGraphicsTextItem("", self)
        self.note.setDefaultTextColor(QColor("#7d6071"))
        self.note.setFont(QFont("Segoe UI", 8))
        self.note.setTextWidth(190)
        self.note.setPos(12, 74)
        self.refresh_note()

    def refresh_note(self) -> None:
        note = self.counts.get(self.step_id, "этап алгоритма")
        self.note.setPlainText(note)

    def set_selected_style(self, selected: bool) -> None:
        self.setPen(QPen(QColor(PINK_DARK if selected else BORDER), 2.4 if selected else 1.2))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.on_select:
            self.on_select(self.step_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.on_open:
            self.on_open(self.step_id)
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:  # noqa: N802
        result = super().itemChange(change, value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            for arrow in list(self.arrows):
                arrow.update_position()
        return result


class FlowSchemeWidget(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(540)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#fffafd"))
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1720, 680)
        self.setScene(self.scene)
        self.counts: Dict[str, str] = {}
        self.selected_id = "data"
        self.on_select = None
        self.on_open = None
        self.blocks: Dict[str, FlowBlockItem] = {}
        self.arrows: List[FlowArrowItem] = []
        self.default_positions = {
            "data": QPointF(50, 95),
            "target": QPointF(50, 270),
            "shocks": QPointF(330, 182),
            "body": QPointF(620, 55),
            "environment": QPointF(620, 205),
            "transport": QPointF(620, 355),
            "lags": QPointF(905, 205),
            "scoring": QPointF(1185, 205),
            "recipe": QPointF(1460, 205),
            "validation": QPointF(1460, 55),
            "output": QPointF(1460, 355),
        }
        self.build_scene()

    def build_scene(self) -> None:
        self.scene.clear()
        self.blocks = {}
        self.arrows = []
        title = self.scene.addText("Блок-схема подбора индекса", QFont("Segoe UI", 16, QFont.Bold))
        title.setDefaultTextColor(QColor(TEXT))
        title.setPos(28, 24)
        subtitle = self.scene.addText(
            "Данные -> шоки -> тело / среда / транспорт -> лаги -> оценка -> рецепт -> проверка -> результат",
            QFont("Segoe UI", 9),
        )
        subtitle.setDefaultTextColor(QColor(MUTED))
        subtitle.setPos(30, 55)

        lanes = [
            (28, 86, 250, 345, "1. Источники"),
            (306, 128, 245, 210, "2. Шоки"),
            (590, 34, 255, 475, "3. Слои индекса"),
            (876, 170, 235, 205, "4. Время"),
            (1156, 170, 235, 205, "5. Отбор"),
            (1430, 34, 255, 475, "6. Рецепт и вывод"),
        ]
        for x, y, width, height, label in lanes:
            lane = self.scene.addRect(
                QRectF(x, y, width, height),
                QPen(QColor("#f1d4e2"), 1),
                QBrush(QColor(255, 247, 251, 120)),
            )
            lane.setZValue(-30)
            lane_label = self.scene.addText(label, QFont("Segoe UI", 9, QFont.Bold))
            lane_label.setDefaultTextColor(QColor(MUTED))
            lane_label.setPos(x + 12, y + 10)
            lane_label.setZValue(-20)

        by_id = {step[0]: step for step in SCHEME_STEPS}
        for step_id, point in self.default_positions.items():
            block = FlowBlockItem(by_id[step_id], self.counts, on_select=self.select_block, on_open=self.open_block)
            block.setPos(point)
            self.scene.addItem(block)
            self.blocks[step_id] = block

        for source, target in SCHEME_LINKS:
            arrow = FlowArrowItem(self.blocks[source], self.blocks[target])
            self.scene.addItem(arrow)
            self.arrows.append(arrow)
        self.select_block(self.selected_id)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor("#fffafd"))
        painter.setPen(QPen(QColor("#f5dce8"), 1))
        left = int(rect.left()) - int(rect.left()) % 48
        top = int(rect.top()) - int(rect.top()) % 48
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += 48
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += 48

    def set_counts(self, counts: Dict[str, str]) -> None:
        self.counts = counts
        for block in self.blocks.values():
            block.counts = counts
            block.refresh_note()
        self.viewport().update()

    def select_block(self, step_id: str) -> None:
        self.selected_id = step_id
        for block_id, block in self.blocks.items():
            block.set_selected_style(block_id == step_id)
        if self.on_select:
            self.on_select(step_id)

    def open_block(self, step_id: str) -> None:
        self.select_block(step_id)
        if self.on_open:
            self.on_open(step_id)

    def reset_layout(self) -> None:
        for step_id, point in self.default_positions.items():
            if step_id in self.blocks:
                self.blocks[step_id].setPos(point)
        for arrow in self.arrows:
            arrow.update_position()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            return
        super().wheelEvent(event)


class NavigationButton(QPushButton):
    def __init__(self, text: str, index: int, parent=None) -> None:
        super().__init__(text, parent)
        self.index = index
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class IndexLabWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Лаборатория индекса")
        self.resize(1600, 900)
        self.factors: List[FactorSpec] = []
        self.recipe = IndexRecipe()
        self.last_result_frame: Any = None
        self.last_scoreboard: Any = None

        self.factor_rows: List[Dict[str, Any]] = []
        self.scheme_detail = QTextEdit()
        self.nav_buttons: List[NavigationButton] = []
        self.project_title = QLineEdit("Индекс пространственно-временного инфляционного давления")
        self.target_combo = QComboBox()
        self.horizon_combo = QComboBox()
        self.horizon_combo.addItems(["1", "2", "3", "6"])

        self.build_ui()
        self.apply_styles()
        self.load_catalog(silent=True)
        self.load_recipe(silent=True)
        self.refresh_all()

    def build_ui(self) -> None:
        root = BackgroundWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 18, 10, 12)
        side_layout.setSpacing(8)
        logo = QLabel("Fedstat")
        logo.setObjectName("Logo")
        side_layout.addWidget(logo)
        for title, idx in [
            ("Схема работы", 0),
            ("Роадмап", 1),
            ("Паспорт данных", 2),
            ("Потребность в данных", 3),
            ("Факторы", 4),
            ("Конструктор индекса", 5),
            ("Автоподбор", 6),
            ("Результаты", 7),
        ]:
            btn = NavigationButton(title, idx)
            btn.clicked.connect(lambda checked=False, b=btn: self.select_page(b.index))
            side_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        side_layout.addStretch()
        status = QLabel("Лаборатория индекса\nMVP N_002")
        status.setObjectName("SidebarStatus")
        side_layout.addWidget(status)
        main.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 24, 16, 12)
        content_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.page_title = QLabel("Схема работы")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("Визуальная блок-схема подбора и исследования индекса")
        self.page_subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(self.page_title)
        title_box.addWidget(self.page_subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.schema_button = QToolButton()
        self.schema_button.setText("Схема")
        self.schema_button.clicked.connect(lambda: self.select_page(0))
        header.addWidget(self.schema_button)
        open_button = QToolButton()
        open_button.setText("Папка результатов")
        open_button.clicked.connect(lambda: open_path(DEFAULT_OUTPUT_DIR))
        header.addWidget(open_button)
        content_layout.addLayout(header)

        row = QHBoxLayout()
        row.addWidget(QLabel("Название индекса"))
        self.project_title.setObjectName("LongInput")
        row.addWidget(self.project_title, 1)
        row.addWidget(QLabel("Цель"))
        row.addWidget(self.target_combo)
        row.addWidget(QLabel("Горизонт"))
        row.addWidget(self.horizon_combo)
        content_layout.addLayout(row)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        self.stack.addWidget(self.build_scheme_page())
        self.stack.addWidget(self.build_roadmap_page())
        self.stack.addWidget(self.build_passport_page())
        self.stack.addWidget(self.build_data_needs_page())
        self.stack.addWidget(self.build_factors_page())
        self.stack.addWidget(self.build_constructor_page())
        self.stack.addWidget(self.build_auto_page())
        self.stack.addWidget(self.build_results_page())

        bottom = QHBoxLayout()
        self.status_label = QLabel("Готово")
        self.status_label.setObjectName("StatusLabel")
        bottom.addWidget(self.status_label)
        bottom.addStretch()
        save_btn = QPushButton("Сохранить рецепт")
        save_btn.clicked.connect(self.save_recipe)
        bottom.addWidget(save_btn)
        content_layout.addLayout(bottom)
        main.addWidget(content, 1)
        self.select_page(0)

    def build_scheme_page(self) -> QWidget:
        page = QFrame()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        left = QFrame()
        left.setObjectName("Panel")
        left_layout = QVBoxLayout(left)
        self.scheme = FlowSchemeWidget()
        self.scheme.on_select = self.update_scheme_detail
        self.scheme.on_open = self.open_scheme_block
        scheme_toolbar = QHBoxLayout()
        scheme_label = QLabel("Карта алгоритма")
        scheme_label.setObjectName("SectionTitle")
        scheme_toolbar.addWidget(scheme_label)
        scheme_toolbar.addStretch()
        reset_scheme = QPushButton("Вернуть схему")
        reset_scheme.setToolTip("Вернуть блоки на исходные места.")
        reset_scheme.clicked.connect(self.scheme.reset_layout)
        scheme_toolbar.addWidget(reset_scheme)
        left_layout.addLayout(scheme_toolbar)
        left_layout.addWidget(self.scheme)
        layout.addWidget(left, 1)
        right = QFrame()
        right.setObjectName("Panel")
        right.setFixedWidth(360)
        right_layout = QVBoxLayout(right)
        right_title = QLabel("Описание этапа")
        right_title.setObjectName("SectionTitle")
        right_layout.addWidget(right_title)
        self.scheme_detail.setReadOnly(True)
        self.scheme_detail.setObjectName("DetailText")
        right_layout.addWidget(self.scheme_detail, 1)
        layout.addWidget(right)
        return page

    def build_roadmap_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        intro = QFrame()
        intro.setObjectName("Panel")
        intro_layout = QVBoxLayout(intro)
        title = QLabel("Роадмап исполнения")
        title.setObjectName("SectionTitle")
        intro_layout.addWidget(title)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setObjectName("DetailText")
        text.setMaximumHeight(118)
        text.setPlainText(
            "Работа идёт этапами. Новый функционал добавляем только тогда, когда понятно, "
            "какие данные он принимает, что вычисляет и каким критерием считаем этап готовым.\n\n"
            "Текущий фокус: интерпретировать матрицу целей/горизонтов v0, "
            "дробить тело индекса и начать сбор среды D09-D10."
        )
        intro_layout.addWidget(text)
        layout.addWidget(intro)

        self.roadmap_table = QTableWidget(len(ROADMAP_ITEMS), 6)
        self.roadmap_table.setObjectName("DataTable")
        self.roadmap_table.setHorizontalHeaderLabels(["Этап", "Название", "Цель", "Что делаем", "Готово когда", "Статус"])
        self.roadmap_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.roadmap_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.roadmap_table.setWordWrap(True)
        self.roadmap_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roadmap_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, item in enumerate(ROADMAP_ITEMS):
            values = [item["stage"], item["title"], item["goal"], item["work"], item["ready"], item["status"]]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column in (0, 5):
                    cell.setTextAlignment(Qt.AlignCenter)
                self.roadmap_table.setItem(row, column, cell)
        layout.addWidget(self.roadmap_table, 1)
        return page

    def build_passport_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        top = QFrame()
        top.setObjectName("Panel")
        top_layout = QVBoxLayout(top)
        title_row = QHBoxLayout()
        title = QLabel("Паспорт данных M1")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        apply_btn = QPushButton("Применить правки")
        apply_btn.clicked.connect(self.apply_passport_edits)
        save_btn = QPushButton("Сохранить каталог")
        save_btn.clicked.connect(self.save_recipe)
        export_btn = QPushButton("Экспорт паспорта CSV")
        export_btn.clicked.connect(self.export_passport_csv)
        title_row.addWidget(apply_btn)
        title_row.addWidget(save_btn)
        title_row.addWidget(export_btn)
        top_layout.addLayout(title_row)

        self.passport_summary = QTextEdit()
        self.passport_summary.setObjectName("DetailText")
        self.passport_summary.setReadOnly(True)
        self.passport_summary.setMaximumHeight(104)
        top_layout.addWidget(self.passport_summary)
        layout.addWidget(top)

        self.passport_table = QTableWidget(0, len(PASSPORT_COLUMNS))
        self.passport_table.setObjectName("DataTable")
        self.passport_table.setHorizontalHeaderLabels([label for _, label in PASSPORT_COLUMNS])
        self.passport_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.passport_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.passport_table.setWordWrap(True)
        self.passport_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.passport_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        for column, width in enumerate([120, 210, 110, 130, 160, 90, 95, 95, 95, 120, 210, 120, 100, 120, 130, 150, 220]):
            self.passport_table.setColumnWidth(column, width)
        layout.addWidget(self.passport_table, 1)
        return page

    def build_data_needs_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        top = QFrame()
        top.setObjectName("Panel")
        top_layout = QVBoxLayout(top)
        title_row = QHBoxLayout()
        title = QLabel("Потребность в данных")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        export_btn = QPushButton("Экспорт CSV")
        export_btn.clicked.connect(self.export_data_needs_csv)
        title_row.addWidget(export_btn)
        top_layout.addLayout(title_row)

        summary = QTextEdit()
        summary.setObjectName("DetailText")
        summary.setReadOnly(True)
        summary.setMaximumHeight(112)
        summary.setPlainText(
            "Это очередь добычи данных для роадмапа. D01-D08 скачаны, D15 скачан и гармонизирован, "
            "QC v0 завершён: 13 рядов допущены, 5 временно исключены. "
            "Матрица целей/горизонтов v0 готова; следующий поиск — D09-D10.\n\n"
            "Каждый найденный ряд добавляем в «Факторы», затем заполняем его паспорт в M1."
        )
        top_layout.addWidget(summary)
        layout.addWidget(top)

        self.data_needs_table = QTableWidget(len(DATA_NEEDS_ITEMS), len(DATA_NEEDS_COLUMNS))
        self.data_needs_table.setObjectName("DataTable")
        self.data_needs_table.setHorizontalHeaderLabels([label for _, label in DATA_NEEDS_COLUMNS])
        self.data_needs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.data_needs_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.data_needs_table.setWordWrap(True)
        self.data_needs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_needs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for column, width in enumerate([70, 80, 80, 120, 260, 170, 100, 110, 190, 300, 260, 130]):
            self.data_needs_table.setColumnWidth(column, width)
        for row, item in enumerate(DATA_NEEDS_ITEMS):
            for column, (key, _) in enumerate(DATA_NEEDS_COLUMNS):
                cell = QTableWidgetItem(str(item.get(key, "")))
                if key in {"need_id", "priority", "stage", "status"}:
                    cell.setTextAlignment(Qt.AlignCenter)
                self.data_needs_table.setItem(row, column, cell)
        layout.addWidget(self.data_needs_table, 1)
        return page

    def build_factors_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        form = QFrame()
        form.setObjectName("Panel")
        form_layout = QVBoxLayout(form)
        r1 = QHBoxLayout()
        self.factor_file = QLineEdit()
        self.factor_name = QLineEdit()
        self.factor_role = QComboBox()
        self.factor_role.addItems(list(ROLE_LABELS.values()))
        choose = QPushButton("Выбрать файл")
        choose.clicked.connect(self.choose_factor_file)
        add = QPushButton("Добавить фактор")
        add.clicked.connect(self.add_factor)
        r1.addWidget(QLabel("Файл"))
        r1.addWidget(self.factor_file, 2)
        r1.addWidget(choose)
        r1.addWidget(QLabel("Название"))
        r1.addWidget(self.factor_name, 1)
        r1.addWidget(QLabel("Роль"))
        r1.addWidget(self.factor_role)
        r1.addWidget(add)
        form_layout.addLayout(r1)
        r2 = QHBoxLayout()
        self.region_column = QComboBox()
        self.period_column = QComboBox()
        self.value_column = QComboBox()
        self.factor_transform = QComboBox()
        self.factor_transform.addItems(list(TRANSFORM_LABELS.values()))
        for label, combo in [("Регион", self.region_column), ("Период", self.period_column), ("Значение", self.value_column), ("Преобразование", self.factor_transform)]:
            r2.addWidget(QLabel(label))
            r2.addWidget(combo)
        form_layout.addLayout(r2)
        layout.addWidget(form)
        self.factors_table = QTableWidget(0, 7)
        self.factors_table.setObjectName("DataTable")
        self.factors_table.setHorizontalHeaderLabels(["ID", "Название", "Роль", "Преобразование", "Паспорт", "Файл", "Вкл."])
        self.factors_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.factors_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.factors_table, 1)
        return page

    def build_constructor_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        controls = QFrame()
        controls.setObjectName("Panel")
        row = QHBoxLayout(controls)
        self.term_factor = QComboBox()
        self.term_weight = QLineEdit("1.0")
        self.term_lag = QLineEdit("0")
        add_body = QPushButton("В тело")
        add_env = QPushButton("В среду")
        add_body.clicked.connect(lambda: self.add_recipe_term(ROLE_BODY))
        add_env.clicked.connect(lambda: self.add_recipe_term(ROLE_ENVIRONMENT))
        row.addWidget(QLabel("Фактор"))
        row.addWidget(self.term_factor)
        row.addWidget(QLabel("Вес"))
        row.addWidget(self.term_weight)
        row.addWidget(QLabel("Лаг"))
        row.addWidget(self.term_lag)
        row.addWidget(add_body)
        row.addWidget(add_env)
        layout.addWidget(controls)

        tables = QHBoxLayout()
        self.body_table = self.recipe_table("Тело индекса")
        self.env_table = self.recipe_table("Среда")
        self.transport_table = self.recipe_table("Транспорт")
        tables.addWidget(self.body_table)
        tables.addWidget(self.env_table)
        tables.addWidget(self.transport_table)
        layout.addLayout(tables, 1)

        transport = QFrame()
        transport.setObjectName("Panel")
        trow = QHBoxLayout(transport)
        self.transport_type = QComboBox()
        self.transport_type.addItems(list(TRANSPORT_LABELS.values()))
        self.transport_weight = QLineEdit("0.3")
        self.transport_lag = QLineEdit("1")
        add_transport = QPushButton("Добавить транспорт")
        add_transport.clicked.connect(self.add_transport)
        trow.addWidget(QLabel("Тип"))
        trow.addWidget(self.transport_type)
        trow.addWidget(QLabel("Вес"))
        trow.addWidget(self.transport_weight)
        trow.addWidget(QLabel("Лаг"))
        trow.addWidget(self.transport_lag)
        trow.addWidget(add_transport)
        layout.addWidget(transport)
        return page

    @staticmethod
    def recipe_table(title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Фактор", "Вес", "Лаг", "Преобразование"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setObjectName("DataTable")
        frame.table = table  # type: ignore[attr-defined]
        layout.addWidget(table, 1)
        return frame

    def build_auto_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        controls = QFrame()
        controls.setObjectName("Panel")
        row = QHBoxLayout(controls)
        self.auto_lag = QLineEdit("6")
        self.auto_terms = QLineEdit("5")
        run = QPushButton("Запустить автоподбор")
        run.clicked.connect(self.run_auto)
        manual = QPushButton("Рассчитать текущий рецепт")
        manual.clicked.connect(self.run_manual)
        row.addWidget(QLabel("Макс. лаг"))
        row.addWidget(self.auto_lag)
        row.addWidget(QLabel("Макс. факторов"))
        row.addWidget(self.auto_terms)
        row.addWidget(run)
        row.addWidget(manual)
        row.addStretch()
        layout.addWidget(controls)
        self.metrics = QTextEdit()
        self.metrics.setReadOnly(True)
        self.metrics.setObjectName("DetailText")
        layout.addWidget(self.metrics)
        self.sensitivity_summary = QTextEdit()
        self.sensitivity_summary.setReadOnly(True)
        self.sensitivity_summary.setObjectName("DetailText")
        self.sensitivity_summary.setMaximumHeight(126)
        layout.addWidget(self.sensitivity_summary)
        self.score_table = QTableWidget(0, 7)
        self.score_table.setHorizontalHeaderLabels(["Фактор", "Роль", "Лаг", "Транспорт", "Корреляция", "N", "Score"])
        self.score_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.score_table.setObjectName("DataTable")
        layout.addWidget(self.score_table, 1)
        return page

    def build_results_page(self) -> QWidget:
        page = QFrame()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        export = QPushButton("Экспорт CSV")
        export.clicked.connect(self.export_csv)
        actions.addWidget(export)
        actions.addStretch()
        layout.addLayout(actions)
        self.result_table = QTableWidget(0, 7)
        self.result_table.setHorizontalHeaderLabels(["Регион", "Период", "Тело", "Среда", "Транспорт", "Индекс", "Цель t+h"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setObjectName("DataTable")
        layout.addWidget(self.result_table, 1)
        return page

    def apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow {{ background: #fffafd; color: {TEXT}; }}
            #Sidebar {{ background: #fff3f8; border-right: 1px solid #efd5e1; }}
            #Logo {{ color: {TEXT}; font: 700 14px "Segoe UI"; padding: 8px; }}
            QPushButton, QToolButton {{
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                background: rgba(255,255,255,0.84);
                color: {TEXT};
            }}
            QPushButton:hover, QToolButton:hover {{ background: #fdeef6; }}
            QPushButton:checked {{
                background: {PINK_LIGHT};
                color: {PINK_DARK};
                font-weight: 600;
                border-color: #eac2d6;
            }}
            #Content {{ background: transparent; }}
            #Panel {{
                background: rgba(255,255,255,0.78);
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            #PageTitle {{ font: 700 18px "Segoe UI"; color: {TEXT}; }}
            #PageSubtitle, #StatusLabel, #SidebarStatus {{ color: {MUTED}; }}
            #SectionTitle {{ font: 700 12px "Segoe UI"; color: {TEXT}; }}
            QLineEdit, QComboBox {{
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 7px 10px;
                background: rgba(255,255,255,0.9);
            }}
            #LongInput {{ min-width: 520px; }}
            #DataTable {{
                background: rgba(255,255,255,0.72);
                border: 1px solid {BORDER};
                border-radius: 8px;
                gridline-color: #f2dce7;
            }}
            QHeaderView::section {{
                background: #fff2f7;
                color: {MUTED};
                padding: 8px;
                border: 0;
                border-bottom: 1px solid {BORDER};
            }}
            #DetailText {{
                background: rgba(255,255,255,0.72);
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 8px;
            }}
        """)

    def select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        titles = [
            ("Схема работы", "Визуальная блок-схема подбора и исследования индекса"),
            ("Роадмап", "Зафиксированный план исполнения лаборатории индекса"),
            ("Паспорт данных", "M1: управляемый каталог факторов и критерии допуска в подбор"),
            ("Потребность в данных", "Очередь наборов данных, которые нужно достать для M1-M5"),
            ("Факторы", "Каталог тела, среды, транспорта и целевой инфляции"),
            ("Конструктор индекса", "Ручная сборка рецепта: тело, среда и транспорт"),
            ("Автоподбор", "Автоматическая проверка кандидатов и сборка стартового рецепта"),
            ("Результаты", "Панель рассчитанного индекса и экспорт"),
        ]
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])
        for btn in self.nav_buttons:
            btn.setChecked(btn.index == index)

    def scheme_counts(self) -> Dict[str, str]:
        enabled = [f for f in self.factors if f.enabled]
        body_count = len([f for f in enabled if f.role == ROLE_BODY])
        env_count = len([f for f in enabled if f.role == ROLE_ENVIRONMENT])
        target_count = len([f for f in enabled if f.role == ROLE_TARGET])
        return {
            "data": f"{len(enabled)} факторов",
            "target": self.recipe.target_factor_id or f"{target_count} целей",
            "body": f"{body_count} в каталоге / {len(self.recipe.body_terms)} в рецепте",
            "environment": f"{env_count} в каталоге / {len(self.recipe.environment_terms)} в рецепте",
            "transport": f"{len(self.recipe.transport_terms)} слоёв",
            "recipe": f"{len(self.recipe.body_terms) + len(self.recipe.environment_terms)} факторов + {len(self.recipe.transport_terms)} транспорт",
            "output": "CSV / карта / отчёт",
        }

    def scheme_detail_text(self, step_id: str) -> str:
        step = next((item for item in SCHEME_STEPS if item[0] == step_id), SCHEME_STEPS[0])
        details = SCHEME_DETAILS.get(step_id, {})
        counts = self.scheme_counts()
        lines = [
            step[1],
            "",
            step[3],
            "",
            "Вход:",
            details.get("input", "Будет уточняться по мере добавления данных."),
            "",
            "Что делаем:",
            details.get("work", "Описываем операцию и проверяем её на данных."),
            "",
            "Выход:",
            details.get("output", "Получаем промежуточный результат для следующего блока."),
        ]
        if counts.get(step_id):
            lines.extend(["", f"Текущее состояние: {counts[step_id]}"])
        if step_id == "recipe":
            lines.extend([
                "",
                "Важно: ручной режим меняет этот рецепт. Автоматический режим записывает найденную версию в тот же формат.",
            ])
        return "\n".join(lines)

    def update_scheme_detail(self, step_id: str) -> None:
        self.scheme_detail.setPlainText(self.scheme_detail_text(step_id))

    def open_scheme_block(self, step_id: str) -> None:
        step = next((item for item in SCHEME_STEPS if item[0] == step_id), SCHEME_STEPS[0])
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{step[1]} — содержание блока")
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)
        title = QLabel(step[1])
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        body = QTextEdit()
        body.setObjectName("DetailText")
        body.setReadOnly(True)
        body.setPlainText(self.scheme_detail_text(step_id))
        layout.addWidget(body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def choose_factor_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите фактор", str(APP_DIR), "Data files (*.csv *.xlsx *.xls);;All files (*.*)")
        if not path:
            return
        self.factor_file.setText(path)
        self.factor_name.setText(Path(path).stem)
        try:
            columns = preview_columns(Path(path))
            for combo in [self.region_column, self.period_column, self.value_column]:
                combo.clear()
                combo.addItems(columns)
            lower = {c.lower(): c for c in columns}
            for keys, combo in [
                (["region", "регион", "fedstat_name"], self.region_column),
                (["period", "период", "date", "месяц"], self.period_column),
                (["value", "значение", "index", "индекс"], self.value_column),
            ]:
                for key in keys:
                    if key in lower:
                        combo.setCurrentText(lower[key])
                        break
        except Exception as exc:
            QMessageBox.warning(self, "Фактор", str(exc))

    def add_factor(self) -> None:
        name = self.factor_name.text().strip()
        path = self.factor_file.text().strip()
        if not name or not path:
            QMessageBox.information(self, "Фактор", "Выберите файл и укажите название фактора.")
            return
        existing = [f.factor_id for f in self.factors]
        factor = FactorSpec(
            factor_id=safe_id(name, existing),
            name=name,
            role=label_to_key(self.factor_role.currentText(), ROLE_LABELS, ROLE_BODY),
            source_path=path,
            region_column=self.region_column.currentText() or "region",
            period_column=self.period_column.currentText() or "period",
            value_column=self.value_column.currentText() or "value",
            transform=label_to_key(self.factor_transform.currentText(), TRANSFORM_LABELS, "period_zscore"),
            enabled=True,
            source_name=Path(path).name,
            frequency="месяц",
            level="регион",
            allowed_lags="0,1,2,3,6",
            quality_status="черновик",
            missing_policy="не проверено",
            passport_status="требует заполнения",
        )
        self.factors.append(factor)
        self.refresh_all()
        self.status_label.setText(f"Фактор добавлен: {factor.factor_id}")

    def add_recipe_term(self, role: str) -> None:
        factor_id = self.term_factor.currentText().strip()
        if not factor_id:
            return
        try:
            weight = float(self.term_weight.text().replace(",", "."))
            lag = int(float(self.term_lag.text().replace(",", ".")))
        except Exception:
            QMessageBox.warning(self, "Рецепт", "Вес и лаг должны быть числами.")
            return
        term = RecipeTerm(factor_id=factor_id, role=role, weight=weight, lag=max(0, lag))
        if role == ROLE_ENVIRONMENT:
            self.recipe.environment_terms.append(term)
        else:
            self.recipe.body_terms.append(term)
        self.refresh_recipe_tables()

    def add_transport(self) -> None:
        try:
            term = TransportTerm(
                transport_type=label_to_key(self.transport_type.currentText(), TRANSPORT_LABELS, "distance_inverse"),
                weight=float(self.transport_weight.text().replace(",", ".")),
                lag=max(0, int(float(self.transport_lag.text().replace(",", ".")))),
            )
        except Exception:
            QMessageBox.warning(self, "Транспорт", "Вес и лаг должны быть числами.")
            return
        self.recipe.transport_terms.append(term)
        self.refresh_recipe_tables()

    def sync_recipe(self) -> None:
        self.recipe.name = self.project_title.text().strip() or self.recipe.name
        self.recipe.target_factor_id = self.target_combo.currentText().strip()
        try:
            self.recipe.horizon = int(self.horizon_combo.currentText())
        except Exception:
            self.recipe.horizon = 1

    def run_manual(self) -> None:
        try:
            self.sync_recipe()
            result = compute_index(self.recipe, self.factors, REGION_REFERENCE_PATH)
            self.last_result_frame = result.frame
            self.show_metrics(result.metrics)
            self.refresh_result_table()
            self.status_label.setText("Ручной рецепт рассчитан")
            self.select_page(6)
        except Exception as exc:
            QMessageBox.critical(self, "Расчёт", str(exc))

    def run_auto(self) -> None:
        try:
            self.sync_recipe()
            recipe, scoreboard, metrics = auto_build_recipe(
                self.factors,
                self.recipe.target_factor_id,
                self.recipe.horizon,
                REGION_REFERENCE_PATH,
                max_lag=int(self.auto_lag.text() or "3"),
                max_terms=int(self.auto_terms.text() or "5"),
            )
            self.recipe = recipe
            self.last_scoreboard = scoreboard
            result = compute_index(self.recipe, self.factors, REGION_REFERENCE_PATH)
            self.last_result_frame = result.frame
            self.refresh_recipe_tables()
            self.refresh_score_table()
            self.refresh_result_table()
            self.show_metrics(metrics)
            self.status_label.setText("Автоподбор завершён")
            self.select_page(6)
        except Exception as exc:
            QMessageBox.critical(self, "Автоподбор", str(exc))

    def show_metrics(self, metrics: Dict[str, Any]) -> None:
        lines = [
            f"Рецепт: {metrics.get('recipe')}",
            f"Строк индекса: {metrics.get('rows')}",
            f"N проверки: {metrics.get('n_eval')}",
            f"Корреляция: {self.fmt(metrics.get('correlation'))}",
            f"RMSE z-score: {self.fmt(metrics.get('rmse_z'))}",
            f"Точность направления: {self.fmt(metrics.get('direction_accuracy'))}",
        ]
        self.metrics.setPlainText("\n".join(lines))

    def export_csv(self) -> None:
        if self.last_result_frame is None:
            QMessageBox.information(self, "Экспорт", "Сначала рассчитайте индекс.")
            return
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = DEFAULT_OUTPUT_DIR / "index_lab_result.csv"
        self.last_result_frame.to_csv(path, index=False, encoding="utf-8-sig")
        self.status_label.setText(f"Экспортировано: {path}")

    def save_recipe(self) -> None:
        self.sync_recipe()
        save_json(DEFAULT_RECIPE_PATH, recipe_to_dict(self.recipe))
        save_json(DEFAULT_CATALOG_PATH, factors_to_dict(self.factors))
        self.status_label.setText("Рецепт и каталог сохранены")

    def load_catalog(self, silent: bool = False) -> None:
        if not DEFAULT_CATALOG_PATH.exists():
            return
        try:
            self.factors = factors_from_dict(load_json(DEFAULT_CATALOG_PATH))
        except Exception:
            if not silent:
                raise

    def load_recipe(self, silent: bool = False) -> None:
        if not DEFAULT_RECIPE_PATH.exists():
            return
        try:
            self.recipe = recipe_from_dict(load_json(DEFAULT_RECIPE_PATH))
            self.project_title.setText(self.recipe.name)
        except Exception:
            if not silent:
                raise

    def refresh_all(self) -> None:
        ids = [f.factor_id for f in self.factors if f.enabled]
        self.target_combo.clear()
        self.target_combo.addItems(ids)
        if self.recipe.target_factor_id in ids:
            self.target_combo.setCurrentText(self.recipe.target_factor_id)
        self.term_factor.clear()
        self.term_factor.addItems(ids)
        self.refresh_factors_table()
        self.refresh_passport_table()
        self.refresh_recipe_tables()
        self.scheme.set_counts(self.scheme_counts())
        self.update_scheme_detail(self.scheme.selected_id)
        self.load_last_auto_outputs()

    def load_last_auto_outputs(self) -> None:
        if hasattr(self, "metrics") and AUTO_METRICS_PATH.exists():
            try:
                self.show_metrics(load_json(AUTO_METRICS_PATH))
            except Exception:
                pass
        if hasattr(self, "score_table") and AUTO_SCOREBOARD_PATH.exists():
            try:
                import pandas as pd

                self.last_scoreboard = pd.read_csv(AUTO_SCOREBOARD_PATH)
                self.refresh_score_table()
            except Exception:
                pass
        if hasattr(self, "sensitivity_summary") and AUTO_SENSITIVITY_PATH.exists():
            try:
                import pandas as pd

                frame = pd.read_csv(AUTO_SENSITIVITY_PATH)
                top = frame.sort_values("abs_correlation", ascending=False).head(5)
                lines = ["Матрица целей/горизонтов v0: лучшие сценарии"]
                for _, row in top.iterrows():
                    transport = row.get("selected_transport_terms", "")
                    if transport != transport:
                        transport = "без транспорта"
                    lines.append(
                        f"{row.get('target_factor_id')} h={int(row.get('horizon'))}: "
                        f"corr={float(row.get('correlation')):.3f}, "
                        f"dir={float(row.get('direction_accuracy')):.3f}, "
                        f"тело={row.get('top_body_candidate')} lag={int(row.get('top_body_lag'))}, "
                        f"{transport or 'без транспорта'}"
                    )
                self.sensitivity_summary.setPlainText("\n".join(lines))
            except Exception:
                pass

    def refresh_factors_table(self) -> None:
        self.factors_table.setRowCount(len(self.factors))
        for r, factor in enumerate(self.factors):
            values = [
                factor.factor_id,
                factor.name,
                key_to_label(factor.role, ROLE_LABELS),
                key_to_label(factor.transform, TRANSFORM_LABELS),
                factor.passport_status,
                factor.source_path,
                "да" if factor.enabled else "нет",
            ]
            for c, value in enumerate(values):
                self.factors_table.setItem(r, c, QTableWidgetItem(str(value)))

    def refresh_passport_table(self) -> None:
        if not hasattr(self, "passport_table"):
            return
        self.passport_table.setRowCount(len(self.factors))
        for row, factor in enumerate(self.factors):
            for column, (key, _) in enumerate(PASSPORT_COLUMNS):
                value = key_to_label(factor.role, ROLE_LABELS) if key == "role" else getattr(factor, key, "")
                cell = QTableWidgetItem(str(value))
                if key == "factor_id":
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.passport_table.setItem(row, column, cell)
        self.refresh_passport_summary()

    def refresh_passport_summary(self) -> None:
        if not hasattr(self, "passport_summary"):
            return
        total = len(self.factors)
        enabled = len([factor for factor in self.factors if factor.enabled])
        body = len([factor for factor in self.factors if factor.role == ROLE_BODY])
        environment = len([factor for factor in self.factors if factor.role == ROLE_ENVIRONMENT])
        target = len([factor for factor in self.factors if factor.role == ROLE_TARGET])
        needs_passport = len([
            factor for factor in self.factors
            if factor.passport_status.strip().lower() in {"", "требует заполнения", "черновик"}
        ])
        lines = [
            f"Факторов в каталоге: {total}, включено: {enabled}.",
            f"Слои: тело {body}, среда {environment}, цель {target}.",
            f"Требуют заполнения паспорта: {needs_passport}.",
            "Для M1 нужно заполнить источник, частоту, уровень, период, единицы, смысл value, ожидаемый знак, лаги, качество, пропуски и статус допуска.",
        ]
        self.passport_summary.setPlainText("\n".join(lines))

    def apply_passport_edits(self) -> None:
        if not hasattr(self, "passport_table"):
            return
        by_id = {factor.factor_id: factor for factor in self.factors}
        for row in range(self.passport_table.rowCount()):
            id_item = self.passport_table.item(row, 0)
            if id_item is None:
                continue
            factor = by_id.get(id_item.text().strip())
            if factor is None:
                continue
            for column, (key, _) in enumerate(PASSPORT_COLUMNS[1:], start=1):
                item = self.passport_table.item(row, column)
                value = item.text().strip() if item is not None else ""
                if key == "role":
                    factor.role = label_to_key(value, ROLE_LABELS, factor.role)
                else:
                    setattr(factor, key, value)
        self.refresh_all()
        self.status_label.setText("Правки паспорта применены к каталогу")

    def export_passport_csv(self) -> None:
        self.apply_passport_edits()
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = DEFAULT_OUTPUT_DIR / "index_lab_data_passport.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[key for key, _ in PASSPORT_COLUMNS])
            writer.writeheader()
            for factor in self.factors:
                row = {key: getattr(factor, key, "") for key, _ in PASSPORT_COLUMNS}
                row["role"] = key_to_label(factor.role, ROLE_LABELS)
                writer.writerow(row)
        self.status_label.setText(f"Паспорт экспортирован: {path}")

    def export_data_needs_csv(self) -> None:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = DEFAULT_OUTPUT_DIR / "index_lab_data_needs.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[key for key, _ in DATA_NEEDS_COLUMNS])
            writer.writeheader()
            for item in DATA_NEEDS_ITEMS:
                writer.writerow({key: item.get(key, "") for key, _ in DATA_NEEDS_COLUMNS})
        self.status_label.setText(f"Потребность в данных экспортирована: {path}")

    def refresh_recipe_tables(self) -> None:
        self.fill_recipe_table(self.body_table.table, self.recipe.body_terms)  # type: ignore[attr-defined]
        self.fill_recipe_table(self.env_table.table, self.recipe.environment_terms)  # type: ignore[attr-defined]
        self.fill_transport_table()
        self.scheme.set_counts(self.scheme_counts())

    @staticmethod
    def fill_recipe_table(table: QTableWidget, terms: List[RecipeTerm]) -> None:
        table.setRowCount(len(terms))
        for r, term in enumerate(terms):
            for c, value in enumerate([term.factor_id, term.weight, term.lag, term.transform or "по фактору"]):
                table.setItem(r, c, QTableWidgetItem(str(value)))

    def fill_transport_table(self) -> None:
        table = self.transport_table.table  # type: ignore[attr-defined]
        table.setRowCount(len(self.recipe.transport_terms))
        for r, term in enumerate(self.recipe.transport_terms):
            for c, value in enumerate([key_to_label(term.transport_type, TRANSPORT_LABELS), term.weight, term.lag, ""]):
                table.setItem(r, c, QTableWidgetItem(str(value)))

    def refresh_score_table(self) -> None:
        if self.last_scoreboard is None:
            return
        rows = self.last_scoreboard.head(1000)
        self.score_table.setRowCount(len(rows))
        cols = ["candidate", "role", "lag", "transport", "correlation", "n_eval", "score"]
        for r, (_, row) in enumerate(rows.iterrows()):
            for c, col in enumerate(cols):
                self.score_table.setItem(r, c, QTableWidgetItem(self.fmt(row.get(col))))

    def refresh_result_table(self) -> None:
        if self.last_result_frame is None:
            return
        rows = self.last_result_frame.head(1000)
        self.result_table.setRowCount(len(rows))
        cols = ["region", "period", "body", "environment", "transport", "index", "target_future"]
        for r, (_, row) in enumerate(rows.iterrows()):
            for c, col in enumerate(cols):
                self.result_table.setItem(r, c, QTableWidgetItem(self.fmt(row.get(col))))

    @staticmethod
    def fmt(value: Any) -> str:
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


def main() -> int:
    app = QApplication(sys.argv)
    window = IndexLabWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
