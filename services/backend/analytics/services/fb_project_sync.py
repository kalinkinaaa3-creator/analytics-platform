from datasets.models import FbProject
from analytics.clickhouse.repository import ClickHouseRepository


def sync_fb_project_to_clickhouse() -> int:
    rows = list(
        FbProject.objects.all()
        .order_by("id")
        .values()
    )

    repository = ClickHouseRepository()

    repository.truncate_fb_project()
    repository.insert_fb_project_rows(rows)

    return len(rows)