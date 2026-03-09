---
id: "getting-started/installation/ios"
title: "iOS & Apple Platforms"
description: "What is RevenueCat?"
permalink: "/docs/getting-started/installation/ios"
slug: "ios"
version: "current"
original_source: "docs/getting-started/installation/ios.mdx"
---

## What is RevenueCat?

RevenueCat provides a backend and a wrapper around StoreKit and Google Play Billing to make implementing in-app purchases and subscriptions easy. With our SDK, you can build and manage your app business on any platform without having to maintain IAP infrastructure. You can read more about [how RevenueCat fits into your app](https://www.revenuecat.com/blog/growth/where-does-revenuecat-fit-in-your-app/) or you can [sign up free](https://app.revenuecat.com/signup) to start building.

## Installation

[![Release](https://img.shields.io/github/release/RevenueCat/purchases-ios.svg?filter=!*beta*\&style=flat)](https://github.com/RevenueCat/purchases-ios/releases)

RevenueCat for iOS can be installed either via [CocoaPods](/getting-started/installation/ios#section-install-via-cocoapods), [Carthage](ios#section-install-via-carthage), or [Swift Package Manager](/getting-started/installation/ios#section-install-via-swift-package-manager).

:::info
Already have 4.x installed? View our [migration guide to 5.x â](/sdk-guides/ios-native-4x-to-5x-migration)
:::

**Video:** Watch the video content in the hosted documentation.

### Install via Swift Package Manager

You can use Swift Package Manager to add RevenueCat to your Xcode project.

:::tip Speed up the Swift Package Manager installation

Use a mirror of the main repository by selecting `File Â» Add Packages Dependencies...` and entering the repository URL (`https://github.com/RevenueCat/purchases-ios-spm.git`) into the search bar (top right).

This will integrate far more quickly than using the main repository directly.
:::

Set the Dependency Rule to `Up to next major`, and the version number to `5.0.0 < 6.0.0`.

When "Choose Package Products for purchases-ios" appears, only select `RevenueCat` and `RevenueCatUI` and click "Add Package".

![SPM integration](/docs_images/sdk/spm-integration.png)

Click "Add Package". The library should have been added to the Package Dependencies section and you should now be able to `import RevenueCat` into your source files.

### Install via CocoaPods

To always use the latest release, add the following to your Podfile:

*Interactive content is available in the web version of this doc.*

Alternatively, pin to a specific minor version:

*Interactive content is available in the web version of this doc.*

And then run:

*Interactive content is available in the web version of this doc.*

This will add `RevenueCat.framework` to your workspace.

### Install via Carthage

To always use the latest release, add the following to your Cartfile:

*Interactive content is available in the web version of this doc.*

Alternatively, pin to a specific minor version:

*Interactive content is available in the web version of this doc.*

#### Carthage with XCFrameworks

If you're using Carthage version >= 0.37, you can use RevenueCat as an XCFramework instead of a Universal Framework. This makes setup easier, since you don't have to set up build phases at all.
To use XCFrameworks with Carthage, you need to pass in `--use-xcframeworks`.

*Interactive content is available in the web version of this doc.*

More information on using XCFrameworks with Carthage is available at https://github.com/carthage/Carthage/#building-platform-independent-xcframeworks-xcode-12-and-above

:::warning
Under certain configurations, when debugging your app, using `po` to print objects to the console might result in an error `\"Couldn't IRGen Expression\"`. If you run into this, one workaround is to add a single, empty Objective-C file to your project, and create a bridging header. There's more information on this issue [here](https://steipete.me/posts/2020/couldnt-irgen-expression/)
:::

#### Carthage with regular frameworks

Run:

*Interactive content is available in the web version of this doc.*

## Import the SDK

:::info Objective-C Only Projects
You may need to add an empty Swift file and a bridging header to your project before compiling.
:::

You should now be able to `import RevenueCat`.

*Interactive content is available in the web version of this doc.*

:::info Enable In-App Purchase capability for your project
Don't forget to enable the In-App Purchase capability for your project under `Project Target -> Capabilities -> In-App Purchase`
:::

## Next Steps

- Now that you've installed the SDK in your iOS app, get started by [configuring an instance of Purchases â](/getting-started/quickstart#3-using-revenuecats-purchases-sdk)
