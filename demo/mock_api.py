"""Mock API responses for demo mode. All data is clearly labeled [DEMO]."""

from advocate.revenuecat.charts import ChartData, CHARTS_CAVEAT

DEMO_BADGE = "[DEMO MODE - Mock data, not real RevenueCat metrics]"


class MockRevenueCatClient:
    """Returns realistic-looking mock responses, all labeled [DEMO]."""

    def get_project(self) -> dict:
        return {
            "id": "proj_demo_001",
            "name": f"revcat-agent-advocate Demo Project {DEMO_BADGE}",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def list_apps(self) -> dict:
        return {
            "items": [
                {"id": "app_demo_ios", "name": f"Demo iOS App {DEMO_BADGE}", "platform": "ios"},
                {"id": "app_demo_android", "name": f"Demo Android App {DEMO_BADGE}", "platform": "android"},
            ]
        }

    def list_products(self, app_id: str = "") -> dict:
        return {
            "items": [
                {"id": "prod_monthly", "name": f"Monthly Premium {DEMO_BADGE}", "price": 9.99},
                {"id": "prod_annual", "name": f"Annual Premium {DEMO_BADGE}", "price": 79.99},
            ]
        }

    def list_offerings(self) -> dict:
        return {
            "items": [
                {"id": "offering_default", "name": f"Default Offering {DEMO_BADGE}", "packages": [
                    {"id": "pkg_monthly", "product_id": "prod_monthly"},
                    {"id": "pkg_annual", "product_id": "prod_annual"},
                ]}
            ]
        }

    def list_entitlements(self) -> dict:
        return {
            "items": [
                {"id": "ent_premium", "name": f"Premium Access {DEMO_BADGE}"},
            ]
        }

    def get_customer(self, customer_id: str = "") -> dict:
        return {
            "id": f"customer_demo_{DEMO_BADGE}",
            "first_seen": "2026-01-15T00:00:00Z",
            "subscriber": {"entitlements": {"premium": {"is_active": True}}},
        }


class MockChartsClient:
    """Returns demo timeseries data."""

    def query_chart(
        self,
        metric="mrr",
        start_date="2026-02-01",
        end_date="2026-03-01",
        resolution="day",
        filters=None,
    ) -> ChartData:
        # Generate synthetic timeseries
        from datetime import datetime, timedelta
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        values = []
        current = start
        base_value = 10000
        while current <= end:
            values.append({
                "date": current.strftime("%Y-%m-%d"),
                "value": round(base_value + (current - start).days * 50, 2),
            })
            current += timedelta(days=1)

        return ChartData(
            metric=str(metric),
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
            values=values,
            filters=filters or {},
        )

    def summarize(self, data: ChartData) -> str:
        lines = [DEMO_BADGE]
        lines.append(f"### {data.metric.replace('_', ' ').title()}")
        if data.values:
            lines.append(f"Range: ${data.values[0]['value']:,.2f} -> ${data.values[-1]['value']:,.2f}")
        lines.append("")
        lines.append(CHARTS_CAVEAT)
        return "\n".join(lines)


class MockMCPClient:
    """Returns mock MCP tool list."""

    MOCK_TOOLS = [
        {"name": "get-project-info", "description": "Get project details"},
        {"name": "list-apps", "description": "List all apps in the project"},
        {"name": "get-app", "description": "Get details for a specific app"},
        {"name": "list-products", "description": "List all products"},
        {"name": "get-product", "description": "Get details for a specific product"},
        {"name": "list-offerings", "description": "List all offerings"},
        {"name": "get-offering", "description": "Get details for a specific offering"},
        {"name": "list-packages", "description": "List all packages in an offering"},
        {"name": "list-entitlements", "description": "List all entitlements"},
        {"name": "get-entitlement", "description": "Get details for a specific entitlement"},
        {"name": "list-subscribers", "description": "List subscribers"},
        {"name": "get-subscriber", "description": "Get subscriber details"},
        {"name": "get-customer", "description": "Get customer info by ID"},
        {"name": "query-charts", "description": "Query charts data for metrics"},
        {"name": "create-entitlement", "description": "Create a new entitlement"},
        {"name": "update-entitlement", "description": "Update an entitlement"},
        {"name": "delete-entitlement", "description": "Delete an entitlement"},
        {"name": "create-offering", "description": "Create a new offering"},
        {"name": "update-offering", "description": "Update an offering"},
        {"name": "delete-offering", "description": "Delete an offering"},
        {"name": "create-package", "description": "Create a new package"},
        {"name": "update-package", "description": "Update a package"},
        {"name": "delete-package", "description": "Delete a package"},
        {"name": "attach-product-to-entitlement", "description": "Attach a product to an entitlement"},
        {"name": "detach-product-from-entitlement", "description": "Detach a product from an entitlement"},
        {"name": "grant-promotional-entitlement", "description": "Grant a promotional entitlement"},
    ]

    def list_tools(self) -> list[dict]:
        return self.MOCK_TOOLS

    def call_tool(self, name: str, params: dict) -> dict:
        return {"result": f"{DEMO_BADGE} Mock result for {name}", "demo": True}
