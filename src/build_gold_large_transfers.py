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


def load_large_transfer_config():
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
        raise RuntimeError(
            "Missing large_transfer_monitoring "
            "config"
        )

    if not rule.get(
        "enabled",
        False,
    ):
        raise RuntimeError(
            "Large transfer monitoring "
            "is disabled"
        )

    if (
        rule.get("scope")
        != "organization"
    ):
        raise RuntimeError(
            "V1 large transfer scope must "
            "be organization"
        )

    if (
        rule.get("asset_type")
        != "erc20"
    ):
        raise RuntimeError(
            "V1 large transfer asset_type "
            "must be erc20"
        )

    if (
        rule.get("quote_currency")
        != "usd"
    ):
        raise RuntimeError(
            "V1 large transfer quote_currency "
            "must be usd"
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
            "Invalid large transfer "
            "threshold_usd"
        ) from error

    if threshold_usd <= 0:
        raise RuntimeError(
            "Large transfer threshold "
            "must be greater than zero"
        )

    return threshold_usd


def build_large_transfer_table(
    connection,
    threshold_usd,
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
        gold.organization_large_erc20_transfers
        """
    )

    connection.execute(
        """
        CREATE TABLE
        gold.organization_large_erc20_transfers
        AS

        WITH blockchain_events AS (
            SELECT DISTINCT
                v.blockchain_event_id,

                v.chain_id,

                v.organization_id,

                v.valuation_date
                    AS event_date,

                v.block_timestamp
                    AS event_timestamp,

                v.transaction_hash,

                v.log_index,

                v.token_contract,

                v.token_name,

                v.token_symbol,

                v.token_decimals,

                v.from_address,

                v.to_address,

                v.amount_decimal,

                v.daily_price_usd,

                v.value_usd,

                v.price_provider,

                v.price_confidence

            FROM
                gold.wallet_erc20_transfer_valuations
                AS v

            WHERE
                v.valuation_status = 'VALUED'

                AND

                v.value_usd IS NOT NULL
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
        )

        SELECT
            blockchain_event_id,

            chain_id,

            organization_id,

            event_date,

            event_timestamp,

            transaction_hash,

            log_index,

            token_contract,

            token_name,

            token_symbol,

            token_decimals,

            from_address,

            to_address,

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
                    to_address

                ELSE
                    NULL
            END
                AS counterparty_address,

            organization_direction
                = 'INTERNAL'
                AS is_internal_transfer,

            amount_decimal,

            daily_price_usd,

            value_usd,

            price_provider,

            price_confidence,

            CAST(
                ?
                AS DECIMAL(38,8)
            ) AS threshold_usd,

            TRUE
                AS large_transfer_flag

        FROM
            classified

        WHERE
            value_usd >= CAST(
                ?
                AS DECIMAL(38,8)
            )
        """,
        [
            threshold_usd,
            threshold_usd,
        ],
    )


def print_summary(
    connection,
    threshold_usd,
):
    print()
    print("=" * 100)
    print(
        "GOLD LARGE ERC20 TRANSFER BUILD"
    )
    print("=" * 100)

    print(
        "Threshold USD:",
        threshold_usd,
    )

    total_rows = connection.execute(
        """
        SELECT COUNT(*)

        FROM
            gold.organization_large_erc20_transfers
        """
    ).fetchone()[0]

    print(
        "Large blockchain events:",
        total_rows,
    )

    print()
    print(
        "Direction summary:"
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

    for row in rows:
        print(
            "  ",
            row[0],
            "| events:",
            row[1],
            "| total USD:",
            row[2],
        )

    print()
    print(
        "Largest 10 events:"
    )

    rows = connection.execute(
        """
        SELECT
            event_timestamp,

            organization_direction,

            token_symbol,

            amount_decimal,

            value_usd,

            from_address,

            to_address

        FROM
            gold.organization_large_erc20_transfers

        ORDER BY
            value_usd DESC

        LIMIT 10
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
            "| amount:",
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
            "DuckDB database not found: "
            f"{DATABASE_PATH}"
        )

    threshold_usd = (
        load_large_transfer_config()
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

        build_large_transfer_table(
            connection,
            threshold_usd,
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
            connection,
            threshold_usd,
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()