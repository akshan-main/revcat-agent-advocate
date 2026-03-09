---
id: "integrations/third-party-integrations/posthog"
title: "PostHog"
description: "PostHog can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use PostHog's product analytics to find patterns in customer behavior and inform marketing strategies."
permalink: "/docs/integrations/third-party-integrations/posthog"
slug: "posthog"
version: "current"
original_source: "docs/integrations/third-party-integrations/posthog.mdx"
---

PostHog can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use PostHog's product analytics to find patterns in customer behavior and inform marketing strategies.

With our PostHog integration, you can:

- Create a behavioral cohort of customers based on specific actions, such as watching a specific episode of a show after subscribing. Follow a cohort throughout their lifecycle to realize overarching trends.
- Measure the path of a user from marketing material to the purchase of a subscription.

With accurate and up-to-date subscription data in PostHog, you'll be set to turbocharge your product analytics â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events |                                                                 Optional Event Types                                                                 |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------: |
|        â        |            â             |   Requires API key   |              â              |          â           | `non_subscription_purchase_event` `uncancellation_event` `subscription_paused_event` `expiration_event` `billing_issue_event` `product_change_event` |

## Events

The PostHog integration tracks the following events:

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

For events that have revenue, such as trial conversions and renewals, RevenueCat will automatically record this amount along with the event in PostHog. Bear in mind that revenue will always be reported in USD. If it's been made with a different currency, we'll automatically convert it to USD. You can find the currency of the original transaction in the `currency` field of the event.

## Setup

### 1. Set PostHog User Identity

In order to associate RevenueCat data with a PostHog User, the RevenueCat `$posthogUserId` [Attribute](/customers/customer-attributes) should be set in RevenueCat. If this field does not exist, RevenueCat will fallback to the RevenueCat app user ID. You can read more about PostHog user profiles in PostHog's [Identifying users](https://posthog.com/docs/product-analytics/identify) documentation.

### 2. Send RevenueCat Events to PostHog

After you've set up the Purchase SDK and PostHog SDK to have the same user identity, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'PostHog' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your PostHog [Project API key](https://posthog.com/docs/api) to the **API key** field in RevenueCat. The integration uses only public endpoints, so there is no need to set up personal API keys.
3. Enter the event names that RevenueCat will send or choose the default event names
4. Select whether you want sales reported as gross revenue (before app store commission), or after store commission and/or estimated taxes.

:::info PostHog sandbox environment
PostHog recommends having a production and sandbox project to separate live and testing environments. You can input both keys in the RevenueCat PostHog settings page.
:::

## Testing the PostHog integration

### Make a sandbox purchase with a new user

Simulate a new user installing your app, and go through your app flow to complete the [sandbox purchase](/test-and-launch/sandbox).

### Check that the PostHog event delivered successfully

While still on the Customer View, select the purchase event in the [Customer History](/dashboard-and-metrics/customer-profile) page and make sure that the PostHog integration event exists and was delivered successfully.

![Check that the PostHog event was delivered](/docs_images/integrations/third-party-integrations/posthog/posthog-event-details.png)

### Check the PostHog dashboard for the delivered event

Navigate to your PostHog dashboard > People and groups. In the 'People & groups' tab, you will see the event's user created as a Person.

![Check that a PostHog Person has been created](/docs_images/integrations/third-party-integrations/posthog/posthog-people-and-groups.png)

Navigate to your PostHog dashboard > Data management. In the 'Events' tab, you will see events RevenueCat has dispatched to PostHog.

![Check that a PostHog Event has been created](/docs_images/integrations/third-party-integrations/posthog/posthog-events-list.png)

## Sample Events

Below are sample JSONs that are delivered to PostHog for events.

*Interactive content is available in the web version of this doc.*

## Subscription Status Attribute

Whenever RevenueCat sends an event to PostHog, we'll update the `rc_subscription_status` user attribute with any applicable changes, using one of the following values:

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
