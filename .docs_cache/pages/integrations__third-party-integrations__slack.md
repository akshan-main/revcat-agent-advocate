---
id: "integrations/third-party-integrations/slack"
title: "Slack"
description: "RevenueCat can send you Slack message to a channel any time an event happens in your app. This lets you keep a close pulse on your app and celebrate those money making moments!"
permalink: "/docs/integrations/third-party-integrations/slack"
slug: "slack"
version: "current"
original_source: "docs/integrations/third-party-integrations/slack.mdx"
---

RevenueCat can send you Slack message to a channel any time an event happens in your app. This lets you keep a close pulse on your app and celebrate those money making moments!

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events  | Includes Customer Attributes | Sends Transfer Events | Optional Event Types |
| :--------------: | :-----------------------: | :-------------------: | :--------------------------: | :-------------------: | :------------------: |
|        â        |            â             | Toggle on in Settings |              â              |          â           |          â          |

## Events

The Slack integration tracks the following events:

| Event Type                | Default Event Name (Fallback)                                                           | Description                                                                                                                                                                                                                                                         | App Store | Play Store | Amazon | Stripe | Promo |
| ------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ---------- | ------ | ------ | ----- |
| Initial Purchase          | Customer `<user_id>` just started a subscription of `<product_id>`                      | A new subscription has been purchased.                                                                                                                                                                                                                              | â        | â         | â     | â     | â    |
| Trial Started             | Customer `<user_id>` just started a free trial of `<product_id>`                        | The start of an auto-renewing subscription product free trial.                                                                                                                                                                                                      | â        | â         | â     | â     | â    |
| Trial Converted           | Customer `<user_id>` just converted from a free trial of `<product_id>`                 | When an auto-renewing subscription product converts from a free trial to normal paid period.                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Trial Cancelled           | Customer `<user_id>` just cancelled their free trial of `<product_id>`                  | When a user turns off renewals for an auto-renewing subscription product during a free trial period.                                                                                                                                                                | â        | â         | â     | â     | â    |
| Renewal                   | Customer `<user_id>` just renewed their subscription of `<product_id>`                  | An existing subscription has been renewed or a lapsed user has resubscribed.                                                                                                                                                                                        | â        | â         | â     | â     | â    |
| Cancellation              | Customer `<user_id>` just cancelled their subscription of `<product_id>`                | A subscription or non-renewing purchase has been cancelled. See [cancellation reasons](/integrations/webhooks/event-types-and-fields#cancellation-and-expiration-reasons) for more details.                                                                         | â        | â         | â     | â     | â    |
| Non Subscription Purchase | Customer `<user_id>` just purchased `<product_id>`                                      | A customer has made a purchase that will not auto-renew.                                                                                                                                                                                                            | â        | â         | â     | â     | â    |
| Billing Issue             | Customer `<user_id>` got a billing issue on `<product_id>`                              | There has been a problem trying to charge the subscriber. This does not mean the subscription has expired. Can be safely ignored if listening to CANCELLATION event + cancel\_reason=BILLING\_ERROR.                                                                  | â        | â         | â     | â     | â    |
| Product Change            | Customer `<user_id>` got a product change from `<old_product_id>` to `<new_product_id>` | A subscriber has changed the product of their subscription. This does not mean the new subscription is in effect immediately. See [Managing Subscriptions](/subscription-guidance/managing-subscriptions) for more details on updates, downgrades, and crossgrades. | â        | â         | â     | â     | â    |

## Configure Slack Workspace

Before RevenueCat can post to your Slack channel, you need to authorize a webhook to post to your workspace. Slack has a more [detailed article](https://get.slack.help/hc/en-us/articles/115005265063-Incoming-WebHooks-for-Slack) on their website explaining how to set this up if you have trouble.

### 1. Create a **Slack app**

- Navigate to [https://api.slack.com/apps](https://api.slack.com/apps?new_app=1) and create a new app. Give it a name like "RevenueCat" and select your workspace.

![](/docs_images/integrations/third-party-integrations/slack/slack-app-creation.png)

- Click **Create App**

### 2. Enable **Incoming Webhooks** from the settings page

![](/docs_images/integrations/third-party-integrations/slack/slack-enable-webhooks.png)

1. Select **Incoming Webhooks** from the sidebar
2. Enable the Incoming Webhooks toggle
3. After the settings page refreshes, click **Add New Webhook to Workspace**

### 3. Pick a channel that the app will post to, then click **Authorize**

![](/docs_images/integrations/third-party-integrations/slack/slack-authorize-channel.png)

## Configure RevenueCat Integration

1. Navigate to your project settings in the RevenueCat dashboard and choose 'Slack' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

2. Enter your configuration details.

:::success
You're all set! RevenueCat will start sending events into Slack!
:::

![](/docs_images/integrations/third-party-integrations/slack/slack-successful-event.png)

## Sample Events

Below are sample JSONs that are delivered to Slack for each event type.

*Interactive content is available in the web version of this doc.*

*Interactive content is available in the web version of this doc.*
