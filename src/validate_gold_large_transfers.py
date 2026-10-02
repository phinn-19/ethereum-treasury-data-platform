import json
from decimal import Decimal
from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)

CONFIG_PATH = Path(
    "config",
    "monitoring.json",
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


def load_threshold():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "Monitoring config not found: "
            f"{CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    rule = config.get(
        "large_transfer_monitoring"
    )

    if not isinstance(
        rule,
        dict,
    ):
        fail(
            "Missing large_transfer_monitoring "
            "configuration"
        )

    if not rule.get(
        "enabled",
        False,
    ):
        fail(
            "Large transfer monitoring "
            "is disabled"
        )

    try:
        threshold_usd = Decimal(
            str(
                rule[
                    "threshold_usd"
                ]
            )
        )

    except Exception as error:
        raise RuntimeError(
            "Invalid threshold_usd"
        ) from error

    if threshold_usd <= 0:
        fail(
            "threshold_usd must be "
            "greater than zero"
        )

    return threshold_usd


def check_table_exists(
    connection,
):
    section(
        "LARGE TRANSFER TABLE CHECK"
    )

    exists = connection.execute(
        """
        SELECT COUNT(*)

        FROM information_schema.tables

        WHERE
            table_schema = 'gold'

            AND

            table_name
                = 'organization_large_erc20_transfers'
        """
    ).fetchone()[0]

    print(
        "Table exists:",
        exists == 1,
    )

    if exists != 1:
        fail(
            "Missing Gold large transfer table"
        )

    row_count = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.organization_large_erc20_transfers
        """
    ).fetchone()[0]

    print(
        "Large transfer rows:",
        row_count,
    )

    if row_count == 0:
        fail(
            "Large transfer table is empty"
        )


def check_grain(
    connection,
):
    section(
        "LARGE TRANSFER GRAIN CHECK"
    )

    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    blockchain_event_id

                FROM
                    gold.organization_large_erc20_transfers

                GROUP BY
                    blockchain_event_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    null_event_ids = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                blockchain_event_id IS NULL
            """
        ).fetchone()[0]
    )

    print(
        "Duplicate blockchain_event_id groups:",
        duplicate_groups,
    )

    print(
        "NULL blockchain_event_id rows:",
        null_event_ids,
    )

    if duplicate_groups != 0:
        fail(
            "Large transfer table contains "
            "duplicate blockchain events"
        )

    if null_event_ids != 0:
        fail(
            "Large transfer rows contain "
            "NULL blockchain_event_id"
        )


