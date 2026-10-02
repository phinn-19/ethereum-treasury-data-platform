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
        "wallet_erc20_transfer_valuations",
        "wallet_daily_erc20_flows",
        "organization_daily_erc20_flows",
        "wallet_daily_transaction_activity",
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

    transaction_duplicates = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    activity_date,
                    wallet_id

                FROM
                    gold.wallet_daily_transaction_activity

                GROUP BY
                    activity_date,
                    wallet_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    valuation_duplicates = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    activity_id

                FROM
                    gold.wallet_erc20_transfer_valuations

                GROUP BY
                    activity_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    print(
        "Transfer valuation duplicate "
        "activity_id groups:",
        valuation_duplicates,
    )

    print(
        "Wallet ERC20 duplicate "
        "(date, wallet, token) groups:",
        wallet_duplicates,
    )

    print(
        "Organization ERC20 duplicate "
        "(date, organization, token) groups:",
        organization_duplicates,
    )

    print(
        "Transaction activity duplicate "
        "(date, wallet) groups:",
        transaction_duplicates,
    )

    if valuation_duplicates != 0:
        fail(
            "ERC20 transfer valuation grain "
            "contains duplicate activity_id values"
        )

    if wallet_duplicates != 0:
        fail(
            "Wallet ERC20 Gold grain "
            "contains duplicates"
        )

    if organization_duplicates != 0:
        fail(
            "Organization ERC20 Gold grain "
            "contains duplicates"
        )

    if transaction_duplicates != 0:
        fail(
            "Transaction activity Gold grain "
            "contains duplicates"
        )


