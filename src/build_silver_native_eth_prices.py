import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
    "native_eth_prices",
)

CHAIN_ID = 1
CHAIN_NAME = "ethereum"

ASSET_ID = "eth_native"
ASSET_TYPE = "native"
CONFIGURED_SYMBOL = "ETH"

PROVIDER = "defillama"
PROVIDER_ASSET_ID = "coingecko:ethereum"
QUOTE_CURRENCY = "USD"

MAX_ALIGNMENT_DELTA_SECONDS = (
    12 * 60 * 60
)


def parse_datetime(value):
    if value is None:
        return None

    parsed = datetime.fromisoformat(
        str(value).replace(
            "Z",
            "+00:00",
        )
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def parse_decimal(value):
    if value is None:
        return None

    try:
        result = Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None

    if not result.is_finite():
        return None

    return result


def parse_confidence(value):
    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def timestamp_to_date(
    timestamp,
):
    return datetime.fromtimestamp(
        int(timestamp),
        tz=timezone.utc,
    ).date()


def match_requested_to_prices(
    requested_timestamps,
    price_points,
):
    """
    Match each requested timestamp to at most one
    returned source price, and each source price
    to at most one requested timestamp.

    Only matches inside the 12-hour guardrail.
    """

    candidates = []

    for requested_timestamp in (
        requested_timestamps
    ):
        for point in price_points:
            source_timestamp = point[
                "timestamp"
            ]

            delta = (
                source_timestamp
                - requested_timestamp
            )

            absolute_delta = abs(
                delta
            )

            if (
                absolute_delta
                <= MAX_ALIGNMENT_DELTA_SECONDS
            ):
                candidates.append(
                    (
                        absolute_delta,
                        requested_timestamp,
                        source_timestamp,
                        delta,
                        point,
                    )
                )

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        )
    )

    matched_requested = set()
    matched_sources = set()

    matches = {}

    for (
        _,
        requested_timestamp,
        source_timestamp,
        delta,
        point,
    ) in candidates:
        if (
            requested_timestamp
            in matched_requested
        ):
            continue

        if (
            source_timestamp
            in matched_sources
        ):
            continue

        matches[
            requested_timestamp
        ] = {
            "point": point,
            "delta": delta,
        }

        matched_requested.add(
            requested_timestamp
        )

        matched_sources.add(
            source_timestamp
        )

    return matches


