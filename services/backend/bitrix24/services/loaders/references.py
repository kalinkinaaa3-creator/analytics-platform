from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixCrmField,
    BitrixDepartment,
    BitrixSyncRun,
    BitrixUser,
    BitrixUserDepartment,
)
from bitrix24.services.client import Bitrix24Client, Bitrix24ResponseError
from bitrix24.services.sync_state import (
    BitrixSyncStats,
    fail_sync,
    finish_sync,
    start_sync,
)

from .common import as_bool, as_int, source_value, text


def _upsert_page(model, objects, *, key_field: str, update_fields: tuple[str, ...]):
    if not objects:
        return 0, 0
    keys = [getattr(item, key_field) for item in objects]
    existing = set(
        model.objects.filter(**{f"{key_field}__in": keys}).values_list(
            key_field, flat=True
        )
    )
    model.objects.bulk_create(
        objects,
        update_conflicts=True,
        unique_fields=(key_field,),
        update_fields=update_fields,
    )
    return len(keys) - len(existing), len(existing)


def load_departments(
    client: Bitrix24Client,
    *,
    mode: str = BitrixSyncRun.Mode.FULL,
) -> BitrixSyncRun:
    run = start_sync("departments", mode)
    received = created = updated = 0
    try:
        for page in client.iter_pages("department.get", {"sort": "ID", "order": "ASC"}):
            seen_at = timezone.now()
            objects = []
            for row in page:
                department_id = as_int(source_value(row, "ID", "id"))
                if department_id is None:
                    raise Bitrix24ResponseError("Department row has no valid ID.")
                objects.append(
                    BitrixDepartment(
                        department_id=department_id,
                        name=text(source_value(row, "NAME", "name")),
                        parent_id=as_int(source_value(row, "PARENT", "parent")),
                        head_user_id=as_int(source_value(row, "UF_HEAD", "ufHead")),
                        sort=as_int(source_value(row, "SORT", "sort")),
                        last_seen_at=seen_at,
                        is_deleted=False,
                        raw_payload=row,
                    )
                )
            page_created, page_updated = _upsert_page(
                BitrixDepartment,
                objects,
                key_field="department_id",
                update_fields=(
                    "name",
                    "parent_id",
                    "head_user_id",
                    "sort",
                    "last_seen_at",
                    "is_deleted",
                    "raw_payload",
                    "date_update",
                ),
            )
            received += len(objects)
            created += page_created
            updated += page_updated

        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            if received == 0 and BitrixDepartment.objects.filter(is_deleted=False).exists():
                raise Bitrix24ResponseError("Empty department response; existing departments preserved")
            deactivated = BitrixDepartment.objects.filter(
                is_deleted=False,
            ).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True)
        finish_sync(
            run,
            stats=BitrixSyncStats(received, created, updated, deactivated),
        )
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def _department_ids(row: dict[str, Any]) -> list[int]:
    raw_ids = source_value(row, "UF_DEPARTMENT", "UF_DEPARTMENT_IDS", "ufDepartment", default=[])
    if not isinstance(raw_ids, (list, tuple)):
        raw_ids = [raw_ids]
    result = []
    for value in raw_ids:
        department_id = as_int(value)
        if department_id is not None and department_id not in result:
            result.append(department_id)
    return result


def _refresh_user_departments(user_ids: Iterable[int]) -> None:
    users = list(BitrixUser.objects.filter(user_id__in=user_ids))
    if not users:
        return
    departments = {
        item.department_id: item
        for item in BitrixDepartment.objects.filter(
            department_id__in={
                department_id
                for user in users
                for department_id in user.department_ids
            }
        )
    }
    BitrixUserDepartment.objects.filter(user__in=users).delete()
    links = []
    for user in users:
        for position, department_id in enumerate(user.department_ids):
            department = departments.get(department_id)
            if department is not None:
                links.append(
                    BitrixUserDepartment(
                        user=user,
                        department=department,
                        position=position,
                        is_primary=position == 0,
                    )
                )
    BitrixUserDepartment.objects.bulk_create(links)