def check_erc20_transfer_valuations(
    connection,
):
    section(
        "ERC20 TRANSFER USD VALUATION CHECK"
    )

    silver_rows = connection.execute(
        """
        SELECT COUNT(*)

        FROM silver.erc20_transfers
        """
    ).fetchone()[0]

    valuation_rows = connection.execute(
        """
        SELECT COUNT(*)

        FROM gold.wallet_erc20_transfer_valuations
        """
    ).fetchone()[0]

    row_reconciliation_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                silver.erc20_transfers AS s

            FULL OUTER JOIN
                gold.wallet_erc20_transfer_valuations AS v

                ON s.activity_id = v.activity_id

            WHERE
                s.activity_id IS NULL

                OR v.activity_id IS NULL

                OR s.blockchain_event_id
                    IS DISTINCT FROM
                    v.blockchain_event_id

                OR s.chain_id
                    IS DISTINCT FROM
                    v.chain_id

                OR s.organization_id
                    IS DISTINCT FROM
                    v.organization_id

                OR s.wallet_id
                    IS DISTINCT FROM
                    v.wallet_id

                OR s.token_contract
                    IS DISTINCT FROM
                    v.token_contract

                OR s.block_timestamp
                    IS DISTINCT FROM
                    v.block_timestamp

                OR s.amount_decimal
                    IS DISTINCT FROM
                    v.amount_decimal

                OR s.direction
                    IS DISTINCT FROM
                    v.direction
            """
        ).fetchone()[0]
    )

    expected_status_mismatches = (
        connection.execute(
            """
            WITH expected AS (
                SELECT
                    s.activity_id,

                    p.asset_id
                        AS expected_price_asset_id,

                    p.price_status
                        AS expected_source_price_status,

                    p.provider
                        AS expected_price_provider,

                    p.price_usd
                        AS expected_daily_price_usd,

                    p.confidence
                        AS expected_price_confidence,

                    p.requested_timestamp
                        AS expected_requested_timestamp,

                    p.source_timestamp
                        AS expected_source_timestamp,

                    p.source_delta_seconds
                        AS expected_source_delta_seconds,

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
                            AND s.amount_decimal IS NOT NULL

                        THEN
                            'VALUED'

                        WHEN
                            p.price_status = 'AVAILABLE'
                            AND p.price_usd IS NOT NULL
                            AND s.amount_decimal IS NULL

                        THEN
                            'AMOUNT_UNAVAILABLE'

                        ELSE
                            'PRICE_DATA_INVALID'
                    END AS expected_valuation_status

                FROM
                    silver.erc20_transfers AS s

                LEFT JOIN
                    silver.token_prices_daily AS p

                    ON
                        s.chain_id = p.chain_id

                        AND

                        s.token_contract
                            = p.token_contract

                        AND

                        CAST(
                            s.block_timestamp
                            AS DATE
                        )
                            = p.price_date
            )

            SELECT COUNT(*)

            FROM
                expected AS e

            JOIN
                gold.wallet_erc20_transfer_valuations
                AS v

                ON
                    e.activity_id
                        = v.activity_id

            WHERE
                e.expected_price_asset_id
                    IS DISTINCT FROM
                    v.price_asset_id

                OR e.expected_source_price_status
                    IS DISTINCT FROM
                    v.source_price_status

                OR e.expected_price_provider
                    IS DISTINCT FROM
                    v.price_provider

                OR e.expected_daily_price_usd
                    IS DISTINCT FROM
                    v.daily_price_usd

                OR e.expected_price_confidence
                    IS DISTINCT FROM
                    v.price_confidence

                OR e.expected_requested_timestamp
                    IS DISTINCT FROM
                    v.price_requested_timestamp

                OR e.expected_source_timestamp
                    IS DISTINCT FROM
                    v.price_source_timestamp

                OR e.expected_source_delta_seconds
                    IS DISTINCT FROM
                    v.price_source_delta_seconds

                OR e.expected_valuation_status
                    IS DISTINCT FROM
                    v.valuation_status
            """
        ).fetchone()[0]
    )

    formula_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status = 'VALUED'

                AND

                value_usd
                    IS DISTINCT FROM
                    CAST(
                        CAST(
                            amount_decimal
                            AS DOUBLE
                        )
                        *
                        CAST(
                            daily_price_usd
                            AS DOUBLE
                        )
                        AS DECIMAL(38,8)
                    )
            """
        ).fetchone()[0]
    )

    invalid_valued_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status = 'VALUED'

                AND (
                    amount_decimal IS NULL

                    OR daily_price_usd IS NULL

                    OR daily_price_usd <= 0

                    OR value_usd IS NULL

                    OR source_price_status
                        IS DISTINCT FROM
                        'AVAILABLE'

                    OR price_asset_id IS NULL
                )
            """
        ).fetchone()[0]
    )

    invalid_price_unavailable_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status
                    = 'PRICE_UNAVAILABLE'

                AND (
                    price_asset_id IS NULL

                    OR source_price_status
                        IS DISTINCT FROM
                        'UNAVAILABLE'

                    OR daily_price_usd
                        IS NOT NULL

                    OR value_usd
                        IS NOT NULL
                )
            """
        ).fetchone()[0]
    )

    invalid_asset_not_priced_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status
                    = 'ASSET_NOT_PRICED'

                AND (
                    price_asset_id IS NOT NULL

                    OR source_price_status
                        IS NOT NULL

                    OR price_provider
                        IS NOT NULL

                    OR daily_price_usd
                        IS NOT NULL

                    OR price_confidence
                        IS NOT NULL

                    OR price_requested_timestamp
                        IS NOT NULL

                    OR price_source_timestamp
                        IS NOT NULL

                    OR price_source_delta_seconds
                        IS NOT NULL

                    OR value_usd
                        IS NOT NULL
                )
            """
        ).fetchone()[0]
    )

    unexpected_status_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status NOT IN (
                    'VALUED',
                    'PRICE_UNAVAILABLE',
                    'ASSET_NOT_PRICED',
                    'AMOUNT_UNAVAILABLE',
                    'PRICE_DATA_INVALID'
                )
            """
        ).fetchone()[0]
    )

    amount_unavailable_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status
                    = 'AMOUNT_UNAVAILABLE'
            """
        ).fetchone()[0]
    )

    invalid_price_data_rows = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_erc20_transfer_valuations

            WHERE
                valuation_status
                    = 'PRICE_DATA_INVALID'
            """
        ).fetchone()[0]
    )

    status_rows = connection.execute(
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

    print(
        "Silver ERC20 rows:",
        silver_rows,
    )

    print(
        "Gold valuation rows:",
        valuation_rows,
    )

    print(
        "Transfer row reconciliation mismatches:",
        row_reconciliation_mismatches,
    )

    print(
        "Price/status linkage mismatches:",
        expected_status_mismatches,
    )

    print(
        "USD formula mismatches:",
        formula_mismatches,
    )

    print(
        "Invalid VALUED rows:",
        invalid_valued_rows,
    )

    print(
        "Invalid PRICE_UNAVAILABLE rows:",
        invalid_price_unavailable_rows,
    )

    print(
        "Invalid ASSET_NOT_PRICED rows:",
        invalid_asset_not_priced_rows,
    )

    print(
        "AMOUNT_UNAVAILABLE rows:",
        amount_unavailable_rows,
    )

    print(
        "PRICE_DATA_INVALID rows:",
        invalid_price_data_rows,
    )

    print(
        "Unexpected valuation statuses:",
        unexpected_status_rows,
    )

    print()
    print(
        "Valuation status summary:"
    )

    for row in status_rows:
        print(
            "  ",
            row[0],
            "| rows:",
            row[1],
        )

    if silver_rows != valuation_rows:
        fail(
            "Gold ERC20 valuation row count "
            "does not match Silver"
        )

    if row_reconciliation_mismatches != 0:
        fail(
            "Gold ERC20 valuation rows "
            "do not reconcile one-to-one "
            "with Silver"
        )

    if expected_status_mismatches != 0:
        fail(
            "Gold ERC20 valuation price "
            "linkage or status is incorrect"
        )

    if formula_mismatches != 0:
        fail(
            "Some ERC20 USD values do not "
            "equal amount_decimal * price"
        )

    if invalid_valued_rows != 0:
        fail(
            "Invalid VALUED ERC20 rows detected"
        )

    if invalid_price_unavailable_rows != 0:
        fail(
            "Invalid PRICE_UNAVAILABLE "
            "ERC20 rows detected"
        )

    if invalid_asset_not_priced_rows != 0:
        fail(
            "Invalid ASSET_NOT_PRICED "
            "ERC20 rows detected"
        )

    if amount_unavailable_rows != 0:
        fail(
            "Some ERC20 transfers cannot "
            "be valued because amount_decimal "
            "is unavailable"
        )

    if invalid_price_data_rows != 0:
        fail(
            "Invalid token price data reached "
            "the Gold valuation table"
        )

    if unexpected_status_rows != 0:
        fail(
            "Unexpected ERC20 valuation "
            "status detected"
        )


def check_wallet_usd_measures(
    connection,
):
    section(
        "WALLET ERC20 USD RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH expected AS (
                SELECT
                    valuation_date
                        AS flow_date,

                    wallet_id,

                    token_contract,

                    CASE
                        WHEN
                            COUNT(
                                CASE
                                    WHEN
                                        direction = 'IN'
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
                                        direction = 'IN'
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN direction = 'IN'
                                    THEN value_usd

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
                                    WHEN
                                        direction = 'OUT'
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
                                        direction = 'OUT'
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN direction = 'OUT'
                                    THEN value_usd

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
                                        direction IN (
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
                                        direction IN (
                                            'IN',
                                            'OUT'
                                        )
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN direction = 'IN'
                                    THEN value_usd

                                    WHEN direction = 'OUT'
                                    THEN -value_usd

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
                            WHEN
                                valuation_status = 'VALUED'
                            THEN 1
                        END
                    ) AS valued_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'PRICE_UNAVAILABLE'
                            THEN 1
                        END
                    ) AS price_unavailable_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'ASSET_NOT_PRICED'
                            THEN 1
                        END
                    ) AS asset_not_priced_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'AMOUNT_UNAVAILABLE'
                            THEN 1
                        END
                    ) AS amount_unavailable_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'PRICE_DATA_INVALID'
                            THEN 1
                        END
                    ) AS price_data_invalid_event_count

                FROM
                    gold.wallet_erc20_transfer_valuations

                GROUP BY
                    1,
                    2,
                    3
            )

            SELECT COUNT(*)

            FROM
                expected AS e

            FULL OUTER JOIN
                gold.wallet_daily_erc20_flows AS g

                ON
                    e.flow_date = g.flow_date

                    AND

                    e.wallet_id = g.wallet_id

                    AND

                    e.token_contract
                        = g.token_contract

            WHERE
                e.flow_date IS NULL

                OR g.flow_date IS NULL

                OR e.inflow_usd
                    IS DISTINCT FROM
                    g.inflow_usd

                OR e.outflow_usd
                    IS DISTINCT FROM
                    g.outflow_usd

                OR e.net_flow_usd
                    IS DISTINCT FROM
                    g.net_flow_usd

                OR e.valued_event_count
                    IS DISTINCT FROM
                    g.valued_event_count

                OR e.price_unavailable_event_count
                    IS DISTINCT FROM
                    g.price_unavailable_event_count

                OR e.asset_not_priced_event_count
                    IS DISTINCT FROM
                    g.asset_not_priced_event_count

                OR e.amount_unavailable_event_count
                    IS DISTINCT FROM
                    g.amount_unavailable_event_count

                OR e.price_data_invalid_event_count
                    IS DISTINCT FROM
                    g.price_data_invalid_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Wallet USD aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Wallet ERC20 USD aggregates "
            "do not reconcile with transfer "
            "valuations"
        )


