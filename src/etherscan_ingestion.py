import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_URL = "https://api.etherscan.io/v2/api"

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 2

RETRYABLE_HTTP_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

RETRYABLE_API_MESSAGES = (
    "max rate limit reached",
    "query timeout",
    "server too busy",
    "timeout occurred",
    "timeout occured",
)

#lấy 1 page an toàn
def fetch_page(
    api_key,
    address,
    action,
    page,
    offset,
):
    params = {
        "chainid": "1",
        "module": "account",
        "action": action,
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
                BASE_URL,
                params=params,
                timeout=20,
            )

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as error:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Network request failed after "
                    f"{MAX_RETRIES} attempts on page {page}"
                ) from error

            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))

            print(
                f"Network error. "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)
            continue


        if response.status_code in RETRYABLE_HTTP_STATUS_CODES:
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


        try:
            payload = response.json()

        except ValueError as error:
            raise RuntimeError(
                f"Invalid JSON response on page {page}"
            ) from error


        result = payload.get("result")

        api_message = (
            f"{payload.get('message', '')} "
            f"{result}"
        ).lower()


        if payload.get("status") == "0":

            if "no transactions found" in api_message:
                return response, []

            is_retryable_api_error = any(
                message in api_message
                for message in RETRYABLE_API_MESSAGES
            )

            if is_retryable_api_error:
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        f"Etherscan API still failing after "
                        f"{MAX_RETRIES} attempts: {result}"
                    )

                delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))

                print(
                    f"Temporary Etherscan API error. "
                    f"Retrying in {delay}s..."
                )

                time.sleep(delay)
                continue

            raise RuntimeError(
                f"Etherscan API error: "
                f"{payload.get('message')} - {result}"
            )


        if not isinstance(result, list):
            raise RuntimeError(
                f"Unexpected Etherscan result "
                f"on page {page}: {result}"
            )


        return response, result


    raise RuntimeError(
        f"Unexpected retry failure on page {page}"
    )

# 1-> n và lưu all xuống raw

def ingest_account_history(
    api_key,
    address,
    action,
    dataset_name,
    file_prefix,
    offset,
):
    run_time = datetime.now(timezone.utc)

    date_folder = run_time.strftime("%Y-%m-%d")
    timestamp = run_time.strftime("%Y%m%dT%H%M%SZ")


    output_dir = Path(
        "data",
        "raw",
        "ethereum",
        dataset_name,
        f"ingestion_date={date_folder}",
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    page = 1
    pages_saved = 0
    total_records = 0


    while True:
        print(f"Fetching page {page}...")

        response, result = fetch_page(
            api_key=api_key,
            address=address,
            action=action,
            page=page,
            offset=offset,
        )


        if len(result) == 0:
            print("No more records.")
            break


        output_file = (
            output_dir
            / (
                f"{file_prefix}_"
                f"{address.lower()}_"
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
    print("Dataset:", dataset_name)
    print("Pages saved:", pages_saved)
    print("Total records:", total_records)
    print("Output directory:", output_dir)