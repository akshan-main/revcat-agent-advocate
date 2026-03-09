---
id: "getting-started/installation/roku"
title: "Roku"
description: "General setup"
permalink: "/docs/getting-started/installation/roku"
slug: "roku"
version: "current"
original_source: "docs/getting-started/installation/roku.mdx"
---

## General setup

### Prerequisites

#### Setting up your Roku developer account

Follow the [First Steps](https://developer.roku.com/en-gb/docs/developer-program/getting-started/first-steps.md) guide to create a Roku developer account, log in to your Roku device and enable developer mode on your Roku device.

#### Setting up your Roku channel

Once you have your developer account created, head to the [dashboard](https://developer.roku.com/dev/dashboard)

1. First, [create a new Channel](https://developer.roku.com/en-gb/docs/developer-program/publishing/channel-publishing-guide.md#create-a-channel).
2. If you want to use this channel for testing, make sure the channel is [enabled for billing testing](https://developer.roku.com/en-gb/docs/developer-program/roku-pay/testing/billing-testing.md).
3. Under "Monetization" -> "Test users", [add a test user](https://developer.roku.com/en-gb/docs/developer-program/roku-pay/quickstart/test-users.md) with the email associated to your Roku device.
4. Under "Monetization" -> "Product", follow the process to submit the tax documents, and after you're approved, you can [create in-channel products](/getting-started/entitlements/roku-products).

### App configuration

1. Make sure your project has been enabled to create Roku apps. If you're not sure, talk to your RevenueCat contact.
2. Open the RevenueCat dashboard, select your project, and go to "Apps & providers" to click "Add app config" > "Roku Channel Store".

![](/docs_images/projects/add-app-platform.png)

3. Navigate to the [Roku Pay Web Services page](https://developer.roku.com/rpay-web-services) to copy your Roku Pay API key and paste this to the RevenueCat dashboard under 'Roku Pay API Key'. The Roku Pay API key must be set before being able to select 'SAVE CHANGES'.

![](/docs_images/platform-resources/roku/roku-api-key.png)

![](/docs_images/platform-resources/roku/roku-configuration.png)

4. Once the app is created, click on the "Roku Server to Server notifications settings", copy the "Roku Push Notification URL" which starts with `https://api.revenuecat.com/v1/incoming-webhooks/roku-pay-jwt-notification`. Navigate back to your [Roku Pay Web Services page](https://developer.roku.com/rpay-web-services) (where you found the Roku API key) and scroll down until you see a section called 'Push Notifications' and paste RevenueCat's Push notifications URL in the text box.

![](/docs_images/platform-resources/roku/roku-notification-url.png)

![](/docs_images/platform-resources/roku/roku-notifications.png)
Remember to select 'SAVE CHANGES'

5. Back to the RevenueCat dashboard, click on "Public API Key" and copy over the value which should start with "roku\_XXXXXX". You will need it to configure the SDK later.

![](/docs_images/platform-resources/roku/revenuecat-api-key.png)

### Multi-channel support

The Roku channel ID is required for supporting multiple channels on a single Roku account. If your Roku account has more than one Roku Channel, you will need to enter your Channel ID for each Roku app on the RevenueCat dashboard.

1. Navigate to your [Roku Developer Dashboard](https://developer.roku.com/dev/dashboard).
2. On the left-hand side of the Developer Dashboard, you'll see the main navigation panel. Under 'Channel', navigate to where your channel is located (e.g: public or beta channels) and select the channel.
3. Find your Roku Channel ID and copy this value.

![](/docs_images/platform-resources/roku/roku-channel-id.png)

4. Back in the RevenueCat app settings page, enter your Roku Channel ID the 'Multi-channel support' expanded section.

![](/docs_images/platform-resources/roku/roku-multi-channel.png)

[](/docs_images/platform-resources/roku/roku-multi-channel.png)
Remember to select 'SAVE CHANGES'

### Product configuration

After you have configured the Roku Store app on RevenueCat, you should [create your in-channel products](/getting-started/entitlements/roku-products) and then follow RevenueCat's regular setup of [entitlements, products, and offerings](/getting-started/entitlements).

## Installing the SDK

[![Release](https://img.shields.io/github/release/RevenueCat/purchases-roku.svg?filter=!*beta*\&style=flat)](https://github.com/RevenueCat/purchases-roku/releases)

1. Clone the repository:

*Interactive content is available in the web version of this doc.*

2. Copy the `components/purchases` folder into your app's `components` folder.
3. Copy the `source/Purchases.brs` file into your app's `source` folder.
4. Import the SDK in the .xml file of the component where you want to use it:

*Interactive content is available in the web version of this doc.*

## Configuring the SDK

**Important:** The SDK should be used only from SceneGraph components. Calling it from the main thread or from a Task component is not supported.

Initialize the SDK with your api key. You typically do this inside the `init()` method of your main scene.

*Interactive content is available in the web version of this doc.*

## Callbacks and error handling

In methods of the SDK which perform async operations, you can get the result by passing a sub routine or a callback name.

- The first parameter will contain the result.
- The second parameter will contain an error if there was one, or `invalid` if there wasnt.

**Example:**

*Interactive content is available in the web version of this doc.*

## Models

### Subscriber

*Interactive content is available in the web version of this doc.*

### Offerings

*Interactive content is available in the web version of this doc.*

### Purchase

#### Making a purchase

As a parameter to the `purchase()` method, you can pass an associative array containing one of the following keys:

- `code`: A string containing the product id.
- `product`: From the `getOfferings` result: e.g. `offerings.current().annual.storeProduct`
- `package`: From the `getOfferings` result: e.g. `offerings.current().annual`

Additionally,you can pass the following optional parameters:

- `action`: To perform a product change. Valid values: `Upgrade` or `Downgrade`

#### Sync purchases

This method will post all purchases associated with the current Roku account to RevenueCat and become associated with the current User ID. It should only be used if you're migrating from using your own Roku Pay implementation and want to track previous purchases in RevenueCat.

*Interactive content is available in the web version of this doc.*

### Error

The error model contains two fields: `code` and `message`

*Interactive content is available in the web version of this doc.*

### Tying everything together

For most apps, the usage of the SDK would look like this:

1. Initialise the SDK
2. Log in the user
3. Check if the entitlement is active
4. Fetch offerings and show your paywall UI
5. Make a purchase

*Interactive content is available in the web version of this doc.*

## Testing

:::warning
Only the "root account user" can test billing on device. If you get added as a collaborator to someone else's developer account, billing testing will not work. You'll need to create your own developer account.
:::

Roku transactions **do not** have an "associated" environment. Both types of transactions arrive via push notifications, however, there are key differences between them.

- **Price differentiation**:
  - *Test purchases*: Always have a price of **0**
  - *Production purchases*: Will have a non-zero price (unless it's a trial)
- **Charges**:
  - *Test purchases*: The end customer will not be charged for a test purchase
  - *Production purchases*: The end customer will be charged according to the product details (e.g: pricing tier, trials, offers, etc)

In order to perform a test purchase, a [test user must be created](https://developer.roku.com/en-gb/docs/developer-program/roku-pay/quickstart/test-users.md) and associated with the channel.

After that, the test user will be able to make test purchases on the channel, regardless of the installation method: Public, Beta or Sideloaded (Billing Testing must be enabled). However, you can only use one Roku channel at a time for testing.

### RevenueCat limitations

Since Roku transactions do not have an associated environment, RevenueCat defines a **"sandbox"** purchase as any purchase made in a **Sideloaded** channel. A **"production"** purchase is defined as any purchase made in either a **beta** or **public** channel, regardless of whether the end customer was actually charged or not for it.

This also means for any events RevenueCat dispatches containing an [`environment` field](/integrations/webhooks/event-types-and-fields#events-format), the Roku channel where the purchase was made will determine whether the value is set to `SANDBOX` or `PRODUCTION`.

To ensure a clear separation between your "testing" and "production" purchases, we recommend creating a **separate channel** specifically for testing purchases and creating a new [RevenueCat Roku Store app](/getting-started/installation/roku#app-configuration) for that channel.

### Testing with a beta channel

Roku's beta channels are a special channel type to assist with testing your channel in a production-like environment before publishing.

#### Beta channel rules

- **120 days**: A beta channel can exist for only 120 days after you create it. After 120 days, the channel will be (1) deleted and removed from your Developer Dashboard and (2) disabled for all users who have it installed
- **10 channels**: There is a maximum of 10 beta channels at a time
- **20 test users**: There can only be 20 beta test users per beta channel at any given time

## Limitations

RevenueCat features not yet supported:

- [RevenueCat paywalls](/tools/paywalls)
- [Trusted entitlements](/customers/trusted-entitlements)
- [Offline entitlements](/customers/customer-info#offline-entitlements)
- [Customer Center](/tools/customer-center)

Functionality not yet supported:

- Detecting price changes
- Chargebacks
- Extending subscriptions

If your use case is not supported above, reach out to [RevenueCat Support](https://app.revenuecat.com/settings/support) so we can discuss more on how to support you!
