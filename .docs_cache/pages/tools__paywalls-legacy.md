---
id: "tools/paywalls-legacy"
title: "Paywalls (Legacy)"
description: "RevenueCat's Paywalls allow you to remotely configure your entire paywall view without any code changes or app updates. Whether youâre building a new app, exploring new paywall concepts, or diving into experimentation; RevenueCatâs Paywalls make it easy to get started."
permalink: "/docs/tools/paywalls-legacy"
slug: "paywalls-legacy"
version: "current"
original_source: "docs/tools/paywalls-legacy.mdx"
---

RevenueCat's Paywalls allow you to remotely configure your entire paywall view without any code changes or app updates. Whether youâre building a new app, exploring new paywall concepts, or diving into experimentation; RevenueCatâs Paywalls make it easy to get started.

**Video:** Watch the video content in the hosted documentation.

:::info Legacy Paywalls
These docs refer to our legacy paywalls. To learn more about our new paywall builder, [click here](/tools/paywalls/creating-paywalls).
:::

You can think of a Paywall as an optional feature of your Offering. An Offering is the collection of Products which are organized into Packages to be displayed to your customers as a single "offer" across platforms. Now, with Paywalls, you can control the actual view that is used to display that "offer" in addition to controlling the products that are offered.

Therefore, you can create a unique Paywall for each of your Offerings, and can create an unlimited number of Offerings & Paywalls for each variation you want to test with Experiments.

### Getting Started

Our paywall templates use native code to deliver smooth, intuitive experiences to your customers when youâre ready to deliver them an Offering; and you can use our Dashboard to pick the right template and configuration to meet your needs.

To use RevenueCat Paywalls, simply:

1. [Install the RevenueCat UI SDK](/tools/paywalls-legacy/installation)

2. [Create a Paywall](/tools/paywalls-legacy/creating-paywalls) on the Dashboard for the [Offering](/getting-started/entitlements) you intend to serve to your customers

3. See [displaying paywalls](/tools/paywalls-legacy/displaying-paywalls) for how to display it into your app.

## Limitations

### Platforms (support for more coming)

- â iOS 15.0 and higher
- â visionOS 1.0 and higher
- â Mac Catalyst 15.0 and higher
- â watchOS 8.0 and higher
- â Android 7.0 (API level 24)
- â macOS
- â tvOS

### Android's Google Play developer determined offers

Paywalls in Android will use the default subscription option which, in case you use [developer determined offers](/subscription-guidance/subscription-offers/google-play-offers#eligibility-criteria), will always be available, providing these types of offers always to your users. If you want to avoid this behavior when using paywalls, add the `rc-ignore-offer` tag to the developer determined offer from your product.

## Next Steps

- Now that you know how our paywalls work, read about [creating paywalls](/tools/paywalls-legacy/creating-paywalls)
- Once you're ready to see your paywalls in action, you can follow our guides on [displaying paywalls](/tools/paywalls-legacy/displaying-paywalls)
- If you need inspiration with some paywall examples, you can try our [Paywalls Tester app](https://github.com/RevenueCat/purchases-ios/tree/main/Tests/TestingApps/PaywallsTester)
