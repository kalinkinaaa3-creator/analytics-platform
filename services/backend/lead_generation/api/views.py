from io import BytesIO
from zipfile import BadZipFile

from django.http import FileResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from lead_generation.access import can_edit, can_view
from lead_generation.excel import load_plan, plan_workbook
from lead_generation.models import LeadGenerationSourcePreference
from lead_generation.services import build_report, normalize_filters, refresh_information, source_options, update_source_preference


PLAN_COLUMNS = [
    ("week_start", "Неделя"), ("budget_vat", "Бюджет ЯндексДирект, руб"),
    ("target_lead_price", "Средняя цена целевого лида, руб"), ("planned_target_leads", "Количество целевых лидов, шт"),
    ("average_revenue_per_lead", "Средняя выручка на лид, руб"), ("revenue_plan", "Потенциал выручки, руб"),
    ("budget_revenue_share", "Доля от выручки, %"), ("direct_cost", "Расходы, руб"),
    ("cost_delta", "Дельта расхода, руб"), ("total_leads", "Общее количество лидов, шт"),
    ("target_leads", "Целевые лиды, шт"), ("non_target_leads", "Нецелевые лиды, шт"),
    ("unprocessed_leads", "Необработанные лиды, шт"), ("target_conversion", "Конверсия в целевые, %"),
    ("target_delta", "Дельта количества целевых лидов, шт"), ("actual_target_cpl", "Фактическая средняя цена целевого лида, руб"),
    ("target_cpl_delta", "Дельта цены целевого лида, руб"), ("lead_opportunity", "Сумма лидов, руб"),
]
SOURCE_COLUMNS = [
    ("week_start", "Неделя"), ("planned_target_leads", "Количество целевых лидов, шт"),
    ("total_leads", "Общее количество лидов, шт"), ("target_leads", "Целевые лиды, шт"),
    ("non_target_leads", "Нецелевые лиды, шт"), ("unprocessed_leads", "Необработанные лиды, шт"),
    ("target_conversion", "CR в целевые, %"), ("target_delta", "Дельта целевых лидов, шт"),
    ("target_deviation", "Отклонение, %"), ("associated_target_leads", "Ассоциированные"),
    ("associated_share", "Доля ассоциированных, %"), ("other_target_leads", "Прочие источники"),
    ("other_share", "Доля прочих источников, %"),
]


def _report_total(page, rows, sources):
    def summed(key):
        return sum(float(row.get(key) or 0) for row in rows)
    keys = [key for key, _label in (PLAN_COLUMNS if page == "plan" else SOURCE_COLUMNS)]
    total = {key: ("Итого" if key == "week_start" else summed(key)) for key in keys}
    if page == "plan":
        total["target_lead_price"] = total["budget_vat"] / total["planned_target_leads"] if total["planned_target_leads"] else None
        total["average_revenue_per_lead"] = total["revenue_plan"] / total["planned_target_leads"] if total["planned_target_leads"] else None
        total["budget_revenue_share"] = total["budget_vat"] * 100 / total["revenue_plan"] if total["revenue_plan"] else None
        total["cost_delta"] = total["budget_vat"] - total["direct_cost"]
        total["target_conversion"] = total["target_leads"] * 100 / total["total_leads"] if total["total_leads"] else None
        total["target_delta"] = total["target_leads"] - total["planned_target_leads"]
        total["actual_target_cpl"] = total["direct_cost"] / total["target_leads"] if total["target_leads"] else None
        total["target_cpl_delta"] = total["target_lead_price"] - total["actual_target_cpl"] if total["actual_target_cpl"] is not None else None
    else:
        total["target_conversion"] = total["target_leads"] * 100 / total["total_leads"] if total["total_leads"] else None
        total["target_delta"] = total["target_leads"] - total["planned_target_leads"]
        total["target_deviation"] = total["target_delta"] * 100 / total["planned_target_leads"] if total["planned_target_leads"] else None
        total["associated_share"] = total["associated_target_leads"] * 100 / total["target_leads"] if total["target_leads"] else None
        total["other_share"] = total["other_target_leads"] * 100 / total["target_leads"] if total["target_leads"] else None
        total["sources"] = {}
        for source in sources:
            source_total = sum(float(row.get("sources", {}).get(source["id"], {}).get("total") or 0) for row in rows)
            source_target = sum(float(row.get("sources", {}).get(source["id"], {}).get("target") or 0) for row in rows)
            total["sources"][source["id"]] = {"total": source_total, "target": source_target, "conversion": source_target * 100 / source_total if source_total else None}
    return total


