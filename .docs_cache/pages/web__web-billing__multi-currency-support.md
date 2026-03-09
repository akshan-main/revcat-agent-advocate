---
id: "web/web-billing/multi-currency-support"
title: "Supporting Multiple Currencies"
description: "Web Billing (formerly RevenueCat Billing) supports multiple currencies for your web subscriptions."
permalink: "/docs/web/web-billing/multi-currency-support"
slug: "multi-currency-support"
version: "current"
original_source: "docs/web/web-billing/multi-currency-support.mdx"
---

Web Billing (formerly RevenueCat Billing) supports multiple currencies for your web subscriptions.

### App setup

In the setup of the Web Billing app, you can select the default currency for the app. This currency will be used for customers whose location is not supported by any of the currencies you have configured, or when the customer's location is undetermined.

![App configuration page](/docs_images/web/web-billing/new-web-billing-app-for-currency.png)

### Product setup

When creating a new product in the RevenueCat dashboard, you can set the price for each currency you want to support. Each product can have only one price per currency. You can add additional currencies to a product by editing it, but you can't change the currency of an existing price or remove a currency.

![New product configuration page](/docs_images/web/web-billing/new-product-configuration.png)

### Minimum price per currency

To ensure a consistent customer experience across regions, RevenueCat enforces a minimum price per currency. These minimums are based on an approximate equivalent of $0.99 USD, rounded to a price that makes sense in the local market.
If you set a price below the minimum for a given currency, you'll receive a validation error when saving the product.

| Currency | Minimum Price |
| -------- | ------------- |
| USD      | $0.99         |
| EUR      | â¬0.99         |
| JPY      | Â¥99           |
| GBP      | Â£0.79         |
| AUD      | $0.99         |
| CAD      | $0.99         |
| BRL      | R$4.99        |
| KRW      | â©999          |
| CNY      | Â¥9.99         |
| MXN      | $19.99        |
| SEK      | 9.99-kr.      |
| PLN      | 3,99 zÅ       |
| AED      | 3.49 Ø¯.Ø¥      |
| BGN      | 1,49 Ð»Ð²       |
| CHF      | 0.99 Fr       |
| CLP      | $899          |
| COP      | $3,999        |
| CRC      | â¡499          |
| CZK      | 19,99 KÄ      |
| DKK      | 5,99 kr.      |
| GEL      | 2.49 GEL      |
| HKD      | HK$7.49       |
| HUF      | 299 Ft        |
| IDR      | Rp15.999      |
| ILS      | âª3.49         |
| IQD      | 999 Ø¯.Ø¹       |
| JOD      | 0.99 Ø¯.Ø£      |
| KES      | KSh 99        |
| KZT      | 499 â¸         |
| MAD      | 8.99 Ø¯.Ù.     |
| MYR      | RM3.99        |
| NOK      | 9,99 kr       |
| NZD      | $1.49         |
| PEN      | S/ 3.49       |
| PHP      | â±54.49        |
| QAR      | 3.49 Ø±.Ù      |
| RON      | 3,99 lei      |
| RSD      | 99 Ð´Ð¸Ð½.       |
| SAR      | 3.49 Ø±.Ø³      |
| SGD      | $0.99         |
| THB      | à¸¿29.99        |
| TWD      | NT$29.99      |
| TZS      | TSh 1,999     |
| VND      | 24.999â«       |
| ZAR      | R17.49        |

### Making a purchase

When a customer makes a purchase, RevenueCat will automatically select the price in the currency that best matches the customer's location. This happens regardless of whether the purchase is made through the Web SDK or a Web Purchase Link. If the customer's currency is not supported, RevenueCat will default to the default currency.

### Specifying a currency manually

#### Web SDK

If you want to specify a currency manually, you can do so by passing the `currency` parameter when calling the `getOfferings` method of the Web SDK. This will override the automatic currency selection.

*Interactive content is available in the web version of this doc.*

#### Web Purchase Links

When generating a Web Purchase Link, you can specify the currency by appending the `currency` query parameter to the URL. This will override the automatic currency selection.

Example:

```
https://pay.rev.cat/<paywall_ID>/<app_user_ID>?currency=EUR
```

### Differentiating prices in the same currency

Given that each product can have only one price per currency, if you want to offer different prices for the same product in the same currency, you will need to create a new product with a different identifier. You can then use [targeting](/tools/targeting) to show the correct product to the customer based on their location or other criteria.
