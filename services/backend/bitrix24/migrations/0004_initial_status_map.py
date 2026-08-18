from django.db import migrations


INITIAL_STATUSES = (
    ("NEW", "unprocessed", "Не обработан", False, False, False, False, 10),
    ("IN_PROCESS", "assigned", "Назначен", False, False, True, False, 20),
    ("UC_BL6VX8", "in_progress", "В работе", False, False, True, False, 30),
    ("CONVERTED", "converted", "Конвертирован", False, False, True, True, 40),
    ("5", "converted", "Передано в Айпласт Маркет", True, False, True, True, 50),
)


def add_initial_statuses(apps, schema_editor):
    status_map = apps.get_model("bitrix24", "BitrixDashboardStatusMap")
    for (
        status_id,
        dashboard_status,
        display_name,
        is_apm,
        is_low_quality,
        is_processed,
        is_final,
        sort,
    ) in INITIAL_STATUSES:
        status_map.objects.update_or_create(
            entity_id="STATUS",
            status_id=status_id,
            defaults={
                "dashboard_status": dashboard_status,
                "display_name": display_name,
                "is_apm": is_apm,
                "is_low_quality": is_low_quality,
                "is_processed": is_processed,
                "is_final": is_final,
                "is_active": True,
                "sort": sort,
            },
        )


def remove_initial_statuses(apps, schema_editor):
    status_map = apps.get_model("bitrix24", "BitrixDashboardStatusMap")
    status_map.objects.filter(
        entity_id="STATUS",
        status_id__in=[item[0] for item in INITIAL_STATUSES],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bitrix24", "0003_bitrixleadanalytics_and_more"),
    ]

    operations = [
        migrations.RunPython(add_initial_statuses, remove_initial_statuses),
    ]
