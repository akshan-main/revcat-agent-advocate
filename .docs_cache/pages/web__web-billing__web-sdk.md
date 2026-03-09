---
id: "web/web-billing/web-sdk"
title: "Web SDK"
description: "- RevenueCat Web Billing: supported â (requires Stripe account for payment gateway)"
permalink: "/docs/web/web-billing/web-sdk"
slug: "web-sdk"
version: "current"
original_source: "docs/web/web-billing/web-sdk.mdx"
---

:::warning Web SDK billing engine support

- RevenueCat Web Billing: supported â (requires Stripe account for payment gateway)
- Paddle Billing: supported â (requires Paddle account)
- Stripe Billing:Â not yet supported â

:::

RevenueCat's Web SDK allow you to easily sell subscriptions and other purchases in your web app.

Web Billing differs from external payment integrations in that it takes care of the purchase UI, the subscription management portal, and the recurring billing logic.

:::info Fees
If you're using Web Billing, Stripe will still charge a [payment processing fee](https://stripe.com/pricing) for transactions, but you will not have to pay [Stripe Billing fees](https://stripe.com/billing/pricing). See [fee comparison](overview#fee-comparison)
If you're using Paddle, you'll be charged [Paddle's transaction fees](https://www.paddle.com/pricing).
:::

## Installation

Start by installing the `@revenuecat/purchases-js` package using the package manager of your choice:

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*

:::info
When testing Web Billing with [unpkg](https://www.unpkg.com/), add `Purchases` before all method names to access them.
For example, use `Purchases.Purchases.configure()` instead of `Purchases.configure()`.
:::

## General setup

### Connect with billing provider

To get started, you first need to connect a billing engine.

### App configuration

To start using Web Billing, you will need to add a Web Billing platform to your project. To do that, go to **Apps & providers** and add a new *Web Billing* web config to your project.

![New Web Billing Platform](/docs_images/projects/add-web-platform.png)

In the following step, you can set up the most important information for the new App:

- **Stripe Account**: The Stripe account to use. To use a different Stripe account not shown in the list, [connect it to RevenueCat first](/web/connect-stripe-account).
- **Default Currency**: The default currency to use for the prices of the products. [Read more about multi-currency support in Web Billing](/web/web-billing/multi-currency-support).
- **App Name**: The name of the app. This will also be shown in the purchase flow, in emails, and on invoices.
- **Support Email**: An email address that customers can send support requests to. This will also be shown in the purchase flow, in emails, and on invoices.
- **Store URLs**: Links to your native iOS and Android apps that are used in the checkout and emails, to enable customers to download them after purchasing.
- **Redemption Links settings**: See [Redemption Links](/web/web-billing/redemption-links/) for how to configure them.
- **Appearance**: The Appearance tab allows customizing the look and feel of the purchase flow, including colors, button shapes and more. [Read more about customizing the appearance](/web/web-billing/customization).

![New Web Billing App](/docs_images/web/web-billing/new-web-billing-configuration.png)

After creating the app, some additional fields will be shown:

- **App icon**: You can upload an app icon here that will be shown in the purchase flow, in emails, and on invoices.
- **Logo**: You can additionally upload a full size logo or wordmark that will be shown instead of the App Icon when appropriate. We recommend transparent PNG images.
- **Public API Key**: The API key to be used in your web application when initializing the SDK. This key is safe to be included in production code.
- **Sandbox API Key**: The API key to be used for [testing](#Testing) purposes. Do not share this API key or include it in your production web app, as it allows to make purchases and unlocking entitlements using test cards.

### Product configuration

To get started with the Web SDK, you should follow the regular setup of [entitlements, products, and offerings](/getting-started/entitlements).

However, you can configure your product and its duration [directly in the RevenueCat dashboard](/web/web-billing/product-setup):

![New product configuration page](/docs_images/web/web-billing/new-product-configuration.png)

## SDK configuration

Configure the RevenueCat Web SDK by calling the static `configure()` method of the `Purchases` class:

*Interactive content is available in the web version of this doc.*

:::warning Only configure once
You should configure the SDK only once in your code.
:::

You can use the object returned from the `configure()` method to call any of the SDK methods, or use the static method `getSharedInstance()` of the `Purchases` class to returned the initialized `Purchases` object.

The method will throw an exception if the SDK has not yet been configured.

You can use both anonymous and identified app user ids when configuring the SDK, check out the next section to understand the differences.

## Identifying Customers

The RevenueCat Web SDK supports both [identified](/customers/user-ids) and [anonymous](/customers/user-ids#anonymous-app-user-ids) customers, offering flexibility in how you manage user accounts and subscriptions.
Both anonymous and identified customers are supported by the SDK and by the [Web Purchase Links](/web/web-billing/web-purchase-links).
Hereâs how these options work:

### Identified Customers

For identified customers, you provide a unique App User ID linked to the customerâs account. This is ideal for apps with authentication mechanisms or shared subscription access between platforms (e.g., web and mobile). To implement this approach:

- Use a third-party authentication provider like [Firebase](https://firebase.google.com/docs/auth) / [Supabase](https://supabase.com/docs/guides/auth) or a library like [auth.js](https://authjs.dev/).
- By sharing authentication across your web app and mobile apps, customers can seamlessly access subscriptions they purchased on any platform without additional configurationâjust map products to the correct entitlements.

Hereâs how you can configure `purchases-js` to use identified customers:

*Interactive content is available in the web version of this doc.*

### Anonymous Customers

With [Redemption Links](/web/web-billing/redemption-links/), anonymous customers can now purchase subscriptions on the web without being logged into an account. These customers can later redeem their purchases on mobile apps or other platforms.
Redemption Links enable you to:

- Share subscription access without requiring user authentication.
- Ensure purchases remain accessible, even for anonymous users.

Hereâs how you can configure `purchases-js` to use anonymous customers:

*Interactive content is available in the web version of this doc.*

Find out more about Redemption Links and how to set them up [here](/web/web-billing/redemption-links/) .

## Getting customer information

You can access the customer information using the `getCustomerInfo()` method of the `Purchases` object:

*Interactive content is available in the web version of this doc.*

You can then use the `entitlements` property of the `CustomerInfo` object to check whether the customer has access to a specific entitlement:

*Interactive content is available in the web version of this doc.*

If your app has multiple entitlements, you might also want to check if the customer has any active entitlements:

*Interactive content is available in the web version of this doc.*

## Building your paywall

### Getting and displaying products

We recommend using [Offerings](/getting-started/entitlements#offerings) to configure which products get presented to the customer. You can access the offerings for a given app user ID with the (asynchronous) method `purchases.getOfferings()`. The current offering for the customer is contained in the `current` property of the return value.

*Interactive content is available in the web version of this doc.*

If you want to [support multiple currencies](/web/web-billing/multi-currency-support) and manually specify the currency, you can pass the currency code to the `getOfferings()` method. If you do not specify the currency, RevenueCat will attempt to geolocate the customer and use the currency of the customer's country if it's available, or fall back to the default currency of the app.

*Interactive content is available in the web version of this doc.*

It's also possible to access other Offerings besides the Current Offering directly by its identifier.

*Interactive content is available in the web version of this doc.*

Each Offering contains a list of Packages. Packages can be accessed in a few different ways:

1. via the `.availablePackages` property on an Offering.
2. via the duration convenience property on an Offering
3. via the `.packagesById` property of an Offering, keyed by the package identifier

*Interactive content is available in the web version of this doc.*

Each Package contains information about the product in the `webBillingProduct` property:

*Interactive content is available in the web version of this doc.*

### Purchasing a package

To purchase a package, use the `purchase()` method of the `Purchases` object. It returns a `Promise<{customerInfo: CustomerInfo}>`. To handle errors, you should catch any exceptions that occur.

*Interactive content is available in the web version of this doc.*

### Presenting a RevenueCat Paywall with purchases-js

To render a paywall that RevenueCat manages for you, call `presentPaywall()`. This method displays the configured paywall, guides the customer through checkout, and resolves once the flow is complete. Provide the HTML element where the paywall should be injected. Optionally, pass an offering object retrieved from `purchases.getOfferings()` to select a specific paywall; otherwise the customer's current offering will be used.

```ts title="Presenting a paywall"
async function showPaywall() {
  const paywallContainer = document.getElementById("paywall-container");

  try {
    const purchaseResult = await purchases.presentPaywall({
      htmlTarget: paywallContainer,
      // no offering specified, the current offering will be used.
    });

    console.log("Paywall completed", purchaseResult);
  } catch (error) {
    console.error("Error presenting paywall", error);
  }
}
```

You can also specify the offering to use by passing it to `presentPaywall()`.

```ts title="Presenting a paywall"
async function showPaywall() {
  const paywallContainer = document.getElementById("paywall-container");
  const offerings = await purchases.getOfferings();
  const offeringToUse = offerings.all["offering-id-to-use"];
  try {
    const purchaseResult = await purchases.presentPaywall({
      htmlTarget: paywallContainer,
      offering: offeringToUse,
    });

    console.log("Paywall completed", purchaseResult);
  } catch (error) {
    console.error("Error presenting paywall", error);
  }
}
```

### Customizing the purchase flow

The `purchase()` method accepts a `PurchaseParams` object to set custom purchase options, including the following:

- Send the customer's billing email address, skipping the email collection step (`customerEmail`)
- Setting the selected and default locales (`defaultLocale`, `selectedLocale`) âÂ see [Localization](/web/web-billing/localization)
- Setting the HTML target element for the purchase flow to be rendered in (`htmlTarget`)
- Passing purchase metadata to be sent to the backend (`metadata`) âÂ see [Custom Metadata](/web/web-billing/custom-metadata)

## Testing

See [Testing Web Purchases](/web/web-billing/testing)
