---
id: "integrations/third-party-integrations/mparticle"
title: "mParticle"
description: "mParticle can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use mParticle to clean up your data infrastructure and collect new customer data, which can then be connected with other tools through mParticleâs powerful API."
permalink: "/docs/integrations/third-party-integrations/mparticle"
slug: "mparticle"
version: "current"
original_source: "docs/integrations/third-party-integrations/mparticle.mdx"
---

mParticle can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use mParticle to clean up your data infrastructure and collect new customer data, which can then be connected with other tools through mParticleâs powerful API.

With our mParticle integration, you can:

- Use the API to identify users who are at risk of churning and begin a campaign to win them back.
- Set up push notifications and emails to users who have subscribed to your product but do not engage very much.

With accurate and up-to-date subscription data in mParticle, you'll be set to turbocharge your campaigns â¡ï¸

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events | Optional Event Types |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :------------------: |
|        â        |            â             |          â          |              â              |          â           |          â          |

## Events

The mParticle integration tracks the following events:

| Event                     | Default Event Name           | Description                                                                                                                                                                                                                                                                                                                                 | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | initial\_purchase             | A new subscription has been purchased.                                                                                                                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Started             | trial\_started                | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Converted           | trial\_converted              | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Trial Cancelled           | trial\_cancelled              | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Renewal                   | renewal                      | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                                                                                                | â        | â         | â     | â     | â    |
| Cancellation              | cancellation                 | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                                                                                                 | â        | â         | â     | â     | â    |
| Uncancellation            | uncancellation               | A non-expired cancelled subscription has been re-enabled.                                                                                                                                                                                                                                                                                   | â        | â         | â     | â     | â    |
| Non Subscription Purchase | non\_renewing\_purchase        | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                                                                                                    | â        | â         | â     | â     | â    |
| Subscription Paused       | rc\_subscription\_paused\_event | A subscription has been paused.                                                                                                                                                                                                                                                                                                             | â        | â         | â     | â     | â    |
| Expiration                | expiration                   | A subscription has expired and access should be removed. If you have [Platform Server Notifications](/platform-resources/server-notifications) configured, this event will occur as soon as we are notified (within seconds to minutes) of the expiration. If you do not have notifications configured, delays may be approximately 1 hour. | â        | â         | â     | â     | â    |
| Billing Issues            | billing\_issue                | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                                                                                          | â        | â         | â     | â     | â    |
| Product Change            | product\_change               | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades.                                                                         | â        | â         | â     | â     | â    |
| Refund                    | refund                       | When a user canceled their subscription via customer support.                                                                                                                                                                                                                                                                               | â        | â         | â     | â     | â    |
| Transfer                  | rc\_transfer\_event            | A transfer of transactions and entitlements was initiated between one App User ID(s) to another. (Interactive content is available in the web version of this doc.) (Interactive content is available in the web version of this doc.)Please note: Two events will be sent for each transfer, one for the original user and another for the destination user.                                                                                                         | â        | â         | â     | â     | â    |

For events that have revenue, such as trial conversions and renewals, RevenueCat will automatically record this amount along with the event in mParticle.

## Setup

### 1. Set mParticle User Identity and Send Device Data to RevenueCat

If you're using the mParticle SDK, you can set the User ID to match the RevenueCat App User Id. This way, events sent from the mParticle SDK and events sent from RevenueCat can be synced to the same user.

The mParticle integration also requires some device-specific data. RevenueCat will only send events into mParticle if the below [Attribute](/customers/customer-attributes) keys have been set for the device.

