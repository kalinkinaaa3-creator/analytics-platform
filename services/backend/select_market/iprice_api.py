from django.db import transaction
from django.http import HttpResponse
from django.urls import path
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboards.models import Dashboard
from dashboards.services.access import user_can_edit_dashboard, user_can_view_dashboard
from .iprice_prices import PriceImportError, import_price_file


class PriceFileView(APIView):
    organization_aware = True
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        organization = request.organization
        if organization.code != "select-market":
            raise PermissionDenied("Доступно только в Селект Маркете.")
        dashboard = Dashboard.objects.filter(organization=organization, component="suc").first()
        allowed = user_can_view_dashboard if request.method in ('GET', 'HEAD', 'OPTIONS') else user_can_edit_dashboard
        if dashboard is None or not allowed(request.user, dashboard):
            raise PermissionDenied("Нет доступа к управлению ценами.")
        self.dashboard = dashboard

    def get(self, request):
        from .iprice_templates import export_template
        output = export_template('price')
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="select_market_prices.xlsx"'
        return response

    def post(self, request):
        file = request.FILES.get("file")
        if file is None or not file.name.lower().endswith(".xlsx"):
            raise ValidationError("Выберите файл XLSX.")
        if file.size > 10 * 1024 * 1024:
            raise ValidationError("Размер файла не должен превышать 10 МБ.")
        try:
            batch = import_price_file(file.read(), filename=file.name, user=request.user, organization=request.organization,
                                      price_date=request.data.get('price_date'))
        except PriceImportError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({"date": batch.date, "rows": batch.rows, "revision": batch.revision, "vat_included": True})


class SourceFileView(PriceFileView):
    def get(self, request, kind):
        from .iprice_templates import export_template
        from .iprice_sources import LOADERS
        if kind not in LOADERS:
            raise ValidationError("Неизвестный тип источника.")
        output = export_template(kind)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="select_market_{kind}.xlsx"'
        return response

    def post(self, request, kind):
        from .iprice_sources import import_source
        file = request.FILES.get("file")
        if file is None or file.size > 10 * 1024 * 1024:
            raise ValidationError("Выберите XLSX размером не более 10 МБ.")
        try:
            result = import_source(file.read(), kind=kind, filename=file.name, user=request.user, organization=request.organization)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result)


class SourcesStatusView(PriceFileView):
    http_method_names = ['get', 'head', 'options']
    def get(self, request):
        from .iprice_models import IPriceSourceImport, IPricePriceImport
        from django.db.models import Max
        from .iprice_domain_models import ParserMasterPipelineRun
        from datasets.services.parsers.queue_execution import enabled
        from datasets.services.parsers.global_queue import queue_status
        run = ParserMasterPipelineRun.objects.order_by('-id').first()
        return Response({
            'can_edit': user_can_edit_dashboard(request.user, self.dashboard),
            'parsers_enabled': enabled(),
            'imports': list(IPriceSourceImport.objects.filter(id__in=IPriceSourceImport.objects.values('kind').annotate(last=Max('id')).values('last')).order_by('-id').values('id', 'kind', 'filename', 'created_at')),
            'price_imports': list(IPricePriceImport.objects.order_by('-date_add').values('id', 'filename', 'date', 'rows', 'revision', 'date_add')[:10]),
            'queue': queue_status(organization=request.organization) if enabled() else [],
            'run': {'id': run.pk, 'status': run.status, 'step': run.current_step,
                    'started_at': run.started_at, 'finished_at': run.finished_at,
                    'completed_steps': run.result.get('completed_steps', [])} if run else None,
        })


class HealthView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        from .iprice_health import health_report
        from rest_framework import serializers
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page', 1))
        level = serializers.ChoiceField(choices=['', 'error', 'warning']).run_validation(request.query_params.get('level', ''))
        section = serializers.CharField(allow_blank=True, max_length=100).run_validation(request.query_params.get('section', ''))
        if set(section.split(',')) - {'', 'sources', 'snapshot'}:
            raise ValidationError('Неизвестный раздел проверки.')
        all_results = serializers.BooleanField().run_validation(request.query_params.get("all_results", False))
        return Response(health_report(page=page, level=level, section=section, page_size=None if all_results else 50,
            search=request.query_params.get('search', '')[:200], code=request.query_params.get('code', '')[:200]))


