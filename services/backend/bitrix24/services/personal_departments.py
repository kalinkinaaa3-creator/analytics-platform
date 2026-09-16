"""Personal department groups use manager IDs, never source department labels."""


def department_mapping(options):
    return tuple(sorted(
        (row["manager_id"], row["display_name"])
        for row in options if row["selected"]
    ))


def department_expression(mapping, params):
    from .dashboard_query import UNTRACKED_DEPARTMENT_NAME

    params["personal_untracked"] = UNTRACKED_DEPARTMENT_NAME
    groups = {}
    for manager_id, name in mapping:
        groups.setdefault(name, []).append(manager_id)
    branches = []
    for index, (name, ids) in enumerate(sorted(groups.items())):
        params[f"personal_ids_{index}"] = tuple(ids)
        params[f"personal_name_{index}"] = name
        branches.extend((f"manager_id IN %(personal_ids_{index})s", f"%(personal_name_{index})s"))
    return "multiIf(" + ", ".join([*branches, "%(personal_untracked)s"]) + ")" if branches else "%(personal_untracked)s"


def personal_tracking(refs, filters):
    if "personal_departments" in filters:
        return {manager_id: {"department_name": name}
                for manager_id, name in filters["personal_departments"]}
    tracking = refs["tracking"]
    if "tracked_manager_ids" in filters:
        ids = set(filters["tracked_manager_ids"])
        tracking = {key: row for key, row in tracking.items() if key in ids}
    return tracking
