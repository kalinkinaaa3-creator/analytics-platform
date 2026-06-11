import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from datasets.models import FbProject


MONTHS_RU = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}


FB_PROJECT_FIELDS = [
    "id",
    "folder_lvl1",
    "folder_lvl2",
    "folder_lvl3",
    "project_name",
    "project_manager",
    "start_date",
    "end_date",
    "project_status",
    "project_type",
    "department",
    "subtask_id",
    "subtask_name",
    "subtask_responsible",
    "subtask_start_date",
    "subtask_end_date",
    "actual_start_project",
    "actual_end_project",
    "actual_start_subtask",
    "actual_end_subtask",
    "subtask_status",
    "m_quarter_text",
    "deviation",
    "deviation_project",
    "number",
    "predecessor",
    "code_sdr",
    "type_depend",
    "delay",
    "unit",
    "hier_subtask1",
    "hier_subtask2",
    "hier_subtask3",
    "hier_subtask4",
    "hier_subtask5",
    "hier_subtask6",
    "hier_subtask7",
    "hier_subtask8",
    "hier_subtask9",
    "hier_subtask10",
]


def prepare_fb_project_rows() -> list[dict]:
    return list(
        FbProject.objects.all()
        .order_by("id")
        .values(*FB_PROJECT_FIELDS)
    )


def assign_knot_fields(project_tasks: list[dict]) -> list[dict]:
    dedup_key_fields = (
        "project_name",
        "project_manager",
        "subtask_name",
        "subtask_responsible",
        "subtask_status",
        "subtask_start_date",
        "subtask_end_date",
        "actual_start_subtask",
        "actual_end_subtask",
    )

    seen = set()
    unique_tasks = []

    for task in project_tasks:
        key = tuple(task.get(field) for field in dedup_key_fields)
        if key not in seen:
            seen.add(key)
            unique_tasks.append(task)

    projects = defaultdict(list)

    for task in unique_tasks:
        projects[task.get("project_name")].append(task)

    knot_fields_map = {
        "responsible": "subtask_responsible",
        "start_date": "subtask_start_date",
        "end_date": "subtask_end_date",
        "start_subtask": "actual_start_subtask",
        "end_subtask": "actual_end_subtask",
        "status": "subtask_status",
    }

    final_tasks = []

    for project_name, tasks in projects.items():
        tasks_pool = {
            task["subtask_name"]: task
            for task in tasks
            if task.get("subtask_name") and task.get("subtask_name") != "-"
        }

        used_tasks = set()

        for row in tasks:
            for i in range(10, 0, -1):
                hier_name = row.get(f"hier_subtask{i}")

                if not hier_name or hier_name == "-":
                    continue

                found_task = tasks_pool.get(hier_name)

                if found_task:
                    used_tasks.add(hier_name)

                    for suffix, orig_field in knot_fields_map.items():
                        row[f"knot_{suffix}{i}"] = found_task.get(orig_field)

        for task in tasks:
            if task.get("subtask_name") not in used_tasks:
                final_tasks.append(task)

    return final_tasks


def _to_date_or_none(value):
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    return None


def is_valid_date_val(value) -> bool:
    parsed = _to_date_or_none(value)
    return parsed is not None and parsed.year != 1


def normalize_actual_dates(start_value, end_value):
    today = date.today()

    start = _to_date_or_none(start_value) if is_valid_date_val(start_value) else None
    end = _to_date_or_none(end_value) if is_valid_date_val(end_value) else None

    start_ok = start is not None
    end_ok = end is not None

    if not start_ok and not end_ok:
        return "", ""

    if start_ok and not end_ok:
        return start, today

    if end_ok and not start_ok:
        return "", end

    return start, end


def norm_display(value):
    if not is_valid_date_val(value):
        return ""

    return _to_date_or_none(value)


