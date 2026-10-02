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


REQUIRED_TABLES = [
    "wallet_native_eth_valuations",
    "organization_native_eth_valuations",
    "wallet_daily_native_eth_usd_flows",
    "organization_daily_native_eth_usd_flows",
    "organization_large_native_eth_transfers",
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


def load_threshold():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Monitoring config not found: "
            f"{CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    rule = config.get(
        "native_eth_large_transfer_monitoring"
    )

    if not isinstance(
        rule,
        dict,
    ):
        fail(
            "Missing native ETH large transfer "
            "monitoring config"
        )

    if not rule.get(
        "enabled",
        False,
    ):
        fail(
            "Native ETH large transfer "
            "monitoring is disabled"
        )

    if (
        rule.get("scope")
        != "organization"
    ):
        fail(
            "Native ETH monitoring scope "
            "must be organization"
        )

    if (
        rule.get("asset_type")
        != "native_eth"
    ):
        fail(
            "Native ETH monitoring asset_type "
            "must be native_eth"
        )

    if (
        rule.get("quote_currency")
        != "usd"
    ):
        fail(
            "Native ETH quote currency "
            "must be usd"
        )

    try:
        threshold = Decimal(
            str(
                rule[
                    "threshold_usd"
                ]
            )
        )

    except Exception as error:
        raise RuntimeError(
            "Invalid native ETH "
            "threshold_usd"
        ) from error

    if threshold <= 0:
        fail(
            "Native ETH threshold must be "
            "greater than zero"
        )

    return threshold


def check_tables(
    connection,
):
    section(
        "NATIVE ETH USD TABLE CHECK"
    )

    for table_name in (
        REQUIRED_TABLES
    ):
        exists = connection.execute(
            """
            SELECT COUNT(*)

            FROM information_schema.tables

            WHERE
                table_schema = 'gold'

                AND

                table_name = ?
            """,
            [table_name],
        ).fetchone()[0]

        if exists != 1:
            fail(
                f"Missing gold.{table_name}"
            )

        row_count = connection.execute(
            f"""
            SELECT COUNT(*)

            FROM gold.{table_name}
            """
        ).fetchone()[0]

        print(
            f"{table_name}:",
            row_count,
        )


def check_wallet_valuations(
    connection,
):
    section(
        "WALLET NATIVE ETH VALUATION CHECK"
    )

    source_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_native_eth_movements
            """
        ).fetchone()[0]
    )

    valuation_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_native_eth_valuations
            """
        ).fetchone()[0]
    )

    duplicate_grain = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    wallet_id,
                    native_event_id

                FROM
                    gold.wallet_native_eth_valuations

                GROUP BY
                    wallet_id,
                    native_event_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    missing_or_unexpected = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.wallet_native_eth_movements
                AS m

            FULL OUTER JOIN
                gold.wallet_native_eth_valuations
                AS v

                ON
                    m.wallet_id
                        = v.wallet_id

                    AND

                    m.native_event_id
                        = v.native_event_id

            WHERE
                m.native_event_id IS NULL

                OR

                v.native_event_id IS NULL
            """
        ).fetchone()[0]
    )

    print(
        "Source wallet movements:",
        source_count,
    )

    print(
        "Wallet valuations:",
        valuation_count,
    )

    print(
        "Duplicate valuation grain:",
        duplicate_grain,
    )

    print(
        "Missing/unexpected rows:",
        missing_or_unexpected,
    )

    if (
        source_count
        != valuation_count
    ):
        fail(
            "Wallet valuation row count "
            "does not match wallet movements"
        )

    if duplicate_grain != 0:
        fail(
            "Wallet native ETH valuation "
            "grain is not unique"
        )

    if missing_or_unexpected != 0:
        fail(
            "Wallet valuation rows do not "
            "reconcile with movements"
        )


def check_organization_valuations(
    connection,
):
    section(
        "ORGANIZATION NATIVE ETH VALUATION CHECK"
    )

    source_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_movements
            """
        ).fetchone()[0]
    )

    valuation_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations
            """
        ).fetchone()[0]
    )

    duplicate_events = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    native_event_id

                FROM
                    gold.organization_native_eth_valuations

                GROUP BY
                    native_event_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    missing_or_unexpected = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_movements
                AS m

            FULL OUTER JOIN
                gold.organization_native_eth_valuations
                AS v

                ON
                    m.native_event_id
                        = v.native_event_id

            WHERE
                m.native_event_id IS NULL

                OR

                v.native_event_id IS NULL
            """
        ).fetchone()[0]
    )

    print(
        "Source organization movements:",
        source_count,
    )

    print(
        "Organization valuations:",
        valuation_count,
    )

    print(
        "Duplicate organization events:",
        duplicate_events,
    )

    print(
        "Missing/unexpected rows:",
        missing_or_unexpected,
    )

    if (
        source_count
        != valuation_count
    ):
        fail(
            "Organization valuation count "
            "does not match movements"
        )

    if duplicate_events != 0:
        fail(
            "Organization valuation grain "
            "is not unique"
        )

    if missing_or_unexpected != 0:
        fail(
            "Organization valuation rows "
            "do not reconcile"
        )


