---
id: "tools/paywalls/creating-paywalls/variables"
title: "Variables"
description: "For some Paywall strings you may want to set values based on the package that's being displayed instead of hardcoding a single value, such as when quoting a price, or describing the duration of an Introductory Offer."
permalink: "/docs/tools/paywalls/creating-paywalls/variables"
slug: "variables"
version: "current"
original_source: "docs/tools/paywalls/creating-paywalls/variables.mdx"
---

For some Paywall strings you may want to set values based on the package that's being displayed instead of hardcoding a single value, such as when quoting a price, or describing the duration of an Introductory Offer.

To make this easier and ensure accuracy, we recommend using **Variables** for these values that are package-specific.

For example, to describe a trial that offers "1 week free", you should use the `{{ product.offer_period_with_unit  }}` variable to insert `1 week` to ensure the string is accurate for any product you use, even if you make changes to the product or its introductory offer in the future.

We support the following variables:

| Variable                                   | Weekly Example    | Monthly Example   | 2 Month Example   | 3 Month Example   | 6 Month Example   | Annual Example    | Lifetime Example |
| :----------------------------------------- | :---------------- | :---------------- | :---------------- | :---------------- | :---------------- | :---------------- | :--------------- |
| product.price                              | $2.99             | $9.99             | $17.99            | $24.99            | $39.99            | $69.99            | $119.99          |
| product.price\_per\_period                   | $2.99/week        | $9.99/month       | $17.99/2 months   | $24.99/3 months   | $39.99/6 months   | $69.99/year       | $119.99          |
| product.price\_per\_period\_abbreviated       | $2.99/wk          | $9.99/mo          | $17.99/2mo        | $24.99/3mo        | $39.99/6mo        | $69.99/yr         | $119.99          |
| product.price\_per\_day                      | $0.43             | $0.33             | $0.30             | $0.28             | $0.22             | $0.19             | $119.99          |
| product.price\_per\_week                     | $2.99             | $2.50             | $2.25             | $1.92             | $1.54             | $1.35             | $119.99          |
| product.price\_per\_month                    | $11.96            | $9.99             | $9.00             | $8.33             | $6.67             | $5.83             | $119.99          |
| product.price\_per\_year                     | $155.48           | $119.88           | $107.94           | $99.96            | $79.98            | $69.99            | $119.99          |
| product.period                             | week              | month             | 2 months          | 3 months          | 6 months          | annual            | lifetime         |
| product.period\_abbreviated                 | wk                | mo                | 2mo               | 3mo               | 6mo               | yr                | lifetime         |
| product.periodly                           | weekly            | monthly           | 2 months          | 3 months          | 6 months          | annually          | lifetime         |
| product.period\_in\_days                     | 7                 | 30                | 60                | 90                | 180               | 365               | nan              |
| product.period\_in\_weeks                    | 1                 | 4                 | 8                 | 13                | 13                | 52                | nan              |
| product.period\_in\_months                   | 0                 | 1                 | 2                 | 3                 | 6                 | 12                | nan              |
| product.period\_in\_years                    | 0                 | 0                 | 0                 | 0                 | 0                 | 1                 | nan              |
| product.period\_with\_unit                   | 1 week            | 1 month           | 2 months          | 3 months          | 6 months          | 1 year            | lifetime         |
| product.currency\_code                      | USD               | USD               | USD               | USD               | USD               | USD               | USD              |
| product.currency\_symbol                    | $                 | $                 | $                 | $                 | $                 | $                 | $                |
| product.offer\_price                        | $1.99             | $1.99             | $1.99             | $1.99             | $1.99             | $1.99             | nan              |
| product.offer\_price\_per\_day                | $0.07             | $0.07             | $0.07             | $0.07             | $0.07             | $0.07             | nan              |
| product.offer\_price\_per\_week               | $0.50             | $0.50             | $0.50             | $0.50             | $0.50             | $0.50             | nan              |
| product.offer\_price\_per\_month              | $1.99             | $1.99             | $1.99             | $1.99             | $1.99             | $1.99             | nan              |
| product.offer\_price\_per\_year               | $23.88            | $23.88            | $23.88            | $23.88            | $23.88            | $23.88            | nan              |
| product.offer\_period                       | week              | week              | week              | week              | week              | week              | nan              |
| product.offer\_period\_abbreviated           | wk                | wk                | wk                | wk                | wk                | wk                | nan              |
| product.offer\_period\_in\_days               | 7                 | 7                 | 7                 | 7                 | 7                 | 7                 | nan              |
| product.offer\_period\_in\_weeks              | 1                 | 1                 | 1                 | 1                 | 1                 | 1                 | nan              |
| product.offer\_period\_in\_months             | 0                 | 0                 | 0                 | 0                 | 0                 | 0                 | nan              |
| product.offer\_period\_in\_years              | 0                 | 0                 | 0                 | 0                 | 0                 | 0                 | nan              |
| product.offer\_period\_with\_unit             | 1 week            | 1 week            | 1 week            | 1 week            | 1 week            | 1 week            | nan              |
| product.offer\_end\_date                     | December 31, 2024 | December 31, 2024 | December 31, 2024 | December 31, 2024 | December 31, 2024 | December 31, 2024 | nan              |
| product.secondary\_offer\_price              | $2.99             | $2.99             | $2.99             | $2.99             | $2.99             | $2.99             | nan              |
| product.secondary\_offer\_period             | week              | week              | week              | week              | week              | week              | nan              |
| product.secondary\_offer\_period\_abbreviated | wk                | wk                | wk                | wk                | wk                | wk                | nan              |
| product.relative\_discount                  | 19%               | 19%               | 19%               | 19%               | 19%               | 19%               | 19%              |
| product.store\_product\_name                 | Pro Access        | Pro Access        | Pro Access        | Pro Access        | Pro Access        | Pro Access        | Pro Access       |

