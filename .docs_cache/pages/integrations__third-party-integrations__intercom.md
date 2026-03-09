---
id: "integrations/third-party-integrations/intercom"
title: "Intercom"
description: "Intercom can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. You can use Intercomâs comprehensive communication and engagement system to retain customers."
permalink: "/docs/integrations/third-party-integrations/intercom"
slug: "intercom"
version: "current"
original_source: "docs/integrations/third-party-integrations/intercom.mdx"
---

Intercom can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. You can use Intercomâs comprehensive communication and engagement system to retain customers.

With our Intercom integration, you can:

- Create Intercom filters for users that canceled free trials.
- Allow customer support to communicate with loyal users with access to all the information they need to solve their problem or even grant them a promotional subscription.
- Send an onboarding campaign to a user in a free trial

With accurate and up-to-date subscription data in Intercom, you'll be set to turbocharge your customer support â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events  | Includes Customer Attributes | Sends Transfer Events |                                       Optional Event Types                                        |
| :--------------: | :-----------------------: | :-------------------: | :--------------------------: | :-------------------: | :-----------------------------------------------------------------------------------------------: |
|        â        |            â             | Toggle on in Settings |              â              |          â           | `non_subscription_purchase_event` `expiration_event` `billing_issue_event` `product_change_event` |

## Events

The Intercom integration tracks the following events:

| Event Type                | Default Event Name                 | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | rc\_initial\_purchase\_event          | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Started             | rc\_trial\_started\_event             | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Converted           | rc\_trial\_converted\_event           | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Trial Cancelled           | rc\_trial\_cancelled\_event           | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Renewal                   | rc\_renewal\_event                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | rc\_cancellation\_event              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Non Subscription Purchase | rc\_non\_subscription\_purchase\_event | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Expiration                | rc\_expiration\_event                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issue             | rc\_billing\_issue\_event             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Product Change            | rc\_product\_change\_event            | rc\_product\_change\_event A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades.                                                 | â        | â         | â     | â     | â    |

## Setup

### 1. Connect with Intercom

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Intercom' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Choose **Intercom** from the Integrations menu

3. Click the **Connect with Intercom** button in your project settings.

4. Click **Authorize access**. If you have multiple workspaces, click the workspace name and choose the workspace you want to connect this RevenueCat project to. Also ensure the correct data host region is selected.

![](/docs_images/integrations/third-party-integrations/intercom/intercom-authorization-screen.png)

### 2. Set Event Names

Once your account is connected, you can configure the event names that we'll send to Intercom. If you leave any field blank, we'll just use our default names.

:::success You're all set!
That's all there is to it! You'll now be seeing subscription events in Intercom. Woohoo!
:::

### Sample Events

Below are sample JSONs that are delivered to Intercom for each event.

*Interactive content is available in the web version of this doc.*

## Subscription Status Attribute

:::info Intercom API V2
If you created your Intercom integration before February 2024, you may be using the Intercom API V1. If so, you'll need to upgrade to API V2 to receive the `subscription_status` attribute. You can upgrade from your Intercom integration page in RevenueCat.
:::

Whenever RevenueCat sends an event to Intercom, we'll send a `subscription_status` user custom attribute with any applicable changes, using one of the following values:

| Status              | Description                                                                                                                                |
| :------------------ | :----------------------------------------------------------------------------------------------------------------------------------------- |
| active              | The customer has an active, paid subscription which is set to renew at their next renewal date.                                            |
| intro               | The customer has an active, paid subscription through a paid introductory offer.                                                           |
| cancelled           | The customer has a paid subscription which is set to expire at their next renewal date.                                                    |
| grace\_period        | The customer has a paid subscription which has entered a grace period after failing to renew successfully.                                 |
| trial               | The customer is in a trial period which is set to convert to paid at the end of their trial period.                                        |
| cancelled\_trial     | The customer is in a trial period which is set to expire at the end of their trial period.                                                 |
| grace\_period\_trial  | The customer was in a trial period and has now entered a grace period after failing to renew successfully.                                 |
| expired             | The customer's subscription has expired.                                                                                                   |
| promotional         | The customer has access to an entitlement through a RevenueCat [Granted Entitlement](/dashboard-and-metrics/customer-profile#entitlements) |
| expired\_promotional | The customer previously had access to an entitlement through a RevenueCat Granted Entitlement that has since expired.                      |
| paused              | The customer has a paid subscription which has been paused and is set to resume at some future date.                                       |

For customers with multiple active subscriptions, this attribute will represent the status of only the subscription for which the most recent event occurred.

Please note that since this attribute is set and updated when events are delivered, subscribers with events prior to our release of this attribute (during January 2024) will not have this attribute set until/unless a future event (renewal, cancellation, etc) occurs.
