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
         if row["user_id"] in historical_ids),
        key=lambda row: (row["manager_name"], row["user_id"]),
    )
    preference = BitrixUserDepartmentPreference.objects.filter(user=user).first()
    saved = {int(row["manager_id"]): row for row in (preference.manager_settings if preference else [])}
    department_names = {}
    for row in tracking:
        setting = saved.get(row["user_id"], {})
        name = setting.get("display_name") if not setting.get("needs_department_review") else None
        if name and row["department_id"] is not None:
            department_names.setdefault(row["department_id"], set()).add(name)
    options = []
    for row in tracking:
        stored = saved.get(row["user_id"], {})
        names = department_names.get(row["department_id"], set())
        display_name = stored.get("display_name") or (next(iter(names)) if len(names) == 1 else row["department_name"])
        needs_review = bool(stored.get("needs_department_review")) or (not stored.get("display_name") and len(names) > 1)
        options.append({
            "manager_id": row["user_id"],
            "manager_name": row["manager_name"],
            "active": row["active"],
            "crm_department_name": row["department_name"],
            "filter_department_name": display_name,
            "display_name": display_name,
            "needs_department_review": needs_review,
            "selected": bool(stored.get("selected", row["active"])),
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
        name = str(item.get("display_name") or original["display_name"]).strip()[:255] or original["display_name"]
        normalized.append({
            "manager_id": manager_id,
            "selected": bool(item.get("selected")),
            "display_name": name,
            "needs_department_review": original["needs_department_review"] and name == original["display_name"],
        })
    for manager_id, original in available.items():
        if manager_id not in seen:
            normalized.append({"manager_id": manager_id, "selected": original["selected"], "display_name": original["display_name"], "needs_department_review": original["needs_department_review"]})
    # Preserve saved choices for managers temporarily absent from the available data.
    preference = BitrixUserDepartmentPreference.objects.filter(user=user).first()
    normalized.extend(row for row in (preference.manager_settings if preference else [])
                      if int(row["manager_id"]) not in available)
    BitrixUserDepartmentPreference.objects.update_or_create(user=user, defaults={"manager_settings": normalized})
    invalidate_bitrix24_cache()
    return manager_options(user, with_data_only=True)


def selected_manager_ids(user):
    return [row["manager_id"] for row in manager_options(user) if row["selected"]]


def display_names(user):
    return {row["manager_id"]: row["display_name"] for row in manager_options(user)}
