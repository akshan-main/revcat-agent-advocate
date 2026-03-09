---
id: "platform-resources/apple-platform-resources/swiftui-helpers"
title: "Using RevenueCat with SwiftUI"
description: "Debugging"
permalink: "/docs/platform-resources/apple-platform-resources/swiftui-helpers"
slug: "swiftui-helpers"
version: "current"
original_source: "docs/platform-resources/apple-platform-resources/swiftui-helpers.mdx"
---

## Debugging

The Purchases SDK includes a debug overlay that allows developers to see various configuration details while running an app. You can read more about the debug overlay in our [Debugging](/test-and-launch/debugging#debug-ui) guide.

## SwiftUI Previews

SwiftUI Previews allow developers to preview their views directly in Xcode without building and running your app. The Purchases SDK includes convenience types for displaying mock products and offerings to avoid having to build and run your app to test your paywall.

*Interactive content is available in the web version of this doc.*

## SDK Initialization

We recommend following our [guide](/getting-started/configuring-sdk) for more information on configuring the Purchases SDK. However, we detail multiple methods for configuring the SDK in SwiftUI below.

### Option 1: App Init

For basic initialization without delegate methods, you can implement the App `init` method:

*Interactive content is available in the web version of this doc.*

### Option 2: App Delegate

Another method of initialization is to use the `@UIApplicationDelegateAdaptor` property wrapper to configure the Purchases SDK. The `@UIApplicationDelegateAdaptor` gives the option of using UIApplicationDelegate methods that are traditionally used in UIKit applications.

#### Creating a Delegate

Begin by creating a delegate class and initializing the *Purchases* SDK like the following:

*Interactive content is available in the web version of this doc.*

#### Attaching the Delegate

As previously mentioned, the new `@UIApplicationDelegateAdaptor` property attaches the delegate to the new SwiftUI App struct. Add the property wrapper like the following:

*Interactive content is available in the web version of this doc.*

Build and run the app, and *Purchases* will be initialized on app launch.

For more information on configuring the SDK, check out the [Configuring SDK](/getting-started/configuring-sdk) guide.
