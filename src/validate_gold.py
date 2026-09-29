from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
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


def check_tables(
    connection,
):
    section(
        "GOLD TABLE CHECK"
    )

    required_tables = {
        "wallet_daily_erc20_flows",
        "organization_daily_erc20_flows",
    }

    rows = connection.execute(
        """
        SELECT table_name

        FROM information_schema.tables

        WHERE table_schema = 'gold'
        """
    ).fetchall()

    existing_tables = {
        row[0]
        for row in rows
    }

    for table_name in sorted(
        required_tables
    ):
        if (
            table_name
            not in existing_tables
        ):
            fail(
                f"Missing Gold table: "
                f"{table_name}"
            )

        count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM gold.{table_name}
            """
        ).fetchone()[0]

        print(
            table_name,
            ":",
            count,
        )

        if count == 0:
            fail(
                f"{table_name} is empty"
            )


def check_grain(
    connection,
):
    section(
        "GOLD GRAIN CHECK"
    )

    wallet_duplicates = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    flow_date,
                    wallet_id,
                    token_contract

                FROM
                    gold.wallet_daily_erc20_flows

                GROUP BY
                    flow_date,
                    wallet_id,
                    token_contract

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    organization_duplicates = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    flow_date,
                    organization_id,
                    token_contract

                FROM
                    gold.organization_daily_erc20_flows

                GROUP BY
                    flow_date,
                    organization_id,
                    token_contract

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    print(
        "Wallet duplicate "
        "(date, wallet, token) groups:",
        wallet_duplicates,
    )

    print(
        "Organization duplicate "
        "(date, organization, token) groups:",
        organization_duplicates,
    )

    if wallet_duplicates != 0:
        fail(
            "Wallet Gold grain "
            "contains duplicates"
        )

    if organization_duplicates != 0:
        fail(
            "Organization Gold grain "
            "contains duplicates"
        )


def check_decimal_coverage(
    connection,
):
    section(
        "DECIMAL COVERAGE CHECK"
    )

    silver_wallet_nulls = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.erc20_transfers

            WHERE amount_decimal IS NULL
            """
        ).fetchone()[0]
    )

    silver_event_nulls = (
        connection.execute(
            """
            SELECT COUNT(
                DISTINCT blockchain_event_id
            )

            FROM silver.erc20_transfers

            WHERE amount_decimal IS NULL
            """
        ).fetchone()[0]
    )

    gold_wallet_nulls = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        non_decimal_event_count
                    ),
                    0
                )

            FROM
                gold.wallet_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    gold_org_nulls = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        non_decimal_event_count
                    ),
                    0
                )

            FROM
                gold.organization_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    print(
        "Silver wallet rows "
        "without amount_decimal:",
        silver_wallet_nulls,
    )

    print(
        "Gold wallet "
        "non-decimal events:",
        gold_wallet_nulls,
    )

    print(
        "Silver unique events "
        "without amount_decimal:",
        silver_event_nulls,
    )

    print(
        "Gold organization "
        "non-decimal events:",
        gold_org_nulls,
    )

    if (
        silver_wallet_nulls
        != gold_wallet_nulls
    ):
        fail(
            "Wallet decimal coverage "
            "does not reconcile"
        )

    if (
        silver_event_nulls
        != gold_org_nulls
    ):
        fail(
            "Organization decimal coverage "
            "does not reconcile"
        )

    if silver_wallet_nulls != 0:
        fail(
            "Some ERC20 amounts cannot "
            "be represented as "
            "DECIMAL(38,18)"
        )


