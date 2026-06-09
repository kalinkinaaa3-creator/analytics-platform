import csv

from datasets.models import Dataset
from datasets.models import DatasetRow


def load_csv(dataset: Dataset):

    path = dataset.source_file.path

    rows_to_create = []

    with open(
        path,
        mode="r",
        encoding="utf-8",
        newline=""
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        for row in reader:

            rows_to_create.append(
                DatasetRow(
                    dataset=dataset,
                    data=row
                )
            )

    DatasetRow.objects.bulk_create(
        rows_to_create,
        batch_size=1000
    )