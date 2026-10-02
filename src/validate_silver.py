import json
from pathlib import Path

import duckdb


SILVER_DB_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)

ASSET_CONFIG_PATH = Path(
    "config",
    "assets.json",
)

MAX_PRICE_ALIGNMENT_SECONDS = 12 * 60 * 60


KNOWN_WETH_TX = (
    "0xb35666a6280f0b796502afff1b4e7707"
    "24448cfde00a8da96a5b7aaaeccd8639"
)

ENDOWMENT_WALLET_ID = "endowment"

WETH_CONTRACT = (
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
)

EXPECTED_WETH_VALUE_RAW = (
    "250000000000000000000"
)

CREATE2_TX = (
    "0xafd94af14c9d5b7b77db8ed502c7ea7d"
    "141a779d54e599782f9ae3fb649b2f55"
)


def fail(message):
    raise RuntimeError(
        f"VALIDATION FAILED: {message}"
    )


def section(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def load_price_config():
    if not ASSET_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "Asset config not found: "
            f"{ASSET_CONFIG_PATH}"
        )

    with ASSET_CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    enabled_assets = [
        asset
        for asset in config.get("assets", [])
        if asset.get("price_enabled", False)
    ]

    if not enabled_assets:
        fail(
            "No price-enabled assets found "
            "in config/assets.json"
        )

    asset_ids = [
        asset["asset_id"]
        for asset in enabled_assets
    ]

    contracts = [
        asset["contract_address"].lower()
        for asset in enabled_assets
    ]

    if len(asset_ids) != len(set(asset_ids)):
        fail(
            "Duplicate asset_id values found "
            "in config/assets.json"
        )

    if len(contracts) != len(set(contracts)):
        fail(
            "Duplicate price-enabled contract "
            "addresses found in config/assets.json"
        )

    return config, enabled_assets


def check_table_counts(
    connection,
):
    section(
        "TABLE COUNTS"
    )

    tables = [
        "wallets",
        "transactions",
        "erc20_transfers",
        "internal_transactions",
        "token_prices_daily",
    ]

    for table_name in tables:
        count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM silver.{table_name}
            """
        ).fetchone()[0]

        print(
            table_name,
            ":",
            count,
        )

        if count == 0:
            fail(
                f"silver.{table_name} "
                "is empty"
            )


def check_wallet_count(
    connection,
):
    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM silver.wallets
        """
    ).fetchone()[0]

    print()
    print(
        "Monitoring wallets:",
        count,
    )

    if count != 5:
        fail(
            "Expected 5 monitored "
            f"wallets, got {count}"
        )


def check_other_directions(
    connection,
):
    section(
        "DIRECTION CHECK"
    )

    tables = [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]

    for table_name in tables:
        count = connection.execute(
            f"""
            SELECT COUNT(*)

            FROM silver.{table_name}

            WHERE direction = 'OTHER'
            """
        ).fetchone()[0]

        print(
            table_name,
            "OTHER rows:",
            count,
        )

        if count != 0:
            fail(
                f"silver.{table_name} "
                f"contains {count} OTHER rows"
            )


