---
id: "web/integrations/stripe"
title: "Stripe Billing"
description: "RevenueCat supports importing web purchases from Stripe Billing. This allows you to let users subscribe on your web app or store with Stripe Billing, and automatically unlock access in your mobile app via the Purchases SDK."
permalink: "/docs/web/integrations/stripe"
slug: "stripe"
version: "current"
original_source: "docs/web/integrations/stripe.mdx"
---

RevenueCat supports importing web purchases from Stripe Billing. This allows you to let users subscribe on your web app or store with Stripe Billing, and automatically unlock access in your mobile app via the *Purchases SDK*.

Before connecting Stripe, be sure to read the limitations that apply when [working with Stripe Billing purchases](#working-with-stripe-billing-purchases).

:::info April 2025 U.S. District Court Ruling on External Payment Options
A recent U.S. District Court ruling found Apple in violation of a 2021 injunction meant to allow developers to direct users to external payment options, like Web Billing. As a result, iOS developers are now permitted to guide users to web-based payment flows without additional Apple fees or restrictive design requirements. You can [find more details on the RevenueCat blog](https://revenuecat.com/blog/growth/introducing-web-paywall-buttons).

For apps available outside the U.S. App Store, Apple still requires that digital goods and subscriptions be purchased through in-app purchases. Promoting or linking to alternative payment methods within the app for non-U.S. users may lead to app review rejection or removal. Always ensure external payment links are shown only to eligible U.S. users.
:::

## 1. Connect with Stripe

To get started, you first need to connect your Stripe account with RevenueCat. If you haven't already done so, follow the instructions [here](/web/connect-stripe-account).

## 2. Create products and prices on Stripe

The Stripe Billing integration requires you to create and manage your Stripe product(s) directly in [the Stripe dashboard](https://dashboard.stripe.com/subscriptions/products).

:::warning Limitation: Product-price mapping
In Stripe, a *product* can have multiple *prices*. These are useful if you want to offer different price points for the same product. Currently, a product in RevenueCat maps directly to a product in Stripe, so if you're using multiple Stripe prices, it can be difficult to detect correct product and price information within RevenueCat. We currently recommend configuring a single price per Stripe product.
:::

### Pricing model compatibility

RevenueCat only supports **per unit** and **recurring quantity** subscription plans.

The following Stripe pricing models are supported within RevenueCat:

- Recurring - flat rate (e.g. $1.99 per month)
- Recurring - package pricing (e.g. $5.99 per 10 units / month)
- One-off - flat rate (e.g. $23.99 paid once)
- One-off - package pricing (e.g. $30.00 per 12 units)

These pricing models are currently not supported:

- Recurring - tiered pricing (e.g. starts at $1.99 per unit + $5.00 / month)
- Recurring - usage based (e.g. $13.99 per unit / month - based on metered usage)
- One-off - customer chooses price

## 3. Create subscriptions on Stripe

A typical setup consists of a website that uses [Stripe checkout](https://stripe.com/payments/checkout) to tokenize the customer payment information, and send this information to your server. After that, your server will be able to subscribe your customer to a product.

On the server-side, you can use [Stripe's REST API](https://stripe.com/docs/api/subscriptions) or their library for your favorite programming language. An example can be found [here](https://stripe.com/docs/billing/quickstart#create-subscription).

Alternatively, you can also use the Stripe dashboard for manually creating the subscriptions for testing.

You can also use [Stripe Payment Links](https://stripe.com/payments/payment-links) for a fully Stripe-hosted checkout solution.

:::info Stripe session configuration
[Ensure your session creates a Stripe Customer](https://stripe.com/docs/api/checkout/sessions/create#create_checkout_session-customer_creation) by setting `customer_creation` to `always`.
:::

:::warning One-time purchase support
RevenueCat supports non-subscription purchases, as long as they are created through a [Checkout Session](https://docs.stripe.com/api/checkout/sessions). Other ways of selling one-time purchases outside of Checkout Sessions can't be identified. All purchases handled through Stripe Checkout are compatible.
:::

## 4. Add your Stripe products to your RevenueCat project's entitlements

Add your Stripe products to your project's [entitlements](/getting-started/entitlements) to easily group the products for your app. RevenueCat will send Stripe subscriptions to your app the same way we do for the other app stores.

![](/docs_images/web/stripe/attach-entitlement.png)

:::info Stripe product identifier
In order for Stripe subscriptions to unlock [entitlements](/getting-started/entitlements), you must set a Product Identifier in the desired Offering to match a Stripe **product ID** exactly.
:::

## 5. Send Stripe tokens to RevenueCat

:::danger Crucial step
Failure to complete this step will result in Stripe subscriptions that are not tracked in RevenueCat.
:::

The following sections provide step-by-step instructions for two methods of sending Stripe tokens to RevenueCat, through one of two methods:

- Sending purchases manually through RevenueCat's API (POST receipt endpoint)
- Automated tracking of purchases using server-to-sever notifications (web hooks)

### Tracking purchases manually through RevenueCat API

You can send your Stripe subscriptions to RevenueCat through the [POST receipt endpoint](/migrating-to-revenuecat/migrating-existing-subscriptions/receipt-imports). When using Stripe Checkout, you should listen to and send subscriptions to RevenueCat only after either of these events have completed:

- `customer.subscription.created`
- `checkout.session.completed`

:::info
We recommend that you listen to `customer.subscription.created` for subscriptions and `checkout.session.completed` for one-time purchases for the simplest flow.
:::
The only required fields when sending your Stripe purchase to the RevenueCat API are the following:

- `fetch_token`: Your Stripe subscription ID (`sub_...`) OR your Stripe Checkout Session ID
- `app_user_id`: The App User ID that the subscription should be applied to

**Headers**

- `X-Platform`: Should be set to `stripe`.
- `Authorization`: It should be `Bearer YOUR_REVENUECAT_STRIPE_APP_PUBLIC_API_KEY`

Stripe subscriptions are automatically refreshed by RevenueCat the same way as subscriptions from the app stores. This means that **it may take up to two hours for a Stripe cancellation to be reflected in the RevenueCat backend**. Alternatively, you can re-post the same subscription to RevenueCat after a user has cancelled, and it will be updated right away.

*Interactive content is available in the web version of this doc.*

### Track new purchases via server-to-server-notifications

RevenueCat can automatically process Stripe tokens sent through server-to-server notifications. To enable automatic processing of Stripe purchases, ensure the following features are enabled:

- [Stripe Server Notifications](/platform-resources/server-notifications/stripe-server-notifications)
- [Track new purchases from server-to-server notifications](/platform-resources/server-notifications/stripe-server-notifications#tracking-new-purchases-using-stripe-server-notifications)

### One-time Stripe purchases

To track one-time purchases made through Stripe Checkout, you'll need to send us the Checkout Session ID as the fetch\_token if you are manually sending Stripe tokens to RevenueCat. Additionally, you'll need to use Stripe's [Prices](https://stripe.com/docs/api/prices) objects. RevenueCat supports both one-time purchases and subscriptions made through Stripe Checkout.

:::info App User ID is required
In order for a Stripe subscription to be honored within an app, the *Purchases SDK* needs to be configured with the same App User ID associated with the Stripe subscription.
:::

## 6. Test your Stripe subscriptions

You can test your implementation for Stripe and RevenueCat by using [Stripe's test mode](https://stripe.com/docs/testing).

The subscriptions you create using this environment will be considered *sandbox transactions* in RevenueCat.

![](/docs_images/web/stripe/test-data.png)

:::danger Stripe Test Clocks not fully supported
Stripe allows using [test clocks](https://stripe.com/docs/billing/testing/test-clocks) to manipulate how subscriptions move through time. Since using test clocks lead to time divergences between Stripe and RevenueCat, data may not be accurately reflected in RevenueCat when using Stripe test clocks.
:::

## Working with Stripe Billing purchases

Subscription payments through the web are processed with the same logic as subscriptions through the app stores. This means there are currently some limitations that must be considered for web payments to work properly.

:::success Coupons are supported
Pricing in RevenueCat [Charts](/dashboard-and-metrics/charts) and [customer events](/dashboard-and-metrics/customer-profile) will reflect any coupons applied to a Stripe purchase.
:::

### Upgrading and downgrading

Prorated amounts are not factored into *MRR* or *Revenue* calculations. If someone changes plans, the default behavior in Stripe is to give the user credit for any unused portion and bill them for the remainder of the new plan cost. You need to disable this behavior manually, or by passing the `prorate=false` flag through the Stripe API for accurate revenue calculations in RevenueCat.

### Cancellations

When a subscription is cancelled in Stripe, you have two options:

1. Immediate cancellation: The subscription is cancelled immediately, with the option to pro-rate or not.
2. Cancellation at the end of the period: The subscription is cancelled at the end of the current billing period (this is how the app stores behave).

Both options are supported by RevenueCat, but the *MRR* and *Revenue* calculations will only be accurate in the first case if you choose **not** to prorate.

Cancellations in Stripe are automatically detected by RevenueCat the same way as subscriptions from the app stores. This means there may be up to a two-hour delay between when the subscription is cancelled in Stripe and when the cancellation is reflected in the RevenueCat backend.

### Billing Issues

When a customer encounters an issue with their payment, RevenueCat will generate a billing issue event in the RevenueCat [Customer History](/dashboard-and-metrics/customer-profile). If all retries for a payment fails, you have three options:

1. cancel the subscription: RevenueCat will **revoke access**.
2. mark the subscription as unpaid: RevenueCat will **revoke access**.
3. leave the subscription as-is: RevenueCat **will not revoke access**.

You can find these options, along with your Retry schedule, in your Stripe dashboard under **Settings > Billing > Subscriptions and email > Manage failed payments**.

If you are expecting a billing issue event, it may take a few hours for the RevenueCat dashboard to display the event. Note that we will only generate the billing issue event once and we do not generate new ones when subsequent retries fail.

:::success That's it!
You can now allow users to subscribe from the web or within your app, and let them access their subscription anywhere.
:::

### Managing subscriptions with Stripe's customer portal

When using Stripe Billing, you'll need to direct customers to the Stripe customer portal if they want to make changes to their subscription, download receipts, etc. The RevenueCat Web Billing Customer Portal does not work with Stripe Billing purchases.

You can configure the Stripe customer portal in your Stripe dashboard [settings](https://dashboard.stripe.com/settings/billing/portal).

Once configured, you can save your **customer portal URL** in the RevenueCat dashboard Stripe provider settings. It will be returned in the `managementUrl` property in the SDK's `CustomerInfo` object, and anywhere else the customer should be redirected to manage their purchases:

![stripe customer portal URL](/docs_images/web/stripe/stripe-customer-portal-url.png)

## Troubleshooting

**A Stripe purchase is missing/not found in RevenueCat**

If a Stripe purchase seems to be missing in RevenueCat, first double check you've got the right App User ID. Sometimes users may have multiple accounts, and may contact you referencing the wrong identifier.

If you're sure you've got the right App User ID, you'll likely need to re-send the purchase token and App User ID to our API as detailed above, or wait for a new subscription event to occur (if you have `Track new purchases from server-to-server-notifications` enabled). The end-user won't be able to directly restore their Stripe purchases to sync to RevenueCat as is possible with the mobile app stores.
