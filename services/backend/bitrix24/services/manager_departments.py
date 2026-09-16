from bitrix24.models import BitrixDepartment, BitrixUser

UNKNOWN_DEPARTMENT_NAME = "Подразделение не указано"


def automatic_manager_directory(*, active_only=False):
    """Return the current Bitrix manager-to-primary-department mapping."""
    departments = dict(
        BitrixDepartment.objects.filter(is_deleted=False).values_list(
            "department_id", "name"
        )
    )
    users = BitrixUser.objects.filter(is_deleted=False)
    if active_only:
        users = users.filter(active=True)
    return {
        row["user_id"]: {
            "user_id": row["user_id"],
            "manager_name": row["full_name"] or str(row["user_id"]),
            "active": row["active"],
            "department_id": row["primary_department_id"],
            "department_name": departments.get(row["primary_department_id"])
            or UNKNOWN_DEPARTMENT_NAME,
        }
        for row in users.values("user_id", "full_name", "primary_department_id", "active")
    }
