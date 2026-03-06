# RevenueCat MCP Server

The RevenueCat MCP (Model Context Protocol) Server enables AI agents and tools to interact with RevenueCat data and functionality through the standardized MCP protocol.

## Overview

The MCP server exposes 26 tools that allow AI agents to:
- Query subscription metrics and charts data
- Manage offerings, products, and entitlements
- Look up customer information
- Perform administrative operations

## Endpoint

```
https://mcp.revenuecat.ai/mcp
```

The server uses Streamable HTTP transport, compatible with the official MCP SDK.

## Authentication

Authenticate using your RevenueCat secret API key as a Bearer token:

```
Authorization: Bearer sk_your_secret_key_here
```

## Setting Up with Claude Code

To add the RevenueCat MCP server to Claude Code:

```bash
claude mcp add revenuecat -t http -- https://mcp.revenuecat.ai/mcp \
  --header "Authorization: Bearer YOUR_API_KEY"
```

## Available Tools (26 total)

### Read Operations
- `get-project-info`: Get project details and configuration
- `list-apps`: List all apps in a project
- `list-products`: List products for an app
- `list-offerings`: List all offerings in a project
- `list-entitlements`: List all entitlements
- `get-customer`: Get customer details by ID
- `query-charts`: Query charts data for metrics
- `list-subscribers`: List subscribers with filters
- `get-subscriber`: Get detailed subscriber info
- `list-packages`: List packages in an offering

### Write Operations
- `create-offering`: Create a new offering
- `update-offering`: Update an existing offering
- `create-package`: Create a package in an offering
- `update-package`: Update a package
- `create-entitlement`: Create a new entitlement
- `attach-product-to-entitlement`: Link a product to an entitlement
- `grant-promotional-entitlement`: Grant a promotional entitlement
- `revoke-promotional-entitlement`: Revoke a promotional entitlement
- `set-customer-attributes`: Set custom attributes on a customer
- `delete-customer`: Delete a customer record
- `refund-and-revoke`: Process a refund and revoke access
- `create-purchase`: Record a purchase
- `defer-billing`: Defer a subscription billing date
- `set-offer-eligibility`: Configure offer eligibility
- `import-subscribers`: Bulk import subscriber data
- `trigger-webhook-test`: Send a test webhook event

## Python SDK Usage

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    "https://mcp.revenuecat.ai/mcp",
    headers={"Authorization": "Bearer sk_your_key"}
) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("get-project-info", {"project_id": "proj_xxx"})
```

## Safety Considerations

- Read operations are safe and do not modify data
- Write operations should be gated behind explicit user confirmation
- The `delete-customer` and `refund-and-revoke` tools are destructive and should require additional authorization
- Always validate tool parameters before execution

## Sources
- [RevenueCat MCP Server Documentation](https://www.revenuecat.com/docs/tools/mcp)
- [MCP Tools Reference](https://www.revenuecat.com/docs/tools/mcp/tools-reference)