def check_price_linkage(
    connection,
):
    section(
        "NATIVE ETH PRICE LINKAGE CHECK"
    )

    result = connection.execute(
        """
        WITH expected AS (
            SELECT
                m.native_event_id,

                CAST(
                    m.block_timestamp
                    AS DATE
                ) AS valuation_date,

                p.price_status
                    AS expected_price_status,

                p.provider
                    AS expected_provider,

                p.price_usd
                    AS expected_price_usd,

                p.confidence
                    AS expected_confidence,

                p.requested_timestamp
                    AS expected_requested_timestamp,

                p.source_timestamp
                    AS expected_source_timestamp,

                p.source_delta_seconds
                    AS expected_delta_seconds,

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
                        p.price_status
                            = 'AVAILABLE'

                        AND

                        p.price_usd
                            IS NOT NULL

                        AND

                        m.value_eth_decimal
                            IS NOT NULL

                    THEN
                        'VALUED'

                    ELSE
                        'PRICE_DATA_INVALID'
                END
                    AS expected_valuation_status

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
        )

        SELECT COUNT(*)

        FROM expected AS e

        JOIN
            gold.organization_native_eth_valuations
            AS v

            ON
                e.native_event_id
                    = v.native_event_id

        WHERE
            e.valuation_date
                IS DISTINCT FROM
                v.valuation_date

            OR

            e.expected_price_status
                IS DISTINCT FROM
                v.source_price_status

            OR

            e.expected_provider
                IS DISTINCT FROM
                v.price_provider

            OR

            e.expected_price_usd
                IS DISTINCT FROM
                v.daily_price_usd

            OR

            e.expected_confidence
                IS DISTINCT FROM
                v.price_confidence

            OR

            e.expected_requested_timestamp
                IS DISTINCT FROM
                v.price_requested_timestamp

            OR

            e.expected_source_timestamp
                IS DISTINCT FROM
                v.price_source_timestamp

            OR

            e.expected_delta_seconds
                IS DISTINCT FROM
                v.price_source_delta_seconds

            OR

            e.expected_valuation_status
                IS DISTINCT FROM
                v.valuation_status
        """
    ).fetchone()[0]

    print(
        "Price/status linkage mismatches:",
        result,
    )

    if result != 0:
        fail(
            "Native ETH valuation does not "
            "match Silver price data"
        )


def check_value_formula(
    connection,
):
    section(
        "NATIVE ETH USD FORMULA CHECK"
    )

    formula_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations

            WHERE
                value_usd
                    IS DISTINCT FROM

                    CASE
                        WHEN
                            source_price_status
                                = 'AVAILABLE'

                            AND

                            daily_price_usd
                                IS NOT NULL

                            AND

                            value_eth_decimal
                                IS NOT NULL

                        THEN
                            CAST(
                                CAST(
                                    value_eth_decimal
                                    AS DOUBLE
                                )
                                *
                                CAST(
                                    daily_price_usd
                                    AS DOUBLE
                                )
                                AS DECIMAL(38,8)
                            )

                        ELSE
                            NULL
                    END
            """
        ).fetchone()[0]
    )

    invalid_valued = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations

            WHERE
                valuation_status = 'VALUED'

                AND (
                    daily_price_usd IS NULL

                    OR

                    daily_price_usd <= 0

                    OR

                    value_eth_decimal IS NULL

                    OR

                    value_eth_decimal <= 0

                    OR

                    value_usd IS NULL

                    OR

                    value_usd < 0
                )
            """
        ).fetchone()[0]
    )

    invalid_unvalued = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations

            WHERE
                valuation_status
                    != 'VALUED'

                AND

                value_usd IS NOT NULL
            """
        ).fetchone()[0]
    )

    unexpected_status = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations

            WHERE
                valuation_status NOT IN (
                    'VALUED',
                    'PRICE_NOT_FOUND',
                    'PRICE_UNAVAILABLE',
                    'PRICE_DATA_INVALID'
                )

                OR

                valuation_status IS NULL
            """
        ).fetchone()[0]
    )

    print(
        "USD formula mismatches:",
        formula_mismatches,
    )

    print(
        "Invalid VALUED rows:",
        invalid_valued,
    )

    print(
        "Invalid unvalued rows:",
        invalid_unvalued,
    )

    print(
        "Unexpected valuation statuses:",
        unexpected_status,
    )

    if formula_mismatches != 0:
        fail(
            "Native ETH USD formula mismatch"
        )

    if invalid_valued != 0:
        fail(
            "Invalid VALUED native ETH rows"
        )

    if invalid_unvalued != 0:
        fail(
            "Unvalued rows contain USD value"
        )

    if unexpected_status != 0:
        fail(
            "Unexpected valuation status"
        )


