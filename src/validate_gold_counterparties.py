from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


ZERO_ADDRESS = (
    "0x0000000000000000000000000000000000000000"
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


def check_table(
    connection,
):
    section(
        "COUNTERPARTY GOLD TABLE CHECK"
    )

    row_count = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.wallet_daily_erc20_counterparty_flows
        """
    ).fetchone()[0]

    print(
        "Gold rows:",
        row_count,
    )

    if row_count == 0:
        fail(
            "Counterparty Gold table is empty"
        )


def check_grain(
    connection,
):
    section(
        "COUNTERPARTY GRAIN CHECK"
    )

    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    activity_date,
                    wallet_id,
                    counterparty_address,
                    token_contract

                FROM
                    gold.wallet_daily_erc20_counterparty_flows

                GROUP BY
                    activity_date,
                    wallet_id,
                    counterparty_address,
                    token_contract

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    null_counterparties = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows

            WHERE
                counterparty_address IS NULL
            """
        ).fetchone()[0]
    )

    print(
        "Duplicate grain groups:",
        duplicate_groups,
    )

    print(
        "NULL counterparties:",
        null_counterparties,
    )

    if duplicate_groups != 0:
        fail(
            "Counterparty Gold contains "
            "duplicate grain"
        )

    if null_counterparties != 0:
        fail(
            "Counterparty Gold contains "
            "NULL counterparties"
        )


def check_event_counts(
    connection,
):
    section(
        "EVENT RECONCILIATION"
    )

    silver_total = connection.execute(
        """
        SELECT COUNT(*)

        FROM silver.erc20_transfers
        """
    ).fetchone()[0]

    gold_total = connection.execute(
        """
        SELECT
            COALESCE(
                SUM(total_event_count),
                0
            )

        FROM
            gold.wallet_daily_erc20_counterparty_flows
        """
    ).fetchone()[0]

    silver_counts = connection.execute(
        """
        SELECT
            COUNT(
                CASE
                    WHEN direction = 'IN'
                    THEN 1
                END
            ),

            COUNT(
                CASE
                    WHEN direction = 'OUT'
                    THEN 1
                END
            ),

            COUNT(
                CASE
                    WHEN direction = 'SELF'
                    THEN 1
                END
            )

        FROM silver.erc20_transfers
        """
    ).fetchone()

    gold_counts = connection.execute(
        """
        SELECT
            COALESCE(
                SUM(inflow_event_count),
                0
            ),

            COALESCE(
                SUM(outflow_event_count),
                0
            ),

            COALESCE(
                SUM(self_event_count),
                0
            )

        FROM
            gold.wallet_daily_erc20_counterparty_flows
        """
    ).fetchone()

    print(
        "Silver events:",
        silver_total,
    )

    print(
        "Gold events:",
        gold_total,
    )

    print(
        "Silver IN / OUT / SELF:",
        silver_counts,
    )

    print(
        "Gold IN / OUT / SELF:",
        gold_counts,
    )

    if silver_total != gold_total:
        fail(
            "Gold event count does not "
            "match Silver"
        )

    if silver_counts != gold_counts:
        fail(
            "Gold direction counts do not "
            "match Silver"
        )


def check_counterparty_types(
    connection,
):
    section(
        "COUNTERPARTY TYPE CHECK"
    )

    rows = connection.execute(
        """
        SELECT
            counterparty_type,
            SUM(total_event_count)

        FROM
            gold.wallet_daily_erc20_counterparty_flows

        GROUP BY
            counterparty_type

        ORDER BY
            counterparty_type
        """
    ).fetchall()

    allowed_types = {
        "SELF",
        "ZERO_ADDRESS",
        "MONITORED_WALLET",
        "EXTERNAL_ADDRESS",
    }

    found_types = set()

    for row in rows:
        found_types.add(
            row[0]
        )

        print(
            row[0],
            ":",
            row[1],
        )

    unexpected = (
        found_types
        - allowed_types
    )

    if unexpected:
        fail(
            "Unexpected counterparty types: "
            f"{sorted(unexpected)}"
        )


