import logging

from django.http import FileResponse
from zipfile import BadZipFile
from django.core.cache import cache
from django.db import transaction
from datasets.api.permissions import HasInternalApiKey
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from openpyxl.utils.exceptions import InvalidFileException

from seo_analytics.services.access import can_edit, can_view
from seo_analytics.services.configuration import (
    CONFIG_BRANDS,
    CONFIG_GOALS,
    build_configuration_workbook,
    load_configuration,
)
from seo_analytics.services.clickhouse import reclassify_phrase_types
from seo_analytics.models import SeoBrandMask, SeoExportRun
from seo_analytics.services.export_jobs import (
    ExportAlreadyRunning, export_directory, launch_export, state,
)
from seo_analytics.services.filters import normalize_query
from seo_analytics.services.options import get_filter_options
from seo_analytics.services.refresh import (
    SeoRefreshAlreadyRunning,
    latest_state,
    launch_background_refresh,
)
from seo_analytics.services.reporting import SUPPORTED_PAGES, get_report


logger = logging.getLogger("seo_analytics.configuration")

class SeoAccessMixin:
    edit_required = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        allowed = can_edit(request.user) if self.edit_required else can_view(request.user)
        if not allowed:
            raise PermissionDenied("Нет доступа к SEO-аналитике.")


def _page(value):
    if value not in SUPPORTED_PAGES:
        raise NotFound("Страница SEO-аналитики не найдена.")
    return value


class SeoFilterOptionsView(SeoAccessMixin, APIView):
    def get(self, request):
        filters = normalize_query(request.query_params)
        options = get_filter_options(filters=filters, page=request.query_params.get("page", ""))
        return Response({
            "options": options,
            "configured": options.get("metrika_configured", False),
            "can_edit": can_edit(request.user),
        })


class SeoReportView(SeoAccessMixin, APIView):
    def get(self, request, page):
        filters = normalize_query(request.query_params)
        return Response(get_report(_page(page), filters))


class SeoReportExportView(SeoAccessMixin, APIView):
    def post(self, request, page):
        filters = normalize_query(request.query_params)
        page = _page(page)
        try:
            run = launch_export(request.user, page, filters)
        except ExportAlreadyRunning as exc:
            return Response({"status": "running", "message": str(exc)}, status=409)
        return Response(state(run), status=202)


class SeoExportStateView(SeoAccessMixin, APIView):
    def get(self, request, run_id):
        try:
            run = SeoExportRun.objects.get(pk=run_id, started_by=request.user)
        except SeoExportRun.DoesNotExist:
            raise NotFound("Экспорт не найден.")
        return Response(state(run))


class SeoExportDownloadView(SeoAccessMixin, APIView):
    def get(self, request, run_id):
        try:
            run = SeoExportRun.objects.get(pk=run_id, started_by=request.user, status="success")
        except SeoExportRun.DoesNotExist:
            raise NotFound("Готовый экспорт не найден.")
        path = export_directory() / f"{run.id}.xlsx"
        if not path.is_file():
            raise NotFound("Файл экспорта уже удалён.")
        return FileResponse(path.open("rb"), as_attachment=True,
                            filename=f"seo_{run.page}.xlsx",
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _configuration_kind(value):
    if value not in {CONFIG_GOALS, CONFIG_BRANDS}:
        raise NotFound("Тип настроек SEO не найден.")
    return value


class SeoConfigurationTemplateView(SeoAccessMixin, APIView):
    edit_required = True

    def get(self, request, kind):
        kind = _configuration_kind(kind)
        filename = "seo_goals.xlsx" if kind == CONFIG_GOALS else "seo_brand_masks.xlsx"
        return FileResponse(
            build_configuration_workbook(kind),
            as_attachment=True,
            filename=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class SeoConfigurationUploadView(SeoAccessMixin, APIView):
    edit_required = True
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, kind):
        kind = _configuration_kind(kind)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": "Файл не передан."})
        if not uploaded.name.lower().endswith(".xlsx"):
            raise ValidationError({"file": "Поддерживается только формат .xlsx."})
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError({"file": "Размер файла не должен превышать 5 МБ."})
        try:
            with transaction.atomic():
                result = load_configuration(uploaded, kind)
                if kind == CONFIG_BRANDS:
                    try:
                        reclassify_phrase_types(
                            SeoBrandMask.objects.filter(is_active=True).values_list("mask", flat=True)
                        )
                    except Exception as exc:
                        logger.exception("SEO phrase reclassification failed")
                        raise ValueError(
                            "Маски не сохранены: не удалось пересчитать типы фраз в аналитической витрине."
                        ) from exc
        except (ValueError, TypeError, BadZipFile, InvalidFileException) as exc:
            raise ValidationError({"file": str(exc)})
        cache.delete_pattern("seo:report:v1:*")
        cache.delete_pattern("seo:report:v2:*")
        cache.delete_pattern("seo:report:v3:*")
        cache.delete_pattern("seo:report:v4:*")
        cache.delete_pattern("seo:report:v5:*")
        cache.delete_pattern("seo:report:v6:*")
        cache.delete_pattern("context:report:*")
        cache.delete_pattern("context:filter-options:*")
        return Response({"status": "ok", **result})


class SeoRefreshView(SeoAccessMixin, APIView):
    def post(self, request):
        page = request.query_params.get("page", "")
        if page:
            _page(page)
        try:
            launch_background_refresh(
                request.user,
                page=page,
                filters=None,
            )
        except SeoRefreshAlreadyRunning as exc:
            return Response({"status": "running", "message": str(exc)}, status=409)
        return Response({"status": "started"}, status=202)


class SeoRefreshStateView(SeoAccessMixin, APIView):
    def get(self, request):
        return Response({**latest_state(), "can_edit": can_edit(request.user)})


class SeoInternalRefreshView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        window = request.query_params.get("window", "default")
        if window not in {"default", "two-months"}:
            raise ValidationError({"window": "Неизвестное окно обновления."})
        try:
            launch_background_refresh(
                trigger="scheduled",
                window=window,
            )
        except SeoRefreshAlreadyRunning as exc:
            # A retry after a lost HTTP response must not start a duplicate job.
            return Response({"status": "running", "message": str(exc)}, status=202)
        return Response({"status": "started"}, status=202)
