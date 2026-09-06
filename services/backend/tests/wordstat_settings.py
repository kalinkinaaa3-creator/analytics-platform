"""Isolated Wordstat tests: in-memory SQLite, no app startup integrations."""
from django.apps import AppConfig


class DatasetsTestConfig(AppConfig):
    name = "datasets"
    default_auto_field = "django.db.models.BigAutoField"


SECRET_KEY = "wordstat-local-test-only"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "tests.wordstat_settings.DatasetsTestConfig"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Europe/Moscow"
YD_WORDSTAT_API_KEY = "test-key"
YD_WORDSTAT_FOLDER_ID = "test-folder"
YD_WORDSTAT_API_BASE_URL = "https://searchapi.api.cloud.yandex.net/v2/wordstat"
YD_WORDSTAT_API_MAX_ATTEMPTS = 3
YD_WORDSTAT_REQUESTS_PER_SECOND = 10
YD_WORDSTAT_REQUESTS_PER_HOUR = 100
YD_WORDSTAT_API_CONNECT_TIMEOUT = 10
YD_WORDSTAT_API_TIMEOUT = 60
YD_WORDSTAT_V2_LOAD_ENABLED = False
