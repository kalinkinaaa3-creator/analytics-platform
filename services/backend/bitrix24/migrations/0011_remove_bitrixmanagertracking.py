from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("bitrix24", "0010_bitrixuserdepartmentpreference")]

    operations = [
        migrations.DeleteModel(name="BitrixManagerTracking"),
    ]
