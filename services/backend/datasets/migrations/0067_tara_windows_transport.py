from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('datasets', '0066_tara_session_jobs')]
    operations = [
        migrations.RemoveField(model_name='tararun', name='session'),
        migrations.DeleteModel(name='TaraSession'),
        migrations.CreateModel(name='TaraWorker', fields=[
            ('key', models.PositiveSmallIntegerField(primary_key=True, default=1, serialize=False)),
            ('owner', models.CharField(max_length=64, default='')),
            ('heartbeat', models.DateTimeField(null=True)),
            ('ready', models.BooleanField(default=False)),
        ]),
        migrations.CreateModel(name='TaraFetch', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('run_lease', models.CharField(max_length=64)),
            ('url', models.TextField()),
            ('status', models.CharField(max_length=16, default='pending', db_index=True)),
            ('token', models.CharField(max_length=64, default='')),
            ('payload', models.JSONField(default=dict)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('expires_at', models.DateTimeField()),
            ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fetches', to='datasets.tararun')),
        ]),
    ]
