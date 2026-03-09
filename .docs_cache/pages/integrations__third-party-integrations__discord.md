---
id: "integrations/third-party-integrations/discord"
title: "Discord"
description: "The Discord integration is available to all users signed up after September '23, the legacy Starter and Pro plans, and Enterprise plans. If you're on a legacy Free plan and want to access this integration, migrate to our new pricing via your billing settings."
permalink: "/docs/integrations/third-party-integrations/discord"
slug: "discord"
version: "current"
original_source: "docs/integrations/third-party-integrations/discord.mdx"
---

:::success Pro Integration
The Discord integration is available to all users signed up after September '23, the legacy Starter and Pro plans, and Enterprise plans. If you're on a legacy Free plan and want to access this integration, migrate to our new pricing via your [billing settings](https://app.revenuecat.com/settings/billing).
:::

Receive instant updates on your Discord server from RevenueCat whenever a new purchase event occurs in your app.

## Events

The Discord integration tracks the following events:

| Event Type                | Default Event Name (Fallback)                                                        | Description                                                                                                                                                                                                                                                         | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | Customer \<user\_id> just started a subscription of \<product\_id>                     | A new subscription has been purchased.                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Started             | Customer \<user\_id> just started a free trial of \<product\_id>                       | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Converted           | Customer \<user\_id> just converted from a free trial of \<product\_id>                | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Trial Cancelled           | Customer \<user\_id> just cancelled their free trial of \<product\_id>                 | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                | â        | â         | â     | â     | â    |
| Renewal                   | Customer \<user\_id> just renewed their subscription of \<product\_id>                 | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Cancellation              | Customer \<user\_id> just cancelled their subscription of \<product\_id>               | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                         | â        | â         | â     | â     | â    |
| Non Subscription Purchase | Customer \<user\_id> just purchased \<product\_id>                                     | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                            | â        | â         | â     | â     | â    |
| Billing Issue             | Customer \<user\_id> got a billing issue on \<product\_id>                             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                  | â        | â         | â     | â     | â    |
| Product Change            | Customer \<user\_id> got a product change from \<old\_product\_id> to \<new\_product\_id> | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades. | â        | â         | â     | â     | â    |

## Configure Discord server

You need to configure your Discord server to authorize a webhook to post to your workspace. Please follow this Discord [article](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) on their website explaining how to set this up.

## Configure RevenueCat Integration

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Discord' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Enter the details into the Discord Integration section of your [dashboard](https://app.revenuecat.com).

:::success You're all set!
RevenueCat will start sending events into Discord!
:::

## Sample Events

Below are sample JSONs that are delivered to Discord for each event type.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*
