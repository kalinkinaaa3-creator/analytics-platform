from django.conf import settings
from django.db import migrations


def seed(apps, schema_editor):
    db = schema_editor.connection.alias
    Organization = apps.get_model("organizations", "Organization")
    Membership = apps.get_model("organizations", "OrganizationMembership")
    Profile = apps.get_model("organizations", "UserProfile")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    iplast, _ = Organization.objects.using(db).get_or_create(code="iplast", defaults={
        "name": "Ай-Пласт", "theme": "iplast", "postgres_schema": "public",
    })
    select, _ = Organization.objects.using(db).get_or_create(code="select-market", defaults={
        "name": "Селект Маркет", "theme": "select-market", "postgres_schema": "select_market",
        "clickhouse_database": "select_market",
    })
    for user in User.objects.using(db).iterator():
        Profile.objects.using(db).get_or_create(user_id=user.pk, defaults={
            "full_name": " ".join(filter(None, (user.last_name, user.first_name))),
        })
        Membership.objects.using(db).get_or_create(user_id=user.pk, organization_id=iplast.pk, defaults={"is_default": True})
        # Only existing global administrators initially see the new workspace.
        if user.is_superuser:
            Membership.objects.using(db).get_or_create(user_id=user.pk, organization_id=select.pk)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
