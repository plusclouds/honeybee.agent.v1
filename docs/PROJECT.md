# honeybee.agent.v1 — KipHok Order Printer

## Purpose

A Windows application (`print.py`) that polls a REST API for pending restaurant orders and prints them silently to a **thermal receipt printer** via ESC/POS commands — no browser, no print dialog, no user interaction required.

---

## Entry Point

**`print.py`** — single-file application. Run with:

```bash
python print.py --token <bearer_token> --interval <seconds>
# or place token in .env as API_TOKEN and run:
python print.py
```

### Dependencies

```
requests
python-dotenv
pywin32          # Windows only — provides win32print
```

Install: `pip install requests python-dotenv pywin32`

---

## API

### Poll Endpoint

```
GET https://api.plusclouds.com/leo/printer/kiphok?json=true&shouldDelete=true
Authorization: Bearer <token>
```

- `json=true` — returns structured JSON (not HTML)
- `shouldDelete=true` — removes order from queue after fetch
- Returns a single order object **or** a list of orders under `data`

### Sample Response

```json
{
  "status": true,
  "data": {
    "order": {
      "id": 5747,
      "order_no": "KipHok - 5747",
      "status": "Accepted",
      "created_at": "2026-04-17 14:55:23+03",
      "customer_note": null,
      "tags": "{b-20}",
      "total_amount": 750
    },
    "orderItems": {
      "Other": [
        { "name": "Avokado Ezme", "catalog": "Tam", "quantity": 1, "price_per_item": 250 },
        { "name": "Acili Ezme",   "catalog": "Tam", "quantity": 1, "price_per_item": 250 },
        { "name": "Havuc Tarator","catalog": "Tam", "quantity": 1, "price_per_item": 250 }
      ]
    }
  }
}
```

### Field Notes

| Field | Type | Notes |
|---|---|---|
| `total_amount` | number or string | always cast with `float()` |
| `price_per_item` | number or string | always cast with `float()` |
| `tags` | string `"{b-20}"` or array `["a1"]` | `parse_tags()` handles both |
| `customer_note` | string or `null` | skipped if null |
| `catalog` | string or missing | shown in parentheses next to item name |
| `orderItems["Other"]` | category name | suppressed from receipt header |
| `data` | object or array | normalized to list in `poll()` |

---

## Architecture

### Key Functions

| Function | Description |
|---|---|
| `poll(token, interval)` | Main loop — fetches API, normalizes `data` to list, calls `print_receipt` once |
| `print_receipt(orders)` | On Windows: builds ESC/POS payload and sends to default printer via `win32print`. On non-Windows: calls `preview_receipt` |
| `build_receipt(orders)` | Assembles raw ESC/POS bytes for all orders; one `FEED_CUT` at the very end |
| `_build_single(buf, data)` | Appends one order's ESC/POS bytes into `buf` |
| `preview_receipt(orders)` | Renders a clean plain-text receipt to stdout (for development/testing) |
| `parse_tags(tags)` | Normalises `"{b-20}"` → `"b-20"` and `["a1"]` → `"a1"` |

### Print Flow

```
poll()
  └─ GET /kiphok?json=true&shouldDelete=true
       └─ normalize data → list of orders
            └─ print_receipt(orders)
                 ├─ [Windows]  build_receipt() → win32print RAW → thermal printer
                 └─ [non-Win]  preview_receipt() → stdout
```

### ESC/POS Commands Used

| Constant | Bytes | Effect |
|---|---|---|
| `INIT` | `ESC @` | Reset printer |
| `ALIGN_CTR` | `ESC a 1` | Center align |
| `ALIGN_LEFT` | `ESC a 0` | Left align |
| `ALIGN_RIGHT` | `ESC a 2` | Right align |
| `BOLD_ON/OFF` | `ESC E 1/0` | Bold text |
| `DBLH_ON/OFF` | `ESC ! 0x10/0x00` | Double-height text |
| `FEED_CUT` | `GS V A 05` | Feed 5 lines + partial cut |

- Text is encoded as **cp1254** (Windows Turkish) with `errors="replace"`
- `LINE_WIDTH = 42` characters

### Receipt Layout

```
==========================================
           KipHok - XXXX              ← bold, double-height, centered
       2026-04-17 14:55:23+03         ← centered
              Masa: b-20              ← bold, centered (if tags present)
==========================================
Category Name                          ← bold (skipped if "Other")
  1x Item Name (Catalog)    250 TL
  1x Item Name (Catalog)    250 TL
------------------------------------------
                    TOPLAM: 750 TL    ← bold, right-aligned
==========================================
  Not: <customer note>                ← only if present
==========================================   ← repeated for each order
[FEED + PARTIAL CUT]                  ← once at the very end
```

---

## Configuration

### `.env` file (optional)

```
API_TOKEN=your-bearer-token-here
```

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--token` | — | Bearer token (overrides `.env`) |
| `--interval` | `30` | Poll interval in seconds |

---

## Known Behaviours / Edge Cases

- **HTTP 500**: Full response body is printed to stdout for debugging
- **No orders**: Prints `No new orders.` and waits for next interval
- **Multiple orders in one poll**: All merged into a single print job, one paper cut at end
- **Non-Windows**: `win32print` import fails gracefully; app runs in preview-only mode