def check_duplicate_activity_ids(
    connection,
):
    section(
        "ACTIVITY ID CHECK"
    )

    tables = [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]

    for table_name in tables:
        duplicate_groups = (
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM (
                    SELECT
                        activity_id

                    FROM silver.{table_name}

                    GROUP BY
                        activity_id

                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )

        print(
            table_name,
            "duplicate activity IDs:",
            duplicate_groups,
        )

        if duplicate_groups != 0:
            fail(
                f"silver.{table_name} "
                "contains duplicate "
                "activity_id values"
            )


def check_erc20_event_identity(
    connection,
):
    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    wallet_id,
                    transaction_hash,
                    log_index

                FROM silver.erc20_transfers

                GROUP BY
                    wallet_id,
                    transaction_hash,
                    log_index

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    null_log_indexes = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.erc20_transfers

            WHERE log_index IS NULL
            """
        ).fetchone()[0]
    )

    section(
        "ERC20 EVENT IDENTITY CHECK"
    )

    print(
        "Duplicate "
        "(wallet, tx, log_index) groups:",
        duplicate_groups,
    )

    print(
        "NULL log_index rows:",
        null_log_indexes,
    )

    if duplicate_groups != 0:
        fail(
            "ERC20 event identity "
            "contains duplicates"
        )

    if null_log_indexes != 0:
        fail(
            "ERC20 rows exist without "
            "log_index"
        )


def check_known_weth_regression(
    connection,
):
    rows = connection.execute(
        """
        SELECT
            log_index,
            value_raw,
            from_address,
            to_address

        FROM silver.erc20_transfers

        WHERE
            wallet_id = ?
            AND transaction_hash = ?
            AND token_contract = ?
            AND value_raw = ?

        ORDER BY
            log_index
        """,
        [
            ENDOWMENT_WALLET_ID,
            KNOWN_WETH_TX,
            WETH_CONTRACT,
            EXPECTED_WETH_VALUE_RAW,
        ],
    ).fetchall()

    section(
        "KNOWN WETH REGRESSION CHECK"
    )

    print(
        "Matching rows:",
        len(rows),
    )

    for row in rows:
        print(
            "  log_index:",
            row[0],
            "| value_raw:",
            row[1],
            "| from:",
            row[2],
            "| to:",
            row[3],
        )

    actual_log_indexes = [
        row[0]
        for row in rows
    ]

    expected_log_indexes = [
        13,
        14,
        15,
    ]

    if (
        actual_log_indexes
        != expected_log_indexes
    ):
        fail(
            "Known 3x250 WETH transfer "
            "was not preserved correctly. "
            f"Expected log indexes "
            f"{expected_log_indexes}, "
            f"got {actual_log_indexes}"
        )


def check_create2_regression(
    connection,
):
    rows = connection.execute(
        """
        SELECT
            wallet_id,
            transaction_hash,
            contract_address,
            call_type,
            direction

        FROM silver.internal_transactions

        WHERE
            wallet_id = ?
            AND transaction_hash = ?
        """,
        [
            ENDOWMENT_WALLET_ID,
            CREATE2_TX,
        ],
    ).fetchall()

    section(
        "CREATE2 REGRESSION CHECK"
    )

    for row in rows:
        print(
            "wallet_id:",
            row[0],
            "| tx:",
            row[1],
            "| contract:",
            row[2],
            "| call_type:",
            row[3],
            "| direction:",
            row[4],
        )

    if len(rows) != 1:
        fail(
            "Expected exactly one "
            "Endowment CREATE2 row, "
            f"got {len(rows)}"
        )

    row = rows[0]

    if row[3] != "create2":
        fail(
            "Known Endowment creation "
            "row is not call_type=create2"
        )

    if row[4] != "CREATE":
        fail(
            "Known Endowment creation "
            "row is not direction=CREATE"
        )


def check_token_price_quality(
    connection,
):
    section(
        "TOKEN PRICE QUALITY CHECK"
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

                FROM silver.token_prices_daily

                GROUP BY
                    price_date,
                    chain_id,
                    token_contract

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    unexpected_status_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                price_status NOT IN (
                    'AVAILABLE',
                    'UNAVAILABLE'
                )
            """
        ).fetchone()[0]
    )

    invalid_available_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

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

    invalid_unavailable_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                price_status = 'UNAVAILABLE'
                AND (
                    price_usd IS NOT NULL
                    OR source_timestamp IS NOT NULL
                    OR source_delta_seconds IS NOT NULL
                    OR confidence IS NOT NULL
                )
            """
        ).fetchone()[0]
    )

    delta_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'
                AND source_delta_seconds
                    IS DISTINCT FROM
                    source_timestamp
                    - requested_timestamp
            """
        ).fetchone()[0]
    )

    over_alignment_limit = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                price_status = 'AVAILABLE'
                AND ABS(source_delta_seconds) > ?
            """,
            [
                MAX_PRICE_ALIGNMENT_SECONDS,
            ],
        ).fetchone()[0]
    )

    invalid_confidence_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                confidence IS NOT NULL
                AND (
                    confidence < 0
                    OR confidence > 1
                )
            """
        ).fetchone()[0]
    )

    total_rows, available_rows, unavailable_rows = (
        connection.execute(
            """
            SELECT
                COUNT(*),
                COUNT(
                    CASE
                        WHEN price_status = 'AVAILABLE'
                        THEN 1
                    END
                ),
                COUNT(
                    CASE
                        WHEN price_status = 'UNAVAILABLE'
                        THEN 1
                    END
                )

            FROM silver.token_prices_daily
            """
        ).fetchone()
    )

    max_delta = connection.execute(
        """
        SELECT
            MAX(
                ABS(source_delta_seconds)
            )

        FROM silver.token_prices_daily

        WHERE price_status = 'AVAILABLE'
        """
    ).fetchone()[0]

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
        "Duplicate price grain groups:",
        duplicate_groups,
    )

    print(
        "Unexpected price statuses:",
        unexpected_status_rows,
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
        "Source delta mismatches:",
        delta_mismatches,
    )

    print(
        "Rows over 12-hour alignment limit:",
        over_alignment_limit,
    )

    print(
        "Invalid confidence rows:",
        invalid_confidence_rows,
    )

    print(
        "Maximum absolute source delta:",
        max_delta,
        "seconds",
    )

    if (
        available_rows
        + unavailable_rows
        != total_rows
    ):
        fail(
            "AVAILABLE + UNAVAILABLE does not "
            "equal total token price rows"
        )

    if duplicate_groups != 0:
        fail(
            "Duplicate token price grain "
            "detected"
        )

    if unexpected_status_rows != 0:
        fail(
            "Unexpected token price status "
            "detected"
        )

    if invalid_available_rows != 0:
        fail(
            "Invalid AVAILABLE token price "
            "rows detected"
        )

    if invalid_unavailable_rows != 0:
        fail(
            "Invalid UNAVAILABLE token price "
            "rows detected"
        )

    if delta_mismatches != 0:
        fail(
            "Token price source delta values "
            "are inconsistent"
        )

    if over_alignment_limit != 0:
        fail(
            "Token price rows exceed the "
            "12-hour alignment limit"
        )

    if invalid_confidence_rows != 0:
        fail(
            "Token price confidence values "
            "fall outside 0..1"
        )


