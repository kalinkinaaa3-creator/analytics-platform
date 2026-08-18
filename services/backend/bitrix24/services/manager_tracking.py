from __future__ import annotations

import tempfile
from pathlib import Path

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from bitrix24.models import BitrixDepartment, BitrixManagerTracking, BitrixUser


SHEET_UPLOAD = "Загрузка"
SHEET_UNTRACKED = "Не отмеченные"
HEADERS = ("Менеджер", "Подразделение", "Отслеживать")


class ManagerTrackingValidationError(ValueError):
    pass


def _normalize(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def _active_users():
    return BitrixUser.objects.filter(active=True, is_deleted=False).order_by(
        "full_name", "user_id"
    )


def build_manager_tracking_template() -> Path:
    tracking = {
        row.user_id: row
        for row in BitrixManagerTracking.objects.select_related("department")
    }
    departments = dict(
        BitrixDepartment.objects.filter(is_deleted=False).values_list(
            "department_id", "name"
        )
    )
    workbook = Workbook()
    upload = workbook.active
    upload.title = SHEET_UPLOAD
    untracked = workbook.create_sheet(SHEET_UNTRACKED)
    upload.append(HEADERS)
    untracked.append(("Менеджер",))
    for sheet in (upload, untracked):
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="515B4B")
            cell.font = Font(color="FFFFFF", bold=True)
        sheet.freeze_panes = "A2"
        sheet.column_dimensions["A"].width = 42
    upload.column_dimensions["B"].width = 36
    upload.column_dimensions["C"].width = 18

    for user in _active_users().iterator(chunk_size=500):
        current = tracking.get(user.user_id)
        department_name = (
            current.department.name
            if current
            else departments.get(user.primary_department_id, "")
        )
        is_tracked = bool(current and current.is_tracked)
        row = (user.full_name, department_name, "Да" if is_tracked else "Нет")
        upload.append(row)
        if not is_tracked:
            untracked.append((user.full_name,))

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    path = Path(temporary.name)
    temporary.close()
    workbook.save(path)
    return path


def load_manager_tracking(uploaded_file) -> dict:
    workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    try:
        if SHEET_UPLOAD not in workbook.sheetnames:
            raise ManagerTrackingValidationError(
                f'В файле отсутствует лист «{SHEET_UPLOAD}».'
            )
        sheet = workbook[SHEET_UPLOAD]
        header = tuple(
            " ".join(str(value or "").split())
            for value in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))[:3]
        )
        if header != HEADERS:
            raise ManagerTrackingValidationError(
                "Первая строка должна содержать: Менеджер, Подразделение, Отслеживать."
            )

        users_by_name = {}
        for user in _active_users().only("user_id", "full_name"):
            users_by_name.setdefault(_normalize(user.full_name), []).append(user)
        departments_by_name = {}
        for department in BitrixDepartment.objects.filter(is_deleted=False).only(
            "department_id", "name"
        ):
            departments_by_name.setdefault(_normalize(department.name), []).append(
                department
            )

        parsed = []
        seen_user_ids = set()
        errors = []
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, values_only=True), start=2
        ):
            manager_name, department_name, tracked_value = (tuple(row) + (None,) * 3)[:3]
            if not any(value not in (None, "") for value in (manager_name, department_name, tracked_value)):
                continue
            users = users_by_name.get(_normalize(manager_name), [])
            if len(users) != 1:
                errors.append(
                    f"Строка {row_number}: менеджер «{manager_name or ''}» "
                    + ("не найден." if not users else "найден неоднозначно.")
                )
                continue
            departments = departments_by_name.get(_normalize(department_name), [])
            if len(departments) != 1:
                errors.append(
                    f"Строка {row_number}: подразделение «{department_name or ''}» "
                    + ("не найдено." if not departments else "найдено неоднозначно.")
                )
                continue
            tracked_normalized = _normalize(tracked_value)
            if tracked_normalized not in {"да", "нет"}:
                errors.append(
                    f"Строка {row_number}: в поле «Отслеживать» допустимы только Да или Нет."
                )
                continue
            user = users[0]
            if user.user_id in seen_user_ids:
                errors.append(f"Строка {row_number}: менеджер указан повторно.")
                continue
            seen_user_ids.add(user.user_id)
            parsed.append((user, departments[0], tracked_normalized == "да"))

        if errors:
            raise ManagerTrackingValidationError("\n".join(errors[:50]))
        if not parsed:
            raise ManagerTrackingValidationError("На листе «Загрузка» нет строк для загрузки.")

        with transaction.atomic():
            BitrixManagerTracking.objects.update(is_tracked=False)
            for user, department, is_tracked in parsed:
                BitrixManagerTracking.objects.update_or_create(
                    user_id=user.user_id,
                    defaults={
                        "manager_name": user.full_name,
                        "department": department,
                        "is_tracked": is_tracked,
                    },
                )
        return {
            "rows": len(parsed),
            "tracked": sum(1 for _, _, value in parsed if value),
            "not_tracked": sum(1 for _, _, value in parsed if not value),
        }
    finally:
        workbook.close()
