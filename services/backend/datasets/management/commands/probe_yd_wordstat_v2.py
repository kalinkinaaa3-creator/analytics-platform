"""One explicitly requested paid dynamics call, without saving statistics."""
import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from datasets.services.external_api.yd_wordstat_api_loader import get_configuration
from datasets.services.external_api.yd_wordstat_contract import parse_monthly_results, validate_group_tree
from datasets.services.external_api.yd_wordstat_search_api_client import fetch_dynamics, fetch_regions_tree


class Command(BaseCommand):
    help = "Paid v2 probe: one phrase and optional IPLAST group; saves quota usage only"

    def add_arguments(self, parser):
        parser.add_argument("--phrase", required=True)
        parser.add_argument("--from-date", required=True, type=date.fromisoformat)
        parser.add_argument("--to-date", required=True, type=date.fromisoformat)
        parser.add_argument("--group", default=None, help="Exact IPLAST group name")
        parser.add_argument("--device", choices=["all", "desktop", "phone", "tablet"], default="all")

    def handle(self, *args, **options):
        regions = None
        if options["group"]:
            config = get_configuration()
            groups = {item["name"]: item for item in config["groups"]}
            if options["group"] not in groups:
                raise CommandError("Unknown IPLAST group")
            validate_group_tree(config["groups"], fetch_regions_tree())
            regions = groups[options["group"]]["regions"]
        data = fetch_dynamics(
            options["phrase"], options["from_date"], options["to_date"],
            devices=[options["device"]], regions=regions,
        )
        rows = parse_monthly_results(data, options["from_date"], options["to_date"])
        self.stdout.write(json.dumps({
            "phrase": options["phrase"], "group": options["group"],
            "regions": regions, "statistics_saved": False, "results": rows,
        }, ensure_ascii=False, indent=2, default=str))
