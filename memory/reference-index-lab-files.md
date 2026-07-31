---
name: reference-index-lab-files
description: "Как запускать лабораторию индекса и где лежат ключевые файлы, данные и результаты"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 581760c9-5644-4311-9349-9efc4ed41895
  modified: 2026-07-31T16:41:59.647Z
---

Корень: `C:\Projects\_NOU_2026\Fedstat Research Workstation_ wave surface city visibility and opacity controls`.

**Запуск лаборатории (с интерактивной блок-схемой конвейера):** `index_lab_qt_app.py` (точка входа `main()` ~стр. 1822) или батник `run_index_lab.bat`. Блок-схема — класс `FlowSchemeWidget`; этапы конвейера в `SCHEME_STEPS`/`SCHEME_LINKS` (данные→шоки→тело/среда/транспорт→лаги→оценка→рецепт→проверка→результат). НЕ путать с `main.py` — это отдельная Fedstat Workstation (карта РФ + волновая поверхность инфляции).

**Ключевой код:** `index_lab_core.py` (ядро расчётов), `index_lab_qc.py` (QC + автоподбор), `fedstat_lab_downloader.py` (headless-загрузка Fedstat 31074), `region_harmonizer.py` (104 Fedstat-имени → 85 субъектов РФ).

**Данные:** `data/fedstat_targets/processed/` — целевые ряды `target_ipc_*` и кандидаты тела `body_ipc_*`; `data/fedstat_targets/*.csv|md` — отчёты QC; `data/geo/` — гео-слой (границы ADM1 geoBoundaries, справочники регионов, маппинг Fedstat). **Результаты автоподбора v0:** `index_lab_output/auto_selection_v0_*` + матрица 4 цели×4 горизонта в `index_lab_output/auto_selection_v0_sensitivity/`. **Рабочий рецепт:** `settings/index_lab_recipe.json`.

Стек: Python 3.12, PySide6/Qt + WebView, Plotly, MapLibre GL JS. Зависимости — `requirements.txt`. См. [[project-fedstat-impulse-index]].
