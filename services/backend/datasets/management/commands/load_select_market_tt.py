import json

from django.core.management.base import BaseCommand, CommandError
from organizations.models import Organization
from datasets.services.iprice_workspace import workspace_for
from datasets.services.parsers.global_queue import QueueOwnershipError
from select_market.iprice_competitors import collect_competitor


def load_tt(*, workspace, limit=None, workers=1, sync_links=False):
    return collect_competitor("tt", workspace=workspace, limit=limit, workers=workers, sync_links=sync_links)


class Command(BaseCommand):
    source = "tt"
    help = "Collect Select Market TT data through shared parser capacity"

    def add_arguments(self, parser):
        parser.add_argument("--sync-links", action="store_true")
        parser.add_argument("--limit", type=int)
        parser.add_argument("--workers", type=int, default=1)

    def handle(self, *args, **options):
        try:
            workspace = workspace_for(Organization.objects.get(code="select-market"))
            result = collect_competitor(self.source, workspace=workspace, limit=options["limit"], workers=options["workers"], sync_links=options["sync_links"])
        except (QueueOwnershipError, ValueError, RuntimeError, Organization.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
