---
id: "tools/paywalls/displaying-paywalls"
title: "Displaying Paywalls"
description: "Platform specific instructions"
permalink: "/docs/tools/paywalls/displaying-paywalls"
slug: "displaying-paywalls"
version: "current"
original_source: "docs/tools/paywalls/displaying-paywalls.mdx"
---

## Platform specific instructions

### iOS

RevenueCat Paywalls will show paywalls in a sheet or fullscreen on iPhone, and there are multiple ways to do this with SwiftUI and UIKit.

- Depending on an entitlement with `presentPaywallIfNeeded`
- Custom logic with `presentPaywallIfNeeded`
- Manually with `PaywallView` or `PaywallViewController`

*Interactive content is available in the web version of this doc.*

#### Paywalls on iPad

When using `presentPaywallIfNeeded` to display a paywall on iPad, we'll automatically show a paywall in a modal that is roughly iPhone sized. If instead you prefer to show a paywall that is full screen on iPad, you can use the `PaywallView` or `PaywallViewController` methods instead.

![Paywalls on iPad](/docs_images/paywalls/paywalls-on-ipad.jpeg)

### Android

RevenueCat Paywalls will, by default, show paywalls fullscreen and there are multiple ways to do this with `Activity`s and Jetpack Compose.

- Depending on an entitlement with `PaywallDialog`
- Custom logic with `PaywallDialog`
- Manually with `Paywall`, `PaywallDialog`, or `PaywallActivityLauncher`

*Interactive content is available in the web version of this doc.*

### React Native

There are several ways to present paywalls:

- Using `RevenueCatUI.presentPaywall`: this will display a paywall when invoked.
- Using `RevenueCatUI.presentPaywallIfNeeded`: this will present a paywall only if the customer does not have an unlocked entitlement.
- Manually presenting `<RevenueCatUI.Paywall>`: this gives you more flexibility on how the paywall is presented.

*Interactive content is available in the web version of this doc.*

There are also several listeners that can be used to handle the paywall lifecycle, such as `onPurchaseStarted`, `onPurchaseCompleted`, and `onRestoreStarted`.

#### Listeners

When using `RevenueCatUI.Paywall`, you may use one of the provided listeners to react to user actions.

Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onPurchaseCancelled
- onRestoreStarted
- onRestoreCompleted
- onRestoreError
- onDismiss

### Flutter

There are several ways to present paywalls:

- Using `RevenueCatUI.presentPaywall`: this will display a paywall when invoked.
- Using `RevenueCatUI.presentPaywallIfNeeded`: this will present a paywall only if the customer does not have an unlocked entitlement.
- Manually presenting `PaywallView`: this gives you more flexibility on how the paywall is presented.

*Interactive content is available in the web version of this doc.*

#### Listeners

When using `PaywallView`, you may use one of the provided listeners to react to user actions.
Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onRestoreCompleted
- onRestoreError
- onDismiss

### Kotlin Multiplatform

You can present a fullscreen Paywall using the `Paywall` composable. You have the flexibility to decide when to call this. You could, for instance, add it to your navigation graph.

*Interactive content is available in the web version of this doc.*

#### Listeners

When using `Paywall`, you may use one of the provided listeners to react to user actions.
Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onPurchaseCancelled
- onRestoreStarted
- onRestoreCompleted
- onRestoreError

### Capacitor

There are several ways to present paywalls:

- Using `RevenueCatUI.presentPaywall`: this will display a paywall when invoked.
- Using `RevenueCatUI.presentPaywallIfNeeded`: this will present a paywall only if the customer does not have an unlocked entitlement.

*Interactive content is available in the web version of this doc.*

### Unity

RevenueCat Paywalls for Unity provide native paywall presentation on iOS and Android with simple C# APIs.

There are several ways to present paywalls:

- Using `PaywallsPresenter.Present()`: this will display a paywall when invoked.
- Using `PaywallsPresenter.PresentIfNeeded()`: this will present a paywall only if the customer does not have an unlocked entitlement.
- Using `PaywallsBehaviour` component: configure paywalls through Unity's Inspector for Editor workflows.

*Interactive content is available in the web version of this doc.*

#### Using PaywallsBehaviour Component

For developers who prefer configuring paywalls through Unity's Inspector, you can use the `PaywallsBehaviour` MonoBehaviour component:

1. Add a `PaywallsBehaviour` component to any GameObject
2. Configure the options in the Inspector:
   - **Offering Identifier**: Leave empty to use current offering, or specify an offering ID
   - **Display Close Button**: Whether to show a close button (original templates only)
   - **Required Entitlement Identifier**: Optional - paywall will only show if user lacks this entitlement
