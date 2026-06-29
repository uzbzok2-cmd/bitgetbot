---
name: Bitget API quirks
description: Bitget v2 REST API field names and endpoint differences discovered in practice
---

## Key field name differences (v2 vs docs)

- `openPriceAvg` — average open price of a position (not `averageOpenPrice`)
- `markPrice` — current mark price ✓
- `marginSize` — margin used (not `margin`)
- `unrealizedPL` — unrealized PnL ✓
- `totalFee` — total fees paid ✓

## Endpoint differences

- Futures account balance: `/api/v2/mix/account/accounts?productType=USDT-FUTURES` returns array, filter by `marginCoin=="USDT"`
- NOT `/api/v2/mix/account/account` (returns 400172 Parameter verification failed)
- Positions: `/api/v2/mix/position/all-position` with `productType` + `marginCoin` ✓
- Open orders: `/api/v2/mix/order/orders-pending` ✓
- Plan orders (TP/SL): `/api/v2/mix/order/orders-plan-pending` ✓

**Why:** Discovered during live API testing against real Bitget account. The v2 API docs are inconsistent; always test field names against real responses.

**How to apply:** When adding new endpoints, test field names by printing `list(data[0].keys())` on real response before writing formatters.
