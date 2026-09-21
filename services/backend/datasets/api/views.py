from analytics.services.bitrix_notify import send_bitrix_message
import logging

import tempfile
import os
import calendar

from datetime import datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.viewsets import ModelViewSet

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, NullIf

from django.db import models, transaction
from django.utils import timezone

from datasets.models import (
    Dataset,
    DatasetRow,
    PlanSales,
    ParserMasterPipelineRun,
    IPriceSnapshot,
    IPriceSnapshotRegion,
    IPriceSnapshotProduct,
    IPriceSnapshotApproval,
    IPriceCompetitorSelectionOverride,
    BaseProductPrice,
    ParserProductClassification,
    ParserProductUrl,
    FBPurchasesUseIndicator,
    TurnoverIndicator,

)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from datasets.services.fb_project_loader import load_fb_project_csv
from analytics.services.fb_project_sync import sync_fb_project_to_clickhouse

from dashboards.cache.invalidation import invalidate_dashboard_by_name

from dashboards.models import DashboardAccess, Dashboard

from rest_framework.parsers import MultiPartParser, FormParser

from .serializers import (
    DatasetSerializer,
    DatasetRowSerializer,
    FbProjectUploadSerializer,
    FBPurchasesUploadSerializer,
    FBTurnoverUploadSerializer,
    FBAccreceivUploadSerializer,
    IndicatorUploadSerializer,
    PlannedSalesUploadSerializer,
    PlanSalesUploadSerializer,
    PlannedSalesDirectoryUploadSerializer,

    ParserPrefixUploadSerializer,
    ProductClassificationUploadSerializer,

    ExcelUploadSerializer,

    TransportCostUploadSerializer,
    ProductCostUploadSerializer,
    IPriceCalculationConfigUploadSerializer,
    IPriceSnapshotRunSerializer,
    IPriceParameterChangeSerializer,
    IPriceSnapshotSerializer,
    IPriceSnapshotProductSerializer,
    IPriceSnapshotRegionSerializer,
    IPriceSnapshotFiltersSerializer,
    IPriceSnapshotRowsRequestSerializer,
    IPriceSnapshotCompetitorSerializer,
    IPriceSnapshotApprovalSaveSerializer,
    IPriceSnapshotApprovalSerializer,
    IPriceCompetitorSelectionSerializer,
    IPriceSnapshotCompareRequestSerializer,
    IPriceSnapshotCompareFiltersRequestSerializer,
    IPriceHealthRequestSerializer,
    IPricePriceAnalyticsRequestSerializer,
    IPriceAnalyticsSelectionSerializer,
    IPricePriceZoneConfigSerializer,

)





from datasets.services.fb_purchases_loader import (
    load_fb_purchases_use_csv,
    load_fb_purchases_indicator_xlsx,
)
from analytics.services.fb_purchases_sync import sync_fb_purchases_to_clickhouse


from datasets.services.fb_turnover_loader import (
    load_fb_turnover_csv,
    load_fb_turnover_indicator_xlsx,
)
from analytics.services.fb_turnover_sync import sync_fb_turnover_to_clickhouse


from django.core.management import call_command


from datasets.services.fb_accreceiv_loader import (
    load_fb_accreceiv_csv,
    load_fb_accreceiv_indicator_xlsx,
)
from analytics.services.fb_accreceiv_sync import sync_fb_accreceiv_to_clickhouse





from analytics.clickhouse.repository import ClickHouseRepository

from analytics.services.fb_purchases_prepare import (
    group_purchases_by_month,
    add_indicator_to_purchases,
    add_deviation_to_purchases,
)

from analytics.services.fb_turnover_prepare import group_turnover_monthly
from analytics.services.fb_accreceiv_prepare import group_accreceiv_monthly

from analytics.services.excel_exports import (
    export_wordstat_to_excel,
    export_purchases_to_excel,
    export_turnover_to_excel,
    export_accreceiv_to_excel,

    export_revenue_to_excel,
)


from datasets.services.planned_sales_loader import (
    load_planned_sales_csv,
    load_plan_sales_xlsx,
    load_planned_sales_directory_xlsx,
)
from analytics.services.planned_sales_sync import sync_planned_sales_to_clickhouse

from dashboards.realtime import notify_dashboard_updated


from datasets.api.permissions import HasInternalApiKey
from dashboards.api.permissions import (
    CanEditIPriceDashboard,
    CanViewIPriceDashboard,
    get_iprice_dashboard,
)
from dashboards.services.access import (
    user_can_edit_dashboard,
    user_can_view_dashboard,
)
from dashboards.services.audit import (
    log_dashboard_view,
)

from analytics.services.fb_project_api_pipeline import run_fb_project_api_pipeline
from analytics.services.planned_sales_api_pipeline import run_planned_sales_api_pipeline
from analytics.services.fb_purchases_api_pipeline import run_fb_purchases_api_pipeline
from analytics.services.fb_turnover_api_pipeline import run_fb_turnover_api_pipeline
from analytics.services.fb_accreceiv_api_pipeline import run_fb_accreceiv_api_pipeline

from datasets.services.external_api.nomenclature_api_loader import (
    load_nomenclature_from_api,
)

from datasets.services.external_api.price_api_loader import (
    load_prices_from_api,
)

from datasets.services.transport_cost_loader import (
    load_transport_cost_from_excel,
)

from datasets.services.product_cost_loader import (
    load_product_cost_from_excel,
)


from datasets.services.iprice_product_cost_export import (
    export_iprice_product_cost_template,
)

from datasets.services.iprice_upload_template_export import (
    EXCEL_CONTENT_TYPE as IPRICE_TEMPLATE_CONTENT_TYPE,
    UPLOAD_TEMPLATE_HEADERS,
    export_iprice_upload_template,
)

from datasets.services.iprice_parser_products_export import (
    export_iprice_parser_products,
)

from datasets.services.iprice_preparation_check import (
    export_iprice_preparation_check,
)

from datasets.services.iprice_calculation_config_loader import (
    load_iprice_calculation_config_from_xlsx,
)

from datasets.services.iprice_snapshot_builder import (
    activate_iprice_snapshot,
    create_iprice_snapshot,
    deactivate_iprice_snapshot,
    IPriceSnapshotBuildError,
)
from datasets.services.iprice_parameter_changes import (
    IPriceParameterChangeError,
    apply_iprice_parameter_changes,
    preview_iprice_parameter_changes,
)

from datasets.services.iprice_snapshot_launcher import (
    launch_iprice_snapshot,
)

from datasets.services.iprice_snapshot_filters import (
    apply_iprice_products_search,
    apply_iprice_regions_search,
    build_iprice_snapshot_filters,
    filter_iprice_products_queryset,
    filter_iprice_regions_queryset,
)

from datasets.services.iprice_snapshot_approval import (
    IPriceSnapshotApprovalError,
    create_iprice_snapshot_approval,
)

from datasets.services.iprice_snapshot_export import (
    EXCEL_CONTENT_TYPE,
    export_iprice_snapshot_to_excel,
)

from datasets.services.iprice_market_assortment import (
    IPriceMarketAssortmentError,
    build_iprice_market_assortment,
    group_snapshot_competitor_cards,
)
from datasets.services.iprice_own_assortment import (
    IPriceOwnAssortmentError,
    build_iprice_own_assortment,
)

from datasets.services.iprice_snapshot_compare import (
    IPriceSnapshotCompareError,
    compare_iprice_snapshots,
    build_iprice_snapshot_compare_filters,
)

from datasets.services.iprice_health import (
    build_iprice_health_response,
)
from datasets.services.iprice_price_analytics import (
    IPricePriceAnalyticsError,
    activate_price_zone_config,
    build_iprice_price_analytics,
    build_iprice_regional_price_analytics,
    resolve_iprice_analytics_product_keys,
    get_active_price_zone_config,
    serialize_price_zone_config,
)
from datasets.services.iprice_analytics_selection import (
    create_analytics_selection,
    get_analytics_selection,
)
from datasets.services.iprice_runtime import (
    publish_iprice_update,
    sync_activation_and_publish,
    sync_approval_and_publish,
    sync_snapshot_and_publish,
)
from datasets.services.iprice_competitor_selection import (
    IPriceCompetitorSelectionError,
    apply_competitor_selection,
    is_selection_editable,
)
from dashboards.cache.iprice_cache import (
    get_iprice_cache as _get_iprice_cache,
    set_iprice_cache as _set_iprice_cache,
)

from django.core.paginator import Paginator

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from dashboards.models import DashboardPublicAccess, DashboardPublicGroup


from datasets.services.parsers.prefix_loader import load_parser_prefixes_from_excel

from datasets.services.parsers.product_classification_match_loader import (
    ProductClassificationMatchLoadError,
    load_product_classification_matches,
)

from datasets.services.parsers.master_pipeline_launcher import (
    launch_parser_master_pipeline,
)



from datasets.services.external_api.yd_wordstat_ref_excel_loader import (
    load_yd_wordstat_phrase_ref_from_excel,
    load_yd_wordstat_device_ref_from_excel,
    load_yd_wordstat_iplast_region_ref_from_excel,
)



from analytics.services.yd_wordstat_api_pipeline import run_yd_wordstat_api_pipeline


from django.core.cache import cache




SALES_PIPELINE_RUNNING_LOCK_KEY = "sales_pipeline_running_lock"
SALES_MANUAL_REFRESH_LOCK_KEY = "sales_api_refresh_lock"

SALES_PIPELINE_RUNNING_LOCK_TIMEOUT = 60 * 60
SALES_MANUAL_REFRESH_LOCK_TIMEOUT = 60 * 60


PARSER_MASTER_START_LOCK_KEY = "parser_master_pipeline_start_lock"
PARSER_MASTER_START_LOCK_TIMEOUT = 60


IPRICE_SNAPSHOT_START_LOCK_KEY = (
    "iprice_snapshot_start_lock"
)

IPRICE_SNAPSHOT_START_LOCK_TIMEOUT = 60
IPRICE_PARAMETER_CHANGE_LOCK_KEY = "iprice:parameter-change"


def get_iprice_cache(scope, payload):
    try:
        return _get_iprice_cache(scope, payload)
    except Exception:
        return None


def set_iprice_cache(scope, payload, value):
    try:
        _set_iprice_cache(scope, payload, value)
    except Exception:
        pass






def get_public_group_or_404(token):
    try:
        group = DashboardPublicGroup.objects.prefetch_related(
            "items__dashboard"
        ).get(token=token)
    except DashboardPublicGroup.DoesNotExist:
        raise NotFound("Public group not found")

    if not group.is_valid():
        raise PermissionDenied("Public group expired")

    return group


def check_public_dashboard_access(token, dashboard_slug):
    group = get_public_group_or_404(token)

    group_item = (
        group.items
        .select_related("dashboard")
        .filter(dashboard__slug=dashboard_slug)
        .first()
    )

    if group_item is None:
        raise PermissionDenied("Dashboard is not available in this public group")

    return group_item


