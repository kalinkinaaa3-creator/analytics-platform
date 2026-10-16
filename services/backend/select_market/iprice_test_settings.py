"""In-memory contract tests for both iPrice workspaces; never production settings."""
SECRET_KEY = "isolated-iprice-tests-only-not-a-production-secret"
DEBUG = False
USE_TZ = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIDDLEWARE = []
ALLOWED_HOSTS = ["testserver"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["organizations.authentication.OrganizationJWTAuthentication"]}

INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "organizations", "dashboards",
    "select_market.iprice_test_apps.IPriceStorageTestsConfig",
    "select_market.iprice_test_apps.LegacyStorageTestsConfig",
]
ROOT_URLCONF = "select_market.iprice_api"
MIGRATION_MODULES = {name: None for name in ("auth", "contenttypes", "organizations", "dashboards", "select_market", "datasets")}