def calc_bar(start, end, months_list):
    start = _to_date_or_none(start)
    end = _to_date_or_none(end)

    if not start or not end:
        return None

    offset = 0
    width = 0
    offset_set = False

    for month in months_list:
        month_start = month["start"]
        month_end = month["end"]
        month_width = month["width"]

        if end < month_start or start > month_end:
            continue

        bar_start = max(start, month_start)
        bar_end = min(end, month_end)

        days_in_month = (month_end - month_start).days + 1
        days_of_bar = (bar_end - bar_start).days + 1

        if not offset_set:
            offset = (
                sum(m["width"] for m in months_list if m["end"] < bar_start)
                + ((bar_start - month_start).days / days_in_month * month_width)
            )
            offset_set = True

        width += (days_of_bar / days_in_month) * month_width

    if not offset_set:
        return None

    return {
        "offset": offset,
        "width": width,
    }


def _conv_to_date_if_dt(value):
    if isinstance(value, datetime):
        return value.date()

    return value


def build_months_list(start_date: date, end_date: date) -> list[dict]:
    months_list = []

    current = start_date.replace(day=1)

    while current <= end_date:
        month_end = (current + relativedelta(months=1)) - timedelta(days=1)
        month_end = min(month_end, end_date)

        months_list.append({
            "label": f"{MONTHS_RU[current.month]},{str(current.year)[-2:]}",
            "start": current,
            "end": month_end,
            "width": 62,
        })

        current += relativedelta(months=1)

    return months_list


def sort_tree_by_plan_start(projects_list: list[dict]) -> list[dict]:
    def sort_nodes(nodes):
        nodes.sort(
            key=lambda node: node["sign"]["plan"]["start"] or date.max
        )

        for node in nodes:
            node["subtasks"].sort(
                key=lambda subtask: subtask["sign"]["plan"]["start"] or date.max
            )
            sort_nodes(node["children"])

    projects_list.sort(
        key=lambda project: project["sign"]["plan"]["start"] or date.max
    )

    for project in projects_list:
        project["subtasks"].sort(
            key=lambda subtask: subtask["sign"]["plan"]["start"] or date.max
        )
        sort_nodes(project["hierarchy"])

    return projects_list


