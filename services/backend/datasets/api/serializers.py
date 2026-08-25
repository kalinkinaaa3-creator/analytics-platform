from decimal import Decimal

from rest_framework import serializers

from datasets.models import (
    Dataset,
    DatasetRow,
    IPriceSnapshot,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
    IPriceSnapshotCompetitor,
    IPriceSnapshotApproval,
    ParserProductClassification,
    ParserProductUrl,

)


class DatasetSerializer(serializers.ModelSerializer):

    class Meta:
        model = Dataset
        fields = "__all__"


class DatasetRowSerializer(serializers.ModelSerializer):

    class Meta:
        model = DatasetRow
        fields = "__all__"


class FbProjectUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class YdWordstatUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class FBPurchasesUploadSerializer(serializers.Serializer):
    use_file = serializers.FileField()


class FBTurnoverUploadSerializer(serializers.Serializer):
    turnover_file = serializers.FileField()


class FBAccreceivUploadSerializer(serializers.Serializer):
    accreceiv_file = serializers.FileField()


class IndicatorUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlannedSalesUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlanSalesUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PlannedSalesDirectoryUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ParserPrefixUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ProductClassificationUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ExcelUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class TransportCostUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

class ProductCostUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class IPriceCalculationConfigUploadSerializer(serializers.Serializer):
    file = serializers.FileField()




class IPriceSnapshotRunSerializer(
    serializers.Serializer
):
    calculation_date = serializers.DateField(
        required=False,
    )


class IPriceParameterChangeSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=("products", "regions"))
    filters = serializers.JSONField(required=False, default=dict)
    search = serializers.CharField(required=False, allow_blank=True, default="")
    coefficients = serializers.JSONField(required=False, default=dict)
    discounts = serializers.JSONField(required=False, default=dict)
    preview = serializers.BooleanField(required=False, default=False)


class IPriceSnapshotSerializer(
    serializers.ModelSerializer
):
    display_version = serializers.CharField(
        read_only=True,
    )

    created_by_username = (
        serializers.CharField(
            source="created_by.username",
            read_only=True,
            allow_null=True,
        )
    )

    activated_by_username = (
        serializers.CharField(
            source="activated_by.username",
            read_only=True,
            allow_null=True,
        )
    )

    products_count = (
        serializers.SerializerMethodField()
    )

    regions_count = (
        serializers.SerializerMethodField()
    )

    errors_count = (
        serializers.SerializerMethodField()
    )

    is_latest = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = IPriceSnapshot

        fields = [
            "id",
            "calculation_date",
            "version_number",
            "revision_for_date",
            "display_version",
            "status",
            "is_current",
            "is_active",
            "was_active",
            "is_latest",
            "created_by",
            "created_by_username",
            "created_at",
            "finished_at",
            "activated_by",
            "activated_by_username",
            "activated_at",
            "error",
            "parameters",
            "products_count",
            "regions_count",
            "errors_count",
        ]

        read_only_fields = fields

    def get_products_count(
        self,
        obj,
    ):
        annotated_value = getattr(
            obj,
            "products_count_value",
            None,
        )

        if annotated_value is not None:
            return annotated_value

        return obj.products.count()

    def get_regions_count(
        self,
        obj,
    ):
        annotated_value = getattr(
            obj,
            "regions_count_value",
            None,
        )

        if annotated_value is not None:
            return annotated_value

        return sum(
            product.regions.count()
            for product in (
                obj.products.all()
            )
        )

    def get_errors_count(
        self,
        obj,
    ):
        annotated_value = getattr(
            obj,
            "errors_count_value",
            None,
        )

        if annotated_value is not None:
            return annotated_value

        return sum(
            product.regions.filter(
                calculation_status="error",
            ).count()
            for product in (
                obj.products.all()
            )
        )

    def get_is_latest(
        self,
        obj,
    ):
        latest_id = self.context.get(
            "latest_snapshot_id"
        )

        return (
            latest_id is not None
            and obj.pk == latest_id
        )


