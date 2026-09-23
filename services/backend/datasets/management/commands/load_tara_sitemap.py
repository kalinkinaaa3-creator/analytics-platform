import uuid
from django.core.management.base import BaseCommand, CommandError
from datasets.services.parsers.tara_jobs import create_run, kick, TaraPending


class Command(BaseCommand):
    help = 'Queue Tara sitemap synchronization through the Windows executor'

    def handle(self, *args, **options):
        try:
            run = create_run(request_key='sitemap:'+uuid.uuid4().hex, origin='cli',
                             options={'sitemap': True, 'sitemap_only': True})
        except TaraPending as exc:
            raise CommandError('Another Tara run is active') from exc
        kick()
        self.stdout.write(f'Tara sitemap #{run.pk}: queued. Progress in iPrice.')
