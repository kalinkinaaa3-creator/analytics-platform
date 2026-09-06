from collections import defaultdict
from datetime import date

from seo_analytics.models import SeoGoal
from seo_analytics.services.clickhouse import (
    CONVERSION_TABLE,
    LANDING_TABLE,
    PHRASE_TABLE,
    TRAFFIC_TABLE,
    ensure_seo_tables,
)


def _where(filters, supported):
    clauses = ["month >= %(date_from)s", "month <= %(date_to)s"]
    params = {
        "date_from": date.fromisoformat(filters["date_from"]).replace(day=1),
        "date_to": date.fromisoformat(filters["date_to"]).replace(day=1),
    }
    mapping = {
        "device": "device", "search_engine": "search_engine", "region": "region",
        "robotness": "robotness", "phrase_type": "phrase_type",
    }
    for key, column in mapping.items():
        values = tuple(filters.get(key) or ())
        if values and column in supported:
            clauses.append(f"{column} IN %({key})s")
            params[key] = values
    return " AND ".join(clauses), params


def _query(sql, params):
    return ensure_seo_tables().execute(sql, params, with_column_types=True)


def _dicts(sql, params):
    rows, columns = _query(sql, params)
    names = [column[0] for column in columns]
    return [dict(zip(names, row)) for row in rows]


def _quality():
    return [{"sampled": False, "sample_share": None, "data_lag": None, "source": "clickhouse"}]


def _meta(page, filters, loaded_at=None):
    result = {
        "page": page, "date_from": filters["date_from"], "date_to": filters["date_to"],
        "last_updated": loaded_at.isoformat() if loaded_at else None,
        "stale": loaded_at is None,
        "granularity": "month",
    }
    if loaded_at is None:
        result["warning"] = "Для выбранного периода локальная SEO-витрина ещё не загружена."
    return result


def _previous_month(value):
    return date(value.year - 1, 12, 1) if value.month == 1 else date(value.year, value.month - 1, 1)


def _engine_group_expression(filters):
    if filters.get("search_engine"):
        return "search_engine"
    # clickhouse-driver applies Python %-interpolation when query parameters are
    # supplied, so literal percent signs in LIKE patterns must be doubled.
    return "multiIf(lowerUTF8(search_engine) LIKE '%%google%%', 'Google', lowerUTF8(search_engine) LIKE '%%яндекс%%' OR lowerUTF8(search_engine) LIKE '%%yandex%%', 'Яндекс', 'Остальные')"


