from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import BaseModel

from ..config import Config


class ChartsMetric(str, Enum):
    MRR = "mrr"
    ARR = "arr"
    REVENUE = "revenue"
    ACTIVE_SUBSCRIPTIONS = "active_subscriptions"
    ACTIVE_TRIALS = "active_trials"
    CHURN = "churn"
    LTV = "ltv"
    REFUNDS = "refunds"
    NEW_CUSTOMERS = "new_customers"
    CONVERSIONS = "conversions"


class ChartData(BaseModel):
    metric: str
    start_date: str
    end_date: str
    resolution: str = "day"
    values: list[dict] = []
    filters: dict = {}


CHARTS_CAVEAT = (
    "Note: Charts data is based on current purchase receipt snapshots "
    "and reflects production data only (sandbox excluded). "
    "All times are UTC. Historical values may change if refunds occur. "
    "Data may differ from store reports if not all receipts pass through RevenueCat."
)


class ChartsClient:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = "https://api.revenuecat.com/v2"
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {config.revenuecat_api_key}"
        self.session.headers["Content-Type"] = "application/json"

        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def query_chart(
        self,
        metric: ChartsMetric | str,
        start_date: str,
        end_date: str,
        resolution: str = "day",
        filters: dict | None = None,
    ) -> ChartData:
        metric_str = metric.value if isinstance(metric, ChartsMetric) else metric
        project_id = self.config.revenuecat_project_id

        params = {
            "start_date": start_date,
            "end_date": end_date,
            "resolution": resolution,
        }
        if filters:
            params.update(filters)

        resp = self.session.get(
            f"{self.base_url}/projects/{project_id}/charts/{metric_str}",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        return ChartData(
            metric=metric_str,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
            values=data.get("values", data.get("data", [])),
            filters=filters or {},
        )

    def summarize(self, data: ChartData) -> str:
        """Generate a human-readable markdown summary of chart data."""
        lines = [f"### {data.metric.replace('_', ' ').title()}"]
        lines.append(f"Period: {data.start_date} to {data.end_date} ({data.resolution})")

        if data.values:
            first = data.values[0].get("value", "N/A")
            last = data.values[-1].get("value", "N/A")
            lines.append(f"Range: {first} -> {last}")
            lines.append(f"Data points: {len(data.values)}")
        else:
            lines.append("No data available.")

        lines.append("")
        lines.append(CHARTS_CAVEAT)
        return "\n".join(lines)
