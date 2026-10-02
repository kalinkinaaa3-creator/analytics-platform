"""Serialize 1C price/stock day replacements across all entry points."""
import logging
from functools import wraps

from django.db import connection


# Separate from the commercial-price publication lock (83100427).
LOCK_ID = 83100428
logger = logging.getLogger("sales_calculator")


def serialized_nomenclature_day(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        day = kwargs.get("load_date", args[0] if args else None)
        logger.info("Waiting for shared 1C load lock: loader=%s date=%s", function.__name__, day)
        # Session lock: do not keep a database transaction open during the HTTP
        # request. The existing day transaction still commits before unlocking.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_ID])
        logger.info("Acquired shared 1C load lock: loader=%s date=%s", function.__name__, day)
        try:
            return function(*args, **kwargs)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
            logger.info("Released shared 1C load lock: loader=%s date=%s", function.__name__, day)
    return wrapped
