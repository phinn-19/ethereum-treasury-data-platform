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


def load_threshold():
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    rule = config.get(
        "native_eth_large_transfer_monitoring"
    )

    if not isinstance(rule, dict):
        raise RuntimeError(
            "Missing native ETH large transfer config"
        )

    if not rule.get("enabled", False):
        raise RuntimeError(
            "Native ETH large transfer monitoring "
            "is disabled"
        )

    if rule.get("scope") != "organization":
        raise RuntimeError(
            "Native ETH monitoring scope "
            "must be organization"
        )

    if rule.get("asset_type") != "native_eth":
        raise RuntimeError(
            "Native ETH monitoring asset_type "
            "must be native_eth"
        )

    if rule.get("quote_currency") != "usd":
        raise RuntimeError(
            "Native ETH monitoring quote_currency "
            "must be usd"
        )

    threshold = Decimal(
        str(rule["threshold_usd"])
    )

    if threshold <= 0:
        raise RuntimeError(
            "Native ETH threshold must be > 0"
        )

    return threshold


def build_wallet_valuations(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_native_eth_valuations
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallet_native_eth_valuations
        AS

        SELECT
            m.*,

            CAST(
                m.block_timestamp
                AS DATE
            ) AS valuation_date,

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
                WHEN p.price_date IS NULL
                THEN
                    'PRICE_NOT_FOUND'

                WHEN
                    p.price_status
                        = 'UNAVAILABLE'
                THEN
                    'PRICE_UNAVAILABLE'

                WHEN
                    p.price_status = 'AVAILABLE'
                    AND p.price_usd IS NOT NULL
                    AND m.value_eth_decimal IS NOT NULL
                THEN
                    'VALUED'

                ELSE
                    'PRICE_DATA_INVALID'
            END
                AS valuation_status,

            CASE
                WHEN
                    p.price_status = 'AVAILABLE'

                    AND

                    p.price_usd IS NOT NULL

                    AND

                    m.value_eth_decimal IS NOT NULL

                THEN
                    CAST(
                        CAST(
                            m.value_eth_decimal
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
            END
                AS value_usd

        FROM
            gold.wallet_native_eth_movements
            AS m

        LEFT JOIN
            silver.native_eth_prices_daily
            AS p

            ON
                m.chain_id
                    = p.chain_id

                AND

                CAST(
                    m.block_timestamp
                    AS DATE
                )
                    = p.price_date
        """
    )


def build_organization_valuations(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_native_eth_valuations
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_native_eth_valuations
        AS

        SELECT
            m.*,

            CAST(
                m.block_timestamp
                AS DATE
            ) AS valuation_date,

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
                WHEN p.price_date IS NULL
                THEN
                    'PRICE_NOT_FOUND'

                WHEN
                    p.price_status
                        = 'UNAVAILABLE'
                THEN
                    'PRICE_UNAVAILABLE'

                WHEN
                    p.price_status = 'AVAILABLE'
                    AND p.price_usd IS NOT NULL
                    AND m.value_eth_decimal IS NOT NULL
                THEN
                    'VALUED'

                ELSE
                    'PRICE_DATA_INVALID'
            END
                AS valuation_status,

            CASE
                WHEN
                    p.price_status = 'AVAILABLE'

                    AND

                    p.price_usd IS NOT NULL

                    AND

                    m.value_eth_decimal IS NOT NULL

                THEN
                    CAST(
                        CAST(
                            m.value_eth_decimal
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
            END
                AS value_usd

        FROM
            gold.organization_native_eth_movements
            AS m

        LEFT JOIN
            silver.native_eth_prices_daily
            AS p

            ON
                m.chain_id
                    = p.chain_id

                AND

                CAST(
                    m.block_timestamp
                    AS DATE
                )
                    = p.price_date
        """
    )


def build_daily_usd_flows(
    connection,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.wallet_daily_native_eth_usd_flows
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.wallet_daily_native_eth_usd_flows
        AS

        SELECT
            valuation_date
                AS activity_date,

            chain_id,

            organization_id,

            wallet_id,

            SUM(
                CASE
                    WHEN direction = 'IN'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ) AS inflow_eth,

            SUM(
                CASE
                    WHEN direction = 'OUT'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ) AS outflow_eth,

            SUM(
                CASE
                    WHEN direction = 'IN'
                    THEN value_eth_decimal

                    WHEN direction = 'OUT'
                    THEN -value_eth_decimal

                    ELSE 0
                END
            ) AS net_flow_eth,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN direction = 'IN'
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            direction = 'IN'
                            AND value_usd IS NULL
                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN direction = 'IN'
                            THEN value_usd
                        END
                    )
            END AS inflow_usd,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN direction = 'OUT'
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            direction = 'OUT'
                            AND value_usd IS NULL
                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN direction = 'OUT'
                            THEN value_usd
                        END
                    )
            END AS outflow_usd,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN direction IN (
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

                WHEN COUNT(
                    CASE
                        WHEN
                            direction IN (
                                'IN',
                                'OUT'
                            )

                            AND

                            value_usd IS NULL

                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN direction = 'IN'
                            THEN value_usd

                            WHEN direction = 'OUT'
                            THEN -value_usd

                            ELSE
                                CAST(
                                    0
                                    AS DECIMAL(38,8)
                                )
                        END
                    )
            END AS net_flow_usd,

            COUNT(*)
                AS event_count,

            COUNT(
                CASE
                    WHEN valuation_status = 'VALUED'
                    THEN 1
                END
            ) AS valued_event_count,

            COUNT(
                CASE
                    WHEN valuation_status != 'VALUED'
                    THEN 1
                END
            ) AS unvalued_event_count

        FROM
            gold.wallet_native_eth_valuations

        GROUP BY
            valuation_date,
            chain_id,
            organization_id,
            wallet_id
        """
    )

    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_daily_native_eth_usd_flows
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_daily_native_eth_usd_flows
        AS

        SELECT
            valuation_date
                AS activity_date,

            chain_id,

            organization_id,

            SUM(
                CASE
                    WHEN organization_direction = 'IN'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ) AS inflow_eth,

            SUM(
                CASE
                    WHEN organization_direction = 'OUT'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ) AS outflow_eth,

            SUM(
                CASE
                    WHEN
                        organization_direction
                            = 'INTERNAL'
                    THEN value_eth_decimal
                    ELSE 0
                END
            ) AS internal_eth,

            SUM(
                CASE
                    WHEN organization_direction = 'IN'
                    THEN value_eth_decimal

                    WHEN organization_direction = 'OUT'
                    THEN -value_eth_decimal

                    ELSE 0
                END
            ) AS net_flow_eth,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction = 'IN'
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction = 'IN'

                            AND

                            value_usd IS NULL

                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'IN'
                            THEN value_usd
                        END
                    )
            END AS inflow_usd,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction = 'OUT'
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction = 'OUT'

                            AND

                            value_usd IS NULL

                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'OUT'
                            THEN value_usd
                        END
                    )
            END AS outflow_usd,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction
                                = 'INTERNAL'
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction
                                = 'INTERNAL'

                            AND

                            value_usd IS NULL

                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN
                                organization_direction
                                    = 'INTERNAL'
                            THEN value_usd
                        END
                    )
            END AS internal_usd,

            CASE
                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction
                                IN ('IN', 'OUT')
                        THEN 1
                    END
                ) = 0
                THEN
                    CAST(
                        0
                        AS DECIMAL(38,8)
                    )

                WHEN COUNT(
                    CASE
                        WHEN
                            organization_direction
                                IN ('IN', 'OUT')

                            AND

                            value_usd IS NULL

                        THEN 1
                    END
                ) > 0
                THEN NULL

                ELSE
                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'IN'
                            THEN value_usd

                            WHEN
                                organization_direction = 'OUT'
                            THEN -value_usd

                            ELSE
                                CAST(
                                    0
                                    AS DECIMAL(38,8)
                                )
                        END
                    )
            END AS net_flow_usd,

            COUNT(*)
                AS event_count,

            COUNT(
                CASE
                    WHEN valuation_status = 'VALUED'
                    THEN 1
                END
            ) AS valued_event_count,

            COUNT(
                CASE
                    WHEN valuation_status != 'VALUED'
                    THEN 1
                END
            ) AS unvalued_event_count

        FROM
            gold.organization_native_eth_valuations

        GROUP BY
            valuation_date,
            chain_id,
            organization_id
        """
    )

def build_large_transfers(
    connection,
    threshold,
):
    connection.execute(
        """
        DROP TABLE IF EXISTS
        gold.organization_large_native_eth_transfers
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_large_native_eth_transfers
        AS

        SELECT
            *,

            CAST(
                ?
                AS DECIMAL(38,8)
            ) AS threshold_usd,

            TRUE
                AS large_transfer_flag

        FROM
            gold.organization_native_eth_valuations

        WHERE
            valuation_status = 'VALUED'

            AND

            value_usd >= CAST(
                ?
                AS DECIMAL(38,8)
            )
        """,
        [
            threshold,
            threshold,
        ],
    )


def print_summary(
    connection,
    threshold,
):
    print()
    print("=" * 100)
    print(
        "GOLD NATIVE ETH USD BUILD"
    )
    print("=" * 100)

    tables = [
        "wallet_native_eth_valuations",
        "organization_native_eth_valuations",
        "wallet_daily_native_eth_usd_flows",
        "organization_daily_native_eth_usd_flows",
        "organization_large_native_eth_transfers",
    ]

    for table_name in tables:
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

    print()
    print("Valuation status:")

    rows = connection.execute(
        """
        SELECT
            valuation_status,
            COUNT(*) AS event_count

        FROM
            gold.organization_native_eth_valuations

        GROUP BY
            valuation_status

        ORDER BY
            valuation_status
        """
    ).fetchall()

    for row in rows:
        print(
            " ",
            row[0],
            "| events:",
            row[1],
        )

    print()
    print(
        "Large transfer threshold USD:",
        threshold,
    )

    rows = connection.execute(
        """
        SELECT
            organization_direction,
            COUNT(*) AS event_count,
            SUM(value_usd)
                AS total_value_usd

        FROM
            gold.organization_large_native_eth_transfers

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
            "| total USD:",
            row[2],
        )

    print()
    print("Largest 10 native ETH transfers:")

    rows = connection.execute(
        """
        SELECT
            block_timestamp,
            organization_direction,
            value_eth_decimal,
            daily_price_usd,
            value_usd,
            from_address,
            effective_to_address

        FROM
            gold.organization_large_native_eth_transfers

        ORDER BY
            value_usd DESC

        LIMIT 10
        """
    ).fetchall()

    for row in rows:
        print(
            " ",
            row[0],
            "|",
            row[1],
            "| ETH:",
            row[2],
            "| price:",
            row[3],
            "| USD:",
            row[4],
            "| from:",
            row[5],
            "| to:",
            row[6],
        )


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB not found: {DATABASE_PATH}"
        )

    threshold = load_threshold()

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

        build_wallet_valuations(
            connection
        )

        build_organization_valuations(
            connection
        )

        build_daily_usd_flows(
            connection
        )

        build_large_transfers(
            connection,
            threshold,
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
            connection,
            threshold,
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()