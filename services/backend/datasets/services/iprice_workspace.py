"""Explicit storage selection. No thread-local routing or live model mutation."""
from dataclasses import dataclass
from django.apps import apps


DATA_MODELS = frozenset("""
DepartureDiscount ParserPrefix ParserProductUrl ParserProductProperty
TaraProductPrice PsProductPrice TtProductPrice ParserProductMatch
IPriceCompetitorSelectionOverride IPriceCompetitorSelectionChange BaseProductPrice
ParserProductClassification Nomenclature NomenclaturePrice TransportCost ProductCost
IPriceCalculationConfig ParserMasterPipelineRun IPriceSnapshot IPriceSnapshotProduct
IPriceSnapshotCompetitor IPriceSnapshotRegion IPriceSnapshotApproval
TaraCoordinator TaraItem TaraRun TaraFetch TaraWorker
""".split())
DASHBOARD_MODELS = frozenset({"IPriceParameterChangeLog", "IPricePriceZoneConfig"})
RETIRED_SELECT_MARKET_MODELS = frozenset({'Nomenclature', 'ProductCost', 'TransportCost', 'DepartureDiscount', 'IPriceCalculationConfig'})


@dataclass(frozen=True)
class IPriceWorkspace:
    code: str

    def __post_init__(self):
        if self.code not in {"iplast", "select-market"}:
            raise ValueError("Unsupported iPrice organization")

    def model(self, name):
        if self.code == 'select-market' and name in RETIRED_SELECT_MARKET_MODELS:
            raise ValueError(f'Retired Select Market source: {name}; use price list and regional inputs')
        if name not in DATA_MODELS | DASHBOARD_MODELS:
            raise ValueError(f"Unsupported iPrice model: {name}")
        label = "select_market" if self.code == "select-market" else "dashboards" if name in DASHBOARD_MODELS else "datasets"
        return apps.get_model(label, name)

    def namespace(self, kind):
        if kind not in {"cache", "events", "files", "runs"}:
            raise ValueError("Unsupported iPrice namespace")
        return f"iprice:{self.code}:{kind}"

    def product_code(self, value):
        if self.code == "select-market":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Select Market product code must be nonempty text")
            if len(value.strip()) > 160:
                raise ValueError("Product code exceeds 160 characters")
            return value.strip()
        if value is None or str(value).strip() == "":
            return None
        return int(value)


def workspace_for(organization):
    expected = {"iplast": "public", "select-market": "select_market"}
    if expected.get(organization.code) != organization.postgres_schema:
        raise ValueError("Organization schema does not match the iPrice storage contract")
    return IPriceWorkspace(organization.code)
