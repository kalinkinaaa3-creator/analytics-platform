import json
from django.core.management.base import BaseCommand, CommandError
from organizations.models import Organization
from datasets.services.iprice_workspace import workspace_for
from datasets.services.parsers.tara_jobs import create_run, dispatch, progress, TaraPending


class Command(BaseCommand):
    help = 'Create a durable Select Market Tara run using the shared Windows executor'

    def add_arguments(self, parser):
        parser.add_argument('--request-key', required=True)
        parser.add_argument('--sync-links', action='store_true')
        parser.add_argument('--limit', type=int)
        parser.add_argument('--workers', type=int, default=1)

    def handle(self, *args, **options):
        try:
            workspace = workspace_for(Organization.objects.get(code='select-market'))
            key = options['request_key'].strip()
            if not key or len(key) > 200:
                raise ValueError('request-key must contain 1 to 200 characters')
            run = create_run(request_key=key, workspace=workspace, options={
                'sitemap': options['sync_links'], 'limit': options['limit'], 'workers': options['workers']})
            dispatch(workspace=workspace)
        except (ValueError, TaraPending, Organization.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        run.refresh_from_db()
        self.stdout.write(json.dumps(progress(run), ensure_ascii=False, default=str))
