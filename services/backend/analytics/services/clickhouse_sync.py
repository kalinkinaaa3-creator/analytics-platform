from datasets.models import DatasetRow

from analytics.clickhouse.repository import ClickHouseRepository


def sync_dataset_to_clickhouse(dataset_id: int):

    rows = DatasetRow.objects.filter(
        dataset_id=dataset_id
    ).values_list(
        "data",
        flat=True
    )

    rows = list(rows)

    repository = ClickHouseRepository()

    repository.insert_dataset_rows(
        dataset_id=dataset_id,
        rows=rows,
    )

    return len(rows)