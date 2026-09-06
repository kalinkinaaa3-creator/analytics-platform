import logging
from datetime import date, timedelta

from django.db.models import Max


logger = logging.getLogger("external_api.yd_wordstat")


DEFAULT_START_DATE = date(2018, 1, 1)
MONTHS_TO_RELOAD = 12




def get_previous_month_last_day(today: date | None = None) -> date:
    today = today or date.today()
    first_day_current_month = today.replace(day=1)

    return first_day_current_month - timedelta(days=1)


def get_reload_from_date(
    today: date | None = None,
    months_to_reload: int = MONTHS_TO_RELOAD,
) -> date:
    today = today or date.today()

    first_day_current_month = today.replace(day=1)
    current = first_day_current_month - timedelta(days=1)

    for _ in range(months_to_reload - 1):
        current = current.replace(day=1) - timedelta(days=1)

    return current.replace(day=1)


def get_next_month_first_day(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)

    return date(value.year, value.month + 1, 1)


def get_reload_period_without_delete(
    model,
    filters: dict,
    today: date | None = None,
    months_to_reload: int = MONTHS_TO_RELOAD,
):
    """
    Безопасная версия старой логики:
    1. Определяем дату, с которой нужно переудалять последние 12 месяцев.
    2. MAX(date) считаем только по данным ДО этого периода.
    3. Удаление здесь НЕ делаем.
    4. Удаление выполняется позже, только после успешного ответа API.
    """

    today = today or date.today()

    reload_from_date = get_reload_from_date(
        today=today,
        months_to_reload=months_to_reload,
    )

    max_date = (
        model.objects
        .filter(**filters)
        .exclude(date__gte=reload_from_date)
        .aggregate(max_date=Max("date"))
    )["max_date"]

    if max_date is None:
        date_start = DEFAULT_START_DATE
    else:
        date_start = get_next_month_first_day(max_date)

    date_finish = get_previous_month_last_day(today=today)

    logger.info(
        "YD Wordstat reload period prepared without delete: "
        "model=%s, filters=%s, reload_from=%s, max_date=%s, date_start=%s, date_finish=%s",
        model.__name__,
        filters,
        reload_from_date,
        max_date,
        date_start,
        date_finish,
    )

    return {
        "reload_from_date": reload_from_date,
        "max_date": max_date,
        "date_start": date_start,
        "date_finish": date_finish,
        "skipped": date_start > date_finish,
    }