def check_any_public_dashboard_access(token, dashboard_slug):
    """Accept both a public-group token and a direct dashboard public token."""
    group = DashboardPublicGroup.objects.filter(token=token).first()
    if group is not None:
        if not group.is_valid():
            raise PermissionDenied("Public group expired")
        item = group.items.select_related("dashboard").filter(dashboard__slug=dashboard_slug).first()
        if item is None:
            raise PermissionDenied("Dashboard is not available in this public group")
        return item.dashboard
    public_access = DashboardPublicAccess.objects.select_related("dashboard").filter(
        token=token, dashboard__slug=dashboard_slug,
    ).first()
    if public_access is None:
        raise NotFound("Public dashboard link not found")
    if not public_access.is_valid():
        raise PermissionDenied("Public dashboard link is inactive or expired")
    return public_access.dashboard


def _plan_date(value, field_name):
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError({field_name: "Укажите дату в формате ГГГГ-ММ-ДД."})
    return parsed


def _days_between(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class ProcurementPlanView(APIView):
    permission_classes = [IsAuthenticated]
    dashboard_slug = ""
    dashboard_name = ""
    model = None
    date_field = ""
    sync = None

    def _authorize(self, request, **kwargs):
        dashboard = Dashboard.objects.filter(slug=self.dashboard_slug).first()
        if dashboard is None:
            raise NotFound("Dashboard not found")
        if not user_can_view_dashboard(request.user, dashboard):
            raise PermissionDenied("Нет доступа к дашборду.")

    def _range(self, data):
        start = _plan_date(data.get("date_start"), "date_start")
        end = _plan_date(data.get("date_end"), "date_end")
        if start > end:
            raise ValidationError({"period": "Начало периода не может быть позже окончания."})
        if start.day != 1 or end.day != calendar.monthrange(end.year, end.month)[1]:
            raise ValidationError({
                "period": "Период плана должен начинаться с первого числа месяца и заканчиваться последним числом месяца."
            })
        if (end - start).days > 3652:
            raise ValidationError({"period": "Период не должен превышать 10 лет."})
        return start, end

    def _existing(self, start, end):
        rows = self.model.objects.filter(**{
            f"{self.date_field}__gte": start,
            f"{self.date_field}__lte": end,
        }).order_by(self.date_field, "id").values(self.date_field, "indicator")
        return [{"period": row[self.date_field].isoformat(), "value": int(row["indicator"])} for row in rows]

    def get(self, request, **kwargs):
        self._authorize(request, **kwargs)
        start, end = self._range(request.query_params)
        return Response({"existing": self._existing(start, end)})

    def post(self, request, **kwargs):
        self._authorize(request, **kwargs)
        start, end = self._range(request.data)
        try:
            value = int(str(request.data.get("value", "")).strip())
        except (TypeError, ValueError):
            raise ValidationError({"value": "Введите целое плановое значение."})
        if value <= 0:
            raise ValidationError({"value": "Плановое значение должно быть больше нуля."})
        days = list(_days_between(start, end))
        existing = self._existing(start, end)
        with transaction.atomic():
            self.model.objects.filter(**{
                f"{self.date_field}__gte": start,
                f"{self.date_field}__lte": end,
            }).delete()
            self.model.objects.bulk_create([
                self.model(**{self.date_field: day, "indicator": value}) for day in days
            ])
        self.sync()
        invalidate_dashboard_by_name(self.dashboard_name)
        notify_dashboard_updated(self.dashboard_name)
        return Response({
            "status": "ok", "updated_days": len(days), "value": value,
            "date_start": start.isoformat(), "date_end": end.isoformat(),
            "replaced": existing,
        })


class PurchasesPlanView(ProcurementPlanView):
    dashboard_slug = "purchases"
    dashboard_name = "Purchases"
    model = FBPurchasesUseIndicator
    date_field = "date_draft"
    sync = staticmethod(sync_fb_purchases_to_clickhouse)


class TurnoverPlanView(ProcurementPlanView):
    dashboard_slug = "turnover"
    dashboard_name = "Turnover"
    model = TurnoverIndicator
    date_field = "date_start"
    sync = staticmethod(sync_fb_turnover_to_clickhouse)


class PublicProcurementPlanMixin:
    authentication_classes = []
    permission_classes = []

    def _authorize(self, request, token=None, **kwargs):
        check_any_public_dashboard_access(token, self.dashboard_slug)


class PublicPurchasesPlanView(PublicProcurementPlanMixin, PurchasesPlanView):
    pass


class PublicTurnoverPlanView(PublicProcurementPlanMixin, TurnoverPlanView):
    pass









class DatasetViewSet(ModelViewSet):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer

class DatasetRowViewSet(ModelViewSet):
    queryset = DatasetRow.objects.all()
    serializer_class = DatasetRowSerializer





class FbProjectUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FbProjectUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            if not uploaded_file:
                return Response(
                    {"error": "file is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)

                temp_path = temp_file.name

            postgres_count = load_fb_project_csv(temp_path)
            projects_count = sync_fb_project_to_clickhouse()

            invalidate_dashboard_by_name("Projects")

            return Response({
                "status": "ok",
                "postgres_rows": postgres_count,
                "projects_count": projects_count,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FbProjectUploadView failed")
            send_bitrix_message("[b]FbProjectUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class FBPurchasesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBPurchasesUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            use_file = serializer.validated_data["use_file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_use:
                for chunk in use_file.chunks():
                    temp_use.write(chunk)
                use_path = temp_use.name

            postgres_use_count = load_fb_purchases_use_csv(use_path)

            clickhouse_result = sync_fb_purchases_to_clickhouse()

            invalidate_dashboard_by_name("Purchases")

            return Response({
                "status": "ok",
                "postgres": {
                    "fb_purchases_use": postgres_use_count,
                },
                "clickhouse": clickhouse_result,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBPurchasesUploadView failed")
            send_bitrix_message("[b]FBPurchasesUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise




class FBTurnoverUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBTurnoverUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            turnover_file = serializer.validated_data["turnover_file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_turnover:
                for chunk in turnover_file.chunks():
                    temp_turnover.write(chunk)
                turnover_path = temp_turnover.name

            postgres_turnover_count = load_fb_turnover_csv(turnover_path)

            clickhouse_result = sync_fb_turnover_to_clickhouse()

            invalidate_dashboard_by_name("Turnover")

            call_command("warmup_turnover_cache")

            return Response({
                "status": "ok",
                "postgres": {
                    "fb_turnover_use": postgres_turnover_count,
                },
                "clickhouse": clickhouse_result,
                "cache": {
                    "invalidated": "Turnover",
                    "warmed": True,
                    "command": "warmup_turnover_cache",
                },
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBTurnoverUploadView failed")
            send_bitrix_message("[b]FBTurnoverUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise




class FBAccreceivUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = FBAccreceivUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            accreceiv_file = serializer.validated_data["accreceiv_file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_accreceiv:
                for chunk in accreceiv_file.chunks():
                    temp_accreceiv.write(chunk)
                accreceiv_path = temp_accreceiv.name

            postgres_accreceiv_count = load_fb_accreceiv_csv(accreceiv_path)

            clickhouse_result = sync_fb_accreceiv_to_clickhouse()

            invalidate_dashboard_by_name("Accreceiv")

            return Response({
                "status": "ok",
                "postgres": {
                    "fb_accreceiv_use": postgres_accreceiv_count,
                },
                "clickhouse": clickhouse_result,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBAccreceivUploadView failed")
            send_bitrix_message("[b]FBAccreceivUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise
    




class FBAccreceivIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            dashboard = Dashboard.objects.filter(slug="accreceiv").first()
            if dashboard is None:
                raise NotFound("Dashboard not found")
            if not user_can_edit_dashboard(request.user, dashboard):
                raise PermissionDenied("Нет права редактирования дашборда.")

            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            try:
                postgres_result = load_fb_accreceiv_indicator_xlsx(temp_path)
                clickhouse_result = sync_fb_accreceiv_to_clickhouse()

                invalidate_dashboard_by_name("Accreceiv")

                return Response({
                    "status": "ok",
                    "postgres": postgres_result,
                    "clickhouse": clickhouse_result,
                })
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBAccreceivIndicatorUploadView failed")
            send_bitrix_message("[b]FBAccreceivIndicatorUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class FBPurchasesIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            postgres_result = load_fb_purchases_indicator_xlsx(temp_path)
            clickhouse_result = sync_fb_purchases_to_clickhouse()

            invalidate_dashboard_by_name("Purchases")

            return Response({
                "status": "ok",
                "postgres": postgres_result,
                "clickhouse": clickhouse_result,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBPurchasesIndicatorUploadView failed")
            send_bitrix_message("[b]FBPurchasesIndicatorUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class FBTurnoverIndicatorUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IndicatorUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            postgres_result = load_fb_turnover_indicator_xlsx(temp_path)
            clickhouse_result = sync_fb_turnover_to_clickhouse()

            invalidate_dashboard_by_name("Turnover")
            call_command("warmup_turnover_cache")

            return Response({
                "status": "ok",
                "postgres": postgres_result,
                "clickhouse": clickhouse_result,
                "cache": {
                    "warmed": True,
                    "command": "warmup_turnover_cache",
                },
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("FBTurnoverIndicatorUploadView failed")
            send_bitrix_message("[b]FBTurnoverIndicatorUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise







class WordstatExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_yd_wordstat_rows(filters)

        return export_wordstat_to_excel(rows)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)
    


class FBPurchasesExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_purchases_use_rows(filters)
        indicator_rows = repo.fetch_fb_purchases_indicator_rows(filters)

        purchases_list = group_purchases_by_month(rows)
        purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
        purchases_list = add_deviation_to_purchases(purchases_list)

        return export_purchases_to_excel(purchases_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)


class FBTurnoverExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_turnover_use_rows(filters)

        turnover_list = group_turnover_monthly(rows)

        return export_turnover_to_excel(turnover_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)


class FBAccreceivExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_fb_accreceiv_use_rows(filters)

        accreceiv_list = group_accreceiv_monthly(rows)

        return export_accreceiv_to_excel(accreceiv_list)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)





class PublicFBTurnoverExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="turnover",
        )
        filters = request.data or {}
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_turnover_use_rows(filters)
        turnover_list = group_turnover_monthly(rows)
        return export_turnover_to_excel(turnover_list)
    def get(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="turnover",
        )
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        repo = ClickHouseRepository()
        rows = repo.fetch_fb_turnover_use_rows(filters)
        turnover_list = group_turnover_monthly(rows)
        return export_turnover_to_excel(turnover_list)


class PublicFBAccreceivExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def post(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="accreceiv",
        )
        filters = request.data or {}
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_accreceiv_use_rows(filters)
        accreceiv_list = group_accreceiv_monthly(rows)
        return export_accreceiv_to_excel(accreceiv_list)
    def get(self, request, token):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="accreceiv",
        )
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)
            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_accreceiv_use_rows(filters)
        accreceiv_list = group_accreceiv_monthly(rows)
        return export_accreceiv_to_excel(accreceiv_list)


class PublicFBPurchasesExportView(APIView):
    authentication_classes = []
    permission_classes = []
    def _get_filters_from_query_params(self, request):
        filters = {}
        for key in request.query_params.keys():
            values = request.query_params.getlist(key)
            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]
        return filters
    def _get_filters_from_body(self, request):
        return request.data or {}
    def _export(self, token, filters):
        check_public_dashboard_access(
            token=token,
            dashboard_slug="purchases",
        )
        repo = ClickHouseRepository()
        rows = repo.fetch_fb_purchases_use_rows(filters)
        indicator_rows = repo.fetch_fb_purchases_indicator_rows(filters)
        purchases_list = group_purchases_by_month(rows)
        purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
        purchases_list = add_deviation_to_purchases(purchases_list)
        return export_purchases_to_excel(purchases_list)
    def get(self, request, token):
        filters = self._get_filters_from_query_params(request)
        return self._export(token=token, filters=filters)
    def post(self, request, token):
        filters = self._get_filters_from_body(request)
        return self._export(token=token, filters=filters)














class PlannedSalesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlannedSalesUploadSerializer

    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            postgres_count = load_planned_sales_csv(temp_path)
            clickhouse_result = sync_planned_sales_to_clickhouse()

            invalidate_dashboard_by_name("PlannedSales")
            notify_dashboard_updated("PlannedSales")

            return Response({
                "status": "ok",
                "postgres": {
                    "planned_sales": postgres_count,
                },
                "clickhouse": clickhouse_result,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("PlannedSalesUploadView failed")
            send_bitrix_message("[b]PlannedSalesUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class PlanSalesUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlanSalesUploadSerializer

    def post(self, request):
        try:
            dashboard = Dashboard.objects.filter(name="PlannedSales").first()

            if not dashboard:
                return Response(
                    {"error": "PlannedSales dashboard not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            can_edit = DashboardAccess.objects.filter(
                user=request.user,
                dashboard=dashboard,
                can_edit=True,
            ).exists()

            if not can_edit:
                return Response(
                    {"error": "No edit permission"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".xlsx",
            ) as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)

                temp_path = temp_file.name

            try:
                postgres_count = load_plan_sales_xlsx(temp_path)

                clickhouse_result = sync_planned_sales_to_clickhouse()

                invalidate_dashboard_by_name("PlannedSales")
                notify_dashboard_updated("PlannedSales")

                return Response({
                    "status": "ok",
                    "postgres": {
                        "plan_sales": postgres_count,
                    },
                    "clickhouse": clickhouse_result,
                })

            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("PlanSalesUploadView failed")
            send_bitrix_message("[b]PlanSalesUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class PlannedSalesDirectoryUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = PlannedSalesDirectoryUploadSerializer

    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            postgres_count = load_planned_sales_directory_xlsx(temp_path)
            clickhouse_result = sync_planned_sales_to_clickhouse()

            invalidate_dashboard_by_name("PlannedSales")
            notify_dashboard_updated("PlannedSales")

            return Response({
                "status": "ok",
                "postgres": {
                    "planned_sales_directory": postgres_count,
                },
                "clickhouse": clickhouse_result,
            })
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("PlannedSalesDirectoryUploadView failed")
            send_bitrix_message("[b]PlannedSalesDirectoryUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise




class PlannedSalesSavePlanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        field = request.data.get("field")
        value = request.data.get("value")
        row_date = request.data.get("date")
        id_directory = request.data.get("id_directory")

        dashboard = Dashboard.objects.filter(name="PlannedSales").first()

        if not dashboard:
            return Response(
                {"error": "PlannedSales dashboard not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        can_edit = DashboardAccess.objects.filter(
            user=request.user,
            dashboard=dashboard,
            can_edit=True,
        ).exists()

        if not can_edit:
            return Response(
                {"error": "No edit permission"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if field == "projection":
            field = "projection_s"

        if field not in ("plan", "projection_s"):
            return Response(
                {"error": "field must be plan or projection_s"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not row_date or not id_directory:
            return Response(
                {"error": "date and id_directory are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            parsed_row_date = datetime.strptime(
                str(row_date),
                "%Y-%m-%d",
            ).date()
        except (TypeError, ValueError):
            return Response(
                {"error": "date must be YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_month = timezone.localdate().replace(day=1)
        row_month = parsed_row_date.replace(day=1)
        if field == "projection_s" and row_month < current_month:
            return Response(
                {
                    "error": (
                        "Проекция прошедшего месяца равна факту "
                        "и недоступна для редактирования"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        PlanSales.objects.update_or_create(
            date=parsed_row_date,
            id_directory=int(id_directory),
            defaults={
                field: value or 0,
            },
        )

        clickhouse_result = sync_planned_sales_to_clickhouse()

        invalidate_dashboard_by_name("PlannedSales")
        notify_dashboard_updated("PlannedSales")

        return Response({
            "status": "ok",
            "clickhouse": clickhouse_result,
        })
    




class FbProjectApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_project_api_pipeline()
        return Response(result)
    

class PlannedSalesApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        running_lock_acquired = cache.add(
            SALES_PIPELINE_RUNNING_LOCK_KEY,
            True,
            timeout=SALES_PIPELINE_RUNNING_LOCK_TIMEOUT,
        )

        if not running_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполняется",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            result = run_planned_sales_api_pipeline()
            return Response(result)

        finally:
            cache.delete(SALES_PIPELINE_RUNNING_LOCK_KEY)



class SalesRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        manual_lock_acquired = cache.add(
            SALES_MANUAL_REFRESH_LOCK_KEY,
            True,
            timeout=SALES_MANUAL_REFRESH_LOCK_TIMEOUT,
        )

        if not manual_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполнено за текущий час",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        running_lock_acquired = cache.add(
            SALES_PIPELINE_RUNNING_LOCK_KEY,
            True,
            timeout=SALES_PIPELINE_RUNNING_LOCK_TIMEOUT,
        )

        if not running_lock_acquired:
            return Response(
                {
                    "status": "locked",
                    "message": "Обновление данных уже выполняется",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            result = run_planned_sales_api_pipeline()
            return Response(result)

        finally:
            cache.delete(SALES_PIPELINE_RUNNING_LOCK_KEY)



class FBPurchasesApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_purchases_api_pipeline()

        return Response(result)
    

class FBTurnoverApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_turnover_api_pipeline()

        return Response(result)
    

class FBAccreceivApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_fb_accreceiv_api_pipeline()

        return Response(result)
    



class TableHealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        call_command("check_table_health")

        return Response({
            "status": "ok",
            "command": "check_table_health",
        })


class ProcessKillView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        call_command("kill_long_running_processes")

        return Response({
            "status": "ok",
            "command": "kill_long_running_processes",
        })
    







class ParserPrefixUploadView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ParserPrefixUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            try:
                result = load_parser_prefixes_from_excel(
                    uploaded_file
                )

            except ValueError as exc:
                send_bitrix_message("[b]ParserPrefixUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043c\u043f\u043e\u0440\u0442\u0430: \u0444\u0430\u0439\u043b \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043e\u0442\u0432\u0435\u0442\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.", logger_name="datasets.upload")
                return Response(
                    {
                        "status": "error",
                        "error": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publish_iprice_update(
                "source_data_updated",
                invalidate_health=True,
                source="regional_prefixes",
            )

            return Response(
                {
                    "status": "ok",
                    **result,
                },
                status=status.HTTP_200_OK,
            )
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("ParserPrefixUploadView failed")
            send_bitrix_message("[b]ParserPrefixUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class ParserMasterPipelineRunView(APIView):
    def get_permissions(self):
        permission_class = (
            CanViewIPriceDashboard
            if self.request.method == "GET"
            else CanEditIPriceDashboard
        )
        return [permission_class()]

    def get(
        self,
        request,
    ):
        active_run = (
            ParserMasterPipelineRun.objects
            .filter(
                status__in=[
                    (
                        ParserMasterPipelineRun
                        .STATUS_QUEUED
                    ),
                    (
                        ParserMasterPipelineRun
                        .STATUS_RUNNING
                    ),
                    ParserMasterPipelineRun.STATUS_WAITING_TARA,
                    ParserMasterPipelineRun.STATUS_WAITING_SESSION,
                ],
            )
            .select_related(
                "started_by",
            )
            .order_by(
                "-date_add",
            )
            .first()
        )

        latest_run = (
            ParserMasterPipelineRun.objects
            .select_related(
                "started_by",
            )
            .order_by(
                "-date_add",
            )
            .first()
        )

        return Response(
            {
                "active_run": (
                    self._serialize_run(
                        active_run
                    )
                    if active_run
                    else None
                ),
                "latest_run": (
                    self._serialize_run(
                        latest_run
                    )
                    if latest_run
                    else None
                ),
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        lock_acquired = cache.add(
            PARSER_MASTER_START_LOCK_KEY,
            True,
            timeout=PARSER_MASTER_START_LOCK_TIMEOUT,
        )

        if not lock_acquired:
            return Response(
                {
                    "status": "launch_in_progress",
                    "message": (
                        "Запрос на запуск парсеров уже обрабатывается"
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            return self._start_pipeline(request)

        finally:
            cache.delete(PARSER_MASTER_START_LOCK_KEY)

    def _start_pipeline(self, request):
        now = timezone.now()

        stale_before = now - timedelta(
            hours=settings.PARSER_MASTER_PIPELINE_STALE_HOURS,
        )

        # Если контейнер или отдельный процесс ранее аварийно завершился,
        # старая запись queued/running не должна навсегда блокировать запуск.
        stale_runs = (
            ParserMasterPipelineRun.objects
            .filter(
                status__in=[
                    ParserMasterPipelineRun.STATUS_QUEUED,
                    ParserMasterPipelineRun.STATUS_RUNNING,
                ]
            )
            .filter(
                models.Q(
                    started_at__lt=stale_before,
                )
                | models.Q(
                    started_at__isnull=True,
                    date_add__lt=stale_before,
                )
            )
        )

        stale_runs = stale_runs.exclude(current_step__startswith="tara_")

        stale_runs.update(
            status=ParserMasterPipelineRun.STATUS_FAILED,
            current_step="stale",
            finished_at=now,
            error=(
                "Запуск автоматически помечен как failed: "
                "статус queued/running устарел."
            ),
        )

        active_run = (
            ParserMasterPipelineRun.objects
            .filter(
                status__in=[
                    ParserMasterPipelineRun.STATUS_QUEUED,
                    ParserMasterPipelineRun.STATUS_RUNNING,
                    ParserMasterPipelineRun.STATUS_WAITING_TARA,
                    ParserMasterPipelineRun.STATUS_WAITING_SESSION,
                ]
            )
            .select_related("started_by")
            .order_by("-date_add")
            .first()
        )

        if active_run is not None:
            return Response(
                {
                    "status": "already_running",
                    "message": (
                        "Мастер-пайплайн парсеров уже выполняется"
                    ),
                    "run": self._serialize_run(active_run),
                },
                status=status.HTTP_409_CONFLICT,
            )

        run = ParserMasterPipelineRun.objects.create(
            status=ParserMasterPipelineRun.STATUS_QUEUED,
            current_step="queued",
            started_by=request.user,
        )

        try:
            process_id = launch_parser_master_pipeline(
                run_id=run.pk,
            )

        except Exception as exc:
            run.status = ParserMasterPipelineRun.STATUS_FAILED
            run.current_step = "launch_failed"
            run.finished_at = timezone.now()
            run.error = str(exc)
            run.result = {
                "status": "failed",
                "failed_step": "launch",
                "error": str(exc),
            }

            run.save(
                update_fields=[
                    "status",
                    "current_step",
                    "finished_at",
                    "error",
                    "result",
                ]
            )

            publish_iprice_update(
                "parser_failed",
                invalidate_health=True,
                run_id=run.pk,
                current_step=run.current_step,
            )

            return Response(
                {
                    "status": "error",
                    "message": (
                        "Не удалось запустить "
                        "мастер-пайплайн парсеров"
                    ),
                    "run": self._serialize_run(run),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_run = self._serialize_run(run)
        response_run["process_id"] = process_id

        publish_iprice_update(
            "parser_started",
            run_id=run.pk,
            current_step=run.current_step,
            process_id=process_id,
        )

        return Response(
            {
                "status": "started",
                "message": (
                    "Мастер-пайплайн парсеров запущен"
                ),
                "run": response_run,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @staticmethod
    def _serialize_run(run):
        return {
            "id": run.pk,
            "status": run.status,
            "current_step": run.current_step,
            "started_by": (
                run.started_by.username
                if run.started_by
                else None
            ),
            "date_add": (
                run.date_add.isoformat()
                if run.date_add
                else None
            ),
            "started_at": (
                run.started_at.isoformat()
                if run.started_at
                else None
            ),
            "finished_at": (
                run.finished_at.isoformat()
                if run.finished_at
                else None
            ),
            "error": run.error,
            "result": run.result,
        }


class ProductClassificationUploadView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ProductClassificationUploadSerializer

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            if not uploaded_file.name.casefold().endswith(".xlsx"):
                return Response(
                    {"status": "error", "error": "Ожидается файл .xlsx"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            lock_key = IPRICE_PARAMETER_CHANGE_LOCK_KEY
            if not cache.add(lock_key, True, timeout=60 * 30):
                return Response(
                    {
                        "status": "already_running",
                        "message": (
                            "Дождитесь завершения текущего изменения данных iPrice"
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            try:
                if (
                    cache.get(IPRICE_SNAPSHOT_START_LOCK_KEY)
                    or IPriceSnapshot.objects.filter(
                        status=IPriceSnapshot.STATUS_BUILDING,
                    ).exists()
                ):
                    return Response(
                        {
                            "status": "calculation_running",
                            "message": (
                                "Дождитесь завершения текущего расчёта iPrice"
                            ),
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                try:
                    result = load_product_classification_matches(
                        uploaded_file,
                        filename=uploaded_file.name,
                    )
                except ProductClassificationMatchLoadError as exc:
                    send_bitrix_message("[b]ProductClassificationUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043c\u043f\u043e\u0440\u0442\u0430: \u0444\u0430\u0439\u043b \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043e\u0442\u0432\u0435\u0442\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.", logger_name="datasets.upload")
                    return Response(
                        {"status": "error", "error": str(exc)},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                publish_iprice_update(
                    "product_classification_applied",
                    invalidate_health=True,
                )
                return Response(result, status=status.HTTP_200_OK)
            finally:
                cache.delete(lock_key)
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("ProductClassificationUploadView failed")
            send_bitrix_message("[b]ProductClassificationUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise







class BaseYdWordstatRefExcelUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ExcelUploadSerializer
    loader_func = None

    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = serializer.validated_data["file"]

            temp_path = None

            try:
                suffix = os.path.splitext(uploaded_file.name)[1] or ".xlsx"

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=suffix,
                ) as temp_file:
                    for chunk in uploaded_file.chunks():
                        temp_file.write(chunk)

                    temp_path = temp_file.name

                result = self.loader_func(temp_path)

                return Response(result)

            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("BaseYdWordstatRefExcelUploadView failed")
            send_bitrix_message("[b]BaseYdWordstatRefExcelUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise



class YdWordstatPhraseRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_phrase_ref_from_excel)


class YdWordstatDeviceRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_device_ref_from_excel)


class YdWordstatIplastRegionRefUploadView(BaseYdWordstatRefExcelUploadView):
    loader_func = staticmethod(load_yd_wordstat_iplast_region_ref_from_excel)


class YdWordstatFullLoadFromApiView(APIView):
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = run_yd_wordstat_api_pipeline(source=None)
        return Response(result)


class BaseYdWordstatApiPipelineView(APIView):
    permission_classes = [IsAuthenticated]
    source = None

    def post(self, request):
        result = run_yd_wordstat_api_pipeline(source=self.source)
        return Response(result)


class YdWordstatAllLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "all"


class YdWordstatDeviceLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "device"


class YdWordstatRegionLoadFromApiView(BaseYdWordstatApiPipelineView):
    source = "region"






class RevenueExportView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return filters

    def _get_filters_from_body(self, request):
        return request.data or {}

    def _export(self, filters):
        repo = ClickHouseRepository()

        rows = repo.fetch_revenue_sales_rows(filters)

        return export_revenue_to_excel(rows)

    def get(self, request):
        filters = self._get_filters_from_query_params(request)

        return self._export(filters)

    def post(self, request):
        filters = self._get_filters_from_body(request)

        return self._export(filters)




class NomenclatureApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = load_nomenclature_from_api()

        return Response(result)


class NomenclaturePriceApiLoadView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        result = load_prices_from_api()
        return Response(result)


class TransportCostUploadView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = TransportCostUploadSerializer

    def post(self, request):
        try:
            serializer = self.serializer_class(
                data=request.data,
            )

            serializer.is_valid(
                raise_exception=True,
            )

            uploaded_file = serializer.validated_data["file"]

            try:
                result = load_transport_cost_from_excel(
                    uploaded_file
                )

            except ValueError as exc:
                send_bitrix_message("[b]TransportCostUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043c\u043f\u043e\u0440\u0442\u0430: \u0444\u0430\u0439\u043b \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043e\u0442\u0432\u0435\u0442\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.", logger_name="datasets.upload")
                return Response(
                    {
                        "status": "error",
                        "error": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publish_iprice_update(
                "source_data_updated",
                invalidate_health=True,
                source="transport_costs",
            )

            return Response(
                {
                    "status": "ok",
                    **result,
                },
                status=status.HTTP_200_OK,
            )
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("TransportCostUploadView failed")
            send_bitrix_message("[b]TransportCostUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class ProductCostUploadView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = ProductCostUploadSerializer

    def post(self, request):
        try:
            serializer = self.serializer_class(
                data=request.data,
            )

            serializer.is_valid(
                raise_exception=True,
            )

            uploaded_file = serializer.validated_data["file"]

            try:
                result = load_product_cost_from_excel(
                    uploaded_file
                )

            except ValueError as exc:
                send_bitrix_message("[b]ProductCostUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043c\u043f\u043e\u0440\u0442\u0430: \u0444\u0430\u0439\u043b \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043e\u0442\u0432\u0435\u0442\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.", logger_name="datasets.upload")
                return Response(
                    {
                        "status": "error",
                        "error": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publish_iprice_update(
                "source_data_updated",
                invalidate_health=True,
                source="product_costs",
            )

            return Response(
                {
                    "status": "ok",
                    **result,
                },
                status=status.HTTP_200_OK,
            )
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("ProductCostUploadView failed")
            send_bitrix_message("[b]ProductCostUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class IPriceAccessView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        dashboard = get_iprice_dashboard(request)

        log_dashboard_view(
            request=request,
            dashboard=dashboard,
            filters={},
            access_type="auth",
        )

        return Response({
            "dashboard": {
                "id": dashboard.id,
                "name": dashboard.name,
                "slug": dashboard.slug,
                "can_view": True,
                "can_edit": user_can_edit_dashboard(
                    request.user,
                    dashboard,
                ),
            },
        })


class IPriceProductCostTemplateExportView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        file_obj = export_iprice_product_cost_template()

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = (
            f"iprice_product_cost_template_"
            f"{timestamp}.xlsx"
        )

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )


class IPriceUploadTemplateExportView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request, upload_type):
        if upload_type not in UPLOAD_TEMPLATE_HEADERS:
            raise Http404("Неизвестный тип шаблона iPrice")

        file_obj = export_iprice_upload_template(
            upload_type
        )
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=(
                f"iprice_{upload_type}_template_"
                f"{timestamp}.xlsx"
            ),
            content_type=IPRICE_TEMPLATE_CONTENT_TYPE,
        )


class IPriceParserProductsExportView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        file_obj = export_iprice_parser_products()

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = (
            f"iprice_parser_products_"
            f"{timestamp}.xlsx"
        )

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

class IPricePreparationCheckExportView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        file_obj, check_result = (
            export_iprice_preparation_check()
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = (
            f"iprice_preparation_check_"
            f"{timestamp}.xlsx"
        )

        response = FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        # Это пригодится фронту:
        response["X-IPrice-Check-Status"] = (
            check_result["status"]
        )

        response["X-IPrice-Check-Errors"] = str(
            check_result["errors"]
        )

        return response


class IPriceCalculationConfigUploadView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = IPriceCalculationConfigUploadSerializer

    def post(self, request):
        try:
            serializer = self.serializer_class(
                data=request.data,
            )

            serializer.is_valid(
                raise_exception=True,
            )

            uploaded_file = serializer.validated_data["file"]

            if not uploaded_file.name.lower().endswith(".xlsx"):
                return Response(
                    {
                        "status": "error",
                        "error": (
                            "Поддерживается только формат XLSX"
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                result = (
                    load_iprice_calculation_config_from_xlsx(
                        uploaded_file
                    )
                )

            except ValueError as exc:
                send_bitrix_message("[b]IPriceCalculationConfigUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0438\u043c\u043f\u043e\u0440\u0442\u0430: \u0444\u0430\u0439\u043b \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043e\u0442\u0432\u0435\u0442\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u0447\u0438\u043a\u0430.", logger_name="datasets.upload")
                return Response(
                    {
                        "status": "error",
                        "error": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            publish_iprice_update(
                "source_data_updated",
                invalidate_health=True,
                source="calculation_config",
            )

            return Response(
                {
                    "status": "ok",
                    **result,
                },
                status=status.HTTP_200_OK,
            )
        except (ValidationError, PermissionDenied, NotFound):
            raise
        except Exception:
            logging.getLogger("datasets.upload").exception("IPriceCalculationConfigUploadView failed")
            send_bitrix_message("[b]IPriceCalculationConfigUploadView[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0444\u0430\u0439\u043b\u0430 \u0438\u043b\u0438 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0434\u0430\u043d\u043d\u044b\u0445. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0435 Django.", logger_name="datasets.upload")
            raise


class IPriceParameterChangeView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    serializer_class = IPriceParameterChangeSerializer

    def post(self, request, snapshot_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = IPriceSnapshot.objects.filter(pk=snapshot_id).first()
        if snapshot is None:
            raise Http404("Snapshot не найден")
        data = serializer.validated_data
        try:
            if data["preview"]:
                affected = preview_iprice_parameter_changes(
                    snapshot=snapshot,
                    mode=data["mode"],
                    filters=data["filters"],
                    search=data["search"],
                )
                return Response({"status": "preview", "affected": affected})

            if IPriceSnapshot.objects.filter(
                status=IPriceSnapshot.STATUS_BUILDING,
            ).exists():
                return Response(
                    {
                        "status": "calculation_running",
                        "message": "Дождитесь завершения текущего расчёта iPrice",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            lock_key = IPRICE_PARAMETER_CHANGE_LOCK_KEY
            if not cache.add(lock_key, True, timeout=60 * 30):
                return Response(
                    {
                        "status": "already_running",
                        "message": "Изменение параметров уже выполняется",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                affected = apply_iprice_parameter_changes(
                    snapshot=snapshot,
                    mode=data["mode"],
                    filters=data["filters"],
                    search=data["search"],
                    coefficient_values=data["coefficients"],
                    discount_values=data["discounts"],
                    user=request.user,
                )
                publish_iprice_update(
                    "parameters_changed",
                    snapshot_id=snapshot.id,
                    affected=affected,
                )
            finally:
                cache.delete(lock_key)
        except IPriceParameterChangeError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "status": "ok",
            "message": "Параметры применены",
            "affected": affected,
        })


class IPriceSnapshotRunView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    serializer_class = (
        IPriceSnapshotRunSerializer
    )

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        calculation_date = (
            serializer.validated_data.get(
                "calculation_date"
            )
            or timezone.localdate()
        )

        if (
            calculation_date
            > timezone.localdate()
        ):
            return Response(
                {
                    "status": "error",
                    "message": (
                        "Дата расчета не может "
                        "быть в будущем"
                    ),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        operation_lock_acquired = cache.add(
            IPRICE_PARAMETER_CHANGE_LOCK_KEY,
            True,
            timeout=60 * 30,
        )
        if not operation_lock_acquired:
            return Response(
                {
                    "status": "parameters_changing",
                    "message": (
                        "Дождитесь завершения текущего изменения данных iPrice"
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        lock_acquired = cache.add(
            IPRICE_SNAPSHOT_START_LOCK_KEY,
            True,
            timeout=(
                IPRICE_SNAPSHOT_START_LOCK_TIMEOUT
            ),
        )

        if not lock_acquired:
            cache.delete(IPRICE_PARAMETER_CHANGE_LOCK_KEY)
            return Response(
                {
                    "status": (
                        "launch_in_progress"
                    ),
                    "message": (
                        "Запрос на запуск snapshot "
                        "уже обрабатывается"
                    ),
                },
                status=(
                    status.HTTP_409_CONFLICT
                ),
            )

        try:
            return self._start_snapshot(
                request=request,
                calculation_date=(
                    calculation_date
                ),
            )

        finally:
            cache.delete(
                IPRICE_SNAPSHOT_START_LOCK_KEY
            )
            cache.delete(
                IPRICE_PARAMETER_CHANGE_LOCK_KEY
            )

    def _start_snapshot(
        self,
        *,
        request,
        calculation_date,
    ):
        building_snapshot = (
            IPriceSnapshot.objects
            .filter(
                status=(
                    IPriceSnapshot
                    .STATUS_BUILDING
                ),
            )
            .order_by(
                "-created_at",
                "-id",
            )
            .first()
        )

        if building_snapshot is not None:
            serializer = (
                IPriceSnapshotSerializer(
                    building_snapshot,
                )
            )

            return Response(
                {
                    "status": "already_running",
                    "message": (
                        "Расчет iPrice уже "
                        "выполняется"
                    ),
                    "snapshot": serializer.data,
                },
                status=(
                    status.HTTP_409_CONFLICT
                ),
            )

        snapshot = create_iprice_snapshot(
            calculation_date=(
                calculation_date
            ),
            created_by=request.user,
            parameters={
                "source": "api",
                "current_step": "queued",
            },
        )

        try:
            process_id = (
                launch_iprice_snapshot(
                    snapshot_id=snapshot.id,
                )
            )

        except Exception as exc:
            snapshot.status = (
                IPriceSnapshot.STATUS_FAILED
            )

            snapshot.finished_at = (
                timezone.now()
            )

            snapshot.error = str(exc)

            snapshot.parameters = {
                **snapshot.parameters,
                "current_step": (
                    "launch_failed"
                ),
            }

            snapshot.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "error",
                    "parameters",
                ]
            )

            sync_snapshot_and_publish(
                snapshot.id,
                "snapshot_failed",
                metadata_only=True,
            )

            return Response(
                {
                    "status": "error",
                    "message": (
                        "Не удалось запустить "
                        "расчет iPrice"
                    ),
                    "snapshot_id": (
                        snapshot.id
                    ),
                    "error": str(exc),
                },
                status=(
                    status
                    .HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        response_serializer = (
            IPriceSnapshotSerializer(
                snapshot,
            )
        )

        sync_snapshot_and_publish(
            snapshot.id,
            "snapshot_started",
            metadata_only=True,
            process_id=process_id,
        )

        return Response(
            {
                "status": "started",
                "message": (
                    "Расчет iPrice запущен"
                ),
                "process_id": process_id,
                "snapshot": (
                    response_serializer.data
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class IPriceSnapshotListView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request):
        calculation_date_param = (
            request.query_params.get(
                "calculation_date"
            )
        )

        if calculation_date_param:
            try:
                datetime.strptime(
                    calculation_date_param,
                    "%Y-%m-%d",
                )
            except ValueError:
                return Response(
                    {
                        "status": "error",
                        "message": (
                            "calculation_date must "
                            "be YYYY-MM-DD"
                        ),
                    },
                    status=(
                        status
                        .HTTP_400_BAD_REQUEST
                    ),
                )

        cache_payload = request.query_params.dict()
        cached = get_iprice_cache(
            "postgres:snapshots",
            cache_payload,
        )
        if cached is not None:
            return Response(cached)

        queryset = (
            IPriceSnapshot.objects
            .select_related(
                "created_by",
                "activated_by",
            )
            .annotate(
                products_count_value=Count(
                    "products",
                    distinct=True,
                ),
                regions_count_value=Count(
                    "products__regions",
                    distinct=True,
                ),
                errors_count_value=Count(
                    "products__regions",
                    filter=Q(
                        products__regions__calculation_status=
                            IPriceSnapshotRegion.STATUS_ERROR,
                    ),
                    distinct=True,
                ),
            )
            .order_by(
                "-created_at",
                "-id",
            )
        )

        status_filter = (
            request.query_params.get(
                "status"
            )
        )

        if status_filter:
            queryset = queryset.filter(
                status=status_filter,
            )

        calculation_date = (
            request.query_params.get(
                "calculation_date"
            )
        )

        if calculation_date:
            try:
                parsed_date = (
                    datetime.strptime(
                        calculation_date,
                        "%Y-%m-%d",
                    )
                    .date()
                )

            except ValueError:
                return Response(
                    {
                        "status": "error",
                        "message": (
                            "calculation_date must "
                            "be YYYY-MM-DD"
                        ),
                    },
                    status=(
                        status
                        .HTTP_400_BAD_REQUEST
                    ),
                )

            queryset = queryset.filter(
                calculation_date=parsed_date,
            )

        current_only = (
            request.query_params.get(
                "current_only"
            )
        )

        if (
            current_only
            and current_only.lower()
            in {"1", "true", "yes"}
        ):
            queryset = queryset.filter(
                is_current=True,
            )

        latest_snapshot_id = (
            IPriceSnapshot.objects
            .filter(
                status=(
                    IPriceSnapshot
                    .STATUS_SUCCESS
                ),
            )
            .order_by(
                "-created_at",
                "-id",
            )
            .values_list(
                "id",
                flat=True,
            )
            .first()
        )

        serializer = (
            IPriceSnapshotSerializer(
                queryset,
                many=True,
                context={
                    "latest_snapshot_id": (
                        latest_snapshot_id
                    ),
                },
            )
        )

        result = {
            "count": queryset.count(),
            "results": serializer.data,
        }
        set_iprice_cache(
            "postgres:snapshots",
            cache_payload,
            result,
        )
        return Response(result)


class IPriceSnapshotDetailView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request, snapshot_id):
        cache_payload = {"snapshot_id": snapshot_id}
        cached = get_iprice_cache(
            "postgres:snapshot",
            cache_payload,
        )
        if cached is not None:
            return Response(cached)

        snapshot = (
            IPriceSnapshot.objects
            .select_related(
                "created_by",
                "activated_by",
            )
            .annotate(
                products_count_value=Count(
                    "products",
                    distinct=True,
                ),
                regions_count_value=Count(
                    "products__regions",
                    distinct=True,
                ),

                errors_count_value=Count(
                    "products__regions",
                    filter=Q(
                        products__regions__calculation_status=
                            IPriceSnapshotRegion.STATUS_ERROR,
                    ),
                    distinct=True,
                ),
            )
            .filter(
                pk=snapshot_id,
            )
            .first()
        )

        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        latest_snapshot_id = (
            IPriceSnapshot.objects
            .filter(
                status=(
                    IPriceSnapshot
                    .STATUS_SUCCESS
                ),
            )
            .order_by(
                "-created_at",
                "-id",
            )
            .values_list(
                "id",
                flat=True,
            )
            .first()
        )

        serializer = (
            IPriceSnapshotSerializer(
                snapshot,
                context={
                    "latest_snapshot_id": (
                        latest_snapshot_id
                    ),
                },
            )
        )

        result = serializer.data
        set_iprice_cache(
            "postgres:snapshot",
            cache_payload,
            result,
        )
        return Response(result)


def serialize_iprice_snapshot_with_latest(snapshot):
    latest_snapshot_id = (
        IPriceSnapshot.objects
        .filter(status=IPriceSnapshot.STATUS_SUCCESS)
        .order_by("-created_at", "-id")
        .values_list("id", flat=True)
        .first()
    )
    return IPriceSnapshotSerializer(
        snapshot,
        context={"latest_snapshot_id": latest_snapshot_id},
    ).data


class IPriceSnapshotActivateView(APIView):
    permission_classes = [CanEditIPriceDashboard]

    def post(self, request, snapshot_id):
        snapshot = (
            IPriceSnapshot.objects
            .filter(
                pk=snapshot_id,
            )
            .first()
        )

        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        try:
            snapshot = activate_iprice_snapshot(
                snapshot=snapshot,
                activated_by=request.user,
            )

        except IPriceSnapshotBuildError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        serialized_snapshot = serialize_iprice_snapshot_with_latest(snapshot)

        sync_activation_and_publish(
            snapshot.id,
        )

        return Response(
            {
                "status": "activated",
                "message": (
                    "Расчёт назначен "
                    "активным окончательным расчетом"
                ),
                "snapshot": serialized_snapshot,
            }
        )

    def delete(self, request, snapshot_id):
        snapshot = IPriceSnapshot.objects.filter(pk=snapshot_id).first()
        if snapshot is None:
            return Response(
                {"status": "not_found", "message": "Snapshot не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            snapshot = deactivate_iprice_snapshot(snapshot=snapshot)
        except IPriceSnapshotBuildError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serialized_snapshot = serialize_iprice_snapshot_with_latest(snapshot)
        sync_activation_and_publish(
            snapshot.id,
            change_type="snapshot_deactivated",
        )
        return Response({
            "status": "deactivated",
            "message": "Версия деактивирована",
            "snapshot": serialized_snapshot,
        })


def build_iprice_paginated_response(
    *,
    queryset,
    serializer_class,
    page_number,
    page_size,
    mode,
    snapshot_id,
):
    """
    Формирует единый ответ пагинации
    для products и regions.
    """

    paginator = Paginator(
        queryset,
        page_size,
    )

    page_obj = paginator.get_page(
        page_number
    )

    serializer = serializer_class(
        page_obj.object_list,
        many=True,
    )

    return Response(
        {
            "count": paginator.count,
            "total_pages": (
                paginator.num_pages
            ),
            "page": page_obj.number,
            "page_size": page_size,
            "has_next": (
                page_obj.has_next()
            ),
            "has_previous": (
                page_obj.has_previous()
            ),
            "results": serializer.data,
            "mode": mode,
            "snapshot_id": snapshot_id,
        },
        status=status.HTTP_200_OK,
    )


class IPriceSnapshotCompareView(
    APIView
):
    permission_classes = [
        CanViewIPriceDashboard,
    ]

    serializer_class = (
        IPriceSnapshotCompareRequestSerializer
    )

    def get_serializer(
        self,
        *args,
        **kwargs,
    ):
        return self.serializer_class(
            *args,
            **kwargs,
        )

    def post(
        self,
        request,
    ):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        validated_data = (
            serializer.validated_data
        )

        cache_payload = {
            "base_snapshot_id": (
                validated_data[
                    "base_snapshot_id"
                ]
            ),
            "comparison_snapshot_id": (
                validated_data[
                    "comparison_snapshot_id"
                ]
            ),
            "mode": validated_data[
                "mode"
            ],
            "change_type": (
                validated_data[
                    "change_type"
                ]
            ),
            "page": validated_data[
                "page"
            ],
            "page_size": validated_data[
                "page_size"
            ],
            "search": validated_data[
                "search"
            ],
            "filters": validated_data[
                "filters"
            ],
        }

        cached_result = get_iprice_cache(
            "postgres:compare:rows:v2",
            cache_payload,
        )

        if cached_result is not None:
            return Response(
                cached_result,
                status=status.HTTP_200_OK,
            )

        try:
            result = compare_iprice_snapshots(
                base_snapshot_id=(
                    validated_data[
                        "base_snapshot_id"
                    ]
                ),
                comparison_snapshot_id=(
                    validated_data[
                        "comparison_snapshot_id"
                    ]
                ),
                mode=validated_data[
                    "mode"
                ],
                change_type=(
                    validated_data[
                        "change_type"
                    ]
                ),
                page=validated_data[
                    "page"
                ],
                page_size=validated_data[
                    "page_size"
                ],
                search=validated_data[
                    "search"
                ],
                filters=validated_data[
                    "filters"
                ],
            )

        except IPriceSnapshotCompareError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        set_iprice_cache(
            "postgres:compare:rows:v2",
            cache_payload,
            result,
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotCompareFiltersView(
    APIView
):
    permission_classes = [
        CanViewIPriceDashboard,
    ]

    serializer_class = (
        IPriceSnapshotCompareFiltersRequestSerializer
    )

    def get_serializer(
        self,
        *args,
        **kwargs,
    ):
        return self.serializer_class(
            *args,
            **kwargs,
        )

    def post(
        self,
        request,
    ):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        validated_data = (
            serializer.validated_data
        )

        cache_payload = {
            "base_snapshot_id": (
                validated_data[
                    "base_snapshot_id"
                ]
            ),
            "comparison_snapshot_id": (
                validated_data[
                    "comparison_snapshot_id"
                ]
            ),
            "mode": validated_data[
                "mode"
            ],
            "filters": validated_data[
                "filters"
            ],
        }

        cached_result = get_iprice_cache(
            "postgres:compare:filters",
            cache_payload,
        )

        if cached_result is not None:
            return Response(
                cached_result,
                status=status.HTTP_200_OK,
            )

        try:
            result = (
                build_iprice_snapshot_compare_filters(
                    base_snapshot_id=(
                        validated_data[
                            "base_snapshot_id"
                        ]
                    ),
                    comparison_snapshot_id=(
                        validated_data[
                            "comparison_snapshot_id"
                        ]
                    ),
                    mode=validated_data[
                        "mode"
                    ],
                    filters=validated_data[
                        "filters"
                    ],
                )
            )

        except IPriceSnapshotCompareError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        set_iprice_cache(
            "postgres:compare:filters",
            cache_payload,
            result,
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceHealthView(
    APIView
):
    permission_classes = [
        CanViewIPriceDashboard,
    ]

    serializer_class = (
        IPriceHealthRequestSerializer
    )

    def get_serializer(
        self,
        *args,
        **kwargs,
    ):
        return self.serializer_class(
            *args,
            **kwargs,
        )

    def post(
        self,
        request,
    ):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        validated_data = (
            serializer.validated_data
        )

        try:
            result = (
                build_iprice_health_response(
                    page=validated_data[
                        "page"
                    ],
                    page_size=validated_data[
                        "page_size"
                    ],
                    level=validated_data[
                        "level"
                    ],
                    sections=validated_data[
                        "sections"
                    ],
                    issue_groups=(
                        validated_data[
                            "issue_groups"
                        ]
                    ),
                    error_codes=(
                        validated_data[
                            "error_codes"
                        ]
                    ),
                    search=validated_data[
                        "search"
                    ],
                    force_refresh=(
                        validated_data[
                            "force_refresh"
                        ]
                    ),
                )
            )

        except Exception as exc:
            return Response(
                {
                    "detail": (
                        "Не удалось выполнить "
                        "контроль подготовки iPrice."
                    ),
                    "error": str(exc),
                },
                status=(
                    status
                    .HTTP_500_INTERNAL_SERVER_ERROR
                ),
            )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotRowsView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    serializer_class = (
        IPriceSnapshotRowsRequestSerializer
    )

    PRODUCT_ORDERING_FIELDS = {
        "code_1c",
        "-code_1c",
        "nom",
        "-nom",

        "competitor_count",
        "-competitor_count",

        "competitor_rrp_min",
        "-competitor_rrp_min",
        "competitor_rrp_max",
        "-competitor_rrp_max",
        "competitor_rrp_median",
        "-competitor_rrp_median",

        "current_retail_min",
        "-current_retail_min",
        "current_retail_max",
        "-current_retail_max",
        "current_retail_median",
        "-current_retail_median",

        "effective_approved_rrp_median",
        "-effective_approved_rrp_median",

        "pricing_method",
        "-pricing_method",
        "calculation_status",
        "-calculation_status",

        "current_vs_approved_amount",
        "-current_vs_approved_amount",
        "approved_vs_competitor_percent",
        "-approved_vs_competitor_percent",

        "current_vs_competitor_amount",
        "-current_vs_competitor_amount",
        "current_vs_competitor_percent",
        "-current_vs_competitor_percent",
    }

    REGION_ORDERING_FIELDS = {
        "snapshot_product__code_1c",
        "-snapshot_product__code_1c",
        "snapshot_product__nom",
        "-snapshot_product__nom",
        "snapshot_product__pricing_method",
        "-snapshot_product__pricing_method",

        "sale_region",
        "-sale_region",
        "departure",
        "-departure",

        "current_retail",
        "-current_retail",

        "product_cost",
        "-product_cost",
        "logistics_unit",
        "-logistics_unit",
        "transport_cost",
        "-transport_cost",
        "cost_with_logistics",
        "-cost_with_logistics",

        "calculated_rrp",
        "-calculated_rrp",
        "default_approved_rrp",
        "-default_approved_rrp",
        "effective_approved_rrp",
        "-effective_approved_rrp",

        "regional_competitor_count",
        "-regional_competitor_count",
        "regional_competitor_rrp_median",
        "-regional_competitor_rrp_median",

        "margin_current",
        "-margin_current",
        "margin_calculated",
        "-margin_calculated",
        "effective_margin_calculated",
        "-effective_margin_calculated",

        "current_vs_calculated_percent",
        "-current_vs_calculated_percent",
        "current_vs_effective_approved_amount",
        "-current_vs_effective_approved_amount",
        "effective_vs_competitor_percent",
        "-effective_vs_competitor_percent",
        "current_vs_competitor_percent",
        "-current_vs_competitor_percent",
        "calculation_status",
        "-calculation_status",
    }

    def post(
        self,
        request,
        snapshot_id,
    ):
        snapshot = (
            IPriceSnapshot.objects
            .filter(
                pk=snapshot_id,
            )
            .first()
        )

        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        data = serializer.validated_data
        mode = data["mode"]
        cache_payload = {
            "snapshot_id": snapshot.id,
            **data,
        }
        cached = get_iprice_cache(
            "postgres:rows:v2",
            cache_payload,
        )
        if cached is not None:
            return Response(
                cached,
                status=status.HTTP_200_OK,
            )

        if mode == "products":
            response = self._get_products(
                snapshot=snapshot,
                data=data,
            )
        else:
            response = self._get_regions(
                snapshot=snapshot,
                data=data,
            )

        set_iprice_cache(
            "postgres:rows:v2",
            cache_payload,
            response.data,
        )
        return response

    @classmethod
    def _get_products(
        cls,
        *,
        snapshot,
        data,
    ):
        queryset = (
            IPriceSnapshotProduct.objects
            .filter(
                snapshot=snapshot,
            )
            .annotate(
                approved_vs_competitor_percent=(
                    ExpressionWrapper(
                        (
                            F("effective_approved_rrp_median")
                            - F("competitor_rrp_median")
                        )
                        / NullIf(
                            F("competitor_rrp_median"),
                            Value(0),
                        ),
                        output_field=DecimalField(
                            max_digits=24,
                            decimal_places=8,
                        ),
                    )
                ),
            )
        )

        queryset = (
            filter_iprice_products_queryset(
                queryset=queryset,
                filters=(
                    data.get("filters")
                    or {}
                ),
            )
        )

        queryset = (
            apply_iprice_products_search(
                queryset=queryset,
                search=(
                    data.get("search")
                    or ""
                ),
            )
        )

        ordering = (
            data.get("ordering")
            or (
                "-current_vs_"
                "competitor_percent"
            )
        )

        if (
            ordering
            not in cls.PRODUCT_ORDERING_FIELDS
        ):
            ordering = (
                "-current_vs_"
                "competitor_percent"
            )

        queryset = queryset.order_by(
            ordering,
            "code_1c",
            "id",
        )

        return build_iprice_paginated_response(
            queryset=queryset,
            serializer_class=(
                IPriceSnapshotProductSerializer
            ),
            page_number=data["page"],
            page_size=data["page_size"],
            mode="products",
            snapshot_id=snapshot.id,
        )

    @classmethod
    def _get_regions(
        cls,
        *,
        snapshot,
        data,
    ):
        current_approvals_queryset = (
            IPriceSnapshotApproval.objects
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
        )

        all_approvals_queryset = (
            IPriceSnapshotApproval.objects
            .select_related(
                "approved_by",
            )
            .order_by(
                "-revision",
                "-id",
            )
        )

        queryset = (
            IPriceSnapshotRegion.objects
            .filter(
                snapshot_product__snapshot=(
                    snapshot
                ),
            )
            .select_related(
                "snapshot_product",
            )
            .prefetch_related(
                Prefetch(
                    "approvals",
                    queryset=(
                        current_approvals_queryset
                    ),
                    to_attr=(
                        "prefetched_current_approvals"
                    ),
                ),
                Prefetch(
                    "approvals",
                    queryset=all_approvals_queryset,
                    to_attr=(
                        "prefetched_all_approvals"
                    ),
                ),
            )
        )

        decimal_output = DecimalField(
            max_digits=24,
            decimal_places=8,
        )
        current_approval_rrp = (
            IPriceSnapshotApproval.objects
            .filter(
                snapshot_region_id=OuterRef("pk"),
                is_current=True,
            )
            .order_by("-revision", "-id")
            .values("approved_rrp")[:1]
        )
        queryset = queryset.annotate(
            effective_approved_rrp=Coalesce(
                Subquery(
                    current_approval_rrp,
                    output_field=decimal_output,
                ),
                F("default_approved_rrp"),
                output_field=decimal_output,
            ),
        )
        queryset = queryset.annotate(
            current_vs_effective_approved_amount=(
                ExpressionWrapper(
                    F("current_retail")
                    - F("effective_approved_rrp"),
                    output_field=decimal_output,
                )
            ),
            effective_margin_calculated=(
                ExpressionWrapper(
                    (
                        F("effective_approved_rrp")
                        - F("cost_with_logistics")
                    )
                    / NullIf(
                        F("effective_approved_rrp"),
                        Value(
                            0,
                            output_field=decimal_output,
                        ),
                    ),
                    output_field=decimal_output,
                )
            ),
            effective_vs_competitor_percent=(
                ExpressionWrapper(
                    (
                        F("effective_approved_rrp")
                        - F("regional_competitor_rrp_median")
                    )
                    / NullIf(
                        F("regional_competitor_rrp_median"),
                        Value(0, output_field=decimal_output),
                    ),
                    output_field=decimal_output,
                )
            ),
            current_vs_competitor_percent=(
                ExpressionWrapper(
                    (
                        F("current_retail")
                        - F("regional_competitor_rrp_median")
                    )
                    / NullIf(
                        F("regional_competitor_rrp_median"),
                        Value(0, output_field=decimal_output),
                    ),
                    output_field=decimal_output,
                )
            ),
        )

        queryset = (
            filter_iprice_regions_queryset(
                queryset=queryset,
                filters=(
                    data.get("filters")
                    or {}
                ),
            )
        )

        queryset = (
            apply_iprice_regions_search(
                queryset=queryset,
                search=(
                    data.get("search")
                    or ""
                ),
            )
        )

        ordering = (
            data.get("ordering")
            or (
                "-current_vs_"
                "effective_approved_amount"
            )
        )

        if (
            ordering
            not in cls.REGION_ORDERING_FIELDS
        ):
            ordering = (
                "-current_vs_"
                "effective_approved_amount"
            )

        queryset = queryset.order_by(
            ordering,
            "snapshot_product__code_1c",
            "sale_region",
            "departure",
            "id",
        )

        return build_iprice_paginated_response(
            queryset=queryset,
            serializer_class=(
                IPriceSnapshotRegionSerializer
            ),
            page_number=data["page"],
            page_size=data["page_size"],
            mode="regions",
            snapshot_id=snapshot.id,
        )


class IPricePriceAnalyticsView(APIView):
    permission_classes = [CanViewIPriceDashboard]
    serializer_class = IPricePriceAnalyticsRequestSerializer

    def post(self, request, snapshot_id):
        snapshot = (
            IPriceSnapshot.objects
            .filter(pk=snapshot_id)
            .first()
        )
        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": "Snapshot не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        if snapshot.status != IPriceSnapshot.STATUS_SUCCESS:
            return Response(
                {
                    "status": "not_ready",
                    "message": (
                        "Аналитика доступна только для "
                        "успешно рассчитанного snapshot"
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cache_payload = {
            "snapshot_id": snapshot.id,
            **data,
        }
        cached = get_iprice_cache(
            "postgres:price-analytics:v3",
            cache_payload,
        )
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        try:
            if data["view"] == "regions":
                result = build_iprice_regional_price_analytics(
                    snapshot=snapshot,
                    filters=data.get("filters") or {},
                    search=data.get("search") or "",
                    drill_path=data.get("drill_path") or {},
                    page=data["page"],
                    page_size=data["page_size"],
                    ordering=data.get("ordering") or "",
                    selected_zones=data.get("price_zones") or [],
                )
            else:
                result = build_iprice_price_analytics(
                    snapshot=snapshot,
                    filters=data.get("filters") or {},
                    search=data.get("search") or "",
                    drill_level=data["drill_level"],
                    drill_path=data.get("drill_path") or {},
                    page=data["page"],
                    page_size=data["page_size"],
                    ordering=data.get("ordering") or "",
                    selected_zones=data.get("price_zones") or [],
                )
        except IPricePriceAnalyticsError as exc:
            return Response(
                {
                    "status": "invalid_drill_path",
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        set_iprice_cache(
            "postgres:price-analytics:v3",
            cache_payload,
            result,
        )
        return Response(result, status=status.HTTP_200_OK)


class IPriceAnalyticsSelectionView(APIView):
    permission_classes = [CanViewIPriceDashboard]
    serializer_class = IPriceAnalyticsSelectionSerializer

    def post(self, request, snapshot_id):
        snapshot = IPriceSnapshot.objects.filter(
            pk=snapshot_id,
            status=IPriceSnapshot.STATUS_SUCCESS,
        ).first()
        if snapshot is None:
            return Response(
                {"message": "Успешная версия расчёта не найдена."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        product_keys = resolve_iprice_analytics_product_keys(
            snapshot=snapshot,
            filters=data.get("filters") or {},
            search=data.get("search") or "",
            drill_level=data.get("drill_level") or "root",
            drill_path=data.get("drill_path") or {},
            selected_zones=data.get("price_zones") or [],
        )
        if not product_keys:
            return Response(
                {"message": "В выбранной области аналитики товары не найдены."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        filters = data.get("filters") or {}
        context = {
            "filters": filters,
            "search": data.get("search") or "",
            "drill_path": data.get("drill_path") or {},
            "price_zones": data.get("price_zones") or [],
            "mode": (
                "regions"
                if filters.get("sale_region") or filters.get("departure")
                else "products"
            ),
        }
        token, payload = create_analytics_selection(
            user=request.user,
            snapshot=snapshot,
            product_keys=product_keys,
            context=context,
        )
        return Response({
            "token": token,
            "snapshot_id": snapshot.id,
            "product_count": len(product_keys),
            "context": payload["context"],
        }, status=status.HTTP_201_CREATED)


class IPriceAnalyticsSelectionDetailView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request, token):
        payload = get_analytics_selection(user=request.user, token=token)
        if payload is None:
            return Response(
                {"message": "Выборка аналитики истекла или недоступна."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "snapshot_id": payload["snapshot_id"],
            "product_keys": payload["product_keys"],
            "product_count": len(payload["product_keys"]),
            "context": payload["context"],
        })


class IPricePriceZoneConfigView(APIView):
    def get_permissions(self):
        permission_classes = (
            [CanEditIPriceDashboard]
            if self.request.method == "POST"
            else [CanViewIPriceDashboard]
        )
        return [permission() for permission in permission_classes]

    def get(self, request):
        result = serialize_price_zone_config(
            get_active_price_zone_config()
        )
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = IPricePriceZoneConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        divisor = Decimal("100")

        config, changed = activate_price_zone_config(
            below_market_threshold=(
                data["below_market_percent"] / divisor
            ),
            above_market_threshold=(
                data["above_market_percent"] / divisor
            ),
            critical_threshold=(
                data["critical_percent"] / divisor
            ),
            user=request.user,
        )

        if changed:
            publish_iprice_update(
                "price_zones_updated",
                price_zone_config_id=config["id"],
            )

        return Response(
            {
                **serialize_price_zone_config(config),
                "changed": changed,
            },
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotFiltersView(APIView):
    permission_classes = [CanViewIPriceDashboard]
    serializer_class = (
        IPriceSnapshotFiltersSerializer
    )

    def post(
        self,
        request,
        snapshot_id,
    ):
        snapshot = (
            IPriceSnapshot.objects
            .filter(
                pk=snapshot_id,
            )
            .first()
        )

        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        mode = serializer.validated_data[
            "mode"
        ]

        filters = (
            serializer.validated_data.get(
                "filters"
            )
            or {}
        )
        cache_payload = {
            "snapshot_id": snapshot.id,
            "mode": mode,
            "filters": filters,
        }
        cached = get_iprice_cache(
            "postgres:filters",
            cache_payload,
        )
        if cached is not None:
            return Response(
                cached,
                status=status.HTTP_200_OK,
            )

        result = (
            build_iprice_snapshot_filters(
                snapshot=snapshot,
                mode=mode,
                filters=filters,
            )
        )
        set_iprice_cache(
            "postgres:filters",
            cache_payload,
            result,
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotProductDetailView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(
        self,
        request,
        snapshot_id,
        product_id,
    ):
        cache_payload = {
            "snapshot_id": snapshot_id,
            "product_id": product_id,
            "sale_regions": request.query_params.getlist(
                "sale_region"
            ),
            "departures": request.query_params.getlist(
                "departure"
            ),
        }
        cached = get_iprice_cache(
            "postgres:product:v6",
            cache_payload,
        )
        if cached is not None:
            return Response(
                cached,
                status=status.HTTP_200_OK,
            )

        product = (
            IPriceSnapshotProduct.objects
            .filter(
                pk=product_id,
                snapshot_id=snapshot_id,
            )
            .select_related(
                "snapshot",
            )
            .prefetch_related(
                "competitors",
            )
            .first()
        )

        if product is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Товар snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        sale_regions = (
            request.query_params.getlist(
                "sale_region"
            )
        )

        departures = (
            request.query_params.getlist(
                "departure"
            )
        )

        current_approvals_queryset = (
            IPriceSnapshotApproval.objects
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
        )

        regions_queryset = (
            IPriceSnapshotRegion.objects
            .filter(
                snapshot_product=product,
            )
            .select_related(
                "snapshot_product",
            )
            .prefetch_related(
                Prefetch(
                    "approvals",
                    queryset=(
                        current_approvals_queryset
                    ),
                    to_attr=(
                        "prefetched_current_approvals"
                    ),
                )
            )
        )

        if sale_regions:
            region_query = Q()

            for sale_region in sale_regions:
                sale_region = (
                    str(sale_region)
                    .strip()
                )

                if not sale_region:
                    continue

                region_query |= Q(
                    sale_region__iexact=(
                        sale_region
                    )
                )

            if region_query:
                regions_queryset = (
                    regions_queryset.filter(
                        region_query
                    )
                )

        if departures:
            departure_query = Q()

            for departure in departures:
                departure = (
                    str(departure)
                    .strip()
                )

                if not departure:
                    continue

                departure_query |= Q(
                    departure__iexact=(
                        departure
                    )
                )

            if departure_query:
                regions_queryset = (
                    regions_queryset.filter(
                        departure_query
                    )
                )

        regions_queryset = (
            regions_queryset.order_by(
                "sale_region",
                "departure",
                "id",
            )
        )

        competitors = list(
            product.competitors
            .all()
            .order_by(
                "source",
                "competitor_product_key",
                "id",
            )
        )

        competitor_product_keys = {
            row.competitor_product_key
            for row in competitors
        }
        competitor_product_metadata = {
            product_key: {}
            for product_key in competitor_product_keys
        }
        for row in ParserProductClassification.objects.filter(
            product_key__in=competitor_product_keys,
            status=ParserProductClassification.STATUS_ACTIVE,
        ).values(
            "product_key",
            "material",
            "color",
            "modification",
            "article_number_analogs",
            "image",
        ):
            competitor_product_metadata[row["product_key"]].update(row)
        for product_key, additional_property in (
            ParserProductUrl.objects.filter(
                id__in=competitor_product_keys,
            ).values_list("id", "additional_property")
        ):
            competitor_product_metadata[product_key][
                "additional_property"
            ] = additional_property

        product_serializer = (
            IPriceSnapshotProductSerializer(
                product,
            )
        )

        competitor_serializer = (
            IPriceSnapshotCompetitorSerializer(
                competitors,
                many=True,
                context={
                    "competitor_product_metadata": competitor_product_metadata,
                },
            )
        )
        competitor_cards = group_snapshot_competitor_cards(
            list(competitor_serializer.data),
        )
        override_modes = dict(
            IPriceCompetitorSelectionOverride.objects.filter(
                product_key_base=product.base_product_key,
            ).values_list("product_key_competitor", "selection_mode")
        )
        for card in competitor_cards:
            keys = card.get("competitor_product_keys") or []
            modes = {override_modes.get(int(key), "auto") for key in keys}
            card["selection_mode"] = (
                "exclude" if modes == {"exclude"}
                else "include" if "include" in modes
                else "auto"
            )

        region_serializer = (
            IPriceSnapshotRegionSerializer(
                regions_queryset,
                many=True,
            )
        )

        product_payload = dict(product_serializer.data)
        product_payload["site_name"] = (
            BaseProductPrice.objects.filter(
                product_key=product.base_product_key,
            ).exclude(name__isnull=True).exclude(name="").order_by(
                "-date_add", "-id",
            ).values_list("name", flat=True).first()
        )
        product_payload["article_number_analogs"] = (
            ParserProductClassification.objects.filter(
                product_key=product.base_product_key,
                status=ParserProductClassification.STATUS_ACTIVE,
            ).values_list("article_number_analogs", flat=True).first()
        )

        result = {
            "snapshot": {
                    "id": product.snapshot.id,
                    "calculation_date": (
                        product
                        .snapshot
                        .calculation_date
                        .isoformat()
                    ),
                    "display_version": (
                        product
                        .snapshot
                        .display_version
                    ),
                    "is_current": (
                        product.snapshot.is_current
                    ),
                    "is_active": (
                        product.snapshot.is_active
                    ),
                    "was_active": product.snapshot.was_active,
                    "competitor_selection_editable": is_selection_editable(
                        product.snapshot,
                    ),
            },
            "product": product_payload,
            "competitors": competitor_cards,
            "regions": region_serializer.data,
            "counts": {
                "competitors": len(competitor_cards),
                "regions": regions_queryset.count(),
            },
        }
        set_iprice_cache(
            "postgres:product:v6",
            cache_payload,
            result,
        )
        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotMarketAssortmentView(
    APIView
):
    """
    Возвращает справочный ассортимент конкурентов
    для одного нашего товара snapshot.

    В выборку входят все активные конкурентные
    классификации с совпадающими:

        category
        subcategory
        subcategory_type
        item_type

    material, color и modification не ограничивают
    выборку, а используются для оценки сходства
    и сортировки результата.

    Справочный ассортимент не влияет на:

        медиану конкурентов;
        расчётную РРЦ;
        данные существующего snapshot.
    """

    permission_classes = [
        CanViewIPriceDashboard,
    ]

    def get(
        self,
        request,
        snapshot_id,
        product_id,
    ):
        snapshot_product = (
            IPriceSnapshotProduct.objects
            .filter(
                pk=product_id,
                snapshot_id=snapshot_id,
            )
            .select_related(
                "snapshot",
            )
            .prefetch_related(
                "competitors",
            )
            .first()
        )

        if snapshot_product is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Товар snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        try:
            result = (
                build_iprice_market_assortment(
                    snapshot_product=(
                        snapshot_product
                    ),
                )
            )
            override_modes = dict(
                IPriceCompetitorSelectionOverride.objects.filter(
                    product_key_base=snapshot_product.base_product_key,
                ).values_list("product_key_competitor", "selection_mode")
            )
            for card in result.get("results", []):
                keys = card.get("competitor_product_keys") or []
                modes = {override_modes.get(int(key), "auto") for key in keys}
                card["selection_mode"] = (
                    "exclude" if modes == {"exclude"}
                    else "include" if "include" in modes
                    else "auto"
                )
            result["competitor_selection_editable"] = is_selection_editable(
                snapshot_product.snapshot,
            )

        except IPriceMarketAssortmentError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        return Response(
            {
                "status": "ok",
                **result,
            },
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotCompetitorSelectionView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    serializer_class = IPriceCompetitorSelectionSerializer

    def post(self, request, snapshot_id, product_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        if IPriceSnapshot.objects.filter(
            status=IPriceSnapshot.STATUS_BUILDING,
        ).exists():
            return Response(
                {
                    "status": "calculation_running",
                    "message": "Дождитесь завершения текущего расчёта iPrice",
                },
                status=status.HTTP_409_CONFLICT,
            )
        lock_key = IPRICE_PARAMETER_CHANGE_LOCK_KEY
        if not cache.add(lock_key, True, timeout=60 * 30):
            return Response(
                {
                    "status": "already_running",
                    "message": "Дождитесь завершения изменения расчёта iPrice",
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            result = apply_competitor_selection(
                snapshot_id=snapshot_id,
                product_id=product_id,
                competitor_product_keys=serializer.validated_data[
                    "competitor_product_keys"
                ],
                selection_mode=serializer.validated_data["selection_mode"],
                reason=serializer.validated_data["reason"],
                user=request.user,
            )
        except (IPriceCompetitorSelectionError, IPriceSnapshot.DoesNotExist,
                IPriceSnapshotProduct.DoesNotExist) as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        finally:
            cache.delete(lock_key)
        publish_iprice_update(
            "competitor_selection_changed",
            snapshot_id=snapshot_id,
            product_id=product_id,
            **{
                key: value for key, value in result.items()
                if key not in {"snapshot_id", "product_id"}
            },
        )
        return Response({
            "status": "ok",
            "message": "Состав конкурентов и цены пересчитаны",
            "result": result,
        })


class IPriceSnapshotOwnAssortmentView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(self, request, snapshot_id, product_id):
        product = (
            IPriceSnapshotProduct.objects
            .filter(pk=product_id, snapshot_id=snapshot_id)
            .first()
        )
        if product is None:
            return Response(
                {
                    "status": "not_found",
                    "message": "Товар расчёта не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = build_iprice_own_assortment(
                snapshot_product=product
            )
        except IPriceOwnAssortmentError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"status": "ok", **result},
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotApprovalSaveView(APIView):
    permission_classes = [CanEditIPriceDashboard]
    serializer_class = (
        IPriceSnapshotApprovalSaveSerializer
    )

    def post(
        self,
        request,
        snapshot_id,
        region_id,
    ):
        region = (
            IPriceSnapshotRegion.objects
            .filter(
                pk=region_id,
                snapshot_product__snapshot_id=(
                    snapshot_id
                ),
            )
            .select_related(
                "snapshot_product__snapshot",
            )
            .first()
        )

        if region is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Региональная строка snapshot "
                        "не найдена"
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        try:
            approval = (
                create_iprice_snapshot_approval(
                    snapshot_region=region,
                    approved_rrp=(
                        serializer
                        .validated_data[
                            "approved_rrp"
                        ]
                    ),
                    approved_by=request.user,
                    comment=(
                        serializer
                        .validated_data
                        .get(
                            "comment",
                            "",
                        )
                    ),
                )
            )

        except IPriceSnapshotApprovalError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        response_serializer = (
            IPriceSnapshotApprovalSerializer(
                approval,
            )
        )

        sync_approval_and_publish(
            snapshot_id=snapshot_id,
            product_id=(
                region.snapshot_product_id
            ),
            region_id=region.id,
        )

        return Response(
            {
                "status": "approved",
                "message": (
                    "Утверждённая цена сохранена"
                ),
                "approval": (
                    response_serializer.data
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class IPriceSnapshotApprovalHistoryView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(
        self,
        request,
        snapshot_id,
        region_id,
    ):
        cache_payload = {
            "snapshot_id": snapshot_id,
            "region_id": region_id,
        }
        cached = get_iprice_cache(
            "postgres:approvals",
            cache_payload,
        )
        if cached is not None:
            return Response(
                cached,
                status=status.HTTP_200_OK,
            )

        region_exists = (
            IPriceSnapshotRegion.objects
            .filter(
                pk=region_id,
                snapshot_product__snapshot_id=(
                    snapshot_id
                ),
            )
            .exists()
        )

        if not region_exists:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Региональная строка snapshot "
                        "не найдена"
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = (
            IPriceSnapshotApproval.objects
            .filter(
                snapshot_region_id=region_id,
            )
            .select_related(
                "approved_by",
            )
            .order_by(
                "-revision",
                "-id",
            )
        )

        serializer = (
            IPriceSnapshotApprovalSerializer(
                queryset,
                many=True,
            )
        )

        result = {
            "count": queryset.count(),
            "results": serializer.data,
        }
        set_iprice_cache(
            "postgres:approvals",
            cache_payload,
            result,
        )
        return Response(
            result,
            status=status.HTTP_200_OK,
        )


class IPriceSnapshotExportView(APIView):
    permission_classes = [CanViewIPriceDashboard]

    def get(
        self,
        request,
        snapshot_id,
    ):
        snapshot = (
            IPriceSnapshot.objects
            .select_related(
                "created_by",
                "activated_by",
            )
            .filter(
                pk=snapshot_id,
            )
            .first()
        )

        if snapshot is None:
            return Response(
                {
                    "status": "not_found",
                    "message": (
                        "Snapshot не найден"
                    ),
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        if (
            snapshot.status
            != IPriceSnapshot.STATUS_SUCCESS
        ):
            return Response(
                {
                    "status": "error",
                    "message": (
                        "Можно выгружать только "
                        "успешно рассчитанный snapshot"
                    ),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        try:
            file_obj = (
                export_iprice_snapshot_to_excel(
                    snapshot=snapshot,
                )
            )

        except ValueError as exc:
            return Response(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        filename = (
            f"iprice_snapshot_"
            f"{snapshot.version_number}_"
            f"{snapshot.calculation_date:%Y%m%d}_"
            f"{timestamp}.xlsx"
        )

        return FileResponse(
            file_obj,
            as_attachment=True,
            filename=filename,
            content_type=EXCEL_CONTENT_TYPE,
        )
