# Charts

RevenueCat Charts provide a real-time view of your subscription metrics directly in the RevenueCat dashboard.

## Overview

Charts help you track key metrics like Monthly Recurring Revenue (MRR), Active Subscriptions, Active Trials, Churn, and more. All data is based on production purchase receipts processed through RevenueCat.

## Available Metrics

### Monthly Recurring Revenue (MRR)
MRR represents the normalized monthly revenue from all active subscriptions. Annual subscriptions are divided by 12, weekly subscriptions are multiplied by ~4.33, etc.

### Active Subscriptions
The count of currently active, paid subscriptions. This excludes trials and grace period subscriptions by default.

### Active Trials
The count of users currently in a free trial period.

### Churn Rate
The percentage of subscribers who cancel their subscription in a given period. Calculated as: (Churned Subscribers / Total Subscribers at Start of Period) * 100.

### Revenue
Total revenue recognized in a given period, including new subscriptions, renewals, and one-time purchases.

## Using the Charts API

You can query charts data programmatically using the RevenueCat REST API v2:

```
GET /v2/projects/{project_id}/charts/{metric}
```

Parameters:
- `metric`: One of `mrr`, `revenue`, `active_subscriptions`, `active_trials`, `churn`, `ltv`, `refunds`, `new_customers`, `conversions`
- `start_date`: Start date in YYYY-MM-DD format
- `end_date`: End date in YYYY-MM-DD format
- `resolution`: One of `day`, `week`, `month` (default: `day`)

### Example Response

```json
{
  "metric": "mrr",
  "start_date": "2026-01-01",
  "end_date": "2026-02-01",
  "resolution": "day",
  "values": [
    {"date": "2026-01-01", "value": 12345.67},
    {"date": "2026-01-02", "value": 12389.50}
  ]
}
```

## Important Notes

- Charts data reflects production data only (sandbox excluded)
- All times are UTC
- Historical values may change if refunds occur
- Data may differ from store reports if not all receipts pass through RevenueCat
- Charts were released in their current form in February 2026

## Sources
- [RevenueCat Charts Documentation](https://www.revenuecat.com/docs/dashboard-and-metrics/charts)
- [REST API v2 Reference](https://www.revenuecat.com/docs/api-v2)