class IPriceSnapshotProductSerializer(
    serializers.ModelSerializer
):
    image = serializers.CharField(
        allow_null=True,
        read_only=True,
    )

    class Meta:
        model = IPriceSnapshotProduct

        fields = [
            "id",
            "snapshot",
            "base_product_key",
            "code_1c",
            "nom",
            "nom_hier_code",
            "nom_hier",
            "nom_view",
            "nom_category",
            "nom_group",
            "assortment_matrix_status",
            "our_offer",
            "category",
            "subcategory",
            "subcategory_type",
            "color",
            "material",
            "modification",
            "image",
            "url",
            "item_type",
            "pricing_method",
            "competitor_count",
            "competitor_rrp_min",
            "competitor_rrp_max",
            "competitor_rrp_median",
            "current_retail_min",
            "current_retail_max",
            "current_retail_median",
            "current_vs_competitor_amount",
            "current_vs_competitor_percent",
            "effective_approved_rrp_median",
            "current_vs_approved_amount",
            "calculation_status",
            "warning_codes",
            "error_codes",
            "calculation_details",
        ]

        read_only_fields = fields


class IPriceSnapshotApprovalSerializer(
    serializers.ModelSerializer
):
    approved_by_username = serializers.CharField(
        source="approved_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = IPriceSnapshotApproval

        fields = [
            "id",
            "snapshot_region",
            "revision",
            "approved_rrp",
            "approved_distr",
            "approved_distr_1",
            "approved_small",
            "approved_medium",
            "approved_large",
            "approved_by",
            "approved_by_username",
            "approved_at",
            "comment",
            "is_current",
        ]

        read_only_fields = fields


class IPriceSnapshotRegionSerializer(
    serializers.ModelSerializer
):
    base_product_key = serializers.IntegerField(
        source="snapshot_product.base_product_key",
        read_only=True,
    )

    code_1c = serializers.IntegerField(
        source="snapshot_product.code_1c",
        read_only=True,
    )

    nom = serializers.CharField(
        source="snapshot_product.nom",
        read_only=True,
        allow_null=True,
    )

    nom_hier_code = serializers.CharField(
        source="snapshot_product.nom_hier_code",
        read_only=True,
        allow_null=True,
    )

    nom_hier = serializers.CharField(
        source="snapshot_product.nom_hier",
        read_only=True,
        allow_null=True,
    )

    nom_view = serializers.CharField(
        source="snapshot_product.nom_view",
        read_only=True,
        allow_null=True,
    )

    nom_category = serializers.CharField(
        source="snapshot_product.nom_category",
        read_only=True,
        allow_null=True,
    )

    nom_group = serializers.CharField(
        source="snapshot_product.nom_group",
        read_only=True,
        allow_null=True,
    )

    assortment_matrix_status = serializers.CharField(
        source=(
            "snapshot_product."
            "assortment_matrix_status"
        ),
        read_only=True,
        allow_null=True,
    )

    our_offer = serializers.CharField(
        source=(
            "snapshot_product."
            "our_offer"
        ),
        read_only=True,
        allow_null=True,
    )

    category = serializers.CharField(
        source="snapshot_product.category",
        read_only=True,
        allow_null=True,
    )

    subcategory = serializers.CharField(
        source="snapshot_product.subcategory",
        read_only=True,
        allow_null=True,
    )

    subcategory_type = serializers.CharField(
        source="snapshot_product.subcategory_type",
        read_only=True,
        allow_null=True,
    )

    color = serializers.CharField(
        source="snapshot_product.color",
        read_only=True,
        allow_null=True,
    )

    material = serializers.CharField(
        source="snapshot_product.material",
        read_only=True,
        allow_null=True,
    )

    modification = serializers.CharField(
        source="snapshot_product.modification",
        read_only=True,
        allow_null=True,
    )

    image = serializers.CharField(
        source="snapshot_product.image",
        read_only=True,
        allow_null=True,
    )

    url = serializers.CharField(
        source="snapshot_product.url",
        read_only=True,
        allow_null=True,
    )

    item_type = serializers.CharField(
        source="snapshot_product.item_type",
        read_only=True,
    )

    pricing_method = serializers.CharField(
        source="snapshot_product.pricing_method",
        read_only=True,
    )

    current_approval = (
        serializers.SerializerMethodField()
    )

    effective_approved_rrp = (
        serializers.SerializerMethodField()
    )

    effective_distr = (
        serializers.SerializerMethodField()
    )

    effective_distr_1 = (
        serializers.SerializerMethodField()
    )

    effective_small = (
        serializers.SerializerMethodField()
    )

    effective_medium = (
        serializers.SerializerMethodField()
    )

    effective_large = (
        serializers.SerializerMethodField()
    )

    effective_margin_calculated = (
        serializers.SerializerMethodField()
    )

    current_vs_effective_approved_amount = (
        serializers.SerializerMethodField()
    )

    current_vs_effective_approved_percent = (
        serializers.SerializerMethodField()
    )

    previous_effective_margin_calculated = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = IPriceSnapshotRegion

        fields = [
            "id",
            "snapshot_product",

            "base_product_key",
            "code_1c",
            "nom",
            "nom_hier_code",
            "nom_hier",
            "nom_view",
            "nom_category",
            "nom_group",
            "assortment_matrix_status",
            "our_offer",

            "category",
            "subcategory",
            "subcategory_type",
            "color",
            "material",
            "modification",

            "image",
            "url",
            "item_type",
            "pricing_method",

            "sale_region",
            "departure",

            "product_cost_source_id",
            "transport_cost_source_id",
            "nomenclature_price_source_id",
            "departure_discount_source_id",
            "calculation_config_source_id",

            "product_cost_month",
            "nomenclature_price_date",

            "current_retail",
            "current_distr",
            "current_distr_1",
            "current_small",
            "current_medium",
            "current_large",

            "product_cost",
            "transport_cost",
            "quantity_eurotruck",
            "logistics_unit",
            "cost_with_logistics",

            "regional_competitor_count",
            "regional_competitor_rrp_min",
            "regional_competitor_rrp_max",
            "regional_competitor_rrp_median",

            "base_analog",
            "base_exclusive",
            "minimum_margin",

            "discount_distr",
            "discount_distr_1",
            "discount_small",
            "discount_medium",
            "discount_large",

            "preliminary_rrp",
            "minimum_price",
            "calculated_rrp",
            "default_approved_rrp",

            "calculated_distr",
            "calculated_distr_1",
            "calculated_small",
            "calculated_medium",
            "calculated_large",

            "current_approval",

            "effective_approved_rrp",
            "effective_distr",
            "effective_distr_1",
            "effective_small",
            "effective_medium",
            "effective_large",

            "effective_margin_calculated",
            "previous_effective_margin_calculated",

            "current_vs_effective_approved_amount",
            "current_vs_effective_approved_percent",

            "margin_current",
            "margin_calculated",
            "current_vs_calculated_percent",

            "calculation_status",
            "warning_codes",
            "error_codes",
            "calculation_details",
        ]

        read_only_fields = fields

    @staticmethod
    def _get_current_approval(
        obj,
    ):
        """
        Сначала использует заранее загруженное
        текущее утверждение из Prefetch.

        Если сериализатор вызван без Prefetch,
        выполняет один запрос и сохраняет результат
        на объекте, чтобы остальные effective-поля
        не создавали повторные запросы.
        """

        prefetched_approvals = getattr(
            obj,
            "prefetched_current_approvals",
            None,
        )

        if prefetched_approvals is not None:
            return (
                prefetched_approvals[0]
                if prefetched_approvals
                else None
            )

        cache_attribute = (
            "_iprice_current_approval_cache"
        )

        if hasattr(
            obj,
            cache_attribute,
        ):
            return getattr(
                obj,
                cache_attribute,
            )

        approval = (
            obj.approvals
            .filter(
                is_current=True,
            )
            .select_related(
                "approved_by",
            )
            .order_by(
                "-revision",
                "-id",
            )
            .first()
        )

        setattr(
            obj,
            cache_attribute,
            approval,
        )

        return approval

    def get_current_approval(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is None:
            return None

        return (
            IPriceSnapshotApprovalSerializer(
                approval
            ).data
        )

    def get_effective_approved_rrp(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_rrp

        return (
            obj.default_approved_rrp
            if obj.default_approved_rrp is not None
            else obj.calculated_rrp
        )

    def get_effective_distr(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_distr

        return obj.calculated_distr

    def get_effective_distr_1(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_distr_1

        return obj.calculated_distr_1

    def get_effective_small(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_small

        return obj.calculated_small

    def get_effective_medium(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_medium

        return obj.calculated_medium

    def get_effective_large(
        self,
        obj,
    ):
        approval = (
            self._get_current_approval(
                obj
            )
        )

        if approval is not None:
            return approval.approved_large

        return obj.calculated_large

    @staticmethod
    def _calculate_margin(
        price,
        cost,
    ):
        if price is None or cost is None:
            return None

        price = Decimal(price)

        if price == 0:
            return None

        return (
            price - Decimal(cost)
        ) / price

    def get_effective_margin_calculated(
        self,
        obj,
    ):
        return self._calculate_margin(
            self.get_effective_approved_rrp(obj),
            obj.cost_with_logistics,
        )

    def get_current_vs_effective_approved_amount(
        self,
        obj,
    ):
        effective_rrp = self.get_effective_approved_rrp(
            obj
        )

        if obj.current_retail is None or effective_rrp is None:
            return None

        return Decimal(obj.current_retail) - Decimal(
            effective_rrp
        )

    def get_current_vs_effective_approved_percent(
        self,
        obj,
    ):
        effective_rrp = self.get_effective_approved_rrp(
            obj
        )

        if effective_rrp is None:
            return None

        effective_rrp = Decimal(effective_rrp)

        if effective_rrp == 0 or obj.current_retail is None:
            return None

        return (
            Decimal(obj.current_retail)
            - effective_rrp
        ) / effective_rrp

    def get_previous_effective_margin_calculated(
        self,
        obj,
    ):
        current = self._get_current_approval(obj)

        if current is None:
            return None

        prefetched = getattr(
            obj,
            "prefetched_all_approvals",
            None,
        )

        if prefetched is None:
            prefetched = list(
                obj.approvals.order_by(
                    "-revision",
                    "-id",
                )
            )

        previous = next(
            (
                approval
                for approval in prefetched
                if approval.revision < current.revision
            ),
            None,
        )
        previous_rrp = (
            previous.approved_rrp
            if previous is not None
            else obj.default_approved_rrp
        )

        return self._calculate_margin(
            previous_rrp,
            obj.cost_with_logistics,
        )


class IPriceSnapshotFiltersSerializer(
    serializers.Serializer
):
    mode = serializers.ChoiceField(
        choices=(
            "products",
            "regions",
        ),
        default="products",
    )

    filters = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(
                allow_blank=False,
                trim_whitespace=True,
            ),
            allow_empty=True,
        ),
        required=False,
        default=dict,
    )


class IPriceSnapshotRowsRequestSerializer(
    serializers.Serializer
):
    mode = serializers.ChoiceField(
        choices=(
            "products",
            "regions",
        ),
        default="products",
    )

    page = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )

    page_size = serializers.IntegerField(
        min_value=1,
        max_value=500,
        required=False,
        default=50,
    )

    ordering = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )

    filters = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(
                allow_blank=False,
                trim_whitespace=True,
            ),
            allow_empty=True,
        ),
        required=False,
        default=dict,
    )


class IPricePriceAnalyticsRequestSerializer(
    serializers.Serializer
):
    view = serializers.ChoiceField(
        choices=("products", "regions"),
        default="products",
    )
    drill_level = serializers.ChoiceField(
        choices=(
            "root",
            "category",
            "subcategory",
            "subcategory_type",
        ),
        default="root",
    )
    drill_path = serializers.DictField(
        child=serializers.CharField(
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        default=dict,
    )
    page = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=500,
        required=False,
        default=50,
    )
    ordering = serializers.CharField(
        required=False,
        allow_blank=True,
        default="-product_count",
    )
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )
    filters = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(
                allow_blank=False,
                trim_whitespace=True,
            ),
            allow_empty=True,
        ),
        required=False,
        default=dict,
    )
    price_zones = serializers.ListField(
        child=serializers.ChoiceField(
            choices=(
                "below_market",
                "in_market",
                "above_market",
                "critical_above",
                "no_market_data",
            ),
        ),
        required=False,
        default=list,
    )