## Custom variables

In addition to the product variables listed above, you can create **Custom variables** to insert dynamic content that isn't tied to a specific product. This is useful for displaying values like user-specific information, app state, or promotional messaging that changes based on your app's context.

### Creating and using custom variables in the editor

To create a custom variable:

1. In the paywall editor, select the **Variables** tab from the left-hand sidebar
2. Click "Create variable"
3. Set the name of the variable - this will be how you reference it in your paywall
4. Give it a default value - this is what will be displayed in the preview and used as a fallback if no value is provided

The default value you set applies across your entire project, ensuring consistency wherever the variable is used. Once created, you can insert the custom variable into any text field using the same `{{ custom.variable_name }}` syntax.

### Passing custom variable values from your app

When displaying a paywall in your app, you'll need to pass actual values for any custom variables you've created. This allows you to provide dynamic, context-specific content based on the user's session or app state.

For details on how to pass custom variable values when presenting a paywall, see [Displaying Paywalls](/tools/paywalls/displaying-paywalls#custom-variables).

## Countdown variables

When using a [Countdown component](/tools/paywalls/creating-paywalls/components#countdown) on your paywall, you can use countdown-specific variables within any text component inside that countdown. These variables display the time remaining until the countdown's target date.

| Variable                      | Description                                    | Example |
| :---------------------------- | :--------------------------------------------- | :------ |
| count\_days\_with\_zero          | Days remaining with leading zero               | 07      |
| count\_days\_without\_zero       | Days remaining without leading zero            | 7       |
| count\_hours\_with\_zero         | Hours remaining with leading zero              | 04      |
| count\_hours\_without\_zero      | Hours remaining without leading zero           | 4       |
| count\_minutes\_with\_zero       | Minutes remaining with leading zero            | 09      |
| count\_minutes\_without\_zero    | Minutes remaining without leading zero         | 9       |
| count\_seconds\_with\_zero       | Seconds remaining with leading zero            | 03      |
| count\_seconds\_without\_zero    | Seconds remaining without leading zero         | 3       |

The values displayed by these variables depend on the **Count From** setting of your countdown component:

- **Days**: Shows total days with remainder hours (0-23), minutes (0-59), and seconds (0-59)
- **Hours**: Shows 0 days, total hours, remainder minutes (0-59), and seconds (0-59)
- **Minutes**: Shows 0 days, 0 hours, total minutes, and seconds (0-59)

:::tip
Countdown variables are only available within text components that are inside a countdown component. They cannot be used elsewhere on your paywall.
:::

## Variable preview values

The paywall preview is generated using our example values for each package listed above, and therefore will differ from the actual values for the product's you choose to present on your paywall.

To see a more accurate preview, we recommend running your application on your physical device or in the simulator, as this will present details based on the actual information for the products you're displaying on that device.

## Variable modifiers

We support a handful of modifiers that can be used to format the variable values:

- `uppercase`: Converts the value to uppercase.
- `lowercase`: Converts the value to lowercase.
- `capitalize`: Capitalizes the first letter of each word in the value.

These modifiers can be used with the `|` operator after the variable name, for example:

- `{{ product.price_per_period }}` will yield `$2.99/week`
- `{{ product.price_per_period | uppercase }}` will yield `$2.99/WEEK`
- `{{ product.price_per_period | capitalize }}` will yield `$2.99/Week`

## FAQs

| Question     | Answer  |
| ------------------ | ------------------|
| How is the `product.relative_discount` variable calculated? |  `relative_discount` returns the localized discount percentage of a given package compared to the most expensive package per period that's offered on your paywall. For example, if you're displaying a monthly package that is $10/month, and a yearly package that is $80/year (or $6.67/month), the relative discount for the annual package is 67%. Because of this, we recommend only using this variable within packages that are NOT the most expensive package per period, as the most expensive package will have a null value returned, since its relative discount is null. |
