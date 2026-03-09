---
id: "tools/funnels/configuring-payments"
title: "Configuring Payments"
description: "Before you can create and deploy funnels, you need to set up RevenueCat Web Billing. Funnels use Web Billing to process payments through checkout steps, so this configuration is required."
permalink: "/docs/tools/funnels/configuring-payments"
slug: "configuring-payments"
version: "current"
original_source: "docs/tools/funnels/configuring-payments.mdx"
---

Before you can create and deploy funnels, you need to set up RevenueCat Web Billing. Funnels use Web Billing to process payments through checkout steps, so this configuration is required.

:::info Checkout steps require Web Billing
Checkout steps in your funnels automatically use RevenueCat Web Billing and will display the appropriate payment interface based on your project's configuration. Make sure your funnel is associated with the correct app and Offering before adding checkout steps.
:::

## Prerequisites

To use Funnels, you'll need:

- â A Stripe account connected to RevenueCat
- â A Web Billing app configuration
- â At least one Web Billing product configured
- â An Offering that includes your Web Billing products

## Step 1: Connect your Stripe account

RevenueCat Web Billing uses Stripe as the payment processor. Before you can create a Web Billing app, you need to connect your Stripe account to RevenueCat.

1. Log into the RevenueCat dashboard
2. Go to your [account settings](https://app.revenuecat.com/settings/account)
3. Click **Connect Stripe account**
4. Install the RevenueCat app from the Stripe App Marketplace
5. Sign in with RevenueCat from within the Stripe app

:::info Project owner required
Only the project owner can connect a Stripe account. Collaborators cannot add or remove Stripe connections.
:::

For detailed instructions, see [Connect to your Stripe account](/web/connect-stripe-account).

## Step 2: Create a Web Billing app

After connecting Stripe, create a Web Billing app configuration in your RevenueCat project:

1. Navigate to **Apps & providers** in your project
2. Click **+ Add platform** and select **Web Billing**
3. Configure the following required fields:
   - **Stripe Account**: Select the connected Stripe account
   - **Default Currency**: The default currency for product prices
   - **App Name**: Displayed in purchase flows, emails, and invoices
   - **Support Email**: Customer support contact information
4. (Optional) Configure additional settings:
   - **Store URLs**: Links to your iOS and Android apps
   - **Redemption Links**: Enable anonymous purchases with mobile redemption
   - **Appearance**: Customize colors, button styles, and branding

:::warning Redemption Links are required for anonymous purchases
Redemption Links are required to use your funnels with anonymous users, such as those coming directly from an ad, a landing page, a social media post, and other traffic sources outside of a logged in app session.
:::

::info Appearance fields
These fields will influence the appearance of the checkout flow in your funnels, and therefore should match the branding you'll be using throughout the funnel to create a cohesive experience.
:::

:::warning Register your Funnels domain for Apple Pay & Google Pay
If you want Apple Pay or Google Pay to appear in funnel checkout steps, you must register the domain where your funnel checkout is hosted in Stripe's Payment Method Domains settings.

- Register `signup.cat` when using RevenueCat-hosted funnel URLs.
- If you've configured a custom domain for Funnels, register that domain instead.

For step-by-step instructions, see [Configuring Apple Pay & Google Pay](https://www.revenuecat.com/docs/web/web-billing/payment-methods#configuring-apple-pay--google-pay).
::::

For more details on app configuration, see [Web SDK - App configuration](/web/web-billing/web-sdk#app-configuration).

## Step 3: Create Web Billing products

Create products that customers can purchase through your funnels:

1. Go to **Product catalog â Products**
2. Select your Web Billing configuration
3. Click **+ New** to create a product
4. Configure:
   - **Product identifier**: Unique ID for the product
   - **Product type**: Auto-renewing subscription, consumable, or non-consumable
   - **Duration**: Billing cycle for subscriptions
   - **Pricing**: Set prices for each currency
   - **Free trial** (optional): Trial period duration
   - **Introductory period** (optional): Discounted pricing for a limited time

For complete product setup instructions, see [Configure Products & Prices](/web/web-billing/product-setup).

## Step 4: Create Offerings

Offerings group products together and are required for Funnels. Checkout steps in your funnels use the Offering settings to determine which products to display.

1. Go to **Product catalog â Offerings**
2. Click **+ New** to create an Offering
3. Add packages that group equivalent products across platforms
4. Mark one Offering as the **Default Offering** (this is what funnels will use by default)

For more information on Offerings, see [Offerings overview](/offerings/overview).

## Additional configuration

Once you have the basics set up, you can optionally configure things like multi-currency support, tax collection, and more. See [Configure Web Billing](/web/web-billing/configuring-overview) for a complete list of configuration options.

## Next steps

With your Web Billing setup complete, you're ready to:

- [Create your first funnel](/tools/funnels/creating-funnels)
- [Learn about deploying funnels](/tools/funnels/deploying-funnels)
- [Understand funnel analytics](/tools/funnels/analyzing-funnels)
