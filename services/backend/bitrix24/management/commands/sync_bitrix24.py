from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from bitrix24.models import BitrixSyncRun
from bitrix24.services.client import Bitrix24Client
from bitrix24.services.loaders import (
    load_crm_dictionaries,
    load_crm_fields,
    load_departments,
    load_leads,
    load_stage_history,
    load_users,
)


LOADERS = {
    "departments": load_departments,
    "users": load_users,
    "dictionaries": load_crm_dictionaries,
    "fields": load_crm_fields,
    "leads": load_leads,
    "stage_history": load_stage_history,
}


def _datetime_option(value: str) -> datetime:
    parsed = parse_datetime(value)
    if parsed is None:
        raise CommandError(f"Invalid ISO datetime: {value}")
    return parsed


class Command(BaseCommand):
    help = "Synchronize one read-only Bitrix24 entity into PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("entity", choices=tuple(LOADERS))
        parser.add_argument(
            "--mode",
            choices=BitrixSyncRun.Mode.values,
            default=BitrixSyncRun.Mode.INCREMENTAL,
        )
        parser.add_argument("--date-from", type=_datetime_option)
        parser.add_argument("--date-to", type=_datetime_option)

    def handle(self, *args, **options):
        entity = options["entity"]
        mode = options["mode"]
        if entity not in {"leads", "stage_history"} and (
            options["date_from"] or options["date_to"]
        ):
            raise CommandError(
                "--date-from/--date-to are supported only for leads and stage_history."
            )

        client = Bitrix24Client()
        loader = LOADERS[entity]
        kwargs = {"mode": mode}
        if entity in {"leads", "stage_history"}:
            kwargs.update(
                date_from=options["date_from"],
                date_to=options["date_to"],
            )
        result = loader(client, **kwargs)
        run = result[0] if isinstance(result, tuple) else result
        self.stdout.write(
            self.style.SUCCESS(
                f"Bitrix24 {entity} sync completed: run={run.pk}, status=success."
            )
        )
