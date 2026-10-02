from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


REQUIRED_TABLES = [
    "wallet_native_eth_movements",
    "organization_native_eth_movements",
    "wallet_daily_native_eth_flows",
    "organization_daily_native_eth_flows",
]


def fail(message):
    raise RuntimeError(
        f"VALIDATION FAILED: {message}"
    )


def section(title):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def check_tables(connection):
    section("NATIVE ETH TABLE CHECK")

    for table_name in REQUIRED_TABLES:
        exists = connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE
                table_schema = 'gold'
                AND table_name = ?
            """,
            [table_name],
        ).fetchone()[0]

        if exists != 1:
            fail(
                f"Missing gold.{table_name}"
            )

        count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM gold.{table_name}
            """
        ).fetchone()[0]

        print(
            f"{table_name}:",
            count,
        )


def check_wallet_grain(connection):
    section("WALLET MOVEMENT GRAIN CHECK")

    duplicates = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                wallet_id,
                native_event_id
            FROM
                gold.wallet_native_eth_movements
            GROUP BY
                wallet_id,
                native_event_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    null_event_ids = connection.execute(
        """
        SELECT COUNT(*)
        FROM gold.wallet_native_eth_movements
        WHERE native_event_id IS NULL
        """
    ).fetchone()[0]

    invalid_values = connection.execute(
        """
        SELECT COUNT(*)
        FROM gold.wallet_native_eth_movements
        WHERE
            value_eth_decimal IS NULL
            OR value_eth_decimal <= 0
        """
    ).fetchone()[0]

    invalid_sources = connection.execute(
        """
        SELECT COUNT(*)
        FROM gold.wallet_native_eth_movements
        WHERE source_type NOT IN (
            'NORMAL',
            'INTERNAL'
        )
        """
    ).fetchone()[0]

    print(
        "Duplicate (wallet_id, native_event_id):",
        duplicates,
    )
    print(
        "NULL native_event_id:",
        null_event_ids,
    )
    print(
        "Invalid positive ETH values:",
        invalid_values,
    )
    print(
        "Unexpected source types:",
        invalid_sources,
    )

    if duplicates != 0:
        fail(
            "Wallet native ETH grain is not unique"
        )

    if null_event_ids != 0:
        fail(
            "NULL native_event_id found"
        )

    if invalid_values != 0:
        fail(
            "Invalid native ETH values found"
        )

    if invalid_sources != 0:
        fail(
            "Unexpected native ETH source type"
        )


def check_source_reconciliation(connection):
    section("SOURCE RECONCILIATION")

    result = connection.execute(
        """
        WITH expected AS (
            SELECT
                'NORMAL'
                    AS source_type,

                activity_id
                    AS source_activity_id,

                chain_id,
                organization_id,
                wallet_id,
                transaction_hash,
                from_address,
                to_address,
                contract_address,
                direction,
                value_wei_raw,
                value_eth_decimal

            FROM silver.transactions

            WHERE
                value_eth_decimal > 0
                AND receipt_status = 1
                AND is_error IS NOT TRUE

            UNION ALL

            SELECT
                'INTERNAL'
                    AS source_type,

                activity_id
                    AS source_activity_id,

                chain_id,
                organization_id,
                wallet_id,
                transaction_hash,
                from_address,
                to_address,
                contract_address,
                direction,
                value_wei_raw,
                value_eth_decimal

            FROM silver.internal_transactions

            WHERE
                value_eth_decimal > 0
                AND is_error IS NOT TRUE
        ),

        compared AS (
            SELECT
                e.source_activity_id
                    AS expected_id,

                g.source_activity_id
                    AS actual_id,

                CASE
                    WHEN
                        e.source_type
                            IS DISTINCT FROM
                            g.source_type

                        OR e.chain_id
                            IS DISTINCT FROM
                            g.chain_id

                        OR e.organization_id
                            IS DISTINCT FROM
                            g.organization_id

                        OR e.wallet_id
                            IS DISTINCT FROM
                            g.wallet_id

                        OR e.transaction_hash
                            IS DISTINCT FROM
                            g.transaction_hash

                        OR e.from_address
                            IS DISTINCT FROM
                            g.from_address

                        OR e.to_address
                            IS DISTINCT FROM
                            g.to_address

                        OR e.contract_address
                            IS DISTINCT FROM
                            g.contract_address

                        OR e.direction
                            IS DISTINCT FROM
                            g.direction

                        OR e.value_wei_raw
                            IS DISTINCT FROM
                            g.value_wei_raw

                        OR e.value_eth_decimal
                            IS DISTINCT FROM
                            g.value_eth_decimal

                    THEN 1
                    ELSE 0
                END
                    AS mismatch

            FROM expected AS e

            FULL OUTER JOIN
                gold.wallet_native_eth_movements
                AS g

                ON
                    e.source_type
                        = g.source_type

                    AND

                    e.source_activity_id
                        = g.source_activity_id
        )

        SELECT
            COUNT(*)
                FILTER (
                    WHERE expected_id IS NULL
                ) AS unexpected_rows,

            COUNT(*)
                FILTER (
                    WHERE actual_id IS NULL
                ) AS missing_rows,

            SUM(mismatch)
                AS field_mismatches

        FROM compared
        """
    ).fetchone()

    unexpected_rows = result[0]
    missing_rows = result[1]
    field_mismatches = result[2] or 0

    print(
        "Missing source rows:",
        missing_rows,
    )
    print(
        "Unexpected Gold rows:",
        unexpected_rows,
    )
    print(
        "Field mismatches:",
        field_mismatches,
    )

    if missing_rows != 0:
        fail(
            "Source native ETH rows are missing"
        )

    if unexpected_rows != 0:
        fail(
            "Unexpected native ETH Gold rows exist"
        )

    if field_mismatches != 0:
        fail(
            "Gold native ETH rows differ from source"
        )


