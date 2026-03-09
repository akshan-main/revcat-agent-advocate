---
id: "integrations/data-onboarding"
title: "Data Onboarding"
description: "So, you're a data person, huh? Well youâre in luck, because we have a lot of it. Here, weâll cover some of the basics to help you get started with RevenueCat."
permalink: "/docs/integrations/data-onboarding"
slug: "data-onboarding"
version: "current"
original_source: "docs/integrations/data-onboarding.md"
---

So, you're a data person, huh? Well youâre in luck, because we have a lot of it. Here, weâll cover some of the basics to help you get started with RevenueCat.

## Core Data Definitions

Letâs start with some definitions to help you understand & analyze your RevenueCat data. You can think about the following core metrics as foundational measures for your conversion funnel.

- New Customers: 'New Customers' includes the number of unique users (App User IDs) created in a given time window. Multiple App User IDs aliased together will be counted as 1 New Customer. Note: New Customers â  Active Subscribers. New Customers simply represents new users that were seen in your app.
- Initial Conversions: Customers that converted on any product or subscription within the specified Conversion Timeframe
- Active Subscriptions: Active Subscriptions shows the number of unexpired, paid subscriptions. This includes active paid subscriptions which may be cancelled, or within a grace period, until they expire.

## Example Chart: Trial Conversions

This becomes a bit more nuanced when observing all current states of your users, including trials, pending conversions, and abandons. A chart that data engineers reference frequently is Trial Conversion Chart, which gives a detailed view into the conversion funnel, from New Customer to Trials Started, Converted, Pending & Abandoned.

- Trials Started: The number of new customers that were first seen during the cohort period.
- Conversion Rate: The number of trials started by customers in this cohort.
- Pending Rate: The number of active trials that are set to auto-convert on completion.
- Abandon Rate: The number of trials that have completed without converting or that are active but are not set to auto-convert on completion.

## Solving Common Data Challenges with RevenueCat

1. Cross-platform reporting: combining data from multiple sources (e.g. app stores) can be difficult (to say the least) due to lack of common identifiers, differences in definitions in different sources, and delayed data availability. RevenueCat eliminates the need to deduce complex data formats from app stores, which are formatted for transaction processing, not analytics use cases. Read more about Scheduled Date Exports & 3rd Party Integrations.
2. Leveraging Custom User Attributes: organizing customer data to attach to targeted offers, pricing, packaging & paywalls is especially challenging given the above cross-platform challenges. RevenueCat Targeting allows you to use ready-made filters to strategically group your users by any custom attribute you define; or by dimensions like country, app platform, app version, RevenueCat SDK version. Watch the Video
3. Monitoring state changes in subscribers: RevenueCat Events notify you in near real-time to any changes that occur to a customer's subscription and can automatically be sent into a variety of third-party tools to get clean data in all of your systems.

RevenueCat events work by connecting directly to the app stores, meaning they are not dependent on any in-app usage or activity and are always sent from RevenueCat's servers. Server-side event detection is crucial for subscription apps since most interesting events occur when your app is inactive (e.g. trial conversions, renewals, cancellations, etc.).

Read more about Events and explore Common Webhook Flows used to notify you throughout a customerâs journey.

### More Popular Features & FAQs

1. Cohorts & Conversion Timeframes
2. Date Range Options & Conversion Windows
3. Common Data Discrepancies
4. Events Overview & Getting Data Out of RevenueCat
5. Scheduled Data Exports
6. 3rd Party Integrations
