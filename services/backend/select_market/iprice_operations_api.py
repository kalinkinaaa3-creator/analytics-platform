"""Editor operations use the shared iPrice services and explicit local storage."""
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from .iprice_api import PriceFileView
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion, IPriceSnapshotApproval, IPriceParameterChangeLog
from .iprice_row_controls import RowControls


class ApprovalInput(serializers.Serializer):
    approved_rrp = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal('0.0001'))
    comment = serializers.CharField(max_length=2000, allow_blank=False)
    expected_revision = serializers.IntegerField(min_value=0)


class RowApprovalView(PriceFileView):
    http_method_names = ['get', 'post', 'options']
    parser_classes = [JSONParser]

    def get(self, request, snapshot_id, row_id):
        from .iprice_prices import whole_rubles, price_with_vat
        from .iprice_regional_calculation import prices_meet_margin
        row = get_object_or_404(IPriceSnapshotRegion, pk=row_id, snapshot_product__snapshot_id=snapshot_id)
        price = serializers.DecimalField(max_digits=18, decimal_places=0, min_value=Decimal('1')).run_validation(request.query_params.get('price'))
        prices = {'rrp': price}
        for tier in ('small', 'medium', 'large'):
            discount = getattr(row, 'discount_' + tier)
            prices[tier] = whole_rubles(price * (1 - discount)) if discount is not None else None
        valid = all(value is not None and value > 0 for value in prices.values()) and prices_meet_margin(row, list(prices.values()))
        return Response({'price': str(price), 'prices': prices, 'gross': {key: price_with_vat(value) if value is not None else None for key, value in prices.items()},
            'margin': (price - row.cost_with_logistics) / price if row.cost_with_logistics is not None else None,
            'valid': valid, 'message': '' if valid else 'Цена или оптовые скидки нарушают минимальную маржу либо не заполнены.'})

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
    preserve_manual_row_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=True)
    expected_manual_signature = serializers.RegexField(r'^[a-f0-9]{64}$', required=False)
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    filters = serializers.DictField(child=serializers.ListField(child=serializers.CharField(max_length=1000), max_length=100), allow_empty=True)
    list_scope = RowControls(required=False)
    expected_scope = serializers.RegexField(r'^[a-f0-9]{64}$', required=False)
    search = serializers.CharField(max_length=200, allow_blank=True, default='')
    coefficients = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=6), required=False, default=dict)
    discounts = serializers.DictField(child=serializers.DecimalField(max_digits=7, decimal_places=6), required=False, default=dict)
    preview = serializers.BooleanField(default=True)
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    delivery = DeliveryInput(required=False)

    def validate(self, attrs):
        if not attrs['preview'] and not attrs['reason'].strip():
            raise serializers.ValidationError({'reason': 'Укажите причину изменения.'})
        from .iprice_filters import PRODUCT_FILTERS
        from datasets.services.iprice_parameter_changes import COEFFICIENT_FIELDS, DISCOUNT_FIELDS
        if set(attrs['filters']) - set(PRODUCT_FILTERS) - {'code_1c', 'sale_region'} or (not any(attrs['filters'].values()) and 'list_scope' not in attrs):
            raise serializers.ValidationError('Выберите поддерживаемые непустые фильтры.')
        if set(attrs['coefficients']) - set(COEFFICIENT_FIELDS) or set(attrs['discounts']) - {'small', 'medium', 'large'}:
            raise serializers.ValidationError('Неизвестный параметр расчёта.')
        if not attrs['preview'] and 'expected_revision' not in attrs:
            raise serializers.ValidationError('Сначала выполните предварительный просмотр.')
        if not attrs['preview'] and 'list_scope' in attrs and 'expected_scope' not in attrs:
            raise serializers.ValidationError('Повторите предварительный просмотр списка.')
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
        args = dict(snapshot=snapshot, filters=values['filters'], search=values['search'], list_scope=values.get('list_scope'))
        try:
            if values['coefficients'] or values['discounts'] or not values.get('delivery'):
                validate_changes(parse_changes(values['coefficients'], COEFFICIENT_FIELDS), parse_changes(values['discounts'], DISCOUNT_FIELDS))
            if values['preview']:
                from .iprice_regional_edits import preview
                return Response({'affected': preview(**args),
                                 'edit_revision': snapshot.parameters.get('edit_revision', 0)})
            from .iprice_regional_edits import apply
            affected = apply(**args, coefficients=values['coefficients'],
                discounts=values['discounts'], delivery=values.get('delivery'), user=request.user, reason=values['reason'],
                expected_revision=values['expected_revision'], expected_scope=values.get('expected_scope'),
                preserve_manual_row_ids=values.get('preserve_manual_row_ids'), expected_manual_signature=values.get('expected_manual_signature'))
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
        from .iprice_regional_edits import parameter_change_products
        if 'parameter_change_id' in request.query_params:
            log_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['parameter_change_id'])
            log = get_object_or_404(IPriceParameterChangeLog, pk=log_id, snapshot_id=snapshot.pk)
            products = parameter_change_products(snapshot.pk, log.affected)
            pager = Paginator(products or [], 25)
            if page > pager.num_pages:
                raise ValidationError('Страница не найдена.')
            return Response({'available': products is not None, 'results': list(pager.page(page)),
                             'count': pager.count, 'page': page, 'pages': pager.num_pages})
        approvals = IPriceSnapshotApproval.objects.filter(snapshot_region__snapshot_product__snapshot=snapshot).order_by('-approved_at', '-id').values(
            'id', 'revision', 'approved_rrp', 'approved_by__username', 'approved_at', 'comment', 'is_current',
            'snapshot_region__snapshot_product__code_1c', 'snapshot_region__sale_region')
        if 'row_id' in request.query_params:
            row_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['row_id'])
            get_object_or_404(IPriceSnapshotRegion, pk=row_id, snapshot_product__snapshot=snapshot)
            approvals = approvals.filter(snapshot_region_id=row_id)
        paginator = Paginator(approvals, 50)
        if page > paginator.num_pages:
            raise ValidationError('Страница не найдена.')
        parameter_changes = []
        if 'row_id' not in request.query_params:
            logs = IPriceParameterChangeLog.objects.filter(snapshot_id=snapshot.pk).order_by('-id')
            parameter_row = None
            if request.query_params.get('parameter_row_id'):
                key = serializers.IntegerField(min_value=1).run_validation(request.query_params['parameter_row_id'])
                parameter_row = get_object_or_404(IPriceSnapshotRegion, pk=key, snapshot_product__snapshot=snapshot)
            for log in logs.values('id', 'user__username', 'changes', 'filters', 'affected', 'status', 'created_at', 'reason', 'search').iterator():
                if parameter_row:
                    ids = log['affected'].get('row_ids')
                    if ids is not None:
                        if parameter_row.pk not in ids:
                            continue
                    else:
                        from .iprice_regional_edits import resolve
                        filters = dict(log['filters'])
                        scope = filters.pop('_list_scope', None)
                        try:
                            if not resolve(snapshot, filters, log['search'], scope).filter(pk=parameter_row.pk).exists():
                                continue
                        except (ValueError, ValidationError):
                            continue
                products = parameter_change_products(snapshot.pk, log['affected'])
                log['targets'] = {'available': products is not None, 'count': len(products or []),
                                  'first': products[0] if products else None}
                log['affected'] = {key: value for key, value in log['affected'].items() if key != 'product_details'}
                parameter_changes.append(log)
                if len(parameter_changes) == 50:
                    break
        return Response({'activations': snapshot.parameters.get('activation_history', []),
            'approvals': list(paginator.page(page)), 'page': page, 'pages': paginator.num_pages, 'count': paginator.count,
            'parameter_changes': parameter_changes})


