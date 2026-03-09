---
id: "customers/trusted-entitlements"
title: "Trusted Entitlements"
description: "RevenueCat uses strong SSL to secure communications against interception. But the user is in control of the client device, and, while not an easy process, they can configure it to allow and execute MiTM attacks to grant themselves entitlements without actually paying you."
permalink: "/docs/customers/trusted-entitlements"
slug: "trusted-entitlements"
version: "current"
original_source: "docs/customers/trusted-entitlements.mdx"
---

RevenueCat uses strong SSL to secure communications against interception. But the user is in control of the client device, and, while not an easy process, they can configure it to allow and execute [MiTM](https://en.wikipedia.org/wiki/Man-in-the-middle_attack) attacks to grant themselves entitlements without actually paying you.

**Trusted Entitlements** helps you detect and respond to such attacks. When enabled, our native (iOS/Android) SDKs work together with our backend to verify response integrity by checking a cryptographic signature on entitlement data. This verification result is then provided to your app, allowing *you* to decide how to handle potentially compromised entitlements.

:::info
Trusted Entitlements is supported in iOS SDK version 4.25.0 and up, and Android SDK version 6.6.0 and up.
:::

## Setup

### Default Behavior

**For newer SDK versions (iOS 5.15.0+, Android 8.11.0+):**

- Trusted Entitlements is **enabled by default** - the SDK will provide verification data
- **However, verification results are informational only** - your app must check the verification result and decide how to handle unverified entitlements
- No automatic blocking or rejection of unverified entitlements occurs

**For older SDK versions (iOS 4.25.0-5.14.x, Android 6.6.0-8.10.x):**

- Trusted Entitlements is **disabled by default** - no verification data is provided
- You must explicitly enable it to get verification information

:::warning Important
**Enabling Trusted Entitlements does not automatically protect your app.** The SDK provides verification data, but it's your responsibility to check the verification result in your code and decide whether to grant access based on unverified entitlements.
:::

### Configuration

**To disable Trusted Entitlements** (when it's enabled by default):

*Interactive content is available in the web version of this doc.*

**To enable Trusted Entitlements** (for older SDK versions where it's disabled by default):

Use the same configuration as above, but set the mode to `EntitlementVerificationMode.informational` instead of `EntitlementVerificationMode.disabled`.

:::info
Trusted Entitlements has no impact on performance or behavior when enabled.
:::

### Verification

When Trusted Entitlements are enabled, `EntitlementInfo` contains the verification result:

*Interactive content is available in the web version of this doc.*

Additionally, verification errors are always forwarded to `Purchases.errorHandler`.

## Edge cases

### Cache leftover

Transitioning an app from `EntitlementVerificationMode.disabled` to `EntitlementVerificationMode.informational` means that cached data would not be verified. The SDK will keep using that cached data, which should be updated with the result of the verification after a request to the RevenueCat servers is performed successfully. In this scenario, the `EntitlementInfo` will have a VerificationResult of "not requested". You may clear the CustomerInfo cache by calling the `Purchases/invalidateCustomerInfoCache()` method in the SDK if you want to avoid having unverified entitlements.

### Key replacement

We use intermediate keys that are rotated frequently. These are signed by a root key. In the very unlikely event that the root key is compromised and needs to be replaced, this would be the process:

- The old pair would be considered insecure
- A new version of API endpoints would be added
- A new version of the SDK that uses the new set of endpoints and the new public key would be rolled out

In this way, apps using the old version of the SDK would continue to work, but they would have to be updated to the new set of keys if they want to continue being secure against tampering.

## Compatibility

- Android 4.4+
- iOS 13.x+
