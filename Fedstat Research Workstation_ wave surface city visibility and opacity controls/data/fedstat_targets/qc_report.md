# QC-отчет D01-D08 и первый автоподбор v0

Дата: 2026-07-30T20:14:23

## Что сделано

- Региональная панель считается по гармонизированным 85 субъектам.
- Сырые Fedstat CSV не изменены.
- Целевые ряды Fedstat 31074 переведены в `period_zscore`, потому что исходное значение уже является процентом к предыдущему месяцу.
- В каталог факторов добавлены производные body-кандидаты `body_ipc_nonfood_broad` и `body_ipc_services_broad`.
- Короткие исторические ряды 2002-2006 и авиа с экстремумами временно исключены из автоподбора v0.
- Первый автоподбор запущен против `target_ipc_food`, горизонт 1 месяц, лаги 0-6.

## Решения QC

| qc_decision | auto_ready | count |
| --- | --- | --- |
| exclude_auto_v0 | no | 5 |
| ready_target | yes | 4 |
| ready_with_warning | yes | 9 |

## Горизонты целей

| target_factor_id | horizon | future_rows | future_regions | period_min | period_max |
| --- | --- | --- | --- | --- | --- |
| target_ipc_all | 1 | 20999 | 85 | 2002-01 | 2022-12 |
| target_ipc_all | 2 | 20914 | 85 | 2002-01 | 2022-11 |
| target_ipc_all | 3 | 20829 | 85 | 2002-01 | 2022-10 |
| target_ipc_all | 6 | 20574 | 85 | 2002-01 | 2022-07 |
| target_ipc_food | 1 | 20999 | 85 | 2002-01 | 2022-12 |
| target_ipc_food | 2 | 20914 | 85 | 2002-01 | 2022-11 |
| target_ipc_food | 3 | 20829 | 85 | 2002-01 | 2022-10 |
| target_ipc_food | 6 | 20574 | 85 | 2002-01 | 2022-07 |
| target_ipc_nonfood | 1 | 20999 | 85 | 2002-01 | 2022-12 |
| target_ipc_nonfood | 2 | 20914 | 85 | 2002-01 | 2022-11 |
| target_ipc_nonfood | 3 | 20829 | 85 | 2002-01 | 2022-10 |
| target_ipc_nonfood | 6 | 20574 | 85 | 2002-01 | 2022-07 |
| target_ipc_services | 1 | 20999 | 85 | 2002-01 | 2022-12 |
| target_ipc_services | 2 | 20914 | 85 | 2002-01 | 2022-11 |
| target_ipc_services | 3 | 20829 | 85 | 2002-01 | 2022-10 |
| target_ipc_services | 6 | 20574 | 85 | 2002-01 | 2022-07 |

## Оставшиеся флаги после гармонизации

Всего флагов: 26.

| factor_id | region | period | value |
| --- | --- | --- | --- |
| body_ipc_air_transport | Амурская область | 2013-03 | 200.11 |
| body_ipc_air_transport | Вологодская область | 2008-07 | 205.71 |
| body_ipc_air_transport | Вологодская область | 2010-02 | 48.61 |
| body_ipc_air_transport | Кабардино-Балкарская Республика | 2021-09 | 49.37 |
| body_ipc_air_transport | Калининградская область | 2011-09 | 37.96 |
| body_ipc_air_transport | Курганская область | 2020-09 | 49.51 |
| body_ipc_air_transport | Республика Алтай | 2020-08 | 222.17 |
| body_ipc_air_transport | Республика Алтай | 2021-07 | 205.93 |
| body_ipc_air_transport | Республика Дагестан | 2019-08 | 213.5 |
| body_ipc_air_transport | Республика Дагестан | 2020-09 | 40.68 |
| body_ipc_air_transport | Республика Дагестан | 2022-07 | 204.63 |
| body_ipc_air_transport | Республика Ингушетия | 2019-05 | 48.73 |

## Автоподбор v0

- Цель: `target_ipc_food`.
- Корреляция: `0.1539450428532057`.
- N проверки: `20999`.
- RMSE z-score: `1.300780278830301`.
- Точность направления: `0.5477879899042811`.

Выбранные body-термы:

| factor_id | weight | lag | transform |
| --- | --- | --- | --- |
| body_ipc_food_no_alcohol | 1.0 | 0 | period_zscore |
| body_ipc_food_ex_veg_pot_fruit | 0.7406 | 0 | period_zscore |
| body_ipc_food_no_alcohol | -0.4472 | 1 | period_zscore |
| body_ipc_food_no_alcohol | -0.422 | 6 | period_zscore |
| body_ipc_food_no_alcohol | -0.4116 | 2 | period_zscore |

