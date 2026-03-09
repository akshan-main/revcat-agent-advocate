---
id: "integrations/third-party-integrations/telemetrydeck"
title: "TelemetryDeck"
description: "TelemetryDeck can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use TelemetryDeck's app analytics to find patterns in customer behavior and inform marketing strategies."
permalink: "/docs/integrations/third-party-integrations/telemetrydeck"
slug: "telemetrydeck"
version: "current"
original_source: "docs/integrations/third-party-integrations/telemetrydeck.mdx"
---

TelemetryDeck can be a useful integration tool for seeing all events and revenue that occur for your app even if itâs not active for a period of time. You can use TelemetryDeck's app analytics to find patterns in customer behavior and inform marketing strategies.

### Integration at a Glance

| Includes Revenue | Supports Negative Revenue | Sends Sandbox Events | Includes Customer Attributes | Sends Transfer Events |                                                                 Optional Event Types                                                                 |
| :--------------: | :-----------------------: | :------------------: | :--------------------------: | :-------------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------: |
|        â        |            â             |          â          |              â              |          â           | `non_subscription_purchase_event` `uncancellation_event` `subscription_paused_event` `expiration_event` `billing_issue_event` `product_change_event` |

## Setup

Please follow the instructions in [TelemetryDeck's documentation](https://telemetrydeck.com/docs/integrations/revenuecat/) to set up the integration on the TelemetryDeck side.

### 1. Set TelemetryDeck User Identity

In order to associate RevenueCat data with a TelemetryDeck User, the following [Customer Attributes](/customers/customer-attributes) should be set in RevenueCat:

- `$telemetryDeckAppId`: This attribute should be set to your TelemetryDeck App ID, the same one you pass into the TelemetryDeck SDK for initialization.
- `$telemetryDeckUserId`: This attribute needs to be the already-hashed user identifier that TelemetryDeck is using.

### 2. Send RevenueCat Events to TelemetryDeck

After you've set up the Purchase SDK and TelemetryDeck SDK to have the same user identity, you can "turn on" the integration and configure the event names from the RevenueCat dashboard.

Navigate to your project settings in the RevenueCat dashboard and choose 'TelemetryDeck' from the Integrations menu

![Integration setup](/docs_images/integrations/setup-integrations.png)

That's it! No configuration is needed on the RevenueCat side.
