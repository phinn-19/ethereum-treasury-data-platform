from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


def check_source_assumptions(
    connection,
):
    """
    Guardrails before building Gold.

    V1 assumptions:
    1. A successful positive-value internal movement must not repeat
       with the same signature inside the same monitored wallet view.
    2. Successful positive-value normal and internal movements must
       not have an exact cross-source overlap.

    If either assumption stops being true, fail instead of silently
    deduplicating potentially real ETH movements.
    """

    same_wallet_repeat_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    organization_id,
                    wallet_id,
                    chain_id,
                    transaction_hash,
                    from_address,
                    to_address,
                    contract_address,
                    value_wei_raw,
                    call_type

                FROM
                    silver.internal_transactions

                WHERE
                    value_eth_decimal > 0

                    AND

                    is_error IS NOT TRUE

                GROUP BY
                    organization_id,
                    wallet_id,
                    chain_id,
                    transaction_hash,
                    from_address,
                    to_address,
                    contract_address,
                    value_wei_raw,
                    call_type

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    cross_source_overlap = (
        connection.execute(
            """
            WITH normal AS (
                SELECT DISTINCT
                    chain_id,
                    transaction_hash,
                    from_address,

                    COALESCE(
                        to_address,
                        contract_address
                    ) AS effective_to_address,

                    value_wei_raw

                FROM
                    silver.transactions

                WHERE
                    value_eth_decimal > 0

                    AND

                    receipt_status = 1

                    AND

                    is_error IS NOT TRUE
            ),

            internal AS (
                SELECT DISTINCT
                    chain_id,
                    transaction_hash,
                    from_address,

                    COALESCE(
                        to_address,
                        contract_address
                    ) AS effective_to_address,

                    value_wei_raw

                FROM
                    silver.internal_transactions

                WHERE
                    value_eth_decimal > 0

                    AND

                    is_error IS NOT TRUE
            )

            SELECT COUNT(*)

            FROM normal AS n

            JOIN internal AS i
                ON
                    n.chain_id
                        = i.chain_id

                    AND

                    n.transaction_hash
                        = i.transaction_hash

                    AND

                    n.from_address
                        IS NOT DISTINCT FROM
                        i.from_address

                    AND

                    n.effective_to_address
                        IS NOT DISTINCT FROM
                        i.effective_to_address

                    AND

                    n.value_wei_raw
                        = i.value_wei_raw
            """
        ).fetchone()[0]
    )

    print(
        "Internal same-wallet repeated "
        "signature groups:",
        same_wallet_repeat_groups,
    )

    print(
        "Exact normal/internal "
        "cross-source overlaps:",
        cross_source_overlap,
    )

    if same_wallet_repeat_groups != 0:
        raise RuntimeError(
            "Ambiguous internal ETH data: "
            "the same movement signature "
            "appears more than once inside "
            "the same monitored wallet view. "
            "V1 cannot safely identify those "
            "movements without a stronger "
            "source-native trace identifier."
        )

    if cross_source_overlap != 0:
        raise RuntimeError(
            "Ambiguous native ETH data: "
            "exact positive-value movement "
            "overlap exists between normal "
            "and internal sources. "
            "Investigate before building Gold."
        )


