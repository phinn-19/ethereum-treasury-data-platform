import json
import time
from datetime import datetime, time as datetime_time, timezone
from pathlib import Path

import duckdb
import requests


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
    "native_eth_prices",
)

DEFILLAMA_URL = (
    "https://coins.llama.fi/batchHistorical"
)

PROVIDER = "defillama"
PROVIDER_ASSET_ID = "coingecko:ethereum"

ASSET_ID = "eth_native"
SYMBOL = "ETH"
QUOTE_CURRENCY = "USD"

MAX_TIMESTAMPS_PER_REQUEST = 50
MAX_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30


def get_required_timestamps():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "DuckDB database not found: "
            f"{DATABASE_PATH}"
        )

    connection = duckdb.connect(
        str(DATABASE_PATH),
        read_only=True,
    )

    try:
        connection.execute(
            """
            SET TimeZone = 'UTC'
            """
        )

        dates = connection.execute(
            """
            SELECT DISTINCT
                CAST(
                    block_timestamp
                    AS DATE
                ) AS activity_date

            FROM
                gold.organization_native_eth_movements

            ORDER BY
                activity_date
            """
        ).fetchall()

    finally:
        connection.close()

    timestamps = []

    for row in dates:
        activity_date = row[0]

        midnight_utc = datetime.combine(
            activity_date,
            datetime_time.min,
            tzinfo=timezone.utc,
        )

        timestamps.append(
            int(
                midnight_utc.timestamp()
            )
        )

    return timestamps


def load_attempted_timestamps():
    attempted = set()

    if not RAW_ROOT.exists():
        return attempted

    for path in RAW_ROOT.rglob("*.json"):
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                payload = json.load(file)

        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        requested = payload.get(
            "requested_timestamps",
            [],
        )

        for timestamp in requested:
            try:
                attempted.add(
                    int(timestamp)
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

    return attempted


def chunked(
    values,
    size,
):
    for index in range(
        0,
        len(values),
        size,
    ):
        yield values[
            index:index + size
        ]


def request_prices(
    session,
    timestamps,
):
    request_payload = {
        PROVIDER_ASSET_ID: timestamps
    }

    params = {
        "coins": json.dumps(
            request_payload,
            separators=(",", ":"),
        )
    }

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = session.get(
                DEFILLAMA_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 429:
                wait_seconds = min(
                    2 ** attempt,
                    30,
                )

                print(
                    "Rate limited. "
                    f"Retrying in {wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            if (
                500
                <= response.status_code
                <= 599
            ):
                wait_seconds = min(
                    2 ** attempt,
                    30,
                )

                print(
                    "DefiLlama server error "
                    f"{response.status_code}. "
                    f"Retrying in {wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            response.raise_for_status()

            return response.json()

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            last_error = error

            if attempt == MAX_RETRIES:
                break

            wait_seconds = min(
                2 ** attempt,
                30,
            )

            print(
                "Request failed: "
                f"{error}. "
                f"Retrying in {wait_seconds}s..."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "Failed to fetch native ETH "
        "historical prices from DefiLlama"
    ) from last_error


def write_raw_batch(
    requested_timestamps,
    response_payload,
    batch_number,
):
    now = datetime.now(
        timezone.utc
    )

    ingestion_date = (
        now.date().isoformat()
    )

    directory = (
        RAW_ROOT
        / f"ingestion_date={ingestion_date}"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp_text = now.strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    filename = (
        "defillama_eth_native_"
        f"batch_{batch_number:04d}_"
        f"{timestamp_text}.json"
    )

    final_path = directory / filename

    temporary_path = (
        directory
        / f".{filename}.tmp"
    )

    payload = {
        "provider": PROVIDER,
        "provider_asset_id": (
            PROVIDER_ASSET_ID
        ),
        "asset_id": ASSET_ID,
        "symbol": SYMBOL,
        "quote_currency": (
            QUOTE_CURRENCY
        ),
        "requested_timestamps": (
            requested_timestamps
        ),
        "ingested_at_utc": (
            now.isoformat()
        ),
        "response": response_payload,
    }

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_path.replace(
        final_path
    )

    return final_path


def count_returned_prices(
    response_payload,
):
    coins = response_payload.get(
        "coins",
        {},
    )

    asset = coins.get(
        PROVIDER_ASSET_ID,
        {},
    )

    prices = asset.get(
        "prices",
        [],
    )

    if not isinstance(
        prices,
        list,
    ):
        return 0

    return len(prices)


def main():
    required_timestamps = (
        get_required_timestamps()
    )

    attempted_timestamps = (
        load_attempted_timestamps()
    )

    pending_timestamps = [
        timestamp
        for timestamp
        in required_timestamps
        if timestamp
        not in attempted_timestamps
    ]

    print()
    print("=" * 100)
    print(
        "NATIVE ETH PRICE INGESTION"
    )
    print("=" * 100)

    print(
        "Required activity-date prices:",
        len(required_timestamps),
    )

    print(
        "Already attempted:",
        len(
            set(required_timestamps)
            & attempted_timestamps
        ),
    )

    print(
        "New timestamps to request:",
        len(pending_timestamps),
    )

    if not pending_timestamps:
        print(
            "No new native ETH prices "
            "need to be requested."
        )
        return

    session = requests.Session()

    total_requested = 0
    total_returned = 0
    api_batches = 0

    try:
        for batch_number, batch in enumerate(
            chunked(
                pending_timestamps,
                MAX_TIMESTAMPS_PER_REQUEST,
            ),
            start=1,
        ):
            print()
            print(
                "Requesting batch",
                batch_number,
                "| points:",
                len(batch),
            )

            response_payload = (
                request_prices(
                    session,
                    batch,
                )
            )

            returned_count = (
                count_returned_prices(
                    response_payload
                )
            )

            raw_path = write_raw_batch(
                requested_timestamps=batch,
                response_payload=response_payload,
                batch_number=batch_number,
            )

            total_requested += len(
                batch
            )

            total_returned += (
                returned_count
            )

            api_batches += 1

            print(
                "Returned prices:",
                returned_count,
            )

            print(
                "Raw file:",
                raw_path,
            )

    finally:
        session.close()

    print()
    print("=" * 100)
    print(
        "NATIVE ETH PRICE INGESTION SUMMARY"
    )
    print("=" * 100)

    print(
        "Requested:",
        total_requested,
    )

    print(
        "Returned:",
        total_returned,
    )

    print(
        "Missing:",
        (
            total_requested
            - total_returned
        ),
    )

    print(
        "API batches:",
        api_batches,
    )


if __name__ == "__main__":
    main()