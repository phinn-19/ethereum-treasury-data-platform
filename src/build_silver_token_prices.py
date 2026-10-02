import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb


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


MAX_ALIGNMENT_SECONDS = (
    12 * 60 * 60
)


def parse_timestamp(
    value,
):
    if value is None:
        return None

    return datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )


def load_price_rows():
    if not RAW_ROOT.exists():
        raise FileNotFoundError(
            "Token price Bronze directory "
            f"not found: {RAW_ROOT}"
        )

    rows_by_key = {}

    raw_files = sorted(
        RAW_ROOT.glob(
            "ingestion_date=*/"
            "defillama_*_batch_*.json"
        )
    )

    if not raw_files:
        raise RuntimeError(
            "No token price Bronze files found"
        )

    print(
        "Bronze price files:",
        len(raw_files),
    )

    for file_path in raw_files:
        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        provider = payload[
            "provider"
        ]

        chain_id = int(
            payload[
                "chain_id"
            ]
        )

        chain_name = payload[
            "chain_name"
        ]

        quote_currency = payload[
            "quote_currency"
        ]

        asset_id = payload[
            "asset_id"
        ]

        configured_symbol = payload[
            "configured_symbol"
        ]

        token_contract = payload[
            "contract_address"
        ].lower()

        coin_key = payload[
            "coin_key"
        ]

        ingested_at_utc = parse_timestamp(
            payload[
                "ingested_at_utc"
            ]
        )

        requested_points = payload.get(
            "requested_points",
            [],
        )

        response_coin = (
            payload
            .get(
                "response",
                {},
            )
            .get(
                "coins",
                {},
            )
            .get(
                coin_key,
                {},
            )
        )

        provider_symbol = (
            response_coin.get(
                "symbol"
            )
        )

        prices = response_coin.get(
            "prices",
            [],
        )

        requested_by_timestamp = {
            int(
                point[
                    "requested_timestamp"
                ]
            ): point
            for point in requested_points
        }

        matched_prices = {}

        if requested_by_timestamp:
            for price in prices:
                source_timestamp = int(
                    price[
                        "timestamp"
                    ]
                )

                nearest_requested = min(
                    requested_by_timestamp,
                    key=lambda timestamp: abs(
                        timestamp
                        - source_timestamp
                    ),
                )

                delta_seconds = (
                    source_timestamp
                    - nearest_requested
                )

                if (
                    abs(
                        delta_seconds
                    )
                    > MAX_ALIGNMENT_SECONDS
                ):
                    raise RuntimeError(
                        "Price observation exceeds "
                        "12-hour alignment limit. "
                        f"Asset: {asset_id}, "
                        f"requested: "
                        f"{nearest_requested}, "
                        f"source: "
                        f"{source_timestamp}, "
                        f"delta: "
                        f"{delta_seconds}s"
                    )

                if (
                    nearest_requested
                    in matched_prices
                ):
                    raise RuntimeError(
                        "Multiple price observations "
                        "matched the same requested "
                        "timestamp. "
                        f"Asset: {asset_id}, "
                        f"requested: "
                        f"{nearest_requested}"
                    )

                matched_prices[
                    nearest_requested
                ] = price

        for (
            requested_timestamp,
            requested_point,
        ) in requested_by_timestamp.items():
            price = matched_prices.get(
                requested_timestamp
            )

            if price is None:
                price_status = (
                    "UNAVAILABLE"
                )

                source_timestamp = None
                source_delta_seconds = None
                price_usd = None
                confidence = None

            else:
                price_status = (
                    "AVAILABLE"
                )

                source_timestamp = int(
                    price[
                        "timestamp"
                    ]
                )

                source_delta_seconds = (
                    source_timestamp
                    - requested_timestamp
                )

                price_usd = Decimal(
                    str(
                        price[
                            "price"
                        ]
                    )
                )

                confidence_value = (
                    price.get(
                        "confidence"
                    )
                )

                confidence = (
                    float(
                        confidence_value
                    )
                    if confidence_value
                    is not None
                    else None
                )

            price_date = (
                requested_point[
                    "activity_date"
                ]
            )

            row = {
                "price_date": (
                    price_date
                ),
                "chain_id": (
                    chain_id
                ),
                "chain_name": (
                    chain_name
                ),
                "asset_id": (
                    asset_id
                ),
                "token_contract": (
                    token_contract
                ),
                "configured_symbol": (
                    configured_symbol
                ),
                "provider": (
                    provider
                ),
                "provider_symbol": (
                    provider_symbol
                ),
                "quote_currency": (
                    quote_currency
                ),
                "requested_timestamp": (
                    requested_timestamp
                ),
                "source_timestamp": (
                    source_timestamp
                ),
                "source_delta_seconds": (
                    source_delta_seconds
                ),
                "price_usd": (
                    price_usd
                ),
                "confidence": (
                    confidence
                ),
                "price_status": (
                    price_status
                ),
                "ingested_at_utc": (
                    ingested_at_utc
                ),
                "source_file": str(
                    file_path
                ),
            }

            key = (
                chain_id,
                token_contract,
                price_date,
            )

            existing = (
                rows_by_key.get(
                    key
                )
            )

            if (
                existing is None
                or
                (
                    ingested_at_utc
                    is not None
                    and (
                        existing[
                            "ingested_at_utc"
                        ]
                        is None
                        or
                        ingested_at_utc
                        > existing[
                            "ingested_at_utc"
                        ]
                    )
                )
            ):
                rows_by_key[
                    key
                ] = row

    return list(
        rows_by_key.values()
    )