3. Wire up UnityEvent callbacks: `OnPurchased`, `OnRestored`, `OnCancelled`, `OnNotPresented`, `OnError`
4. Call `PresentPaywall()` method (e.g., from a UI Button's OnClick event)

#### Platform Notes

- The paywall UI is only available on iOS and Android device builds.
- Unity Editor is not supported for displaying the paywall UI.
- Build to device when testing the paywall UI.

### Web

Paywalls are supported on the web through RevenueCat's Web Billing system. To serve your Paywall to customers on the web via a new or existing Web Purchase Link, [click here](https://www.revenuecat.com/docs/web/web-billing/paywalls).
You can also present the same remotely configured paywall directly within your own web experience using the [purchases-js SDK](https://www.revenuecat.com/docs/web/web-billing/web-sdk). Call `presentPaywall` with the element that should host the paywall. Optionally, provide an offering from `purchases.getOfferings()` to choose which paywall to display. The SDK renders the paywall, runs the purchase, and resolves with the result.

```ts title="Presenting a paywall from purchases-js"
async function showPaywall() {
  const paywallContainer = document.getElementById("paywall-container");
  try{
      const purchaseResult = await purchases.presentPaywall({
        htmlTarget: paywallContainer,
        // no offering specified â defaults to the current offering
      });
      console.log("Purchase completed", purchaseResult);
  } catch (e){
      console.log("Something went wrong while purchasing through Paywalls");
  }
}
```

If you omit the `offering` parameter (or pass `undefined`), the paywall from the offering marked as `current` will be displayed.

You can also specify an offering by passing it as parameter to `presentPaywall`.

```ts title="Presenting a paywall from purchases-js with a specific offering"
async function showPaywall() {
  const offerings=await purchases.getOfferings();
  const offeringToUse= offerings.all['offeringIdToUse'];
  const paywallContainer = document.getElementById("paywall-container");
  try{
      const purchaseResult = await purchases.presentPaywall({
        htmlTarget: paywallContainer,
        offering: offeringToUse
      });
      console.log("Purchase completed", purchaseResult);
  } catch (e){
      console.log("Something went wrong while purchasing through Paywalls");
  }
}
```

:::info Max width
Paywalls on the web have a maximum width of 968px.
Individual components can be configured to have their own width settings within that max width of the paywall itself.

When used in Web Purchase Links, if the window the paywall is being displayed in is wider than 968px, the additional space will be filled based on the specified background color of your WPL. [Learn more](https://www.revenuecat.com/docs/web/web-billing/web-purchase-links)
:::

## Handling paywall navigation

When creating a paywall, consider whether it will be presented in a sheet, or as a full screen view. Sheets won't require a dedicated close button. Full screen views should have either a close button (if presented modally) or a back button (if part of a navigation stack or host) unless you intend to provide a hard paywall to your customers that cannot be bypassed.

## Setting preferred locale

You can set a preferred locale for your paywalls to display in a specific language. This is useful when you want to override the device's default language for paywall content.

*Interactive content is available in the web version of this doc.*

## Custom variables

Custom variables allow you to pass dynamic values from your app to display in your paywall text. This is useful for displaying values like user-specific information, app state, or promotional messaging that changes based on your app's context.

When you create custom variables in the [paywall editor](/tools/paywalls/creating-paywalls/variables#custom-variables), you set default values that will be used as fallbacks. When displaying the paywall in your app, you can override these defaults with actual runtime values specific to the user's session.

### iOS

*Interactive content is available in the web version of this doc.*

### Android

*Interactive content is available in the web version of this doc.*

### React Native

*Interactive content is available in the web version of this doc.*

### Flutter

*Interactive content is available in the web version of this doc.*

:::info Availability
Custom variables for Flutter paywalls require `purchases_ui_flutter` version 9.12.0 or later.
:::

:::info Variable naming
Custom variable keys must start with a letter and can only contain letters, numbers, and underscores. In your paywall text, reference them using the template syntax: `{{ custom.variable_name }}`
:::

## Custom fonts

Using custom fonts in your paywall can now be done by uploading font files directly to RevenueCat. See the [Custom fonts](/tools/paywalls/creating-paywalls/components#custom-fonts) section for more information.

### Including custom fonts in your app

To improve the performance and reduce loading times of your paywall using custom fonts, you can add the font to your app's resources using the instructions below.

#### Android

To add a custom font to your Android app, place the font file in the `res/font` folder. Make sure that the filename (without the extension) corresponds to the font name in the paywall editor. See [the official Android documentation](https://developer.android.com/develop/ui/views/text-and-emoji/fonts-in-xml) for more information.

#### iOS

To add a custom font to your iOS app, go to *File* and then *Add Files to "Your Project Name"*. The font file should be a target member of your app, and be registered with iOS by adding the "Fonts provided by the application" key to your *Info.plist* file. Make sure that the filename (without the extension) corresponds to the font name in the paywall editor. See [the official iOS documentation](https://developer.apple.com/documentation/uikit/adding-a-custom-font-to-your-app) for more information.

#### Kotlin Multiplatform, React Native, and Flutter

Adding custom fonts to a hybrid app involves adding the font files to the underlying Android and iOS projects following the instructions above.

## Intercepting an initiated purchase

You can intercept a purchase flow before it begins by using the `onPurchaseInitiated` view modifier in iOS and the `onPurchasePackageInitiated` method on the `PaywallListener` interface in Android. This allows you to perform custom logic, such as showing additional information to the user or performing validation checks, before the purchase proceeds.

When a user initiates a purchase, your interceptor callback will be invoked with:

- The `Package` that the user selected
- A `ResumeAction` closure that you must call to either proceed with or cancel the purchase

The purchase flow will pause until you call the `resume` action. If you call `resume(false)`, the purchase will be cancelled. If you call `resume(true)`, the purchase will proceed as normal.

:::info Availability
This feature is currently available on the native iOS and Android SDKs.
:::

*Interactive content is available in the web version of this doc.*

## Exit offers

Exit offers allow you to present an alternative offer when a user dismisses your paywall without making a purchase. This is a powerful tool for recovering potentially lost conversions by giving users a second chance to subscribe with a different offer, such as a discounted price or alternative package.

When a user tries to close or navigate back from the paywall, instead of immediately dismissing, a secondary paywall will be displayed with the exit offer.

### How it works

1. User attempts to dismiss the main paywall without purchasing
2. An exit offer paywall is automatically presented with an alternative offering
3. The user can either:
   - Subscribe to the exit offer
   - Dismiss the exit offer, which then dismisses the main paywall

### Configuration

Exit offers are configured entirely in the [Paywalls editor](/tools/paywalls/creating-paywalls#configuring-exit-offers) in the RevenueCat dashboard. No code changes are required to use this feature. Once configured, the exit offer will automatically be presented when users attempt to dismiss the paywall, as long as you're using a supported presentation method.

### Supported presentation methods

Exit offers only work when using the `presentPaywall` or `presentPaywallIfNeeded` functions that display paywalls in iOS and cross platform SDKs. In Android, they work automatically when using the `PaywallDialog` and `PaywallActivity` classes.

:::warning View-based APIs not supported
Exit offers will **not** work if you manually embed paywall views/components in your UI (e.g., `PaywallView`, `Paywall` composable, `<RevenueCatUI.Paywall>` component, etc).
:::

### Platform support

| Platform      | Minimum Version |
| :------------ | :-------------- |
| iOS           | 5.52.0+         |
| Android       | 9.18.0+         |
| React Native  | 9.6.15+         |
| Flutter       | 9.10.5+         |
| Capacitor     | 12.0.3+         |
| Unity         | 8.4.15+         |
| KMP           | Not supported   |

## Changes from legacy Paywalls

#### Footer Paywalls

Our current Paywalls no longer support footer Paywalls. If your app requests the Paywall for an Offering to display that has a current Paywall, it will display a default version of that paywall instead (see below). Footer mode can still be used on legacy Paywalls templates using the existing method, or the new `.originalTemplatePaywallFooter()` method on SDK versions that support our current Paywalls.

#### Close buttons

Our current Paywalls do not require the `displayCloseButton` parameter (or equivalent for other platforms), and it will have no effect if used, since close buttons can be optionally added directly to your paywall as a component if desired.

#### Font provider

Our current Paywalls do not support passing in a custom font provider as legacy Paywalls did. Instead, you can now configure Paywalls to use the fonts you've already installed in your app directly from the Dashboard. Using the original handler will have no effect on current Paywalls. For more information, [click here](/tools/paywalls/creating-paywalls/components#custom-fonts)

## Default Paywall

If you attempt to display a Paywall for an Offering that doesn't have one configured, or that has a Paywall configured which is not supported on the installed SDK version, the RevenueCatUI SDK will display a default Paywall.

The default paywall displays all packages in the Offering.

On iOS it uses the app's `accentColor` for styling.
On Android, it uses the app's `Material3`'s `ColorScheme`.

:::tip Targeting
If your app supports our legacy Paywall templates, consider using Targeting to create an audience that only receives your new Paywall if they're using an SDK version that does not support our current Paywalls. This will ensure that older app versions continue to receive the Offering and Paywall that they support, while any app versions running a supported RC SDK version receive your new Paywall. [Learn more about Targeting.](/tools/targeting)
:::
