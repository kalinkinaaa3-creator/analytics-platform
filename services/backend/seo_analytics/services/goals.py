from django.db import transaction
from django.utils import timezone

from seo_analytics.models import SeoGoal


def _flatten_goals(goals, parent_id=None, level=0):
    for source in goals or []:
        source = source.get("goal") if isinstance(source, dict) and isinstance(source.get("goal"), dict) else source
        if not isinstance(source, dict) or not source.get("id"):
            continue
        external_id = int(source["id"])
        yield source, parent_id, level
        yield from _flatten_goals(source.get("steps"), external_id, level + 1)


def sync_goal_catalog(client):
    source_goals = list(_flatten_goals(client.goals()))
    now = timezone.now()
    received_ids = []
    created = 0
    updated = 0

    with transaction.atomic():
        for position, (source, parent_id, level) in enumerate(source_goals, 1):
            external_id = int(source["id"])
            if external_id in received_ids:
                continue
            name = str(source.get("name") or f"Цель {external_id}").strip()[:255]
            goal_type = str(source.get("type") or "")[:64]
            goal = SeoGoal.objects.filter(external_id=external_id).first()
            was_created = goal is None
            if was_created:
                goal = SeoGoal.objects.create(
                    external_id=external_id, name=name, source_name=name,
                    is_active=True, is_available=True, source_updated_at=now,
                    position=position * 10, parent_external_id=parent_id,
                    nesting_level=level, goal_type=goal_type,
                )
            else:
                goal.source_name = name
                goal.is_available = True
                goal.source_updated_at = now
                goal.position = position * 10
                goal.parent_external_id = parent_id
                goal.nesting_level = level
                goal.goal_type = goal_type
                goal.save(update_fields=(
                    "source_name", "is_available", "source_updated_at",
                    "position", "parent_external_id", "nesting_level",
                    "goal_type", "date_update",
                ))
            if was_created:
                created += 1
            else:
                updated += 1
            received_ids.append(external_id)

        SeoGoal.objects.exclude(external_id__in=received_ids).update(
            is_available=False,
            is_active=False,
        )

    return {
        "received": len(received_ids),
        "created": created,
        "updated": updated,
    }
