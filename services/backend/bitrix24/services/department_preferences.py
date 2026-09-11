from bitrix24.models import BitrixDepartment, BitrixManagerTracking, BitrixUser, BitrixUserDepartmentPreference
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME


def manager_options(user):
    tracked = {row["user_id"]: row for row in BitrixManagerTracking.objects.values("user_id", "manager_name", "department_name")}
    departments = dict(BitrixDepartment.objects.filter(is_deleted=False).values_list("department_id", "name"))
    tracking = []
    for user_row in BitrixUser.objects.filter(is_deleted=False, active=True).order_by("full_name", "user_id").values("user_id", "full_name", "primary_department_id"):
        configured = tracked.get(user_row["user_id"], {})
        tracking.append({
            "user_id": user_row["user_id"],
            "manager_name": user_row["full_name"] or configured.get("manager_name") or str(user_row["user_id"]),
            "department_name": departments.get(user_row["primary_department_id"]) or configured.get("department_name") or UNTRACKED_DEPARTMENT_NAME,
        })
    preference = BitrixUserDepartmentPreference.objects.filter(user=user).first()
    saved = {int(row["manager_id"]): row for row in (preference.manager_settings if preference else [])}
    options = []
    for row in tracking:
        stored = saved.get(row["user_id"], {})
        options.append({
            "manager_id": row["user_id"],
            "manager_name": row["manager_name"],
            "crm_department_name": row["department_name"],
            "filter_department_name": tracked.get(row["user_id"], {}).get("department_name") or UNTRACKED_DEPARTMENT_NAME,
            "display_name": stored.get("display_name") or row["department_name"],
            "selected": bool(stored.get("selected", True)) if preference else True,
        })
    return options


def save_manager_options(user, rows):
    available = {row["manager_id"]: row for row in manager_options(user)}
    normalized = []
    seen = set()
    for item in rows:
        manager_id = int(item.get("manager_id"))
        if manager_id in seen or manager_id not in available:
            continue
        seen.add(manager_id)
        original = available[manager_id]
        normalized.append({
            "manager_id": manager_id,
            "selected": bool(item.get("selected")),
            "display_name": str(item.get("display_name") or original["crm_department_name"]).strip()[:255] or original["crm_department_name"],
        })
    for manager_id, original in available.items():
        if manager_id not in seen:
            normalized.append({"manager_id": manager_id, "selected": False, "display_name": original["crm_department_name"]})
    BitrixUserDepartmentPreference.objects.update_or_create(user=user, defaults={"manager_settings": normalized})
    return manager_options(user)


def selected_manager_ids(user):
    return [row["manager_id"] for row in manager_options(user) if row["selected"]]


def display_names(user):
    return {row["manager_id"]: row["display_name"] for row in manager_options(user)}
