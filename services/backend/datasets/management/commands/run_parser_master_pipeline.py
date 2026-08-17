from django.core.management.base import BaseCommand, CommandError

from datasets.models import ParserMasterPipelineRun
from datasets.services.parsers.master_pipeline import (
    ParserMasterPipelineError,
    run_parser_master_pipeline,
)


class Command(BaseCommand):
    help = "Run complete parser master pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--run-id",
            type=int,
            required=True,
        )

    def handle(self, *args, **options):
        run_id = options["run_id"]

        if not ParserMasterPipelineRun.objects.filter(
            pk=run_id,
        ).exists():
            raise CommandError(
                f"ParserMasterPipelineRun id={run_id} not found"
            )

        try:
            result = run_parser_master_pipeline(
                run_id=run_id,
            )

        except ParserMasterPipelineError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Parser master pipeline completed: "
                f"run_id={result['run_id']}, "
                f"status={result['status']}"
            )
        )