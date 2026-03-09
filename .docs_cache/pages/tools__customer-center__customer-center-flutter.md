---
id: "tools/customer-center/customer-center-flutter"
title: "Integrating Customer Center on Flutter"
description: "Installation"
permalink: "/docs/tools/customer-center/customer-center-flutter"
slug: "customer-center-flutter"
version: "current"
original_source: "docs/tools/customer-center/customer-center-flutter.mdx"
---

## Installation

[![Release](https://img.shields.io/github/release/RevenueCat/purchases-flutter.svg?filter=!*beta*\&style=flat)](https://github.com/RevenueCat/purchases-flutter/releases)

Before integrating the Customer Center in Flutter, add `purchases_ui_flutter` (Interactive content is available in the web version of this doc.) or higher in your `pubspec.yaml`:

```yaml
dependencies:
  purchases_flutter: <latest version>
  purchases_ui_flutter: <latest version>
```

## Integration

Opening the customer center is as simple as:

```dart
  await RevenueCatUI.presentCustomerCenter();
```

## Setup promotional offers

Promotional Offers allow developers to apply custom pricing and trials to new customers and to existing and lapsed subscriptions. Unique promotional offers can be assigned to different paths and survey responses in the Customer Center, but first they must be setup in App Store Connect and Google Play Store.

The Customer Center will automatically show offers based on specific user actions. By default we have defined it for cancellations but it can be modified to any of the defined paths. For Flutter you are going to have to configure these promotional offers in both Google Play Console and App Store Connect.
Refer to [configuring Google Play Store promotional offers](/tools/customer-center/customer-center-promo-offers-google) and [configuring App Store Connect promotional offers](/tools/customer-center/customer-center-promo-offers-apple) for detailed instructions.

Learn more about configuring the Customer Center in the [configuration guide](/tools/customer-center/customer-center-configuration).
