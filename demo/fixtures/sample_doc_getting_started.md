# Getting Started with RevenueCat

RevenueCat provides a backend and SDK for managing in-app purchases and subscriptions across iOS, Android, and web platforms.

## Quick Start

1. **Create a RevenueCat account** at https://app.revenuecat.com
2. **Create a project** in the RevenueCat dashboard
3. **Add your apps** (iOS, Android, Stripe, etc.)
4. **Configure products** in your app store and link them in RevenueCat
5. **Install the SDK** in your app
6. **Configure offerings** to control what products are shown to users

## Installing the SDK

### iOS (Swift)
```swift
// In your Podfile
pod 'RevenueCat'

// Or with SPM, add:
// https://github.com/RevenueCat/purchases-ios.git
```

### Android (Kotlin)
```kotlin
// In your app/build.gradle
implementation 'com.revenuecat.purchases:purchases:7.0.0'
```

### Flutter
```yaml
# In pubspec.yaml
dependencies:
  purchases_flutter: ^6.0.0
```

## SDK Configuration

Initialize the SDK as early as possible in your app lifecycle:

```swift
// iOS
import RevenueCat
Purchases.configure(withAPIKey: "atk_your_app_key")
```

```kotlin
// Android
import com.revenuecat.purchases.Purchases
import com.revenuecat.purchases.PurchasesConfiguration

Purchases.configure(
    PurchasesConfiguration.Builder(this, "atk_your_app_key").build()
)
```

## Configuring Products

Products are configured in two places:
1. **App Store / Play Store**: Create the actual product with pricing
2. **RevenueCat Dashboard**: Link the store product to RevenueCat

### Product Types
- **Subscriptions**: Auto-renewing subscriptions (weekly, monthly, yearly)
- **Non-Consumables**: One-time purchases that persist (e.g., lifetime access)
- **Consumables**: One-time purchases that can be bought multiple times

## Next Steps

- Set up [Offerings](https://www.revenuecat.com/docs/offerings) to organize your products
- Configure [Paywalls](https://www.revenuecat.com/docs/paywalls) for in-app purchase UI
- Review [Entitlements](https://www.revenuecat.com/docs/entitlements) for access control
- Explore the [REST API v2](https://www.revenuecat.com/docs/api-v2) for server-side integration

## Sources
- [RevenueCat Welcome](https://www.revenuecat.com/docs/welcome)
- [Installation Guide](https://www.revenuecat.com/docs/getting-started/installation)
- [Configuring Products](https://www.revenuecat.com/docs/getting-started/configuring-products)
