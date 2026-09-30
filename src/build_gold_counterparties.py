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


def build_wallet_daily_counterparty_flows(
    connection,
):
    connection.execute(
        """
        CREATE SCHEMA
        IF NOT EXISTS gold
        """
    )


    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_daily_erc20_counterparty_flows
        """
    )


    connection.execute(
        """
        CREATE TABLE
        gold.wallet_daily_erc20_counterparty_flows
        AS

        WITH base_activity AS (
            SELECT
                CAST(
                    t.block_timestamp
                    AS DATE
                ) AS activity_date,

                t.block_timestamp,

                t.organization_id,

                t.wallet_id,

                t.treasury_address,

                t.token_contract,

                t.token_name,

                t.token_symbol,

                t.token_decimals,

                t.direction,

                t.amount_decimal,


                CASE
                    WHEN t.direction = 'IN'
                    THEN t.from_address

                    WHEN t.direction = 'OUT'
                    THEN t.to_address

                    WHEN t.direction = 'SELF'
                    THEN t.treasury_address

                    ELSE NULL
                END AS counterparty_address


            FROM
                silver.erc20_transfers AS t
        ),


        enriched_activity AS (
            SELECT
                b.*,

                counterparty_wallet.organization_id
                    AS counterparty_organization_id,

                counterparty_wallet.wallet_id
                    AS counterparty_wallet_id,

                counterparty_wallet.wallet_name
                    AS counterparty_wallet_name,

                counterparty_wallet.wallet_role
                    AS counterparty_wallet_role,


                CASE
                    WHEN
                        b.counterparty_address
                            = b.treasury_address

                    THEN 'SELF'


                    WHEN
                        b.counterparty_address
                            = ?

                    THEN 'ZERO_ADDRESS'


                    WHEN
                        counterparty_wallet.wallet_id
                            IS NOT NULL

                    THEN 'MONITORED_WALLET'


                    ELSE 'EXTERNAL_ADDRESS'
                END AS counterparty_type,


                CASE
                    WHEN
                        counterparty_wallet.organization_id
                            = b.organization_id

                    THEN TRUE

                    ELSE FALSE
                END AS same_organization


            FROM
                base_activity AS b


            LEFT JOIN
                silver.wallets
                AS counterparty_wallet

                ON
                    b.counterparty_address
                        = counterparty_wallet.address

                    AND

                    counterparty_wallet.monitoring_enabled
                        = TRUE
        )


        SELECT
            e.activity_date,

            e.organization_id,

            e.wallet_id,

            w.wallet_name,

            w.wallet_role,

            e.treasury_address,


            e.counterparty_address,

            e.counterparty_type,

            e.counterparty_organization_id,

            e.counterparty_wallet_id,

            e.counterparty_wallet_name,

            e.counterparty_wallet_role,

            e.same_organization,


            e.token_contract,

            e.token_name,

            e.token_symbol,

            e.token_decimals,


            SUM(
                CASE
                    WHEN e.direction = 'IN'
                    THEN e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS inflow_amount,


            SUM(
                CASE
                    WHEN e.direction = 'OUT'
                    THEN e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS outflow_amount,


            SUM(
                CASE
                    WHEN e.direction = 'IN'
                    THEN e.amount_decimal

                    WHEN e.direction = 'OUT'
                    THEN -e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS net_flow_amount,


            COUNT(
                CASE
                    WHEN e.direction = 'IN'
                    THEN 1
                END
            ) AS inflow_event_count,


            COUNT(
                CASE
                    WHEN e.direction = 'OUT'
                    THEN 1
                END
            ) AS outflow_event_count,


            COUNT(
                CASE
                    WHEN e.direction = 'SELF'
                    THEN 1
                END
            ) AS self_event_count,


            COUNT(*) AS total_event_count,


            MIN(
                e.block_timestamp
            ) AS first_event_timestamp,


            MAX(
                e.block_timestamp
            ) AS last_event_timestamp


        FROM
            enriched_activity AS e


        JOIN
            silver.wallets AS w

            ON
                e.wallet_id
                    = w.wallet_id


        WHERE
            e.counterparty_address
                IS NOT NULL


        GROUP BY
            e.activity_date,

            e.organization_id,

            e.wallet_id,

            w.wallet_name,

            w.wallet_role,

            e.treasury_address,

            e.counterparty_address,

            e.counterparty_type,

            e.counterparty_organization_id,

            e.counterparty_wallet_id,

            e.counterparty_wallet_name,

            e.counterparty_wallet_role,

            e.same_organization,

            e.token_contract,

            e.token_name,

            e.token_symbol,

            e.token_decimals
        """,
        [
            ZERO_ADDRESS
        ],
    )


def print_summary(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "COUNTERPARTY GOLD BUILD COMPLETE"
    )
    print(
        "=" * 100
    )


    row_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_daily_erc20_counterparty_flows
            """
        ).fetchone()[0]
    )


    total_events = (
        connection.execute(
            """
            SELECT
                SUM(total_event_count)

            FROM
                gold.wallet_daily_erc20_counterparty_flows
            """
        ).fetchone()[0]
    )


    print(
        "Gold rows:",
        row_count,
    )

    print(
        "Total ERC20 wallet events:",
        total_events,
    )


    print()
    print(
        "Counterparty summary by wallet:"
    )


    rows = connection.execute(
        """
        SELECT
            wallet_id,

            COUNT(
                DISTINCT counterparty_address
            ) AS distinct_counterparties,

            SUM(
                total_event_count
            ) AS total_events,

            SUM(
                CASE
                    WHEN
                        counterparty_type
                            = 'MONITORED_WALLET'

                    THEN total_event_count

                    ELSE 0
                END
            ) AS monitored_wallet_events,

            SUM(
                CASE
                    WHEN
                        counterparty_type
                            = 'SELF'

                    THEN total_event_count

                    ELSE 0
                END
            ) AS self_events,

            SUM(
                CASE
                    WHEN
                        counterparty_type
                            = 'ZERO_ADDRESS'

                    THEN total_event_count

                    ELSE 0
                END
            ) AS zero_address_events


        FROM
            gold.wallet_daily_erc20_counterparty_flows


        GROUP BY
            wallet_id


        ORDER BY
            wallet_id
        """
    ).fetchall()


    for row in rows:
        print(
            "  ",
            row[0],
            "| counterparties:",
            row[1],
            "| events:",
            row[2],
            "| monitored wallet:",
            row[3],
            "| self:",
            row[4],
            "| zero address:",
            row[5],
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


        connection.execute(
            "BEGIN TRANSACTION"
        )


        build_wallet_daily_counterparty_flows(
            connection
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
        print_summary(
            connection
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()