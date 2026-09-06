from datetime import date

from rest_framework.exceptions import ValidationError


FILTER_KEYS = ("device", "search_engine", "region", "robotness")


def _date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "Ожидается дата в формате YYYY-MM-DD."})


def normalize_query(query_params):
    today = date.today()
    date_from = _date(query_params.get("date_from", f"{today.year}-01-01"), "date_from")
    date_to = _date(query_params.get("date_to", today.isoformat()), "date_to")
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 3660:
        raise ValidationError("Максимальный период отчёта — 10 лет.")

    result = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }
    try:
        landing_limit = int(query_params.get("landing_limit", 20))
    except (TypeError, ValueError):
        raise ValidationError({"landing_limit": "Количество страниц должно быть целым числом."})
    if landing_limit not in {10, 20, 30, 50, 100}:
        raise ValidationError({"landing_limit": "Допустимые значения: 10, 20, 30, 50 или 100."})
    result["landing_limit"] = landing_limit
    for key in (*FILTER_KEYS, "phrase_type", "product_category", "query_group"):
        values = [str(value).strip() for value in query_params.getlist(key) if str(value).strip()]
        if len(values) > 100:
            raise ValidationError({key: "Можно выбрать не более 100 значений."})
        if any(len(value) > 255 for value in values):
            raise ValidationError({key: "Значение фильтра не должно превышать 255 символов."})
        if key == "phrase_type" and any(
            value not in {"Брендовые", "Небрендовые", "Не определено"}
            for value in values
        ):
            raise ValidationError({key: "Передан неизвестный тип поисковой фразы."})
        result[key] = sorted(set(values))
    return result
