from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from bitrix24.models import BitrixLead, BitrixSyncRun
from bitrix24.services.client import Bitrix24Client, Bitrix24ResponseError
from bitrix24.services.sync_state import (
    BitrixSyncStats,
    fail_sync,
    finish_sync,
    get_incremental_from,
    start_sync,
)

from .common import (
    as_bool,
    as_datetime,
    as_decimal,
    as_int,
    source_value,
    text,
)
from .references import _upsert_page


LEAD_SELECT = (
    "ID",
    "TITLE",
    "NAME",
    "COMPANY_TITLE",
    "COMPANY_ID",
    "CONTACT_ID",
    "SOURCE_ID",
    "STATUS_ID",
    "STATUS_SEMANTIC_ID",
    "ASSIGNED_BY_ID",
    "CREATED_BY_ID",
    "MODIFY_BY_ID",
    "MOVED_BY_ID",
    "MOVED_TIME",
    "DATE_CREATE",
    "DATE_MODIFY",
    "DATE_CLOSED",
    "LAST_ACTIVITY_TIME",
    "OPPORTUNITY",
    "CURRENCY_ID",
    "IS_RETURN_CUSTOMER",
    "UF_CRM_1680165215489",
    "UF_CRM_1707131669360",
    "ORIGINATOR_ID",
    "ADDRESS_CITY",
    "ADDRESS_PROVINCE",
    "ADDRESS_COUNTRY",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
    "UTM_CONTENT",
    "UTM_TERM",
)


def _normalize_lead(row, *, seen_at):
    lead_id = as_int(source_value(row, "ID", "id"))
    if lead_id is None:
        raise Bitrix24ResponseError("Lead row has no valid ID.")

    return BitrixLead(
        lead_id=lead_id,
        title=text(source_value(row, "TITLE", "title")),
        name=text(source_value(row, "NAME", "name")),
        company_title=text(source_value(row, "COMPANY_TITLE", "companyTitle")),
        company_id=as_int(source_value(row, "COMPANY_ID", "companyId")),
        contact_id=as_int(source_value(row, "CONTACT_ID", "contactId")),
        source_id=text(source_value(row, "SOURCE_ID", "sourceId")),
        status_id=text(source_value(row, "STATUS_ID", "statusId")),
        status_semantic_id=text(
            source_value(row, "STATUS_SEMANTIC_ID", "statusSemanticId")
        ),
        assigned_by_id=as_int(source_value(row, "ASSIGNED_BY_ID", "assignedById")),
        created_by_id=as_int(source_value(row, "CREATED_BY_ID", "createdById")),
        updated_by_id=as_int(source_value(row, "MODIFY_BY_ID", "updatedById")),
        moved_by_id=as_int(source_value(row, "MOVED_BY_ID", "movedById")),
        moved_time=as_datetime(source_value(row, "MOVED_TIME", "movedTime")),
        source_created_at=as_datetime(source_value(row, "DATE_CREATE", "createdTime")),
        source_updated_at=as_datetime(source_value(row, "DATE_MODIFY", "updatedTime")),
        closed_time=as_datetime(source_value(row, "DATE_CLOSED", "closedTime")),
        last_activity_time=as_datetime(
            source_value(row, "LAST_ACTIVITY_TIME", "lastActivityTime")
        ),
        opportunity=as_decimal(source_value(row, "OPPORTUNITY", "opportunity")),
        currency_id=text(source_value(row, "CURRENCY_ID", "currencyId")),
        is_return_customer=as_bool(
            source_value(row, "IS_RETURN_CUSTOMER", "isReturnCustomer")
        ),
        project_id=text(source_value(row, "UF_CRM_1707131669360", "ufCrm1707131669360") or ""),
        activity_event_id=text(
            source_value(row, "UF_CRM_1680165215489", "ufCrm1680165215489")
        ),
        originator_id=text(source_value(row, "ORIGINATOR_ID", "originatorId")),
        address_city=text(source_value(row, "ADDRESS_CITY", "addressCity")),
        address_province=text(
            source_value(row, "ADDRESS_PROVINCE", "addressProvince")
        ),
        address_country=text(source_value(row, "ADDRESS_COUNTRY", "addressCountry")),
        utm_source=text(source_value(row, "UTM_SOURCE", "utmSource")),
        utm_medium=text(source_value(row, "UTM_MEDIUM", "utmMedium")),
        utm_campaign=text(source_value(row, "UTM_CAMPAIGN", "utmCampaign")),
        utm_content=text(source_value(row, "UTM_CONTENT", "utmContent")),
        utm_term=text(source_value(row, "UTM_TERM", "utmTerm")),
        last_seen_at=seen_at,
        is_deleted=False,
        raw_payload=row,
    )


