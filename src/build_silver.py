import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb


CHAIN_ID = 1

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)

SILVER_DB_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)

INGESTION_TIMESTAMP_PATTERN = re.compile(
    r"_(\d{8}T\d{6}Z)\.json$"
)


DATASETS = {
    "transactions": {
        "file_prefix": "txlist",
        "stable_fields": (
            "hash",
        ),
    },

    "erc20_transfers": {
        "file_prefix": "tokentx",
        "stable_fields": (
            "hash",
            "transactionIndex",
            "contractAddress",
            "from",
            "to",
            "value",
        ),
    },

    "internal_transactions": {
        "file_prefix": "txlistinternal",
        "stable_fields": (
            "hash",
            "traceId",
            "from",
            "to",
            "value",
            "type",
            "contractAddress",
            "input",
        ),
    },
}


LOWERCASE_SIGNATURE_FIELDS = {
    "hash",
    "from",
    "to",
    "contractAddress",
}


def clean_text(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    return text


def normalize_address(value):
    value = clean_text(value)

    if value is None:
        return None

    return value.lower()


def normalize_hex(value):
    value = clean_text(value)

    if value is None:
        return None

    return value.lower()


def parse_int(value):
    value = clean_text(value)

    if value is None:
        return None

    return int(value)


def parse_bool_flag(value):
    value = clean_text(value)

    if value == "1":
        return True

    if value == "0":
        return False

    return None


def parse_block_timestamp(value):
    timestamp = parse_int(value)

    if timestamp is None:
        return None

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


def parse_ingested_at(raw_file):
    match = INGESTION_TIMESTAMP_PATTERN.search(
        raw_file.name
    )

    if match is None:
        raise ValueError(
            "Could not read ingestion timestamp "
            f"from filename: {raw_file}"
        )

    return datetime.strptime(
        match.group(1),
        "%Y%m%dT%H%M%SZ",
    ).replace(
        tzinfo=timezone.utc
    )


def normalize_signature_value(
    field,
    value,
):
    if (
        field in LOWERCASE_SIGNATURE_FIELDS
        and isinstance(value, str)
    ):
        return value.lower()

    return value


def make_signature(
    record,
    fields,
):
    return tuple(
        normalize_signature_value(
            field,
            record.get(field),
        )
        for field in fields
    )


def make_event_id(
    dataset_name,
    treasury_address,
    signature,
):
    payload = json.dumps(
        [
            dataset_name,
            CHAIN_ID,
            treasury_address,
            *signature,
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def scale_integer_string(
    raw_value,
    decimals,
):
    raw_value = clean_text(raw_value)

    if raw_value is None:
        return None

    decimals = int(decimals)

    if decimals < 0:
        raise ValueError(
            "Decimals cannot be negative"
        )

    negative = raw_value.startswith("-")

    if negative:
        raw_value = raw_value[1:]

    if not raw_value.isdigit():
        raise ValueError(
            f"Expected integer value, got: {raw_value}"
        )

    digits = raw_value.lstrip("0") or "0"

    if decimals == 0:
        result = digits

    else:
        padded = digits.zfill(
            decimals + 1
        )

        whole_part = padded[:-decimals]

        fractional_part = (
            padded[-decimals:]
            .rstrip("0")
        )

        if fractional_part:
            result = (
                f"{whole_part}."
                f"{fractional_part}"
            )

        else:
            result = whole_part

    if negative and result != "0":
        result = "-" + result

    return result


def to_decimal_38_18_or_none(
    exact_amount,
):
    if exact_amount is None:
        return None

    unsigned = exact_amount.lstrip("-")

    if "." in unsigned:
        whole_part, fractional_part = (
            unsigned.split(".", 1)
        )
    else:
        whole_part = unsigned
        fractional_part = ""

    integer_digits = len(
        whole_part.lstrip("0")
    )

    if integer_digits == 0:
        integer_digits = 1

    if integer_digits > 20:
        return None

    if len(fractional_part) > 18:
        return None

    return Decimal(exact_amount)


def require_decimal_38_18(
    exact_amount,
    field_name,
):
    value = to_decimal_38_18_or_none(
        exact_amount
    )

    if (
        exact_amount is not None
        and value is None
    ):
        raise ValueError(
            f"{field_name} cannot fit into "
            "DECIMAL(38,18): "
            f"{exact_amount}"
        )

    return value


def classify_direction(
    from_address,
    to_address,
    treasury_address,
):
    if (
        from_address == treasury_address
        and to_address == treasury_address
    ):
        return "SELF"

    if from_address == treasury_address:
        return "OUT"

    if to_address == treasury_address:
        return "IN"

    return "OTHER"


def classify_transaction_direction(
    from_address,
    to_address,
    contract_address,
    treasury_address,
):
    if (
        to_address is None
        and contract_address
        == treasury_address
    ):
        return "CREATE"

    return classify_direction(
        from_address,
        to_address,
        treasury_address,
    )


def load_canonical_records(
    dataset_name,
    treasury_address,
):
    config = DATASETS[dataset_name]

    dataset_dir = (
        RAW_ROOT
        / dataset_name
    )

    pattern = (
        f"**/"
        f"{config['file_prefix']}_"
        f"{treasury_address}_*.json"
    )

    raw_files = sorted(
        dataset_dir.glob(pattern)
    )

    if not raw_files:
        raise FileNotFoundError(
            "No Bronze files found for "
            f"{dataset_name} "
            f"and address "
            f"{treasury_address}"
        )

    canonical_records = {}

    raw_record_count = 0


    for raw_file in raw_files:
        ingested_at = parse_ingested_at(
            raw_file
        )

        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            raise ValueError(
                "Expected result to be a list "
                f"in {raw_file}"
            )

        raw_record_count += len(result)


        signatures = [
            make_signature(
                record,
                config["stable_fields"],
            )
            for record in result
        ]


        signature_counts = Counter(
            signatures
        )

        repeated_signatures = [
            signature
            for signature, count
            in signature_counts.items()
            if count > 1
        ]


        if repeated_signatures:
            raise RuntimeError(
                "Data quality check failed. "
                "The same Silver deduplication "
                "signature appeared more than "
                "once inside one Bronze file.\n"
                f"Dataset: {dataset_name}\n"
                f"File: {raw_file}\n"
                f"First repeated signature: "
                f"{repeated_signatures[0]}"
            )


        for record, signature in zip(
            result,
            signatures,
        ):
            existing = (
                canonical_records.get(
                    signature
                )
            )

            if (
                existing is None
                or ingested_at
                > existing["ingested_at"]
            ):
                canonical_records[
                    signature
                ] = {
                    "record": record,
                    "signature": signature,
                    "source_file": str(
                        raw_file
                    ),
                    "ingested_at": (
                        ingested_at
                    ),
                }


    stats = {
        "raw_files": len(raw_files),
        "raw_records": raw_record_count,
        "canonical_records": len(
            canonical_records
        ),
        "duplicates_removed": (
            raw_record_count
            - len(canonical_records)
        ),
    }

    return (
        list(
            canonical_records.values()
        ),
        stats,
    )


def normalize_transactions(
    items,
    treasury_address,
):
    rows = []

    for item in items:
        record = item["record"]

        transaction_hash = normalize_hex(
            record.get("hash")
        )

        from_address = normalize_address(
            record.get("from")
        )

        to_address = normalize_address(
            record.get("to")
        )

        contract_address = normalize_address(
            record.get(
                "contractAddress"
            )
        )

        value_wei = (
            clean_text(
                record.get("value")
            )
            or "0"
        )

        eth_value_exact = (
            scale_integer_string(
                value_wei,
                18,
            )
        )

        eth_value = require_decimal_38_18(
            eth_value_exact,
            "eth_value",
        )

        gas_used = parse_int(
            record.get("gasUsed")
        )

        gas_price_wei = parse_int(
            record.get("gasPrice")
        )

        gas_cost_eth = None

        if (
            gas_used is not None
            and gas_price_wei is not None
        ):
            gas_cost_wei = (
                gas_used
                * gas_price_wei
            )

            gas_cost_exact = (
                scale_integer_string(
                    str(gas_cost_wei),
                    18,
                )
            )

            gas_cost_eth = (
                require_decimal_38_18(
                    gas_cost_exact,
                    "gas_cost_eth",
                )
            )


        rows.append(
            (
                CHAIN_ID,
                treasury_address,
                transaction_hash,
                parse_int(
                    record.get(
                        "blockNumber"
                    )
                ),
                parse_block_timestamp(
                    record.get(
                        "timeStamp"
                    )
                ),
                parse_int(
                    record.get(
                        "transactionIndex"
                    )
                ),
                from_address,
                to_address,
                classify_transaction_direction(
                    from_address,
                    to_address,
                    contract_address,
                    treasury_address,
                ),
                value_wei,
                eth_value,
                parse_int(
                    record.get("gas")
                ),
                gas_price_wei,
                gas_used,
                gas_cost_eth,
                parse_bool_flag(
                    record.get("isError")
                ),
                parse_int(
                    record.get(
                        "txreceipt_status"
                    )
                ),
                clean_text(
                    record.get("methodId")
                ),
                clean_text(
                    record.get(
                        "functionName"
                    )
                ),
                clean_text(
                    record.get("input")
                ),
                contract_address,
                parse_int(
                    record.get(
                        "confirmations"
                    )
                ),
                item["source_file"],
                item["ingested_at"],
            )
        )


    rows.sort(
        key=lambda row: (
            row[3],
            row[5] or -1,
            row[2],
        )
    )

    return rows


def normalize_erc20_transfers(
    items,
    treasury_address,
):
    rows = []

    for item in items:
        record = item["record"]

        from_address = normalize_address(
            record.get("from")
        )

        to_address = normalize_address(
            record.get("to")
        )

        token_decimals = parse_int(
            record.get("tokenDecimal")
        )

        raw_value = (
            clean_text(
                record.get("value")
            )
            or "0"
        )

        amount_exact = (
            scale_integer_string(
                raw_value,
                token_decimals,
            )
        )

        amount_decimal = (
            to_decimal_38_18_or_none(
                amount_exact
            )
        )

        transfer_id = make_event_id(
            "erc20_transfers",
            treasury_address,
            item["signature"],
        )


        rows.append(
            (
                transfer_id,
                CHAIN_ID,
                treasury_address,
                normalize_hex(
                    record.get("hash")
                ),
                parse_int(
                    record.get(
                        "blockNumber"
                    )
                ),
                parse_block_timestamp(
                    record.get(
                        "timeStamp"
                    )
                ),
                parse_int(
                    record.get(
                        "transactionIndex"
                    )
                ),
                from_address,
                to_address,
                classify_direction(
                    from_address,
                    to_address,
                    treasury_address,
                ),
                normalize_address(
                    record.get(
                        "contractAddress"
                    )
                ),
                clean_text(
                    record.get("tokenName")
                ),
                clean_text(
                    record.get(
                        "tokenSymbol"
                    )
                ),
                token_decimals,
                raw_value,
                amount_exact,
                amount_decimal,
                clean_text(
                    record.get("methodId")
                ),
                clean_text(
                    record.get(
                        "functionName"
                    )
                ),
                parse_int(
                    record.get(
                        "statusRep"
                    )
                ),
                parse_int(
                    record.get(
                        "confirmations"
                    )
                ),
                item["source_file"],
                item["ingested_at"],
            )
        )


    rows.sort(
        key=lambda row: (
            row[4],
            row[6] or -1,
            row[0],
        )
    )

    return rows


def normalize_internal_transactions(
    items,
    treasury_address,
):
    rows = []

    for item in items:
        record = item["record"]

        from_address = normalize_address(
            record.get("from")
        )

        to_address = normalize_address(
            record.get("to")
        )

        value_wei = (
            clean_text(
                record.get("value")
            )
            or "0"
        )

        eth_value_exact = (
            scale_integer_string(
                value_wei,
                18,
            )
        )

        eth_value = require_decimal_38_18(
            eth_value_exact,
            "internal eth_value",
        )

        internal_event_id = (
            make_event_id(
                "internal_transactions",
                treasury_address,
                item["signature"],
            )
        )


        rows.append(
            (
                internal_event_id,
                CHAIN_ID,
                treasury_address,
                normalize_hex(
                    record.get("hash")
                ),
                parse_int(
                    record.get(
                        "blockNumber"
                    )
                ),
                parse_block_timestamp(
                    record.get(
                        "timeStamp"
                    )
                ),
                parse_int(
                    record.get(
                        "transactionIndex"
                    )
                ),
                clean_text(
                    record.get("traceId")
                ),
                from_address,
                to_address,
                classify_direction(
                    from_address,
                    to_address,
                    treasury_address,
                ),
                value_wei,
                eth_value,
                clean_text(
                    record.get("type")
                ),
                normalize_address(
                    record.get(
                        "contractAddress"
                    )
                ),
                clean_text(
                    record.get("input")
                ),
                parse_int(
                    record.get("gas")
                ),
                parse_int(
                    record.get("gasUsed")
                ),
                parse_bool_flag(
                    record.get("isError")
                ),
                clean_text(
                    record.get("errCode")
                ),
                item["source_file"],
                item["ingested_at"],
            )
        )


    rows.sort(
        key=lambda row: (
            row[4],
            row[6] or -1,
            row[0],
        )
    )

    return rows


def insert_rows(
    connection,
    table_name,
    rows,
):
    if not rows:
        return

    placeholders = ", ".join(
        "?"
        for _ in range(
            len(rows[0])
        )
    )

    connection.executemany(
        f"""
        INSERT INTO {table_name}
        VALUES ({placeholders})
        """,
        rows,
    )


def build_database(
    transaction_rows,
    erc20_rows,
    internal_rows,
):
    SILVER_DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = duckdb.connect(
        str(SILVER_DB_PATH)
    )

    try:
        connection.execute(
            "BEGIN TRANSACTION"
        )

        connection.execute(
            """
            CREATE SCHEMA
            IF NOT EXISTS silver
            """
        )


        connection.execute(
            """
            DROP TABLE IF EXISTS
            silver.transactions
            """
        )

        connection.execute(
            """
            CREATE TABLE
            silver.transactions (
                chain_id INTEGER NOT NULL,
                treasury_address VARCHAR NOT NULL,
                transaction_hash VARCHAR NOT NULL,
                block_number BIGINT NOT NULL,
                block_timestamp TIMESTAMPTZ NOT NULL,
                transaction_index INTEGER,
                from_address VARCHAR,
                to_address VARCHAR,
                direction VARCHAR NOT NULL,
                value_wei VARCHAR NOT NULL,
                eth_value DECIMAL(38,18),
                gas BIGINT,
                gas_price_wei BIGINT,
                gas_used BIGINT,
                gas_cost_eth DECIMAL(38,18),
                is_error BOOLEAN,
                receipt_status INTEGER,
                method_id VARCHAR,
                function_name VARCHAR,
                input VARCHAR,
                contract_address VARCHAR,
                confirmations BIGINT,
                source_file VARCHAR NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL,

                PRIMARY KEY (
                    chain_id,
                    treasury_address,
                    transaction_hash
                )
            )
            """
        )


        connection.execute(
            """
            DROP TABLE IF EXISTS
            silver.erc20_transfers
            """
        )

        connection.execute(
            """
            CREATE TABLE
            silver.erc20_transfers (
                transfer_id VARCHAR PRIMARY KEY,
                chain_id INTEGER NOT NULL,
                treasury_address VARCHAR NOT NULL,
                transaction_hash VARCHAR NOT NULL,
                block_number BIGINT NOT NULL,
                block_timestamp TIMESTAMPTZ NOT NULL,
                transaction_index INTEGER,
                from_address VARCHAR,
                to_address VARCHAR,
                direction VARCHAR NOT NULL,
                token_contract VARCHAR NOT NULL,
                token_name VARCHAR,
                token_symbol VARCHAR,
                token_decimals INTEGER,
                value_raw VARCHAR NOT NULL,
                amount_exact VARCHAR NOT NULL,
                amount_decimal DECIMAL(38,18),
                method_id VARCHAR,
                function_name VARCHAR,
                status_rep INTEGER,
                confirmations BIGINT,
                source_file VARCHAR NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL
            )
            """
        )


        connection.execute(
            """
            DROP TABLE IF EXISTS
            silver.internal_transactions
            """
        )

        connection.execute(
            """
            CREATE TABLE
            silver.internal_transactions (
                internal_event_id VARCHAR
                    PRIMARY KEY,
                chain_id INTEGER NOT NULL,
                treasury_address VARCHAR NOT NULL,
                transaction_hash VARCHAR NOT NULL,
                block_number BIGINT NOT NULL,
                block_timestamp TIMESTAMPTZ NOT NULL,
                transaction_index INTEGER,
                trace_id VARCHAR,
                from_address VARCHAR,
                to_address VARCHAR,
                direction VARCHAR NOT NULL,
                value_wei VARCHAR NOT NULL,
                eth_value DECIMAL(38,18),
                call_type VARCHAR,
                contract_address VARCHAR,
                input VARCHAR,
                gas BIGINT,
                gas_used BIGINT,
                is_error BOOLEAN,
                error_code VARCHAR,
                source_file VARCHAR NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL
            )
            """
        )


        insert_rows(
            connection,
            "silver.transactions",
            transaction_rows,
        )

        insert_rows(
            connection,
            "silver.erc20_transfers",
            erc20_rows,
        )

        insert_rows(
            connection,
            "silver.internal_transactions",
            internal_rows,
        )


        connection.execute(
            "COMMIT"
        )


        decimal_fallback_count = (
            connection.execute(
                """
                SELECT COUNT(*)
                FROM silver.erc20_transfers
                WHERE amount_decimal IS NULL
                  AND amount_exact IS NOT NULL
                """
            ).fetchone()[0]
        )

        other_direction_count = (
            connection.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM silver.transactions
                        WHERE direction = 'OTHER'
                    )
                    +
                    (
                        SELECT COUNT(*)
                        FROM silver.erc20_transfers
                        WHERE direction = 'OTHER'
                    )
                    +
                    (
                        SELECT COUNT(*)
                        FROM silver.internal_transactions
                        WHERE direction = 'OTHER'
                    )
                """
            ).fetchone()[0]
        )

        return {
            "decimal_fallback_count":
                decimal_fallback_count,
            "other_direction_count":
                other_direction_count,
        }


    except Exception:
        connection.execute(
            "ROLLBACK"
        )

        raise


    finally:
        connection.close()


def print_dataset_summary(
    name,
    stats,
):
    print()
    print(name)
    print("-" * len(name))

    print(
        "Raw files:",
        stats["raw_files"],
    )

    print(
        "Raw records:",
        stats["raw_records"],
    )

    print(
        "Silver records:",
        stats[
            "canonical_records"
        ],
    )

    print(
        "Duplicate copies removed:",
        stats[
            "duplicates_removed"
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build normalized Silver tables "
            "from Ethereum Bronze JSON files."
        )
    )

    parser.add_argument(
        "address",
        help=(
            "Treasury Ethereum address "
            "to build Silver data for."
        ),
    )

    args = parser.parse_args()

    treasury_address = (
        normalize_address(
            args.address
        )
    )


    if (
        treasury_address is None
        or re.fullmatch(
            r"0x[a-f0-9]{40}",
            treasury_address,
        )
        is None
    ):
        parser.error(
            "address must be a valid "
            "Ethereum address"
        )


    print(
        "Building Silver for:",
        treasury_address,
    )


    transaction_items, transaction_stats = (
        load_canonical_records(
            "transactions",
            treasury_address,
        )
    )

    erc20_items, erc20_stats = (
        load_canonical_records(
            "erc20_transfers",
            treasury_address,
        )
    )

    internal_items, internal_stats = (
        load_canonical_records(
            "internal_transactions",
            treasury_address,
        )
    )


    transaction_rows = (
        normalize_transactions(
            transaction_items,
            treasury_address,
        )
    )

    erc20_rows = (
        normalize_erc20_transfers(
            erc20_items,
            treasury_address,
        )
    )

    internal_rows = (
        normalize_internal_transactions(
            internal_items,
            treasury_address,
        )
    )


    quality_summary = build_database(
        transaction_rows,
        erc20_rows,
        internal_rows,
    )


    print()
    print("=" * 80)
    print("SILVER BUILD COMPLETE")
    print("=" * 80)


    print_dataset_summary(
        "transactions",
        transaction_stats,
    )

    print_dataset_summary(
        "erc20_transfers",
        erc20_stats,
    )

    print_dataset_summary(
        "internal_transactions",
        internal_stats,
    )


    print()
    print(
        "ERC20 rows preserved only as "
        "exact text because DECIMAL(38,18) "
        "could not represent them:",
        quality_summary[
            "decimal_fallback_count"
        ],
    )

    print(
        "Rows with direction OTHER:",
        quality_summary[
            "other_direction_count"
        ],
    )

    print()
    print(
        "Database:",
        SILVER_DB_PATH,
    )


if __name__ == "__main__":
    main()