from bitrix24.models import BitrixDeal, BitrixLead, BitrixUserDepartmentPreference
from bitrix24.cache import invalidate_bitrix24_cache
from bitrix24.services.manager_departments import automatic_manager_directory


def managers_with_data():
    """Use all loaded history, independently of dashboard dates and filters."""
    manager_ids = set()
    for model in (BitrixLead, BitrixDeal):
        manager_ids.update(
            model.objects.filter(is_deleted=False, assigned_by_id__isnull=False)
            .order_by().values_list("assigned_by_id", flat=True).distinct()
        )
    return manager_ids


def manager_options(user, *, with_data_only=False):
    historical_ids = managers_with_data()
    tracking = sorted(
        (row for row in automatic_manager_directory().values()
         if row["active"] or row["user_id"] in historical_ids),
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
            "active": row["active"],
            "crm_department_name": row["department_name"],
            "filter_department_name": row["department_name"],
            "display_name": stored.get("display_name") or row["department_name"],
            "selected": bool(stored.get("selected", row["active"])),
        })
    if with_data_only:
        departments = {row["department_name"] for row in tracking if row["user_id"] in historical_ids}
        options = [row for row in options if row["crm_department_name"] in departments]
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
            # Departments without data are absent from the form, not deselected.
            normalized.append({"manager_id": manager_id, "selected": original["selected"], "display_name": original["display_name"]})
    BitrixUserDepartmentPreference.objects.update_or_create(user=user, defaults={"manager_settings": normalized})
    invalidate_bitrix24_cache()
    return manager_options(user, with_data_only=True)


def selected_manager_ids(user):
    return [row["manager_id"] for row in manager_options(user) if row["selected"]]


def display_names(user):
    return {row["manager_id"]: row["display_name"] for row in manager_options(user)}
