from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('select_market', '0013_price_assortment_matrix_status')]
    operations = [
        migrations.AddField(model_name='parserproducturl', name='own_code', field=models.CharField(max_length=160, blank=True, null=True, db_index=True)),
        migrations.AddField(model_name='parserproducturl', name='in_price', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='parserproducturl', name='on_website', field=models.BooleanField(default=False)),
        migrations.AlterField(model_name='parserproducturl', name='url', field=models.URLField(max_length=1000, blank=True, null=True, verbose_name='URL с префиксом')),
        migrations.RemoveConstraint(model_name='parserproducturl', name='sm_parser_product_url_e394bf'),
        migrations.AddConstraint(model_name='parserproducturl', constraint=models.UniqueConstraint(fields=['source', 'url', 'additional_property'], condition=models.Q(url__isnull=False), nulls_distinct=False, name='sm_parser_product_url_e394bf')),
        migrations.AddConstraint(model_name='parserproducturl', constraint=models.UniqueConstraint(fields=['own_code'], condition=models.Q(source='base', own_code__isnull=False), name='sm_own_product_code_unique')),
    ]
