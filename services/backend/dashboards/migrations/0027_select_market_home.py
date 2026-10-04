from django.db import migrations


def seed(apps, schema_editor):
    db = schema_editor.connection.alias
    Organization = apps.get_model("organizations", "Organization")
    Dashboard = apps.get_model("dashboards", "Dashboard")
    organization = Organization.objects.using(db).get(code="select-market")
    for order, (code, name) in enumerate([
        ("sps", "Система прогнозирования спроса"), ("suc", "Система управления ценой"),
    ]):
        Dashboard.objects.using(db).get_or_create(organization_id=organization.pk, slug=code, defaults={
            "name": name, "display_name": name, "component": code, "menu_icon": code,
            "menu_group": "Системы", "menu_order": order,
        })


class Migration(migrations.Migration):
    dependencies = [("dashboards", "0026_dashboard_component_dashboard_display_name_and_more")]
    # Removing workspaces can destroy assigned permissions; rollback is a restore
    # from backup, not an automatic reverse data migration.
    operations = [migrations.RunPython(seed)]
