"""Isolated acceptance database. Never imports production credentials/settings."""
import os
from .iprice_test_settings import *  # noqa: F403

INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'organizations', 'dashboards',
                  'select_market', 'select_market.iprice_test_apps.LegacyStorageTestsConfig']
MIGRATION_MODULES = {}
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'postgres',
    'USER': os.environ.get('IPRICE_TEST_USER', 'postgres'),
    'PASSWORD': os.environ.get('IPRICE_TEST_PASSWORD', ''),
    'HOST': os.environ.get('IPRICE_TEST_HOST', '127.0.0.1'),
    'PORT': os.environ.get('IPRICE_TEST_PORT', '5432'),
    'TEST': {'NAME': 'test_iprice_acceptance'},
}}