def _audience(page, filters):
    where, params = _where(filters, {"device", "search_engine", "region", "robotness"})
    engine_group = _engine_group_expression(filters)
    totals = _dicts(
        f"""SELECT sum(visits) visits, sum(pageviews) pageviews, sum(users) users,
                    sum(new_users) new_users, sum(new_visits) new_visits,
                    sum(new_pageviews) new_pageviews, sum(returned_visits) returned_visits,
                    sum(returned_pageviews) returned_pageviews
             FROM {TRAFFIC_TABLE} WHERE {where}""", params,
    )[0]
    loaded_at = _dicts(f"SELECT max(loaded_at) loaded_at FROM {TRAFFIC_TABLE} WHERE {where}", params)[0]["loaded_at"]
    visits, users, new_users = (int(totals.get(key) or 0) for key in ("visits", "users", "new_users"))
    returned = max(0, users - new_users)
    new_visits = int(totals.get("new_visits") or 0)
    new_pageviews = int(totals.get("new_pageviews") or 0)
    returned_visits = int(totals.get("returned_visits") or 0)
    returned_pageviews = int(totals.get("returned_pageviews") or 0)
    pageviews = int(totals.get("pageviews") or 0)
    cards = {
        "visits": visits, "pageviews": pageviews,
        "users": users, "new_users": new_users,
        "returned_users": returned,
        "new_share": new_users * 100 / users if users else 0,
        "returned_share": returned * 100 / users if users else 0,
        "new_visits": new_visits, "new_pageviews": new_pageviews,
        "returned_visits": returned_visits, "returned_pageviews": returned_pageviews,
        "page_depth": pageviews / visits if visits else 0,
    }
    dynamics_rows = _dicts(
        f"""SELECT month, {engine_group} search_engine, sum(visits) visits, sum(users) users,
                    sum(new_users) new_users, sum(pageviews) pageviews,
                    sum(new_visits) new_visits, sum(new_pageviews) new_pageviews,
                    sum(returned_visits) returned_visits, sum(returned_pageviews) returned_pageviews
             FROM {TRAFFIC_TABLE} WHERE {where}
             GROUP BY month, search_engine ORDER BY month, search_engine""", params,
    )
    series = defaultdict(list)
    for row in dynamics_rows:
        row_users = int(row["users"] or 0)
        row_new = int(row["new_users"] or 0)
        row_visits = int(row["visits"] or 0)
        row_pageviews = int(row["pageviews"] or 0)
        series[row["search_engine"]].append({
            "period": row["month"].isoformat(), "visits": row_visits,
            "users": row_users, "new_users": row_new,
            "returned_users": max(0, row_users - row_new),
            "new_share": row_new * 100 / row_users if row_users else 0,
            "returned_share": max(0, row_users - row_new) * 100 / row_users if row_users else 0,
            "page_depth": row_pageviews / row_visits if row_visits else 0,
        })
    dynamics = [{"key": name, "name": name, "points": points} for name, points in series.items()]
    grouped = _dicts(
        f"""SELECT age_interval, gender, sum(visits) visits, sum(users) users,
                    sum(new_users) new_users, sum(pageviews) pageviews
             FROM {TRAFFIC_TABLE} WHERE {where}
             GROUP BY age_interval, gender""", params,
    )
    demographics = []
    for row in grouped:
        row_visits = int(row["visits"] or 0)
        demographics.append({
            "dimensions": [{"name": row["age_interval"]}, {"name": row["gender"]}],
            "visits": row_visits, "users": int(row["users"] or 0),
            "new_users": int(row["new_users"] or 0),
            "page_depth": float(row["pageviews"] or 0) / row_visits if row_visits else 0,
        })
    regions = _dicts(
        f"""SELECT region, sum(visits) visits, sum(users) users, sum(new_users) new_users
             FROM {TRAFFIC_TABLE} WHERE {where} GROUP BY region ORDER BY visits DESC""", params,
    )
    region_rows = [{"dimensions": [{"name": row["region"]}], **row} for row in regions]
    sources = _dicts(
        f"""SELECT search_engine, sum(visits) visits, sum(users) users,
                    sum(new_users) new_users, sum(pageviews) pageviews
             FROM {TRAFFIC_TABLE} WHERE {where} GROUP BY search_engine ORDER BY visits DESC""", params,
    )
    source_rows = []
    for row in sources:
        row_visits, row_users, row_new = int(row["visits"] or 0), int(row["users"] or 0), int(row["new_users"] or 0)
        source_rows.append({"dimensions": [{"name": row["search_engine"]}], **row,
                            "returned_users": max(0, row_users - row_new),
                            "new_share": row_new * 100 / row_users if row_users else 0,
                            "returned_share": max(0, row_users - row_new) * 100 / row_users if row_users else 0,
                            "page_depth": float(row["pageviews"] or 0) / row_visits if row_visits else 0})
    return {"cards": cards, "charts": {"dynamics": dynamics, "demographics": demographics, "regions": region_rows},
            "tables": {"sources": source_rows}, "quality": _quality(), "meta": _meta(page, filters, loaded_at)}


def _phrases(filters):
    where, params = _where(filters, {"search_engine", "robotness", "phrase_type"})
    totals = _dicts(
        f"SELECT sum(visits) visits, sum(pageviews) pageviews, sum(users) users, "
        f"sum(new_users) new_users FROM {PHRASE_TABLE} WHERE {where}", params,
    )[0]
    loaded_at = _dicts(f"SELECT max(loaded_at) loaded_at FROM {PHRASE_TABLE} WHERE {where}", params)[0]["loaded_at"]
    visits, users, new_users = (int(totals.get(key) or 0) for key in ("visits", "users", "new_users"))
    rows = _dicts(
        f"""SELECT search_engine, search_phrase, phrase_type, sum(visits) visits,
                    sum(users) users, sum(new_users) new_users
             FROM {PHRASE_TABLE} WHERE {where}
             GROUP BY search_engine, search_phrase, phrase_type ORDER BY visits DESC LIMIT 10000""", params,
    )
    table_rows = [{"dimensions": [{"name": row["search_engine"]}, {"name": row["search_phrase"]}], **row,
                   "returned_users": max(0, int(row["users"] or 0) - int(row["new_users"] or 0))} for row in rows]
    dynamics = _dicts(
        f"""SELECT month, search_engine, phrase_type, sum(visits) visits, sum(new_users) new_users
             FROM {PHRASE_TABLE} WHERE {where}
             GROUP BY month, search_engine, phrase_type ORDER BY month""", params,
    )
    def series_by(key):
        grouped = defaultdict(list)
        for row in dynamics:
            name = row[key]
            if key == "search_engine" and not filters.get("search_engine"):
                normalized = str(name or "").lower()
                name = "Google" if "google" in normalized else "Яндекс" if "яндекс" in normalized or "yandex" in normalized else "Остальные"
            point = {"period": row["month"].isoformat(), "visits": int(row["visits"] or 0), "new_users": int(row["new_users"] or 0)}
            existing = next((item for item in grouped[name] if item["period"] == point["period"]), None)
            if existing:
                existing["visits"] += point["visits"]
                existing["new_users"] += point["new_users"]
            else:
                grouped[name].append(point)
        return [{"key": name, "name": name, "points": points} for name, points in grouped.items()]
    returned = max(0, users - new_users)
    return {"cards": {"visits": visits, "pageviews": int(totals.get("pageviews") or 0),
                      "users": users, "new_users": new_users, "returned_users": returned,
                      "new_share": new_users * 100 / users if users else 0,
                      "returned_share": returned * 100 / users if users else 0,
                      "page_depth": float(totals.get("pageviews") or 0) / visits if visits else 0},
            "charts": {"engines": series_by("search_engine"), "phrase_types": series_by("phrase_type")},
            "tables": {"phrases": table_rows}, "quality": _quality(), "warnings": [],
            "meta": _meta("search-phrases", filters, loaded_at)}