def check_organization_grain(
    connection,
):
    section("ORGANIZATION MOVEMENT CHECK")

    duplicate_events = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                native_event_id
            FROM
                gold.organization_native_eth_movements
            GROUP BY
                native_event_id
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    wallet_rows = connection.execute(
        """
        SELECT COUNT(*)
        FROM gold.wallet_native_eth_movements
        """
    ).fetchone()[0]

    distinct_events = connection.execute(
        """
        SELECT COUNT(
            DISTINCT native_event_id
        )
        FROM gold.wallet_native_eth_movements
        """
    ).fetchone()[0]

    organization_rows = connection.execute(
        """
        SELECT COUNT(*)
        FROM
            gold.organization_native_eth_movements
        """
    ).fetchone()[0]

    missing_events = connection.execute(
        """
        SELECT COUNT(*)

        FROM (
            SELECT DISTINCT
                native_event_id
            FROM
                gold.wallet_native_eth_movements
        ) AS w

        LEFT JOIN
            gold.organization_native_eth_movements
            AS o

            ON
                w.native_event_id
                    = o.native_event_id

        WHERE
            o.native_event_id IS NULL
        """
    ).fetchone()[0]

    unexpected_events = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.organization_native_eth_movements
            AS o

        LEFT JOIN (
            SELECT DISTINCT
                native_event_id
            FROM
                gold.wallet_native_eth_movements
        ) AS w

            ON
                o.native_event_id
                    = w.native_event_id

        WHERE
            w.native_event_id IS NULL
        """
    ).fetchone()[0]

    print(
        "Duplicate organization events:",
        duplicate_events,
    )
    print(
        "Wallet views:",
        wallet_rows,
    )
    print(
        "Unique native events:",
        distinct_events,
    )
    print(
        "Extra wallet views:",
        wallet_rows - distinct_events,
    )
    print(
        "Organization rows:",
        organization_rows,
    )
    print(
        "Missing organization events:",
        missing_events,
    )
    print(
        "Unexpected organization events:",
        unexpected_events,
    )

    if duplicate_events != 0:
        fail(
            "Organization native event grain "
            "is not unique"
        )

    if organization_rows != distinct_events:
        fail(
            "Organization row count does not "
            "match unique wallet events"
        )

    if missing_events != 0:
        fail(
            "Native ETH organization events missing"
        )

    if unexpected_events != 0:
        fail(
            "Unexpected organization events exist"
        )


def check_organization_direction(
    connection,
):
    section("ORGANIZATION DIRECTION CHECK")

    mismatches = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.organization_native_eth_movements
            AS e

        LEFT JOIN
            silver.wallets
            AS from_wallet

            ON
                e.organization_id
                    = from_wallet.organization_id

                AND

                e.from_address
                    = from_wallet.address

                AND

                from_wallet.monitoring_enabled
                    = TRUE

        LEFT JOIN
            silver.wallets
            AS to_wallet

            ON
                e.organization_id
                    = to_wallet.organization_id

                AND

                e.effective_to_address
                    = to_wallet.address

                AND

                to_wallet.monitoring_enabled
                    = TRUE

        WHERE
            e.organization_direction
                IS DISTINCT FROM

                CASE
                    WHEN
                        from_wallet.wallet_id
                            IS NOT NULL

                        AND

                        to_wallet.wallet_id
                            IS NOT NULL

                    THEN 'INTERNAL'

                    WHEN
                        from_wallet.wallet_id
                            IS NOT NULL

                    THEN 'OUT'

                    WHEN
                        to_wallet.wallet_id
                            IS NOT NULL

                    THEN 'IN'

                    ELSE 'OTHER'
                END
        """
    ).fetchone()[0]

    other_events = connection.execute(
        """
        SELECT COUNT(*)
        FROM
            gold.organization_native_eth_movements
        WHERE
            organization_direction = 'OTHER'
        """
    ).fetchone()[0]

    counterparty_mismatches = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.organization_native_eth_movements

        WHERE
            counterparty_address
                IS DISTINCT FROM

                CASE
                    WHEN
                        organization_direction = 'IN'

                    THEN from_address

                    WHEN
                        organization_direction = 'OUT'

                    THEN effective_to_address

                    ELSE NULL
                END
        """
    ).fetchone()[0]

    internal_flag_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_movements

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
        "Direction mismatches:",
        mismatches,
    )
    print(
        "OTHER events:",
        other_events,
    )
    print(
        "Counterparty mismatches:",
        counterparty_mismatches,
    )
    print(
        "Internal flag mismatches:",
        internal_flag_mismatches,
    )

    if mismatches != 0:
        fail(
            "Organization direction is incorrect"
        )

    if other_events != 0:
        fail(
            "Unexpected OTHER native ETH events"
        )

    if counterparty_mismatches != 0:
        fail(
            "Native ETH counterparty logic incorrect"
        )

    if internal_flag_mismatches != 0:
        fail(
            "Internal transfer flag incorrect"
        )


def check_flow_reconciliation(
    connection,
):
    section("ETH FLOW RECONCILIATION")

    wallet = connection.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN direction = 'IN'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ),

            SUM(
                CASE
                    WHEN direction = 'OUT'
                    THEN value_eth_decimal
                    ELSE 0
                END
            )

        FROM
            gold.wallet_native_eth_movements
        """
    ).fetchone()

    organization = connection.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN organization_direction = 'IN'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ),

            SUM(
                CASE
                    WHEN organization_direction = 'OUT'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ),

            SUM(
                CASE
                    WHEN organization_direction = 'INTERNAL'
                    THEN value_eth_decimal
                    ELSE 0
                END
            )

        FROM
            gold.organization_native_eth_movements
        """
    ).fetchone()

    wallet_in = wallet[0]
    wallet_out = wallet[1]

    org_in = organization[0]
    org_out = organization[1]
    org_internal = organization[2]

    expected_wallet_in = (
        org_in
        + org_internal
    )

    expected_wallet_out = (
        org_out
        + org_internal
    )

    print(
        "Wallet IN:",
        wallet_in,
    )
    print(
        "Organization external IN:",
        org_in,
    )
    print(
        "Organization INTERNAL:",
        org_internal,
    )
    print(
        "Expected wallet IN:",
        expected_wallet_in,
    )

    print()

    print(
        "Wallet OUT:",
        wallet_out,
    )
    print(
        "Organization external OUT:",
        org_out,
    )
    print(
        "Expected wallet OUT:",
        expected_wallet_out,
    )

    if wallet_in != expected_wallet_in:
        fail(
            "Wallet IN does not reconcile with "
            "organization IN + INTERNAL"
        )

    if wallet_out != expected_wallet_out:
        fail(
            "Wallet OUT does not reconcile with "
            "organization OUT + INTERNAL"
        )


def check_wallet_daily(
    connection,
):
    section("WALLET DAILY AGGREGATE CHECK")

    mismatches = connection.execute(
        """
        WITH expected AS (
            SELECT
                CAST(
                    block_timestamp AS DATE
                ) AS activity_date,

                chain_id,
                organization_id,
                wallet_id,

                SUM(
                    CASE
                        WHEN direction = 'IN'
                        THEN value_eth_decimal
                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS inflow_eth,

                SUM(
                    CASE
                        WHEN direction = 'OUT'
                        THEN value_eth_decimal
                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS outflow_eth,

                SUM(
                    CASE
                        WHEN direction = 'IN'
                        THEN value_eth_decimal

                        WHEN direction = 'OUT'
                        THEN -value_eth_decimal

                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS net_flow_eth,

                COUNT(*)
                    AS event_count

            FROM
                gold.wallet_native_eth_movements

            GROUP BY
                activity_date,
                chain_id,
                organization_id,
                wallet_id
        )

        SELECT COUNT(*)

        FROM expected AS e

        FULL OUTER JOIN
            gold.wallet_daily_native_eth_flows
            AS g

            USING (
                activity_date,
                chain_id,
                organization_id,
                wallet_id
            )

        WHERE
            e.activity_date IS NULL

            OR g.activity_date IS NULL

            OR e.inflow_eth
                IS DISTINCT FROM
                g.inflow_eth

            OR e.outflow_eth
                IS DISTINCT FROM
                g.outflow_eth

            OR e.net_flow_eth
                IS DISTINCT FROM
                g.net_flow_eth

            OR e.event_count
                IS DISTINCT FROM
                g.event_count
        """
    ).fetchone()[0]

    print(
        "Wallet daily mismatches:",
        mismatches,
    )

    if mismatches != 0:
        fail(
            "Wallet daily native ETH "
            "aggregates do not reconcile"
        )


def check_organization_daily(
    connection,
):
    section("ORGANIZATION DAILY AGGREGATE CHECK")

    mismatches = connection.execute(
        """
        WITH expected AS (
            SELECT
                CAST(
                    block_timestamp AS DATE
                ) AS activity_date,

                chain_id,
                organization_id,

                SUM(
                    CASE
                        WHEN organization_direction = 'IN'
                        THEN value_eth_decimal
                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS inflow_eth,

                SUM(
                    CASE
                        WHEN organization_direction = 'OUT'
                        THEN value_eth_decimal
                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS outflow_eth,

                SUM(
                    CASE
                        WHEN organization_direction = 'INTERNAL'
                        THEN value_eth_decimal
                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS internal_eth,

                SUM(
                    CASE
                        WHEN organization_direction = 'IN'
                        THEN value_eth_decimal

                        WHEN organization_direction = 'OUT'
                        THEN -value_eth_decimal

                        ELSE CAST(
                            0 AS DECIMAL(38,18)
                        )
                    END
                ) AS net_flow_eth,

                COUNT(*)
                    AS event_count

            FROM
                gold.organization_native_eth_movements

            GROUP BY
                activity_date,
                chain_id,
                organization_id
        )

        SELECT COUNT(*)

        FROM expected AS e

        FULL OUTER JOIN
            gold.organization_daily_native_eth_flows
            AS g

            USING (
                activity_date,
                chain_id,
                organization_id
            )

        WHERE
            e.activity_date IS NULL

            OR g.activity_date IS NULL

            OR e.inflow_eth
                IS DISTINCT FROM
                g.inflow_eth

            OR e.outflow_eth
                IS DISTINCT FROM
                g.outflow_eth

            OR e.internal_eth
                IS DISTINCT FROM
                g.internal_eth

            OR e.net_flow_eth
                IS DISTINCT FROM
                g.net_flow_eth

            OR e.event_count
                IS DISTINCT FROM
                g.event_count
        """
    ).fetchone()[0]

    print(
        "Organization daily mismatches:",
        mismatches,
    )

    if mismatches != 0:
        fail(
            "Organization daily native ETH "
            "aggregates do not reconcile"
        )


def print_summary(connection):
    section("NATIVE ETH SUMMARY")

    rows = connection.execute(
        """
        SELECT
            organization_direction,
            COUNT(*) AS event_count,
            SUM(value_eth_decimal)
                AS total_eth

        FROM
            gold.organization_native_eth_movements

        GROUP BY
            organization_direction

        ORDER BY
            organization_direction
        """
    ).fetchall()

    for row in rows:
        print(
            " ",
            row[0],
            "| events:",
            row[1],
            "| ETH:",
            row[2],
        )


def main():
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

        check_tables(
            connection
        )

        check_wallet_grain(
            connection
        )

        check_source_reconciliation(
            connection
        )

        check_organization_grain(
            connection
        )

        check_organization_direction(
            connection
        )

        check_flow_reconciliation(
            connection
        )

        check_wallet_daily(
            connection
        )

        check_organization_daily(
            connection
        )

        print_summary(
            connection
        )

        print()
        print("=" * 100)
        print(
            "GOLD NATIVE ETH VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()