from django.apps import AppConfig, apps
from django.db import connection


class IPriceStorageTestsConfig(AppConfig):
    name = "select_market"

    def ready(self):
        if connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
            raise RuntimeError("Test mappings require in-memory SQLite")
        for label in ("select_market", "datasets"):
            for model in apps.get_app_config(label).get_models():
                model._meta.db_table = f"test_{label}_{model._meta.model_name}"


class LegacyStorageTestsConfig(AppConfig):
    # No ingestion signals or external connections in isolated storage tests.
    name = "datasets"
