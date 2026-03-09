---
id: "known-store-issues/xcode-26/app-crash-urlsessionconfiguration"
title: "URLSessionConfiguration Crash"
description: "Issue Description"
permalink: "/docs/known-store-issues/xcode-26/app-crash-urlsessionconfiguration"
slug: "docs/known-store-issues/xcode-26/app-crash-urlsessionconfiguration"
version: "current"
original_source: "docs/known-store-issues/xcode-26/app-crash-urlsessionconfiguration.mdx"
---

## Issue Description

Xcode 26 beta introduces a bug that may cause your app to crash when integrating multiple librariesâsuch as RevenueCat's SDKâthat utilize `URLSessionConfiguration`. This issue occurs when running the app on iOS 26 simulators.

You can find more information in the following [Apple Developer Forum thread](https://developer.apple.com/forums/thread/787365).

## Affected Versions

- Xcode 26 beta
- iOS 26 simulators

## Symptoms

- Your project includes libraries in addition to RevenueCat.
- The app crashes immediately upon launch when using Xcode 26 beta with iOS 26 simulators.

## Workarounds

While awaiting a fix from Apple, a temporary workaround is to initiate a networking call early during app initialization. This appears to prevent the crash.

*Interactive content is available in the web version of this doc.*

## Apple Feedback

For ongoing updates, refer to [this Apple Developer Forum thread](https://developer.apple.com/forums/thread/787365). If the workaround above does not resolve the issue, please consider filing a bug report within that thread.

## Status

ð°ï¸ Waiting on Apple's resolution.