class IPriceAnalyticsSelectionSerializer(
    IPricePriceAnalyticsRequestSerializer
):
    pass


class IPricePriceZoneConfigSerializer(
    serializers.Serializer
):
    below_market_percent = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
    )
    above_market_percent = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
    )
    critical_percent = serializers.DecimalField(
        max_digits=8,
        decimal_places=4,
    )

    def validate(self, attrs):
        below = attrs["below_market_percent"]
        above = attrs["above_market_percent"]
        critical = attrs["critical_percent"]

        if below >= 0:
            raise serializers.ValidationError({
                "below_market_percent": (
                    "Нижний порог должен быть меньше нуля."
                ),
            })
        if above <= 0:
            raise serializers.ValidationError({
                "above_market_percent": (
                    "Верхний порог должен быть больше нуля."
                ),
            })
        if critical <= above:
            raise serializers.ValidationError({
                "critical_percent": (
                    "Критический порог должен быть больше верхнего."
                ),
            })
        return attrs


class IPriceSnapshotCompareRequestSerializer(
    serializers.Serializer
):
    MODE_PRODUCTS = "products"
    MODE_REGIONS = "regions"

    CHANGE_ALL = "all"
    CHANGE_ADDED = "added"
    CHANGE_REMOVED = "removed"
    CHANGE_CHANGED = "changed"
    CHANGE_UNCHANGED = "unchanged"
    CHANGE_PRICE_INCREASED = "price_increased"
    CHANGE_PRICE_DECREASED = "price_decreased"
    CHANGE_FINAL_RRP_INCREASED = "final_rrp_increased"
    CHANGE_FINAL_RRP_DECREASED = "final_rrp_decreased"
    CHANGE_NEW_ERROR = "new_error"
    CHANGE_RESOLVED_ERROR = "resolved_error"
    CHANGE_STATUS_CHANGED = "status_changed"

    base_snapshot_id = serializers.IntegerField(
        min_value=1,
    )

    comparison_snapshot_id = serializers.IntegerField(
        min_value=1,
    )

    mode = serializers.ChoiceField(
        choices=(
            MODE_PRODUCTS,
            MODE_REGIONS,
        ),
        default=MODE_PRODUCTS,
    )

    change_type = serializers.ChoiceField(
        choices=(
            CHANGE_ALL,
            CHANGE_ADDED,
            CHANGE_REMOVED,
            CHANGE_CHANGED,
            CHANGE_UNCHANGED,
            CHANGE_PRICE_INCREASED,
            CHANGE_PRICE_DECREASED,
            CHANGE_FINAL_RRP_INCREASED,
            CHANGE_FINAL_RRP_DECREASED,
            CHANGE_NEW_ERROR,
            CHANGE_RESOLVED_ERROR,
            CHANGE_STATUS_CHANGED,
        ),
        required=False,
        default=CHANGE_ALL,
    )

    page = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )

    page_size = serializers.IntegerField(
        min_value=1,
        max_value=500,
        required=False,
        default=50,
    )

    search = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )

    filters = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(
                allow_blank=False,
                trim_whitespace=True,
            ),
            allow_empty=True,
        ),
        required=False,
        default=dict,
    )

    def validate(self, attrs):
        base_snapshot_id = attrs[
            "base_snapshot_id"
        ]

        comparison_snapshot_id = attrs[
            "comparison_snapshot_id"
        ]

        if (
            base_snapshot_id
            == comparison_snapshot_id
        ):
            raise serializers.ValidationError({
                "comparison_snapshot_id": (
                    "Сравниваемая версия должна "
                    "отличаться от базовой."
                ),
            })

        return attrs


