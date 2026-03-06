import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Config, SafetyError


class RevenueCatAPIError(Exception):
    def __init__(self, status_code: int, message: str, body: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"RevenueCat API {status_code}: {message}")


class RevenueCatClient:
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

    @property
    def _project_path(self) -> str:
        return f"/projects/{self.config.revenuecat_project_id}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        if method.upper() != "GET" and not self.config.allow_writes:
            raise SafetyError(
                f"Write operation blocked: {method} {path}. Set ALLOW_WRITES=true to allow."
            )

        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, timeout=30, **kwargs)

        # Handle rate limiting
        if resp.status_code == 429:
            import time
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            resp = self.session.request(method, url, timeout=30, **kwargs)

        if resp.status_code >= 400:
            body = None
            try:
                body = resp.json()
            except Exception:
                pass
            raise RevenueCatAPIError(resp.status_code, resp.text[:200], body)

        return resp.json()

    def get_project(self) -> dict:
        return self._request("GET", self._project_path)

    def list_apps(self) -> dict:
        return self._request("GET", f"{self._project_path}/apps")

    def list_products(self, app_id: str) -> dict:
        return self._request("GET", f"{self._project_path}/apps/{app_id}/products")

    def list_offerings(self) -> dict:
        return self._request("GET", f"{self._project_path}/offerings")

    def list_entitlements(self) -> dict:
        return self._request("GET", f"{self._project_path}/entitlements")

    def get_customer(self, customer_id: str) -> dict:
        return self._request("GET", f"{self._project_path}/customers/{customer_id}")
