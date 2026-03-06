# Authentication

RevenueCat uses API keys to authenticate requests to the REST API and SDKs.

## API Key Types

### Secret API Keys (sk_)
Secret API keys are used for server-to-server communication with the REST API v2. These keys have full read and write access to your project.

**Important**: Never expose secret API keys in client-side code, public repositories, or anywhere accessible to end users.

### App-Specific API Keys (atk_)
App-specific API keys are used by the RevenueCat SDKs in your mobile and web applications. These keys are safe to include in client-side code as they are scoped to a single app.

## Using API Keys

### REST API v2 Authentication
All REST API v2 requests require a Bearer token in the Authorization header:

```
Authorization: Bearer sk_your_secret_key_here
```

### SDK Configuration
Configure the SDK with your app-specific API key:

```swift
// iOS
Purchases.configure(withAPIKey: "atk_your_app_key")
```

```kotlin
// Android
Purchases.configure(PurchasesConfiguration.Builder(context, "atk_your_app_key").build())
```

```dart
// Flutter
await Purchases.configure(PurchasesConfiguration("atk_your_app_key"));
```

## Project IDs

Each RevenueCat project has a unique project ID (format: `proj_xxxxx`). This ID is required for REST API v2 endpoints:

```
GET /v2/projects/{project_id}/apps
GET /v2/projects/{project_id}/offerings
```

## Rate Limits

The REST API v2 enforces rate limits:
- 120 requests per minute per API key
- When rate limited, the API returns HTTP 429 with a `Retry-After` header

## Best Practices

1. Store API keys in environment variables, not in code
2. Use secret keys (sk_) only on your server
3. Use app-specific keys (atk_) in client applications
4. Rotate keys periodically through the RevenueCat dashboard
5. Monitor API usage in the dashboard for unusual patterns

## Sources
- [RevenueCat Authentication Documentation](https://www.revenuecat.com/docs/projects/authentication)
- [REST API v2 Reference](https://www.revenuecat.com/docs/api-v2)
