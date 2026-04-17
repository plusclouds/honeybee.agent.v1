import requests
import subprocess
import tempfile
import os
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description="Fetch orders and print via lp.")
    parser.add_argument("token", help="Bearer token for authentication")
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Polling interval in seconds (default: 30)"
    )
    args = parser.parse_args()

    url = "https://apiv4.plusclouds.com/leo/printer/kiphok?shouldDelete=true"

    headers = {
        "Authorization": f"Bearer {args.token}",
        "Accept": "application/json"
    }

    print(f"🔄 Starting job polling every {args.interval} seconds...")
    try:
        while True:
            try:
                response = requests.get(url, headers=headers, timeout=10)

                if response.status_code == 200:
                    result = response.json()

                    if result.get("status") and "data" in result:
                        for item in result["data"]:
                            order_id = item.get("orderId")
                            if not order_id:
                                continue

                            print(f"🔹 Processing Order ID: {order_id}")

                            # Second API request for printing
                            print_url = f"https://serdesin-honeybee.plusclouds.com/us/queue/print?orderId={order_id}"
                            print_resp = requests.get(print_url, timeout=10)

                            if print_resp.status_code == 200:
                                with tempfile.NamedTemporaryFile(
                                    delete=False,
                                    suffix=".html",
                                    mode="w",
                                    encoding="utf-8"
                                ) as tmp_file:
                                    tmp_file.write(print_resp.text)
                                    tmp_filename = tmp_file.name

                                print(f"✅ Saved to {tmp_filename}")

                                try:
                                    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                                    subprocess.run([
                                        chrome_path,
                                        "--kiosk-printing",
                                        "--kiosk",
                                        tmp_filename
                                    ], check=True)
                                    print(f"🖨️ Sent order {order_id} to printer")
                                except subprocess.CalledProcessError as e:
                                    print(f"⚠️ Printing failed for {order_id}: {e}")

                            else:
                                print(f"❌ Failed to fetch print content for {order_id}: {print_resp.status_code}")

                    else:
                        print("ℹ️ No new jobs.")

                else:
                    print(f"❌ API request failed with status {response.status_code}")
                    print(response.text)

            except requests.exceptions.RequestException as e:
                print(f"⚠️ Network error: {e}")

            # wait before polling again
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n⏹️ Stopped by user.")

if __name__ == "__main__":
    main()
