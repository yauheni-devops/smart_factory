"""Какие метрики слать для каждого типа площадки. Числа учебные, не с завода."""

import random

# профиль -> список (metric, unit, среднее, разброс)
PROFILES: dict[str, list[tuple[str, str, float, float]]] = {
    "workshop_power": [
        ("power_kw", "kW", 110.0, 25.0),
        ("voltage_v", "V", 400.0, 4.0),
        ("current_a", "A", 160.0, 20.0),
        ("temp_c", "C", 41.0, 3.0),
    ],
    "boiler_heat": [
        ("heat_mw", "MW", 2.4, 0.3),
        ("temp_supply_c", "C", 95.0, 3.0),
        ("temp_return_c", "C", 70.0, 3.0),
        ("pressure_bar", "bar", 6.0, 0.3),
    ],
    "warehouse_climate": [
        ("lighting_kw", "kW", 8.0, 1.5),
        ("temp_c", "C", 18.0, 1.5),
    ],
    "abk_building": [
        ("lighting_kw", "kW", 12.0, 2.0),
        ("temp_c", "C", 21.0, 1.0),
    ],
    "ktp_substation": [
        ("voltage_lv_v", "V", 400.0, 5.0),
        ("current_a", "A", 900.0, 80.0),
        ("power_kw", "kW", 620.0, 50.0),
        ("oil_temp_c", "C", 55.0, 4.0),
    ],
}


def sample(profile: str) -> list[tuple[str, float, str]]:
    specs = PROFILES.get(profile)
    if not specs:
        specs = [("power_kw", "kW", 10.0, 2.0)]
    out = []
    for metric, unit, mean, spread in specs:
        value = random.gauss(mean, spread)
        if metric.endswith("_kw") or metric.endswith("_mw") or metric.endswith("_a"):
            value = max(0.0, value)
        out.append((metric, round(value, 2), unit))
    return out