def load_users(
    client: Bitrix24Client,
    *,
    mode: str = BitrixSyncRun.Mode.FULL,
) -> BitrixSyncRun:
    run = start_sync("users", mode)
    received = created = updated = 0
    try:
        for page in client.iter_pages("user.get", {"order": {"ID": "ASC"}}):
            seen_at = timezone.now()
            objects = []
            page_user_ids = []
            for row in page:
                user_id = as_int(source_value(row, "ID", "id"))
                if user_id is None:
                    raise Bitrix24ResponseError("User row has no valid ID.")
                department_ids = _department_ids(row)
                first_name = text(source_value(row, "NAME", "name"))
                last_name = text(source_value(row, "LAST_NAME", "lastName"))
                second_name = text(source_value(row, "SECOND_NAME", "secondName"))
                full_name = " ".join(
                    part for part in (last_name, first_name, second_name) if part
                )
                objects.append(
                    BitrixUser(
                        user_id=user_id,
                        active=as_bool(source_value(row, "ACTIVE", "active")) is not False,
                        first_name=first_name,
                        last_name=last_name,
                        second_name=second_name,
                        full_name=full_name,
                        email=text(source_value(row, "EMAIL", "email")),
                        work_position=text(source_value(row, "WORK_POSITION", "workPosition")),
                        department_ids=department_ids,
                        primary_department_id=department_ids[0] if department_ids else None,
                        last_seen_at=seen_at,
                        is_deleted=False,
                        raw_payload=row,
                    )
                )
                page_user_ids.append(user_id)
            with transaction.atomic():
                page_created, page_updated = _upsert_page(
                    BitrixUser,
                    objects,
                    key_field="user_id",
                    update_fields=(
                        "active",
                        "first_name",
                        "last_name",
                        "second_name",
                        "full_name",
                        "email",
                        "work_position",
                        "department_ids",
                        "primary_department_id",
                        "last_seen_at",
                        "is_deleted",
                        "raw_payload",
                        "date_update",
                    ),
                )
                _refresh_user_departments(page_user_ids)
            received += len(objects)
            created += page_created
            updated += page_updated

        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            if received == 0 and BitrixUser.objects.filter(is_deleted=False).exists():
                raise Bitrix24ResponseError("Empty user response; existing users preserved")
            deactivated = BitrixUser.objects.filter(
                is_deleted=False,
            ).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True, active=False)
        finish_sync(
            run,
            stats=BitrixSyncStats(received, created, updated, deactivated),
        )
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def load_crm_dictionaries(
    client: Bitrix24Client,
    *,
    entity_ids: tuple[str, ...] = ("STATUS", "SOURCE"),
    mode: str = BitrixSyncRun.Mode.FULL,
) -> BitrixSyncRun:
    run = start_sync("crm_dictionary", mode)
    received = created = updated = deactivated = 0
    try:
        for entity_id in entity_ids:
            seen_at = timezone.now()
            rows = list(
                client.iter_items(
                    "crm.status.list",
                    {"filter": {"ENTITY_ID": entity_id}},
                )
            )
            objects = []
            status_ids = []
            for row in rows:
                status_id = text(source_value(row, "STATUS_ID", "statusId"))
                if not status_id:
                    raise Bitrix24ResponseError("CRM dictionary row has no STATUS_ID.")
                status_ids.append(status_id)
                objects.append(
                    BitrixCrmDictionary(
                        entity_id=entity_id,
                        status_id=status_id,
                        name=text(source_value(row, "NAME", "name")),
                        sort=as_int(source_value(row, "SORT", "sort")),
                        semantics=text(source_value(row, "SEMANTICS", "semantics")),
                        last_seen_at=seen_at,
                        is_deleted=False,
                        raw_payload=row,
                    )
                )
            existing = set(
                BitrixCrmDictionary.objects.filter(
                    entity_id=entity_id,
                    status_id__in=status_ids,
                ).values_list("status_id", flat=True)
            )
            BitrixCrmDictionary.objects.bulk_create(
                objects,
                update_conflicts=True,
                unique_fields=("entity_id", "status_id"),
                update_fields=(
                    "name",
                    "sort",
                    "semantics",
                    "last_seen_at",
                    "is_deleted",
                    "raw_payload",
                    "date_update",
                ),
            )
            received += len(objects)
            created += len(objects) - len(existing)
            updated += len(existing)
            if mode == BitrixSyncRun.Mode.FULL:
                if not objects and BitrixCrmDictionary.objects.filter(entity_id=entity_id, is_deleted=False).exists():
                    raise Bitrix24ResponseError("Empty dictionary response; existing dictionary preserved")
                deactivated += BitrixCrmDictionary.objects.filter(
                    entity_id=entity_id,
                    is_deleted=False,
                ).filter(
                    Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
                ).update(is_deleted=True)
        finish_sync(
            run,
            stats=BitrixSyncStats(received, created, updated, deactivated),
        )
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def load_crm_fields(
    client: Bitrix24Client,
    *,
    entity_type_id: int = 1,
    mode: str = BitrixSyncRun.Mode.FULL,
) -> BitrixSyncRun:
    if entity_type_id not in (1, 2):
        raise ValueError("CRM fields support leads and deals only")
    entity = f"crm_fields_{entity_type_id}"
    run = start_sync(entity, mode)
    try:
        payload = (client.call("crm.lead.fields") if entity_type_id == 1
                   else client.call("crm.item.fields", {"entityTypeId": 2, "useOriginalUfNames": "Y"}))
        result = payload["result"]
        if entity_type_id == 2 and isinstance(result, dict):
            result = result.get("fields")
        if not isinstance(result, dict):
            raise Bitrix24ResponseError("CRM fields result must be an object.")
        seen_at = timezone.now()
        objects = []
        field_codes = []
        for field_code, row in result.items():
            if not isinstance(row, dict):
                continue
            field_codes.append(field_code)
            objects.append(
                BitrixCrmField(
                    entity_type_id=entity_type_id,
                    field_code=field_code,
                    title=text(source_value(row, "title", "formLabel", "listLabel")),
                    data_type=text(source_value(row, "type")),
                    is_multiple=as_bool(source_value(row, "isMultiple")) is True,
                    is_required=as_bool(source_value(row, "isRequired")) is True,
                    is_custom=field_code.upper().startswith("UF_CRM_"),
                    last_seen_at=seen_at,
                    is_deleted=False,
                    raw_payload=row,
                )
            )
        existing = set(
            BitrixCrmField.objects.filter(
                entity_type_id=entity_type_id,
                field_code__in=field_codes,
            ).values_list("field_code", flat=True)
        )
        BitrixCrmField.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=("entity_type_id", "field_code"),
            update_fields=(
                "title",
                "data_type",
                "is_multiple",
                "is_required",
                "is_custom",
                "last_seen_at",
                "is_deleted",
                "raw_payload",
                "date_update",
            ),
        )
        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            if not objects and BitrixCrmField.objects.filter(entity_type_id=entity_type_id, is_deleted=False).exists():
                raise Bitrix24ResponseError("Empty fields response; existing fields preserved")
            deactivated = BitrixCrmField.objects.filter(
                entity_type_id=entity_type_id,
                is_deleted=False,
            ).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True)
        finish_sync(
            run,
            stats=BitrixSyncStats(
                len(objects),
                len(objects) - len(existing),
                len(existing),
                deactivated,
            ),
        )
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise
