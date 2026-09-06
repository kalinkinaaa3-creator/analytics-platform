from datetime import date, timedelta
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from context_analytics.models import ContextCampaign

from context_analytics.services.clickhouse import (
    CRITERIA_GOAL_TABLE, CRITERIA_TABLE, GOAL_TABLE, PERFORMANCE_TABLE, VISITOR_TABLE, ensure_tables,
)
from seo_analytics.models import SeoGoal


SUPPORTED_PAGES = {"summary", "weekly", "lead_structure", "conversions", "criteria", "demography", "devices"}
CACHE_VERSION = "v11"


def normalize_query(params):
    today = timezone.localdate()
    campaigns = [int(value) for value in params.getlist("campaigns") if str(value).isdigit()]
    ad_groups = [int(value) for value in params.getlist("ad_groups") if str(value).isdigit()]
    criteria = [int(value) for value in params.getlist("criteria") if str(value).isdigit()]
    campaign_types = [str(value) for value in params.getlist("campaign_types") if value]
    day_types = [value for value in params.getlist("day_types") if value in {"workdays", "weekends"}]
    if ad_groups:
        # The UI exposes unique group names. Expand its representative ID to every
        # ad-group ID carrying the same displayed name, as requested by the report.
        ch = ensure_tables()
        names = [row[0] for row in ch.execute(
            f"SELECT DISTINCT ad_group_name FROM {PERFORMANCE_TABLE} WHERE ad_group_id IN %(ad_groups)s",
            {"ad_groups": tuple(ad_groups)},
        )]
        if names:
            ad_groups = sorted(int(row[0]) for row in ch.execute(
                f"SELECT DISTINCT ad_group_id FROM {PERFORMANCE_TABLE} WHERE ad_group_name IN %(ad_group_names)s",
                {"ad_group_names": tuple(names)},
            ))
    if campaign_types:
        matching = set(ContextCampaign.objects.filter(campaign_type__in=campaign_types, is_available=True)
                       .values_list("external_id", flat=True))
        campaigns = sorted(matching.intersection(campaigns) if campaigns else matching)
        if not campaigns:
            campaigns = [-1]
    result = {
        "date_from": params.get("date_from") or today.replace(month=1, day=1).isoformat(),
        "date_to": params.get("date_to") or (today - timedelta(days=1)).isoformat(),
        "campaigns": campaigns,
        "ad_groups": ad_groups,
        "criteria": criteria,
        "campaign_types": campaign_types,
        "day_types": day_types or ["workdays", "weekends"],
        "granularity": "day" if params.get("granularity") == "day" else "week",
    }
    if date.fromisoformat(result["date_from"]) > date.fromisoformat(result["date_to"]):
        raise ValueError("Дата начала не может быть позже даты окончания.")
    return result


def _where(filters, alias="", include_criteria=False, include_ad_groups=True):
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}date BETWEEN %(date_from)s AND %(date_to)s"]
    params = {"date_from": filters["date_from"], "date_to": filters["date_to"]}
    if filters["campaigns"]:
        clauses.append(f"{prefix}campaign_id IN %(campaigns)s")
        params["campaigns"] = tuple(filters["campaigns"])
    if include_ad_groups and filters["ad_groups"]:
        clauses.append(f"{prefix}ad_group_id IN %(ad_groups)s")
        params["ad_groups"] = tuple(filters["ad_groups"])
    if include_criteria and filters["criteria"]:
        clauses.append(f"{prefix}criterion_id IN %(criteria)s")
        params["criteria"] = tuple(filters["criteria"])
    if filters["day_types"] == ["workdays"]:
        clauses.append(f"toDayOfWeek({prefix}date) BETWEEN 1 AND 5")
    elif filters["day_types"] == ["weekends"]:
        clauses.append(f"toDayOfWeek({prefix}date) IN (6,7)")
    return " AND ".join(clauses), params


def _active_goals():
    return list(SeoGoal.objects.filter(is_active=True, is_available=True).order_by("position", "id"))


def _goal_config_version():
    value = SeoGoal.objects.aggregate(updated=Max("date_update"))["updated"]
    return value.isoformat() if value else "empty"


def _cache_key(page, filters):
    payload = {"page": page, "filters": filters, "goals": _goal_config_version()}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"context:report:{CACHE_VERSION}:{page}:{digest}"


def _goal_where(filters):
    where, params = _where(filters)
    goals = _active_goals()
    if goals:
        where += " AND goal_id IN %(goal_ids)s"
        params["goal_ids"] = tuple(goal.external_id for goal in goals)
    else:
        where += " AND 0"
    return where, params, goals


def _metrics(ch, filters):
    where, params = _where(filters)
    row = ch.execute(f"""SELECT sum(impressions),sum(clicks),toFloat64(sum(cost)),sum(sessions),sum(bounces),
      sumIf(sessions,isNotNull(bounces)),
      if(sum(sessions)=0,0,sum(avg_pageviews*sessions)/sum(sessions)),
      if(sumIf(impressions,avg_impression_position>0)=0,NULL,
         sum(ifNull(avg_impression_position,0)*impressions)/sumIf(impressions,avg_impression_position>0)),
      if(sumIf(clicks,avg_click_position>0)=0,NULL,
         sum(ifNull(avg_click_position,0)*clicks)/sumIf(clicks,avg_click_position>0)),max(loaded_at)
      FROM {PERFORMANCE_TABLE} WHERE {where}""", params)[0]
    goal_where, goal_params, _ = _goal_where(filters)
    leads = ch.execute(f"SELECT sum(conversions) FROM {GOAL_TABLE} WHERE {goal_where}", goal_params)[0][0] or 0
    # The visitor fact has no ad-group dimension. Do not either reference a missing
    # column or silently show campaign-wide visitors as if they were group-filtered.
    if filters["ad_groups"]:
        users, new_users = None, None
    else:
        visitor_where, visitor_params = _where(filters, include_ad_groups=False)
        # A zero campaign ID represents visitor rows that Metrika could not
        # attribute to a concrete Direct campaign. Exclude those rows only from
        # the returning-users KPI; performance and conversion metrics keep their
        # existing scope.
        visitor_where += " AND campaign_id != 0"
        users, new_users = ch.execute(
            f"SELECT sum(users),sum(new_users) FROM {VISITOR_TABLE} WHERE {visitor_where}", visitor_params
        )[0]
    impressions, clicks, cost, sessions, bounces, bounce_sessions, depth, avg_imp, avg_click, updated = row
    return {"impressions": int(impressions or 0), "clicks": int(clicks or 0), "cost": float(cost or 0),
            "visits": int(sessions or 0), "users": int(users) if users is not None else None,
            "new_users": int(new_users) if new_users is not None else None,
            "returning_users": max(0, int(users) - int(new_users)) if users is not None and new_users is not None else None,
            "leads": int(leads),
            "ctr": float(clicks or 0) * 100 / impressions if impressions else None,
            "cpc": float(cost or 0) / clicks if clicks else None,
            "cr": float(leads) * 100 / clicks if clicks else None,
            "cpl": float(cost or 0) / leads if leads else None,
            "bounce_rate": float(bounces or 0) * 100 / bounce_sessions if bounce_sessions else None,
            "page_depth": float(depth or 0),
            "avg_impression_position": float(avg_imp) if avg_imp is not None else None,
            "avg_click_position": float(avg_click) if avg_click is not None else None,
            "last_updated": updated}


def _criteria_metrics(ch, filters, base):
    where, params = _where(filters, include_criteria=True)
    row = ch.execute(f"""SELECT sum(impressions),sum(clicks),toFloat64(sum(cost)),sum(sessions),sum(bounces),
      sumIf(sessions,isNotNull(bounces)),
      if(sum(sessions)=0,0,sum(avg_pageviews*sessions)/sum(sessions)),
      if(sumIf(impressions,avg_impression_position>0)=0,NULL,
         sum(ifNull(avg_impression_position,0)*impressions)/sumIf(impressions,avg_impression_position>0)),
      if(sumIf(clicks,avg_click_position>0)=0,NULL,
         sum(ifNull(avg_click_position,0)*clicks)/sumIf(clicks,avg_click_position>0))
      FROM {CRITERIA_TABLE} WHERE {where}""", params)[0]
    goal_where, goal_params = _where(filters, include_criteria=True)
    goals = _active_goals()
    if goals:
        goal_where += " AND goal_id IN %(goal_ids)s"
        goal_params["goal_ids"] = tuple(goal.external_id for goal in goals)
    else:
        goal_where += " AND 0"
    leads = ch.execute(f"SELECT sum(conversions) FROM {CRITERIA_GOAL_TABLE} WHERE {goal_where}", goal_params)[0][0] or 0
    impressions, clicks, cost, visits, bounces, bounce_sessions, depth, avg_imp, avg_click = row
    return {**base, "impressions": int(impressions or 0), "clicks": int(clicks or 0),
            "cost": float(cost or 0), "visits": int(visits or 0), "leads": int(leads),
            "ctr": float(clicks or 0) * 100 / impressions if impressions else None,
            "cpc": float(cost or 0) / clicks if clicks else None,
            "cr": float(leads) * 100 / clicks if clicks else None,
            "cpl": float(cost or 0) / leads if leads else None,
            "bounce_rate": float(bounces or 0) * 100 / bounce_sessions if bounce_sessions else None,
            "page_depth": float(depth or 0),
            "avg_impression_position": float(avg_imp) if avg_imp is not None else None,
            "avg_click_position": float(avg_click) if avg_click is not None else None}


def _series(ch, filters, dimensions):
    where, params = _where(filters)
    dims = ",".join(dimensions)
    rows = ch.execute(
        f"""SELECT {dims},sum(impressions),sum(clicks),toFloat64(sum(cost)),sum(sessions),sum(bounces),
        sumIf(sessions,isNotNull(bounces)),
        sumIf(impressions,avg_impression_position>0),
        sumIf(clicks,avg_click_position>0),
        if(sumIf(impressions,avg_impression_position>0)=0,NULL,
           sum(ifNull(avg_impression_position,0)*impressions)/sumIf(impressions,avg_impression_position>0)),
        if(sumIf(clicks,avg_click_position>0)=0,NULL,
           sum(ifNull(avg_click_position,0)*clicks)/sumIf(clicks,avg_click_position>0))
        FROM {PERFORMANCE_TABLE} WHERE {where} GROUP BY {dims} ORDER BY {dims}""",
        params,
    )
    keys = [item.rsplit(" AS ", 1)[-1] for item in dimensions] + [
        "impressions", "clicks", "cost", "visits", "bounces", "bounce_sessions",
        "position_impressions", "position_clicks",
        "avg_impression_position", "avg_click_position",
    ]
    result = []
    for row in rows:
        dimensions_row, values = row[:-10], row[-10:]
        (impressions, clicks, cost, visits, bounces, bounce_sessions, position_impressions,
         position_clicks, avg_impression, avg_click) = values
        result.append(dict(zip(keys, (*dimensions_row, int(impressions), int(clicks), float(cost),
                                       int(visits or 0), int(bounces or 0), int(bounce_sessions or 0),
                                       int(position_impressions or 0), int(position_clicks or 0),
                                       float(avg_impression) if avg_impression is not None else None,
                                       float(avg_click) if avg_click is not None else None))))
    return result


def _breakdown(ch, filters, dimensions):
    rows = _series(ch, filters, dimensions)
    keys = [item.rsplit(" AS ", 1)[-1] for item in dimensions]
    goal_where, params, _ = _goal_where(filters)
    dims = ",".join(dimensions)
    goal_rows = ch.execute(f"SELECT {dims},sum(conversions) FROM {GOAL_TABLE} WHERE {goal_where} GROUP BY {dims}", params)
    leads = {tuple(row[:-1]): int(row[-1]) for row in goal_rows}
    for row in rows:
        row["leads"] = leads.get(tuple(row[key] for key in keys), 0)
        row["ctr"] = row["clicks"] * 100 / row["impressions"] if row["impressions"] else None
        row["cpc"] = row["cost"] / row["clicks"] if row["clicks"] else None
        row["bounce_rate"] = row["bounces"] * 100 / row["bounce_sessions"] if row["bounce_sessions"] else None
        row["cr"] = row["leads"] * 100 / row["clicks"] if row["clicks"] else None
        row["cpl"] = row["cost"] / row["leads"] if row["leads"] else None
    return rows


def _conversion_breakdown(ch, filters):
    """Return one campaign/ad-group matrix built from this page's own filtered slice."""
    where, params = _where(filters)
    base_rows = ch.execute(
        f"""SELECT campaign_id,any(campaign_name),ad_group_id,any(ad_group_name),
          sum(clicks),toFloat64(sum(cost)) FROM {PERFORMANCE_TABLE}
          WHERE {where} GROUP BY campaign_id,ad_group_id ORDER BY 2,4""",
        params,
    )
    goal_where, goal_params, goals = _goal_where(filters)
    goal_rows = ch.execute(
        f"""SELECT campaign_id,ad_group_id,goal_id,sum(conversions) FROM {GOAL_TABLE}
          WHERE {goal_where} GROUP BY campaign_id,ad_group_id,goal_id""",
        goal_params,
    )
    by_group = {}
    totals = {str(goal.external_id): 0 for goal in goals}
    for campaign_id, ad_group_id, goal_id, conversions in goal_rows:
        value = int(conversions or 0)
        by_group[(campaign_id, ad_group_id, str(goal_id))] = value
        totals[str(goal_id)] = totals.get(str(goal_id), 0) + value
    rows = []
    for campaign_id, campaign_name, ad_group_id, ad_group_name, clicks, cost in base_rows:
        values = {str(goal.external_id): by_group.get((campaign_id, ad_group_id, str(goal.external_id)), 0)
                  for goal in goals}
        leads = sum(values.values())
        click_count, cost_value = int(clicks or 0), float(cost or 0)
        rows.append({
            "campaign_id": campaign_id, "campaign_name": campaign_name,
            "ad_group_id": ad_group_id, "ad_group_name": ad_group_name,
            "clicks": click_count, "cost": cost_value, "goals": values, "leads": leads,
            "cr": leads * 100 / click_count if click_count else None,
            "cpl": cost_value / leads if leads else None,
        })
    configured = [{"id": goal.external_id, "name": goal.name} for goal in goals]
    goal_totals = [{"id": goal.external_id, "name": goal.name,
                    "leads": totals.get(str(goal.external_id), 0)} for goal in goals]
    return configured, goal_totals, rows


def _daily_campaign_rows(ch, filters):
    """Campaign/ad-group facts for exports, without changing report-page granularity."""
    where, params = _where(filters)
    base_rows = ch.execute(
        f"""SELECT date,campaign_id,any(campaign_name),ad_group_id,any(ad_group_name),
          sum(impressions),sum(clicks),toFloat64(sum(cost)),sum(sessions),sum(bounces),
          sumIf(sessions,isNotNull(bounces)),
          sumIf(impressions,avg_impression_position>0),
          sumIf(clicks,avg_click_position>0),
          if(sumIf(impressions,avg_impression_position>0)=0,NULL,
             sum(ifNull(avg_impression_position,0)*impressions)/sumIf(impressions,avg_impression_position>0)),
          if(sumIf(clicks,avg_click_position>0)=0,NULL,
             sum(ifNull(avg_click_position,0)*clicks)/sumIf(clicks,avg_click_position>0))
          FROM {PERFORMANCE_TABLE} WHERE {where}
          GROUP BY date,campaign_id,ad_group_id ORDER BY date,campaign_id,ad_group_id""",
        params,
    )
    goal_where, goal_params, _ = _goal_where(filters)
    leads = {
        (row[0], row[1], row[2]): int(row[3] or 0)
        for row in ch.execute(
            f"SELECT date,campaign_id,ad_group_id,sum(conversions) FROM {GOAL_TABLE} "
            f"WHERE {goal_where} GROUP BY date,campaign_id,ad_group_id",
            goal_params,
        )
    }
    result = []
    for row in base_rows:
        day, campaign_id, campaign_name, ad_group_id, ad_group_name = row[:5]
        (impressions, clicks, cost, visits, bounces, bounce_sessions, position_impressions,
         position_clicks, avg_imp, avg_click) = row[5:]
        lead_count = leads.get((day, campaign_id, ad_group_id), 0)
        result.append({
            "date": day, "campaign_id": campaign_id, "campaign_name": campaign_name,
            "ad_group_id": ad_group_id, "ad_group_name": ad_group_name,
            "impressions": int(impressions or 0), "clicks": int(clicks or 0),
            "ctr": float(clicks or 0) * 100 / impressions if impressions else None,
            "cpc": float(cost or 0) / clicks if clicks else None,
            "bounces": int(bounces or 0),
            "bounce_sessions": int(bounce_sessions or 0),
            "position_impressions": int(position_impressions or 0),
            "position_clicks": int(position_clicks or 0),
            "bounce_rate": float(bounces or 0) * 100 / bounce_sessions if bounce_sessions else None,
            "avg_impression_position": float(avg_imp) if avg_imp is not None else None,
            "avg_click_position": float(avg_click) if avg_click is not None else None,
            "cost": float(cost or 0),
            "visits": int(visits or 0), "leads": lead_count,
            "cr": lead_count * 100 / clicks if clicks else None,
            "cpl": float(cost or 0) / lead_count if lead_count else None,
        })
    return result


def get_export_report(page, filters):
    """Return complete daily rows for Excel while keeping get_report aggregated for the UI."""
    ch = ensure_tables()
    if page == "summary":
        return {"campaigns": _daily_campaign_rows(ch, filters)}
    if page == "weekly":
        return {"weekly": _breakdown(ch, filters, ["date"])}
    if page in {"lead_structure", "conversions"}:
        base_rows = _daily_campaign_rows(ch, filters)
        goal_where, goal_params, goals = _goal_where(filters)
        goal_values = {
            (row[0], row[1], row[2], str(row[3])): int(row[4] or 0)
            for row in ch.execute(
                f"SELECT date,campaign_id,ad_group_id,goal_id,sum(conversions) FROM {GOAL_TABLE} "
                f"WHERE {goal_where} GROUP BY date,campaign_id,ad_group_id,goal_id",
                goal_params,
            )
        }
        for row in base_rows:
            values = {str(goal.external_id): goal_values.get(
                (row["date"], row["campaign_id"], row["ad_group_id"], str(goal.external_id)), 0
            ) for goal in goals}
            row["goals"] = values
            row["leads"] = sum(values.values())
            row["cr"] = row["leads"] * 100 / row["clicks"] if row["clicks"] else None
            row["cpl"] = row["cost"] / row["leads"] if row["leads"] else None
        return {
            "configured_goals": [{"id": goal.external_id, "name": goal.name} for goal in goals],
            "campaign_groups": base_rows,
        }
    if page == "devices":
        return {"rows": _breakdown(ch, filters, ["date", "device"])}
    if page == "demography":
        return {"rows": _breakdown(ch, filters, ["date", "gender", "age"])}
    if page == "criteria":
        where, params = _where(filters, include_criteria=True)
        base_rows = ch.execute(
            f"""SELECT date,campaign_id,any(campaign_name),ad_group_id,any(ad_group_name),
              criterion_id,any(criterion),criterion_type,sum(impressions),sum(clicks),toFloat64(sum(cost))
              FROM {CRITERIA_TABLE} WHERE {where}
              GROUP BY date,campaign_id,ad_group_id,criterion_id,criterion_type
              ORDER BY date,campaign_id,ad_group_id,criterion_id""",
            params,
        )
        goal_where, goal_params = _where(filters, include_criteria=True)
        goals = _active_goals()
        if goals:
            goal_where += " AND goal_id IN %(goal_ids)s"
            goal_params["goal_ids"] = tuple(goal.external_id for goal in goals)
        else:
            goal_where += " AND 0"
        leads = {
            (row[0], row[1], row[2], row[3], row[4]): int(row[5] or 0)
            for row in ch.execute(
                f"SELECT date,campaign_id,ad_group_id,criterion_id,criterion_type,sum(conversions) "
                f"FROM {CRITERIA_GOAL_TABLE} WHERE {goal_where} "
                "GROUP BY date,campaign_id,ad_group_id,criterion_id,criterion_type",
                goal_params,
            )
        }
        rows = []
        for raw in base_rows:
            day, campaign_id, campaign_name, ad_group_id, ad_group_name = raw[:5]
            criterion_id, criterion, criterion_type, impressions, clicks, cost = raw[5:]
            lead_count = leads.get((day, campaign_id, ad_group_id, criterion_id, criterion_type), 0)
            rows.append({
                "date": day, "campaign_id": campaign_id, "campaign": campaign_name,
                "ad_group_id": ad_group_id, "ad_group": ad_group_name,
                "criterion_id": criterion_id, "criterion": criterion,
                "criterion_type": criterion_type, "impressions": int(impressions or 0),
                "clicks": int(clicks or 0),
                "ctr": float(clicks or 0) * 100 / impressions if impressions else None,
                "cpc": float(cost or 0) / clicks if clicks else None, "cost": float(cost or 0),
                "leads": lead_count, "cr": lead_count * 100 / clicks if clicks else None,
                "cpl": float(cost or 0) / lead_count if lead_count else None,
            })
        return {"rows": rows}
    return {}


def iter_criteria_export_rows(filters):
    """Stream the largest export without materializing criteria and leads in Python."""
    ch = ensure_tables()
    base_where, params = _where(filters, include_criteria=True)
    goal_where, goal_params = _where(filters, include_criteria=True)
    goals = _active_goals()
    if goals:
        goal_where += " AND goal_id IN %(goal_ids)s"
        goal_params["goal_ids"] = tuple(goal.external_id for goal in goals)
    else:
        goal_where += " AND 0"
    params.update(goal_params)
    rows = ch.execute_iter(
        f"""SELECT b.date,b.campaign_id,b.campaign_name,b.ad_group_id,b.ad_group_name,
          b.criterion_id,b.criterion,b.criterion_type,b.impressions,b.clicks,b.cost,
          ifNull(g.leads,0)
          FROM (
            SELECT date,campaign_id,any(campaign_name) campaign_name,
              ad_group_id,any(ad_group_name) ad_group_name,criterion_id,
              any(criterion) criterion,criterion_type,sum(impressions) impressions,
              sum(clicks) clicks,toFloat64(sum(cost)) cost
            FROM {CRITERIA_TABLE} WHERE {base_where}
            GROUP BY date,campaign_id,ad_group_id,criterion_id,criterion_type
          ) b
          LEFT JOIN (
            SELECT date,campaign_id,ad_group_id,criterion_id,criterion_type,
              sum(conversions) leads
            FROM {CRITERIA_GOAL_TABLE} WHERE {goal_where}
            GROUP BY date,campaign_id,ad_group_id,criterion_id,criterion_type
          ) g USING (date,campaign_id,ad_group_id,criterion_id,criterion_type)
          ORDER BY b.date,b.campaign_id,b.ad_group_id,b.criterion_id""",
        params,
        settings={"max_block_size": 10_000},
    )
    for raw in rows:
        (day, campaign_id, campaign_name, ad_group_id, ad_group_name,
         criterion_id, criterion, criterion_type, impressions, clicks, cost, leads) = raw
        impressions = int(impressions or 0)
        clicks = int(clicks or 0)
        cost = float(cost or 0)
        leads = int(leads or 0)
        yield {
            "date": day, "campaign_id": campaign_id, "campaign": campaign_name,
            "ad_group_id": ad_group_id, "ad_group": ad_group_name,
            "criterion_id": criterion_id, "criterion": criterion,
            "criterion_type": criterion_type, "impressions": impressions,
            "clicks": clicks, "ctr": clicks * 100 / impressions if impressions else None,
            "cpc": cost / clicks if clicks else None, "cost": cost, "leads": leads,
            "cr": leads * 100 / clicks if clicks else None,
            "cpl": cost / leads if leads else None,
        }


def get_options(filters=None):
    if filters is not None:
        return _dependent_options(filters)
    cached = cache.get("context:filter-options:v4")
    if cached is not None:
        return cached
    ch = ensure_tables()
    campaigns = ch.execute(f"SELECT campaign_id,any(campaign_name) FROM {PERFORMANCE_TABLE} GROUP BY campaign_id ORDER BY 2")
    ad_groups = ch.execute(
        f"SELECT min(ad_group_id),ad_group_name FROM {PERFORMANCE_TABLE} "
        "WHERE ad_group_name!='' GROUP BY ad_group_name ORDER BY ad_group_name"
    )
    criteria = ch.execute(f"SELECT criterion_id,any(criterion) FROM {CRITERIA_TABLE} WHERE criterion!='' GROUP BY criterion_id ORDER BY 2")
    types = ch.execute(f"SELECT DISTINCT campaign_type FROM {PERFORMANCE_TABLE} WHERE campaign_type!='' ORDER BY 1")
    bounds = ch.execute(
        f"SELECT minOrNull(date),maxOrNull(date),maxOrNull(loaded_at) FROM {PERFORMANCE_TABLE}"
    )[0]
    result = {"campaigns": [{"id": item[0], "name": item[1]} for item in campaigns],
              "ad_groups": [{"id": item[0], "name": item[1]} for item in ad_groups],
              "criteria": [{"id": item[0], "name": "Автотаргетинг" if item[1] == "---autotargeting" else item[1]} for item in criteria],
              "campaign_types": [item[0] for item in types],
              "data_range": {"min_date": bounds[0], "max_date": bounds[1]}, "last_updated": bounds[2]}
    cache.set("context:filter-options:v4", result, timeout=settings.CONTEXT_REPORT_CACHE_TIMEOUT)
    return result


def _option_where(filters, skip, include_criteria=False):
    clauses = ["date BETWEEN %(date_from)s AND %(date_to)s"]
    params = {"date_from": filters["date_from"], "date_to": filters["date_to"]}
    mapping = {"campaigns": "campaign_id", "ad_groups": "ad_group_id"}
    if include_criteria:
        mapping["criteria"] = "criterion_id"
    for key, column in mapping.items():
        values = tuple(filters.get(key) or ())
        if key != skip and values:
            clauses.append(f"{column} IN %({key})s")
            params[key] = values
    campaign_types = tuple(filters.get("campaign_types") or ())
    if skip != "campaign_types" and campaign_types:
        clauses.append("campaign_type IN %(campaign_types)s")
        params["campaign_types"] = campaign_types
    if filters["day_types"] == ["workdays"]:
        clauses.append("toDayOfWeek(date) BETWEEN 1 AND 5")
    elif filters["day_types"] == ["weekends"]:
        clauses.append("toDayOfWeek(date) IN (6,7)")
    return " AND ".join(clauses), params


def _dependent_options(filters):
    ch = ensure_tables()
    campaign_where, campaign_params = _option_where(filters, "campaigns")
    type_where, type_params = _option_where(filters, "campaign_types")
    group_where, group_params = _option_where(filters, "ad_groups")
    criterion_where, criterion_params = _option_where(filters, "criteria", include_criteria=True)
    campaigns = ch.execute(
        f"SELECT campaign_id,any(campaign_name) FROM {PERFORMANCE_TABLE} WHERE {campaign_where} "
        "GROUP BY campaign_id ORDER BY 2", campaign_params,
    )
    campaign_types = ch.execute(
        f"SELECT DISTINCT campaign_type FROM {PERFORMANCE_TABLE} WHERE {type_where} "
        "AND campaign_type!='' ORDER BY campaign_type", type_params,
    )
    ad_groups = ch.execute(
        f"SELECT min(ad_group_id),ad_group_name FROM {PERFORMANCE_TABLE} WHERE {group_where} "
        "AND ad_group_name!='' GROUP BY ad_group_name ORDER BY ad_group_name", group_params,
    )
    criteria = ch.execute(
        f"SELECT criterion_id,any(criterion) FROM {CRITERIA_TABLE} WHERE {criterion_where} "
        "AND criterion!='' GROUP BY criterion_id ORDER BY 2", criterion_params,
    )
    bounds = ch.execute(
        f"SELECT minOrNull(date),maxOrNull(date),maxOrNull(loaded_at) FROM {PERFORMANCE_TABLE}"
    )[0]
    return {
        "campaigns": [{"id": item[0], "name": item[1]} for item in campaigns],
        "ad_groups": [{"id": item[0], "name": item[1]} for item in ad_groups],
        "criteria": [{"id": item[0], "name": "Автотаргетинг" if item[1] == "---autotargeting" else item[1]} for item in criteria],
        "campaign_types": [item[0] for item in campaign_types],
        "data_range": {"min_date": bounds[0], "max_date": bounds[1]}, "last_updated": bounds[2],
    }


def get_report(page, filters):
    key = _cache_key(page, filters)
    cached = cache.get(key)
    if cached is not None:
        return cached
    ch = ensure_tables()
    result = {"page": page, "summary": _metrics(ch, filters), "warnings": []}
    if page == "criteria":
        result["summary"] = _criteria_metrics(ch, filters, result["summary"])
    if page in {"summary", "weekly"}:
        period = "date AS period" if filters["granularity"] == "day" else "toMonday(date) AS period"
        result["weekly"] = _breakdown(ch, filters, [period])
        result["campaigns"] = _series(
            ch, filters,
            ["campaign_id", "campaign_name", "ad_group_id", "ad_group_name"],
        )
        goal_where, goal_params, _ = _goal_where(filters)
        campaign_leads = {
            (row[0], row[1]): row[2]
            for row in ch.execute(
                f"SELECT campaign_id,ad_group_id,sum(conversions) FROM {GOAL_TABLE} "
                f"WHERE {goal_where} GROUP BY campaign_id,ad_group_id",
                goal_params,
            )
        }
        for row in result["campaigns"]:
            row["leads"] = int(campaign_leads.get((row["campaign_id"], row["ad_group_id"]), 0))
            row["ctr"] = row["clicks"] * 100 / row["impressions"] if row["impressions"] else None
            row["cpc"] = row["cost"] / row["clicks"] if row["clicks"] else None
            row["bounce_rate"] = row["bounces"] * 100 / row["bounce_sessions"] if row["bounce_sessions"] else None
            row["cr"] = row["leads"] * 100 / row["clicks"] if row["clicks"] else None
            row["cpl"] = row["cost"] / row["leads"] if row["leads"] else None
    elif page == "devices":
        result["rows"] = _breakdown(ch, filters, ["device"])
        result["coverage"] = _coverage(result["rows"], result["summary"])
    elif page == "demography":
        result["rows"] = _breakdown(ch, filters, ["gender", "age"])
        result["coverage"] = _coverage(result["rows"], result["summary"])
    elif page in {"lead_structure", "conversions"}:
        configured, goal_totals, campaign_groups = _conversion_breakdown(ch, filters)
        result["configured_goals"] = configured
        result["goals"] = goal_totals
        result["campaign_groups"] = campaign_groups
    elif page == "criteria":
        where, params = _where(filters, include_criteria=True)
        rows = ch.execute(f"""SELECT campaign_id,any(campaign_name),ad_group_id,any(ad_group_name),
          criterion_id,any(criterion),criterion_type,sum(impressions),sum(clicks),toFloat64(sum(cost))
          FROM {CRITERIA_TABLE} WHERE {where}
          GROUP BY campaign_id,ad_group_id,criterion_id,criterion_type
          ORDER BY sum(clicks) DESC""", params)
        result["rows"] = [{"campaign_id": int(r[0]), "campaign": r[1], "ad_group_id": int(r[2]),
                           "ad_group": r[3], "criterion_id": int(r[4]), "criterion": r[5],
                           "criterion_type": r[6], "impressions": int(r[7]), "clicks": int(r[8]),
                           "cost": float(r[9])} for r in rows]
        goal_where, goal_params, _ = _goal_where(filters)
        if filters["criteria"]:
            goal_where += " AND criterion_id IN %(criteria)s"
            goal_params["criteria"] = tuple(filters["criteria"])
        criterion_leads = {
            (row[0], row[1], row[2], row[3]): int(row[4])
            for row in ch.execute(
                f"SELECT campaign_id,ad_group_id,criterion_id,criterion_type,sum(conversions) "
                f"FROM {CRITERIA_GOAL_TABLE} WHERE {goal_where} "
                "GROUP BY campaign_id,ad_group_id,criterion_id,criterion_type",
                goal_params,
            )
        }
        for row in result["rows"]:
            row["leads"] = criterion_leads.get((row["campaign_id"], row["ad_group_id"],
                                                  row["criterion_id"], row["criterion_type"]), 0)
            row["ctr"] = row["clicks"] * 100 / row["impressions"] if row["impressions"] else None
            row["cpc"] = row["cost"] / row["clicks"] if row["clicks"] else None
            row["cr"] = row["leads"] * 100 / row["clicks"] if row["clicks"] else None
            row["cpl"] = row["cost"] / row["leads"] if row["leads"] else None
        distributed = int(ch.execute(f"SELECT sum(clicks) FROM {CRITERIA_TABLE} WHERE {where}", params)[0][0] or 0)
        total = result["summary"]["clicks"]
        result["coverage"] = distributed * 100 / total if total else None
    result["meta"] = {"last_updated": result["summary"].pop("last_updated")}
    cache.set(key, result, timeout=settings.CONTEXT_REPORT_CACHE_TIMEOUT)
    return result


def _coverage(rows, summary):
    checks = {}
    for key in ("impressions", "clicks", "cost", "visits", "leads"):
        detailed = sum(float(row.get(key) or 0) for row in rows)
        total = float(summary.get(key) or 0)
        checks[key] = {"total": total, "detailed": detailed,
                       "difference": detailed - total,
                       "coverage": detailed * 100 / total if total else None}
    return checks
