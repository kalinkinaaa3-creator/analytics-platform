from datasets.models import DatasetRow


def get_dataset_data(dataset_id: int):

    rows = DatasetRow.objects.filter(
        dataset_id=dataset_id
    )

    return [r.data for r in rows]