from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from bitrix24.models import BitrixDeal, BitrixDealCategory, BitrixSyncRun
from bitrix24.services.client import Bitrix24ResponseError
from bitrix24.services.sync_state import (
    BitrixSyncStats, start_sync, finish_sync, fail_sync, get_incremental_from,
)
from .common import as_bool, as_datetime, as_decimal, as_int, text
from .references import _upsert_page, load_crm_dictionaries


def _normalize_deal(row, seen_at):
    deal_id = as_int(row.get("id"))
    if deal_id is None or as_datetime(row.get("updatedTime")) is None:
        raise Bitrix24ResponseError("Deal has no valid ID or updatedTime")
    return BitrixDeal(
        deal_id=deal_id, title=text(row.get("title")),
        category_id=as_int(row.get("categoryId")), stage_id=text(row.get("stageId")),
        stage_semantic_id=text(row.get("stageSemanticId")),
        assigned_by_id=as_int(row.get("assignedById")), lead_id=as_int(row.get("leadId")),
        company_id=as_int(row.get("companyId")), contact_id=as_int(row.get("contactId")),
        contact_ids=row.get("contactIds") or [], opportunity=as_decimal(row.get("opportunity")),
        currency_id=text(row.get("currencyId")), source_id=text(row.get("sourceId")),
        source_created_at=as_datetime(row.get("createdTime")),
        source_updated_at=as_datetime(row.get("updatedTime")),
        begin_date=as_datetime(row.get("begindate")), close_date=as_datetime(row.get("closedate")),
        closed=(as_bool(row.get("closed")) is True if row.get("closed") is not None
                else row.get("stageSemanticId") in {"S", "F"}),
        raw_payload=row, last_seen_at=seen_at, is_deleted=False,
    )


def load_deals(client, *, mode=BitrixSyncRun.Mode.INCREMENTAL,
               date_from=None, date_to=None, created_from=None, created_to=None,
               overlap=timedelta(minutes=10)):
    if mode not in BitrixSyncRun.Mode.values:
        raise ValueError("Unsupported deal loading mode")
    repair = mode == BitrixSyncRun.Mode.REPAIR
    if repair:
        if created_from is None or created_to is None or created_to <= created_from:
            raise ValueError("Repair requires a valid creation window")
        if date_from is not None or date_to is not None:
            raise ValueError("Repair cannot use modification boundaries")
    elif created_from is not None or created_to is not None:
        raise ValueError("Creation boundaries require repair mode")
    if mode == BitrixSyncRun.Mode.FULL and (date_from or date_to):
        raise ValueError("Full deal loading cannot have date limits")
    if date_from is None and mode == BitrixSyncRun.Mode.INCREMENTAL:
        date_from = get_incremental_from("deals", overlap)
    filters = {}
    if repair:
        filters[">=createdTime"] = created_from.isoformat()
        filters["<createdTime"] = created_to.isoformat()
    if date_from is not None:
        filters[">=updatedTime"] = date_from.isoformat()
    if date_to is not None:
        filters["<=updatedTime"] = date_to.isoformat()
    params = {"entityTypeId": 2, "useOriginalUfNames": "Y", "select": ["*"],
              "order": {"updatedTime": "ASC", "id": "ASC"}, "filter": filters}
    run = start_sync("deals", mode, source_updated_from=date_from)
    received = created = updated = 0
    position = None
    update_fields = tuple(f.name for f in BitrixDeal._meta.fields
                          if f.name not in {"id", "deal_id", "date_add"})
    try:
        for page in client.iter_pages("crm.item.list", params):
            objects = [_normalize_deal(row, timezone.now()) for row in page]
            new, changed = _upsert_page(BitrixDeal, objects, key_field="deal_id", update_fields=update_fields)
            received += len(objects)
            created += new
            updated += changed
            for item in objects:
                candidate = (item.source_updated_at, item.deal_id)
                position = max(position, candidate) if position else candidate
        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            unseen = BitrixDeal.objects.filter(is_deleted=False).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True))
            if received == 0 and unseen.exists():
                raise Bitrix24ResponseError("Empty full deal response; existing deals preserved")
            deactivated = unseen.update(is_deleted=True)
        if repair:
            window = BitrixDeal.objects.filter(is_deleted=False,
                source_created_at__gte=created_from, source_created_at__lt=created_to)
            if received == 0 and window.exists():
                raise Bitrix24ResponseError("Empty deal reconciliation response; existing deals preserved")
            deactivated = window.filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True)
        cursor = dict(last_source_updated_at=position[0], last_source_id=position[1]) if position and not repair else {}
        finish_sync(run, stats=BitrixSyncStats(received, created, updated, deactivated), **cursor)
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def load_deal_categories(client, *, mode=BitrixSyncRun.Mode.FULL):
    run = start_sync("deal_categories", mode)
    received = created = updated = 0
    try:
        for page in client.iter_pages("crm.category.list", {"entityTypeId": 2}):
            objects = []
            for row in page:
                category_id = as_int(row.get("id"))
                if category_id is None:
                    raise Bitrix24ResponseError("Deal category has no valid ID")
                objects.append(BitrixDealCategory(category_id=category_id, name=text(row.get("name")),
                    sort=as_int(row.get("sort")), is_default=as_bool(row.get("isDefault")) is True,
                    raw_payload=row, last_seen_at=timezone.now(), is_deleted=False))
            new, changed = _upsert_page(BitrixDealCategory, objects, key_field="category_id",
                update_fields=("name", "sort", "is_default", "raw_payload", "last_seen_at", "is_deleted", "date_update"))
            received += len(objects)
            created += new
            updated += changed
        if not received:
            raise Bitrix24ResponseError("No deal categories returned; existing references preserved")
        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            deactivated = BitrixDealCategory.objects.filter(is_deleted=False).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)).update(is_deleted=True)
        finish_sync(run, stats=BitrixSyncStats(received, created, updated, deactivated))
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def load_deal_stages(client, *, mode=BitrixSyncRun.Mode.FULL):
    categories = list(BitrixDealCategory.objects.filter(is_deleted=False).values_list("category_id", flat=True))
    if not categories:
        raise ValueError("Load deal categories before their stages")
    return load_crm_dictionaries(client, mode=mode, entity_ids=tuple(
        "DEAL_STAGE" if category == 0 else f"DEAL_STAGE_{category}" for category in categories))