class ReviewExportView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, kind):
        from rest_framework import serializers
        from .iprice_review_export import review_workbook
        kind = serializers.ChoiceField(choices=['parser_products', 'preparation_check']).run_validation(kind)
        response = HttpResponse(review_workbook(kind), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="select_market_{kind}.xlsx"'
        response['Cache-Control'] = 'private, no-store'
        return response


class CalculationStartView(PriceFileView):
    from rest_framework.parsers import JSONParser
    parser_classes = [JSONParser]
    http_method_names = ['post', 'options']

    def post(self, request):
        from rest_framework import serializers
        from django.db import transaction
        from django.utils import timezone
        from datasets.services.iprice_workspace import workspace_for
        from datasets.services.iprice_snapshot_builder import create_iprice_snapshot, IPriceSnapshotBuildError
        from datasets.services.iprice_snapshot_launcher import launch_iprice_snapshot
        from .iprice_domain_models import IPriceSnapshot
        day = serializers.DateField().run_validation(request.data.get('calculation_date'))
        if day > timezone.localdate():
            raise ValidationError('Дата расчёта не может быть в будущем.')
        workspace = workspace_for(request.organization)
        try:
            with transaction.atomic():
                snapshot = create_iprice_snapshot(calculation_date=day, created_by=request.user,
                    parameters={'source': 'select_market_ui', 'current_step': 'queued'}, workspace=workspace)

                def launch():
                    try:
                        launch_iprice_snapshot(snapshot_id=snapshot.pk, workspace=workspace)
                    except Exception:
                        import logging
                        logging.getLogger('iprice.select_market').exception('Cannot start calculation %s', snapshot.pk)
                        IPriceSnapshot.objects.filter(pk=snapshot.pk, status='building').update(
                            status='failed', error='Не удалось запустить обработчик расчёта.', finished_at=timezone.now())
                transaction.on_commit(launch)
        except IPriceSnapshotBuildError as exc:
            raise ValidationError('Предыдущий расчёт ещё не завершён. Дождитесь результата или обратитесь к администратору.') from exc
        return Response({'id': snapshot.pk, 'status': 'building'}, status=202)


class SnapshotListView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        from .iprice_domain_models import IPriceSnapshot
        from django.db.models import Count, Q
        rows = list(IPriceSnapshot.objects.annotate(
            products_count=Count('products', distinct=True), regions_count=Count('products__regions', distinct=True),
            errors_count=Count('products__regions', filter=Q(products__regions__calculation_status='error'), distinct=True)
        ).order_by('-version_number').values(
            'id', 'calculation_date', 'version_number', 'revision_for_date', 'status', 'is_current', 'is_active', 'was_active', 'parameters',
            'created_at', 'created_by__username', 'activated_at', 'activated_by__username', 'products_count', 'regions_count', 'errors_count', 'error')[:50])
        from .iprice_domain_models import IPriceSnapshotRegion
        historical = set(IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot_id__in=[row['id'] for row in rows])
                         .exclude(historical_variant='').values_list('snapshot_product__snapshot_id', flat=True).distinct())
        for row in rows:
            row['edit_revision'] = row.pop('parameters').get('edit_revision', 0)
            row['historical_routes'] = row['id'] in historical
        return Response(rows)


class SnapshotActivateView(PriceFileView):
    http_method_names = ['post', 'delete', 'options']
    from rest_framework.parsers import JSONParser
    parser_classes = [JSONParser]

    def post(self, request, snapshot_id):
        from django.shortcuts import get_object_or_404
        from datasets.services.iprice_snapshot_builder import activate_iprice_snapshot, IPriceSnapshotBuildError
        from .iprice_domain_models import IPriceSnapshot
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        from rest_framework import serializers
        revision = serializers.IntegerField(min_value=0).run_validation(request.data.get('expected_revision'))
        try:
            snapshot = activate_iprice_snapshot(snapshot=snapshot, activated_by=request.user, expected_revision=revision)
        except IPriceSnapshotBuildError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({'id': snapshot.pk, 'is_active': snapshot.is_active,
                         'activated_at': snapshot.activated_at})

    def delete(self, request, snapshot_id):
        from django.shortcuts import get_object_or_404
        from datasets.services.iprice_snapshot_builder import deactivate_iprice_snapshot, IPriceSnapshotBuildError
        from .iprice_domain_models import IPriceSnapshot
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        try:
            snapshot = deactivate_iprice_snapshot(snapshot=snapshot, deactivated_by=request.user)
        except IPriceSnapshotBuildError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({'id': snapshot.pk, 'is_active': False})


