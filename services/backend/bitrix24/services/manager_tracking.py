from __future__ import annotations

import tempfile
from pathlib import Path

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from bitrix24.models import BitrixDepartment, BitrixManagerTracking, BitrixUser
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME


SHEET_UPLOAD = "Загрузка"
SHEET_MANAGERS = "Менеджеры и подразделения"
HEADERS = ("Менеджер", "Подразделение")
DIRECTORY_HEADERS = (
    "Менеджер",
    "Подразделение из Bitrix24",
    "Отслеживаемое подразделение",
)


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
        for row in BitrixManagerTracking.objects.all()
    }
    departments = dict(
        BitrixDepartment.objects.filter(is_deleted=False).values_list(
            "department_id", "name"
        )
    )
    workbook = Workbook()
    upload = workbook.active
    upload.title = SHEET_UPLOAD
    managers = workbook.create_sheet(SHEET_MANAGERS)
    upload.append(HEADERS)
    managers.append(DIRECTORY_HEADERS)
    for sheet in (upload, managers):
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="515B4B")
            cell.font = Font(color="FFFFFF", bold=True)
        sheet.freeze_panes = "A2"
        sheet.column_dimensions["A"].width = 42
    upload.column_dimensions["B"].width = 36
    managers.column_dimensions["B"].width = 36
    managers.column_dimensions["C"].width = 36

    for user in _active_users().iterator(chunk_size=500):
        current = tracking.get(user.user_id)
        if current:
            upload.append((user.full_name, current.department_name))
        managers.append(
            (
                user.full_name,
                departments.get(user.primary_department_id, ""),
                current.department_name if current else UNTRACKED_DEPARTMENT_NAME,
            )
        )

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
            for value in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True))[:2]
        )
        if header != HEADERS:
            raise ManagerTrackingValidationError(
                "Первая строка должна содержать: Менеджер, Подразделение."
            )

        users_by_name = {}
        for user in _active_users().only("user_id", "full_name"):
            users_by_name.setdefault(_normalize(user.full_name), []).append(user)
        parsed = []
        seen_user_ids = set()
        errors = []
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, values_only=True), start=2
        ):
            manager_name, department_name = (tuple(row) + (None,) * 2)[:2]
            if not any(value not in (None, "") for value in (manager_name, department_name)):
                continue
            users = users_by_name.get(_normalize(manager_name), [])
            if len(users) != 1:
                errors.append(
                    f"Строка {row_number}: менеджер «{manager_name or ''}» "
                    + ("не найден." if not users else "найден неоднозначно.")
                )
                continue
            department_name = " ".join(str(department_name or "").split())
            if not department_name:
                errors.append(
                    f"Строка {row_number}: подразделение должно быть заполнено вручную."
                )
                continue
            user = users[0]
            if user.user_id in seen_user_ids:
                errors.append(f"Строка {row_number}: менеджер указан повторно.")
                continue
            seen_user_ids.add(user.user_id)
            parsed.append((user, department_name))

        if errors:
            raise ManagerTrackingValidationError("\n".join(errors[:50]))
        active_user_count = _active_users().count()
        with transaction.atomic():
            BitrixManagerTracking.objects.all().delete()
            BitrixManagerTracking.objects.bulk_create(
                [
                    BitrixManagerTracking(
                        user_id=user.user_id,
                        manager_name=user.full_name,
                        department_name=department_name,
                    )
                    for user, department_name in parsed
                ],
                batch_size=500,
            )
        return {
            "rows": len(parsed),
            "tracked": len(parsed),
            "not_tracked": max(0, active_user_count - len(parsed)),
        }
    finally:
        workbook.close()
