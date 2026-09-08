"""Offline CRM regression tests, without external integrations."""
SECRET_KEY = "crm-local-tests"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "bitrix24"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Europe/Moscow"