def check_classification(
    connection,
):
    section(
        "CLASSIFICATION CHECK"
    )

    self_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows

            WHERE
                counterparty_type = 'SELF'

                AND

                counterparty_address
                    != treasury_address
            """
        ).fetchone()[0]
    )

    zero_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows

            WHERE
                counterparty_type = 'ZERO_ADDRESS'

                AND

                counterparty_address != ?
            """,
            [
                ZERO_ADDRESS
            ],
        ).fetchone()[0]
    )

    monitored_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows
                AS g

            LEFT JOIN
                silver.wallets AS w

                ON
                    g.counterparty_address
                        = w.address

                    AND

                    w.monitoring_enabled
                        = TRUE

            WHERE
                g.counterparty_type
                    = 'MONITORED_WALLET'

                AND

                w.wallet_id IS NULL
            """
        ).fetchone()[0]
    )

    external_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows
                AS g

            LEFT JOIN
                silver.wallets AS w

                ON
                    g.counterparty_address
                        = w.address

                    AND

                    w.monitoring_enabled
                        = TRUE

            WHERE
                g.counterparty_type
                    = 'EXTERNAL_ADDRESS'

                AND

                w.wallet_id IS NOT NULL
            """
        ).fetchone()[0]
    )

    print(
        "SELF mismatches:",
        self_mismatches,
    )

    print(
        "ZERO_ADDRESS mismatches:",
        zero_mismatches,
    )

    print(
        "MONITORED_WALLET mismatches:",
        monitored_mismatches,
    )

    print(
        "EXTERNAL_ADDRESS mismatches:",
        external_mismatches,
    )

    if self_mismatches != 0:
        fail(
            "SELF classification is incorrect"
        )

    if zero_mismatches != 0:
        fail(
            "ZERO_ADDRESS classification "
            "is incorrect"
        )

    if monitored_mismatches != 0:
        fail(
            "MONITORED_WALLET classification "
            "is incorrect"
        )

    if external_mismatches != 0:
        fail(
            "EXTERNAL_ADDRESS classification "
            "is incorrect"
        )


def check_amounts(
    connection,
):
    section(
        "COUNTERPARTY AMOUNT RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH expected AS (
                SELECT
                    CAST(
                        block_timestamp
                        AS DATE
                    ) AS activity_date,

                    wallet_id,

                    CASE
                        WHEN direction = 'IN'
                        THEN from_address

                        WHEN direction = 'OUT'
                        THEN to_address

                        WHEN direction = 'SELF'
                        THEN treasury_address
                    END
                        AS counterparty_address,

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

                    COUNT(*) AS total_event_count

                FROM
                    silver.erc20_transfers

                GROUP BY
                    activity_date,
                    wallet_id,
                    counterparty_address,
                    token_contract
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.wallet_daily_erc20_counterparty_flows
                AS g

                ON
                    e.activity_date
                        = g.activity_date

                    AND

                    e.wallet_id
                        = g.wallet_id

                    AND

                    e.counterparty_address
                        = g.counterparty_address

                    AND

                    e.token_contract
                        = g.token_contract

            WHERE
                e.activity_date IS NULL

                OR

                g.activity_date IS NULL

                OR

                e.inflow_amount
                    IS DISTINCT FROM
                    g.inflow_amount

                OR

                e.outflow_amount
                    IS DISTINCT FROM
                    g.outflow_amount

                OR

                e.net_flow_amount
                    IS DISTINCT FROM
                    g.net_flow_amount

                OR

                e.total_event_count
                    IS DISTINCT FROM
                    g.total_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Counterparty Gold values "
            "do not match Silver"
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

        check_table(
            connection
        )

        check_grain(
            connection
        )

        check_event_counts(
            connection
        )

        check_counterparty_types(
            connection
        )

        check_classification(
            connection
        )

        check_amounts(
            connection
        )

        print()
        print("=" * 100)
        print(
            "COUNTERPARTY GOLD VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()