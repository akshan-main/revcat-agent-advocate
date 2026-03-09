---
id: "getting-started/making-purchases"
title: "Making Purchases"
description: "The SDK has a simple method, purchase(package:), that takes a package from the fetched Offering and purchases the underlying product with Apple, Google, or Amazon."
permalink: "/docs/getting-started/making-purchases"
slug: "making-purchases"
version: "current"
original_source: "docs/getting-started/making-purchases.mdx"
---

The SDK has a simple method, `purchase(package:)`, that takes a package from the fetched Offering and purchases the underlying product with Apple, Google, or Amazon.

*Interactive content is available in the web version of this doc.*

The `purchase(package:)` completion block will contain an updated [CustomerInfo](/customers/customer-info) object if successful, along with some details about the transaction.

If the `error` object is present, then the purchase failed. See our guide on [Error Handling](/test-and-launch/errors) for the specific error types.

The `userCancelled` boolean is a helper for handling user cancellation errors. There will still be an error object if the user cancels, but you can optionally check the boolean instead of unwrapping the error completely.

:::info RevenueCat automatically finishes/acknowledges/consumes transactions
Transactions (new and previous transactions that are synced) will be automatically completed (finished on iOS, acknowledged and consumed in Android), and will be made available through the RevenueCat SDK / Dashboard / ETL Exports.

If you are migrating an existing app to RevenueCat and want to continue using your own in-app purchase logic, you can tell the SDK that [your app is completing transactions](/migrating-to-revenuecat/sdk-or-not/finishing-transactions) if you don't wish to have transactions completed automatically, but you will have to make sure that you complete them yourself.
:::

## Next Steps

- Don't forget to provide some way for customers to [restore their purchases](/getting-started/restoring-purchases)
- With purchases coming through, make sure they're [linked to the correct app user ID](/customers/user-ids)
- If you're ready to test, start with our guides on [sandbox testing](/test-and-launch/sandbox)