def _conversions(page, filters):
    where, params = _where(filters, {"device", "search_engine", "region", "phrase_type"})
    goals = list(SeoGoal.objects.filter(is_active=True, is_available=True).order_by("position", "id"))
    metric = "goal_users" if page == "unique-conversions" else "goal_reaches"
    denominator_metric = "users" if page == "unique-conversions" else "visits"
    denominator = _dicts(f"SELECT sum({denominator_metric}) value FROM {CONVERSION_TABLE} WHERE {where} AND goal_id = 0", params)[0]["value"] or 0
    loaded_at = _dicts(f"SELECT max(loaded_at) loaded_at FROM {CONVERSION_TABLE} WHERE {where}", params)[0]["loaded_at"]
    rows = _dicts(
        f"""SELECT goal_id, any(goal_name) goal_name, sum({metric}) value
             FROM {CONVERSION_TABLE} WHERE {where} AND goal_id != 0
             GROUP BY goal_id ORDER BY value DESC""", params,
    )
    by_goal = {int(row["goal_id"]): int(row["value"] or 0) for row in rows}
    goal_cards = [{"id": goal.external_id, "name": goal.name, "value": by_goal.get(goal.external_id, 0)} for goal in goals]
    total = sum(item["value"] for item in goal_cards)
    dynamics_rows = _dicts(
        f"""SELECT month, goal_id, any(goal_name) goal_name, sum({metric}) value
             FROM {CONVERSION_TABLE} WHERE {where} AND goal_id != 0
             GROUP BY month, goal_id ORDER BY month, goal_id""", params,
    )
    grouped = defaultdict(list)
    for row in dynamics_rows:
        grouped[int(row["goal_id"])].append({"period": row["month"].isoformat(), "value": int(row["value"] or 0)})
    periods = sorted({point["period"] for points in grouped.values() for point in points})
    points_by_goal = {goal_id: {point["period"]: point["value"] for point in points} for goal_id, points in grouped.items()}
    denominator_rows = _dicts(
        f"""SELECT month, sum({denominator_metric}) value
             FROM {CONVERSION_TABLE} WHERE {where} AND goal_id = 0
             GROUP BY month ORDER BY month""", params,
    )
    denominator_by_period = {
        row["month"].isoformat(): int(row["value"] or 0)
        for row in denominator_rows
    }
    dynamics = [{"key": "total", "name": "Итого", "points": [
        {"period": period, "denominator": denominator_by_period.get(period, 0), **{str(goal.external_id): points_by_goal.get(goal.external_id, {}).get(period, 0) for goal in goals}}
        for period in periods
    ]}]
    demographics = []
    if page == "unique-conversions":
        demographic_rows = _dicts(
            f"""SELECT age_interval, gender, goal_id, sum(goal_users) value
                 FROM {CONVERSION_TABLE} WHERE {where} AND goal_id != 0
                 GROUP BY age_interval, gender, goal_id
                 ORDER BY age_interval, gender, goal_id""",
            params,
        )
        demographic_map = {}
        for row in demographic_rows:
            key = (row["age_interval"] or "Не определено", row["gender"] or "Не определено")
            item = demographic_map.setdefault(key, {
                "dimensions": [{"name": key[0]}, {"name": key[1]}],
            })
            item[str(int(row["goal_id"]))] = int(row["value"] or 0)
        demographics = list(demographic_map.values())
    return {"cards": {"total": total, "conversion": total * 100 / denominator if denominator else 0,
                      "denominator": int(denominator), "goals": goal_cards},
            "charts": {"dynamics": dynamics, "demographics": demographics}, "tables": {},
            "quality": _quality(), "meta": _meta(page, filters, loaded_at)}


def _landings(filters):
    where, params = _where(filters, {"device", "search_engine", "region"})
    landing_limit = int(filters.get("landing_limit") or 20)
    totals = _dicts(
        f"""SELECT sum(visits) total_visits, uniqExact(landing_url) total_pages
              FROM {LANDING_TABLE} WHERE {where}""", params,
    )[0]
    rows = _dicts(
        f"""SELECT landing_url, sum(visits) visits, sum(users) users,
                    sum(new_users) new_users, sum(pageviews) pageviews
             FROM {LANDING_TABLE} WHERE {where}
             GROUP BY landing_url ORDER BY visits DESC LIMIT {landing_limit}""", params,
    )
    loaded_at = _dicts(f"SELECT max(loaded_at) loaded_at FROM {LANDING_TABLE} WHERE {where}", params)[0]["loaded_at"]
    total_visits = int(totals.get("total_visits") or 0)
    table_rows = []
    for row in rows:
        users, visits = int(row["users"] or 0), int(row["visits"] or 0)
        landing_url = row["landing_url"]
        table_rows.append({**row, "start_url": landing_url,
                           "visits": visits, "dimensions": [{"name": landing_url}],
                           "total_visits": total_visits,
                           "share": visits * 100 / total_visits if total_visits else 0,
                           "new_share": int(row["new_users"] or 0) * 100 / users if users else 0,
                           "page_depth": float(row["pageviews"] or 0) / visits if visits else 0})
    selected_visits = sum(row["visits"] for row in table_rows)
    selected_share = selected_visits * 100 / total_visits if total_visits else 0
    summary = {
        "selected_visits": selected_visits,
        "selected_share": selected_share,
        "total_visits": total_visits,
        "total_pages": int(totals.get("total_pages") or 0),
        "landing_limit": landing_limit,
        # Compatibility with already deployed clients during a rolling update.
        "top20_visits": selected_visits,
        "top20_share": selected_share,
    }
    return {"cards": summary, "charts": {"top": table_rows, "summary": summary}, "tables": {"landing_pages": table_rows},
            "quality": _quality(), "meta": _meta("landing-pages", filters, loaded_at)}