class AnalysisQuery(serializers.Serializer):
    from datasets.services.iprice_price_analytics import ZONE_ORDER
    zone = serializers.CharField(default='', allow_blank=True, max_length=200)
    validate_zone = RowControls.validate_zone
    page = serializers.IntegerField(min_value=1, default=1)
    search = serializers.CharField(max_length=200, allow_blank=True, default='')
    ordering = serializers.ChoiceField(choices=[''] + [prefix + field for field in ('median_deviation_percent', 'product_count', 'nom', 'median_retail_price', 'median_final_rrp', 'median_market_price', 'zone', 'deviation_percent') for prefix in ('', '-')], default='')
    comparison_id = serializers.IntegerField(min_value=1, required=False)
    mode = serializers.ChoiceField(choices=['products', 'regions'], default='regions')
    from datasets.services.iprice_snapshot_compare import ALLOWED_CHANGE_TYPES
    change_type = serializers.ChoiceField(choices=sorted(ALLOWED_CHANGE_TYPES), default='all')
    view = serializers.ChoiceField(choices=['regions', 'groups', 'region_groups'], default='regions')
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
        selected_zones = values['zone'].split(',') if values['zone'] else []
        if selected_zones and values.get('comparison_id'):
            raise ValidationError('Фильтр зон доступен при сравнении с рынком, а не между версиями.')
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
                    page=values['page'], page_size=50, ordering=values['ordering'], selected_zones=selected_zones))
            except IPricePriceAnalyticsError as exc:
                raise ValidationError(str(exc)) from exc
        if values.get('comparison_id'):
            get_object_or_404(IPriceSnapshot, pk=values['comparison_id'], status='success')
            try:
                return Response(compare_iprice_snapshots(base_snapshot_id=values['comparison_id'],
                    comparison_snapshot_id=snapshot.pk, mode=values['mode'], change_type=values['change_type'], page=values['page'], page_size=50,
                    search=values['search'], filters=filters, workspace=IPriceWorkspace('select-market')))
            except IPriceSnapshotCompareError as exc:
                raise ValidationError(str(exc)) from exc
        return Response(build_iprice_regional_price_analytics(snapshot=snapshot, filters=filters, search=values['search'],
            drill_path={}, page=values['page'], page_size=50, selected_zones=selected_zones,
            ordering=values['ordering'], group_by_region=values['view'] == 'region_groups'))


