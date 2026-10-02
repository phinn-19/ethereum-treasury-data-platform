import json
import time
from datetime import datetime, time as datetime_time, timezone
from pathlib import Path

import duckdb
import requests


CONFIG_PATH = Path(
    "config",
    "assets.json",
)

DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
    "token_prices",
)


DEFILLAMA_BATCH_URL = (
    "https://coins.llama.fi/batchHistorical"
)


BATCH_SIZE = 50

MAX_RETRIES = 3

RETRY_BASE_SECONDS = 2

REQUEST_DELAY_SECONDS = 0.25


RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


def load_asset_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Asset config not found: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    return config


def get_activity_points(
    connection,
    contract_address,
):
    rows = connection.execute(
        """
        SELECT DISTINCT
            CAST(
                block_timestamp
                AS DATE
            ) AS activity_date

        FROM
            silver.erc20_transfers

        WHERE
            token_contract = ?

        ORDER BY
            activity_date
        """,
        [
            contract_address,
        ],
    ).fetchall()

    points = []

    for row in rows:
        activity_date = row[0]

        requested_datetime = datetime.combine(
            activity_date,
            datetime_time.min,
            tzinfo=timezone.utc,
        )

        points.append(
            {
                "activity_date": (
                    activity_date.isoformat()
                ),
                "requested_timestamp": int(
                    requested_datetime.timestamp()
                ),
            }
        )

    return points


def load_attempted_timestamps(
    asset_id,
):
    attempted = set()

    if not RAW_ROOT.exists():
        return attempted

    pattern = (
        f"ingestion_date=*/"
        f"defillama_{asset_id}_batch_*.json"
    )

    for file_path in RAW_ROOT.glob(
        pattern
    ):
        try:
            with file_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                payload = json.load(file)

        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        for point in payload.get(
            "requested_points",
            [],
        ):
            timestamp = point.get(
                "requested_timestamp"
            )

            if timestamp is not None:
                attempted.add(
                    int(timestamp)
                )

    return attempted


def chunk_points(
    points,
    batch_size,
):
    for start in range(
        0,
        len(points),
        batch_size,
    ):
        yield points[
            start:start + batch_size
        ]


def request_batch(
    coin_key,
    requested_timestamps,
):
    params = {
        "coins": json.dumps(
            {
                coin_key: requested_timestamps,
            },
            separators=(
                ",",
                ":",
            ),
        )
    }

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = requests.get(
                DEFILLAMA_BATCH_URL,
                params=params,
                timeout=20,
                headers={
                    "User-Agent": (
                        "ethereum-treasury-"
                        "data-platform/1.0"
                    )
                },
            )

            if (
                response.status_code
                in RETRYABLE_STATUS_CODES
            ):
                raise requests.HTTPError(
                    (
                        "Retryable HTTP status: "
                        f"{response.status_code}"
                    ),
                    response=response,
                )

            response.raise_for_status()

            return (
                response.json(),
                response.url,
            )

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            last_error = error

            if attempt == MAX_RETRIES:
                break

            sleep_seconds = (
                RETRY_BASE_SECONDS
                ** attempt
            )

            print(
                "    Request failed. "
                f"Retry {attempt}/{MAX_RETRIES} "
                f"in {sleep_seconds}s: "
                f"{error}"
            )

            time.sleep(
                sleep_seconds
            )

    raise RuntimeError(
        "DefiLlama request failed after "
        f"{MAX_RETRIES} attempts: "
        f"{last_error}"
    )


def build_output_path(
    asset_id,
    batch_number,
):
    now = datetime.now(
        timezone.utc
    )

    ingestion_date = (
        now.date().isoformat()
    )

    timestamp_text = now.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_directory = (
        RAW_ROOT
        / f"ingestion_date={ingestion_date}"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"defillama_{asset_id}"
        f"_batch_{batch_number:04d}"
        f"_{timestamp_text}.json"
    )

    return (
        output_directory
        / filename
    )


def write_json_atomic(
    output_path,
    payload,
):
    temp_path = output_path.with_suffix(
        ".json.tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temp_path.replace(
        output_path
    )


def get_returned_price_count(
    response_data,
    coin_key,
):
    coin_data = (
        response_data
        .get("coins", {})
        .get(coin_key)
    )

    if not coin_data:
        return 0

    prices = coin_data.get(
        "prices",
        []
    )

    if not isinstance(
        prices,
        list,
    ):
        return 0

    return len(
        prices
    )