def build_table(
    connection,
    rows,
):
    connection.execute(
        """
        CREATE SCHEMA
        IF NOT EXISTS silver
        """
    )

    connection.execute(
        """
        DROP TABLE IF EXISTS
        silver.token_prices_daily
        """
    )

    connection.execute(
        """
        CREATE TABLE
        silver.token_prices_daily (
            price_date DATE NOT NULL,

            chain_id INTEGER NOT NULL,

            chain_name VARCHAR NOT NULL,

            asset_id VARCHAR NOT NULL,

            token_contract VARCHAR NOT NULL,

            configured_symbol VARCHAR NOT NULL,

            provider VARCHAR NOT NULL,

            provider_symbol VARCHAR,

            quote_currency VARCHAR NOT NULL,

            requested_timestamp BIGINT NOT NULL,

            source_timestamp BIGINT,

            source_delta_seconds BIGINT,

            price_usd DECIMAL(38,18),

            confidence DOUBLE,

            price_status VARCHAR NOT NULL,

            ingested_at_utc TIMESTAMPTZ,

            source_file VARCHAR NOT NULL
        )
        """
    )

    insert_rows = []

    for row in rows:
        insert_rows.append(
            (
                row[
                    "price_date"
                ],
                row[
                    "chain_id"
                ],
                row[
                    "chain_name"
                ],
                row[
                    "asset_id"
                ],
                row[
                    "token_contract"
                ],
                row[
                    "configured_symbol"
                ],
                row[
                    "provider"
                ],
                row[
                    "provider_symbol"
                ],
                row[
                    "quote_currency"
                ],
                row[
                    "requested_timestamp"
                ],
                row[
                    "source_timestamp"
                ],
                row[
                    "source_delta_seconds"
                ],
                row[
                    "price_usd"
                ],
                row[
                    "confidence"
                ],
                row[
                    "price_status"
                ],
                row[
                    "ingested_at_utc"
                ],
                row[
                    "source_file"
                ],
            )
        )

    connection.executemany(
        """
        INSERT INTO
            silver.token_prices_daily
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?
        )
        """,
        insert_rows,
    )


