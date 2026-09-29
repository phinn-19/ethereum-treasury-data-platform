from pathlib import Path

import duckdb


SILVER_DB_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


KNOWN_WETH_TX = (
    "0xb35666a6280f0b796502afff1b4e7707"
    "24448cfde00a8da96a5b7aaaeccd8639"
)

ENDOWMENT_WALLET_ID = "endowment"

WETH_CONTRACT = (
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
)

EXPECTED_WETH_VALUE_RAW = (
    "250000000000000000000"
)


CREATE2_TX = (
    "0xafd94af14c9d5b7b77db8ed502c7ea7d"
    "141a779d54e599782f9ae3fb649b2f55"
)


def fail(message):
    raise RuntimeError(
        f"VALIDATION FAILED: {message}"
    )


def check_table_counts(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "TABLE COUNTS"
    )
    print(
        "=" * 100
    )


    tables = [
        "wallets",
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]


    for table_name in tables:
        count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM silver.{table_name}
            """
        ).fetchone()[0]

        print(
            table_name,
            ":",
            count,
        )


        if count == 0:
            fail(
                f"silver.{table_name} "
                "is empty"
            )


def check_wallet_count(
    connection,
):
    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM silver.wallets
        """
    ).fetchone()[0]


    print()
    print(
        "Monitoring wallets:",
        count,
    )


    if count != 5:
        fail(
            "Expected 5 monitored "
            f"wallets, got {count}"
        )


def check_other_directions(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "DIRECTION CHECK"
    )
    print(
        "=" * 100
    )


    tables = [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]


    for table_name in tables:
        count = connection.execute(
            f"""
            SELECT COUNT(*)

            FROM silver.{table_name}

            WHERE direction = 'OTHER'
            """
        ).fetchone()[0]


        print(
            table_name,
            "OTHER rows:",
            count,
        )


        if count != 0:
            fail(
                f"silver.{table_name} "
                f"contains {count} OTHER rows"
            )


def check_duplicate_activity_ids(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "ACTIVITY ID CHECK"
    )
    print(
        "=" * 100
    )


    tables = [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]


    for table_name in tables:
        duplicate_groups = (
            connection.execute(
                f"""
                SELECT COUNT(*)

                FROM (
                    SELECT
                        activity_id

                    FROM silver.{table_name}

                    GROUP BY
                        activity_id

                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )


        print(
            table_name,
            "duplicate activity IDs:",
            duplicate_groups,
        )


        if duplicate_groups != 0:
            fail(
                f"silver.{table_name} "
                "contains duplicate "
                "activity_id values"
            )


def check_erc20_event_identity(
    connection,
):
    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    wallet_id,
                    transaction_hash,
                    log_index

                FROM silver.erc20_transfers

                GROUP BY
                    wallet_id,
                    transaction_hash,
                    log_index

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )


    null_log_indexes = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM silver.erc20_transfers

            WHERE log_index IS NULL
            """
        ).fetchone()[0]
    )


    print()
    print(
        "=" * 100
    )
    print(
        "ERC20 EVENT IDENTITY CHECK"
    )
    print(
        "=" * 100
    )

    print(
        "Duplicate "
        "(wallet, tx, log_index) groups:",
        duplicate_groups,
    )

    print(
        "NULL log_index rows:",
        null_log_indexes,
    )


    if duplicate_groups != 0:
        fail(
            "ERC20 event identity "
            "contains duplicates"
        )


    if null_log_indexes != 0:
        fail(
            "ERC20 rows exist without "
            "log_index"
        )


def check_known_weth_regression(
    connection,
):
    rows = connection.execute(
        """
        SELECT
            log_index,
            value_raw,
            from_address,
            to_address

        FROM silver.erc20_transfers

        WHERE
            wallet_id = ?
            AND transaction_hash = ?
            AND token_contract = ?
            AND value_raw = ?

        ORDER BY
            log_index
        """,
        [
            ENDOWMENT_WALLET_ID,
            KNOWN_WETH_TX,
            WETH_CONTRACT,
            EXPECTED_WETH_VALUE_RAW,
        ],
    ).fetchall()


    print()
    print(
        "=" * 100
    )
    print(
        "KNOWN WETH REGRESSION CHECK"
    )
    print(
        "=" * 100
    )


    print(
        "Matching rows:",
        len(rows),
    )


    for row in rows:
        print(
            "  log_index:",
            row[0],
            "| value_raw:",
            row[1],
            "| from:",
            row[2],
            "| to:",
            row[3],
        )


    actual_log_indexes = [
        row[0]
        for row in rows
    ]


    expected_log_indexes = [
        13,
        14,
        15,
    ]


    if (
        actual_log_indexes
        != expected_log_indexes
    ):
        fail(
            "Known 3x250 WETH transfer "
            "was not preserved correctly. "
            f"Expected log indexes "
            f"{expected_log_indexes}, "
            f"got {actual_log_indexes}"
        )


def check_create2_regression(
    connection,
):
    rows = connection.execute(
        """
        SELECT
            wallet_id,
            transaction_hash,
            contract_address,
            call_type,
            direction

        FROM silver.internal_transactions

        WHERE
            wallet_id = ?
            AND transaction_hash = ?
        """,
        [
            ENDOWMENT_WALLET_ID,
            CREATE2_TX,
        ],
    ).fetchall()


    print()
    print(
        "=" * 100
    )
    print(
        "CREATE2 REGRESSION CHECK"
    )
    print(
        "=" * 100
    )


    for row in rows:
        print(
            "wallet_id:",
            row[0],
            "| tx:",
            row[1],
            "| contract:",
            row[2],
            "| call_type:",
            row[3],
            "| direction:",
            row[4],
        )


    if len(rows) != 1:
        fail(
            "Expected exactly one "
            "Endowment CREATE2 row, "
            f"got {len(rows)}"
        )


    row = rows[0]


    if row[3] != "create2":
        fail(
            "Known Endowment creation "
            "row is not call_type=create2"
        )


    if row[4] != "CREATE":
        fail(
            "Known Endowment creation "
            "row is not direction=CREATE"
        )


def print_direction_summary(
    connection,
):
    print()
    print(
        "=" * 100
    )
    print(
        "DIRECTION SUMMARY"
    )
    print(
        "=" * 100
    )


    for table_name in [
        "transactions",
        "erc20_transfers",
        "internal_transactions",
    ]:
        print()
        print(
            table_name
        )


        rows = connection.execute(
            f"""
            SELECT
                wallet_id,
                direction,
                COUNT(*) AS row_count

            FROM silver.{table_name}

            GROUP BY
                wallet_id,
                direction

            ORDER BY
                wallet_id,
                direction
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
            )


def main():
    if not SILVER_DB_PATH.exists():
        raise FileNotFoundError(
            "Silver database not found: "
            f"{SILVER_DB_PATH}"
        )


    connection = duckdb.connect(
        str(
            SILVER_DB_PATH
        ),
        read_only=True,
    )


    try:
        check_table_counts(
            connection
        )

        check_wallet_count(
            connection
        )

        check_other_directions(
            connection
        )

        check_duplicate_activity_ids(
            connection
        )

        check_erc20_event_identity(
            connection
        )

        check_known_weth_regression(
            connection
        )

        check_create2_regression(
            connection
        )

        print_direction_summary(
            connection
        )


        print()
        print(
            "=" * 100
        )
        print(
            "SILVER VALIDATION PASSED"
        )
        print(
            "=" * 100
        )


    finally:
        connection.close()


if __name__ == "__main__":
    main()