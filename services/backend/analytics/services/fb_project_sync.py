from analytics.clickhouse.repository import ClickHouseRepository
from analytics.services.fb_project_prepare import prepare_fb_project_gantt


def sync_fb_project_to_clickhouse() -> int:
    data = prepare_fb_project_gantt()

    repository = ClickHouseRepository()

    repository.truncate_fb_project()
    repository.insert_fb_project_rows([data])

    return len(data.get("projects_tree", []))