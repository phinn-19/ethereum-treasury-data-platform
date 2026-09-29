from pathlib import Path

import duckdb


DATABASE_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


def create_gold_schema(
    connection,
):
    connection.execute(
        """
        CREATE SCHEMA
        IF NOT EXISTS gold
        """
    )


def build_wallet_daily_erc20_flows(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_daily_erc20_flows
        """
    )


    connection.execute(
        """
        CREATE TABLE
        gold.wallet_daily_erc20_flows
        AS

        SELECT
            CAST(
                t.block_timestamp
                AS DATE
            ) AS flow_date,

            t.organization_id,

            t.wallet_id,

            w.wallet_name,

            w.wallet_role,

            t.treasury_address,

            t.token_contract,

            t.token_name,

            t.token_symbol,

            t.token_decimals,

            SUM(
                CASE
                    WHEN t.direction = 'IN'
                    THEN t.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS inflow_amount,

            SUM(
                CASE
                    WHEN t.direction = 'OUT'
                    THEN t.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS outflow_amount,

            SUM(
                CASE
                    WHEN t.direction = 'IN'
                    THEN t.amount_decimal

                    WHEN t.direction = 'OUT'
                    THEN -t.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS net_flow_amount,

            COUNT(
                CASE
                    WHEN t.direction = 'IN'
                    THEN 1
                END
            ) AS inflow_event_count,

            COUNT(
                CASE
                    WHEN t.direction = 'OUT'
                    THEN 1
                END
            ) AS outflow_event_count,

            COUNT(
                CASE
                    WHEN t.direction = 'SELF'
                    THEN 1
                END
            ) AS self_event_count,

            COUNT(*) AS total_event_count,

            COUNT(
                CASE
                    WHEN t.amount_decimal IS NULL
                    THEN 1
                END
            ) AS non_decimal_event_count

        FROM
            silver.erc20_transfers AS t

        JOIN
            silver.wallets AS w
            ON t.wallet_id = w.wallet_id

        GROUP BY
            flow_date,
            t.organization_id,
            t.wallet_id,
            w.wallet_name,
            w.wallet_role,
            t.treasury_address,
            t.token_contract,
            t.token_name,
            t.token_symbol,
            t.token_decimals
        """
    )


def build_organization_daily_erc20_flows(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_daily_erc20_flows
        """
    )


    connection.execute(
        """
        CREATE TABLE
        gold.organization_daily_erc20_flows
        AS

        WITH blockchain_events AS (
            SELECT DISTINCT
                t.blockchain_event_id,

                t.chain_id,

                t.organization_id,

                CAST(
                    t.block_timestamp
                    AS DATE
                ) AS flow_date,

                t.token_contract,

                t.token_name,

                t.token_symbol,

                t.token_decimals,

                t.from_address,

                t.to_address,

                t.amount_decimal

            FROM
                silver.erc20_transfers
                AS t
        ),


        classified_events AS (
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
                END AS organization_direction

            FROM
                blockchain_events AS e


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


        organization_names AS (
            SELECT DISTINCT
                organization_id,
                organization_name

            FROM
                silver.wallets
        )


        SELECT
            e.flow_date,

            e.organization_id,

            o.organization_name,

            e.token_contract,

            e.token_name,

            e.token_symbol,

            e.token_decimals,


            SUM(
                CASE
                    WHEN
                        e.organization_direction = 'IN'

                    THEN e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS external_inflow_amount,


            SUM(
                CASE
                    WHEN
                        e.organization_direction = 'OUT'

                    THEN e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS external_outflow_amount,


            SUM(
                CASE
                    WHEN
                        e.organization_direction = 'IN'

                    THEN e.amount_decimal


                    WHEN
                        e.organization_direction = 'OUT'

                    THEN -e.amount_decimal


                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS net_external_flow_amount,


            SUM(
                CASE
                    WHEN
                        e.organization_direction = 'INTERNAL'

                    THEN e.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS internal_transfer_amount,


            COUNT(
                CASE
                    WHEN
                        e.organization_direction = 'IN'

                    THEN 1
                END
            ) AS external_inflow_event_count,


            COUNT(
                CASE
                    WHEN
                        e.organization_direction = 'OUT'

                    THEN 1
                END
            ) AS external_outflow_event_count,


            COUNT(
                CASE
                    WHEN
                        e.organization_direction = 'INTERNAL'

                    THEN 1
                END
            ) AS internal_transfer_event_count,


            COUNT(
                CASE
                    WHEN
                        e.organization_direction = 'OTHER'

                    THEN 1
                END
            ) AS other_event_count,


            COUNT(*) AS total_event_count,


            COUNT(
                CASE
                    WHEN
                        e.amount_decimal IS NULL

                    THEN 1
                END
            ) AS non_decimal_event_count


        FROM
            classified_events AS e


        JOIN
            organization_names AS o

            ON
                e.organization_id
                    = o.organization_id


        GROUP BY
            e.flow_date,
            e.organization_id,
            o.organization_name,
            e.token_contract,
            e.token_name,
            e.token_symbol,
            e.token_decimals
        """
    )

#transaction_count là tổng normal transaction (giao dịch ngoài cùng) mà Silver đang theo dõi cho wallet trong ngày.
#failed_transaction_count dùng:
#is_error = true
#OR
#receipt_status = 0 -> sucess or failed

def build_wallet_daily_transaction_activity(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_daily_transaction_activity
        """
    )


    connection.execute(
        """
        CREATE TABLE
        gold.wallet_daily_transaction_activity
        AS

        SELECT
            CAST(
                t.block_timestamp
                AS DATE
            ) AS activity_date,

            t.organization_id,

            t.wallet_id,

            w.wallet_name,

            w.wallet_role,

            t.treasury_address,

            COUNT(*) AS transaction_count,


            COUNT(
                CASE
                    WHEN
                        t.is_error IS TRUE

                        OR

                        t.receipt_status = 0

                    THEN 1
                END
            ) AS failed_transaction_count,


            COUNT(
                CASE
                    WHEN
                        t.receipt_status = 1

                        AND

                        t.is_error IS NOT TRUE

                    THEN 1
                END
            ) AS successful_transaction_count,


            COUNT(
                CASE
                    WHEN
                        NOT (
                            t.is_error IS TRUE

                            OR

                            t.receipt_status = 0
                        )

                        AND

                        NOT (
                            t.receipt_status = 1

                            AND

                            t.is_error IS NOT TRUE
                        )

                    THEN 1
                END
            ) AS unknown_status_count,


            COUNT(
                CASE
                    WHEN t.direction = 'CREATE'
                    THEN 1
                END
            ) AS contract_creation_count,


            COALESCE(
                SUM(
                    t.gas_used
                ),
                0
            ) AS total_gas_used,


            SUM(
                COALESCE(
                    t.gas_cost_eth_decimal,

                    CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                )
            ) AS outer_transaction_fee_eth,


            COUNT(
                CASE
                    WHEN
                        t.gas_cost_eth_decimal
                            IS NULL

                    THEN 1
                END
            ) AS missing_fee_count


        FROM
            silver.transactions AS t


        JOIN
            silver.wallets AS w

            ON
                t.wallet_id
                    = w.wallet_id


        GROUP BY
            activity_date,
            t.organization_id,
            t.wallet_id,
            w.wallet_name,
            w.wallet_role,
            t.treasury_address
        """
    )


def print_summary(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "GOLD BUILD COMPLETE"
    )
    print(
        "=" * 100
    )


    for table_name in [
        "wallet_daily_erc20_flows",
        "organization_daily_erc20_flows",
        "wallet_daily_transaction_activity",
    ]:
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
        "Transaction activity summary:"
    )


    rows = connection.execute(
        """
        SELECT
            wallet_id,

            SUM(
                transaction_count
            ) AS transactions,

            SUM(
                successful_transaction_count
            ) AS successful,

            SUM(
                failed_transaction_count
            ) AS failed,

            SUM(
                unknown_status_count
            ) AS unknown,

            SUM(
                contract_creation_count
            ) AS creations,

            SUM(
                missing_fee_count
            ) AS missing_fee

        FROM
            gold.wallet_daily_transaction_activity

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
            "| tx:",
            row[1],
            "| success:",
            row[2],
            "| failed:",
            row[3],
            "| unknown:",
            row[4],
            "| create:",
            row[5],
            "| missing fee:",
            row[6],
        )


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "DuckDB database "
            "not found: "
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


        create_gold_schema(
            connection
        )


        build_wallet_daily_erc20_flows(
            connection
        )


        build_organization_daily_erc20_flows(
            connection
        )


        build_wallet_daily_transaction_activity(
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