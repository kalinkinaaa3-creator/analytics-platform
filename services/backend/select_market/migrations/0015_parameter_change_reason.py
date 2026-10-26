from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('select_market', '0014_own_product_registry')]
    operations = [
        migrations.AddField(
            model_name='ipriceparameterchangelog', name='reason',
            field=models.TextField(blank=True, default='', verbose_name='Причина изменения'),
        ),
    ]