class IPriceHealthRequestSerializer(
    serializers.Serializer
):
    LEVEL_ALL = "all"
    LEVEL_ERROR = "ERROR"
    LEVEL_WARNING = "WARNING"

    level = serializers.ChoiceField(
        choices=(
            LEVEL_ALL,
            LEVEL_ERROR,
            LEVEL_WARNING,
        ),
        required=False,
        default=LEVEL_ALL,
    )

    sections = serializers.ListField(
        child=serializers.CharField(
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        allow_empty=True,
        default=list,
    )

    issue_groups = serializers.ListField(
        child=serializers.CharField(
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        allow_empty=True,
        default=list,
    )

    error_codes = serializers.ListField(
        child=serializers.CharField(
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        allow_empty=True,
        default=list,
    )

    search = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    page = serializers.IntegerField(
        required=False,
        min_value=1,
        default=1,
    )

    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=500,
        default=50,
    )

    force_refresh = serializers.BooleanField(
        required=False,
        default=False,
    )


class IPriceSnapshotCompareFiltersRequestSerializer(
    serializers.Serializer
):
    base_snapshot_id = serializers.IntegerField(
        min_value=1,
    )

    comparison_snapshot_id = serializers.IntegerField(
        min_value=1,
    )

    mode = serializers.ChoiceField(
        choices=(
            "products",
            "regions",
        ),
        default="products",
    )

    filters = serializers.DictField(
        child=serializers.ListField(
            child=serializers.CharField(
                allow_blank=False,
                trim_whitespace=True,
            ),
            allow_empty=True,
        ),
        required=False,
        default=dict,
    )

    def validate(
        self,
        attrs,
    ):
        if (
            attrs["base_snapshot_id"]
            == attrs[
                "comparison_snapshot_id"
            ]
        ):
            raise serializers.ValidationError({
                "comparison_snapshot_id": (
                    "Сравниваемая версия должна "
                    "отличаться от базовой."
                ),
            })

        return attrs


class IPriceSnapshotCompetitorSerializer(
    serializers.ModelSerializer
):
    is_price_used_in_calculation = serializers.SerializerMethodField()
    material = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    modification = serializers.SerializerMethodField()
    article_number_analogs = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    additional_property = serializers.SerializerMethodField()

    def _product_metadata(self, obj):
        preloaded = self.context.get("competitor_product_metadata")
        if preloaded is not None:
            return preloaded.get(obj.competitor_product_key, {})

        cache = self.context.setdefault("_competitor_product_metadata_cache", {})
        product_key = obj.competitor_product_key
        if product_key not in cache:
            classification = (
                ParserProductClassification.objects.filter(
                    product_key=product_key,
                    status=ParserProductClassification.STATUS_ACTIVE,
                ).values(
                    "material", "color", "modification", "article_number_analogs", "image"
                ).first()
                or {}
            )
            product_url = (
                ParserProductUrl.objects.filter(id=product_key)
                .values("additional_property").first()
                or {}
            )
            cache[product_key] = {
                **classification,
                "additional_property": product_url.get("additional_property"),
            }
        return cache[product_key]

    def get_material(self, obj):
        return self._product_metadata(obj).get("material")

    def get_color(self, obj):
        return self._product_metadata(obj).get("color")

    def get_modification(self, obj):
        return self._product_metadata(obj).get("modification")

    def get_article_number_analogs(self, obj):
        return self._product_metadata(obj).get("article_number_analogs")

    def get_image(self, obj):
        return self._product_metadata(obj).get("image")

    def get_additional_property(self, obj):
        return self._product_metadata(obj).get("additional_property")

    def get_is_price_used_in_calculation(self, obj):
        return bool(
            obj.competitor_final_price_max is not None
            and obj.competitor_final_price_max > 0
        )

    class Meta:
        model = IPriceSnapshotCompetitor

        fields = [
            "id",
            "snapshot_product",
            "competitor_product_key",
            "source",
            "url",
            "prefix",
            "competitor_price_date",
            "competitor_final_price_max",
            "source_price_row_id",
            "price_variants",
            "is_all_regions",
            "applicable_regions",
            "base_analog",
            "preliminary_rrp",
            "calculation_status",
            "warning_codes",
            "error_codes",
            "is_price_used_in_calculation",
            "material",
            "color",
            "modification",
            "article_number_analogs",
            "image",
            "additional_property",
        ]

        read_only_fields = fields


class IPriceSnapshotApprovalSaveSerializer(
    serializers.Serializer
):
    approved_rrp = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=0,
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )


class IPriceCompetitorSelectionSerializer(serializers.Serializer):
    competitor_product_keys = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=500,
    )
    selection_mode = serializers.ChoiceField(
        choices=("auto", "include", "exclude"),
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=2000,
        trim_whitespace=True,
    )