def check_wallet_event_counts(
    connection,
):
    section(
        "WALLET EVENT RECONCILIATION"
    )

    silver_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.erc20_transfers
            """
        ).fetchone()[0]
    )

    gold_events = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(total_event_count),
                    0
                )

            FROM
                gold.wallet_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    print(
        "Silver wallet-activity rows:",
        silver_rows,
    )

    print(
        "Gold wallet total events:",
        gold_events,
    )

    if silver_rows != gold_events:
        fail(
            "Wallet Gold event count "
            "does not match Silver"
        )


def check_wallet_measures(
    connection,
):
    section(
        "WALLET AMOUNT RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH expected AS (
                SELECT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS flow_date,

                    wallet_id,
                    token_contract,

                    SUM(
                        CASE
                            WHEN direction = 'IN'
                            THEN amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS inflow_amount,

                    SUM(
                        CASE
                            WHEN direction = 'OUT'
                            THEN amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS outflow_amount,

                    SUM(
                        CASE
                            WHEN direction = 'IN'
                            THEN amount_decimal

                            WHEN direction = 'OUT'
                            THEN -amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS net_flow_amount,

                    COUNT(
                        CASE
                            WHEN direction = 'IN'
                            THEN 1
                        END
                    ) AS inflow_event_count,

                    COUNT(
                        CASE
                            WHEN direction = 'OUT'
                            THEN 1
                        END
                    ) AS outflow_event_count,

                    COUNT(
                        CASE
                            WHEN direction = 'SELF'
                            THEN 1
                        END
                    ) AS self_event_count,

                    COUNT(*) AS total_event_count

                FROM
                    silver.erc20_transfers

                GROUP BY
                    1,
                    2,
                    3
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.wallet_daily_erc20_flows
                AS g

                ON
                    e.flow_date
                        = g.flow_date

                    AND

                    e.wallet_id
                        = g.wallet_id

                    AND

                    e.token_contract
                        = g.token_contract

            WHERE
                e.flow_date IS NULL

                OR g.flow_date IS NULL

                OR e.inflow_amount
                    IS DISTINCT FROM
                    g.inflow_amount

                OR e.outflow_amount
                    IS DISTINCT FROM
                    g.outflow_amount

                OR e.net_flow_amount
                    IS DISTINCT FROM
                    g.net_flow_amount

                OR e.inflow_event_count
                    IS DISTINCT FROM
                    g.inflow_event_count

                OR e.outflow_event_count
                    IS DISTINCT FROM
                    g.outflow_event_count

                OR e.self_event_count
                    IS DISTINCT FROM
                    g.self_event_count

                OR e.total_event_count
                    IS DISTINCT FROM
                    g.total_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Wallet aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Wallet Gold values "
            "do not match Silver"
        )


def check_organization_event_counts(
    connection,
):
    section(
        "ORGANIZATION EVENT RECONCILIATION"
    )

    silver_wallet_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.erc20_transfers
            """
        ).fetchone()[0]
    )

    silver_unique_events = (
        connection.execute(
            """
            SELECT COUNT(
                DISTINCT blockchain_event_id
            )

            FROM silver.erc20_transfers
            """
        ).fetchone()[0]
    )

    gold_events = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(total_event_count),
                    0
                )

            FROM
                gold.organization_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    print(
        "Silver wallet-activity rows:",
        silver_wallet_rows,
    )

    print(
        "Silver unique blockchain events:",
        silver_unique_events,
    )

    print(
        "Extra wallet views:",
        (
            silver_wallet_rows
            - silver_unique_events
        ),
    )

    print(
        "Gold organization total events:",
        gold_events,
    )

    if (
        silver_unique_events
        != gold_events
    ):
        fail(
            "Organization Gold event count "
            "does not match unique "
            "Silver events"
        )


def check_internal_events(
    connection,
):
    section(
        "INTERNAL TRANSFER CHECK"
    )

    result = connection.execute(
        """
        WITH events AS (
            SELECT DISTINCT
                blockchain_event_id,
                organization_id,
                from_address,
                to_address

            FROM
                silver.erc20_transfers
        ),

        classified AS (
            SELECT
                e.blockchain_event_id,

                from_wallet.wallet_id
                    AS from_wallet_id,

                to_wallet.wallet_id
                    AS to_wallet_id

            FROM
                events AS e

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

                    e.to_address
                        = to_wallet.address

                    AND

                    to_wallet.monitoring_enabled
                        = TRUE
        )

        SELECT
            COUNT(
                CASE
                    WHEN
                        from_wallet_id
                            IS NOT NULL

                        AND

                        to_wallet_id
                            IS NOT NULL

                    THEN 1
                END
            ) AS internal_events,

            COUNT(
                CASE
                    WHEN
                        from_wallet_id
                            IS NOT NULL

                        AND

                        to_wallet_id
                            IS NOT NULL

                        AND

                        from_wallet_id
                            != to_wallet_id

                    THEN 1
                END
            ) AS cross_wallet_events,

            COUNT(
                CASE
                    WHEN
                        from_wallet_id
                            IS NOT NULL

                        AND

                        from_wallet_id
                            = to_wallet_id

                    THEN 1
                END
            ) AS self_events

        FROM classified
        """
    ).fetchone()

    expected_internal = (
        result[0]
    )

    cross_wallet = (
        result[1]
    )

    self_events = (
        result[2]
    )

    gold_internal = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        internal_transfer_event_count
                    ),
                    0
                )

            FROM
                gold.organization_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    print(
        "Expected internal events:",
        expected_internal,
    )

    print(
        "Cross-wallet events:",
        cross_wallet,
    )

    print(
        "Self events:",
        self_events,
    )

    print(
        "Gold internal events:",
        gold_internal,
    )

    if (
        expected_internal
        != gold_internal
    ):
        fail(
            "Internal transfer count "
            "does not reconcile"
        )

    if (
        expected_internal
        != cross_wallet
        + self_events
    ):
        fail(
            "Internal event breakdown "
            "is inconsistent"
        )


