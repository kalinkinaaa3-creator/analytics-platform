"""Editor operations use the shared iPrice services and explicit local storage."""
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .iprice_api import PriceFileView
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion, IPriceSnapshotApproval, IPriceParameterChangeLog


class ApprovalInput(serializers.Serializer):
    approved_rrp = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal('0.0001'))
    comment = serializers.CharField(max_length=2000, allow_blank=False)
    expected_revision = serializers.IntegerField(min_value=0)


class RowApprovalView(PriceFileView):
    http_method_names = ['post', 'options']
    parser_classes = [JSONParser]

    def post(self, request, snapshot_id, row_id):
        from datasets.services.iprice_snapshot_approval import create_iprice_snapshot_approval, IPriceSnapshotApprovalError
        row = get_object_or_404(IPriceSnapshotRegion.objects.select_related('snapshot_product__snapshot'),
                               pk=row_id, snapshot_product__snapshot_id=snapshot_id)
        data = ApprovalInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            approval = create_iprice_snapshot_approval(snapshot_region=row, approved_by=request.user, **data.validated_data)
        except IPriceSnapshotApprovalError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({'id': approval.pk, 'revision': approval.revision, 'approved_rrp': str(approval.approved_rrp)})


class DeliveryInput(serializers.Serializer):
    include_transport = serializers.BooleanField(required=False)
    logistics_unit = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0'), required=False)


class ParameterInput(serializers.Serializer):
    filters = serializers.DictField(child=serializers.ListField(child=serializers.CharField(max_length=1000), max_length=100), allow_empty=False)
    coefficients = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=6), required=False, default=dict)
    discounts = serializers.DictField(child=serializers.DecimalField(max_digits=7, decimal_places=6), required=False, default=dict)
    preview = serializers.BooleanField(default=True)
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    delivery = DeliveryInput(required=False)

    def validate(self, attrs):
        from .iprice_filters import PRODUCT_FILTERS
        from datasets.services.iprice_parameter_changes import COEFFICIENT_FIELDS, DISCOUNT_FIELDS
        if set(attrs['filters']) - set(PRODUCT_FILTERS) - {'code_1c', 'sale_region'} or not any(attrs['filters'].values()):
            raise serializers.ValidationError('Выберите поддерживаемые непустые фильтры.')
        if set(attrs['coefficients']) - set(COEFFICIENT_FIELDS) or set(attrs['discounts']) - {'small', 'medium', 'large'}:
            raise serializers.ValidationError('Неизвестный параметр расчёта.')
        if not attrs['preview'] and 'expected_revision' not in attrs:
            raise serializers.ValidationError('Сначала выполните предварительный просмотр.')
        return attrs


class ParameterChangeView(PriceFileView):
    http_method_names = ['post', 'options']
    parser_classes = [JSONParser]

    def post(self, request, snapshot_id):
        from datasets.services.iprice_parameter_changes import (
            preview_iprice_parameter_changes, apply_iprice_parameter_changes, IPriceParameterChangeError,
            parse_changes, validate_changes, COEFFICIENT_FIELDS, DISCOUNT_FIELDS)
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        data = ParameterInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        args = dict(snapshot=snapshot, mode='regions', filters=values['filters'], search='')
        try:
            if values['coefficients'] or values['discounts'] or not values.get('delivery'):
                validate_changes(parse_changes(values['coefficients'], COEFFICIENT_FIELDS), parse_changes(values['discounts'], DISCOUNT_FIELDS))
            if values['preview']:
                return Response({'affected': preview_iprice_parameter_changes(**args),
                                 'edit_revision': snapshot.parameters.get('edit_revision', 0)})
            from .iprice_regional_edits import apply
            affected = apply(snapshot=snapshot, filters=values['filters'], coefficients=values['coefficients'],
                discounts=values['discounts'], delivery=values.get('delivery'), user=request.user,
                expected_revision=values['expected_revision'])
        except IPriceParameterChangeError as exc:
            raise ValidationError(str(exc)) from exc
        return Response({'affected': affected})


