---
id: "getting-started/making-purchases/android-with-jetpack-compose"
title: "Android with Jetpack Compose"
description: "Jetpack Compose is a new modern toolkit for building native UI for Android. One major difference in Jetpack Compose is the absence of Activity. The purchasePackage() and purchasePackageWith() functions accept an Activity as the first parameter but an Activity is not easily accessible in a @Composable function."
permalink: "/docs/getting-started/making-purchases/android-with-jetpack-compose"
slug: "android-with-jetpack-compose"
version: "current"
original_source: "docs/getting-started/making-purchases/android-with-jetpack-compose.mdx"
---

Jetpack Compose is a new modern toolkit for building native UI for Android. One major difference in Jetpack Compose is the absence of `Activity`. The `purchasePackage()` and `purchasePackageWith()` functions accept an `Activity` as the first parameter but an `Activity` is not easily accessible in a `@Composable` function.

To get around this, you can create an extension function to recursively find the nearest `Activity` from your Jetpack Compose context.

*Interactive content is available in the web version of this doc.*

So example below shows how to check the nullable `Activity?` returned by `LocalContext.current.findActivity()` and pass it into `purchase(package:)`.

*Interactive content is available in the web version of this doc.*
