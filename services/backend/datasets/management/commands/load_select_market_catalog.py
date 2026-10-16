import json

from django.core.management.base import BaseCommand, CommandError
from organizations.models import Organization
from datasets.services.iprice_workspace import workspace_for
from datasets.services.parsers.base_parser import BaseParserError, load_base_products
from datasets.services.parsers.global_queue import QueueOwnershipError


class Command(BaseCommand):
    help = "Load Select Market YML into isolated tables through shared parser capacity"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        try:
            workspace = workspace_for(Organization.objects.get(code="select-market"))
            result = load_base_products(limit=options["limit"], workspace=workspace)
        except (BaseParserError, QueueOwnershipError, ValueError, Organization.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        # Image URLs are stored from YML; Iplast's local image cache is not used.
        self.stdout.write(json.dumps(result, ensure_ascii=False))
