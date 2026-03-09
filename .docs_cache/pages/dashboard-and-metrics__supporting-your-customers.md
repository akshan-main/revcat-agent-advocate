---
id: "dashboard-and-metrics/supporting-your-customers"
title: "Supporting Your Customers"
description: "As the central location for all your subscription data, RevenueCat is a power tool for supporting your customers with questions about their subscriptions. From looking up a customerâs purchase history to issuing refunds to granting promotional entitlements, your customer support team has lots of tools at their fingertips in the RevenueCat Dashboard."
permalink: "/docs/dashboard-and-metrics/supporting-your-customers"
slug: "supporting-your-customers"
version: "current"
original_source: "docs/dashboard-and-metrics/supporting-your-customers.md"
---

As the central location for all your subscription data, RevenueCat is a power tool for supporting your customers with questions about their subscriptions. From looking up a customerâs purchase history to issuing refunds to granting promotional entitlements, your customer support team has lots of tools at their fingertips in the RevenueCat Dashboard.

**Video:** Watch the video content in the hosted documentation.

## Inviting your customer support team to RevenueCat

In order for your customer support team to take advantage of RevenueCatâs features, they first need access to RevenueCat!

The âSupportâ role was developed specifically with this use case in mind. Collaborators with this permission can manage individual customers, including Customer Timelines, grant Promotional Entitlements, issue refunds, and delete customers. However, theyâre not able to view any financial data or access most app settings.

Of course, you can also give your support team one of the other RevenueCat roles if you wish them to have access to more data and functionality. See how to invite a collaborator and learn about other permission options here.

## Looking up customers in RevenueCat

How you look up customers will depend partially on your implementation and what data youâre passing into RevenueCat.

All customers can be found by searching for an App User ID, Transaction ID, or Order ID (iOS only). In order to find a customer via their email, you must be passing email as a custom attribute to RevenueCat.

To find a customer, visit the Customer tab in the RevenueCat dashboard and look for the search box. You must enter a search term that exactly matches one of the above options.

To learn more about finding individual customers visit [Find an Individual Customer](/dashboard-and-metrics/customer-lists#find-an-individual-customer).

## Reviewing a customerâs subscription history

RevenueCat knows a lot about your customers from when they were first seen using the app, to when they made their first purchase, and even to when their subscription most recently renewed.

All of these events can be found in the Customer History on the Customerâs profile. Learn more about the specific event types and the additional details they contain from our [Customer History](/dashboard-and-metrics/customer-profile) documentation.

## Managing customer subscriptions

Not only can you see information about your customerâs subscriptions in the RevenueCat dashboard, but you can also perform certain actions (without ever needing to log into the stores).

Here are some of the ways you can make changes to a customerâs subscription from RevenueCat:

- *Issue a refund* - Google Play purchases and purchases made through Web Billing (formerly RevenueCat Billing) can be refunded directly through the RevenueCat dashboard. To refund a purchase, find the transaction event in the customer history and click âRefundâ in the upper right corner. To learn more about how refunds work for Apple, Amazon, and Stripe, visit [Handling Refunds](/subscription-guidance/refunds).
- *Cancel a subscription* - If a subscription was purchased through Web Billing, you can also cancel that purchase from the RevenueCat dashboard. To cancel a subscription, click on the "..." menu on the subscription in the "Entitlements" card of the customer profile and then select "Cancel subscription". Learn more about managing subscriptions with Web Billing [here](/web/web-billing/managing-customer-subscriptions).
- *Transfer a subscription* - In some cases you may want to manually transfer a subscription to a different user. The âTransferâ functionality can be found in the upper right corner of the customer profile page in the Entitlements section (details [here](/dashboard-and-metrics/customer-profile#entitlements#transferring-entitlements) ). Please note that when you transfer a subscription you are not changing the underlying App Store account (for instance, the Apple Account) that owns the subscription. Because of this, the subscription may automatically be transferred again when the user restores purchases. The exact behavior will depend on your RevenueCat Projectâs settings for [restoring purchases](/getting-started/restoring-purchases#transferring-purchases-seen-on-multiple-app-user-ids).
- *Grant a promotional entitlement* - With promotional entitlements you can also use RevenueCat to give users access to your products without involving any third party platform. For example, if you want to give a VIP user or a fellow employee free access to your app, you could grant them a promotional entitlement. Keep in mind this is purely a RevenueCat concept and therefore doesnât change anything about a subscription they may have through the store. Learn more at our [Granted Entitlements](/dashboard-and-metrics/customer-profile#entitlements) documentation.

### More Popular Features & FAQs

1. [Customer History](/dashboard-and-metrics/customer-profile)
2. [Promotionals](/dashboard-and-metrics/customer-profile#entitlements)
3. [Customer Lists](/dashboard-and-metrics/customer-lists)
4. [Deleting Users](/dashboard-and-metrics/customer-profile#delete-customer)
5. [Active Entitlements](/dashboard-and-metrics/customer-profile#entitlements)
