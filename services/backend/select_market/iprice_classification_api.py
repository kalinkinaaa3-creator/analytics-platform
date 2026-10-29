from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from .iprice_api import PriceFileView
from . import iprice_domain_models as m
from .iprice_unclassified import FIELDS, catalogue, classify, classification_combinations


class ClassificationInput(serializers.Serializer):
    product_keys = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=1000)
    revision = serializers.CharField(max_length=64)
    reason = serializers.CharField(max_length=2000)
    values = serializers.DictField(child=serializers.CharField(max_length=255, allow_blank=True))

    def validate_values(self, values):
        if set(values) != set(FIELDS):
            raise serializers.ValidationError('Передайте все поля классификации.')
        if values['item_type'] not in ('product', 'component'):
            raise serializers.ValidationError('Выберите тип позиции.')
        if any(not values[key] for key in ('category', 'subcategory', 'subcategory_type', 'article_number_analogs')):
            raise serializers.ValidationError('Заполните тип, категорию, подкатегорию и группу аналогов.')
        return values


class UnclassifiedView(PriceFileView):
    parser_classes = [JSONParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request, snapshot_id, product_id):
        product = get_object_or_404(m.IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        source = serializers.ChoiceField(choices=['', 'tara', 'tt', 'ps']).run_validation(request.query_params.get('source', ''))
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page', 1))
        search = serializers.CharField(max_length=200, allow_blank=True).run_validation(request.query_params.get('search', ''))
        page_size = serializers.IntegerField(min_value=25, max_value=100).run_validation(request.query_params.get('page_size', 50))
        if page_size not in (25, 50, 100):
            raise serializers.ValidationError('Выберите 25, 50 или 100 товаров на странице.')
        data = catalogue(search=search, source=source, page=page, page_size=page_size)
        base = m.ParserProductClassification.objects.filter(product_key=product.base_product_key, status='active').first()
        data['defaults'] = {key: (getattr(base, key) or '') if base else '' for key in FIELDS}
        data['combinations'] = classification_combinations()
        data['choices'] = {key: sorted({row[key] for row in data['combinations'] if row[key]}) for key in FIELDS}
        data['history'] = list(m.ClassificationChange.objects.order_by('-pk').values(
            'id', 'product_keys', 'after', 'reason', 'created_at', 'changed_by__username')[:50])
        return Response(data)

    def post(self, request, snapshot_id, product_id):
        get_object_or_404(m.IPriceSnapshotProduct, pk=product_id, snapshot_id=snapshot_id)
        form = ClassificationInput(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        try:
            change_id = classify(keys=values['product_keys'], revision=values['revision'], values=values['values'],
                reason=values['reason'], user=request.user, organization=request.organization)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return Response({'id': change_id, 'message': 'Классификация сохранена. Изменения будут учтены в следующем расчёте. Цены обновятся при следующем сборе классифицированных товаров.'})
