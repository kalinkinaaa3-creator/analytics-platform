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
        from .iprice_domain_models import ParserMasterPipelineRun
        from datasets.services.parsers.queue_execution import enabled
        from datasets.services.parsers.global_queue import queue_status
        run = ParserMasterPipelineRun.objects.order_by('-id').first()
        return Response({
            'can_edit': user_can_edit_dashboard(request.user, self.dashboard),
            'parsers_enabled': enabled(),
            'imports': list(IPriceSourceImport.objects.order_by('-id').values('id', 'kind', 'filename', 'created_at')[:20]),
            'price_imports': list(IPricePriceImport.objects.order_by('-date').values('id', 'filename', 'date', 'rows', 'revision')[:10]),
            'queue': queue_status(organization=request.organization) if enabled() else [],
            'run': {'id': run.pk, 'status': run.status, 'step': run.current_step,
                    'started_at': run.started_at, 'finished_at': run.finished_at,
                    'completed_steps': run.result.get('completed_steps', [])} if run else None,
        })


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
        rows = list(IPriceSnapshot.objects.order_by('-version_number').values(
            'id', 'calculation_date', 'version_number', 'revision_for_date', 'status', 'is_current', 'is_active', 'was_active', 'parameters')[:50])
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
        if 'comparison_id' in request.query_params:
            from rest_framework import serializers
            comparison_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['comparison_id'])
            if comparison_id == snapshot.pk or snapshot.status != 'success':
                raise ValidationError('Выберите две разные успешно рассчитанные версии.')
            base = get_object_or_404(IPriceSnapshot, pk=comparison_id, status='success')
            products = comparison_products(base=base, comparison=snapshot)
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
        paginator = Paginator(rows, 50)
        try:
            result = paginator.page(page)
        except EmptyPage:
            raise ValidationError('Страница не найдена.') from None
        payload = []
        for row in result:
            values = {field: getattr(row, field) for field in (
                'id', 'sale_region', 'current_retail', 'cost_with_logistics', 'calculated_rrp',
                'minimum_price', 'regional_competitor_rrp_median', 'regional_competitor_rrp_min', 'regional_competitor_rrp_max', 'base_analog', 'base_exclusive', 'minimum_margin',
                'product_cost', 'quantity_eurotruck', 'logistics_unit', 'preliminary_rrp',
                'nomenclature_price_date', 'product_cost_month',
                'calculation_status', 'warning_codes', 'error_codes')}
            values.update(snapshot_product__code_1c=row.snapshot_product.code_1c,
                include_transport=row.calculation_details.get('include_transport', False),
                entered_logistics_unit=row.calculation_details.get('entered_logistics_unit'),
                snapshot_product__nom=row.snapshot_product.nom, product_id=row.snapshot_product_id,
                effective=get_effective_prices(row), last_approval_revision=row.last_approval_revision or 0)
            from .iprice_prices import price_with_vat
            values['effective_gross'] = {key: price_with_vat(values['effective'][key]) if values['effective'][key] is not None else None
                                         for key in ('rrp', 'small', 'medium', 'large')}
            payload.append(values)
        return Response({'rows': payload, 'page': page, 'pages': paginator.num_pages, 'count': paginator.count})


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


from .iprice_operations_api import RowApprovalView, ParameterChangeView, SnapshotHistoryView, SnapshotAnalysisView, ProductDetailsView, ZoneConfigView, CompetitorSelectionView

urlpatterns = [
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
