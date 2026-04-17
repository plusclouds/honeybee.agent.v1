import requests
import argparse
import time
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import win32print
    WINDOWS = True
except ImportError:
    WINDOWS = False


URL = "https://api.plusclouds.com/leo/printer/kiphok?json=true&shouldDelete=true"
LINE_WIDTH = 42

# ESC/POS commands
ESC         = b"\x1b"
INIT        = ESC + b"\x40"
ALIGN_LEFT  = ESC + b"\x61\x00"
ALIGN_CTR   = ESC + b"\x61\x01"
ALIGN_RIGHT = ESC + b"\x61\x02"
BOLD_ON     = ESC + b"\x45\x01"
BOLD_OFF    = ESC + b"\x45\x00"
DBLH_ON     = ESC + b"\x21\x10"
DBLH_OFF    = ESC + b"\x21\x00"
FEED_CUT    = b"\x1d\x56\x41\x05"   # partial cut after 5-line feed


def _line(text: str = "") -> bytes:
    return (text + "\n").encode("cp1254", errors="replace")


def _divider(char: str = "-") -> bytes:
    return _line(char * LINE_WIDTH)


def _row(left: str, right: str) -> bytes:
    gap = LINE_WIDTH - len(left) - len(right)
    return _line(left + " " * max(1, gap) + right)


def parse_tags(tags) -> str:
    if not tags:
        return ""
    if isinstance(tags, list):
        return ", ".join(str(t) for t in tags)
    # string like "{b-20}" -> "b-20"
    return str(tags).strip("{}")


def _build_single(buf: bytearray, data: dict) -> None:
    order = data["order"]
    order_items = data["orderItems"]
    tag_str = parse_tags(order.get("tags"))
    total = float(order["total_amount"])

    buf += ALIGN_CTR
    buf += BOLD_ON + DBLH_ON
    buf += _line(order["order_no"])
    buf += DBLH_OFF + BOLD_OFF
    buf += _line(order["created_at"])
    if tag_str:
        buf += BOLD_ON + _line(f"Masa: {tag_str}") + BOLD_OFF
    buf += _divider("=")

    buf += ALIGN_LEFT
    for category, items in order_items.items():
        if category != "Other":
            buf += BOLD_ON + _line(category) + BOLD_OFF
        for item in items:
            price = float(item["price_per_item"])
            catalog = item.get("catalog", "")
            left = f"  {item['quantity']}x {item['name']}"
            if catalog:
                left += f" ({catalog})"
            price_str = f"{price:.0f} TL" if price > 0 else ""
            buf += _row(left, price_str) if price_str else _line(left)

    buf += _divider("-")
    buf += BOLD_ON + ALIGN_RIGHT
    buf += _line(f"TOPLAM: {total:.0f} TL  ")
    buf += BOLD_OFF

    if order.get("customer_note"):
        buf += ALIGN_LEFT + _divider("-")
        buf += _line(f"  Not: {order['customer_note']}")

    buf += _divider("=")


def build_receipt(orders: list) -> bytes:
    buf = bytearray()
    buf += INIT
    for data in orders:
        _build_single(buf, data)
    buf += FEED_CUT
    return bytes(buf)


def preview_receipt(orders: list) -> None:
    """Render a clean receipt preview without ESC/POS bytes."""
    def row(left, right=""):
        gap = LINE_WIDTH - len(left) - len(right)
        return left + " " * max(1, gap) + right

    lines = [""]
    for data in orders:
        order = data["order"]
        order_items = data["orderItems"]
        tag_str = parse_tags(order.get("tags"))
        total = float(order["total_amount"])

        lines += [
            "=" * LINE_WIDTH,
            order["order_no"].center(LINE_WIDTH),
            order["created_at"].center(LINE_WIDTH),
        ]
        if tag_str:
            lines.append(f"Masa: {tag_str}".center(LINE_WIDTH))
        lines.append("=" * LINE_WIDTH)

        for category, items in order_items.items():
            lines.append("" if category == "Other" else f"\n{category}")
            for item in items:
                price = float(item["price_per_item"])
                catalog = item.get("catalog", "")
                left = f"  {item['quantity']}x {item['name']}"
                if catalog:
                    left += f" ({catalog})"
                price_str = f"{price:.0f} TL" if price > 0 else ""
                lines.append(row(left, price_str) if price_str else left)

        lines.append("-" * LINE_WIDTH)
        lines.append(row("", f"TOPLAM: {total:.0f} TL"))
        lines.append("=" * LINE_WIDTH)

        if order.get("customer_note"):
            lines.append(f"  Not: {order['customer_note']}")

    lines.append("")
    print("\n".join(lines))


def print_receipt(orders: list) -> None:
    if not WINDOWS:
        preview_receipt(orders)
        return

    payload = build_receipt(orders)

    printer_name = win32print.GetDefaultPrinter()
    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("KipHok Order", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def poll(token: str, interval: int) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    print(f"Polling every {interval}s — press Ctrl+C to stop.")

    try:
        while True:
            try:
                resp = requests.get(URL, headers=headers, timeout=10)

                if resp.status_code == 200:
                    result = resp.json()

                    if result.get("status") and result.get("data"):
                        raw = result["data"]
                        orders = raw if isinstance(raw, list) else [raw]
                        ids = [str(o["order"]["id"]) for o in orders]
                        print(f"  Printing {len(orders)} order(s): {', '.join(ids)}")
                        print_receipt(orders)
                        print(f"  Done — sent to printer.")
                    else:
                        print("  No new orders.")

                else:
                    print(f"  API error {resp.status_code}:\n{resp.text}")

            except requests.exceptions.RequestException as e:
                print(f"  Network error: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll KipHok orders and print silently.")
    parser.add_argument("--token", help="Bearer token (overrides .env API_TOKEN)")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    args = parser.parse_args()

    token = args.token or os.getenv("API_TOKEN")
    if not token:
        parser.error("Token required: pass --token or set API_TOKEN in .env")

    poll(token, args.interval)


if __name__ == "__main__":
    main()