def build_wallet_movements(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_native_eth_movements
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallet_native_eth_movements
        AS

        WITH normal_movements AS (
            SELECT
                'native_'
                    || MD5(
                        CAST(chain_id AS VARCHAR)
                        || '|NORMAL|'
                        || transaction_hash
                    )
                    AS native_event_id,

                CAST(
                    1
                    AS BIGINT
                ) AS occurrence_index,

                'NORMAL'
                    AS source_type,

                activity_id
                    AS source_activity_id,

                chain_id,

                organization_id,

                wallet_id,

                treasury_address,

                transaction_hash,

                CAST(
                    NULL
                    AS VARCHAR
                ) AS trace_id,

                block_number,

                block_timestamp,

                from_address,

                to_address,

                contract_address,

                COALESCE(
                    to_address,
                    contract_address
                ) AS effective_to_address,

                CAST(
                    NULL
                    AS VARCHAR
                ) AS call_type,

                direction,

                value_wei_raw,

                value_eth_exact,

                value_eth_decimal,

                is_error,

                receipt_status,

                ingested_at,

                source_file

            FROM
                silver.transactions

            WHERE
                value_eth_decimal > 0

                AND

                receipt_status = 1

                AND

                is_error IS NOT TRUE
        ),

        ranked_internal AS (
            SELECT
                i.*,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        organization_id,
                        wallet_id,
                        chain_id,
                        transaction_hash,
                        from_address,
                        to_address,
                        contract_address,
                        value_wei_raw,
                        call_type

                    ORDER BY
                        activity_id
                ) AS occurrence_index

            FROM
                silver.internal_transactions
                AS i

            WHERE
                value_eth_decimal > 0

                AND

                is_error IS NOT TRUE
        ),

        internal_movements AS (
            SELECT
                'native_'
                    || MD5(
                        CAST(chain_id AS VARCHAR)
                        || '|INTERNAL|'
                        || transaction_hash
                        || '|'
                        || COALESCE(
                            from_address,
                            ''
                        )
                        || '|'
                        || COALESCE(
                            to_address,
                            ''
                        )
                        || '|'
                        || COALESCE(
                            contract_address,
                            ''
                        )
                        || '|'
                        || value_wei_raw
                        || '|'
                        || COALESCE(
                            call_type,
                            ''
                        )
                        || '|'
                        || CAST(
                            occurrence_index
                            AS VARCHAR
                        )
                    )
                    AS native_event_id,

                occurrence_index,

                'INTERNAL'
                    AS source_type,

                activity_id
                    AS source_activity_id,

                chain_id,

                organization_id,

                wallet_id,

                treasury_address,

                transaction_hash,

                trace_id,

                block_number,

                block_timestamp,

                from_address,

                to_address,

                contract_address,

                COALESCE(
                    to_address,
                    contract_address
                ) AS effective_to_address,

                call_type,

                direction,

                value_wei_raw,

                value_eth_exact,

                value_eth_decimal,

                is_error,

                CAST(
                    NULL
                    AS INTEGER
                ) AS receipt_status,

                ingested_at,

                source_file

            FROM
                ranked_internal
        )

        SELECT *
        FROM normal_movements

        UNION ALL

        SELECT *
        FROM internal_movements
        """
    )


def build_organization_movements(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_native_eth_movements
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_native_eth_movements
        AS

        WITH canonical_events AS (
            SELECT
                native_event_id,

                chain_id,

                organization_id,

                source_type,

                transaction_hash,

                trace_id,

                block_number,

                block_timestamp,

                from_address,

                to_address,

                contract_address,

                effective_to_address,

                call_type,

                value_wei_raw,

                value_eth_exact,

                value_eth_decimal,

                occurrence_index,

                COUNT(*)
                    AS wallet_view_count,

                COUNT(
                    DISTINCT wallet_id
                ) AS monitored_wallet_count

            FROM
                gold.wallet_native_eth_movements

            GROUP BY
                native_event_id,
                chain_id,
                organization_id,
                source_type,
                transaction_hash,
                trace_id,
                block_number,
                block_timestamp,
                from_address,
                to_address,
                contract_address,
                effective_to_address,
                call_type,
                value_wei_raw,
                value_eth_exact,
                value_eth_decimal,
                occurrence_index
        ),

        classified AS (
            SELECT
                e.*,

                from_wallet.wallet_id
                    AS from_wallet_id,

                to_wallet.wallet_id
                    AS to_wallet_id,

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
                    AS organization_direction

            FROM
                canonical_events
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
        )

        SELECT
            native_event_id,

            chain_id,

            organization_id,

            source_type,

            transaction_hash,

            trace_id,

            block_number,

            block_timestamp,

            from_address,

            to_address,

            contract_address,

            effective_to_address,

            call_type,

            value_wei_raw,

            value_eth_exact,

            value_eth_decimal,

            occurrence_index,

            wallet_view_count,

            monitored_wallet_count,

            from_wallet_id,

            to_wallet_id,

            organization_direction,

            CASE
                WHEN
                    organization_direction = 'IN'

                THEN
                    from_address

                WHEN
                    organization_direction = 'OUT'

                THEN
                    effective_to_address

                ELSE
                    NULL
            END
                AS counterparty_address,

            organization_direction
                = 'INTERNAL'
                AS is_internal_transfer

        FROM
            classified
        """
    )


