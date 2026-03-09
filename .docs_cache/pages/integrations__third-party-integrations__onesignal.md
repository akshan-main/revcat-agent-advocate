---
id: "integrations/third-party-integrations/onesignal"
title: "OneSignal"
description: "OneSignal can be a useful integration tool for understanding what stage a customer is in to react accordingly. RevenueCat can automatically update user tags in OneSignal with their latest subscription status."
permalink: "/docs/integrations/third-party-integrations/onesignal"
slug: "onesignal"
version: "current"
original_source: "docs/integrations/third-party-integrations/onesignal.mdx"
---

OneSignal can be a useful integration tool for understanding what stage a customer is in to react accordingly. RevenueCat can automatically update user tags in OneSignal with their latest subscription status.

With our OneSignal integration, you can:

- Send an onboarding campaign to a user in a free trial
- Send a message to churned users and [offer them a discount](/subscription-guidance/subscription-offers/ios-subscription-offers)

With accurate and up-to-date subscription data in OneSignal, you'll be set to turbocharge your campaigns â¡ï¸

For every auto-renewing subscription event in RevenueCat, the following tags get added or updated on the user in OneSignal. By leaving the tag blank in the RevenueCat dashboard, you can choose to not send any value for specific tag(s).

| Tag                          | Description                                                                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app_user_id`                | The RevenueCat App User Id that triggered the event                                                                                                        |
| `period_type`                | The latest period type for the purchase or renewal. Either: `TRIAL` (for free trials), `INTRO` (or introductory pricing), `NORMAL` (standard subscription) |
| `purchased_at`               | Epoch time in seconds of the latest subscription purchase or renewal                                                                                       |
| `expiration_at`              | Epoch time in seconds of the latest subscription expiration date                                                                                           |
| `store`                      | Either `APP_STORE`, `PLAY_STORE`, or `STRIPE`                                                                                                              |
| `environment`                | Either `SANDBOX` or `PRODUCTION`                                                                                                                           |
| `last_event_type`            | The latest event type from the user. Either: `INITIAL_PURCHASE`, `TRIAL_STARTED`, `TRIAL_CONVERTED`, `TRIAL_CANCELLED`, `RENEWAL`, `CANCELLATION`          |
| `product_id`                 | The latest subscription product identifier that the user has purchased or renewed                                                                          |
| `entitlement_ids`            | Comma separated string of RevenueCat Entitlement identifiers that the user unlocked                                                                        |
| `active_subscription`        | The value will be set to `true` on any purchase/renewal event, and `false` on `EXPIRATION`                                                                 |
| `subscription_status`        | See Subscription Status Attribute below                                                                                                                    |
| `grace_period_expiration_at` | If a billing issue occurs, we will send the date of the grace period expiration.                                                                           |

:::info Auto-renewing subscriptions only
RevenueCat only updates data tags in OneSignal in response to auto-renewing subscription events.
:::

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events | Optional Event Types |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :------------------: |
|        â        |            â             |          â          |              â              |          â           |          â          |

## Events

The OneSignal integration tracks the following events:

| Event                     | Default Event Name        | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | initial\_purchase          | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Started             | trial\_started             | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Converted           | trial\_converted           | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Trial Cancelled           | trial\_cancelled           | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Renewal                   | renewal                   | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | cancellation              | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Uncancellation            | uncancellation            | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                                                                                                   | â        | â         | â     | â     | â    |
| Non Subscription Purchase | non\_subscription\_purchase | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Subscription paused       | subscription\_paused       | A subscription has been paused.                                                                                                                                                                                                                                                                                                             | â        | â         | â     | â     | â    |
| Expiration                | expiration                | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issue             | billing\_issue             | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Product Change            | product\_change            | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades.                                                                         | â        | â         | â     | â     | â    |

## 1. Send device data to RevenueCat

### 1.1 User-centric API versions of OneSignal (v5 SDK and above)

The OneSignal integration requires some user-specific data. RevenueCat will only update users in OneSignal if the below data has been added as [Subscriber Attributes](doc:subscriber-attributes) for the user.

| Key                | Description                                                                                                    | Required |
| :----------------- | :------------------------------------------------------------------------------------------------------------- | :------- |
| `$onesignalUserId` | The [OneSignal ID](https://documentation.onesignal.com/docs/users#user-properties) used to represent the user. | â       |

This property can be set manually, like any other [Subscriber Attributes](doc:subscriber-attributes), or through the helper method `setOnesignalUserID()`.

Make sure to call OneSignal's [`login` method](https://documentation.onesignal.com/docs/mobile-sdk-reference#login-external-id) before sending the OneSignal Id as this may change.

You can [listen for changes to the OneSignal Id through their SDK](https://documentation.onesignal.com/docs/mobile-sdk-reference#addobserver-user-state), and send the value to RevenueCat. If you already have OneSignal set up, you should make sure that you're also sending the OneSignal Id for users that are updating to the latest version of your app.

*Interactive content is available in the web version of this doc.*

### 1.2 Device-centric API versions of OneSignal (v4 SDK and below)

The OneSignal integration requires some device-specific data. RevenueCat will only update users in OneSignal if the below data has been added as [Attributes](/customers/customer-attributes) for the Customer.

| Key            | Description                                                                                       | Required |
| :------------- | :------------------------------------------------------------------------------------------------ | :------- |
| `$onesignalId` | The [OneSignal Player Id](https://documentation.onesignal.com/docs/users#player-id) for the user. | â       |

This property can be set manually, like any other [Attribute](/customers/customer-attributes), or through the helper method `setOnesignalID()`.

You can listen for changes to the OneSignal Id through their SDK, and send the value to RevenueCat. If you already have OneSignal set up, you should make sure that you're also sending the OneSignal Id for users that are updating to the latest version of your app.

*Interactive content is available in the web version of this doc.*

## 2. Send RevenueCat events into OneSignal

After you've set up the *Purchases SDK* to send device data to RevenueCat, you can "turn on" the integration and configure the tag names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'OneSignal' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your **OneSignal App Id** and **OneSignal API key**.
3. Enter the tag names that RevenueCat should use, or choose the default tag names.

## 3. Testing the OneSignal integration

You can test the OneSignal integration end-to-end before going live. It's recommended that you test the integration is working properly for new users, and any existing users that may update their app to a new version.

### Make a sandbox purchase with a new user

Simulate a new user installing your app, and go through your app flow to complete a sandbox purchase.

### Check that the required device data is collected

Navigate the the [Customer View](/dashboard-and-metrics/customer-profile#customer-details) for the test user that just made a purchase. Make sure that all of the required data from step 1 above is listed as attributes for the user.

### Check that the OneSignal event delivered successfully

While still on the Customer View, click into the test purchase event in the [Customer History](/dashboard-and-metrics/customer-profile) and make sure that the OneSignal integration event exists and was delivered successfully.

![](/docs_images/integrations/third-party-integrations/onesignal/event-delivered.png)

## Sample Events

Below are sample JSONs that are delivered to OneSignal for events.

*Interactive content is available in the web version of this doc.*

:::warning Why are tags not working?
If your tags aren't working and RevenueCat is sending events successfully with 200 codes, check out [OneSignal's troubleshooting guide](https://documentation.onesignal.com/docs/faq-data-tags).
:::

:::success You've done it!
You should start seeing subscription data from RevenueCat appear on users in OneSignal.
:::

## Subscription Status Attribute

Whenever RevenueCat sends an event to OneSignal, we'll send a `subscription_status` user attribute with any applicable changes, using one of the following values:

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
