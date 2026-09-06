"""Compatibility imports for callers of the former v1 client."""
from .yd_wordstat_search_api_client import (
    YdWordstatSearchApiError as YdWordstatApiError,
    fetch_dynamics as fetch_yd_wordstat_dynamics,
    fetch_regions_tree as fetch_yd_wordstat_regions_tree,
)