def check_threshold(
    connection,
    threshold_usd,
):
    section(
        "LARGE TRANSFER THRESHOLD CHECK"
    )

    below_threshold = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                value_usd < CAST(
                    ?
                    AS DECIMAL(38,8)
                )
            """,
            [
                threshold_usd,
            ],
        ).fetchone()[0]
    )

    threshold_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                threshold_usd
                    IS DISTINCT FROM
                    CAST(
                        ?
                        AS DECIMAL(38,8)
                    )
            """,
            [
                threshold_usd,
            ],
        ).fetchone()[0]
    )

    invalid_flags = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                large_transfer_flag
                    IS DISTINCT FROM TRUE
            """
        ).fetchone()[0]
    )

    print(
        "Configured threshold USD:",
        threshold_usd,
    )

    print(
        "Rows below threshold:",
        below_threshold,
    )

    print(
        "Stored threshold mismatches:",
        threshold_mismatches,
    )

    print(
        "Invalid large_transfer_flag rows:",
        invalid_flags,
    )

    if below_threshold != 0:
        fail(
            "Large transfer table contains "
            "rows below configured threshold"
        )

    if threshold_mismatches != 0:
        fail(
            "Stored threshold does not match "
            "monitoring config"
        )

    if invalid_flags != 0:
        fail(
            "Some large transfer rows are "
            "not flagged TRUE"
        )


def check_source_reconciliation(
    connection,
    threshold_usd,
):
    section(
        "LARGE TRANSFER SOURCE RECONCILIATION"
    )

    expected_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT DISTINCT
                    blockchain_event_id

                FROM
                    gold.wallet_erc20_transfer_valuations

                WHERE
                    valuation_status = 'VALUED'

                    AND

                    value_usd >= CAST(
                        ?
                        AS DECIMAL(38,8)
                    )
            )
            """,
            [
                threshold_usd,
            ],
        ).fetchone()[0]
    )

    actual_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers
            """
        ).fetchone()[0]
    )

    missing_events = (
        connection.execute(
            """
            WITH expected AS (
                SELECT DISTINCT
                    blockchain_event_id

                FROM
                    gold.wallet_erc20_transfer_valuations

                WHERE
                    valuation_status = 'VALUED'

                    AND

                    value_usd >= CAST(
                        ?
                        AS DECIMAL(38,8)
                    )
            )

            SELECT COUNT(*)

            FROM expected AS e

            LEFT JOIN
                gold.organization_large_erc20_transfers
                AS g

                ON
                    e.blockchain_event_id
                        = g.blockchain_event_id

            WHERE
                g.blockchain_event_id
                    IS NULL
            """,
            [
                threshold_usd,
            ],
        ).fetchone()[0]
    )

    unexpected_events = (
        connection.execute(
            """
            WITH expected AS (
                SELECT DISTINCT
                    blockchain_event_id

                FROM
                    gold.wallet_erc20_transfer_valuations

                WHERE
                    valuation_status = 'VALUED'

                    AND

                    value_usd >= CAST(
                        ?
                        AS DECIMAL(38,8)
                    )
            )

            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers
                AS g

            LEFT JOIN
                expected AS e

                ON
                    g.blockchain_event_id
                        = e.blockchain_event_id

            WHERE
                e.blockchain_event_id
                    IS NULL
            """,
            [
                threshold_usd,
            ],
        ).fetchone()[0]
    )

    print(
        "Expected distinct large events:",
        expected_count,
    )

    print(
        "Actual Gold large events:",
        actual_count,
    )

    print(
        "Missing events:",
        missing_events,
    )

    print(
        "Unexpected events:",
        unexpected_events,
    )

    if expected_count != actual_count:
        fail(
            "Large transfer row count "
            "does not match expected events"
        )

    if missing_events != 0:
        fail(
            "Expected large blockchain events "
            "are missing"
        )

    if unexpected_events != 0:
        fail(
            "Unexpected blockchain events "
            "exist in large transfer table"
        )


def check_event_values(
    connection,
):
    section(
        "LARGE TRANSFER VALUE RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH source_events AS (
                SELECT DISTINCT
                    blockchain_event_id,

                    chain_id,

                    organization_id,

                    valuation_date
                        AS event_date,

                    block_timestamp
                        AS event_timestamp,

                    transaction_hash,

                    log_index,

                    token_contract,

                    token_name,

                    token_symbol,

                    token_decimals,

                    from_address,

                    to_address,

                    amount_decimal,

                    daily_price_usd,

                    value_usd,

                    price_provider,

                    price_confidence

                FROM
                    gold.wallet_erc20_transfer_valuations

                WHERE
                    valuation_status = 'VALUED'
            )

            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers
                AS g

            JOIN
                source_events AS s

                ON
                    g.blockchain_event_id
                        = s.blockchain_event_id

            WHERE
                g.chain_id
                    IS DISTINCT FROM
                    s.chain_id

                OR g.organization_id
                    IS DISTINCT FROM
                    s.organization_id

                OR g.event_date
                    IS DISTINCT FROM
                    s.event_date

                OR g.event_timestamp
                    IS DISTINCT FROM
                    s.event_timestamp

                OR g.transaction_hash
                    IS DISTINCT FROM
                    s.transaction_hash

                OR g.log_index
                    IS DISTINCT FROM
                    s.log_index

                OR g.token_contract
                    IS DISTINCT FROM
                    s.token_contract

                OR g.token_name
                    IS DISTINCT FROM
                    s.token_name

                OR g.token_symbol
                    IS DISTINCT FROM
                    s.token_symbol

                OR g.token_decimals
                    IS DISTINCT FROM
                    s.token_decimals

                OR g.from_address
                    IS DISTINCT FROM
                    s.from_address

                OR g.to_address
                    IS DISTINCT FROM
                    s.to_address

                OR g.amount_decimal
                    IS DISTINCT FROM
                    s.amount_decimal

                OR g.daily_price_usd
                    IS DISTINCT FROM
                    s.daily_price_usd

                OR g.value_usd
                    IS DISTINCT FROM
                    s.value_usd

                OR g.price_provider
                    IS DISTINCT FROM
                    s.price_provider

                OR g.price_confidence
                    IS DISTINCT FROM
                    s.price_confidence
            """
        ).fetchone()[0]
    )

    invalid_values = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                amount_decimal IS NULL

                OR daily_price_usd IS NULL

                OR value_usd IS NULL

                OR daily_price_usd <= 0

                OR value_usd < 0
            """
        ).fetchone()[0]
    )

    print(
        "Source value mismatches:",
        mismatch_count,
    )

    print(
        "Invalid amount/price/value rows:",
        invalid_values,
    )

    if mismatch_count != 0:
        fail(
            "Large transfer values do not "
            "match source valuation rows"
        )

    if invalid_values != 0:
        fail(
            "Large transfer table contains "
            "invalid amount or USD values"
        )


def check_direction_classification(
    connection,
):
    section(
        "LARGE TRANSFER DIRECTION CHECK"
    )

    classification_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers
                AS g

            LEFT JOIN
                silver.wallets
                AS from_wallet

                ON
                    g.organization_id
                        = from_wallet.organization_id

                    AND

                    g.from_address
                        = from_wallet.address

                    AND

                    from_wallet.monitoring_enabled
                        = TRUE

            LEFT JOIN
                silver.wallets
                AS to_wallet

                ON
                    g.organization_id
                        = to_wallet.organization_id

                    AND

                    g.to_address
                        = to_wallet.address

                    AND

                    to_wallet.monitoring_enabled
                        = TRUE

            WHERE
                g.organization_direction
                    IS DISTINCT FROM

                    CASE
                        WHEN
                            from_wallet.wallet_id
                                IS NOT NULL

                            AND

                            to_wallet.wallet_id
                                IS NOT NULL

                        THEN
                            'INTERNAL'

                        WHEN
                            from_wallet.wallet_id
                                IS NOT NULL

                            AND

                            to_wallet.wallet_id
                                IS NULL

                        THEN
                            'OUT'

                        WHEN
                            from_wallet.wallet_id
                                IS NULL

                            AND

                            to_wallet.wallet_id
                                IS NOT NULL

                        THEN
                            'IN'

                        ELSE
                            'OTHER'
                    END
            """
        ).fetchone()[0]
    )

    other_events = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                organization_direction = 'OTHER'
            """
        ).fetchone()[0]
    )

    internal_flag_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                is_internal_transfer
                    IS DISTINCT FROM
                    (
                        organization_direction
                            = 'INTERNAL'
                    )
            """
        ).fetchone()[0]
    )

    print(
        "Direction classification mismatches:",
        classification_mismatches,
    )

    print(
        "OTHER events:",
        other_events,
    )

    print(
        "Internal flag mismatches:",
        internal_flag_mismatches,
    )

    if classification_mismatches != 0:
        fail(
            "Large transfer direction "
            "classification is incorrect"
        )

    if other_events != 0:
        fail(
            "Large transfer table contains "
            "OTHER direction events"
        )

    if internal_flag_mismatches != 0:
        fail(
            "is_internal_transfer does not "
            "match organization_direction"
        )


