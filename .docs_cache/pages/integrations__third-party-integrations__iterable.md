---
id: "integrations/third-party-integrations/iterable"
title: "Iterable"
description: "Iterable can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. Iterable is a cross-channel platform that powers unified customer experiences and empowers marketers to create, optimize and measure every interaction taking place throughout the customer journey. With Iterable, brands create individualized marketing touch points that earn engagement, solidify trust and galvanize loyal consumer-brand relationships."
permalink: "/docs/integrations/third-party-integrations/iterable"
slug: "iterable"
version: "current"
original_source: "docs/integrations/third-party-integrations/iterable.mdx"
---

Iterable can be a helpful integration tool in understanding what stage a customer is in and reacting accordingly. Iterable is a cross-channel platform that powers unified customer experiences and empowers marketers to create, optimize and measure every interaction taking place throughout the customer journey. With Iterable, brands create individualized marketing touch points that earn engagement, solidify trust and galvanize loyal consumer-brand relationships.

With our Iterable integration, you can:

- Create an event to track unsubscribes that automatically triggers an email to users who cancel.
- Start a campaign to send users who have been with you for over a certain length of time a discount code for being a loyal customer.

With accurate and up-to date subscription data in Iterable, youâll be set to turbocharge your usersâ engagement â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events |                                                                 Optional Event Types                                                                 |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------: |
|        â        |            â             |   Requires API Key   |              â              |          â           | `non_subscription_purchase_event` `uncancellation_event` `subscription_paused_event` `expiration_event` `billing_issue_event` `product_change_event` |

## Events

The Iterable integration tracks the following events:

| RevenueCat Event Type     | Iterable Event Type | Default Event Name                 | Description                                                                                                                                                                                                                                                         | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | Purchase            | rc\_initial\_purchase\_event          | A new subscription has been purchased.                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Started             | Purchase            | rc\_trial\_started\_event             | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Converted           | Purchase            | rc\_trial\_converted\_event           | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Trial Cancelled           | Custom              | rc\_trial\_cancelled\_event           | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                | â        | â         | â     | â     | â    |
| Renewal                   | Purchase            | rc\_renewal\_event                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Cancellation              | Custom              | rc\_cancellation\_event              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                         | â        | â         | â     | â     | â    |
| Uncancellation            | Custom              | rc\_uncancellation\_event            | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                           | â        | â         | â     | â     | â    |
| Non Subscription Purchase | Purchase            | rc\_non\_subscription\_purchase\_event | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                            | â        | â         | â     | â     | â    |
| Subscription Paused       | Custom              | rc\_subscription\_paused\_event       | A subscription has been paused.                                                                                                                                                                                                                                     | â        | â         | â     | â     | â    |
| Expiration                | Custom              | rc\_expiration\_event                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration.          | â        | â         | â     | â     | â    |
| Billing Issue             | Custom              | rc\_billing\_issue\_event             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                  | â        | â         | â     | â     | â    |
| Product Change            | Custom              | rc\_product\_change\_event            | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades. | â        | â         | â     | â     | â    |

For events that have revenue, such as trial conversions and renewals, RevenueCat will automatically record this amount along with the event in Iterable. Bear in mind that revenue will always be reported in USD. If it's been made with a different currency, we'll automatically convert it to USD. You can find the currency of the original transaction in the `currency` field of the event.

## Setup

### 1. Set Iterable User Identity

In order to associate RevenueCat data with the Iterable User Profile, either the RevenueCat `$email` or `$iterableUserId` [Attribute](/customers/customer-attributes) should be set in RevenueCat. The preferred method is to send the `$email` attribute. If neither of these fields exist, RevenueCat will fallback to the RevenueCat app user ID. You can read more about Iterable user profiles in Iterable's [Identifying the User](https://support.iterable.com/hc/en-us/articles/360035402531-Identifying-the-User-) documentation.

:::info `$iterableUserId` character limit
The `$iterableUserId` can be up to 52 characters long.
:::

### (optional) Set Iterable Campaign ID and/or Template ID

To attribute an event to an Iterable Campaign ID and/or Template ID, set the `$iterableCampaignId` and/or `$iterableTemplateId` attributes through the RevenueCat SDK or [REST API](https://docs.revenuecat.com/reference/update-subscriber-attributes).

*Interactive content is available in the web version of this doc.*

### 2. Send RevenueCat Events to Iterable

After you've set up the Purchase SDK and Iterable SDK to have the same user identity, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Iterable' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your Iterable [Server-side API key](https://support.iterable.com/hc/en-us/articles/360043464871-API-Keys-#creating-api-keys) to the **API key** field in RevenueCat
3. Enter the event names that RevenueCat will send or choose the default event names
4. Select whether you want sales reported as gross revenue (before app store commission), or after store commission and/or estimated taxes.

:::info Iterable sandbox environment
Iterable recommends having a production and sandbox project to separate live and testing environments. You can input both keys in the RevenueCat Iterable settings page.
:::

## Testing the Iterable integration

### Make a sandbox purchase with a new user

Simulate a new user installing your app, and go through your app flow to complete the [sandbox purchase](/test-and-launch/sandbox).

### Check that the Iterable event delivered successfully

While still on the Customer View, select the purchase event in the [Customer History](/dashboard-and-metrics/customer-profile) page and make sure that the Iterable integration event exists and was delivered successfully.

![](/docs_images/integrations/third-party-integrations/iterable/successful-event.png)

### Check Iterable dashboard for the delivered event

Navigate to your Iterable dashboard > Insights > Logs. To find Purchase events navigate to 'Purchases' and to find Custom events navigate to 'Events'. You will see events RevenueCat has dispatched to the Iterable under 'Purchase Log' and 'Events log' respectively.

![](/docs_images/integrations/third-party-integrations/iterable/iterable-purchase-log.png)

![](/docs_images/integrations/third-party-integrations/iterable/iterable-events-log.png)

## Sample Events

Below are sample JSONs that are delivered to Iterable for events.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*

## Considerations

### Refunds

Revenue for Iterable campaign reporting will not be accurate due to refund events. You can build custom workflows around a "refund" event and independently calculate the total revenue refunded for your campaigns.

### Purchase event tracking

Iterable provides two event-tracking APIs:

- [Track Purchase API](https://api.iterable.com/api/docs#commerce_trackPurchase): This aggregates all purchase-related events into a single purchase event for tracking overall revenue. However, it does not distinguish between the types of purchase events (like initial purchases, trials, renewals, etc.).
- [Track Custom Event API](https://api.iterable.com/api/docs#events_track): While it allows for detailed tracking of individual purchase events, it doesn't support revenue tracking as that is exclusive to the Track Purchase API.

You have the flexibility to use one or both APIs depending on whether you need detailed insights into specific events or an aggregate revenue perspective.

Ensure [Allow new custom events into the system](https://support.iterable.com/hc/en-us/articles/115002065083-Managing-Custom-Events-#event-handling-for-newly-encountered-events) is enabled in your Iterable project settings, or manually add all the event names you want to track as custom events to the Iterable project settings.

Learn more about tracking events with this integration in Iterable RevenueCat's [documentation](https://support.iterable.com/hc/en-us/articles/5167223724436-RevenueCat-Iterable-Integration-#in-iterable) or Iterable's [tracking docs](https://support.iterable.com/hc/en-us/articles/205480285-Tracking-Conversions-Purchases-and-Revenue-#step-4-track-custom-events-and-purchases).
