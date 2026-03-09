---
id: "integrations/third-party-integrations/mixpanel"
title: "Mixpanel"
description: "Mixpanel can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use Mixpanelâs array of product analytical tools to help get new customers, and engage and retain old customers."
permalink: "/docs/integrations/third-party-integrations/mixpanel"
slug: "mixpanel"
version: "current"
original_source: "docs/integrations/third-party-integrations/mixpanel.mdx"
---

Mixpanel can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use Mixpanelâs array of product analytical tools to help get new customers, and engage and retain old customers.

With our Mixpanel integration, you can:

- Formulate a data model using interactions between a user and your product.
- Use interactive reports to understand when a user converts and why.

With accurate and up-to-date subscription data in Mixpanel, you'll be set to turbocharge your product analytics â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events |                                                                 Optional Event Types                                                                 |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------: |
|        â        |            â             |    Requires Token    |              â              |          â           | `non_subscription_purchase_event` `uncancellation_event` `subscription_paused_event` `expiration_event` `billing_issue_event` `product_change_event` |

## Events

The Mixpanel integration tracks the following events:

| Event                     | Default Event Name                 | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | rc\_initial\_purchase\_event          | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Started             | rc\_trial\_started\_event             | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Converted           | rc\_trial\_converted\_event           | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Trial Cancelled           | rc\_trial\_cancelled\_event           | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Renewal                   | rc\_renewal\_event                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | rc\_cancellation\_event              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Uncancellation            | rc\_uncancellation\_event            | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                                                                                                   | â        | â         | â     | â     | â    |
| Non Subscription Purchase | rc\_non\_subscription\_purchase\_event | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Subscription Paused       | rc\_subscription\_paused\_event       | A subscription has been paused.                                                                                                                                                                                                                                                                                                             | â        | â         | â     | â     | â    |
| Expiration                | rc\_expiration\_event                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issues            | rc\_billing\_issue\_event             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Product Change            | rc\_product\_change\_event            | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades.                                                                         | â        | â         | â     | â     | â    |

For events that have revenue, such as trial conversions and renewals, RevenueCat will automatically record this amount along with the event in Mixpanel.

## Setup

### 1. Set Mixpanel User Identity

If you're using the Mixpanel SDK, you can set the Distinct Id to match the RevenueCat App User Id. This way, events sent from the Mixpanel SDK and events sent from RevenueCat can be synced to the same user.

Use the `.identify()` method on the Mixpanel SDK to set the same App User ID that is set in RevenueCat.

##### Reserved Mixpanel Customer Attribute

We recommend keeping the Mixpanel SDK identifier the same as RevenueCat's App User ID as described above. Alternatively, if you want Mixpanel events tied to a different identifier, you can set a attribute for `$mixpanelDistinctId` that is sent with events instead of RevenueCat's App User ID.

If a user has that attribute set it will be used instead of the RevenueCat App User ID in the Mixpanel events.

*Interactive content is available in the web version of this doc.*

### 2. Send RevenueCat Events to Mixpanel

After you've set up the *Purchases SDK* and Mixpanel SDK, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Mixpanel' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your Mixpanel Project token
3. Enter the event names that RevenueCat will send or choose the default event names
4. Select whether you want sales reported as gross revenue (before app store commission), or after store commission and/or estimated taxes.

## Sample Events

Below are sample JSONs that are delivered to Mixpanel for events.

*Interactive content is available in the web version of this doc.*

## Subscription Status Attribute

Whenever RevenueCat sends an event to Mixpanel, we'll update the `rc_subscription_status` user attribute with any applicable changes, using one of the following values:

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

Please note that since this attribute is set and updated when events are delivered, subscribers with events prior to our release of this attribute (during November 2023) will not have this attribute set until/unless a future event (renewal, cancellation, etc) occurs.