Транспортные термы:

| transport_type | weight | lag | power | max_distance_km |
| --- | --- | --- | --- | --- |
| same_federal_district | 0.35 | 6 | 1.0 | 0.0 |

Топ кандидатов:

| candidate | role | lag | transport | correlation | n_eval | score |
| --- | --- | --- | --- | --- | --- | --- |
| recipe_plus_transport | transport | 6 | same_federal_district | 0.1539450428532057 | 20999 | 0.1539450428532057 |
| recipe_plus_transport | transport | 3 | distance_band_800 | 0.1536184016255832 | 20999 | 0.1536184016255832 |
| recipe_plus_transport | transport | 6 | distance_band_800 | 0.1534856444387299 | 20999 | 0.1534856444387299 |
| recipe_plus_transport | transport | 3 | same_federal_district | 0.15344942381916724 | 20999 | 0.15344942381916724 |
| recipe_plus_transport | transport | 6 | distance_inverse | 0.15297173255960686 | 20999 | 0.15297173255960686 |
| recipe_plus_transport | transport | 3 | distance_inverse | 0.1528103752123688 | 20999 | 0.1528103752123688 |
| recipe_plus_transport | transport | 2 | distance_band_800 | 0.15220559239570763 | 20999 | 0.15220559239570763 |
| recipe_plus_transport | transport | 5 | distance_inverse | 0.15137755793736785 | 20999 | 0.15137755793736785 |
| recipe_plus_transport | transport | 4 | distance_inverse | 0.15123192983969735 | 20999 | 0.15123192983969735 |
| recipe_plus_transport | transport | 2 | distance_inverse | 0.15112211492852629 | 20999 | 0.15112211492852629 |
| recipe_plus_transport | transport | 4 | same_federal_district | 0.15020546165834545 | 20999 | 0.15020546165834545 |
| recipe_plus_transport | transport | 2 | same_federal_district | 0.1501826471491999 | 20999 | 0.1501826471491999 |
| recipe_plus_transport | transport | 1 | distance_inverse | 0.14974871007152737 | 20999 | 0.14974871007152737 |
| recipe_plus_transport | transport | 4 | distance_band_800 | 0.14947338267963722 | 20999 | 0.14947338267963722 |
| recipe_plus_transport | transport | 5 | same_federal_district | 0.14945051070009702 | 20999 | 0.14945051070009702 |

## Разведка целей и горизонтов

Дополнительно прогнаны все целевые ряды на горизонтах 1, 2, 3 и 6 месяцев.

| target_factor_id | horizon | correlation | direction_accuracy | top_body_candidate | top_body_lag | selected_transport_terms |
| --- | --- | --- | --- | --- | --- | --- |
| target_ipc_food | 6 | 0.1991 | 0.5614 | body_ipc_food_no_alcohol | 6 |  |
| target_ipc_all | 6 | 0.1692 | 0.5572 | body_ipc_food_no_alcohol | 6 | distance_inverse@lag1:0.35 |
| target_ipc_all | 1 | 0.1584 | 0.5516 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag4:0.35 |
| target_ipc_food | 1 | 0.1539 | 0.5478 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag6:0.35 |
| target_ipc_food | 2 | 0.1186 | 0.532 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag6:0.35 |
| target_ipc_food | 3 | 0.1144 | 0.5323 | body_ipc_food_no_alcohol | 4 | same_federal_district@lag6:0.35 |
| target_ipc_all | 2 | 0.0956 | 0.5327 | body_ipc_nonfood_broad | 0 | same_federal_district@lag2:0.35 |
| target_ipc_services | 6 | 0.0918 | 0.5542 | body_ipc_passenger_transport | 6 | distance_inverse@lag1:0.35 |

## Выходные файлы

- `data\fedstat_targets\qc_decisions.csv`
- `data\fedstat_targets\target_horizon_check.csv`
- `data\fedstat_targets\quality_summary_subjects.csv`
- `data\fedstat_targets\quality_flags_subjects.csv`
- `index_lab_output\auto_selection_v0_scoreboard.csv`
- `index_lab_output\auto_selection_v0_recipe.json`
- `index_lab_output\auto_selection_v0_metrics.json`
- `index_lab_output\auto_selection_v0_result.csv`
- `index_lab_output\auto_selection_v0_sensitivity.csv`
- `index_lab_output\auto_selection_v0_sensitivity.md`