---
id: "tools/paywalls-legacy/displaying-paywalls"
title: "Displaying Paywalls"
description: "These docs refer to our legacy paywalls."
permalink: "/docs/tools/paywalls-legacy/displaying-paywalls"
slug: "displaying-paywalls"
version: "current"
original_source: "docs/tools/paywalls-legacy/displaying-paywalls.mdx"
---

:::warning Legacy Paywalls
These docs refer to our legacy paywalls.

To learn more about our new paywall builder, [click here](/tools/paywalls).
:::

## iOS

### How to display a fullscreen Paywall in your app

RevenueCat Paywalls will, by default, show paywalls fullscreen and there are multiple ways to do this with SwiftUI and UIKit.

- Depending on an entitlement with `presentPaywallIfNeeded`
- Custom logic with `presentPaywallIfNeeded`
- Manually with `PaywallView` or `PaywallViewController`

*Interactive content is available in the web version of this doc.*

### Close Button

Paywalls displayed with `presentPaywallIfNeeded` will have a close button on the presented sheet.
However, a `PaywallView` will not have a close button by default. This gives you full control on how to to navigate to and from your `PaywallView`. You can push it onto an existing navigation stack or show it in a sheet with a custom dismiss button using SwiftUI toolbar.

If desired, you can pass `displayCloseButton: true` when creating `PaywallView` to display a close button automatically.

This close button will automatically take the color of your app's tint color. You can also override it by using [`View.tintColor`](https://developer.apple.com/documentation/swiftui/view/tint\(_:\)-23xyq): `PaywallView(...).tintColor(Color.red)`.

You can also set `.onRequestedDismissal()` PaywallView's modifier to modify the dismissal behavior of the PaywallView. By default, the paywall will close automatically when completing a purchase, or when pressing the close button. You can use this modifier to customize the behavior of the close button. If you're using UIKit there's also a `dismissRequestedHandler` parameter in the `PaywallViewController` initializer that you can use to handle the dismissal of the paywall.

### How to display a footer Paywall on your custom paywall

RevenueCatUI also has a paywall variation that can be displayed as a footer below your custom paywall. This allows you to design your paywall exactly as you want with native components while still using RevenueCat UI to handle it. This is done by adding the `.paywallFooter()` view modifier to your view.

:::info New view modifier for footer Paywalls
In iOS SDK versions 5.16.0+, which support Paywalls v2, the original `.paywallFooter()` method has been deprecated and replaced with a new `.originalTemplatePaywallFooter()` method. The behavior is identical, but its important to keep in mind that footer Paywalls are only supported on original Paywalls, and therefore if your app uses them it should only use Offerings with original Paywalls.
:::

The footer paywall mainly consists of the following:

- Purchase button
- Package details text
- Package selection (if there are any multiple packages configured)

This is all remotely configured and RevenueCatUI handles all the intro offer eligibility and purchase logic.

*Interactive content is available in the web version of this doc.*

### How to use custom fonts

Paywalls can be configured to use the same font as your app using a `PaywallFontProvider`. A `PaywallFontProvider` can be passed as an argument into all methods for displaying the paywall.

By default, a paywall will use the `DefaultPaywallFontProvider`. This uses the system default font which supports dynamic type.

We also offer a `CustomPaywallFontProvider` which requires a font name that could be something like "Arial" or "Papyrus".

If you need more control over your font preferences, you can create your own `PaywallFontProvider`. One of the following examples will use a rounded system font in the paywall.

*Interactive content is available in the web version of this doc.*

## Android

### How to display a fullscreen Paywall in your app

RevenueCat Paywalls will, by default, show paywalls fullscreen and there are multiple ways to do this with `Activity`s and Jetpack Compose.

- Depending on an entitlement with `PaywallDialog`
- Custom logic with `PaywallDialog`
- Manually with `Paywall`, `PaywallDialog`, or `PaywallActivityLauncher`

