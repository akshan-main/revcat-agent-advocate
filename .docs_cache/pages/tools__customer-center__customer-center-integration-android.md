---
id: "tools/customer-center/customer-center-integration-android"
title: "Integrating Customer Center on Android"
description: "Installation"
permalink: "/docs/tools/customer-center/customer-center-integration-android"
slug: "customer-center-integration-android"
version: "current"
original_source: "docs/tools/customer-center/customer-center-integration-android.mdx"
---

## Installation

[![Release](https://img.shields.io/github/release/RevenueCat/purchases-android.svg?filter=!*beta*\&style=flat)](https://github.com/RevenueCat/purchases-android/releases)

Before integrating the Customer Center in Android, you need to add the `com.revenuecat.purchases:purchases-ui` SDK (Interactive content is available in the web version of this doc.) or higher to your app.

```groovy build.gradle
implementation 'com.revenuecat.purchases:purchases:<latest version>'
implementation 'com.revenuecat.purchases:purchases-ui:<latest version>'
```

## Integration

There's a `CustomerCenter` composable that can be used to display the Customer Center. It's intended to be used as a full screen composable so make sure to use it with a `fillMaxSize` modifier:

*Interactive content is available in the web version of this doc.*

Alternatively, you can instantiate the Customer Center as an Activity in `com.revenuecat.purchases:purchases-ui` SDK 8.13.0 or higher:

*Interactive content is available in the web version of this doc.*

### Ensuring Proper Theming for Customer Center

To ensure that Customer Center displays correctly with the right colors, contrast, and theme consistency, it needs to be wrapped in Material 3's `MaterialTheme`.
This allows it to dynamically adapt to dark and light mode while applying the correct Material Design colors to all UI elements.
If your app already uses Material 3's `MaterialTheme` with appropriate color schemes for dark and light mode, no additional changes are needed.
However, if CustomerCenter is the only composable in your hierarchy, if you're using Material 2, or if you're using another theming system, you may need to explicitly wrap it in Material 3's `MaterialTheme` to ensure proper theming.

*Interactive content is available in the web version of this doc.*

### Listening to Customer Center Events

You can listen to Customer Center events in two ways: using a global listener, or using a local listener through the CustomerCenter composable options.

First, create a CustomerCenterListener implementation:

*Interactive content is available in the web version of this doc.*

Then, you can use it in one of two ways:

1. As a global listener that will be called for all Customer Center instances:

*Interactive content is available in the web version of this doc.*

2. As a local listener through the CustomerCenter composable options:

*Interactive content is available in the web version of this doc.*

The following events are available:

- `onManagementOptionSelected`: Called when a user selects a management option (missing purchase, cancel, or custom URL)
- `onRestoreStarted`: Called when the restore process begins
- `onRestoreCompleted`: Called when the restore process completes successfully
- `onRestoreFailed`: Called when the restore process fails
- `onShowingManageSubscriptions`: Called when the manage subscriptions screen is shown
- `onFeedbackSurveyCompleted`: Called when a user completes a feedback survey

### Custom Actions

:::info Custom Actions support
The minimum supported version is Android SDK version 9.2.0.
:::

Custom Actions allow you to add your own custom management options to the Customer Center. When a customer taps on a custom action, your app receives a callback with the custom action identifier, allowing you to execute your own code.

To handle custom actions, create a CustomerCenterListener with the `onCustomActionSelected` callback:

*Interactive content is available in the web version of this doc.*

Custom actions are configured in the RevenueCat dashboard under Customer Center settings, where you can:

- Set a custom identifier for the action
- Configure the display text and localization
- Position the action within the management options

## Setup promotional offers

Promotional Offers allow developers to apply custom pricing and trials to new customers and to existing and lapsed subscriptions. Unique promotional offers can be assigned to different paths and survey responses in the Customer Center, but first they must be setup in Google Play Console.

The Customer Center will automatically show offers based on specific user actions. By default we have defined it for cancellations but it can be modified to any of the defined paths. Refer to [configuring Google Play Store promotional offers](/tools/customer-center/customer-center-promo-offers-google) for detailed instructions.

Learn more about configuring the Customer Center in the [configuration guide](/tools/customer-center/customer-center-configuration).
