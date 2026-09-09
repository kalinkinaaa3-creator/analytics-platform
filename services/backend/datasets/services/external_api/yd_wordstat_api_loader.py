"""Load v2 monthly series; the 'region' source now means IPLAST aggregates."""
import logging
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from datasets.models import (
    YdWordstatPhraseRef, YdWordstatDeviceRef, YdWordstatIplastRegionRef,
    YdWordstatAllRaw, YdWordstatDeviceRaw, YdWordstatIplastRaw,
    YdWordstatApiCheckpoint,
)
from .yd_wordstat_contract import (
    build_iplast_groups, dynamics_body, fingerprint, month_dates,
    parse_monthly_results, validate_group_tree,
)
from .yd_wordstat_load_period import get_reload_period_without_delete, get_previous_month_last_day
from .yd_wordstat_search_api_client import fetch_dynamics, fetch_regions_tree

logger = logging.getLogger("external_api.yd_wordstat")


@dataclass(frozen=True)
class LoadJob:
    source: str
    phrase: str
    feature: str | None
    category: str | None
    dimension: str
    fingerprint: str
    regions: tuple = ()

    @property
    def model(self):
        return {"all": YdWordstatAllRaw, "device": YdWordstatDeviceRaw, "region": YdWordstatIplastRaw}[self.source]

    @property
    def filters(self):
        result = {"phrase": self.phrase}
        if self.source == "device":
            result["device"] = self.dimension
        elif self.source == "region":
            result["macroregion_label"] = self.dimension
        return result

    @property
    def checkpoint_key(self):
        return {"source": self.source, "phrase": self.phrase, "dimension": self.dimension}

    @property
    def devices(self):
        return [self.dimension] if self.source == "device" else ["all"]

    @property
    def data_filters(self):
        result = self.filters
        if self.source == "region":
            result["group_fingerprint"] = self.fingerprint
        return result


def get_configuration():
    phrases = list(YdWordstatPhraseRef.objects.exclude(phrase="").order_by("phrase").values("phrase", "feature", "category"))
    devices = list(YdWordstatDeviceRef.objects.order_by("device").values_list("device", flat=True))
    groups = build_iplast_groups(list(YdWordstatIplastRegionRef.objects.values("region_value", "macroregion_label")))
    if not phrases:
        raise ValueError("Wordstat phrase reference is empty")
    if set(devices) != {"desktop", "phone", "tablet"}:
        raise ValueError("Wordstat device reference must contain desktop, phone and tablet")
    # Validate every phrase before starting any paid requests.
    for item in phrases:
        dynamics_body(item["phrase"], date(2025, 1, 1), date(2025, 1, 31))
    return {"phrases": phrases, "devices": devices, "groups": groups}


def make_jobs(config, source=None):
    sources = [source] if source else ["region", "device", "all"]
    if any(item not in ("all", "device", "region") for item in sources):
        raise ValueError("source must be all, device or region (IPLAST groups)")
    for item in sources:
        for phrase in config["phrases"]:
            if item == "all":
                dimensions = [("", (), fingerprint("v2:all"))]
            elif item == "device":
                dimensions = [(device, (), fingerprint("v2:" + device)) for device in config["devices"]]
            else:
                dimensions = [(group["name"], tuple(group["regions"]), group["fingerprint"]) for group in config["groups"]]
            for dimension, regions, signature in dimensions:
                yield LoadJob(item, phrase["phrase"], phrase["feature"], phrase["category"], dimension, signature, regions)


def checkpoint_is_complete(job, today):
    finish = get_previous_month_last_day(today)
    checkpoint = YdWordstatApiCheckpoint.objects.filter(
        **job.checkpoint_key, fingerprint=job.fingerprint, date_finish=finish,
    ).first()
    if checkpoint is None:
        return False
    # CSV imports or manual changes must not leave a stale checkpoint usable.
    rows = list(job.model.objects.filter(
        **job.data_filters, date__gte=checkpoint.date_start, date__lte=finish,
    ).values_list("date", "count"))
    expected = set(month_dates(checkpoint.date_start, finish))
    return (len(rows) == len(expected) and {day for day, _ in rows} == expected
            and all(count is not None and count >= 0 for _, count in rows))


def job_period(job, today):
    period = get_reload_period_without_delete(job.model, job.data_filters, today=today)
    checkpoint = YdWordstatApiCheckpoint.objects.filter(
        **job.checkpoint_key, fingerprint=job.fingerprint,
    ).first()
    if checkpoint:
        from collections import Counter

        records = list(job.model.objects.filter(
            **job.data_filters, date__gte=checkpoint.date_start, date__lte=checkpoint.date_finish,
        ).values_list("date", "count"))
        counts = Counter(day for day, _ in records)
        invalid = {day for day, count in records if count is None or count < 0}
        broken = [day for day in month_dates(checkpoint.date_start, checkpoint.date_finish)
                  if counts[day] != 1 or day in invalid]
        if broken:
            period["date_start"] = min(period["date_start"], min(broken))
    return period


def load_job(job, today):
    if checkpoint_is_complete(job, today):
        return {"skipped": 1, "saved": 0}
    period = job_period(job, today)
    if period["skipped"]:
        raise ValueError("Unexpected empty Wordstat load period")
    data = fetch_dynamics(
        job.phrase, period["date_start"], period["date_finish"],
        devices=job.devices, regions=list(job.regions) if job.regions else None,
    )
    rows = parse_monthly_results(data, period["date_start"], period["date_finish"])
    objects = []
    for row in rows:
        values = {
            **job.filters, **row, "feature": job.feature, "category": job.category,
        }
        if job.source == "region":
            values["group_fingerprint"] = job.fingerprint
        objects.append(job.model(**values))
    with transaction.atomic():
        # Delete precisely the validated interval, including initial history reloads.
        job.model.objects.filter(
            **job.filters, date__gte=period["date_start"], date__lte=period["date_finish"],
        ).delete()
        job.model.objects.bulk_create(objects, batch_size=5000)
        YdWordstatApiCheckpoint.objects.update_or_create(
            **job.checkpoint_key,
            defaults={
                "fingerprint": job.fingerprint,
                "date_start": period["date_start"],
                "date_finish": period["date_finish"],
            },
        )
    logger.info("Wordstat loaded: source=%s phrase=%s dimension=%s months=%s",
                job.source, job.phrase, job.dimension, len(objects))
    return {"skipped": 0, "saved": len(objects)}


def estimate_load(source=None, today=None):
    """Read local references only; no HTTP, quota reservations or writes."""
    from django.conf import settings

    today = today or timezone.localdate()
    config = get_configuration()
    jobs = list(make_jobs(config, source))
    pending = sum(not checkpoint_is_complete(job, today) for job in jobs)
    quota = settings.YD_WORDSTAT_REQUESTS_PER_HOUR
    if quota < 1:
        raise ValueError("Wordstat hourly quota must be positive")
    return {
        "phrases": len(config["phrases"]), "devices": len(config["devices"]),
        "iplast_groups": [{"name": group["name"], "regions": len(group["regions"])} for group in config["groups"]],
        "requests_full_pass": len(jobs), "requests_pending": pending,
        "quota_per_hour": quota, "estimated_quota_hours": round(pending / quota, 2),
        "target_month": get_previous_month_last_day(today).isoformat(),
    }


def validate_download(config, today):
    missing = [
        job.checkpoint_key for job in make_jobs(config)
        if not checkpoint_is_complete(job, today)
    ]
    return {"ok": not missing, "missing_count": len(missing), "missing_examples": missing[:20]}




def check_regions(config):
    return validate_group_tree(config["groups"], fetch_regions_tree())
