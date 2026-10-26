from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('select_market', '0015_parameter_change_reason')]
    operations = [
        migrations.AlterField(
            model_name='ipricesnapshotproduct', name='pricing_method',
            field=models.CharField(choices=[('analog', 'По рынку'), ('exclusive', 'По себестоимости')],
                                   db_index=True, max_length=20, verbose_name='Метод ценообразования'),
        ),
        migrations.AlterField(
            model_name='ipricesnapshotregion', name='base_exclusive',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True,
                                      verbose_name='Маржа по себестоимости'),
        ),
    ]
