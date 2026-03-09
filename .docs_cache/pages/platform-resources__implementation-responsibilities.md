---
id: "platform-resources/implementation-responsibilities"
title: "Implementation Responsibilities"
description: "RevenueCat is the single source-of-truth for your subscription status across iOS, Android, and web. The complicated process surrounding receipt validation and interacting with the various native frameworks like Apple's StoreKit and Google's BillingClient are handled automatically when using RevenueCat's SDK."
permalink: "/docs/platform-resources/implementation-responsibilities"
slug: "implementation-responsibilities"
version: "current"
original_source: "docs/platform-resources/implementation-responsibilities.md"
---

RevenueCat is the single source-of-truth for your subscription status across iOS, Android, and web. The complicated process surrounding receipt validation and interacting with the various native frameworks like Apple's StoreKit and Google's BillingClient are handled automatically when using RevenueCat's SDK.

Subscription status isn't the only aspect of integrating subscriptions into your app, though. Paywalls, content delivery, and attribution are just some of the elements many developers will encounter in the process.

This document intends to outline the responsibilities between developers integrating the Purchases SDK, RevenueCat itself, and the various app stores (App Store, Google Play, Stripe, and Amazon Appstore).

## RevenueCat Responsibilities

### Backend

RevenueCat's backend will appropriately verify, parse, and validate receipts associated with customers for your app and provides continuously updating subscription status via the API and SDK.

### Client SDK

The SDK will fetch product information from stores, manage purchase logic (including purchase environments), sync receipts, fetch customer subscription status from the backend, and sync attribution data for customers.

For more information about the SDK and how to install it for your platform, check out our [Installation](/getting-started/installation) docs.

### Dashboard / Charts

The RevenueCat Dashboard and Charts will display revenue information based on the production receipts synced with the SDK and processed by the backend.

For more information about the Dashboard and Charts, check out our docs [here](/dashboard-and-metrics/overview).

## General Responsibilities

| Responsibility                                                                    | Developer | RevenueCat | App Store | Google Play |
| --------------------------------------------------------------------------------- | --------- | ---------- | --------- | ----------- |
| Fetching product information from store                                           |           | â         | â        | â          |
| [Presenting products to users for purchase](/getting-started/displaying-products) | â        |            |           |             |
| Managing purchase logic                                                           |           | â         |           |             |
| Processing payments                                                               |           |            | â        | â          |
| Managing billing/issuing refunds for subscriptions                                |           |            | â        | â          |
| Unlocking gated content and features                                              | â        |            |           |             |
| Unlocking purchases initiated from the App Store / Google Play / Stripe           | â        |            |           |             |
| Syncing, parsing and verifying receipts                                           |           | â         |           |             |
| [Tracking entitlement status](/customers/customer-info)                           |           | â         |           |             |
| [Tracking purchase history](/dashboard-and-metrics/customer-profile)              |           | â         |           |             |
| Downloading purchased content                                                     | â        |            |           |             |
| [Identifying users](/customers/user-ids)                                          | â        |            |           |             |
| [Getting attribution data for attribution providers](/integrations/attribution)   | â        |            |           |             |
| [Sending attribution data to attribution providers](/integrations/attribution)    |           | â         |           |             |
| [Notifying your servers of purchase events](/integrations/webhooks)               |           | â         |           |             |
| [Reporting revenue](/dashboard-and-metrics/charts)                                |           | â         | â        | â          |
