---
id: "integrations/third-party-integrations/airship"
title: "Airship"
description: "Airship can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. You can design and trigger personalized Airship messages to customers based on purchase behavior."
permalink: "/docs/integrations/third-party-integrations/airship"
slug: "airship"
version: "current"
original_source: "docs/integrations/third-party-integrations/airship.mdx"
---

Airship can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. You can design and trigger personalized Airship messages to customers based on purchase behavior.

Use your RevenueCat events to send Custom Events to trigger messages with Airship. This means you can design personalized Airship [Journeys](https://docs.airship.com/guides/messaging/user-guide/journeys/about/) and [Automations](https://docs.airship.com/guides/messaging/user-guide/messages/automation/about/) based on purchase behavior.

With our Airship Integration, you can:

- Send a message to a user whose subscription experienced a billing issue.
- Send reminders to your app's message center when a user's trial is about to expire.

With accurate and up-to-date subscription data in Airship, you'll be set to turbocharge your users' engagement â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue |    Sends Sandbox Events    | Includes Customer Attributes | Sends Transfer Events |                                                               Optional Event Types                                                                |
| :--------------: | :-----------------------: | :------------------------: | :--------------------------: | :-------------------: | :-----------------------------------------------------------------------------------------------------------------------------------------------: |
|        â        |            â             | Requires Token and App key |              â              |          â           | `non_subscription_purchase_event` `uncancellation_event``subscription_paused_event``expiration_event``billing_issue_event` `product_change_event` |

## Events

The Airship integration tracks the following events:

| Event Type                | Default Event Name                   | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | `rc_initial_purchase_event`          | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Started             | `rc_trial_started_event`             | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Converted           | `rc_trial_converted_event`           | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Trial Cancelled           | `rc_trial_cancelled_event`           | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Renewal                   | `rc_renewal_event`                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | `rc_cancellation_event`              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Uncancellation            | `rc_uncancellation_event`            | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                                                                                                   | â        | â         | â     | â     | â    |
| Non Subscription Purchase | `rc_non_subscription_purchase_event` | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Subscription Paused       | `rc_subscription_paused_event`       | A subscription has been paused.                                                                                                                                                                                                                                                                                                             | â        | â         | â     | â     | â    |
| Expiration                | `rc_expiration_event`                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issue             | `rc_billing_issue_event`             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Product Change            | `rc_product_change_event`            | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades.                                                                         | â        | â         | â     | â     | â    |

For events that have revenue, such as trial conversions and renewals, RevenueCat will automatically record this amount along with the event in Airship.

## Setup

### 1. Set Airship User Identity

If you're using the Airship SDK, you can either send the channel ID to RevenueCat or set an Airship Named User to match the RevenueCat app user ID. The preferred method is to send the channel ID to RevenueCat. Either method you use will allow events sent from the Airship SDK and events sent from RevenueCat to be synced to the same user.

#### Set Airship User Identity Using Channel ID

Setting the Airship channel ID in RevenueCat is the preferred way for identifying users in Airship. Call `setAirshipChannelID` on the Purchases SDK to have RevenueCat use the channel ID to send events to Airship.

*Interactive content is available in the web version of this doc.*

#### \[Advanced Alternative] Set Airship User Identity Using Named Users

**Setting the Airship channel ID in RevenueCat is preferred over using Named Users, even if you have a user authentication system.** However, if you're already using Named Users in your Airship integration, you have the option to set the Named User in the Airship SDK as the same app user ID as RevenueCat. Ensure [Named Users is enabled in your Airship dashboard](https://docs.airship.com/guides/messaging/user-guide/project/enable-features/#named-users).

*Interactive content is available in the web version of this doc.*

### 2. Send RevenueCat Events to Airship

After you've set up the *Purchase* SDK and Airship SDK to have the same user identity, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Airship' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your [Airship app key and token](https://docs.airship.com/guides/admin/security/account-security/)
3. Select the location of your Airship cloud site
4. Enter the event names that RevenueCat will send or choose the default event names
5. Select whether you want sales reported as gross revenue (before app store commission), or after store commission and/or estimated taxes.

## Sample Events

Below are sample JSONs that are delivered to Airship for each event type.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*