*Interactive content is available in the web version of this doc.*

### Close Button

Paywalls displayed with `PaywallDialog` will have a close button on the presented sheet.
However, a `Paywall` will not have a close button by default. This gives you full control over how to navigate to and from your `Paywall` composable. You can push this to the existing navigation stack or display it in a sheet with a custom dismiss button using Android's navigation components and fragments.
When presenting the paywall using the `PaywallActivityLauncher`, the close button will be shown by default since the paywall will be displayed as a new activity on top of the current stack.

If desired, you can use `PaywallOptions.Builder`'s `setShouldDisplayDismissButton(true)` method when creating a `Paywall` to display a close button automatically.

### How to display a footer Paywall on your custom paywall

RevenueCatUI also has a paywall variation that can be displayed as a footer below your custom paywall. This allows you to design your paywall exactly as you want with native components while still using RevenueCat UI to handle it.
This is done by using the `PaywallFooter` composable.

The footer paywall mainly consists of the following:

- Purchase button
- Package details text
- Package selection (if there are any multiple packages configured)

This is all remotely configured and RevenueCatUI handles all the intro offer eligibility and purchase logic.

*Interactive content is available in the web version of this doc.*

### How to use custom fonts

Paywalls can be configured to use the same font as your app using a `FontProvider` when using Compose or `ParcelizableFontProvider` when using `PaywallActivityLauncher`. These can be passed to the `PaywallOptions` or `PaywallDialogOptions` builders or directly to the `launch` method in `PaywallActivityLauncher` into all methods for displaying the paywall.

By default, a paywall will not use a font provider. This uses the current Material3 theme's Typography by default.

We offer a `CustomFontProvider` and `CustomParcelizableFontProvider` which receives a single font family to use by all text styles in the paywall, if you don't need extra granularity control.

If you need more control over your font preferences, you can create your own `FontProvider`. See the following examples for some common use cases:

*Interactive content is available in the web version of this doc.*

## React Native

### How to display a fullscreen Paywall in your app

There are several ways to present paywalls:

- Using `RevenueCatUI.presentPaywall`: this will display a paywall when invoked.
- Using `RevenueCatUI.presentPaywallIfNeeded`: this will present a paywall only if the customer does not have an unlocked entitlement.
- Manually presenting `<RevenueCatUI.Paywall>`: this gives you more flexibility on how the paywall is presented.

*Interactive content is available in the web version of this doc.*

If desired, you can pass `displayCloseButton: true` inside the `options` method when creating a `PaywallView` to display a close button in the paywall. You will need to react by using the `onDismiss` listener.

There are also several listeners that can be used to handle the paywall lifecycle, such as `onPurchaseStarted`, `onPurchaseCompleted`, and `onRestoreStarted`.

### How to display a footer Paywall on your custom paywall

