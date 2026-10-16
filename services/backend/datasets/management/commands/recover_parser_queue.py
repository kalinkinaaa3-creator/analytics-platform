import json

from django.core.management.base import BaseCommand, CommandError
from datasets.parser_queue_models import ParserQueueEntry
from datasets.services.parsers.global_queue import QueueOwnershipError
from datasets.services.parsers.queue_recovery import inspect_entry, recover_stopped


class Command(BaseCommand):
    help = "Inspect a parser slot; release only after confirmed shutdown of all associated workers"

    def add_arguments(self, parser):
        parser.add_argument("entry_id", type=int)
        parser.add_argument("--release", action="store_true")
        parser.add_argument("--workers-confirmed-stopped", action="store_true")
        parser.add_argument("--fingerprint", default="")
        parser.add_argument("--operator", default="")
        parser.add_argument("--reason", default="")

    def handle(self, *args, **options):
        try:
            if options["release"]:
                recover_stopped(options["entry_id"], expected_fingerprint=options["fingerprint"],
                    operator=options["operator"], reason=options["reason"],
                    workers_confirmed_stopped=options["workers_confirmed_stopped"])
            self.stdout.write(json.dumps(inspect_entry(options["entry_id"]), ensure_ascii=False))
        except (ParserQueueEntry.DoesNotExist, QueueOwnershipError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
