# Чувствительность автоподбора v0

Дата: 2026-07-30T20:14:23

Матрица показывает, как текущий набор тела и транспорта работает на разных целях и горизонтах.
Это не финальная модель, а диагностический слой: он отвечает, где уже есть сигнал и где нужно добывать новые данные.

## Все цели и горизонты

| target_factor_id | horizon | correlation | rmse_z | direction_accuracy | n_eval | top_body_candidate | top_body_lag | selected_transport_terms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| target_ipc_all | 1 | 0.1584 | 1.2974 | 0.5516 | 20999 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag4:0.35 |
| target_ipc_all | 2 | 0.0956 | 1.3449 | 0.5327 | 20914 | body_ipc_nonfood_broad | 0 | same_federal_district@lag2:0.35 |
| target_ipc_all | 3 | 0.0859 | 1.3521 | 0.5324 | 20829 | body_ipc_food_no_alcohol | 5 | distance_band_800@lag6:0.35 |
| target_ipc_all | 6 | 0.1692 | 1.289 | 0.5572 | 20164 | body_ipc_food_no_alcohol | 6 | distance_inverse@lag1:0.35 |
| target_ipc_food | 1 | 0.1539 | 1.3008 | 0.5478 | 20999 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag6:0.35 |
| target_ipc_food | 2 | 0.1186 | 1.3277 | 0.532 | 20829 | body_ipc_food_no_alcohol | 0 | same_federal_district@lag6:0.35 |
| target_ipc_food | 3 | 0.1144 | 1.3308 | 0.5323 | 20744 | body_ipc_food_no_alcohol | 4 | same_federal_district@lag6:0.35 |
| target_ipc_food | 6 | 0.1991 | 1.2656 | 0.5614 | 20489 | body_ipc_food_no_alcohol | 6 |  |
| target_ipc_nonfood | 1 | 0.0904 | 1.3488 | 0.5248 | 20999 | body_ipc_food_ex_veg_pot_fruit | 0 | same_federal_district@lag6:0.35 |
| target_ipc_nonfood | 2 | 0.0669 | 1.366 | 0.515 | 20914 | body_ipc_food_ex_veg_pot_fruit | 0 | same_federal_district@lag5:0.35 |
| target_ipc_nonfood | 3 | 0.0571 | 1.3732 | 0.5172 | 20829 | body_ipc_food_ex_veg_pot_fruit | 0 | same_federal_district@lag4:0.35 |
| target_ipc_nonfood | 6 | 0.0497 | 1.3786 | 0.5215 | 20574 | body_ipc_motor_fuel | 6 | same_federal_district@lag1:0.35 |
| target_ipc_services | 1 | 0.0664 | 1.3664 | 0.5123 | 20999 | body_ipc_passenger_transport | 2 | same_federal_district@lag6:0.35 |
| target_ipc_services | 2 | 0.0662 | 1.3666 | 0.5063 | 20914 | body_ipc_passenger_transport | 1 | distance_band_800@lag5:0.35 |
| target_ipc_services | 3 | 0.056 | 1.374 | 0.5053 | 20829 | body_ipc_passenger_transport | 0 | distance_band_800@lag5:0.35 |
| target_ipc_services | 6 | 0.0918 | 1.3477 | 0.5542 | 20322 | body_ipc_passenger_transport | 6 | distance_inverse@lag1:0.35 |

## Лучший горизонт по каждой цели

| target_factor_id | horizon | correlation | direction_accuracy | top_body_candidate | top_body_lag | selected_transport_terms |
| --- | --- | --- | --- | --- | --- | --- |
| target_ipc_all | 6 | 0.1692 | 0.5572 | body_ipc_food_no_alcohol | 6 | distance_inverse@lag1:0.35 |
| target_ipc_food | 6 | 0.1991 | 0.5614 | body_ipc_food_no_alcohol | 6 |  |
| target_ipc_nonfood | 1 | 0.0904 | 0.5248 | body_ipc_food_ex_veg_pot_fruit | 0 | same_federal_district@lag6:0.35 |
| target_ipc_services | 6 | 0.0918 | 0.5542 | body_ipc_passenger_transport | 6 | distance_inverse@lag1:0.35 |

## Общий рейтинг

| target_factor_id | horizon | correlation | direction_accuracy | top_overall_candidate | top_overall_role | top_overall_transport |
| --- | --- | --- | --- | --- | --- | --- |
| target_ipc_food | 6 | 0.1991 | 0.5614 | recipe_plus_transport | transport | distance_inverse |
| target_ipc_all | 6 | 0.1692 | 0.5572 | recipe_plus_transport | transport | distance_inverse |
| target_ipc_all | 1 | 0.1584 | 0.5516 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_food | 1 | 0.1539 | 0.5478 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_food | 2 | 0.1186 | 0.532 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_food | 3 | 0.1144 | 0.5323 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_all | 2 | 0.0956 | 0.5327 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_services | 6 | 0.0918 | 0.5542 | recipe_plus_transport | transport | distance_inverse |
| target_ipc_nonfood | 1 | 0.0904 | 0.5248 | recipe_plus_transport | transport | same_federal_district |
| target_ipc_all | 3 | 0.0859 | 0.5324 | recipe_plus_transport | transport | distance_band_800 |

## Интерпретация

- Если связь быстро падает на горизонтах 2/3/6, текущие факторы больше описывают совпадающее движение цен, чем ранний импульс.
- Если лучшими оказываются укрупненные ИПЦ-группы, тело индекса нужно дробить глубже: мясо, молоко, хлеб, овощи, импортозависимые товары.
- Если транспорт почти не меняет score, географическая матрица v0 слишком грубая и нужна логистика: дороги, грузооборот, ЖД, склады, топливо.
- Если направление около 0.5, индекс пока едва лучше случайного знака; это нормально для v0 без среды.

## Файлы

- `index_lab_output\auto_selection_v0_sensitivity.csv`
- `index_lab_output\auto_selection_v0_sensitivity/`