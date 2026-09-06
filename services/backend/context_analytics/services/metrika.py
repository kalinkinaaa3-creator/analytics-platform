import logging

from context_analytics.models import ContextApiRequestLog
from seo_analytics.services.client import MetrikaClient


logger = logging.getLogger("context_analytics.metrika")


class ContextMetrikaClient(MetrikaClient):
    """Metrika transport with context-specific cache and request audit."""

    cache_prefix = "context:metrika:v1"
    logger = logger

    @staticmethod
    def _log(*, endpoint, report_key, params, status_code, duration_ms, payload, success, error=""):
        try:
            ContextApiRequestLog.objects.create(
                endpoint=endpoint,
                report_key=report_key,
                params=params,
                status_code=status_code,
                duration_ms=duration_ms,
                success=success,
                error=error[:10000],
            )
        except Exception:
            logger.exception("Failed to persist context Metrika request log")
