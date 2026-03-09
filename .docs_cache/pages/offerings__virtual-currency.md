---
id: "offerings/virtual-currency"
title: "Virtual Currency"
description: "Enable transactions for virtual items in your app"
permalink: "/docs/offerings/virtual-currency"
slug: "virtual-currency"
version: "current"
original_source: "docs/offerings/virtual-currency.mdx"
---

Virtual currencies are digital assets used within your app to facilitate transactions, unlock premium features, or enhance customer engagement.

These currencies are typically acquired through in-app purchases, rewards, or gameplay achievements and do not have intrinsic real-world value outside the application. They can be used for purchasing virtual goods, upgrading characters, or accessing exclusive content. Common examples include tokens, coins, credits, or other units that can be replenished through purchases.

You can leverage virtual currencies to monetize apps, encourage customer retention, and create a more immersive experience.

:::tip Tutorial
For a complete walkthrough of implementing virtual currencies, see our [tutorial blogpost](https://www.revenuecat.com/blog/engineering/how-to-monetize-your-ai-app-with-virtual-currencies/).
:::

:::info
This feature is in an early stage and under active development. While what's available today is stable and ready to use, we're continuing to expand its capabilities.

Weâd [love to hear your feedback](https://form.typeform.com/to/jI9vpPZq) to help shape the roadmap.
:::

## Configuration

In RevenueCat, virtual currencies are defined at the project level. You can configure up to 100 virtual currencies per project and use them to enrich your app experience.

1. Click the **âVirtual Currenciesâ** option in the **âProduct catalogâ** of your project sidebar in RevenueCat

![](/docs_images/virtual-currency/vc-sidebar.png)

2. Select **â+ New virtual currencyâ** button in the top right corner. Enter a code and a name for your currency.

- **Code**: This is used across various APIs to identify the virtual currency (e.g: GLD)
- **Icon** (*optional*): Choose an icon to visually represent this currency in the dashboard
- **Name**: This should be a readable name for the currency that you're creating (e.g: GOLD)
- **Description** (*optional*): A description of what this currency represents or how it is used (e.g: Can be used to purchase in-app items)

![](/docs_images/virtual-currency/vc-setup.png)

3. You can optionally associate products with your new currency. Every time customers purchase one of these products, the defined amount of virtual currency will be added to their balance. Click **Add associated product**, pick a product and fill in the amount.

![](/docs_images/virtual-currency/vc-products.png)

You can associate as many products as you want with your virtual currency and you can also associate a product with more than one virtual currency, meaning once it's purchased, multiple types of virtual currencies are added to the customer's balance. If you have not yet configured any products, see our [documentation](/offerings/products/setup-index) for further instructions.

4. Remember to select "SAVE" in the upper right-hand corner. Repeat this process if to create more than one currency.

## Dashboard balances

Once your customer purchase the associated products they will get the defined amount of your virtual currency. You can inspect the virtual currency balances of your customer in the right side-panel of the customer page.

## Usage

### Prerequisites

The endpoints available for virtual currency are supported through our Developer API (2.0.0). You will need a secret key to access it. Make sure that your key at least has Read & Write permissions for Customer Purchases Configuration and Customer Configuration. See our [documentation](https://www.revenuecat.com/docs/api-v2#tag/Overview-\(v2\)/Authentication) for more details on how you can access RevenueCatâs Developer API.

![](/docs_images/virtual-currency/api-secret-key.png)

#### Rate limits

All endpoints for virtual currency under our Developer API are subject to a rate limit of 480 requests per minute. If you exceed this limit, the API will return a 429 Too Many Requests status code, indicating that the rate limit has been reached.

To avoid service interruptions, we recommend implementing retry logic. If you hit the rate limit, the API response will include a `Retry-After` header, specifying the amount of time (in seconds) you need to wait before making further requests.

For more information on handling rate limits and using the Retry-After header, please refer to our [API documentation](https://www.revenuecat.com/docs/api-v2#tag/Rate-Limit).

:::info Need more?
If you anticipate needing higher rate limits, please [contact our support team](https://app.revenuecat.com/settings/support) with details about your use case and anticipated request usage.
:::

### Limitations

The maximum amount of a single virtual currency that a customer can own must be between zero and two billion (2,000,000,000). Negative balances are not supported.

### Reading balances

#### From your backend

The [virtual currency get balance Developer API endpoint](https://www.revenuecat.com/docs/api-v2#tag/Customer/operation/list-virtual-currencies-balances) allows you to retrieve a customer's current balance from your backend:

*Interactive content is available in the web version of this doc.*

The response will include the balances for all the virtual currencies that the customer has.

*Interactive content is available in the web version of this doc.*

#### From the SDK

Fetching virtual currency balances is supported in the following SDK versions:

| SDK              | Supported Versions |
| ---------------- | ------------------ |
| iOS SDK          | 5.32.0+            |
| Android SDK      | 9.1.0+             |
| React Native SDK | 9.1.0+             |
| Flutter SDK      | 9.1.0+             |
| Capacitor SDK    | 11.1.0+            |
| Unity SDK        | 8.1.0+             |
| KMP SDK          | 2.1.0+16.2.0+      |
| Cordova SDK      | 7.1.0+             |
| Web (JS/TS) SDK  | 1.13.0             |

You can use the `virtualCurrencies()` function to retrieve a customer's balance. The function returns a `VirtualCurrencies` object, which includes the customer's balances along with each virtual currency's metadata.

*Interactive content is available in the web version of this doc.*

:::warning VirtualCurrencies does not update automatically when balance changes
When a customer's balance is updated from your backend, the `VirtualCurrencies` object remains cached and is not automatically updated. To get the updated balance, you need to call `Purchases.shared.invalidateVirtualCurrenciesCache()` and fetch the `VirtualCurrencies` object again.

We also recommend calling `invalidateVirtualCurrenciesCache()` after a purchase has completed successfully to ensure that the balances are up to date the next time you fetch them.
:::

You may directly access the cached virtual currencies using the `cachedVirtualCurrencies` property. This is helpful for rendering UI immediately, or for displaying virtual currencies when there is no network connection. Keep in mind that this value is cached and isn't guaranteed to be up to date.

*Interactive content is available in the web version of this doc.*

### Depositing or spending

You can deposit or spend currency by calling the [virtual currency transactions Developer API endpoint](https://www.revenuecat.com/docs/api-v2#tag/Customer/operation/create-virtual-currencies-transaction) from the backend of your app:

*Interactive content is available in the web version of this doc.*

The example request will deduct 20 GLD and 10 SLV from the customer's balance. Upon successful execution, the response will contain the updated balances of the virtual currencies that were spent.

Note that sufficient balances of both currency types are required for the transaction to succeed. If not, the transaction will fail with HTTP 422 error and no virtual currency will be deducted.

*Interactive content is available in the web version of this doc.*

Multiple virtual currency types can be adjusted in a single transaction. Deductions and additions can also be combined. For example, you can execute the conversion of 50 GLD to 200 SLV with the following transaction:

*Interactive content is available in the web version of this doc.*

### Customer center

You can display a customer's virtual currency balances in RevenueCat's [Customer Center](/tools/customer-center/). Please refer to [this section](/tools/customer-center/customer-center-configuration#virtual-currencies) of the Customer Center configuration guide for more information on displaying virtual currencies in the Customer Center.

## Events

RevenueCat provides event tracking for virtual currency transactions, allowing you to monitor and respond to balance changes in real-time through webhooks.

Virtual currency transactions appear in the [Customer History](/dashboard-and-metrics/customer-profile) timeline and trigger `VIRTUAL_CURRENCY_TRANSACTION` webhook events for the entire subscription lifecycle whenever there are currency balance adjustments.

:::info Adjustments via API are view-only
Virtual currency adjustments made through the [API](/offerings/virtual-currency#depositing-or-spending) will appear in the customer timeline, but cannot be clicked for additional details. These adjustments are displayed for reference only and do not generate webhook events.
:::

For more information about virtual currency events, including customer timeline events and webhook events, see our [Virtual Currency Events](/offerings/virtual-currency/events) documentation.

## Sandbox Testing

When testing virtual currency functionality in sandbox environments, you have control over how sandbox purchases affect virtual currency balances. This is particularly important when testing with real app user IDs or test accounts that might overlap with production data.

### Sandbox Access Control

You can configure sandbox testing behavior in the **General** tab of your project settings:

- **Anybody** *(default)*: All sandbox purchases will add virtual currency as configured. This is recommended for early development and internal QA testing.
- **Allowed App User IDs only**: Only specific app user IDs will receive virtual currency from sandbox purchases. Useful for restricted testing scenarios like Google Play closed testing.
- **Nobody**: No sandbox purchases will grant virtual currency. Use this to prevent testing from affecting virtual currency balances.

![Sandbox Testing Settings](/docs_images/projects/sandbox-testing-settings.png)

### What Happens When You Restrict Access

If you update your sandbox access settings to be more restrictive:

- â Sandbox purchases continue to be recorded in RevenueCat
- â Only qualifying customers receive virtual currency going forward
- ð° Previously granted virtual currency remains in customer balances (even if they no longer qualify)

For more detailed information about sandbox testing configuration, see our [Sandbox Testing Access](/projects/sandbox-access) documentation.

## Best practices and security considerations

Virtual currencies is a very powerful feature that RevenueCat provides, however it needs to be used correctly to ensure high standards of security. Here are some necessary requirements in order to make sure that bad actors cannot exploit your system for their benefit or to harm other users of your app.

### Virtual currency transactions should be securely initiated by a backend server

Transactions that add or remove virtual currencies to your customer balances, except for In-App Purchases, should be initiated by the backend of your Application. These requests require RevenueCat secret API keys to be authenticated, and these keys need to be securely stored and never be exposed to the public.

Itâs fine if your backend provides APIs for your app to initiate virtual currency transactions, however, these APIs should not allow direct modifications of customer balances. Instead they should only support operations that do not require direct input of amounts and they should always perform the necessary validations to ensure that the customer has the rights and meets the requirements to perform the requested transaction.

See some examples of secure and unsecure backend APIs:

| Do â                                                                                                                                                                                                             | Do not! â                                                                                                                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| (Interactive content is available in the web version of this doc.) The backend knows the price of the product and charges accordingly. Also it should check that the customer has the right to purchase the product.    | (Interactive content is available in the web version of this doc.) The backend blindly attaches the product to the customer and spends the amount that is defined in the request. |
| (Interactive content is available in the web version of this doc.) The backend grants 100 Gold to the customer after checking that they indeed reached a new level in the game and the reward is not already provided. | (Interactive content is available in the web version of this doc.) The backend blindly rewards 500 GLD to the customer according the HTTP request data.                           |

Following this will ensure that the users of your app cannot tamper / fake requests to your backend for their benefit.

### Communication between your app and your backend should be encrypted and authenticated

All the requests from your app to your backend that could trigger a virtual currency transaction need to be encrypted and authenticated. Make sure you use TLS or equivalent encryption technologies. Also ensure that all the requests that can trigger a virtual currency transaction are authenticated using well proved methodology.

Here are a few options to consider:

- Password based authentication
- Two/Multifactor authentication
- Token based authentication (e.g. JWT, OAuth 2.0)
- Single sign on using widely used services (Google, Facebook, Apple etc)
- Other equivalent or stronger technologies

With this you will ensure that requests that could trigger virtual currency transactions for an account of your app can only be initiated by the actual account owner.

## Tips & Hints

### Ensuring exactly one execution of Virtual Currency transactions

As a common practice, you may implement retries to handle network or other errors when submitting a Virtual Currency transaction. If you want to ensure that your transaction will only be executed once, even if your request reaches our server more than one times, you can make use of our `Idempotency-Key` HTTP header. Make sure that you pass an identifier that uniquely identifies your transaction (e.g. a UUID) and it will be guaranteed that your transaction will be executed at most one time.

*Interactive content is available in the web version of this doc.*

### Virtual Currencies are not transferable

In contrast to regular In-App purchases that can be transferred to other customers during [purchase restores](/projects/restore-behavior), Virtual Currencies are not transferable, and once granted they will remain with the same customer until they are consumed.
