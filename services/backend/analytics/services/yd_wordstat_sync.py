from datasets.models import YdWordstatFor
from analytics.clickhouse.repository import ClickHouseRepository


def sync_yd_wordstat_to_clickhouse() -> int:
    rows = list(
        YdWordstatFor.objects.all()
        .order_by("id")
        .values()
    )

    repository = ClickHouseRepository()

    repository.truncate_yd_wordstat_for()
    repository.insert_yd_wordstat_rows(rows)

    return len(rows)