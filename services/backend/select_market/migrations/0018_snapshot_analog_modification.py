from django.db import migrations, models


def populate(apps, schema_editor):
    Classification = apps.get_model('select_market', 'ParserProductClassification')
    Product = apps.get_model('select_market', 'IPriceSnapshotProduct')
    source = Classification.objects.using(schema_editor.connection.alias).filter(
        product_key=models.OuterRef('base_product_key')).values('article_number_analogs')[:1]
    Product.objects.using(schema_editor.connection.alias).update(article_number_analogs=models.Subquery(source))


class Migration(migrations.Migration):
    dependencies = [('select_market', '0017_classification_editor')]
    operations = [
        migrations.AddField(model_name='ipricesnapshotproduct', name='article_number_analogs',
            field=models.CharField(max_length=255, null=True, blank=True, verbose_name='Модификация (группа аналогов)')),
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