class SnapshotExportView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    @transaction.atomic
    def get(self, request, snapshot_id):
        from django.shortcuts import get_object_or_404
        from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
        from datasets.services.iprice_workspace import workspace_for
        from datasets.services.iprice_snapshot_export import export_iprice_snapshot_to_excel
        from .iprice_domain_models import IPriceSnapshot
        _lock_snapshot_workspace(workspace_for(request.organization))
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        if snapshot.status != 'success':
            raise ValidationError('Выгрузка доступна после завершения расчёта.')
        try:
            output = export_iprice_snapshot_to_excel(snapshot=snapshot)
        except ValueError as exc:
            raise ValidationError('В версии отсутствуют строки для выгрузки.') from exc
        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        output.close()
        response['Content-Disposition'] = f'attachment; filename="select_market_iprice_v{snapshot.version_number}_{snapshot.calculation_date}.xlsx"'
        response['Cache-Control'] = 'private, no-store'
        return response


class SnapshotFiltersView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id):
        from django.shortcuts import get_object_or_404
        from .iprice_domain_models import IPriceSnapshot
        from .iprice_filters import filter_options, query_filters, comparison_products
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        products = snapshot.products.all()
        from .iprice_row_controls import RowControls, filter_rows
        from .iprice_domain_models import IPriceSnapshotRegion
        controls = RowControls(data=request.query_params)
        controls.is_valid(raise_exception=True)
        if 'comparison_id' in request.query_params:
            from rest_framework import serializers
            comparison_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['comparison_id'])
            if comparison_id == snapshot.pk or snapshot.status != 'success':
                raise ValidationError('Выберите две разные успешно рассчитанные версии.')
            base = get_object_or_404(IPriceSnapshot, pk=comparison_id, status='success')
            products = comparison_products(base=base, comparison=snapshot)
        elif controls.validated_data['zone'] or controls.validated_data['problems_only']:
            from .iprice_row_controls import regional_product_summaries
            scoped_rows = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot)
            try:
                regions = query_filters(request.query_params).get('sale_region')
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if regions:
                scoped_rows = scoped_rows.filter(sale_region__in=regions)
            summaries = regional_product_summaries(scoped_rows) if regions and controls.validated_data['mode'] == 'products' else None
            scoped_rows = filter_rows(scoped_rows, controls.validated_data, summaries=summaries)
            products = products.filter(pk__in=scoped_rows.values('snapshot_product_id'))
        try:
            return Response(filter_options(products, query_filters(request.query_params),
                                           request.query_params.get('search', '')[:200]))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class SnapshotRowsView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id):
        from django.shortcuts import get_object_or_404
        from django.core.paginator import Paginator, EmptyPage
        from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        try:
            page = int(request.query_params.get('page', 1))
            if page < 1:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValidationError('Некорректный номер страницы.') from None
        from django.db.models import Prefetch, Q, Max
        from .iprice_domain_models import IPriceSnapshotApproval
        from datasets.services.iprice_snapshot_export import get_effective_prices
        rows = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).annotate(last_approval_revision=Max('approvals__revision')).select_related('snapshot_product').prefetch_related(
            Prefetch('approvals', queryset=IPriceSnapshotApproval.objects.filter(is_current=True).select_related('approved_by').order_by('-revision', '-id'), to_attr='prefetched_current_approvals')).order_by('id')
        search = request.query_params.get('search', '').strip()[:200]
        if request.query_params.get('product_id'):
            from rest_framework import serializers
            product_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['product_id'])
            rows = rows.filter(snapshot_product_id=product_id)
        from .iprice_filters import filter_products, query_filters
        try:
            rows = filter_products(rows, query_filters(request.query_params), prefix='snapshot_product__')
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if search:
            rows = rows.filter(Q(snapshot_product__code_1c__icontains=search) | Q(snapshot_product__nom__icontains=search))
        for field in ('sale_region', 'calculation_status'):
            if request.query_params.get(field):
                rows = rows.filter(**{field: request.query_params[field]})
        from .iprice_row_controls import RowControls, filter_rows
        controls = RowControls(data=request.query_params)
        controls.is_valid(raise_exception=True)
        from .iprice_row_controls import regional_product_summaries
        scoped_summaries = regional_product_summaries(rows) if (
            controls.validated_data['mode'] == 'products' and
            (query_filters(request.query_params).get('sale_region') or request.query_params.get('sale_region'))
        ) else None
        rows = filter_rows(rows, controls.validated_data, summaries=scoped_summaries)
        grouped = controls.validated_data['mode'] == 'products'
        ordering = request.query_params.get('ordering', 'nom')
        field = ordering.lstrip('-')
        allowed = {'nom', 'market', 'current', 'final', 'status', 'sale_region', 'deviation', 'margin'}
        if field not in allowed or (grouped and field in {'sale_region', 'margin'}):
            raise ValidationError('Некорректная сортировка.')
        direction = '-' if ordering.startswith('-') else ''
        from django.db.models import Case, When, Value, F, FloatField, ExpressionWrapper
        def metric(queryset, price, market):
            expression = ExpressionWrapper(F(price) * Value(1.0) / F(market) - Value(1.0), output_field=FloatField())
            return queryset.annotate(_sort_metric=Case(When(**{market + '__gt': 0, price + '__isnull': False}, then=expression), default=None, output_field=FloatField()))
        if grouped:
            path = {'nom': 'nom', 'market': 'competitor_rrp_median', 'current': 'current_retail_median',
                    'final': 'effective_approved_rrp_median', 'status': 'calculation_status', 'deviation': '_sort_metric'}[field]
            products_query = snapshot.products.filter(pk__in=rows.values('snapshot_product_id'))
            if field == 'deviation':
                products_query = metric(products_query, 'effective_approved_rrp_median', 'competitor_rrp_median')
            items = products_query.order_by(direction + path, 'pk').values_list('pk', flat=True)
            if scoped_summaries is not None and field in {'market', 'current', 'final', 'deviation'}:
                from datasets.services.iprice_price_analytics import _deviation
                def scoped_value(pk):
                    summary = scoped_summaries[pk]
                    return (_deviation(summary['effective_approved_rrp_median'], summary['competitor_rrp_median'])
                            if field == 'deviation' else summary[path])
                ids = sorted(items)
                items = sorted((pk for pk in ids if scoped_value(pk) is not None),
                               key=scoped_value, reverse=bool(direction))
                items += [pk for pk in ids if scoped_value(pk) is None]
        else:
            from datasets.services.iprice_price_analytics import _with_effective_approved_rrp
            rows = _with_effective_approved_rrp(rows)
            path = {'nom': 'snapshot_product__nom', 'market': 'regional_competitor_rrp_median', 'current': 'current_retail',
                    'final': 'effective_approved_rrp', 'status': 'calculation_status', 'sale_region': 'sale_region', 'deviation': '_sort_metric', 'margin': '_sort_metric'}[field]
            if field == 'deviation':
                rows = metric(rows, 'effective_approved_rrp', 'regional_competitor_rrp_median')
            elif field == 'margin':
                rows = metric(rows, 'cost_with_logistics', 'effective_approved_rrp').annotate(_sort_metric=-F('_sort_metric'))
            items = rows.order_by(direction + path, 'pk')
        from rest_framework import serializers
        page_size = serializers.ChoiceField(choices=[25, 50, 100]).run_validation(request.query_params.get('page_size', 50))
        paginator = Paginator(items, page_size)
        try:
            result = paginator.page(page)
        except EmptyPage:
            raise ValidationError('Страница не найдена.') from None
        if grouped:
            product_order = list(result)
            result = rows.filter(snapshot_product_id__in=product_order).order_by('snapshot_product_id', 'sale_region', 'id')
        payload = []
        product_summaries = {}
        from datasets.services.iprice_price_analytics import classify_price_zone, _deviation, get_active_price_zone_config
        from datasets.services.iprice_workspace import IPriceWorkspace
        zone_config = get_active_price_zone_config(workspace=IPriceWorkspace('select-market'))
        for row in result:
            if grouped and row.snapshot_product_id not in product_summaries:
                product_summaries[row.snapshot_product_id] = {field: getattr(row.snapshot_product, field) for field in (
                    'current_retail_median', 'effective_approved_rrp_median', 'competitor_rrp_median', 'competitor_count',
                    'pricing_method', 'calculation_status', 'warning_codes', 'error_codes')}
                product_summaries[row.snapshot_product_id]['zone'] = classify_price_zone(_deviation(
                    row.snapshot_product.effective_approved_rrp_median, row.snapshot_product.competitor_rrp_median), zone_config)
                if scoped_summaries is not None:
                    product_summaries[row.snapshot_product_id].update(scoped_summaries[row.snapshot_product_id])
            values = {field: getattr(row, field) for field in (
                'id', 'sale_region', 'current_retail', 'cost_with_logistics', 'calculated_rrp',
                'minimum_price', 'regional_competitor_rrp_median', 'regional_competitor_rrp_min', 'regional_competitor_rrp_max', 'base_analog', 'base_exclusive', 'minimum_margin',
                'product_cost', 'quantity_eurotruck', 'logistics_unit', 'preliminary_rrp',
                'nomenclature_price_date', 'product_cost_month',
                'discount_small', 'discount_medium', 'discount_large', 'current_small', 'current_medium', 'current_large',
                'calculated_small', 'calculated_medium', 'calculated_large',
                'calculation_status', 'warning_codes', 'error_codes')}
            values.update(snapshot_product__code_1c=row.snapshot_product.code_1c,
                include_transport=row.calculation_details.get('include_transport', False),
                entered_logistics_unit=row.calculation_details.get('entered_logistics_unit'),
                snapshot_product__nom=row.snapshot_product.nom, snapshot_product__image=row.snapshot_product.image, product_id=row.snapshot_product_id,
                effective=get_effective_prices(row), last_approval_revision=row.last_approval_revision or 0)
            from .iprice_prices import price_with_vat
            values['effective_gross'] = {key: price_with_vat(values['effective'][key]) if values['effective'][key] is not None else None
                                         for key in ('rrp', 'small', 'medium', 'large')}
            values['zone'] = classify_price_zone(_deviation(values['effective']['rrp'], row.regional_competitor_rrp_median), zone_config)
            payload.append(values)
        if grouped:
            products = {}
            for row in payload:
                products.setdefault(row['product_id'], {'product_id': row['product_id'], 'summary': product_summaries[row['product_id']], 'regions': []})['regions'].append(row)
            payload = [products[key] for key in product_order]
        return Response({'rows': payload, 'page': page, 'pages': paginator.num_pages, 'count': paginator.count,
                         'mode': controls.validated_data['mode']})