def check_token_price_metadata(
    connection,
    config,
    enabled_assets,
):
    section(
        "TOKEN PRICE METADATA CHECK"
    )

    expected_chain_id = int(
        config["chain_id"]
    )

    expected_chain_name = config[
        "chain_name"
    ]

    expected_quote_currency = config[
        "quote_currency"
    ]

    global_mismatches = connection.execute(
        """
        SELECT COUNT(*)

        FROM silver.token_prices_daily

        WHERE
            chain_id IS DISTINCT FROM ?
            OR chain_name IS DISTINCT FROM ?
            OR quote_currency IS DISTINCT FROM ?
        """,
        [
            expected_chain_id,
            expected_chain_name,
            expected_quote_currency,
        ],
    ).fetchone()[0]

    configured_contracts = {
        asset["contract_address"].lower()
        for asset in enabled_assets
    }

    actual_contracts = {
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT token_contract
            FROM silver.token_prices_daily
            """
        ).fetchall()
    }

    unexpected_contracts = (
        actual_contracts
        - configured_contracts
    )

    metadata_mismatches = 0

    for asset in enabled_assets:
        contract = asset[
            "contract_address"
        ].lower()

        mismatch_count = connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.token_prices_daily

            WHERE
                token_contract = ?
                AND (
                    asset_id IS DISTINCT FROM ?
                    OR configured_symbol
                        IS DISTINCT FROM ?
                    OR provider
                        IS DISTINCT FROM ?
                )
            """,
            [
                contract,
                asset["asset_id"],
                asset["symbol"],
                asset["price_source"],
            ],
        ).fetchone()[0]

        metadata_mismatches += mismatch_count

    print(
        "Global chain/currency mismatches:",
        global_mismatches,
    )

    print(
        "Asset metadata mismatches:",
        metadata_mismatches,
    )

    print(
        "Unexpected priced contracts:",
        len(unexpected_contracts),
    )

    if unexpected_contracts:
        for contract in sorted(
            unexpected_contracts
        ):
            print(
                "  unexpected:",
                contract,
            )

    if global_mismatches != 0:
        fail(
            "Token price chain or quote "
            "currency metadata is incorrect"
        )

    if metadata_mismatches != 0:
        fail(
            "Token price asset metadata "
            "does not match config/assets.json"
        )

    if unexpected_contracts:
        fail(
            "Silver token prices contain "
            "contracts that are not currently "
            "price-enabled in config/assets.json"
        )