def check_organization_measures(
    connection,
):
    section(
        "ORGANIZATION AMOUNT RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH blockchain_events AS (
                SELECT DISTINCT
                    blockchain_event_id,
                    organization_id,

                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS flow_date,

                    token_contract,
                    from_address,
                    to_address,
                    amount_decimal

                FROM
                    silver.erc20_transfers
            ),

            classified AS (
                SELECT
                    e.*,

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

                            AND

                            to_wallet.wallet_id
                                IS NULL

                        THEN 'OUT'


                        WHEN
                            from_wallet.wallet_id
                                IS NULL

                            AND

                            to_wallet.wallet_id
                                IS NOT NULL

                        THEN 'IN'


                        ELSE 'OTHER'
                    END
                    AS organization_direction

                FROM
                    blockchain_events
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

                        e.to_address
                            = to_wallet.address

                        AND

                        to_wallet.monitoring_enabled
                            = TRUE
            ),

            expected AS (
                SELECT
                    flow_date,
                    organization_id,
                    token_contract,

                    SUM(
                        CASE
                            WHEN
                                organization_direction
                                    = 'IN'

                            THEN amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS external_inflow_amount,

                    SUM(
                        CASE
                            WHEN
                                organization_direction
                                    = 'OUT'

                            THEN amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS external_outflow_amount,

                    SUM(
                        CASE
                            WHEN
                                organization_direction
                                    = 'IN'

                            THEN amount_decimal

                            WHEN
                                organization_direction
                                    = 'OUT'

                            THEN -amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS net_external_flow_amount,

                    SUM(
                        CASE
                            WHEN
                                organization_direction
                                    = 'INTERNAL'

                            THEN amount_decimal

                            ELSE CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        END
                    ) AS internal_transfer_amount,

                    COUNT(
                        CASE
                            WHEN
                                organization_direction
                                    = 'IN'

                            THEN 1
                        END
                    ) AS external_inflow_event_count,

                    COUNT(
                        CASE
                            WHEN
                                organization_direction
                                    = 'OUT'

                            THEN 1
                        END
                    ) AS external_outflow_event_count,

                    COUNT(
                        CASE
                            WHEN
                                organization_direction
                                    = 'INTERNAL'

                            THEN 1
                        END
                    ) AS internal_transfer_event_count,

                    COUNT(
                        CASE
                            WHEN
                                organization_direction
                                    = 'OTHER'

                            THEN 1
                        END
                    ) AS other_event_count,

                    COUNT(*) AS total_event_count

                FROM classified

                GROUP BY
                    1,
                    2,
                    3
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.organization_daily_erc20_flows
                AS g

                ON
                    e.flow_date
                        = g.flow_date

                    AND

                    e.organization_id
                        = g.organization_id

                    AND

                    e.token_contract
                        = g.token_contract

            WHERE
                e.flow_date IS NULL

                OR g.flow_date IS NULL

                OR e.external_inflow_amount
                    IS DISTINCT FROM
                    g.external_inflow_amount

                OR e.external_outflow_amount
                    IS DISTINCT FROM
                    g.external_outflow_amount

                OR e.net_external_flow_amount
                    IS DISTINCT FROM
                    g.net_external_flow_amount

                OR e.internal_transfer_amount
                    IS DISTINCT FROM
                    g.internal_transfer_amount

                OR e.external_inflow_event_count
                    IS DISTINCT FROM
                    g.external_inflow_event_count

                OR e.external_outflow_event_count
                    IS DISTINCT FROM
                    g.external_outflow_event_count

                OR e.internal_transfer_event_count
                    IS DISTINCT FROM
                    g.internal_transfer_event_count

                OR e.other_event_count
                    IS DISTINCT FROM
                    g.other_event_count

                OR e.total_event_count
                    IS DISTINCT FROM
                    g.total_event_count
            """
        ).fetchone()[0]
    )

    other_events = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(other_event_count),
                    0
                )

            FROM
                gold.organization_daily_erc20_flows
            """
        ).fetchone()[0]
    )

    print(
        "Organization aggregate "
        "mismatches:",
        mismatch_count,
    )

    print(
        "Organization OTHER events:",
        other_events,
    )

    if mismatch_count != 0:
        fail(
            "Organization Gold values "
            "do not match Silver"
        )

    if other_events != 0:
        fail(
            "Organization Gold contains "
            "OTHER events"
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
        ),
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

        check_grain(
            connection
        )

        check_decimal_coverage(
            connection
        )

        check_wallet_event_counts(
            connection
        )

        check_wallet_measures(
            connection
        )

        check_organization_event_counts(
            connection
        )

        check_internal_events(
            connection
        )

        check_organization_measures(
            connection
        )

        print()
        print("=" * 100)
        print(
            "GOLD VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()