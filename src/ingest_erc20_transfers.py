import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


parser = argparse.ArgumentParser(
    description="Ingest ERC-20 transfers for an Ethereum address."
)

parser.add_argument(
    "address",
    help="Ethereum address to ingest.",
)

parser.add_argument(
    "--offset",
    type=int,
    default=100,
    help="Number of records per API page. Default: 100",
)

args = parser.parse_args()

address = args.address
offset = args.offset

if offset <= 0:
    raise ValueError("--offset phải lớn hơn 0")


url = "https://api.etherscan.io/v2/api"
#lần 1 lỗi chờ 2s, lần 2 chờ 4s,.. -> thời gian chờ tăng theo cấp số nhân

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 2

RETRYABLE_STATUS_CODES = {
    429, #giới hạn request
    500, #5xx -> server gặp vấn đề
    502,
    503,
    504,
}

#gọi API và xử lí retry

def fetch_page(page):
    params = {
        "chainid": "1",
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": offset,
        "sort": "asc",
        "apikey": api_key,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=20,
            )

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == MAX_RETRIES:
                    response.raise_for_status()

                delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))

                print(
                    f"Temporary HTTP error "
                    f"{response.status_code}. "
                    f"Retrying in {delay}s..."
                )

                time.sleep(delay)
                continue

            response.raise_for_status()

            return response

        except (
            # quá thời gian chờ và lỗi kết nối
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as error:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Request failed after "
                    f"{MAX_RETRIES} attempts on page {page}"
                ) from error

            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))

            print(
                f"Network error on page {page}. "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)

    raise RuntimeError(
        f"Unexpected retry failure on page {page}"
    )


run_time = datetime.now(timezone.utc)

date_folder = run_time.strftime("%Y-%m-%d")
timestamp = run_time.strftime("%Y%m%dT%H%M%SZ")


output_dir = Path(
    "data",
    "raw",
    "ethereum",
    "erc20_transfers",
    f"ingestion_date={date_folder}",
)

output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


page = 1

pages_saved = 0
total_records = 0

#pagination +save raw data
while True:
    print(f"Fetching page {page}...")

    response = fetch_page(page)

    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(
            f"Invalid JSON response on page {page}"
        ) from error

    result = payload.get("result")


    if (
        payload.get("status") == "0"
        and "No transactions found" in str(result)
    ):
        print("No more records.")
        break


    if not isinstance(result, list):
        raise RuntimeError(
            f"Etherscan API error on page {page}: "
            f"{payload.get('message')} - {result}"
        )


    if len(result) == 0:
        print("No more records.")
        break


    output_file = (
        output_dir
        / (
            f"tokentx_{address.lower()}_"
            f"page_{page:04d}_"
            f"{timestamp}.json"
        )
    )

    output_file.write_text(
        response.text,
        encoding="utf-8",
    )


    pages_saved += 1
    total_records += len(result)


    print(
        f"Saved page {page}: "
        f"{len(result)} records"
    )


    if len(result) < offset:
        print("Reached the last page.")
        break


    page += 1


print()
print("Ingestion completed.")
print("Pages saved:", pages_saved)
print("Total records:", total_records)
print("Output directory:", output_dir)