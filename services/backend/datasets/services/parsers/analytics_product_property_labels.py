from __future__ import annotations

from copy import deepcopy


MATCH_PROPERTY_LABELS = {
    "material": "Материал",
    "color": "Цвет",
    "length": "Длина",
    "width": "Ширина",
    "height": "Высота",
    "volume": "Объём",
    "weight": "Вес",
    "diameter": "Диаметр",
    "base_diameter": "Диаметр основания",
    "thickness": "Толщина",
    "density": "Плотность",
    "bottom_type": "Тип дна",
    "walls_type": "Тип стенок",
    "insertion": "Вкладываемость",
    "support_type": "Тип опоры",
    "cover_included": "Крышка",
    "handles": "Ручки",
    "tap_included": "Кран",
    "drain_hole_included": "Сливное отверстие",
    "drain_hole_diameter": "Диаметр сливного отверстия",
    "opening_pedal_included": "Педаль открывания",
    "legs_included": "Ножки",
    "runner_included": "Полозья",
    "runner_number": "Количество полозьев",
    "wheel_included": "Колёса",
    "wheel_number": "Количество колёс",
    "wheel_diameter": "Диаметр колёс",
    "brake_included": "Тормоз",
}


def get_match_property_label(property_name: str) -> str:
    return MATCH_PROPERTY_LABELS.get(property_name, "Свойство товара")


def label_match_evidence(evidence: dict | None) -> dict:
    result = deepcopy(evidence or {})
    for property_name, values in result.items():
        if isinstance(values, dict):
            values["label"] = get_match_property_label(property_name)
    return result
