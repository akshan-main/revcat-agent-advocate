---
id: "integrations/third-party-integrations/statsig"
title: "Statsig"
description: "Statsig can be a helpful integration for optimizing purchases and revenue, and understanding which features are causing product metrics to move. RevenueCat can automatically send billing, subscription, and revenue metrics to your Statsig project."
permalink: "/docs/integrations/third-party-integrations/statsig"
slug: "statsig"
version: "current"
original_source: "docs/integrations/third-party-integrations/statsig.mdx"
---

Statsig can be a helpful integration for optimizing purchases and revenue, and understanding which features are causing product metrics to move. RevenueCat can automatically send billing, subscription, and revenue metrics to your Statsig project.

With our Statsig integration, you can:

- Compute how every new product improvement impacts your business metrics
- Simplify setting up Feature Gates and be able to automatically A/B test new features
- Run multiple independent experiments in parallel

With accurate and up-to-date subscription data in Statsig, you'll be set to turbocharge your product analytics â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events  | Includes Customer Attributes | Sends Transfer Events | Optional Event Types |
| :--------------: | :-----------------------: | :-------------------: | :--------------------------: | :-------------------: | :------------------: |
|        â        |            â             | Toggle on in Settings |              â              |          â           |          â          |

## Events

The Statsig integration tracks the following events:

| Event Type                | Default Event Name                   | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | `rc_initial_purchase_event`          | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Renewal                   | `rc_renewal_event`                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | `rc_cancellation_event`              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Uncancellation            | `rc_uncancellation_event`            | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                                                                                                   | â        | â         | â     | â     | â    |
| Non Subscription Purchase | `rc_non_subscription_purchase_event` | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Subscription Paused       | `rc_subscription_paused_event`       | A subscription has been paused.                                                                                                                                                                                                                                                                                                             | â        | â         | â     | â     | â    |
| Expiration                | `rc_expiration_event`                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issue             | `rc_billing_issue_event`             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Transfer                  | `rc_transfer_event`                  | A transfer of transactions and entitlements was initiated between one App User ID(s) to another. Please note: Two events will be sent for each transfer, one for the original user and another for the destination user.                                                                                                                    | â        | â         | â     | â     | â    |

## 0. Matching RevenueCat Users with Statsig Users

In order to associate RevenueCat data with Statsig feature gate and/or experiment, the RevenueCat app user ID must match the Statsig User ID. You can read more about Statsig user IDs in their documentation [here](https://docs.statsig.com/server/pythonSDK#statsiguser). You can set up a custom app user ID in RevenueCat by following the instructions in our [Identifying Users](/customers/user-ids#provided-app-user-id) documentation.

## 1. Enable RevenueCat integration with Statsig

On the Statsig [Integration page](https://console.statsig.com/integrations) enable the RevenueCat integration.

![Enable RevenueCat in Statsig integration page](/docs_images/integrations/third-party-integrations/statsig/enable-statsig-integration.png)

## 2. Send RevenueCat events into Statsig

After you enabled the RevenueCat integration in Statsig's dashboard, you can "turn on" the integration from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Statsig' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your ['statsig-server-secret'](https://docs.statsig.com/feature-gates/implement/server#step-1-get-the-statsig-server-secret-key)

## 3. Testing the Statsig integration

Ingesting sandbox events into Statsig can be enabled in the RevenueCat configuration in the Statsig [Integration page](https://console.statsig.com/integrations).

![Include Sandbox Events in Statsig integration page](/docs_images/integrations/third-party-integrations/statsig/enable-sandbox-events.png)

### Make a sandbox purchase with a new user

Simulate a new user installing your app, and go through your app flow to complete a sandbox purchase.

### Check that the Statsig event delivered successfully

While still on the Customer View, select test purchase event in the [Customer History](/dashboard-and-metrics/customer-profile) page and make sure that the Statsig integration event exists and was delivered successfully.

![](/docs_images/integrations/third-party-integrations/statsig/successful-event.png)

### Check Statsig dashboard for the delivered event

Navigate to your Statsig app > Metrics. You will see events RevenueCat has dispatched to Statsig under 'Log Stream'.

![](/docs_images/integrations/third-party-integrations/statsig/statsig-successful-event.png)

## Sample Events

Below are sample JSONs that are delivered to Statsig for each event type.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*

:::success You've done it!
You should start seeing subscription data from RevenueCat appear in Statsig.
:::