| Key            | Description                                                                                                                                     | Required         |
| :------------- | :---------------------------------------------------------------------------------------------------------------------------------------------- | :--------------- |
| `$mparticleId` | The unique mParticle user identifier (mpid).                                                                                                    | â (recommended) |
| `$idfa`        | iOS [advertising identifier](https://developer.apple.com/documentation/adsupport/asidentifiermanager/1614151-advertisingidentifier) UUID        | â (optional)    |
| `$idfv`        | iOS [vendor identifier](https://developer.apple.com/documentation/uikit/uidevice/1620059-identifierforvendor) UUID                              | â (optional)    |
| `$gpsAdId`     | Google [advertising identifier](https://developers.google.com/android/reference/com/google/android/gms/ads/identifier/AdvertisingIdClient.Info) | â (optional)    |
| `$ip`          | The IP address of the device                                                                                                                    | â (optional)    |

:::warning Android ID deprecation
Due to policy changes from the Play Store, Android ID is no longer collected by RevenueCat's Android SDKs starting on versions 6.9.8+, 7.11.1+, and later major versions.

Therefore, Google's Advertising ID acts as the primary device identifier for Android devices in RevenueCat and when connecting with third-party integrations.
:::

These properties can be set manually, like any other [Attribute](/customers/customer-attributes), or through the helper methods `collectDeviceIdentifiers()` and `setMparticleId()`.

Create an `identityRequest` and add it to the `MParticleOptions` that you pass to the `start()` method on the mParticle SDK to set the same App User Id that is set in RevenueCat.

*Interactive content is available in the web version of this doc.*

mParticle also allows you to log a user in after starting the SDK and log a user out; you should handle both of these cases:

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*

:::danger Device identifiers with iOS App Tracking Transparency (iOS 14.5+)
If you are requesting the App Tracking permission through ATT to access the IDFA, you can call `.collectDeviceIdentifiers()` *again* if the customer accepts the permission to update the `$idfa` attribute in RevenueCat.
:::

### 2. Add RevenueCat Feed Inputs in mParticle

In mParticle, add the RevenueCat feed input and create two feeds: one for the Android platform and one for the iOS platform. Copy each feed's Server to Server Key and Server to Server Secret for setup on RevenueCat. Refer to [mParticle's documentation](https://docs.mparticle.com/guides/feeds/) to learn more about feeds.

:::warning
RevenueCat requires [Create & Update Profile](https://docs.mparticle.com/guides/personalization/profiles/#input-protections) permissions in order to send purchase & subscription lifecycle events into mParticle.
:::

![Add RevenueCat feed inputs](/docs_images/integrations/third-party-integrations/mparticle/add-revenuecat-feed-inputs.png)

### 3. Send RevenueCat events to mParticle

After you've set up the *Purchases SDK* and mParticle SDK to have the same user identity, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

1. Navigate to your project settings in the RevenueCat dashboard and choose 'mParticle' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Add your **Server to Server Keys** and **Server to Server Secrets** for each platform from step 2
3. Enter the event names that RevenueCat will send or choose the default event names
4. Select whether you want sales reported as gross revenue (before app store commission), or after store commission and/or estimated taxes.

### 4. Testing the mParticle integration

You can test the mParticle integration end-to-end before going live. It's recommended that you test the integration is working properly for new users, and any existing users that may update their app to a new version.

#### Make a sandbox purchase with a new user

Simulate a new user installing your app, and go through your app flow to complete a sandbox purchase.

#### Check that the required device data is collected

Navigate the the [Customer View](/dashboard-and-metrics/customer-profile#customer-details) for the test user that just made a purchase. Make sure that all of the required data from step 1 above is listed as attributes for the user.

![](/docs_images/integrations/third-party-integrations/mparticle/mparticle-device-data.png)

#### Check that the mParticle event delivered successfully

While still on the Customer View, click into the test purchase event in the [Customer History](/dashboard-and-metrics/customer-profile) and make sure that the mParticle integration event exists and was delivered successfully.

![](/docs_images/integrations/third-party-integrations/mparticle/event-delivered.png)

:::success
You should start seeing events from RevenueCat appear in mParticle
:::

## Sample Events

Below are sample JSONs that are delivered to mParticle for the different event types.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*
