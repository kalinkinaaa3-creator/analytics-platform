from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("datasets", "0069_dataset_organization")]

    operations = [
        migrations.RemoveField(model_name="nomenclaturestock", name="stock"),
        migrations.RemoveField(model_name="nomenclaturestock", name="dev_maximum"),
    ]
