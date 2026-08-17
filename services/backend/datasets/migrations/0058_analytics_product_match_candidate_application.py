from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("datasets", "0057_analyticsproductclassificationprice_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalyticsProductMatchCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_key_base", models.BigIntegerField(db_index=True)),
                ("product_key_competitor", models.BigIntegerField(db_index=True)),
                ("competitor_source", models.CharField(db_index=True, max_length=50)),
                ("match_score", models.DecimalField(decimal_places=4, max_digits=8)),
                ("match_coverage", models.DecimalField(decimal_places=4, max_digits=8)),
                ("is_eligible", models.BooleanField(db_index=True, default=False)),
                ("threshold_status", models.CharField(blank=True, default="", max_length=100)),
                ("control_reasons", models.JSONField(blank=True, default=list)),
                ("match_evidence", models.JSONField(blank=True, default=dict)),
                ("date_add", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="match_candidates", to="datasets.analyticsproductprocessingrun")),
            ],
            options={"db_table": "analytics_product_match_candidate"},
        ),
        migrations.CreateModel(
            name="AnalyticsProductClassificationApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(blank=True, default="", max_length=255)),
                ("checksum", models.CharField(db_index=True, max_length=64)),
                ("classifications_applied", models.PositiveIntegerField(default=0)),
                ("matches_applied", models.PositiveIntegerField(default=0)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("date_add", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="classification_applications", to="datasets.analyticsproductprocessingrun")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="analytics_product_classification_applications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "analytics_product_classification_application", "ordering": ("-date_add", "-id")},
        ),
        migrations.AddField(
            model_name="analyticsproductmatchcandidate",
            name="application",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="match_candidates", to="datasets.analyticsproductclassificationapplication"),
        ),
        migrations.AddConstraint(
            model_name="analyticsproductmatchcandidate",
            constraint=models.UniqueConstraint(condition=models.Q(application__isnull=True), fields=("run", "product_key_base", "product_key_competitor"), name="analytics_match_candidate_run_pair_uniq"),
        ),
        migrations.AddConstraint(
            model_name="analyticsproductmatchcandidate",
            constraint=models.UniqueConstraint(condition=models.Q(application__isnull=False), fields=("application", "product_key_base", "product_key_competitor"), name="analytics_match_candidate_app_pair_uniq"),
        ),
        migrations.AddIndex(
            model_name="analyticsproductmatchcandidate",
            index=models.Index(fields=["run", "product_key_base", "is_eligible"], name="an_match_run_base_eligible_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsproductmatchcandidate",
            index=models.Index(fields=["run", "competitor_source", "is_eligible"], name="an_match_run_src_eligible_idx"),
        ),
        migrations.AddIndex(
            model_name="analyticsproductmatchcandidate",
            index=models.Index(fields=["application", "product_key_base", "is_eligible"], name="an_match_app_base_eligible_idx"),
        ),
    ]