def build_projects_tree(project_tasks: list[dict], months_list: list[dict]):
    projects_map = {}
    global_min = None
    global_max = None
    today_offset = None
    today = date.today()

    for row in project_tasks:
        project_key = row.get("project_name")

        if project_key not in projects_map:
            plan_start, plan_end = normalize_actual_dates(
                row.get("start_date"),
                row.get("end_date"),
            )

            fact_start, fact_end = normalize_actual_dates(
                row.get("actual_start_project"),
                row.get("actual_end_project"),
            )

            projects_map[project_key] = {
                "id": str(uuid.uuid4()),
                "project_name": project_key,
                "folder_lvl1": row.get("folder_lvl1"),
                "folder_lvl2": row.get("folder_lvl2"),
                "folder_lvl3": row.get("folder_lvl3"),
                "project_manager": row.get("project_manager"),
                "project_status": row.get("project_status"),
                "project_type": row.get("project_type"),
                "department": row.get("department"),
                "deviation_project": row.get("deviation_project"),
                "sign": {
                    "plan": {
                        "start": plan_start,
                        "end": plan_end,
                    },
                    "fact": {
                        "start": fact_start,
                        "end": fact_end,
                    },
                },
                "sign_display": {
                    "fact": {
                        "start": norm_display(row.get("actual_start_project")),
                        "end": norm_display(row.get("actual_end_project")),
                    }
                },
                "bar_plan": calc_bar(plan_start, plan_end, months_list),
                "bar_fact": calc_bar(fact_start, fact_end, months_list),
                "tooltip_plan": (
                    f"Наименование: {project_key}\n"
                    f"Ответственный: {row.get('project_manager')}\n"
                    f"Статус: {row.get('project_status')}\n"
                    f"Начало: {plan_start}\n"
                    f"Окончание: {plan_end}"
                ),
                "tooltip_fact": (
                    f"Наименование: {project_key}\n"
                    f"Ответственный: {row.get('project_manager')}\n"
                    f"Статус: {row.get('project_status')}\n"
                    f"Начало: {norm_display(row.get('actual_start_project'))}\n"
                    f"Окончание: {norm_display(row.get('actual_end_project'))}"
                ),
                "subtasks": [],
                "hierarchy": {},
            }

        project = projects_map[project_key]

        if is_valid_date_val(row.get("start_date")):
            current_start = _conv_to_date_if_dt(row.get("start_date"))
            if global_min is None or current_start < global_min:
                global_min = current_start

        if is_valid_date_val(row.get("end_date")):
            current_end = _conv_to_date_if_dt(row.get("end_date"))
            if global_max is None or current_end > global_max:
                global_max = current_end

        if global_min is not None and global_max is not None:
            if global_min <= today <= global_max:
                today_bar = calc_bar(today, today, months_list)
                if today_bar:
                    today_offset = today_bar.get("offset")

        subtask_plan_start, subtask_plan_end = normalize_actual_dates(
            row.get("subtask_start_date"),
            row.get("subtask_end_date"),
        )

        subtask_fact_start, subtask_fact_end = normalize_actual_dates(
            row.get("actual_start_subtask"),
            row.get("actual_end_subtask"),
        )

        subtask_obj = {
            "subtask_name": row.get("subtask_name"),
            "subtask_responsible": row.get("subtask_responsible"),
            "subtask_status": row.get("subtask_status"),
            "sign": {
                "plan": {
                    "start": subtask_plan_start,
                    "end": subtask_plan_end,
                },
                "fact": {
                    "start": subtask_fact_start,
                    "end": subtask_fact_end,
                },
            },
            "sign_display": {
                "fact": {
                    "start": norm_display(row.get("actual_start_subtask")),
                    "end": norm_display(row.get("actual_end_subtask")),
                }
            },
            "bar_plan": calc_bar(subtask_plan_start, subtask_plan_end, months_list),
            "bar_fact": calc_bar(subtask_fact_start, subtask_fact_end, months_list),
            "tooltip_plan": (
                f"Наименование: {row.get('subtask_name')}\n"
                f"Ответственный: {row.get('subtask_responsible')}\n"
                f"Статус: {row.get('subtask_status')}\n"
                f"Начало: {subtask_plan_start}\n"
                f"Окончание: {subtask_plan_end}"
            ),
            "tooltip_fact": (
                f"Наименование: {row.get('subtask_name')}\n"
                f"Ответственный: {row.get('subtask_responsible')}\n"
                f"Статус: {row.get('subtask_status')}\n"
                f"Начало: {norm_display(row.get('actual_start_subtask'))}\n"
                f"Окончание: {norm_display(row.get('actual_end_subtask'))}"
            ),
        }

        hierarchy_names = []

        for i in range(10, 0, -1):
            hierarchy_name = row.get(f"hier_subtask{i}")

            if hierarchy_name and hierarchy_name != "-":
                hierarchy_names.append((i, hierarchy_name))

        if not hierarchy_names:
            project["subtasks"].append(subtask_obj)
            continue

        current_level = project["hierarchy"]
        last_node = None

        for index, name in hierarchy_names:
            if name not in current_level:
                knot_responsible = row.get(f"knot_responsible{index}")
                knot_start_date = row.get(f"knot_start_date{index}")
                knot_end_date = row.get(f"knot_end_date{index}")
                knot_start_subtask = row.get(f"knot_start_subtask{index}")
                knot_end_subtask = row.get(f"knot_end_subtask{index}")
                knot_status = row.get(f"knot_status{index}")

                knot_plan_start, knot_plan_end = normalize_actual_dates(
                    knot_start_date,
                    knot_end_date,
                )

                knot_fact_start, knot_fact_end = normalize_actual_dates(
                    knot_start_subtask,
                    knot_end_subtask,
                )

                node = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "knot_responsible": knot_responsible,
                    "knot_status": knot_status,
                    "sign": {
                        "plan": {
                            "start": knot_plan_start,
                            "end": knot_plan_end,
                        },
                        "fact": {
                            "start": knot_fact_start,
                            "end": knot_fact_end,
                        },
                    },
                    "sign_display": {
                        "fact": {
                            "start": norm_display(knot_start_subtask),
                            "end": norm_display(knot_end_subtask),
                        }
                    },
                    "bar_plan": calc_bar(knot_plan_start, knot_plan_end, months_list),
                    "bar_fact": calc_bar(knot_fact_start, knot_fact_end, months_list),
                    "tooltip_plan": (
                        f"Наименование: {name}\n"
                        f"Ответственный: {knot_responsible}\n"
                        f"Статус: {knot_status}\n"
                        f"Начало: {knot_plan_start}\n"
                        f"Окончание: {knot_plan_end}"
                    ),
                    "tooltip_fact": (
                        f"Наименование: {name}\n"
                        f"Ответственный: {knot_responsible}\n"
                        f"Статус: {knot_status}\n"
                        f"Начало: {norm_display(knot_start_subtask)}\n"
                        f"Окончание: {norm_display(knot_end_subtask)}"
                    ),
                    "children": {},
                    "subtasks": [],
                }

                current_level[name] = node

            last_node = current_level[name]
            current_level = last_node["children"]

        if last_node is not None:
            last_node["subtasks"].append(subtask_obj)
        else:
            project["subtasks"].append(subtask_obj)

    def hierarchy_dict_to_list(hierarchy_dict):
        result = []

        for name, node in hierarchy_dict.items():
            children = hierarchy_dict_to_list(node["children"])

            result.append({
                "id": node["id"],
                "name": node["name"],
                "knot_responsible": node.get("knot_responsible"),
                "knot_status": node.get("knot_status"),
                "sign": node.get("sign"),
                "sign_display": node.get("sign_display"),
                "bar_plan": node.get("bar_plan"),
                "bar_fact": node.get("bar_fact"),
                "tooltip_plan": node.get("tooltip_plan"),
                "tooltip_fact": node.get("tooltip_fact"),
                "subtasks": node.get("subtasks", []),
                "children": children,
            })

        return result

    result = []

    for project_name, project in projects_map.items():
        plan_sign = project["sign"]["plan"]
        fact_sign = project["sign"]["fact"]

        project["bar_plan"] = calc_bar(
            plan_sign.get("start"),
            plan_sign.get("end"),
            months_list,
        )

        project["bar_fact"] = calc_bar(
            fact_sign.get("start"),
            fact_sign.get("end"),
            months_list,
        )

        result.append({
            "id": project["id"],
            "project_name": project["project_name"],
            "folder_lvl1": project.get("folder_lvl1"),
            "folder_lvl2": project.get("folder_lvl2"),
            "folder_lvl3": project.get("folder_lvl3"),
            "project_manager": project.get("project_manager"),
            "project_status": project.get("project_status"),
            "project_type": project.get("project_type"),
            "department": project.get("department"),
            "deviation_project": project.get("deviation_project"),
            "sign": project.get("sign"),
            "sign_display": project.get("sign_display"),
            "bar_plan": project.get("bar_plan"),
            "bar_fact": project.get("bar_fact"),
            "tooltip_plan": project.get("tooltip_plan"),
            "tooltip_fact": project.get("tooltip_fact"),
            "subtasks": project.get("subtasks"),
            "hierarchy": hierarchy_dict_to_list(project["hierarchy"]),
        })

    result = sort_tree_by_plan_start(result)

    return result, global_min or "", global_max or "", today_offset


def prepare_fb_project_gantt(
    project_start: str | None = None,
    project_end: str | None = None,
) -> dict:
    today = date.today()

    if project_start:
        start_date = datetime.strptime(project_start, "%Y-%m-%d").date()
    else:
        start_date = date(today.year - 1, 1, 1)

    if project_end:
        end_date = datetime.strptime(project_end, "%Y-%m-%d").date()
    else:
        end_date = date(today.year + 1, 12, 31)

    months_list = build_months_list(start_date, end_date)

    rows = prepare_fb_project_rows()
    rows = assign_knot_fields(rows)

    projects_tree, global_min, global_max, today_offset = build_projects_tree(
        rows,
        months_list,
    )

    return {
        "projects_tree": projects_tree,
        "global_min": global_min,
        "global_max": global_max,
        "today_offset": today_offset,
        "months_list": months_list,
    }