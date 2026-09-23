import os
import socket
import time
import urllib.parse
import urllib.request

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import connection


TIMEOUT = int(os.getenv("DEPENDENCIES_WAIT_TIMEOUT", "300"))
INTERVAL = int(os.getenv("DEPENDENCIES_WAIT_INTERVAL", "3"))


def check_postgres():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone()[0] == 1


def check_redis():
    with socket.create_connection(("redis", 6379), timeout=5) as sock:
        sock.sendall(b"*1\r\n$4\r\nPING\r\n")
        response = sock.recv(64)
        return b"PONG" in response


def check_clickhouse():
    query = urllib.parse.quote("SELECT 1")
    url = f"http://clickhouse:8123/?query={query}"

    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status == 200 and response.read().strip() == b"1"




CHECKS = {
    "PostgreSQL": check_postgres,
    "Redis": check_redis,
    "ClickHouse": check_clickhouse,
}


def main():
    deadline = time.monotonic() + TIMEOUT

    while True:
        failed = []

        for name, check in CHECKS.items():
            try:
                if not check():
                    failed.append(name)
            except Exception as exc:
                failed.append(f"{name}: {exc}")

        if not failed:
            print("All dependencies are ready.", flush=True)
            return

        if time.monotonic() >= deadline:
            print("Dependencies did not become ready:", flush=True)
            for item in failed:
                print(f" - {item}", flush=True)
            raise SystemExit(1)

        print("Waiting for dependencies:", flush=True)
        for item in failed:
            print(f" - {item}", flush=True)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()