---
id: "getting-started/displaying-products"
title: "Displaying Products"
description: "If you've configured Offerings in RevenueCat, you can control which products are shown to users without requiring an app update. Building paywalls that are dynamic and can react to different product configurations gives you maximum flexibility to make remote updates."
permalink: "/docs/getting-started/displaying-products"
slug: "displaying-products"
version: "current"
original_source: "docs/getting-started/displaying-products.mdx"
---

If you've [configured Offerings](/getting-started/entitlements) in RevenueCat, you can control which products are shown to users without requiring an app update. Building paywalls that are dynamic and can react to different product configurations gives you maximum flexibility to make remote updates.

:::info
Before products and offerings can be fetched from RevenueCat, be sure to initialize the Purchases SDK by following our [Quickstart](/getting-started/quickstart) guide.
:::

## Fetching Offerings

Offerings are fetched through the SDK based on their [configuration](/offerings/overview) in the RevenueCat dashboard.

The `getOfferings` method will fetch the Offerings from RevenueCat. These are pre-fetched in most cases on app launch, so the completion block to get offerings won't need to make a network request in most cases.

*Interactive content is available in the web version of this doc.*

:::warning Avoid pre-warming offerings cache in your Android's Application
Don't call `getOfferings` in your Android app's `Application.onCreate`.

This might trigger additional network requests in some situations (like push notifications) without need, using your customer's data. The offerings cache should be pre-fetched automatically by the SDK.
:::

:::info Offerings, products or available packages empty
If your offerings, products, or available packages are empty, it's due to some configuration issue in App Store Connect or the Play Console.

You can find more information about troubleshooting this issue in our [Troubleshooting Guide](https://www.revenuecat.com/docs/offerings/troubleshooting-offerings).
:::

You must choose one Offering that is the "Default Offering" - which can easily be accessed via the `current` property of the returned offerings for a given customer.

:::info What's the difference between a current Offering and a default Offering?
The current Offering for a given customer may change based on the experiment they're enrolled in, any targeting rules they match, or the default Offering of your Project. Your Project's default Offering is the Offering that will be served as "current" when no other conditions apply for that customer.
:::

To change the default Offering of your Project, navigate to the Offerings tab for that Project in the RevenueCat dashboard, and find the Offering you'd like to make default. Then, click on the icon in the Actions column of that Offering to reveal the available options, and click **Make Default** to make the change.

![Make default offering](/docs_images/offerings/make-default.png)

If you'd like to customize the Offering that's served based on an audience, or their location in your app, check out [Targeting](/tools/targeting).

Offerings can be updated at any time, and the changes will go into effect for all users right away.

### Fetching Offerings by Placement

Alternatively, if your app has multiple paywall locations and you want to control each location uniquely, you can do that with Placements and the `getCurrentOffering(forPlacement: "string")` method.

*Interactive content is available in the web version of this doc.*

To learn more about creating Placements and serving unique Offerings through them, [click here](/tools/targeting/placements).

### Custom Offering identifiers

It's also possible to access other Offerings besides the Current Offering directly by its identifier.

*Interactive content is available in the web version of this doc.*

## Displaying Packages

Packages help abstract platform-specific products by grouping equivalent products across iOS, Android, and web. A package is made up of three parts: identifier, type, and underlying store product.

| Name       | Description                                                                                                                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Identifier | The package identifier (e.g. `com.revenuecat.app.monthly`)                                                                                                                                       |
| Type       | The type of the package: (Interactive content is available in the web version of this doc.) - `UNKNOWN` (Interactive content is available in the web version of this doc.) - `CUSTOM` (Interactive content is available in the web version of this doc.) - `LIFETIME` (Interactive content is available in the web version of this doc.) - `ANNUAL` (Interactive content is available in the web version of this doc.) - `SIX_MONTH` (Interactive content is available in the web version of this doc.) - `THREE_MONTH` (Interactive content is available in the web version of this doc.) - `TWO_MONTH` (Interactive content is available in the web version of this doc.) - `MONTHLY` (Interactive content is available in the web version of this doc.) - `WEEKLY` |
| Product    | The underlying product that is mapped to this package which includes details about the price and duration.                                                                                       |

Packages can be access in a few different ways:

1. via the `.availablePackages` property on an Offering.
2. via the duration convenience property on an Offering
3. via the package identifier directly

*Interactive content is available in the web version of this doc.*

#### Getting the Product from the Package

Each Package includes an underlying product that includes more information about the price, duration, and other metadata. You can access the product via the `storeProduct` property (or `webBillingProduct` property for [Web Billing](/web/web-billing/web-sdk)):

*Interactive content is available in the web version of this doc.*

## Choosing which Offering to display

In practice, you may not want to display the default current Offering to every user and instead have a specific cohort that see a different Offering.

For example, displaying a higher priced Offering to users that came from [paid acquisition](/integrations/attribution) to help recover ad costs, or a specific Offering designed to show [iOS Subscription Offers](/subscription-guidance/subscription-offers/ios-subscription-offers) when a user has [cancelled their subscription](/customers/customer-info#section-get-entitlement-information).

This can be accomplished through Targeting, which supports a handful of predefined dimensions from RevenueCat or **any** custom attribute you set for your customers. [Learn more here.](https://www.revenuecat.com/docs/tools/targeting)

Or, alternatively, you could write your own logic locally in your app to serve custom Offering identifiers for each cohort you have in mind.

*Interactive content is available in the web version of this doc.*

## Best Practices

| Do                                                                          | Don't                                                          |
| :-------------------------------------------------------------------------- | :------------------------------------------------------------- |
| â Make paywalls dynamic by minimizing or eliminating any hardcoded strings | â Make static paywalls hardcoded with specific product IDs    |
| â Use default package types                                                | â Use custom package identifiers in place of a default option |
| â Allow for any number of product choices                                  | â Support only a fixed number of products                     |
| â Support for different free trial durations, or no free trial             | â Hardcode free trial text                                    |

## Next Steps

- Now that you've shown the correct products to users, time to [make a purchase ](/getting-started/making-purchases)
- Check out our [sample apps ](/platform-resources/sample-apps) for examples of how to display products.
