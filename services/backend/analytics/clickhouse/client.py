from clickhouse_driver import Client


def get_clickhouse_client():
    return Client(
        host="clickhouse",
        port=9000,
        user="default",
        password="",
        database="default",
    )