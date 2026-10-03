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


def build_wallet_metadata(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallets
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallets
        AS

        SELECT
            organization_id,
            organization_name,
            wallet_id,
            wallet_name,
            wallet_role,
            LOWER(address) AS address,
            monitoring_enabled

        FROM
            silver.wallets

        ORDER BY
            organization_id,
            wallet_name,
            wallet_id
        """
    )


def build_wallet_erc20_transfer_valuations(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_erc20_transfer_valuations
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallet_erc20_transfer_valuations
        AS

        SELECT
            t.*,

            CAST(
                t.block_timestamp
                AS DATE
            ) AS valuation_date,

            p.asset_id
                AS price_asset_id,

            p.price_status
                AS source_price_status,

            p.provider
                AS price_provider,

            p.price_usd
                AS daily_price_usd,

            p.confidence
                AS price_confidence,

            p.requested_timestamp
                AS price_requested_timestamp,

            p.source_timestamp
                AS price_source_timestamp,

            p.source_delta_seconds
                AS price_source_delta_seconds,

            CASE
                WHEN
                    p.token_contract IS NULL

                THEN
                    'ASSET_NOT_PRICED'

                WHEN
                    p.price_status = 'UNAVAILABLE'

                THEN
                    'PRICE_UNAVAILABLE'

                WHEN
                    p.price_status = 'AVAILABLE'
                    AND p.price_usd IS NOT NULL
                    AND t.amount_decimal IS NOT NULL

                THEN
                    'VALUED'

                WHEN
                    p.price_status = 'AVAILABLE'
                    AND p.price_usd IS NOT NULL
                    AND t.amount_decimal IS NULL

                THEN
                    'AMOUNT_UNAVAILABLE'

                ELSE
                    'PRICE_DATA_INVALID'
            END AS valuation_status,

            CASE
                WHEN
                    p.price_status = 'AVAILABLE'
                    AND p.price_usd IS NOT NULL
                    AND t.amount_decimal IS NOT NULL

                THEN
                    CAST(
                        CAST(
                            t.amount_decimal
                            AS DOUBLE
                        )
                        *
                        CAST(
                            p.price_usd
                            AS DOUBLE
                        )
                        AS DECIMAL(38,8)
                    )

                ELSE
                    NULL
            END AS value_usd

        FROM
            silver.erc20_transfers AS t

        LEFT JOIN
            silver.token_prices_daily AS p

            ON
                t.chain_id
                    = p.chain_id

                AND

                t.token_contract
                    = p.token_contract

                AND

                CAST(
                    t.block_timestamp
                    AS DATE
                )
                    = p.price_date
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
            v.valuation_date
                AS flow_date,

            v.organization_id,

            v.wallet_id,

            w.wallet_name,

            w.wallet_role,

            v.treasury_address,

            v.token_contract,

            v.token_name,

            v.token_symbol,

            v.token_decimals,

            v.valuation_status,

            v.daily_price_usd,

            SUM(
                CASE
                    WHEN v.direction = 'IN'
                    THEN v.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS inflow_amount,

            SUM(
                CASE
                    WHEN v.direction = 'OUT'
                    THEN v.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS outflow_amount,

            SUM(
                CASE
                    WHEN v.direction = 'IN'
                    THEN v.amount_decimal

                    WHEN v.direction = 'OUT'
                    THEN -v.amount_decimal

                    ELSE CAST(
                        0
                        AS DECIMAL(38,18)
                    )
                END
            ) AS net_flow_amount,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN v.direction = 'IN'
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                v.direction = 'IN'
                                AND v.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN v.direction = 'IN'
                            THEN v.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS inflow_usd,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN v.direction = 'OUT'
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                v.direction = 'OUT'
                                AND v.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN v.direction = 'OUT'
                            THEN v.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS outflow_usd,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN
                                v.direction IN (
                                    'IN',
                                    'OUT'
                                )
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                v.direction IN (
                                    'IN',
                                    'OUT'
                                )
                                AND v.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN v.direction = 'IN'
                            THEN v.value_usd

                            WHEN v.direction = 'OUT'
                            THEN -v.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS net_flow_usd,

            COUNT(
                CASE
                    WHEN v.direction = 'IN'
                    THEN 1
                END
            ) AS inflow_event_count,

            COUNT(
                CASE
                    WHEN v.direction = 'OUT'
                    THEN 1
                END
            ) AS outflow_event_count,

            COUNT(
                CASE
                    WHEN v.direction = 'SELF'
                    THEN 1
                END
            ) AS self_event_count,

            COUNT(*) AS total_event_count,

            COUNT(
                CASE
                    WHEN v.amount_decimal IS NULL
                    THEN 1
                END
            ) AS non_decimal_event_count,

            COUNT(
                CASE
                    WHEN
                        v.valuation_status = 'VALUED'
                    THEN 1
                END
            ) AS valued_event_count,

            COUNT(
                CASE
                    WHEN
                        v.valuation_status
                            = 'PRICE_UNAVAILABLE'
                    THEN 1
                END
            ) AS price_unavailable_event_count,

            COUNT(
                CASE
                    WHEN
                        v.valuation_status
                            = 'ASSET_NOT_PRICED'
                    THEN 1
                END
            ) AS asset_not_priced_event_count,

            COUNT(
                CASE
                    WHEN
                        v.valuation_status
                            = 'AMOUNT_UNAVAILABLE'
                    THEN 1
                END
            ) AS amount_unavailable_event_count,

            COUNT(
                CASE
                    WHEN
                        v.valuation_status
                            = 'PRICE_DATA_INVALID'
                    THEN 1
                END
            ) AS price_data_invalid_event_count

        FROM
            gold.wallet_erc20_transfer_valuations
            AS v

        JOIN
            silver.wallets AS w

            ON
                v.wallet_id
                    = w.wallet_id

        GROUP BY
            flow_date,
            v.organization_id,
            v.wallet_id,
            w.wallet_name,
            w.wallet_role,
            v.treasury_address,
            v.token_contract,
            v.token_name,
            v.token_symbol,
            v.token_decimals,
            v.valuation_status,
            v.daily_price_usd
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
                v.blockchain_event_id,

                v.chain_id,

                v.organization_id,

                v.valuation_date
                    AS flow_date,

                v.token_contract,

                v.token_name,

                v.token_symbol,

                v.token_decimals,

                v.from_address,

                v.to_address,

                v.amount_decimal,

                v.valuation_status,

                v.daily_price_usd,

                v.value_usd

            FROM
                gold.wallet_erc20_transfer_valuations
                AS v
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
                END
                    AS organization_direction

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

            e.valuation_status,

            e.daily_price_usd,

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

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'IN'
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'IN'
                                AND e.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'IN'
                            THEN e.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS external_inflow_usd,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'OUT'
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'OUT'
                                AND e.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'OUT'
                            THEN e.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS external_outflow_usd,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                IN (
                                    'IN',
                                    'OUT'
                                )
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                IN (
                                    'IN',
                                    'OUT'
                                )
                                AND e.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'IN'
                            THEN e.value_usd

                            WHEN
                                e.organization_direction
                                    = 'OUT'
                            THEN -e.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS net_external_flow_usd,

            CASE
                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'INTERNAL'
                            THEN 1
                        END
                    ) = 0

                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN
                    COUNT(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'INTERNAL'
                                AND e.value_usd IS NULL
                            THEN 1
                        END
                    ) = 0

                THEN
                    SUM(
                        CASE
                            WHEN
                                e.organization_direction
                                    = 'INTERNAL'
                            THEN e.value_usd

                            ELSE CAST(
                                0
                                AS DECIMAL(38,8)
                            )
                        END
                    )

                ELSE
                    NULL
            END AS internal_transfer_usd,

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
                        e.organization_direction
                            = 'INTERNAL'
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
                    WHEN e.amount_decimal IS NULL
                    THEN 1
                END
            ) AS non_decimal_event_count,

            COUNT(
                CASE
                    WHEN
                        e.valuation_status = 'VALUED'
                    THEN 1
                END
            ) AS valued_event_count,

            COUNT(
                CASE
                    WHEN
                        e.valuation_status
                            = 'PRICE_UNAVAILABLE'
                    THEN 1
                END
            ) AS price_unavailable_event_count,

            COUNT(
                CASE
                    WHEN
                        e.valuation_status
                            = 'ASSET_NOT_PRICED'
                    THEN 1
                END
            ) AS asset_not_priced_event_count,

            COUNT(
                CASE
                    WHEN
                        e.valuation_status
                            = 'AMOUNT_UNAVAILABLE'
                    THEN 1
                END
            ) AS amount_unavailable_event_count,

            COUNT(
                CASE
                    WHEN
                        e.valuation_status
                            = 'PRICE_DATA_INVALID'
                    THEN 1
                END
            ) AS price_data_invalid_event_count

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
            e.token_decimals,
            e.valuation_status,
            e.daily_price_usd
        """
    )


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
    print("=" * 100)
    print("GOLD BUILD COMPLETE")
    print("=" * 100)

    for table_name in [
        "wallets",
        "wallet_erc20_transfer_valuations",
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
        "ERC20 valuation status summary:"
    )

    rows = connection.execute(
        """
        SELECT
            valuation_status,
            COUNT(*) AS row_count

        FROM
            gold.wallet_erc20_transfer_valuations

        GROUP BY
            valuation_status

        ORDER BY
            valuation_status
        """
    ).fetchall()

    for row in rows:
        print(
            "  ",
            row[0],
            "| rows:",
            row[1],
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

        build_wallet_metadata(
            connection
        )

        build_wallet_erc20_transfer_valuations(
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