def read_raw_records():
    if not RAW_ROOT.exists():
        raise FileNotFoundError(
            "Native ETH price Bronze "
            f"directory not found: {RAW_ROOT}"
        )

    records = []

    raw_files = sorted(
        RAW_ROOT.rglob("*.json")
    )

    if not raw_files:
        raise RuntimeError(
            "No native ETH price Bronze "
            "JSON files found"
        )

    for path in raw_files:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(
                file
            )

        provider = payload.get(
            "provider"
        )

        provider_asset_id = payload.get(
            "provider_asset_id"
        )

        asset_id = payload.get(
            "asset_id"
        )

        configured_symbol = payload.get(
            "symbol"
        )

        quote_currency = payload.get(
            "quote_currency"
        )

        ingested_at_utc = (
            parse_datetime(
                payload.get(
                    "ingested_at_utc"
                )
            )
        )

        if provider != PROVIDER:
            raise RuntimeError(
                "Unexpected provider in "
                f"{path}: {provider}"
            )

        if (
            provider_asset_id
            != PROVIDER_ASSET_ID
        ):
            raise RuntimeError(
                "Unexpected provider asset "
                f"in {path}: "
                f"{provider_asset_id}"
            )

        if asset_id != ASSET_ID:
            raise RuntimeError(
                "Unexpected asset_id in "
                f"{path}: {asset_id}"
            )

        if (
            configured_symbol
            != CONFIGURED_SYMBOL
        ):
            raise RuntimeError(
                "Unexpected ETH symbol in "
                f"{path}: "
                f"{configured_symbol}"
            )

        if (
            quote_currency
            != QUOTE_CURRENCY
        ):
            raise RuntimeError(
                "Unexpected quote currency "
                f"in {path}: "
                f"{quote_currency}"
            )

        if ingested_at_utc is None:
            raise RuntimeError(
                "Missing ingested_at_utc "
                f"in {path}"
            )

        requested_raw = payload.get(
            "requested_timestamps",
            [],
        )

        requested_timestamps = []

        for value in requested_raw:
            requested_timestamps.append(
                int(value)
            )

        response = payload.get(
            "response",
            {},
        )

        coins = response.get(
            "coins",
            {},
        )

        asset_response = coins.get(
            PROVIDER_ASSET_ID,
            {},
        )

        provider_symbol = (
            asset_response.get(
                "symbol"
            )
        )

        prices_raw = asset_response.get(
            "prices",
            [],
        )

        price_points = []

        if isinstance(
            prices_raw,
            list,
        ):
            for point in prices_raw:
                if not isinstance(
                    point,
                    dict,
                ):
                    continue

                try:
                    source_timestamp = int(
                        point.get(
                            "timestamp"
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                price_usd = parse_decimal(
                    point.get(
                        "price"
                    )
                )

                confidence = (
                    parse_confidence(
                        point.get(
                            "confidence"
                        )
                    )
                )

                price_points.append(
                    {
                        "timestamp": (
                            source_timestamp
                        ),
                        "price_usd": (
                            price_usd
                        ),
                        "confidence": (
                            confidence
                        ),
                    }
                )

        matches = (
            match_requested_to_prices(
                requested_timestamps,
                price_points,
            )
        )

        for requested_timestamp in (
            requested_timestamps
        ):
            match = matches.get(
                requested_timestamp
            )

            if match is None:
                records.append(
                    (
                        timestamp_to_date(
                            requested_timestamp
                        ),
                        CHAIN_ID,
                        CHAIN_NAME,
                        ASSET_ID,
                        ASSET_TYPE,
                        CONFIGURED_SYMBOL,
                        PROVIDER,
                        PROVIDER_ASSET_ID,
                        provider_symbol,
                        QUOTE_CURRENCY,
                        requested_timestamp,
                        None,
                        None,
                        None,
                        None,
                        "UNAVAILABLE",
                        ingested_at_utc,
                        str(path),
                    )
                )

                continue

            point = match[
                "point"
            ]

            source_timestamp = (
                point["timestamp"]
            )

            source_delta_seconds = (
                match["delta"]
            )

            price_usd = point[
                "price_usd"
            ]

            confidence = point[
                "confidence"
            ]

            if (
                price_usd is not None
                and price_usd > 0
            ):
                price_status = (
                    "AVAILABLE"
                )

            else:
                price_status = (
                    "UNAVAILABLE"
                )

                source_timestamp = None
                source_delta_seconds = None
                price_usd = None
                confidence = None

            records.append(
                (
                    timestamp_to_date(
                        requested_timestamp
                    ),
                    CHAIN_ID,
                    CHAIN_NAME,
                    ASSET_ID,
                    ASSET_TYPE,
                    CONFIGURED_SYMBOL,
                    PROVIDER,
                    PROVIDER_ASSET_ID,
                    provider_symbol,
                    QUOTE_CURRENCY,
                    requested_timestamp,
                    source_timestamp,
                    source_delta_seconds,
                    price_usd,
                    confidence,
                    price_status,
                    ingested_at_utc,
                    str(path),
                )
            )

    return records


def create_stage_table(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        temp.native_eth_price_stage
        """
    )

    connection.execute(
        """
        CREATE TEMP TABLE
        native_eth_price_stage (
            price_date DATE,
            chain_id INTEGER,
            chain_name VARCHAR,
            asset_id VARCHAR,
            asset_type VARCHAR,
            configured_symbol VARCHAR,
            provider VARCHAR,
            provider_asset_id VARCHAR,
            provider_symbol VARCHAR,
            quote_currency VARCHAR,
            requested_timestamp BIGINT,
            source_timestamp BIGINT,
            source_delta_seconds BIGINT,
            price_usd DECIMAL(38,18),
            confidence DOUBLE,
            price_status VARCHAR,
            ingested_at_utc
                TIMESTAMP WITH TIME ZONE,
            source_file VARCHAR
        )
        """
    )


def insert_stage_records(
    connection,
    records,
):
    if not records:
        raise RuntimeError(
            "No native ETH price records "
            "were parsed from Bronze"
        )

    connection.executemany(
        """
        INSERT INTO
            native_eth_price_stage
        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        """,
        records,
    )


def build_silver_table(
    connection,
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
        silver.native_eth_prices_daily
        """
    )

    connection.execute(
        """
        CREATE TABLE
        silver.native_eth_prices_daily
        AS

        WITH ranked AS (
            SELECT
                *,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        price_date,
                        chain_id,
                        asset_id

                    ORDER BY
                        ingested_at_utc DESC,
                        source_file DESC
                ) AS attempt_rank

            FROM
                native_eth_price_stage
        )

        SELECT
            price_date,
            chain_id,
            chain_name,
            asset_id,
            asset_type,
            configured_symbol,
            provider,
            provider_asset_id,
            provider_symbol,
            quote_currency,
            requested_timestamp,
            source_timestamp,
            source_delta_seconds,
            price_usd,
            confidence,
            price_status,
            ingested_at_utc,
            source_file

        FROM ranked

        WHERE
            attempt_rank = 1
        """
    )


def validate_table(
    connection,
):
    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    price_date,
                    chain_id,
                    asset_id

                FROM
                    silver.native_eth_prices_daily

                GROUP BY
                    price_date,
                    chain_id,
                    asset_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    invalid_available = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily

            WHERE
                price_status = 'AVAILABLE'

                AND (
                    price_usd IS NULL
                    OR price_usd <= 0
                    OR source_timestamp IS NULL
                    OR source_delta_seconds IS NULL
                )
            """
        ).fetchone()[0]
    )

    invalid_unavailable = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily

            WHERE
                price_status = 'UNAVAILABLE'

                AND (
                    price_usd IS NOT NULL
                    OR source_timestamp IS NOT NULL
                    OR source_delta_seconds
                        IS NOT NULL
                    OR confidence IS NOT NULL
                )
            """
        ).fetchone()[0]
    )

    unexpected_status = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily

            WHERE
                price_status NOT IN (
                    'AVAILABLE',
                    'UNAVAILABLE'
                )

                OR price_status IS NULL
            """
        ).fetchone()[0]
    )

    over_alignment_guardrail = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily

            WHERE
                price_status = 'AVAILABLE'

                AND

                ABS(
                    source_delta_seconds
                ) > ?
            """,
            [
                MAX_ALIGNMENT_DELTA_SECONDS
            ],
        ).fetchone()[0]
    )

    invalid_confidence = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily

            WHERE
                confidence IS NOT NULL

                AND (
                    confidence < 0
                    OR confidence > 1
                )
            """
        ).fetchone()[0]
    )

    print(
        "Duplicate daily price groups:",
        duplicate_groups,
    )

    print(
        "Invalid AVAILABLE rows:",
        invalid_available,
    )

    print(
        "Invalid UNAVAILABLE rows:",
        invalid_unavailable,
    )

    print(
        "Unexpected statuses:",
        unexpected_status,
    )

    print(
        "Rows over 12h alignment:",
        over_alignment_guardrail,
    )

    print(
        "Invalid confidence rows:",
        invalid_confidence,
    )

    if duplicate_groups != 0:
        raise RuntimeError(
            "Duplicate native ETH daily prices"
        )

    if invalid_available != 0:
        raise RuntimeError(
            "Invalid AVAILABLE native ETH "
            "price rows"
        )

    if invalid_unavailable != 0:
        raise RuntimeError(
            "Invalid UNAVAILABLE native ETH "
            "price rows"
        )

    if unexpected_status != 0:
        raise RuntimeError(
            "Unexpected native ETH price status"
        )

    if over_alignment_guardrail != 0:
        raise RuntimeError(
            "Native ETH price exceeds "
            "12-hour alignment guardrail"
        )

    if invalid_confidence != 0:
        raise RuntimeError(
            "Invalid native ETH price confidence"
        )


def check_activity_date_coverage(
    connection,
):
    expected_count = (
        connection.execute(
            """
            WITH expected_dates AS (
                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.transactions

                WHERE
                    value_eth_decimal > 0
                    AND receipt_status = 1
                    AND is_error IS NOT TRUE

                UNION

                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.internal_transactions

                WHERE
                    value_eth_decimal > 0
                    AND is_error IS NOT TRUE
            )

            SELECT COUNT(*)
            FROM expected_dates
            """
        ).fetchone()[0]
    )

    actual_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily
            """
        ).fetchone()[0]
    )

    missing_dates = (
        connection.execute(
            """
            WITH expected_dates AS (
                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.transactions

                WHERE
                    value_eth_decimal > 0
                    AND receipt_status = 1
                    AND is_error IS NOT TRUE

                UNION

                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.internal_transactions

                WHERE
                    value_eth_decimal > 0
                    AND is_error IS NOT TRUE
            )

            SELECT COUNT(*)

            FROM expected_dates AS e

            LEFT JOIN
                silver.native_eth_prices_daily
                AS p

                ON
                    e.activity_date
                        = p.price_date

            WHERE
                p.price_date IS NULL
            """
        ).fetchone()[0]
    )

    extra_dates = (
        connection.execute(
            """
            WITH expected_dates AS (
                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.transactions

                WHERE
                    value_eth_decimal > 0
                    AND receipt_status = 1
                    AND is_error IS NOT TRUE

                UNION

                SELECT DISTINCT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date

                FROM
                    silver.internal_transactions

                WHERE
                    value_eth_decimal > 0
                    AND is_error IS NOT TRUE
            )

            SELECT COUNT(*)

            FROM
                silver.native_eth_prices_daily
                AS p

            LEFT JOIN
                expected_dates AS e

                ON
                    p.price_date
                        = e.activity_date

            WHERE
                e.activity_date IS NULL
            """
        ).fetchone()[0]
    )

    print()
    print(
        "Expected native ETH activity dates:",
        expected_count,
    )

    print(
        "Actual native ETH price rows:",
        actual_count,
    )

    print(
        "Missing activity dates:",
        missing_dates,
    )

    print(
        "Extra price dates:",
        extra_dates,
    )

    if expected_count != actual_count:
        raise RuntimeError(
            "Native ETH price row count "
            "does not match activity dates"
        )

    if missing_dates != 0:
        raise RuntimeError(
            "Missing native ETH activity-date "
            "prices"
        )

    if extra_dates != 0:
        raise RuntimeError(
            "Unexpected native ETH price dates"
        )


