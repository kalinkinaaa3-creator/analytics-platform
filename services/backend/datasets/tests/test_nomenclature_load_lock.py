from datetime import date
from threading import Event, Lock, Thread
from unittest import TestCase
from unittest.mock import Mock, patch

from datasets.services.external_api import nomenclature_load_lock as locks
from datasets.services.external_api.price_api_loader import load_price_day
from datasets.services.external_api.stock_api_loader import load_stock_day


class NomenclatureLoadLockTests(TestCase):
    def test_both_loaders_lock_before_api_and_unlock_on_failure(self):
        for loader, module, fetch in (
            (load_price_day, "price_api_loader", "fetch_price_api_rows"),
            (load_stock_day, "stock_api_loader", "fetch_stock_api_rows"),
        ):
            events = []
            cursor = Mock()
            cursor.execute.side_effect = lambda sql, params: events.append((sql, params))
            def failed_request(day):
                events.append("request")
                raise ValueError("API failed")
            with patch.object(locks, "connection") as connection, patch(
                f"datasets.services.external_api.{module}.{fetch}", side_effect=failed_request
            ):
                connection.cursor.return_value.__enter__.return_value = cursor
                with self.assertRaisesRegex(ValueError, "API failed"):
                    loader(date(2026, 10, 2))
            self.assertEqual(events, [
                ("SELECT pg_advisory_lock(%s)", [locks.LOCK_ID]), "request",
                ("SELECT pg_advisory_unlock(%s)", [locks.LOCK_ID]),
            ])

    def test_unlock_after_success_and_preserve_result(self):
        cursor = Mock()
        @locks.serialized_nomenclature_day
        def load_day(load_date):
            self.assertEqual(cursor.execute.call_count, 1)
            return {"saved": 5}
        with patch.object(locks, "connection") as connection:
            connection.cursor.return_value.__enter__.return_value = cursor
            self.assertEqual(load_day(load_date=date(2026, 10, 2)), {"saved": 5})
        self.assertEqual(cursor.execute.call_count, 2)

    def test_second_load_waits_until_first_releases(self):
        # Model PostgreSQL's blocking lock with a thread lock, without real APIs.
        mutex = Lock()
        first_running, second_waiting, release_first = Event(), Event(), Event()
        events, errors = [], []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params):
                if "pg_advisory_lock" in sql:
                    if mutex.locked(): second_waiting.set()
                    if not mutex.acquire(timeout=5): raise TimeoutError("test lock")
                else:
                    mutex.release()
        @locks.serialized_nomenclature_day
        def first(day):
            events.append("first start")
            first_running.set()
            if not release_first.wait(5): raise TimeoutError("test release")
            events.append("first commit")
        @locks.serialized_nomenclature_day
        def second(day): events.append("second start")
        def run(loader):
            try: loader(date(2026, 10, 2))
            except Exception as exc: errors.append(exc)
        with patch.object(locks, "connection") as connection:
            connection.cursor.side_effect = Cursor
            a, b = Thread(target=run, args=(first,)), Thread(target=run, args=(second,))
            a.start()
            try:
                self.assertTrue(first_running.wait(5))
                b.start()
                self.assertTrue(second_waiting.wait(5))
                self.assertEqual(events, ["first start"])
            finally:
                release_first.set()
                a.join(5)
                if b.ident is not None: b.join(5)
        self.assertFalse(errors)
        self.assertEqual(events, ["first start", "first commit", "second start"])