def validate_table(
    connection,
    expected_total_rows,
):
    print()
    print(
        "=" * 100
    )
    print(
        "SILVER TOKEN PRICE SUMMARY"
    )
    print(
        "=" * 100
    )

    total_rows = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            silver.token_prices_daily
        """
    ).fetchone()[0]

    available_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'
            """
        ).fetchone()[0]
    )

    unavailable_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'UNAVAILABLE'
            """
        ).fetchone()[0]
    )

    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    price_date,
                    chain_id,
                    token_contract

                FROM
                    silver.token_prices_daily

                GROUP BY
                    price_date,
                    chain_id,
                    token_contract

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    invalid_available_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'

                AND (
                    price_usd IS NULL

                    OR

                    source_timestamp IS NULL

                    OR

                    source_delta_seconds
                        IS NULL
                )
            """
        ).fetchone()[0]
    )

    invalid_unavailable_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'UNAVAILABLE'

                AND (
                    price_usd IS NOT NULL

                    OR

                    source_timestamp
                        IS NOT NULL

                    OR

                    source_delta_seconds
                        IS NOT NULL
                )
            """
        ).fetchone()[0]
    )

    unexpected_status_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status NOT IN (
                    'AVAILABLE',
                    'UNAVAILABLE'
                )
            """
        ).fetchone()[0]
    )

    max_delta = connection.execute(
        """
        SELECT
            MAX(
                ABS(
                    source_delta_seconds
                )
            )

        FROM
            silver.token_prices_daily

        WHERE
            price_status = 'AVAILABLE'
        """
    ).fetchone()[0]

    over_one_hour = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'

                AND

                ABS(
                    source_delta_seconds
                ) > 3600
            """
        ).fetchone()[0]
    )

    over_alignment_limit = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'

                AND

                ABS(
                    source_delta_seconds
                ) > ?
            """,
            [
                MAX_ALIGNMENT_SECONDS
            ],
        ).fetchone()[0]
    )

    print(
        "Total price rows:",
        total_rows,
    )

    print(
        "AVAILABLE:",
        available_rows,
    )

    print(
        "UNAVAILABLE:",
        unavailable_rows,
    )

    print(
        "Duplicate grain groups:",
        duplicate_groups,
    )

    print(
        "Invalid AVAILABLE rows:",
        invalid_available_rows,
    )

    print(
        "Invalid UNAVAILABLE rows:",
        invalid_unavailable_rows,
    )

    print(
        "Unexpected price statuses:",
        unexpected_status_rows,
    )

    print(
        "Maximum absolute "
        "source delta:",
        max_delta,
        "seconds",
    )

    print(
        "Available rows > 1 hour "
        "from requested time:",
        over_one_hour,
    )

    print(
        "Rows over 12-hour "
        "alignment limit:",
        over_alignment_limit,
    )

    print()
    print(
        "Coverage by asset:"
    )

    rows = connection.execute(
        """
        SELECT
            asset_id,

            COUNT(*) AS total_dates,

            COUNT(
                CASE
                    WHEN
                        price_status
                            = 'AVAILABLE'
                    THEN 1
                END
            ) AS available_dates,

            COUNT(
                CASE
                    WHEN
                        price_status
                            = 'UNAVAILABLE'
                    THEN 1
                END
            ) AS unavailable_dates

        FROM
            silver.token_prices_daily

        GROUP BY
            asset_id

        ORDER BY
            asset_id
        """
    ).fetchall()

    for row in rows:
        print(
            "  ",
            row[0],
            "| total:",
            row[1],
            "| available:",
            row[2],
            "| unavailable:",
            row[3],
        )

    if total_rows != expected_total_rows:
        raise RuntimeError(
            "Silver price row count does not "
            "match normalized Bronze rows. "
            f"Expected {expected_total_rows}, "
            f"found {total_rows}"
        )

    if (
        available_rows
        + unavailable_rows
        != total_rows
    ):
        raise RuntimeError(
            "AVAILABLE + UNAVAILABLE does not "
            "equal total Silver price rows"
        )

    if duplicate_groups != 0:
        raise RuntimeError(
            "Duplicate Silver price grain "
            "detected"
        )

    if invalid_available_rows != 0:
        raise RuntimeError(
            "Invalid AVAILABLE price rows"
        )

    if invalid_unavailable_rows != 0:
        raise RuntimeError(
            "Invalid UNAVAILABLE price rows"
        )

    if unexpected_status_rows != 0:
        raise RuntimeError(
            "Unexpected Silver price status "
            "detected"
        )

    if over_alignment_limit != 0:
        raise RuntimeError(
            "Silver price rows exceed "
            "12-hour alignment limit"
        )

    print()
    print(
        "=" * 100
    )
    print(
        "SILVER TOKEN PRICE BUILD PASSED"
    )
    print(
        "=" * 100
    )


def main():
    rows = load_price_rows()

    print(
        "Normalized price rows:",
        len(rows),
    )

    connection = duckdb.connect(
        str(
            DATABASE_PATH
        )
    )

    try:
        connection.execute(
            """
            SET TimeZone = 'UTC'
            """
        )

        connection.execute(
            "BEGIN TRANSACTION"
        )

        build_table(
            connection,
            rows,
        )

        connection.execute(
            "COMMIT"
        )

    except Exception:
        connection.execute(
            "ROLLBACK"
        )

        raise

    try:
        validate_table(
            connection,
            len(rows),
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()