def print_summary(
    connection,
):
    print()
    print("=" * 100)
    print(
        "SILVER NATIVE ETH PRICE BUILD"
    )
    print("=" * 100)

    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total_rows,

            COUNT(
                CASE
                    WHEN
                        price_status = 'AVAILABLE'
                    THEN 1
                END
            ) AS available_rows,

            COUNT(
                CASE
                    WHEN
                        price_status = 'UNAVAILABLE'
                    THEN 1
                END
            ) AS unavailable_rows,

            MAX(
                ABS(
                    source_delta_seconds
                )
            ) AS max_delta_seconds

        FROM
            silver.native_eth_prices_daily
        """
    ).fetchone()

    print(
        "Total rows:",
        row[0],
    )

    print(
        "AVAILABLE:",
        row[1],
    )

    print(
        "UNAVAILABLE:",
        row[2],
    )

    print(
        "Max absolute source delta:",
        row[3],
        "seconds",
    )

    range_row = connection.execute(
        """
        SELECT
            MIN(price_date),
            MAX(price_date),
            MIN(price_usd),
            MAX(price_usd)

        FROM
            silver.native_eth_prices_daily

        WHERE
            price_status = 'AVAILABLE'
        """
    ).fetchone()

    print(
        "Price date range:",
        range_row[0],
        "->",
        range_row[1],
    )

    print(
        "Min ETH price:",
        range_row[2],
    )

    print(
        "Max ETH price:",
        range_row[3],
    )


def main():
    records = read_raw_records()

    connection = duckdb.connect(
        str(DATABASE_PATH)
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

        create_stage_table(
            connection
        )

        insert_stage_records(
            connection,
            records,
        )

        build_silver_table(
            connection
        )

        validate_table(
            connection
        )

        check_activity_date_coverage(
            connection
        )

        connection.execute(
            "COMMIT"
        )

    except Exception:
        try:
            connection.execute(
                "ROLLBACK"
            )
        except Exception:
            pass

        raise

    try:
        print_summary(
            connection
        )

        print()
        print("=" * 100)
        print(
            "SILVER NATIVE ETH PRICE BUILD PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
    