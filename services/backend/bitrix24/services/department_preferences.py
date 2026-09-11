from bitrix24.models import BitrixUserDepartmentPreference
from bitrix24.services.manager_departments import automatic_manager_directory


def manager_options(user):
    tracking = sorted(
        automatic_manager_directory(active_only=True).values(),
        key=lambda row: (row["manager_name"], row["user_id"]),
    )
    preference = BitrixUserDepartmentPreference.objects.filter(user=user).first()
    saved = {int(row["manager_id"]): row for row in (preference.manager_settings if preference else [])}
    options = []
    for row in tracking:
        stored = saved.get(row["user_id"], {})
        options.append({
            "manager_id": row["user_id"],
            "manager_name": row["manager_name"],
            "crm_department_name": row["department_name"],
            "filter_department_name": row["department_name"],
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