def ingest_asset(
    connection,
    config,
    asset,
):
    asset_id = asset[
        "asset_id"
    ]

    symbol = asset[
        "symbol"
    ]

    contract_address = asset[
        "contract_address"
    ].lower()

    chain_name = config[
        "chain_name"
    ]

    coin_key = (
        f"{chain_name}:"
        f"{contract_address}"
    )

    print()
    print(
        f"{symbol} ({asset_id})"
    )

    activity_points = (
        get_activity_points(
            connection,
            contract_address,
        )
    )

    print(
        "  Activity dates:",
        len(activity_points),
    )

    if not activity_points:
        print(
            "  No Silver activity. Skip."
        )

        return {
            "requested": 0,
            "returned": 0,
            "skipped": 0,
            "batches": 0,
        }

    attempted_timestamps = (
        load_attempted_timestamps(
            asset_id
        )
    )

    missing_points = [
        point
        for point in activity_points
        if point[
            "requested_timestamp"
        ]
        not in attempted_timestamps
    ]

    skipped_count = (
        len(activity_points)
        - len(missing_points)
    )

    print(
        "  Already attempted:",
        skipped_count,
    )

    print(
        "  New price points:",
        len(missing_points),
    )

    if not missing_points:
        print(
            "  Nothing new to request."
        )

        return {
            "requested": 0,
            "returned": 0,
            "skipped": skipped_count,
            "batches": 0,
        }

    total_requested = 0
    total_returned = 0
    batch_count = 0

    for batch_number, batch in enumerate(
        chunk_points(
            missing_points,
            BATCH_SIZE,
        ),
        start=1,
    ):
        requested_timestamps = [
            point[
                "requested_timestamp"
            ]
            for point in batch
        ]

        print(
            f"  Batch {batch_number}: "
            f"requesting "
            f"{len(batch)} points..."
        )

        response_data, request_url = (
            request_batch(
                coin_key,
                requested_timestamps,
            )
        )

        returned_count = (
            get_returned_price_count(
                response_data,
                coin_key,
            )
        )

        ingested_at = datetime.now(
            timezone.utc
        ).isoformat()

        payload = {
            "provider": "defillama",
            "endpoint": (
                "batchHistorical"
            ),
            "ingested_at_utc": (
                ingested_at
            ),
            "chain_id": config[
                "chain_id"
            ],
            "chain_name": (
                chain_name
            ),
            "quote_currency": config[
                "quote_currency"
            ],
            "asset_id": asset_id,
            "configured_symbol": (
                symbol
            ),
            "contract_address": (
                contract_address
            ),
            "coin_key": coin_key,
            "requested_points": batch,
            "requested_count": len(
                batch
            ),
            "returned_count": (
                returned_count
            ),
            "request_url": (
                request_url
            ),
            "response": (
                response_data
            ),
        }

        output_path = (
            build_output_path(
                asset_id,
                batch_number,
            )
        )

        write_json_atomic(
            output_path,
            payload,
        )

        print(
            "    Returned:",
            returned_count,
        )

        print(
            "    Saved:",
            output_path,
        )

        total_requested += len(
            batch
        )

        total_returned += (
            returned_count
        )

        batch_count += 1

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    return {
        "requested": (
            total_requested
        ),
        "returned": (
            total_returned
        ),
        "skipped": (
            skipped_count
        ),
        "batches": (
            batch_count
        ),
    }


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "DuckDB database not found: "
            f"{DATABASE_PATH}"
        )

    config = load_asset_config()

    enabled_assets = [
        asset
        for asset in config[
            "assets"
        ]
        if asset.get(
            "price_enabled",
            False,
        )
    ]

    connection = duckdb.connect(
        str(
            DATABASE_PATH
        ),
        read_only=True,
    )

    try:
        connection.execute(
            """
            SET TimeZone = 'UTC'
            """
        )

        print(
            "=" * 100
        )
        print(
            "DEFILLAMA TOKEN PRICE INGESTION"
        )
        print(
            "=" * 100
        )

        print(
            "Configured assets:",
            len(
                config[
                    "assets"
                ]
            ),
        )

        print(
            "Price-enabled assets:",
            len(
                enabled_assets
            ),
        )

        summary = {
            "requested": 0,
            "returned": 0,
            "skipped": 0,
            "batches": 0,
        }

        for asset in enabled_assets:
            result = ingest_asset(
                connection,
                config,
                asset,
            )

            for key in summary:
                summary[key] += (
                    result[key]
                )

    finally:
        connection.close()

    print()
    print(
        "=" * 100
    )
    print(
        "PRICE INGESTION SUMMARY"
    )
    print(
        "=" * 100
    )

    print(
        "New price points requested:",
        summary[
            "requested"
        ],
    )

    print(
        "Price observations returned:",
        summary[
            "returned"
        ],
    )

    print(
        "Existing points skipped:",
        summary[
            "skipped"
        ],
    )

    print(
        "API batches:",
        summary[
            "batches"
        ],
    )

    missing_count = (
        summary[
            "requested"
        ]
        - summary[
            "returned"
        ]
    )

    print(
        "Requested points without "
        "returned observation:",
        missing_count,
    )


if __name__ == "__main__":
    main()