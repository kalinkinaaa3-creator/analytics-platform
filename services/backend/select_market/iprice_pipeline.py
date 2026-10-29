"""Select Market adapters for the existing master pipeline's ordered steps."""
from django.db import transaction
from django.db.models import Count
from organizations.models import Organization
from datasets.services.iprice_workspace import workspace_for, IPriceWorkspace
from datasets.services.parsers import base_parser, tt_product_parser, ps_product_parser, tara_jobs
from datasets.services.parsers.product_key_selector import get_active_classified_product_keys
from datasets.services.parsers.product_image_sync import sync_iprice_product_images
from datasets.services.parsers.queue_execution import enabled, register_master


def create_master(*, request_key=None, full_competitors=False):
    if not enabled():
        raise ValueError('Shared parser queue is disabled')
    with transaction.atomic():
        organization = Organization.objects.select_for_update().get(code='select-market')
        workspace = workspace_for(organization)
        model = workspace.model('ParserMasterPipelineRun')
        if request_key:
            previous = model.objects.filter(result__request_key=request_key).first()
            if previous:
                return previous
        existing = model.objects.exclude(status__in=('success', 'failed', 'cancelled')).order_by('id').first()
        if existing:
            if request_key:
                return None
            return existing
        run = model.objects.create(status='queued', result={
            'request_key': request_key, 'full_competitors': full_competitors,
        })
        register_master(run.pk, workspace=workspace)
        return run


def run_step(run, *, step_name, command_name, options):
    workspace = IPriceWorkspace('select-market')
    if run._meta.app_label != 'select_market':
        raise ValueError('Select Market run required')
    completed = list(run.result.get('completed_steps', []))
    if step_name in completed:
        return
    run.current_step = step_name
    run.save(update_fields=['current_step'])
    results = dict(run.result.get('source_results', {}))
    full = run.result.get('full_competitors', False)
    if full and step_name in ('base_parser', 'base_report'):
        return
    if command_name == 'load_base_products':
        result = base_parser.load_base_products(workspace=workspace)
        sync_iprice_product_images(source="base", workspace=workspace)
    elif command_name in ('load_tt_products', 'load_ps_products'):
        source = 'tt' if command_name == 'load_tt_products' else 'ps'
        parser = tt_product_parser.parse_tt_products if source == 'tt' else ps_product_parser.parse_ps_products
        if full:
            from datasets.services.parsers.tt_links import sync_tt_product_urls
            from datasets.services.parsers.ps_links import sync_ps_product_urls
            (sync_tt_product_urls if source == 'tt' else sync_ps_product_urls)(workspace=workspace)
        keys = None if full else get_active_classified_product_keys(source, workspace=workspace)
        result = parser(workspace=workspace, product_keys=keys, workers=1)
        sync_iprice_product_images(source=source, workspace=workspace)
        if result['failed']:
            run.result = {**run.result, 'source_results': {**results, step_name: result}}
            run.save(update_fields=['result'])
            raise RuntimeError(f'{source}: collection incomplete: {result}')
    elif command_name == 'load_tara_products':
        if full:
            options = {**options, 'classified_only': False, 'sitemap': not options.get('retry_failed', False)}
        child = tara_jobs.create_run(request_key=f'master:{run.pk}:{step_name}', origin='master',
            master_id=run.pk, workspace=workspace, options={**options, 'workers': 1})
        if child.status in ('failed', 'cancelled'):
            raise RuntimeError(child.error or 'Tara run stopped')
        if child.status != 'success':
            tara_jobs.kick()
            raise tara_jobs.TaraPending(f'Tara #{child.pk}: {child.status}')
        result = dict(child.items.values('status').annotate(n=Count('id')).values_list('status', 'n'))
    elif command_name.startswith('report_'):
        # Legacy report commands read Iplast tables; local results are retained on this run.
        result = {'stored_in_run': True}
    else:
        raise ValueError(f'Unsupported Select Market pipeline command: {command_name}')
    results[step_name] = result
    completed.append(step_name)
    run.result = {**run.result, 'completed_steps': completed, 'source_results': results}
    run.save(update_fields=['result'])