def build_report(page, filters):
    if page in {"visits", "new-visitors", "returning-visitors"}:
        return _audience(page, filters)
    if page == "search-phrases":
        return _phrases(filters)
    if page == "traffic-change":
        report = _audience(page, filters)
        report["charts"] = {"traffic": report["charts"]["dynamics"]}
        first_month = date.fromisoformat(filters["date_from"]).replace(day=1)
        prior_month = _previous_month(first_month)
        prior_filters = {
            **filters,
            "date_from": prior_month.isoformat(),
            "date_to": prior_month.isoformat(),
        }
        prior_where, prior_params = _where(
            prior_filters, {"device", "search_engine", "region", "robotness"}
        )
        prior_rows = _dicts(
            f"""SELECT month, {_engine_group_expression(filters)} search_engine, sum(visits) visits
                 FROM {TRAFFIC_TABLE} WHERE {prior_where}
                 GROUP BY month, search_engine ORDER BY month, search_engine""",
            prior_params,
        )
        report["charts"]["previous_month"] = [
            {
                "key": row["search_engine"],
                "name": row["search_engine"],
                "points": [{"period": row["month"].isoformat(), "visits": int(row["visits"] or 0)}],
            }
            for row in prior_rows
        ]
        comparison_filters = {
            **filters,
            "date_from": date.fromisoformat(filters["date_from"]).replace(
                year=date.fromisoformat(filters["date_from"]).year - 1, day=1
            ).isoformat(),
            "date_to": date.fromisoformat(filters["date_to"]).replace(
                year=date.fromisoformat(filters["date_to"]).year - 1, day=1
            ).isoformat(),
        }
        comparison_where, comparison_params = _where(
            comparison_filters, {"device", "search_engine", "region", "robotness"}
        )
        comparison_rows = _dicts(
            f"""SELECT month, {_engine_group_expression(filters)} search_engine, sum(visits) visits
                 FROM {TRAFFIC_TABLE} WHERE {comparison_where}
                 GROUP BY month, search_engine ORDER BY month, search_engine""",
            comparison_params,
        )
        comparison_series = defaultdict(list)
        for row in comparison_rows:
            comparison_series[row["search_engine"]].append({
                "period": row["month"].isoformat(),
                "visits": int(row["visits"] or 0),
            })
        report["charts"]["comparison"] = [
            {"key": name, "name": name, "points": points}
            for name, points in comparison_series.items()
        ]
        report["tables"] = {"traffic": report["charts"]["traffic"]}
        monthly = defaultdict(int)
        for series in report["charts"]["traffic"]:
            for point in series.get("points") or []:
                monthly[point["period"]] += int(point.get("visits") or 0)
        periods = sorted(monthly)
        current_period = periods[-1] if periods else None
        current_period_date = date.fromisoformat(current_period) if current_period else None
        previous_period = _previous_month(current_period_date).isoformat() if current_period_date else None
        current_year = current_period[:4] if current_period else ""
        previous_year = str(int(current_year) - 1) if current_year else ""
        prior_month_total = sum(int(row["visits"] or 0) for row in prior_rows)
        comparison_monthly = defaultdict(int)
        for row in comparison_rows:
            comparison_monthly[row["month"].isoformat()] += int(row["visits"] or 0)
        current_year_periods = [period for period in periods if period.startswith(current_year)]
        previous_year_period = sum(
            comparison_monthly.get(f"{previous_year}-{period[5:7]}-01", 0)
            for period in current_year_periods
        )
        report["cards"] = {
            "current_month": monthly.get(current_period, 0),
            "previous_month": monthly.get(previous_period, prior_month_total),
            "current_period": sum(value for period, value in monthly.items() if period.startswith(current_year)),
            "previous_year_period": previous_year_period,
        }
        return report
    if page in {"conversions", "unique-conversions"}:
        return _conversions(page, filters)
    if page == "landing-pages":
        return _landings(filters)
    raise ValueError(f"Unsupported SEO page: {page}")