class SnapshotHistoryView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id):
        from django.core.paginator import Paginator
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id)
        try:
            page = int(request.query_params.get('page', 1))
            if page < 1:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValidationError('Некорректная страница.') from None
        approvals = IPriceSnapshotApproval.objects.filter(snapshot_region__snapshot_product__snapshot=snapshot).order_by('-approved_at', '-id').values(
            'id', 'revision', 'approved_rrp', 'approved_by__username', 'approved_at', 'comment', 'is_current',
            'snapshot_region__snapshot_product__code_1c', 'snapshot_region__sale_region')
        paginator = Paginator(approvals, 50)
        if page > paginator.num_pages:
            raise ValidationError('Страница не найдена.')
        return Response({'activations': snapshot.parameters.get('activation_history', []),
            'approvals': list(paginator.page(page)), 'page': page, 'pages': paginator.num_pages,
            'parameter_changes': list(IPriceParameterChangeLog.objects.filter(snapshot_id=snapshot.pk).order_by('-id').values(
                'id', 'user__username', 'changes', 'filters', 'affected', 'status', 'created_at')[:50])})


class AnalysisQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    search = serializers.CharField(max_length=200, allow_blank=True, default='')
    comparison_id = serializers.IntegerField(min_value=1, required=False)
    view = serializers.ChoiceField(choices=['regions', 'groups'], default='regions')
    hierarchy = serializers.ChoiceField(choices=['1c', 'classification'], default='1c')
    drill_level = serializers.ChoiceField(choices=['root', 'group_1', 'group_2', 'group_3', 'group_4', 'category', 'subcategory', 'subcategory_type'], default='root')
    group_1 = serializers.CharField(max_length=1000, required=False)
    group_2 = serializers.CharField(max_length=1000, required=False)
    group_3 = serializers.CharField(max_length=1000, required=False)
    group_4 = serializers.CharField(max_length=1000, required=False)
    category = serializers.CharField(max_length=1000, required=False)
    subcategory = serializers.CharField(max_length=1000, required=False)
    subcategory_type = serializers.CharField(max_length=1000, required=False)


class SnapshotAnalysisView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id):
        from datasets.services.iprice_workspace import IPriceWorkspace
        from datasets.services.iprice_snapshot_compare import compare_iprice_snapshots, IPriceSnapshotCompareError
        from datasets.services.iprice_price_analytics import build_iprice_regional_price_analytics
        snapshot = get_object_or_404(IPriceSnapshot, pk=snapshot_id, status='success')
        query = AnalysisQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        from .iprice_filters import query_filters, filter_products
        try:
            filters = query_filters(request.query_params)
            filter_products(snapshot.products.all(), filters)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if values['view'] == 'groups':
            from datasets.services.iprice_price_analytics import build_iprice_price_analytics, IPricePriceAnalyticsError
            try:
                return Response(build_iprice_price_analytics(snapshot=snapshot, filters=filters, search=values['search'],
                    hierarchy=values['hierarchy'], drill_level=values['drill_level'], drill_path={key: values[key] for key in ('group_1', 'group_2', 'group_3', 'group_4', 'category', 'subcategory', 'subcategory_type') if key in values},
                    page=values['page'], page_size=50, ordering=''))
            except IPricePriceAnalyticsError as exc:
                raise ValidationError(str(exc)) from exc
        if values.get('comparison_id'):
            get_object_or_404(IPriceSnapshot, pk=values['comparison_id'], status='success')
            try:
                return Response(compare_iprice_snapshots(base_snapshot_id=values['comparison_id'],
                    comparison_snapshot_id=snapshot.pk, mode='regions', page=values['page'], page_size=50,
                    search=values['search'], filters=filters, workspace=IPriceWorkspace('select-market')))
            except IPriceSnapshotCompareError as exc:
                raise ValidationError(str(exc)) from exc
        return Response(build_iprice_regional_price_analytics(snapshot=snapshot, filters=filters, search=values['search'],
            drill_path={}, page=values['page'], page_size=50))