class ProductDetailsView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id, product_id):
        from .iprice_domain_models import IPriceSnapshotProduct
        product = get_object_or_404(IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        from datasets.services.iprice_price_analytics import classify_price_zone, _deviation, get_active_price_zone_config
        from datasets.services.iprice_workspace import IPriceWorkspace
        summary = {field: getattr(product, field) for field in (
            'image', 'url', 'category', 'subcategory', 'subcategory_type', 'material', 'color', 'modification', 'article_number_analogs',
            'assortment_matrix_status', 'calculation_status', 'warning_codes', 'error_codes', 'competitor_count',
            'competitor_rrp_min', 'competitor_rrp_max', 'competitor_rrp_median', 'current_retail_median', 'effective_approved_rrp_median')}
        summary['zone'] = classify_price_zone(_deviation(product.effective_approved_rrp_median, product.competitor_rrp_median),
                                             get_active_price_zone_config(workspace=IPriceWorkspace('select-market')))
        from datasets.services.iprice_market_assortment import group_snapshot_competitor_cards, get_used_competitor_keys
        from .iprice_domain_models import IPriceCompetitorSelectionOverride
        competitors = list(product.competitors.order_by('source', 'pk').values())
        cards = group_snapshot_competitor_cards(competitors, workspace=IPriceWorkspace('select-market'))
        from .iprice_domain_models import ParserProductClassification
        articles = dict(ParserProductClassification.objects.filter(
            product_key__in=[key for card in cards for key in card['competitor_product_keys']]
        ).values_list('product_key', 'article_number_analogs'))
        for card in cards:
            card['article_number_analogs'] = articles.get(card.get('competitor_product_key'))
        used = get_used_competitor_keys(snapshot_product=product)
        modes = dict(IPriceCompetitorSelectionOverride.objects.filter(product_key_base=product.base_product_key).values_list('product_key_competitor', 'selection_mode'))
        for card in cards:
            variants = card.get('price_variants') or []
            keys = card['competitor_product_keys']
            chosen = {modes.get(key, 'auto') for key in keys}
            card.update(price=card.get('competitor_final_price_median'), regions=card.get('applicable_regions', []),
                product_key=card.get('competitor_product_key'), name=next((v.get('name') for v in variants if v.get('name')), None),
                image=next((v.get('image') for v in variants if v.get('image')), None), is_used_in_snapshot=bool(used.intersection(keys)),
                selection_mode=next(iter(chosen)) if len(chosen) == 1 else 'mixed')
        from .iprice_card_prices import regional_card_prices
        cards = [regional_card_prices(card) for card in cards]
        # Live AUTO links are visible immediately, without rewriting the saved calculation.
        from datasets.services.iprice_market_assortment import build_iprice_market_assortment
        from .iprice_domain_models import ParserProductMatch
        live_keys = set(ParserProductMatch.objects.filter(product_key_base=product.base_product_key,
            status='active').values_list('product_key_competitor', flat=True))
        shown = {key for card in cards for key in card['competitor_product_keys']}
        if live_keys - shown:
            market = build_iprice_market_assortment(snapshot_product=product, workspace=IPriceWorkspace('select-market'))
            for card in market['results']:
                keys = set(card['competitor_product_keys'])
                if keys.intersection(live_keys) and not keys.intersection(shown):
                    selections = {modes.get(key, 'auto') for key in keys}
                    card.update(selection_mode=next(iter(selections)) if len(selections) == 1 else 'mixed',
                                is_current_analog=True, is_used_in_snapshot=False)
                    cards.append(regional_card_prices(card))
        for card in cards:
            card['is_current_analog'] = bool(live_keys.intersection(card['competitor_product_keys']))
        return Response({**summary, 'competitor_cards': cards, 'edit_revision': product.snapshot.parameters.get('edit_revision', 0),
            'code': product.code_1c, 'nom': product.nom, 'method': product.pricing_method,
            'details': product.calculation_details, 'competitors': list(product.competitors.order_by('source', 'id').values(
                'id', 'source', 'url', 'competitor_price_date', 'competitor_final_price_max', 'applicable_regions', 'error_codes'))})


class OwnAssortmentView(PriceFileView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, snapshot_id, product_id, kind='own'):
        from datasets.services.iprice_own_assortment import build_iprice_own_assortment, IPriceOwnAssortmentError
        from datasets.services.iprice_market_assortment import build_iprice_market_assortment, IPriceMarketAssortmentError
        from datasets.services.iprice_workspace import IPriceWorkspace
        from .iprice_domain_models import IPriceSnapshotProduct
        product = get_object_or_404(IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        try:
            build = build_iprice_market_assortment if kind == 'market' else build_iprice_own_assortment
            result = build(snapshot_product=product, workspace=IPriceWorkspace('select-market'))
            if kind == 'market':
                from datasets.services.iprice_competitor_selection import is_selection_editable
                from .iprice_domain_models import IPriceCompetitorSelectionOverride
                modes = dict(IPriceCompetitorSelectionOverride.objects.filter(product_key_base=product.base_product_key).values_list('product_key_competitor', 'selection_mode'))
                from .iprice_card_prices import regional_card_prices
                for card in result['results']:
                    regional_card_prices(card)
                    selections = {modes.get(key, 'auto') for key in card['competitor_product_keys']}
                    card['selection_mode'] = next(iter(selections)) if len(selections) == 1 else 'mixed'
                result.update(editable=is_selection_editable(product.snapshot), edit_revision=product.snapshot.parameters.get('edit_revision', 0))
            if kind == 'own':
                from datasets.services.iprice_price_analytics import _with_effective_approved_rrp
                from collections import defaultdict
                from statistics import median
                rows = _with_effective_approved_rrp(IPriceSnapshotRegion.objects.filter(
                    snapshot_product_id__in=[item['snapshot_product_id'] for item in result['results']]))
                regional = defaultdict(lambda: defaultdict(list))
                for row in rows:
                    regional[row.snapshot_product_id][row.sale_region.casefold()].append({
                        'region': row.sale_region, 'price': row.current_retail,
                        'final_price': row.effective_approved_rrp})
                for item in result['results']:
                    entries = []
                    for _, values in sorted(regional[item['snapshot_product_id']].items()):
                        entry = {'region': values[0]['region'], 'url': item.get('url')}
                        for field in ('price', 'final_price'):
                            prices = [row[field] for row in values if row[field] is not None]
                            entry[field] = median(prices) if prices else None
                        entries.append(entry)
                    item['regional_prices'] = entries
                    prices = [row['final_price'] for row in item['regional_prices'] if row['final_price'] is not None]
                    item['final_price'] = median(prices) if prices else None
            return Response(result)
        except (IPriceOwnAssortmentError, IPriceMarketAssortmentError) as exc:
            return Response({'results': [], 'counts': {'cards': 0}, 'unavailable_reason': str(exc)})


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
        from datasets.services.iprice_market_assortment import get_used_competitor_keys
        used = get_used_competitor_keys(snapshot_product=product)
        changes = list(product.snapshot.competitor_selection_changes.filter(
            override__product_key_base=product.base_product_key).order_by('-id').values(
                'id', 'selection_mode', 'reason', 'date_add', 'changed_by__username', 'override__product_key_competitor')[:50])
        history_keys = {item['override__product_key_competitor'] for item in changes}
        sources = dict(ParserProductUrl.objects.filter(pk__in=history_keys).values_list('pk', 'source'))
        from .iprice_domain_models import TaraProductPrice, PsProductPrice, TtProductPrice
        names = {}
        for model in (TaraProductPrice, PsProductPrice, TtProductPrice):
            for key, name in model.objects.filter(product_key__in=history_keys).exclude(name__isnull=True).exclude(name='').order_by('-date_add', '-pk').values_list('product_key', 'name'):
                names.setdefault(key, name)
        for item in changes:
            key = item['override__product_key_competitor']
            item.update(source=sources.get(key), product_name=names.get(key))
        return Response({'items': [{'id': row.pk, 'source': row.source, 'url': row.url, 'mode': modes.get(row.pk, 'auto'), 'used_in_snapshot': row.pk in used} for row in paginator.page(page)],
            'page': page, 'pages': paginator.num_pages, 'count': paginator.count, 'edit_revision': product.snapshot.parameters.get('edit_revision', 0),
            'editable': is_selection_editable(product.snapshot),
            'changes': changes})

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