def _max_source_position(current, lead: BitrixLead):
    if lead.source_updated_at is None:
        return current
    candidate = (lead.source_updated_at, lead.lead_id)
    if current is None or candidate > current:
        return candidate
    return current


def load_leads(
    client: Bitrix24Client,
    *,
    mode: str = BitrixSyncRun.Mode.INCREMENTAL,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    overlap: timedelta = timedelta(minutes=10),
) -> BitrixSyncRun:
    if mode not in BitrixSyncRun.Mode.values:
        raise ValueError(f"Unsupported Bitrix24 sync mode: {mode}.")

    is_window_reconciliation = mode == BitrixSyncRun.Mode.REPAIR
    if is_window_reconciliation:
        if created_from is None or created_to is None:
            raise ValueError("Repair mode requires created_from and created_to.")
        if created_to <= created_from:
            raise ValueError("created_to must be later than created_from.")
        if date_from is not None or date_to is not None:
            raise ValueError("Repair mode cannot use DATE_MODIFY boundaries.")
    elif created_from is not None or created_to is not None:
        raise ValueError("Creation boundaries are supported only in repair mode.")

    if date_from is None and mode == BitrixSyncRun.Mode.INCREMENTAL:
        date_from = get_incremental_from("leads", overlap)

    filters = {}
    if is_window_reconciliation:
        filters[">=DATE_CREATE"] = created_from.isoformat()
        filters["<DATE_CREATE"] = created_to.isoformat()
    elif date_from is not None:
        filters[">=DATE_MODIFY"] = date_from.isoformat()
    if date_to is not None:
        filters["<=DATE_MODIFY"] = date_to.isoformat()

    params = {
        "order": {"DATE_MODIFY": "ASC", "ID": "ASC"},
        "select": list(LEAD_SELECT),
    }
    if filters:
        params["filter"] = filters

    run = start_sync("leads", mode, source_updated_from=date_from)
    received = created = updated = 0
    max_source_position = None
    try:
        for page in client.iter_pages("crm.lead.list", params):
            seen_at = timezone.now()
            objects = [_normalize_lead(row, seen_at=seen_at) for row in page]
            page_created, page_updated = _upsert_page(
                BitrixLead,
                objects,
                key_field="lead_id",
                update_fields=(
                    "title",
                    "name",
                    "company_title",
                    "company_id",
                    "contact_id",
                    "source_id",
                    "status_id",
                    "status_semantic_id",
                    "assigned_by_id",
                    "created_by_id",
                    "updated_by_id",
                    "moved_by_id",
                    "moved_time",
                    "source_created_at",
                    "source_updated_at",
                    "closed_time",
                    "last_activity_time",
                    "opportunity",
                    "currency_id",
                    "is_return_customer",
                    "activity_event_id",
                    "project_id",
                    "originator_id",
                    "address_city",
                    "address_province",
                    "address_country",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                    "utm_content",
                    "utm_term",
                    "last_seen_at",
                    "is_deleted",
                    "raw_payload",
                    "date_update",
                ),
            )
            for lead in objects:
                max_source_position = _max_source_position(max_source_position, lead)
            received += len(objects)
            created += page_created
            updated += page_updated

        deactivated = 0
        if mode == BitrixSyncRun.Mode.FULL:
            deactivated = BitrixLead.objects.filter(
                is_deleted=False,
            ).filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True)
        elif is_window_reconciliation:
            window_queryset = BitrixLead.objects.filter(
                is_deleted=False,
                source_created_at__gte=created_from,
                source_created_at__lt=created_to,
            )
            if received == 0 and window_queryset.exists():
                raise Bitrix24ResponseError(
                    "Bitrix24 returned no leads for a non-empty reconciliation window."
                )
            deactivated = window_queryset.filter(
                Q(last_seen_at__lt=run.started_at) | Q(last_seen_at__isnull=True)
            ).update(is_deleted=True)

        finish_kwargs = {}
        if max_source_position is not None and not is_window_reconciliation:
            finish_kwargs = {
                "last_source_updated_at": max_source_position[0],
                "last_source_id": max_source_position[1],
            }
        finish_sync(
            run,
            stats=BitrixSyncStats(received, created, updated, deactivated),
            **finish_kwargs,
        )
        return run
    except BaseException as exc:
        fail_sync(run, exc)
        raise


def reconcile_leads_window(
    client: Bitrix24Client,
    *,
    created_from: datetime,
    created_to: datetime,
) -> BitrixSyncRun:
    return load_leads(
        client,
        mode=BitrixSyncRun.Mode.REPAIR,
        created_from=created_from,
        created_to=created_to,
    )
