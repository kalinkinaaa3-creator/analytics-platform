from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('select_market', '0016_pricing_method_labels'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='parserproductclassification', name='manual_edit', field=models.BooleanField(default=False)),
        migrations.CreateModel(name='ClassificationChange', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('product_keys', models.JSONField(default=list)), ('before', models.JSONField(default=dict)),
            ('after', models.JSONField(default=dict)), ('reason', models.TextField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('changed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': '"select_market"."classification_change"'}),
    ]
