from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0061_alter_dashsales_cost"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="parserproductclassification",
            name="parser_class_type_status_idx",
        ),
        migrations.RemoveField(
            model_name="parserproductclassification",
            name="match_type",
        ),
        migrations.AddField(
            model_name="parserproductclassification",
            name="article_number_analogs",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=255,
                null=True,
                verbose_name="Артикул группы аналогов",
            ),
        ),
        migrations.DeleteModel(name="AnalyticsProductMatchCandidate"),
        migrations.DeleteModel(name="AnalyticsProductClassificationApplication"),
        migrations.DeleteModel(name="AnalyticsProductAnalysisResult"),
        migrations.DeleteModel(name="AnalyticsProductProcessingRun"),
        migrations.DeleteModel(name="AnalyticsProductClassificationScoreWeight"),
        migrations.DeleteModel(name="AnalyticsProductMatchingScoreWeight"),
        migrations.DeleteModel(name="AnalyticsProductClassificationScoreProfile"),
        migrations.DeleteModel(name="AnalyticsProductMatchingScoreProfile"),
        migrations.DeleteModel(name="AnalyticsProductClassificationPrice"),
        migrations.DeleteModel(name="AnalyticsProductClassificationProperty"),
        migrations.DeleteModel(name="AnalyticsProductClassificationPriority"),
        migrations.DeleteModel(name="AnalyticsProductSourcePriority"),
        migrations.DeleteModel(name="AnalyticsProductScoringThreshold"),
        migrations.DeleteModel(name="AnalyticsProductModificationRule"),
        migrations.DeleteModel(name="AnalyticsProductManyToManyRule"),
        migrations.DeleteModel(name="AnalyticsProductNumericalMetric"),
        migrations.DeleteModel(name="AnalyticsProductManualProperty"),
        migrations.DeleteModel(name="AnalyticsProductPriceRule"),
        migrations.DeleteModel(name="AnalyticsProductPropertyRule"),
        migrations.DeleteModel(name="AnalyticsProductDirectoryLoad"),
    ]