class ParserStartView(PriceFileView):
    http_method_names = ['post', 'options']
    from rest_framework.parsers import JSONParser
    parser_classes = [JSONParser]

    def post(self, request):
        from .iprice_pipeline import create_master
        from datasets.services.parsers.queue_execution import enabled
        from datasets.services.parsers.tara_jobs import kick
        if not enabled():
            raise ValidationError('Запуск парсеров пока не включён администратором.')
        run = create_master()
        # Durable queue is created first; periodic dispatch also handles launch failures.
        kick()
        return Response({'id': run.pk, 'status': run.status}, status=202)


from .iprice_operations_api import RowApprovalView, ParameterChangeView, SnapshotHistoryView, SnapshotAnalysisView, ProductDetailsView, ZoneConfigView, CompetitorSelectionView, OwnAssortmentView

urlpatterns = [
    path('review/<str:kind>/', ReviewExportView.as_view()),
    path('health/', HealthView.as_view()),
    path('snapshots/<int:snapshot_id>/products/<int:product_id>/own/', OwnAssortmentView.as_view()),
    path('snapshots/<int:snapshot_id>/products/<int:product_id>/market/', OwnAssortmentView.as_view(), {'kind': 'market'}),
    path('snapshots/<int:snapshot_id>/products/<int:product_id>/competitors/', CompetitorSelectionView.as_view()),
    path('price-zones/', ZoneConfigView.as_view()),
    path('snapshots/<int:snapshot_id>/analysis/', SnapshotAnalysisView.as_view()),
    path('snapshots/<int:snapshot_id>/products/<int:product_id>/', ProductDetailsView.as_view()),
    path('snapshots/<int:snapshot_id>/rows/<int:row_id>/approval/', RowApprovalView.as_view()),
    path('snapshots/<int:snapshot_id>/parameters/', ParameterChangeView.as_view()),
    path('snapshots/<int:snapshot_id>/history/', SnapshotHistoryView.as_view()),
    path("calculations/start/", CalculationStartView.as_view()),
    path("snapshots/", SnapshotListView.as_view()),
    path("snapshots/<int:snapshot_id>/rows/", SnapshotRowsView.as_view()),
    path("snapshots/<int:snapshot_id>/filters/", SnapshotFiltersView.as_view()),
    path("snapshots/<int:snapshot_id>/export/", SnapshotExportView.as_view()),
    path("snapshots/<int:snapshot_id>/activate/", SnapshotActivateView.as_view()),
    path("status/", SourcesStatusView.as_view()),
    path("parsers/start/", ParserStartView.as_view()),
    path("price-file/", PriceFileView.as_view()),
    path("sources/<str:kind>/", SourceFileView.as_view()),
]
