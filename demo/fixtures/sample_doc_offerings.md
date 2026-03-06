# Offerings

Offerings are the primary way to organize and control what in-app products are displayed to users in your app.

## Overview

An Offering is a collection of Packages, and each Package contains a product. This abstraction lets you change what products are shown to users without requiring an app update.

## Key Concepts

### Offerings
- A named group of packages (e.g., "default", "premium_tier")
- One offering is marked as "current" and is shown to users by default
- You can create multiple offerings for A/B testing

### Packages
- A container for a single product within an offering
- Has a package type (e.g., `$rc_monthly`, `$rc_annual`, `$rc_lifetime`, or custom)
- Multiple packages can exist in one offering

### Products
- The actual App Store or Play Store product
- Linked to RevenueCat via product identifiers
- Contains pricing information from the store

## Creating Offerings

### Via Dashboard
1. Navigate to your project in the RevenueCat dashboard
2. Go to Products > Offerings
3. Click "New Offering"
4. Add packages and assign products

### Via REST API v2
```
POST /v2/projects/{project_id}/offerings
{
  "lookup_key": "premium_monthly",
  "display_name": "Premium Monthly"
}
```

### Via MCP Server
```python
result = await session.call_tool("create-offering", {
    "project_id": "proj_xxx",
    "lookup_key": "premium_monthly",
    "display_name": "Premium Monthly"
})
```

## Fetching Offerings in Your App

```swift
// iOS
Purchases.shared.getOfferings { offerings, error in
    if let current = offerings?.current {
        // Display packages to the user
        for package in current.availablePackages {
            print(package.localizedPriceString)
        }
    }
}
```

```kotlin
// Android
Purchases.sharedInstance.getOfferingsWith(
    onError = { error -> /* handle error */ },
    onSuccess = { offerings ->
        offerings.current?.availablePackages?.forEach { pkg ->
            println(pkg.product.price)
        }
    }
)
```

## Best Practices

1. Always use the "current" offering for your default paywall
2. Create separate offerings for A/B testing different product configurations
3. Use descriptive lookup_keys for offerings (e.g., "annual_discount_50")
4. Test offering changes in sandbox before applying to production

## Sources
- [Offerings Documentation](https://www.revenuecat.com/docs/offerings)
- [Paywalls Documentation](https://www.revenuecat.com/docs/paywalls)