class AccessMixin:
    edit_required = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        allowed = can_edit(request.user) if self.edit_required else can_view(request.user)
        if not allowed:
            raise PermissionDenied("Нет доступа к отчёту «Лидогенерация».")


def _filters(request):
    try:
        return normalize_filters(request.query_params)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"period": str(exc)})


class ReportView(AccessMixin, APIView):
    def get(self, request, page):
        try:
            return Response(build_report(page, _filters(request), request.user))
        except ValueError as exc:
            raise ValidationError({"page": str(exc)})


class SourcePreferenceView(AccessMixin, APIView):
    def get(self, request):
        preference = LeadGenerationSourcePreference.objects.filter(user=request.user).first()
        return Response({"options": source_options(), "selected": preference.source_ids if preference else [], "can_edit": can_edit(request.user)})

    def post(self, request):
        source_ids = request.data.get("source_ids")
        if not isinstance(source_ids, list):
            raise ValidationError({"source_ids": "Ожидается список источников."})
        return Response({"selected": update_source_preference(request.user, source_ids)})


class PlanUploadView(AccessMixin, APIView):
    edit_required = True
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded or not uploaded.name.lower().endswith(".xlsx"):
            raise ValidationError({"file": "Передайте файл .xlsx."})
        if uploaded.size > 10 * 1024 * 1024:
            raise ValidationError({"file": "Размер файла не должен превышать 10 МБ."})
        try:
            return Response({"status": "ok", **load_plan(uploaded, request.user)})
        except (ValueError, TypeError, BadZipFile, InvalidFileException) as exc:
            raise ValidationError({"file": str(exc)})
        except Exception:
            from analytics.services.bitrix_notify import send_bitrix_message
            send_bitrix_message("[b]Лидогенерация: план[/b] Ошибка загрузки XLSX. Подробности в логе Django.", logger_name="lead_generation")
            raise


class PlanDownloadView(AccessMixin, APIView):
    def get(self, request):
        return FileResponse(plan_workbook(), as_attachment=True, filename="lead_generation_plan.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class ReportExportView(AccessMixin, APIView):
    def get(self, request, page):
        report = build_report(page, _filters(request), request.user)
        columns = list(PLAN_COLUMNS if page == "plan" else SOURCE_COLUMNS)
        if page == "plan":
            position = next(i for i, (key, _) in enumerate(columns) if key == "lead_opportunity")
            columns[position:position] = [("revenue_1c_total", "Выручка итого, руб")] + [
                (item["key"], item["name"]) for item in report.get("revenue_directions", [])
            ]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "План" if page == "plan" else "Источники"
        dynamic = report.get("sources") or []
        headers = [label for _key, label in columns]
        if page == "sources":
            for source in dynamic:
                headers.extend((f"{source['name']}: Общее", f"{source['name']}: Целевые", f"{source['name']}: CR, %"))
        sheet.append(headers)
        for row in report["rows"]:
            values = [row.get(key) for key, _label in columns]
            if page == "sources":
                for source in dynamic:
                    item = row.get("sources", {}).get(source["id"], {})
                    values.extend((item.get("total"), item.get("target"), item.get("conversion")))
            sheet.append(values)
        total = _report_total(page, report["rows"], dynamic)
        if page == "plan":
            for key, _label in columns:
                if key.startswith("revenue_1c_"):
                    total[key] = sum(float(row.get(key) or 0) for row in report["rows"])
        total_values = [total.get(key) for key, _label in columns]
        if page == "sources":
            for source in dynamic:
                item = total.get("sources", {}).get(source["id"], {})
                total_values.extend((item.get("total"), item.get("target"), item.get("conversion")))
        sheet.append(total_values)
        sheet.freeze_panes = "B2"
        sheet.auto_filter.ref = sheet.dimensions
        header_fill = PatternFill("solid", fgColor="536B50")
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for cell in sheet[sheet.max_row]:
            cell.fill = PatternFill("solid", fgColor="DFE8DA")
            cell.font = Font(name="Arial", size=10, bold=True, color="253023")
        sheet.row_dimensions[1].height = 42
        for column_cells in sheet.columns:
            sheet.column_dimensions[column_cells[0].column_letter].width = min(30, max(14, max(len(str(cell.value or "")) for cell in column_cells) + 2))
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return FileResponse(stream, as_attachment=True, filename=f"lead_generation_{page}.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class RefreshInfoView(AccessMixin, APIView):
    def get(self, request):
        return Response(refresh_information())
