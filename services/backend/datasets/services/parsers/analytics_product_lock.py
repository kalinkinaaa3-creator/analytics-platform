from contextlib import contextmanager

from django.db import connection


# Stable project-scoped PostgreSQL advisory lock. It serializes replacement of
# directory rules, background processing and manual classification application.
ANALYTICS_PRODUCT_OPERATION_LOCK_ID = 7_421_905_117


@contextmanager
def analytics_product_operation_lock():
    if connection.vendor != "postgresql":
        yield
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_lock(%s)",
            [ANALYTICS_PRODUCT_OPERATION_LOCK_ID],
        )
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                [ANALYTICS_PRODUCT_OPERATION_LOCK_ID],
            )
