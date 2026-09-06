from zipfile import BadZipFile

from django.core.cache import cache
from django.http import FileResponse
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from context_analytics.services.access import can_edit, can_view
from context_analytics.services.refresh import (
    DEFAULT_INCREMENTAL_DAYS,
    ContextRefreshAlreadyRunning,
    latest_state,
    launch,
)
from context_analytics.services.reporting import SUPPORTED_PAGES, get_options, get_report, normalize_query
from context_analytics.models import ContextExportRun
from context_analytics.services.export_jobs import (
    ExportAlreadyRunning, export_directory, launch_export, state,
)
from datasets.api.permissions import HasInternalApiKey
from seo_analytics.services.configuration import CONFIG_GOALS, build_configuration_workbook, load_configuration

class AccessMixin:
    edit_required = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not (can_edit(request.user) if self.edit_required else can_view(request.user)):
            raise PermissionDenied("Нет доступа к отчёту «Контекстная реклама».")


class FilterOptionsView(AccessMixin, APIView):
    def get(self, request):
        try:
            filters = normalize_query(request.query_params)
        except ValueError as exc:
            raise ValidationError({"period": str(exc)})
        return Response({"options": get_options(filters), "can_edit": can_edit(request.user)})


class ReportView(AccessMixin, APIView):
    def get(self, request, page):
        if page not in SUPPORTED_PAGES:
            raise NotFound("Раздел отчёта не найден.")
        try:
            filters = normalize_query(request.query_params)
        except ValueError as exc:
            raise ValidationError({"period": str(exc)})
        return Response(get_report(page, filters))


class ReportExportView(AccessMixin, APIView):
    def post(self, request, page):
        if page not in SUPPORTED_PAGES:
            raise NotFound("Раздел отчёта не найден.")
        try:
            filters = normalize_query(request.query_params)
        except ValueError as exc:
            raise ValidationError({"period": str(exc)})
        try:
            run = launch_export(request.user, page, filters)
        except ExportAlreadyRunning as exc:
            return Response({"status": "running", "message": str(exc)}, status=409)
        return Response(state(run), status=202)


class ExportStateView(AccessMixin, APIView):
    def get(self, request, run_id):
        try:
            run = ContextExportRun.objects.get(pk=run_id, started_by=request.user)
        except ContextExportRun.DoesNotExist:
            raise NotFound("Экспорт не найден.")
        return Response(state(run))


class ExportDownloadView(AccessMixin, APIView):
    def get(self, request, run_id):
        try:
            run = ContextExportRun.objects.get(pk=run_id, started_by=request.user, status="success")
        except ContextExportRun.DoesNotExist:
            raise NotFound("Готовый экспорт не найден.")
        path = export_directory() / f"{run.id}.xlsx"
        if not path.is_file():
            raise NotFound("Файл экспорта уже удалён.")
        return FileResponse(path.open("rb"), as_attachment=True,
                            filename=f"context_{run.page}.xlsx",
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class ConfigurationTemplateView(AccessMixin, APIView):
    edit_required = True

    def get(self, request):
        return FileResponse(build_configuration_workbook(CONFIG_GOALS), as_attachment=True,
                            filename="analytics_goals.xlsx",
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class ConfigurationUploadView(AccessMixin, APIView):
    edit_required = True
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded or not uploaded.name.lower().endswith(".xlsx"):
            raise ValidationError({"file": "Передайте файл .xlsx."})
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError({"file": "Размер файла не должен превышать 5 МБ."})
        try:
            result = load_configuration(uploaded, CONFIG_GOALS)
        except (ValueError, TypeError, BadZipFile, InvalidFileException) as exc:
            raise ValidationError({"file": str(exc)})
        cache.delete_pattern("seo:report:*")
        cache.delete_pattern("context:report:*")
        cache.delete_pattern("context:filter-options:*")
        return Response({"status": "ok", **result})


class RefreshView(AccessMixin, APIView):
    def post(self, request):
        try:
            launch(request.user)
        except ContextRefreshAlreadyRunning as exc:
            return Response({"status": "running", "message": str(exc)}, status=409)
        return Response({"status": "started"}, status=202)


class RefreshStateView(AccessMixin, APIView):
    def get(self, request):
        return Response({**latest_state(), "can_edit": can_edit(request.user)})


class InternalRefreshView(APIView):
    authentication_classes = []
    permission_classes = [HasInternalApiKey]

    def post(self, request):
        try:
            launch(trigger="scheduled", days=DEFAULT_INCREMENTAL_DAYS)
        except ContextRefreshAlreadyRunning as exc:
            # A retry after a lost HTTP response must not start a duplicate job.
            return Response({"status": "running", "message": str(exc)}, status=202)
        return Response({"status": "started"}, status=202)
