from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Parse Tara product cards through Playwright browser service"

    def add_arguments(self, parser):
        parser.add_argument("--master-run-id", type=int)
        parser.add_argument("--step-key", default="tara_parser")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--workers", type=int, default=None)
        parser.add_argument("--retry-failed", action="store_true")

        parser.add_argument(
            "--retry-blocked",
            action="store_true",
            help="After main pass, retry only blocked Tara products",
        )

        parser.add_argument(
            "--retry-blocked-delay",
            type=int,
            default=300,
        )

        parser.add_argument(
            "--retry-blocked-rounds",
            type=int,
            default=1,
        )

        parser.add_argument(
            "--classified-only",
            action="store_true",
            help=(
                "Parse only active Tara product_key values "
                "from active product classification"
            ),
        )

    def handle(self, *args, **options):
        import uuid
        from django.core.management.base import CommandError
        from datasets.services.parsers.tara_jobs import create_run, kick, TaraPending
        master = options.get("master_run_id")
        key = f"master:{master}:{options['step_key']}" if master else f"cli:{uuid.uuid4().hex}"
        try:
            run = create_run(request_key=key, origin="master" if master else "cli", master_id=master,
                             options={k: options[k] for k in ("limit", "workers", "classified_only", "retry_failed")})
        except TaraPending:
            if master:
                raise
            raise CommandError("Another Tara run is active. See iPrice for progress.") from None
        if run.status in ("failed", "cancelled"):
            raise CommandError(run.error or "Tara run stopped")
        if run.status == "success":
            return
        kick()
        if master:
            raise TaraPending(f"Tara #{run.pk}: {run.status}")
        self.stdout.write(f"Tara #{run.pk}: {run.status}. Background job; progress/session upload in iPrice.")
        if options["retry_blocked"]:
            self.stdout.write("Blocked requests now wait for a new session (4 hours); blind retries are disabled.")