def check_wallet_daily_usd(
    connection,
):
    section(
        "WALLET DAILY USD AGGREGATE CHECK"
    )

    mismatches = (
        connection.execute(
            """
            WITH expected AS (
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

                                    AND

                                    value_usd IS NULL

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
                                WHEN direction
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
                                    direction
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
                            WHEN
                                valuation_status = 'VALUED'
                            THEN 1
                        END
                    ) AS valued_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status != 'VALUED'
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
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.wallet_daily_native_eth_usd_flows
                AS g

                USING (
                    activity_date,
                    chain_id,
                    organization_id,
                    wallet_id
                )

            WHERE
                e.activity_date IS NULL

                OR

                g.activity_date IS NULL

                OR

                e.inflow_eth
                    IS DISTINCT FROM
                    g.inflow_eth

                OR

                e.outflow_eth
                    IS DISTINCT FROM
                    g.outflow_eth

                OR

                e.net_flow_eth
                    IS DISTINCT FROM
                    g.net_flow_eth

                OR

                e.inflow_usd
                    IS DISTINCT FROM
                    g.inflow_usd

                OR

                e.outflow_usd
                    IS DISTINCT FROM
                    g.outflow_usd

                OR

                e.net_flow_usd
                    IS DISTINCT FROM
                    g.net_flow_usd

                OR

                e.event_count
                    IS DISTINCT FROM
                    g.event_count

                OR

                e.valued_event_count
                    IS DISTINCT FROM
                    g.valued_event_count

                OR

                e.unvalued_event_count
                    IS DISTINCT FROM
                    g.unvalued_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Wallet daily USD mismatches:",
        mismatches,
    )

    if mismatches != 0:
        fail(
            "Wallet daily native ETH USD "
            "aggregates do not reconcile"
        )


def check_organization_daily_usd(
    connection,
):
    section(
        "ORGANIZATION DAILY USD AGGREGATE CHECK"
    )

    mismatches = (
        connection.execute(
            """
            WITH expected AS (
                SELECT
                    valuation_date
                        AS activity_date,

                    chain_id,
                    organization_id,

                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'IN'
                            THEN value_eth_decimal
                            ELSE 0
                        END
                    ) AS inflow_eth,

                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'OUT'
                            THEN value_eth_decimal
                            ELSE 0
                        END
                    ) AS outflow_eth,

                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'INTERNAL'
                            THEN value_eth_decimal
                            ELSE 0
                        END
                    ) AS internal_eth,

                    SUM(
                        CASE
                            WHEN
                                organization_direction = 'IN'
                            THEN value_eth_decimal

                            WHEN
                                organization_direction = 'OUT'
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
                                    organization_direction = 'INTERNAL'
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
                                    organization_direction = 'INTERNAL'

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
                                        organization_direction = 'INTERNAL'
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
                            WHEN
                                valuation_status = 'VALUED'
                            THEN 1
                        END
                    ) AS valued_event_count,

                    COUNT(
                        CASE
                            WHEN
                                valuation_status != 'VALUED'
                            THEN 1
                        END
                    ) AS unvalued_event_count

                FROM
                    gold.organization_native_eth_valuations

                GROUP BY
                    valuation_date,
                    chain_id,
                    organization_id
            )

            SELECT COUNT(*)

            FROM expected AS e

            FULL OUTER JOIN
                gold.organization_daily_native_eth_usd_flows
                AS g

                USING (
                    activity_date,
                    chain_id,
                    organization_id
                )

            WHERE
                e.activity_date IS NULL

                OR

                g.activity_date IS NULL

                OR

                e.inflow_eth
                    IS DISTINCT FROM
                    g.inflow_eth

                OR

                e.outflow_eth
                    IS DISTINCT FROM
                    g.outflow_eth

                OR

                e.internal_eth
                    IS DISTINCT FROM
                    g.internal_eth

                OR

                e.net_flow_eth
                    IS DISTINCT FROM
                    g.net_flow_eth

                OR

                e.inflow_usd
                    IS DISTINCT FROM
                    g.inflow_usd

                OR

                e.outflow_usd
                    IS DISTINCT FROM
                    g.outflow_usd

                OR

                e.internal_usd
                    IS DISTINCT FROM
                    g.internal_usd

                OR

                e.net_flow_usd
                    IS DISTINCT FROM
                    g.net_flow_usd

                OR

                e.event_count
                    IS DISTINCT FROM
                    g.event_count

                OR

                e.valued_event_count
                    IS DISTINCT FROM
                    g.valued_event_count

                OR

                e.unvalued_event_count
                    IS DISTINCT FROM
                    g.unvalued_event_count
            """
        ).fetchone()[0]
    )

    print(
        "Organization daily USD mismatches:",
        mismatches,
    )

    if mismatches != 0:
        fail(
            "Organization daily native ETH "
            "USD aggregates do not reconcile"
        )


def check_large_transfers(
    connection,
    threshold,
):
    section(
        "NATIVE ETH LARGE TRANSFER CHECK"
    )

    duplicate_events = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    native_event_id

                FROM
                    gold.organization_large_native_eth_transfers

                GROUP BY
                    native_event_id

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )

    expected_count = (
        connection.execute(
            """
            SELECT COUNT(*)

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
            [threshold],
        ).fetchone()[0]
    )

    actual_count = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_native_eth_transfers
            """
        ).fetchone()[0]
    )

    missing_events = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_native_eth_valuations
                AS v

            LEFT JOIN
                gold.organization_large_native_eth_transfers
                AS l

                ON
                    v.native_event_id
                        = l.native_event_id

            WHERE
                v.valuation_status = 'VALUED'

                AND

                v.value_usd >= CAST(
                    ?
                    AS DECIMAL(38,8)
                )

                AND

                l.native_event_id IS NULL
            """,
            [threshold],
        ).fetchone()[0]
    )

    unexpected_events = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_native_eth_transfers
                AS l

            LEFT JOIN
                gold.organization_native_eth_valuations
                AS v

                ON
                    l.native_event_id
                        = v.native_event_id

            WHERE
                v.native_event_id IS NULL

                OR

                v.valuation_status != 'VALUED'

                OR

                v.value_usd < CAST(
                    ?
                    AS DECIMAL(38,8)
                )
            """,
            [threshold],
        ).fetchone()[0]
    )

    threshold_mismatches = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_native_eth_transfers

            WHERE
                threshold_usd
                    IS DISTINCT FROM

                    CAST(
                        ?
                        AS DECIMAL(38,8)
                    )
            """,
            [threshold],
        ).fetchone()[0]
    )

    invalid_flags = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM
                gold.organization_large_native_eth_transfers

            WHERE
                large_transfer_flag
                    IS DISTINCT FROM TRUE
            """
        ).fetchone()[0]
    )

    print(
        "Configured threshold USD:",
        threshold,
    )

    print(
        "Expected large events:",
        expected_count,
    )

    print(
        "Actual large events:",
        actual_count,
    )

    print(
        "Duplicate large events:",
        duplicate_events,
    )

    print(
        "Missing large events:",
        missing_events,
    )

    print(
        "Unexpected large events:",
        unexpected_events,
    )

    print(
        "Threshold mismatches:",
        threshold_mismatches,
    )

    print(
        "Invalid flags:",
        invalid_flags,
    )

    if duplicate_events != 0:
        fail(
            "Duplicate native ETH large events"
        )

    if expected_count != actual_count:
        fail(
            "Large transfer count mismatch"
        )

    if missing_events != 0:
        fail(
            "Expected native ETH large "
            "events are missing"
        )

    if unexpected_events != 0:
        fail(
            "Unexpected native ETH large "
            "events exist"
        )

    if threshold_mismatches != 0:
        fail(
            "Stored native ETH threshold "
            "does not match config"
        )

    if invalid_flags != 0:
        fail(
            "Invalid native ETH large "
            "transfer flags"
        )


def print_summary(
    connection,
):
    section(
        "NATIVE ETH USD SUMMARY"
    )

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

    print(
        "Valuation status:"
    )

    for row in rows:
        print(
            " ",
            row[0],
            "| events:",
            row[1],
        )

    print()
    print(
        "Large transfers:"
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


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB not found: "
            f"{DATABASE_PATH}"
        )

    threshold = load_threshold()

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

        check_wallet_valuations(
            connection
        )

        check_organization_valuations(
            connection
        )

        check_price_linkage(
            connection
        )

        check_value_formula(
            connection
        )

        check_wallet_daily_usd(
            connection
        )

        check_organization_daily_usd(
            connection
        )

        check_large_transfers(
            connection,
            threshold,
        )

        print_summary(
            connection
        )

        print()
        print("=" * 100)
        print(
            "GOLD NATIVE ETH USD "
            "VALIDATION PASSED"
        )
        print("=" * 100)

    finally:
        connection.close()


if __name__ == "__main__":
    main()