def check_counterparty_logic(
    connection,
):
    section(
        "LARGE TRANSFER COUNTERPARTY CHECK"
    )

    mismatch_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_erc20_transfers

            WHERE
                counterparty_address
                    IS DISTINCT FROM

                    CASE
                        WHEN
                            organization_direction = 'IN'

                        THEN
                            from_address

                        WHEN
                            organization_direction = 'OUT'

                        THEN
                            to_address

                        ELSE
                            NULL
                    END
            """
        ).fetchone()[0]
    )

    print(
        "Counterparty mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Large transfer counterparty "
            "classification is incorrect"
        )


def print_summary(
    connection,
):
    section(
        "LARGE TRANSFER SUMMARY"
    )

    rows = connection.execute(
        """
        SELECT
            organization_direction,

            COUNT(*) AS event_count,

            SUM(value_usd)
                AS total_value_usd

        FROM
            gold.organization_large_erc20_transfers

        GROUP BY
            organization_direction

        ORDER BY
            organization_direction
        """
    ).fetchall()

    total_events = 0

    for row in rows:
        print(
            " ",
            row[0],
            "| events:",
            row[1],
            "| total USD:",
            row[2],
        )

        total_events += row[1]

    print()
    print(
        "Total large events:",
        total_events,
    )


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "DuckDB database not found: "
            f"{DATABASE_PATH}"
        )

    threshold_usd = (
        load_threshold()
    )

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

        check_table_exists(
            connection
        )

        check_grain(
            connection
        )

        check_threshold(
            connection,
            threshold_usd,
        )

        check_source_reconciliation(
            connection,
            threshold_usd,
        )

        check_event_values(
            connection
        )

        check_direction_classification(
            connection
        )

        check_counterparty_logic(
            connection
        )

        print_summary(
            connection
        )

        print()
        print("=" * 100)
        print(
            "GOLD LARGE TRANSFER "
            "VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()