:::warning
`PaywallFooterContainerView` is not supported when [React Native's New Architecture](https://reactnative.dev/blog/2024/10/23/the-new-architecture-is-here) is enabled.
Please see this [GitHub issue](https://github.com/RevenueCat/react-native-purchases/issues/1158#issuecomment-2613000475) for more information.
:::

RevenueCatUI also has a paywall variation that can be displayed as a footer below your custom paywall.
This allows you to design your paywall exactly as you want with native components while still using RevenueCat UI to handle it.
This is done by using `<RevenueCatUI.PaywallFooterContainerView>`.

The footer paywall mainly consists of the following:

- Purchase button
- Package details text
- Package selection (if there are any multiple packages configured)

This is all remotely configured and RevenueCatUI handles all the intro offer eligibility and purchase logic.

*Interactive content is available in the web version of this doc.*

:::warning
`PaywallFooterContainerView` only works correctly when phone is in portrait mode.
Landscape mode support for `PaywallFooterContainerView` is coming soon.
:::

### Listeners

When using `RevenueCatUI.Paywall` or `RevenueCatUI.PaywallFooterContainerView`, you may use one of the provided listeners to react to user actions.
Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onPurchaseCancelled
- onRestoreStarted
- onRestoreCompleted
- onRestoreError
- onDismiss

### How to use custom fonts

Paywalls can be configured to use the same font as your app passing the font family name in the `FullScreenPaywallViewOptions` or `FooterPaywallViewOptions`.

By default, a paywall will use the the system default font which supports dynamic type.

In order to add a font family, add it in your react native app and make sure to run `npx react-native-asset` so it's added to the native components. Supported font types are `.ttf` and `.otf`.
Make sure the file names follow the convention:

- Regular: MyFont.ttf/MyFont.otf
- Bold: MyFont\_bold.ttf/MyFont\_bold.otf
- Italic: MyFont\_italic.ttf/MyFont\_italic.otf
- Bold and Italic: MyFont\_bold\_italic.ttf/MyFont\_bold\_italic.otf

See the following examples for some common use cases:

*Interactive content is available in the web version of this doc.*

## Flutter

### How to display a fullscreen Paywall in your app

There are several ways to present paywalls:

- Using `RevenueCatUI.presentPaywall`: this will display a paywall when invoked.
- Using `RevenueCatUI.presentPaywallIfNeeded`: this will present a paywall only if the customer does not have an unlocked entitlement.
- Manually presenting `PaywallView`: this gives you more flexibility on how the paywall is presented.

*Interactive content is available in the web version of this doc.*

If desired, you can pass `displayCloseButton: true` when creating a `PaywallView` to display a close button in the paywall.
You will need to react by using the `onDismiss` listener.

### How to display a footer Paywall on your custom paywall

purchases\_ui\_flutter also has a paywall variation that can be displayed as a footer below your custom paywall.
This allows you to design your paywall exactly as you want with native components while still using RevenueCat UI to handle it.
This is done by using `PaywallFooterView`.

The footer paywall mainly consists of the following:

- Purchase button
- Package details text
- Package selection (if there are any multiple packages configured)

This is all remotely configured and RevenueCatUI handles all the intro offer eligibility and purchase logic.

*Interactive content is available in the web version of this doc.*

### Listeners

When using `PaywallView` or `PaywallFooterView`, you may use one of the provided listeners to react to user actions.
Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onRestoreCompleted
- onRestoreError
- onDismiss

## Kotlin Multiplatform

### How to display a fullscreen Paywall in your app

You can present a fullscreen Paywall using the `Paywall` composable. You have the flexibility to decide when to call this. You could, for instance, add it to your navigation graph.

*Interactive content is available in the web version of this doc.*

If desired, you can set `shouldDisplayDismissButton` to `true` in your `PaywallOptions` to display a close button in the paywall. You will need to react to it using the `dismissRequest` listener.

### How to display a footer Paywall on your custom paywall

RevenueCatUI also has a paywall variation that can be displayed as a footer below your custom paywall. This allows you to design your paywall exactly as you want with native components while still using RevenueCat UI to handle it.
This is done by using the `PaywallFooter` composable.

The footer paywall mainly consists of the following:

- Purchase button
- Package details text
- Package selection (if there are any multiple packages configured)

This is all remotely configured and RevenueCatUI handles all the intro offer eligibility and purchase logic.

*Interactive content is available in the web version of this doc.*

### Listeners

When using `Paywall` or `PaywallFooter`, you may use one of the provided listeners to react to user actions.
Available listeners at this time are:

- onPurchaseStarted
- onPurchaseCompleted
- onPurchaseError
- onPurchaseCancelled
- onRestoreStarted
- onRestoreCompleted
- onRestoreError

## Default Paywall

If you attempt to display a Paywall for an Offering that doesn't have one configured, the RevenueCatUI SDK will display a default Paywall.
The default paywall displays all packages in the offering.

On iOS it uses the app's `accentColor` for styling.
On Android, it uses the app's `Material3`'s `ColorScheme`.