def check_organization_usd_measures(
    connection,
):
    section(
        "ORGANIZATION ERC20 USD RECONCILIATION"
    )

    mismatch_count = (
        connection.execute(
            """
            WITH blockchain_events AS (
                SELECT DISTINCT
                    blockchain_event_id,

                    organization_id,

                    valuation_date
                        AS flow_date,

                    token_contract,

                    from_address,

                    to_address,

                    valuation_status,

                    value_usd

                FROM
                    gold.wallet_erc20_transfer_valuations
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
                    END AS organization_direction

                FROM
                    blockchain_events AS e

                LEFT JOIN
                    silver.wallets AS from_wallet

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
                    silver.wallets AS to_wallet

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

                    CASE
                        WHEN
                            COUNT(
                                CASE
                                    WHEN
                                        organization_direction
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
                                        organization_direction
                                            = 'IN'
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN
                                        organization_direction
                                            = 'IN'

                                    THEN value_usd

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
                                        organization_direction
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
                                        organization_direction
                                            = 'OUT'
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN
                                        organization_direction
                                            = 'OUT'

                                    THEN value_usd

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
                                        organization_direction
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
                                        organization_direction
                                        IN (
                                            'IN',
                                            'OUT'
                                        )
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN
                                        organization_direction
                                            = 'IN'

                                    THEN value_usd

                                    WHEN
                                        organization_direction
                                            = 'OUT'

                                    THEN -value_usd

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

                        WHEN
                            COUNT(
                                CASE
                                    WHEN
                                        organization_direction
                                            = 'INTERNAL'
                                        AND value_usd IS NULL
                                    THEN 1
                                END
                            ) = 0

                        THEN
                            SUM(
                                CASE
                                    WHEN
                                        organization_direction
                                            = 'INTERNAL'

                                    THEN value_usd

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
                                valuation_status = 'VALUED'
                            THEN 1
                        END
                    ) AS valued_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'PRICE_UNAVAILABLE'
                            THEN 1
                        END
                    ) AS price_unavailable_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'ASSET_NOT_PRICED'
                            THEN 1
                        END
                    ) AS asset_not_priced_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'AMOUNT_UNAVAILABLE'
                            THEN 1
                        END
                    ) AS amount_unavailable_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status
                                    = 'PRICE_DATA_INVALID'
                            THEN 1
                        END
                    ) AS price_data_invalid_event_count

                FROM
                    classified

                GROUP BY
                    1,
                    2,
                    3
            )

            SELECT COUNT(*)

            FROM
                expected AS e

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

                OR e.external_inflow_usd
                    IS DISTINCT FROM
                    g.external_inflow_usd

                OR e.external_outflow_usd
                    IS DISTINCT FROM
                    g.external_outflow_usd

                OR e.net_external_flow_usd
                    IS DISTINCT FROM
                    g.net_external_flow_usd

                OR e.internal_transfer_usd
                    IS DISTINCT FROM
                    g.internal_transfer_usd

                OR e.valued_event_count
                    IS DISTINCT FROM
                    g.valued_event_count

                OR e.price_unavailable_event_count
                    IS DISTINCT FROM
                    g.price_unavailable_event_count

                OR e.asset_not_priced_event_count
                    IS DISTINCT FROM
                    g.asset_not_priced_event_count

                OR e.amount_unavailable_event_count
                    IS DISTINCT FROM
                    g.amount_unavailable_event_count

                OR e.price_data_invalid_event_count
                    IS DISTINCT FROM
                    g.price_data_invalid_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Organization USD aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Organization ERC20 USD aggregates "
            "do not reconcile with deduplicated "
            "transfer valuations"
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
        "WALLET ERC20 EVENT RECONCILIATION"
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
        "WALLET ERC20 AMOUNT RECONCILIATION"
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
        "Wallet ERC20 aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Wallet ERC20 Gold values "
            "do not match Silver"
        )


def check_organization_event_counts(
    connection,
):
    section(
        "ORGANIZATION ERC20 EVENT RECONCILIATION"
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
        "ORGANIZATION ERC20 AMOUNT RECONCILIATION"
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
        "Organization ERC20 aggregate "
        "mismatches:",
        mismatch_count,
    )

    print(
        "Organization OTHER events:",
        other_events,
    )

    if mismatch_count != 0:
        fail(
            "Organization ERC20 Gold values "
            "do not match Silver"
        )

    if other_events != 0:
        fail(
            "Organization Gold contains "
            "OTHER events"
        )


def check_transaction_activity_counts(
    connection,
):
    section(
        "TRANSACTION ACTIVITY COUNT RECONCILIATION"
    )

    silver_transactions = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.transactions
            """
        ).fetchone()[0]
    )

    gold_transaction_count = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(transaction_count),
                    0
                )

            FROM
                gold.wallet_daily_transaction_activity
            """
        ).fetchone()[0]
    )

    status_counts = (
        connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        successful_transaction_count
                    ),
                    0
                ),

                COALESCE(
                    SUM(
                        failed_transaction_count
                    ),
                    0
                ),

                COALESCE(
                    SUM(
                        unknown_status_count
                    ),
                    0
                )

            FROM
                gold.wallet_daily_transaction_activity
            """
        ).fetchone()
    )

    successful = status_counts[0]
    failed = status_counts[1]
    unknown = status_counts[2]

    status_total = (
        successful
        + failed
        + unknown
    )

    print(
        "Silver transactions:",
        silver_transactions,
    )

    print(
        "Gold transaction count:",
        gold_transaction_count,
    )

    print(
        "Successful:",
        successful,
    )

    print(
        "Failed:",
        failed,
    )

    print(
        "Unknown:",
        unknown,
    )

    print(
        "Status bucket total:",
        status_total,
    )

    if (
        silver_transactions
        != gold_transaction_count
    ):
        fail(
            "Gold transaction count "
            "does not match Silver"
        )

    if (
        status_total
        != gold_transaction_count
    ):
        fail(
            "Success + failed + unknown "
            "does not equal total "
            "transaction count"
        )