class ProductDetailsView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id, product_id):
        from .iprice_domain_models import IPriceSnapshotProduct
        product = get_object_or_404(IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        return Response({'code': product.code_1c, 'nom': product.nom, 'method': product.pricing_method,
            'details': product.calculation_details, 'competitors': list(product.competitors.order_by('source', 'id').values(
                'id', 'source', 'url', 'competitor_price_date', 'competitor_final_price_max', 'applicable_regions', 'error_codes'))})


class ZoneInput(serializers.Serializer):
    below_market_threshold = serializers.DecimalField(max_digits=7, decimal_places=6, min_value=Decimal('-1'), max_value=Decimal('0'))
    above_market_threshold = serializers.DecimalField(max_digits=7, decimal_places=6, min_value=Decimal('0'))
    critical_threshold = serializers.DecimalField(max_digits=7, decimal_places=6, min_value=Decimal('0'))

    def validate(self, attrs):
        if attrs['above_market_threshold'] >= attrs['critical_threshold']:
            raise serializers.ValidationError('Критический порог должен превышать верхний.')
        return attrs


class ZoneConfigView(PriceFileView):
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [JSONParser]

    def get(self, request):
        from datasets.services.iprice_price_analytics import get_active_price_zone_config
        from datasets.services.iprice_workspace import IPriceWorkspace
        return Response(get_active_price_zone_config(workspace=IPriceWorkspace('select-market')))

    def post(self, request):
        from datasets.services.iprice_price_analytics import activate_price_zone_config
        from datasets.services.iprice_workspace import IPriceWorkspace
        data = ZoneInput(data=request.data)
        data.is_valid(raise_exception=True)
        result, changed = activate_price_zone_config(**data.validated_data, user=request.user, workspace=IPriceWorkspace('select-market'))
        return Response({**result, 'changed': changed})


class SelectionInput(serializers.Serializer):
    competitor_product_keys = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=50)
    selection_mode = serializers.ChoiceField(choices=['auto', 'include', 'exclude'])
    reason = serializers.CharField(max_length=2000)
    expected_revision = serializers.IntegerField(min_value=0)


class CompetitorSelectionView(PriceFileView):
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [JSONParser]

    def get(self, request, snapshot_id, product_id):
        from django.core.paginator import Paginator
        from django.db.models import Q
        from datasets.services.iprice_competitor_selection import _same_class, is_selection_editable
        from .iprice_domain_models import IPriceSnapshotProduct, ParserProductClassification, ParserProductUrl, IPriceCompetitorSelectionOverride
        product = get_object_or_404(IPriceSnapshotProduct.objects.select_related('snapshot'), pk=product_id, snapshot_id=snapshot_id)
        base = ParserProductClassification.objects.filter(product_key=product.base_product_key, status='active').first()
        keys = [row.product_key for row in ParserProductClassification.objects.filter(status='active') if base and _same_class(base, row)]
        urls = ParserProductUrl.objects.filter(pk__in=keys, status='active').exclude(source='base').order_by('id')
        query = AnalysisQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        if query.validated_data['search']:
            urls = urls.filter(Q(url__icontains=query.validated_data['search']))
        paginator = Paginator(urls, 50)
        page = query.validated_data['page']
        if page > paginator.num_pages:
            raise ValidationError('Страница не найдена.')
        modes = dict(IPriceCompetitorSelectionOverride.objects.filter(product_key_base=product.base_product_key).values_list('product_key_competitor', 'selection_mode'))
        return Response({'items': [{'id': row.pk, 'source': row.source, 'url': row.url, 'mode': modes.get(row.pk, 'auto')} for row in paginator.page(page)],
            'page': page, 'pages': paginator.num_pages, 'edit_revision': product.snapshot.parameters.get('edit_revision', 0),
            'editable': is_selection_editable(product.snapshot),
            'changes': list(product.snapshot.competitor_selection_changes.filter(override__product_key_base=product.base_product_key).order_by('-id').values(
                'id', 'selection_mode', 'reason', 'date_add', 'changed_by__username', 'override__product_key_competitor')[:50])})

    def post(self, request, snapshot_id, product_id):
        from datasets.services.iprice_workspace import IPriceWorkspace
        from datasets.services.iprice_competitor_selection import apply_competitor_selection, IPriceCompetitorSelectionError
        from .iprice_domain_models import IPriceSnapshotProduct, ParserProductUrl
        get_object_or_404(IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        data = SelectionInput(data=request.data)
        data.is_valid(raise_exception=True)
        keys = set(data.validated_data['competitor_product_keys'])
        if ParserProductUrl.objects.filter(pk__in=keys, status='active').exclude(source='base').count() != len(keys):
            raise ValidationError('Выберите активные позиции конкурентов.')
        try:
            result = apply_competitor_selection(snapshot_id=snapshot_id, product_id=product_id,
                workspace=IPriceWorkspace('select-market'), user=request.user, **data.validated_data)
        except IPriceCompetitorSelectionError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result)
