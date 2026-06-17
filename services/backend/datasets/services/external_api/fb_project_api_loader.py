import logging
from datetime import date, datetime

from django.db import transaction

from datasets.models import FbProject
from datasets.services.external_api.fb_project_api_client import (
    fetch_fb_project_api_rows,
)


logger = logging.getLogger("external_api.fb_project")


TEXT_FIELDS = [
    "folder_lvl1",
    "folder_lvl2",
    "folder_lvl3",
    "project_name",
    "project_manager",
    "project_status",
    "project_type",
    "department",
    "subtask_id",
    "subtask_name",
    "subtask_responsible",
    "subtask_status",
    "predecessor",
    "code_sdr",
    "type_depend",
    "delay",
    "unit",
    "hier_subtask1",
    "hier_subtask2",
    "hier_subtask3",
    "hier_subtask4",
    "hier_subtask5",
    "hier_subtask6",
    "hier_subtask7",
    "hier_subtask8",
    "hier_subtask9",
    "hier_subtask10",
]


def clean_str(value, default="-"):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def clean_int(value, default=0):
    if value is None or value == "":
        return default

    try:
        return int(value)
    except Exception:
        return default


def clean_date(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value[:10] == "0001-01-01":
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except Exception:
            pass

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def calc_deviation(
    plan_start,
    plan_end,
    fact_start,
    fact_end,
    today,
):
    if plan_start and fact_start and plan_end and fact_end:
        if plan_start >= fact_start and plan_end >= fact_end:
            return "Выполнены в срок"

    if plan_start and plan_start > today:
        return "Срок выполнения еще не наступил"

    if fact_start and plan_start and plan_end and fact_end:
        if fact_start > plan_start and plan_start < today and plan_end >= fact_end:
            return "Начаты позднее запланированного срока, но окончены в срок (или ранее)"

    if fact_end and plan_end and plan_start and fact_start:
        if fact_end > plan_end and plan_end < today and plan_start >= fact_start:
            return "Окончены позднее запланированного срока, но начаты в срок (или ранее)"

    if fact_start and plan_start and fact_end and plan_end:
        if fact_start > plan_start and plan_start < today and fact_end > plan_end and plan_end < today:
            return "Просрочены"

    if plan_start and fact_start and plan_end:
        if plan_start >= fact_start and plan_start < today and plan_end > today:
            return "Начаты в срок, срок выполнения еще не наступил"

    if plan_start and fact_start and plan_end and fact_end is None:
        if plan_start >= fact_start and plan_start < today and plan_end <= today:
            return "Начаты в срок, фактический срок окончания не установлен"

    if plan_start and plan_end and fact_start is None:
        if plan_start < today and plan_end <= today:
            return "Фактический срок начала не установлен (плановый срок ранее текущей даты)"

    if plan_start and plan_end and fact_start is None:
        if plan_start < today and plan_end > today:
            return "Фактический срок начала не установлен (срок выполнения еще не наступил)"

    if fact_start and plan_start and plan_end:
        if fact_start > plan_start and plan_start < today and plan_end > today:
            return "Начаты позднее запланированного срока, срок выполнения еще не наступил"

    if fact_start and plan_start and plan_end and fact_end is None:
        if fact_start > plan_start and plan_start < today and plan_end <= today:
            return "Начаты позднее запланированного срока, фактический срок окончания не установлен"

    return "Статус не определен"


def normalize_record(record, today):
    start_date = clean_date(record.get("start_date"))
    end_date = clean_date(record.get("end_date"))

    subtask_start_date = clean_date(record.get("subtask_start_date"))
    subtask_end_date = clean_date(record.get("subtask_end_date"))

    if subtask_start_date is None:
        subtask_start_date = start_date

    if subtask_end_date is None:
        subtask_end_date = end_date

    actual_start_project = clean_date(record.get("actual_start_project"))
    actual_end_project = clean_date(record.get("actual_end_project"))
    actual_start_subtask = clean_date(record.get("actual_start_subtask"))
    actual_end_subtask = clean_date(record.get("actual_end_subtask"))

    return FbProject(
        folder_lvl1=clean_str(record.get("folder_lvl1")),
        folder_lvl2=clean_str(record.get("folder_lvl2")),
        folder_lvl3=clean_str(record.get("folder_lvl3")),
        project_name=clean_str(record.get("project_name")),
        project_manager=clean_str(record.get("project_manager")),
        start_date=start_date,
        end_date=end_date,
        project_status=clean_str(record.get("project_status")),
        project_type=clean_str(record.get("project_type")),
        department=clean_str(record.get("department")),
        subtask_id=clean_str(record.get("subtask_id")),
        subtask_name=clean_str(record.get("subtask_name")),
        subtask_responsible=clean_str(record.get("subtask_responsible")),
        subtask_start_date=subtask_start_date,
        subtask_end_date=subtask_end_date,
        actual_start_project=actual_start_project,
        actual_end_project=actual_end_project,
        actual_start_subtask=actual_start_subtask,
        actual_end_subtask=actual_end_subtask,
        subtask_status=clean_str(record.get("subtask_status")),
        number=clean_int(record.get("number_")),
        predecessor=clean_str(record.get("predecessor_")),
        code_sdr=clean_str(record.get("code_sdr")),
        type_depend=clean_str(record.get("type_depend_")),
        delay=clean_str(record.get("delay_")),
        unit=clean_str(record.get("unit_")),
        hier_subtask1=clean_str(record.get("hier_subtask1")),
        hier_subtask2=clean_str(record.get("hier_subtask2")),
        hier_subtask3=clean_str(record.get("hier_subtask3")),
        hier_subtask4=clean_str(record.get("hier_subtask4")),
        hier_subtask5=clean_str(record.get("hier_subtask5")),
        hier_subtask6=clean_str(record.get("hier_subtask6")),
        hier_subtask7=clean_str(record.get("hier_subtask7")),
        hier_subtask8=clean_str(record.get("hier_subtask8")),
        hier_subtask9=clean_str(record.get("hier_subtask9")),
        hier_subtask10=clean_str(record.get("hier_subtask10")),
        deviation=calc_deviation(
            subtask_start_date,
            subtask_end_date,
            actual_start_subtask,
            actual_end_subtask,
            today,
        ),
        deviation_project=calc_deviation(
            start_date,
            end_date,
            actual_start_project,
            actual_end_project,
            today,
        ),
    )


def load_fb_project_from_api(load_date: date | None = None):
    logger.info("FBProject API load started")

    today = date.today()

    rows = fetch_fb_project_api_rows(load_date=load_date)

    logger.info("FBProject API rows received: %s", len(rows))

    objects = [
        normalize_record(record, today=today)
        for record in rows
    ]

    logger.info("FBProject normalize finished: objects=%s", len(objects))

    with transaction.atomic():
        logger.info("FBProject PostgreSQL replace started")

        FbProject.objects.all().delete()
        FbProject.objects.bulk_create(objects, batch_size=5000)

        logger.info("FBProject PostgreSQL replace finished")

    logger.info(
        "FBProject API load finished: received=%s, saved=%s",
        len(rows),
        len(objects),
    )

    return {
        "received": len(rows),
        "saved": len(objects),
    }