def build_wallet_daily_flows(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_daily_native_eth_flows
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallet_daily_native_eth_flows
        AS

        SELECT
            CAST(
                block_timestamp
                AS DATE
            ) AS activity_date,

            chain_id,

            organization_id,

            wallet_id,

            SUM(
                CASE
                    WHEN direction = 'IN'
                    THEN value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS inflow_eth,

            SUM(
                CASE
                    WHEN direction = 'OUT'
                    THEN value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS outflow_eth,

            SUM(
                CASE
                    WHEN direction = 'SELF'
                    THEN value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS self_transfer_eth,

            SUM(
                CASE
                    WHEN direction = 'CREATE'
                    THEN value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS create_eth,

            SUM(
                CASE
                    WHEN direction = 'IN'
                    THEN value_eth_decimal

                    WHEN direction = 'OUT'
                    THEN -value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS net_flow_eth,

            COUNT(*)
                AS event_count,

            COUNT(
                CASE
                    WHEN direction = 'IN'
                    THEN 1
                END
            ) AS in_event_count,

            COUNT(
                CASE
                    WHEN direction = 'OUT'
                    THEN 1
                END
            ) AS out_event_count,

            COUNT(
                CASE
                    WHEN direction = 'SELF'
                    THEN 1
                END
            ) AS self_event_count,

            COUNT(
                CASE
                    WHEN direction = 'CREATE'
                    THEN 1
                END
            ) AS create_event_count,

            COUNT(
                CASE
                    WHEN direction NOT IN (
                        'IN',
                        'OUT',
                        'SELF',
                        'CREATE'
                    )
                    THEN 1
                END
            ) AS other_event_count,

            COUNT(
                CASE
                    WHEN source_type = 'NORMAL'
                    THEN 1
                END
            ) AS normal_event_count,

            COUNT(
                CASE
                    WHEN source_type = 'INTERNAL'
                    THEN 1
                END
            ) AS internal_event_count

        FROM
            gold.wallet_native_eth_movements

        GROUP BY
            activity_date,
            chain_id,
            organization_id,
            wallet_id
        """
    )


def build_organization_daily_flows(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_daily_native_eth_flows
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_daily_native_eth_flows
        AS

        SELECT
            CAST(
                block_timestamp
                AS DATE
            ) AS activity_date,

            chain_id,

            organization_id,

            SUM(
                CASE
                    WHEN
                        organization_direction = 'IN'

                    THEN
                        value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS inflow_eth,

            SUM(
                CASE
                    WHEN
                        organization_direction = 'OUT'

                    THEN
                        value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS outflow_eth,

            SUM(
                CASE
                    WHEN
                        organization_direction = 'INTERNAL'

                    THEN
                        value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS internal_eth,

            SUM(
                CASE
                    WHEN
                        organization_direction = 'OTHER'

                    THEN
                        value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS other_eth,

            SUM(
                CASE
                    WHEN
                        organization_direction = 'IN'

                    THEN
                        value_eth_decimal

                    WHEN
                        organization_direction = 'OUT'

                    THEN
                        -value_eth_decimal

                    ELSE
                        CAST(
                            0
                            AS DECIMAL(38,18)
                        )
                END
            ) AS net_flow_eth,

            COUNT(*)
                AS event_count,

            COUNT(
                CASE
                    WHEN
                        organization_direction = 'IN'

                    THEN 1
                END
            ) AS in_event_count,

            COUNT(
                CASE
                    WHEN
                        organization_direction = 'OUT'

                    THEN 1
                END
            ) AS out_event_count,

            COUNT(
                CASE
                    WHEN
                        organization_direction = 'INTERNAL'

                    THEN 1
                END
            ) AS internal_event_count,

            COUNT(
                CASE
                    WHEN
                        organization_direction = 'OTHER'

                    THEN 1
                END
            ) AS other_event_count,

            COUNT(
                CASE
                    WHEN source_type = 'NORMAL'
                    THEN 1
                END
            ) AS normal_source_event_count,

            COUNT(
                CASE
                    WHEN source_type = 'INTERNAL'
                    THEN 1
                END
            ) AS internal_source_event_count

        FROM
            gold.organization_native_eth_movements

        GROUP BY
            activity_date,
            chain_id,
            organization_id
        """
    )


def print_summary(
    connection,
):
    print()
    print("=" * 100)
    print("GOLD NATIVE ETH BUILD")
    print("=" * 100)

    table_names = [
        "wallet_native_eth_movements",
        "organization_native_eth_movements",
        "wallet_daily_native_eth_flows",
        "organization_daily_native_eth_flows",
    ]

    for table_name in table_names:
        row_count = (
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM gold.{table_name}
                """
            ).fetchone()[0]
        )

        print(
            f"{table_name}:",
            row_count,
        )

    print()
    print(
        "Wallet movement source summary:"
    )

    rows = connection.execute(
        """
        SELECT
            source_type,
            direction,
            COUNT(*) AS event_count,
            SUM(value_eth_decimal)
                AS total_eth

        FROM
            gold.wallet_native_eth_movements

        GROUP BY
            source_type,
            direction

        ORDER BY
            source_type,
            direction
        """
    ).fetchall()

    for row in rows:
        print(
            "  ",
            row[0],
            "|",
            row[1],
            "| events:",
            row[2],
            "| ETH:",
            row[3],
        )

    print()
    print(
        "Organization direction summary:"
    )

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
            "  ",
            row[0],
            "| events:",
            row[1],
            "| ETH:",
            row[2],
        )

    print()
    print(
        "Cross-wallet native events:"
    )

    row = connection.execute(
        """
        SELECT
            COUNT(*) AS event_count,
            SUM(value_eth_decimal)
                AS total_eth

        FROM
            gold.organization_native_eth_movements

        WHERE
            organization_direction
                = 'INTERNAL'
        """
    ).fetchone()

    print(
        "  events:",
        row[0],
        "| ETH:",
        row[1],
    )


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "DuckDB database not found: "
            f"{DATABASE_PATH}"
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

        print()
        print("=" * 100)
        print(
            "NATIVE ETH SOURCE GUARDRAILS"
        )
        print("=" * 100)

        check_source_assumptions(
            connection
        )

        connection.execute(
            "BEGIN TRANSACTION"
        )

        build_wallet_movements(
            connection
        )

        build_organization_movements(
            connection
        )

        build_wallet_daily_flows(
            connection
        )

        build_organization_daily_flows(
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

    finally:
        connection.close()


if __name__ == "__main__":
    main()