def check_token_price_coverage(
    connection,
    enabled_assets,
):
    section(
        "TOKEN PRICE COVERAGE CHECK"
    )

    total_expected_dates = 0
    total_actual_dates = 0
    total_missing_dates = 0
    total_extra_dates = 0

    for asset in enabled_assets:
        asset_id = asset[
            "asset_id"
        ]

        contract = asset[
            "contract_address"
        ].lower()

        expected_dates = connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    CAST(block_timestamp AS DATE)
                        AS activity_date

                FROM silver.erc20_transfers

                WHERE token_contract = ?
            )
            """,
            [
                contract,
            ],
        ).fetchone()[0]

        actual_total, available, unavailable = (
            connection.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(
                        CASE
                            WHEN price_status = 'AVAILABLE'
                            THEN 1
                        END
                    ),
                    COUNT(
                        CASE
                            WHEN price_status = 'UNAVAILABLE'
                            THEN 1
                        END
                    )

                FROM silver.token_prices_daily

                WHERE token_contract = ?
                """,
                [
                    contract,
                ],
            ).fetchone()
        )

        missing_dates = connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    CAST(block_timestamp AS DATE)
                        AS price_date

                FROM silver.erc20_transfers

                WHERE token_contract = ?

                EXCEPT

                SELECT price_date

                FROM silver.token_prices_daily

                WHERE token_contract = ?
            )
            """,
            [
                contract,
                contract,
            ],
        ).fetchone()[0]

        extra_dates = connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT price_date

                FROM silver.token_prices_daily

                WHERE token_contract = ?

                EXCEPT

                SELECT DISTINCT
                    CAST(block_timestamp AS DATE)
                        AS price_date

                FROM silver.erc20_transfers

                WHERE token_contract = ?
            )
            """,
            [
                contract,
                contract,
            ],
        ).fetchone()[0]

        print(
            " ",
            asset_id,
            "| expected:",
            expected_dates,
            "| actual:",
            actual_total,
            "| available:",
            available,
            "| unavailable:",
            unavailable,
            "| missing:",
            missing_dates,
            "| extra:",
            extra_dates,
        )

        total_expected_dates += (
            expected_dates
        )

        total_actual_dates += (
            actual_total
        )

        total_missing_dates += (
            missing_dates
        )

        total_extra_dates += (
            extra_dates
        )

    print()
    print(
        "Expected activity-date price rows:",
        total_expected_dates,
    )

    print(
        "Actual Silver price rows:",
        total_actual_dates,
    )

    print(
        "Missing activity dates:",
        total_missing_dates,
    )

    print(
        "Extra price dates:",
        total_extra_dates,
    )

    if total_missing_dates != 0:
        fail(
            "Price-enabled ERC20 activity "
            "dates are missing from "
            "silver.token_prices_daily"
        )

    if total_extra_dates != 0:
        fail(
            "silver.token_prices_daily "
            "contains dates without matching "
            "ERC20 activity"
        )

    if (
        total_expected_dates
        != total_actual_dates
    ):
        fail(
            "Token price coverage row count "
            "does not reconcile with Silver "
            "ERC20 activity dates"
        )


def print_direction_summary(
    connection,
):
    section(
        "DIRECTION SUMMARY"
    )

    for table_name in [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]:
        print()
        print(
            table_name
        )

        rows = connection.execute(
            f"""
            SELECT
                wallet_id,
                direction,
                COUNT(*) AS row_count

            FROM silver.{table_name}

            GROUP BY
                wallet_id,
                direction

            ORDER BY
                wallet_id,
                direction
            """
        ).fetchall()

        for row in rows:
            print(
                "  ",
                row[0],
                "|",
                row[1],
                "|",
                row[2],
            )


def main():
    if not SILVER_DB_PATH.exists():
        raise FileNotFoundError(
            "Silver database not found: "
            f"{SILVER_DB_PATH}"
        )

    config, enabled_assets = (
        load_price_config()
    )

    connection = duckdb.connect(
        str(
            SILVER_DB_PATH
        ),
        read_only=True,
    )

    try:
        connection.execute(
            """
            SET TimeZone = 'UTC'
            """
        )

        check_table_counts(
            connection
        )

        check_wallet_count(
            connection
        )

        check_other_directions(
            connection
        )

        check_duplicate_activity_ids(
            connection
        )

        check_erc20_event_identity(
            connection
        )

        check_known_weth_regression(
            connection
        )

        check_create2_regression(
            connection
        )

        check_token_price_quality(
            connection
        )

        check_token_price_metadata(
            connection,
            config,
            enabled_assets,
        )

        check_token_price_coverage(
            connection,
            enabled_assets,
        )

        print_direction_summary(
            connection
        )

        print()
        print("=" * 100)
        print(
            "SILVER VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()