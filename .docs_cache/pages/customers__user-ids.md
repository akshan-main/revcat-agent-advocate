---
id: "customers/overview"
title: "Customers in RevenueCat"
description: "In RevenueCat, the term \"customer\" refers to the person using an app that utilizes RevenueCat to handle or track the user's purchases. Customers are referenced by an identifier called an App User ID, which is used as a source of truth for the subscription status of the customer across different devices and platforms."
permalink: "/docs/customers/user-ids"
slug: "user-ids"
version: "current"
original_source: "docs/customers/overview.md"
---

In RevenueCat, the term "customer" refers to the person using an app that utilizes RevenueCat to handle or track the user's purchases. Customers are referenced by an identifier called an `App User ID`, which is used as a source of truth for the [subscription status](/customers/customer-info) of the customer across different devices and platforms.

Customers may be referenced by multiple App User IDs, also known as aliases. Each grouping of App User IDs is considered to be a single customer in RevenueCat.

## Identifying Customers

By default, the RevenueCat SDK will generate anonymous App User IDs for customers. These IDs are generated when the SDK is first initialized, and are used to identify customers in the RevenueCat system.

Alternatively, you can provide a custom App User ID for a customer. This can be useful if you want to identify a customer using an identifier that you already have, such as a database identifier or a user ID from your own backend.

Some apps may use a combination of both anonymous and custom App User IDs, or only one App User ID type.

How to identify customers â

## Getting Subscription Status

The `CustomerInfo` object contains all of the purchase and subscription data available about the user. This object is updated whenever a purchase or restore occurs and periodically throughout the lifecycle of your app. The latest information can always be retrieved by calling `getCustomerInfo()`:

How to get subscription status â

## Setting Customer Attributes

Attributes are useful for storing additional, structured information on a customer that can be referenced elsewhere.

How to set customer attributes â

## Finding a Customer

You can find a customer in the RevenueCat Dashboard by searching for their App User ID.

How to find a customer â

## Blocking a Customer

You can block fraudulent customers, or those that violate your app's Terms of Service, in the RevenueCat Dashboard.

How to block customers â