def check_transaction_activity_measures(
    connection,
):
    section(
        "TRANSACTION ACTIVITY MEASURE RECONCILIATION"
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

                    organization_id,

                    wallet_id,

                    treasury_address,

                    COUNT(*)
                        AS transaction_count,

                    COUNT(
                        CASE
                            WHEN
                                is_error IS TRUE

                                OR

                                receipt_status = 0

                            THEN 1
                        END
                    )
                        AS failed_transaction_count,

                    COUNT(
                        CASE
                            WHEN
                                receipt_status = 1

                                AND

                                is_error IS NOT TRUE

                            THEN 1
                        END
                    )
                        AS successful_transaction_count,

                    COUNT(
                        CASE
                            WHEN
                                NOT (
                                    is_error IS TRUE
                                    OR
                                    receipt_status = 0
                                )

                                AND

                                NOT (
                                    receipt_status = 1
                                    AND
                                    is_error IS NOT TRUE
                                )

                            THEN 1
                        END
                    )
                        AS unknown_status_count,

                    COUNT(
                        CASE
                            WHEN direction = 'CREATE'
                            THEN 1
                        END
                    )
                        AS contract_creation_count,

                    COALESCE(
                        SUM(gas_used),
                        0
                    )
                        AS total_gas_used,

                    SUM(
                        COALESCE(
                            gas_cost_eth_decimal,

                            CAST(
                                0
                                AS DECIMAL(38,18)
                            )
                        )
                    )
                        AS outer_transaction_fee_eth,

                    COUNT(
                        CASE
                            WHEN
                                gas_cost_eth_decimal
                                    IS NULL

                            THEN 1
                        END
                    )
                        AS missing_fee_count

                FROM
                    silver.transactions

                GROUP BY
                    1,
                    2,
                    3,
                    4
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.wallet_daily_transaction_activity
                AS g

                ON
                    e.activity_date
                        = g.activity_date

                    AND

                    e.wallet_id
                        = g.wallet_id

            WHERE
                e.activity_date IS NULL

                OR g.activity_date IS NULL

                OR e.organization_id
                    IS DISTINCT FROM
                    g.organization_id

                OR e.treasury_address
                    IS DISTINCT FROM
                    g.treasury_address

                OR e.transaction_count
                    IS DISTINCT FROM
                    g.transaction_count

                OR e.failed_transaction_count
                    IS DISTINCT FROM
                    g.failed_transaction_count

                OR e.successful_transaction_count
                    IS DISTINCT FROM
                    g.successful_transaction_count

                OR e.unknown_status_count
                    IS DISTINCT FROM
                    g.unknown_status_count

                OR e.contract_creation_count
                    IS DISTINCT FROM
                    g.contract_creation_count

                OR e.total_gas_used
                    IS DISTINCT FROM
                    g.total_gas_used

                OR e.outer_transaction_fee_eth
                    IS DISTINCT FROM
                    g.outer_transaction_fee_eth

                OR e.missing_fee_count
                    IS DISTINCT FROM
                    g.missing_fee_count
            """
        ).fetchone()[0]
    )

    print(
        "Transaction activity "
        "aggregate mismatches:",
        mismatch_count,
    )

    if mismatch_count != 0:
        fail(
            "Transaction activity Gold values "
            "do not match Silver"
        )


def check_transaction_quality(
    connection,
):
    section(
        "TRANSACTION ACTIVITY QUALITY CHECK"
    )

    row = connection.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    unknown_status_count
                ),
                0
            ),

            COALESCE(
                SUM(
                    missing_fee_count
                ),
                0
            ),

            COALESCE(
                SUM(
                    contract_creation_count
                ),
                0
            ),

            COALESCE(
                SUM(
                    total_gas_used
                ),
                0
            ),

            COALESCE(
                SUM(
                    outer_transaction_fee_eth
                ),
                CAST(
                    0
                    AS DECIMAL(38,18)
                )
            )

        FROM
            gold.wallet_daily_transaction_activity
        """
    ).fetchone()

    unknown = row[0]
    missing_fee = row[1]
    creation_count = row[2]
    total_gas_used = row[3]
    total_fee_eth = row[4]

    print(
        "Unknown transaction statuses:",
        unknown,
    )

    print(
        "Transactions missing fee:",
        missing_fee,
    )

    print(
        "Contract creation events:",
        creation_count,
    )

    print(
        "Total gas used:",
        total_gas_used,
    )

    print(
        "Outer transaction fee ETH:",
        total_fee_eth,
    )

    if unknown != 0:
        fail(
            "Some transactions have "
            "unknown status"
        )

    if missing_fee != 0:
        fail(
            "Some transactions are "
            "missing fee information"
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

        check_erc20_transfer_valuations(
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

        check_wallet_usd_measures(
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

        check_organization_usd_measures(
            connection
        )

        check_transaction_activity_counts(
            connection
        )

        check_transaction_activity_measures(
            connection
        )

        check_transaction_quality(
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