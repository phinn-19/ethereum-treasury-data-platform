import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb


CHAIN_ID = 1

WALLET_CONFIG_PATH = Path(
    "config",
    "wallets.json",
)

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)

RECEIPT_ROOT = (
    RAW_ROOT
    / "transaction_receipts"
)

SILVER_DB_PATH = Path(
    "data",
    "silver",
    "ethereum_treasury.duckdb",
)


TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa"
    "952ba7f163c4a11628f55a4df523b3ef"
)


INGESTED_AT_PATTERN = re.compile(
    r"_(\d{8}T\d{6}Z)\.json$"
)


DATASETS = {
    "transactions": "txlist",
    "erc20_transfers": "tokentx",
    "internal_transactions":
        "txlistinternal",
}


def normalize_address(value):
    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return value.lower()


def normalize_hex(value):
    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return value.lower()


def parse_int(value):
    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return int(value)


def parse_hex_or_int(value):
    if value is None:
        return None

    if isinstance(
        value,
        int,
    ):
        return value

    value = str(
        value
    ).strip().lower()

    if not value:
        return None

    if value.startswith(
        "0x"
    ):
        return int(
            value,
            16,
        )

    return int(value)


def parse_bool_flag(value):
    if value is None:
        return None

    value = str(
        value
    ).strip().lower()

    if value in {
        "1",
        "true",
        "yes",
    }:
        return True

    if value in {
        "0",
        "false",
        "no",
    }:
        return False

    return None


def parse_unix_timestamp(
    value,
):
    seconds = parse_int(
        value
    )

    if seconds is None:
        return None

    return datetime.fromtimestamp(
        seconds,
        tz=timezone.utc,
    )


def parse_ingested_at(
    path,
):
    match = (
        INGESTED_AT_PATTERN.search(
            path.name
        )
    )

    if match is None:
        raise ValueError(
            "Could not parse "
            "ingestion timestamp "
            f"from {path}"
        )

    return datetime.strptime(
        match.group(1),
        "%Y%m%dT%H%M%SZ",
    ).replace(
        tzinfo=timezone.utc
    )


def stable_id(*parts):
    text = "|".join(
        ""
        if part is None
        else str(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()


def exact_amount_string(
    value_raw,
    decimals,
):
    if value_raw is None:
        return None

    value_raw = str(
        value_raw
    ).strip()

    if not value_raw:
        return None

    decimals = int(
        decimals
    )

    if decimals < 0:
        raise ValueError(
            "decimals cannot "
            "be negative"
        )

    negative = (
        value_raw.startswith(
            "-"
        )
    )

    digits = (
        value_raw[1:]
        if negative
        else value_raw
    )

    if not digits.isdigit():
        raise ValueError(
            "Invalid integer "
            f"amount: {value_raw}"
        )

    digits = (
        digits.lstrip("0")
        or "0"
    )

    if decimals == 0:
        result = digits

    else:
        digits = digits.zfill(
            decimals + 1
        )

        integer_part = (
            digits[:-decimals]
            or "0"
        )

        fractional_part = (
            digits[-decimals:]
        )

        result = (
            f"{integer_part}."
            f"{fractional_part}"
        )

    if (
        negative
        and result != "0"
    ):
        result = (
            f"-{result}"
        )

    return result


def decimal_38_18_or_none(
    amount_exact,
):
    if amount_exact is None:
        return None

    try:
        value = Decimal(
            amount_exact
        )

    except InvalidOperation:
        return None


    _, digits, exponent = (
        value.as_tuple()
    )


    if exponent >= 0:
        integer_digits = (
            len(digits)
            + exponent
        )

        fractional_digits = 0

    else:
        fractional_digits = (
            -exponent
        )

        integer_digits = max(
            len(digits)
            - fractional_digits,
            0,
        )


    if (
        fractional_digits > 18
        or integer_digits > 20
    ):
        return None

    return value


def load_wallets():
    if (
        not WALLET_CONFIG_PATH
        .exists()
    ):
        raise FileNotFoundError(
            "Wallet config "
            "not found: "
            f"{WALLET_CONFIG_PATH}"
        )


    payload = json.loads(
        WALLET_CONFIG_PATH
        .read_text(
            encoding="utf-8"
        )
    )


    if not isinstance(
        payload,
        list,
    ):
        raise ValueError(
            "wallets.json must "
            "contain a JSON list"
        )


    wallets = []

    seen_ids = set()

    seen_addresses = set()


    for raw_wallet in payload:
        if not raw_wallet.get(
            "monitoring_enabled",
            False,
        ):
            continue


        wallet = dict(
            raw_wallet
        )


        wallet[
            "address"
        ] = normalize_address(
            wallet["address"]
        )


        wallet[
            "chain_id"
        ] = int(
            wallet.get(
                "chain_id",
                CHAIN_ID,
            )
        )


        if (
            wallet["chain_id"]
            != CHAIN_ID
        ):
            raise ValueError(
                "This V1 builder "
                f"supports chain_id="
                f"{CHAIN_ID}, got "
                f"{wallet['chain_id']} "
                "for "
                f"{wallet['wallet_id']}"
            )


        if (
            wallet["wallet_id"]
            in seen_ids
        ):
            raise ValueError(
                "Duplicate wallet_id: "
                f"{wallet['wallet_id']}"
            )


        if (
            wallet["address"]
            in seen_addresses
        ):
            raise ValueError(
                "Duplicate wallet "
                "address: "
                f"{wallet['address']}"
            )


        seen_ids.add(
            wallet["wallet_id"]
        )

        seen_addresses.add(
            wallet["address"]
        )

        wallets.append(
            wallet
        )


    if not wallets:
        raise ValueError(
            "No monitoring-enabled "
            "wallets found"
        )


    return wallets


def load_dataset_entries(
    dataset_name,
    address,
):
    prefix = DATASETS[
        dataset_name
    ]

    pattern = (
        f"**/"
        f"{prefix}_"
        f"{address}_*.json"
    )


    raw_files = sorted(
        (
            RAW_ROOT
            / dataset_name
        ).glob(
            pattern
        )
    )


    if not raw_files:
        raise FileNotFoundError(
            "No Bronze files "
            "found for "
            f"{dataset_name} / "
            f"{address}"
        )


    entries = []


    for raw_file in raw_files:
        ingested_at = (
            parse_ingested_at(
                raw_file
            )
        )


        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )


        result = payload.get(
            "result"
        )


        if not isinstance(
            result,
            list,
        ):
            raise ValueError(
                "Expected result "
                "list in "
                f"{raw_file}"
            )


        for record in result:
            entries.append(
                {
                    "record":
                        record,
                    "ingested_at":
                        ingested_at,
                    "source_file":
                        str(
                            raw_file
                        ),
                }
            )


    return entries


def choose_latest_by_key(
    entries,
    key_function,
):
    latest = {}


    for entry in entries:
        key = key_function(
            entry["record"]
        )


        current = latest.get(
            key
        )


        if (
            current is None
            or entry[
                "ingested_at"
            ]
            > current[
                "ingested_at"
            ]
        ):
            latest[
                key
            ] = entry


    return latest


def transaction_key(
    record,
):
    tx_hash = normalize_hex(
        record.get("hash")
    )


    if not tx_hash:
        raise ValueError(
            "Transaction row "
            "missing hash"
        )


    return tx_hash


def internal_key(
    record,
):
    tx_hash = normalize_hex(
        record.get("hash")
    )


    if not tx_hash:
        raise ValueError(
            "Internal transaction "
            "row missing hash"
        )


    return (
        tx_hash,

        str(
            record.get(
                "traceId",
                "",
            )
        ),

        normalize_address(
            record.get("from")
        ),

        normalize_address(
            record.get("to")
        ),

        str(
            record.get(
                "value",
                "",
            )
        ),

        str(
            record.get(
                "type",
                "",
            )
        ).lower(),

        normalize_address(
            record.get(
                "contractAddress"
            )
        ),

        normalize_hex(
            record.get(
                "input"
            )
        ),
    )


def classify_direction(
    wallet_address,
    from_address,
    to_address,
):
    if (
        from_address
        == wallet_address
        and to_address
        == wallet_address
    ):
        return "SELF"


    if (
        from_address
        == wallet_address
    ):
        return "OUT"


    if (
        to_address
        == wallet_address
    ):
        return "IN"


    return "OTHER"


def classify_transaction_direction(
    wallet_address,
    from_address,
    to_address,
    contract_address,
):
    if (
        to_address is None
        and contract_address
        == wallet_address
    ):
        return "CREATE"


    return classify_direction(
        wallet_address,
        from_address,
        to_address,
    )

def classify_internal_direction(
    wallet_address,
    from_address,
    to_address,
    contract_address,
    call_type,
):
    if (
        contract_address
        == wallet_address
        and call_type
        in {
            "create",
            "create2",
        }
    ):
        return "CREATE"

    return classify_direction(
        wallet_address,
        from_address,
        to_address,
    )

def build_receipt_index():
    receipt_index = {}


    if not RECEIPT_ROOT.exists():
        return receipt_index


    for path in (
        RECEIPT_ROOT.glob(
            "**/receipt_*.json"
        )
    ):
        tx_hash = (
            path.stem[
                len("receipt_"):
            ]
            .lower()
        )


        if (
            tx_hash
            in receipt_index
            and receipt_index[
                tx_hash
            ] != path
        ):
            raise RuntimeError(
                "Multiple receipt "
                "files found for "
                f"{tx_hash}: "
                f"{receipt_index[tx_hash]} "
                f"and {path}"
            )


        receipt_index[
            tx_hash
        ] = path


    return receipt_index


def load_receipt(
    tx_hash,
    receipt_index,
    receipt_cache,
):
    if tx_hash in receipt_cache:
        return receipt_cache[
            tx_hash
        ]


    receipt_path = (
        receipt_index.get(
            tx_hash
        )
    )


    if receipt_path is None:
        raise FileNotFoundError(
            "Missing receipt for "
            f"{tx_hash}"
        )


    payload = json.loads(
        receipt_path.read_text(
            encoding="utf-8"
        )
    )


    receipt = payload.get(
        "result"
    )


    if not isinstance(
        receipt,
        dict,
    ):
        raise ValueError(
            "Expected receipt "
            "object in "
            f"{receipt_path}"
        )


    if (
        normalize_hex(
            receipt.get(
                "transactionHash"
            )
        )
        != tx_hash
    ):
        raise ValueError(
            "Receipt hash mismatch "
            f"in {receipt_path}"
        )


    result = {
        "receipt": receipt,
        "source_file":
            str(receipt_path),
    }


    receipt_cache[
        tx_hash
    ] = result


    return result


def decode_topic_address(
    topic,
):
    topic = normalize_hex(
        topic
    )


    if (
        topic is None
        or not topic.startswith(
            "0x"
        )
        or len(topic) != 66
    ):
        raise ValueError(
            "Invalid address "
            f"topic: {topic}"
        )


    return (
        "0x"
        + topic[-40:]
    )


def decode_erc20_transfer_log(
    log,
):
    topics = log.get(
        "topics"
    )


    if (
        not isinstance(
            topics,
            list,
        )
        or len(topics) != 3
    ):
        return None


    if (
        normalize_hex(
            topics[0]
        )
        != TRANSFER_TOPIC
    ):
        return None


    data = normalize_hex(
        log.get("data")
    )


    if (
        data is None
        or not data.startswith(
            "0x"
        )
        or len(data) != 66
    ):
        return None


    return {
        "token_contract":
            normalize_address(
                log.get(
                    "address"
                )
            ),

        "from_address":
            decode_topic_address(
                topics[1]
            ),

        "to_address":
            decode_topic_address(
                topics[2]
            ),

        "value_raw":
            str(
                int(
                    data,
                    16,
                )
            ),

        "log_index":
            parse_hex_or_int(
                log.get(
                    "logIndex"
                )
            ),

        "transaction_index":
            parse_hex_or_int(
                log.get(
                    "transactionIndex"
                )
            ),

        "block_number":
            parse_hex_or_int(
                log.get(
                    "blockNumber"
                )
            ),
    }


def build_wallet_rows(
    wallets,
):
    return [
        (
            wallet[
                "organization_id"
            ],

            wallet[
                "organization_name"
            ],

            wallet[
                "wallet_id"
            ],

            wallet[
                "wallet_name"
            ],

            wallet[
                "wallet_role"
            ],

            wallet[
                "address"
            ],

            wallet[
                "chain_id"
            ],

            bool(
                wallet[
                    "monitoring_enabled"
                ]
            ),

            wallet.get(
                "source_reference"
            ),
        )
        for wallet in wallets
    ]


def build_transaction_rows(
    wallet,
):
    entries = (
        load_dataset_entries(
            "transactions",
            wallet["address"],
        )
    )


    canonical = (
        choose_latest_by_key(
            entries,
            transaction_key,
        )
    )


    rows = []


    for tx_hash, entry in sorted(
        canonical.items()
    ):
        record = entry[
            "record"
        ]


        from_address = (
            normalize_address(
                record.get("from")
            )
        )


        to_address = (
            normalize_address(
                record.get("to")
            )
        )


        contract_address = (
            normalize_address(
                record.get(
                    "contractAddress"
                )
            )
        )


        direction = (
            classify_transaction_direction(
                wallet["address"],
                from_address,
                to_address,
                contract_address,
            )
        )


        if direction == "OTHER":
            raise RuntimeError(
                "Transaction does not "
                "involve "
                f"{wallet['wallet_id']}: "
                f"{tx_hash}"
            )


        value_raw = str(
            record.get(
                "value",
                "0",
            )
        )


        value_exact = (
            exact_amount_string(
                value_raw,
                18,
            )
        )


        gas_used = parse_int(
            record.get(
                "gasUsed"
            )
        )


        gas_price = parse_int(
            record.get(
                "gasPrice"
            )
        )


        gas_cost_raw = None


        if (
            gas_used is not None
            and gas_price is not None
        ):
            gas_cost_raw = str(
                gas_used
                * gas_price
            )


        gas_cost_exact = (
            exact_amount_string(
                gas_cost_raw,
                18,
            )
            if gas_cost_raw
            is not None
            else None
        )


        rows.append(
            (
                stable_id(
                    "transaction",
                    CHAIN_ID,
                    wallet[
                        "wallet_id"
                    ],
                    tx_hash,
                ),

                CHAIN_ID,

                wallet[
                    "organization_id"
                ],

                wallet[
                    "wallet_id"
                ],

                wallet[
                    "address"
                ],

                tx_hash,

                parse_int(
                    record.get(
                        "blockNumber"
                    )
                ),

                normalize_hex(
                    record.get(
                        "blockHash"
                    )
                ),

                parse_int(
                    record.get(
                        "transactionIndex"
                    )
                ),

                parse_unix_timestamp(
                    record.get(
                        "timeStamp"
                    )
                ),

                from_address,

                to_address,

                contract_address,

                direction,

                value_raw,

                value_exact,

                decimal_38_18_or_none(
                    value_exact
                ),

                parse_int(
                    record.get(
                        "nonce"
                    )
                ),

                parse_int(
                    record.get(
                        "gas"
                    )
                ),

                gas_price,

                gas_used,

                gas_cost_raw,

                gas_cost_exact,

                decimal_38_18_or_none(
                    gas_cost_exact
                ),

                parse_bool_flag(
                    record.get(
                        "isError"
                    )
                ),

                parse_int(
                    record.get(
                        "txreceipt_status"
                    )
                ),

                normalize_hex(
                    record.get(
                        "methodId"
                    )
                ),

                record.get(
                    "functionName"
                ),

                entry[
                    "ingested_at"
                ],

                entry[
                    "source_file"
                ],
            )
        )


    return rows


def erc20_source_signature(
    record,
):
    return (
        normalize_address(
            record.get(
                "contractAddress"
            )
        ),

        normalize_address(
            record.get("from")
        ),

        normalize_address(
            record.get("to")
        ),

        str(
            record.get(
                "value",
                "0",
            )
        ),
    )


def build_erc20_rows(
    wallet,
    receipt_index,
    receipt_cache,
):
    entries = (
        load_dataset_entries(
            "erc20_transfers",
            wallet["address"],
        )
    )


    metadata_by_tx_contract = {}

    source_signatures_by_tx = (
        defaultdict(set)
    )

    contracts_by_tx = (
        defaultdict(set)
    )


    for entry in entries:
        record = entry[
            "record"
        ]


        tx_hash = normalize_hex(
            record.get(
                "hash"
            )
        )


        token_contract = (
            normalize_address(
                record.get(
                    "contractAddress"
                )
            )
        )


        if (
            not tx_hash
            or not token_contract
        ):
            raise ValueError(
                "ERC20 Bronze row "
                "missing transaction "
                "hash or contract address"
            )


        source_signatures_by_tx[
            tx_hash
        ].add(
            erc20_source_signature(
                record
            )
        )


        contracts_by_tx[
            tx_hash
        ].add(
            token_contract
        )


        metadata_key = (
            tx_hash,
            token_contract,
        )


        current = (
            metadata_by_tx_contract
            .get(
                metadata_key
            )
        )


        if (
            current is None
            or entry[
                "ingested_at"
            ]
            > current[
                "ingested_at"
            ]
        ):
            metadata_by_tx_contract[
                metadata_key
            ] = entry


    rows = []

    seen_activity_keys = set()


    for tx_hash in sorted(
        contracts_by_tx
    ):
        receipt_entry = (
            load_receipt(
                tx_hash,
                receipt_index,
                receipt_cache,
            )
        )


        receipt = (
            receipt_entry[
                "receipt"
            ]
        )


        logs = receipt.get(
            "logs"
        )


        if not isinstance(
            logs,
            list,
        ):
            raise ValueError(
                "Receipt logs are "
                "not a list for "
                f"{tx_hash}"
            )


        receipt_signatures = set()


        for log in logs:
            transfer = (
                decode_erc20_transfer_log(
                    log
                )
            )


            if transfer is None:
                continue


            token_contract = (
                transfer[
                    "token_contract"
                ]
            )


            if (
                token_contract
                not in contracts_by_tx[
                    tx_hash
                ]
            ):
                continue


            if (
                transfer[
                    "from_address"
                ]
                != wallet[
                    "address"
                ]
                and transfer[
                    "to_address"
                ]
                != wallet[
                    "address"
                ]
            ):
                continue


            receipt_signature = (
                token_contract,

                transfer[
                    "from_address"
                ],

                transfer[
                    "to_address"
                ],

                transfer[
                    "value_raw"
                ],
            )


            receipt_signatures.add(
                receipt_signature
            )


            metadata_entry = (
                metadata_by_tx_contract[
                    (
                        tx_hash,
                        token_contract,
                    )
                ]
            )


            metadata = (
                metadata_entry[
                    "record"
                ]
            )


            decimals = parse_int(
                metadata.get(
                    "tokenDecimal"
                )
            )


            if decimals is None:
                raise ValueError(
                    "Missing token "
                    "decimals for "
                    f"{token_contract}"
                )


            log_index = (
                transfer[
                    "log_index"
                ]
            )


            if log_index is None:
                raise ValueError(
                    "Transfer log "
                    "missing logIndex "
                    f"in {tx_hash}"
                )


            activity_key = (
                wallet[
                    "wallet_id"
                ],
                tx_hash,
                log_index,
            )


            if (
                activity_key
                in seen_activity_keys
            ):
                raise RuntimeError(
                    "Duplicate ERC20 "
                    "activity identity: "
                    f"{activity_key}"
                )


            seen_activity_keys.add(
                activity_key
            )


            direction = (
                classify_direction(
                    wallet[
                        "address"
                    ],

                    transfer[
                        "from_address"
                    ],

                    transfer[
                        "to_address"
                    ],
                )
            )


            if direction == "OTHER":
                raise RuntimeError(
                    "ERC20 log does "
                    "not involve "
                    f"{wallet['wallet_id']}"
                )


            amount_exact = (
                exact_amount_string(
                    transfer[
                        "value_raw"
                    ],
                    decimals,
                )
            )


            blockchain_event_id = (
                stable_id(
                    "erc20_event",
                    CHAIN_ID,
                    tx_hash,
                    log_index,
                )
            )


            rows.append(
                (
                    stable_id(
                        "erc20_activity",

                        wallet[
                            "wallet_id"
                        ],

                        blockchain_event_id,
                    ),

                    blockchain_event_id,

                    CHAIN_ID,

                    wallet[
                        "organization_id"
                    ],

                    wallet[
                        "wallet_id"
                    ],

                    wallet[
                        "address"
                    ],

                    tx_hash,

                    log_index,

                    (
                        transfer[
                            "block_number"
                        ]
                        or parse_int(
                            metadata.get(
                                "blockNumber"
                            )
                        )
                    ),

                    normalize_hex(
                        receipt.get(
                            "blockHash"
                        )
                    ),

                    transfer[
                        "transaction_index"
                    ],

                    parse_unix_timestamp(
                        metadata.get(
                            "timeStamp"
                        )
                    ),

                    token_contract,

                    metadata.get(
                        "tokenName"
                    ),

                    metadata.get(
                        "tokenSymbol"
                    ),

                    decimals,

                    transfer[
                        "from_address"
                    ],

                    transfer[
                        "to_address"
                    ],

                    direction,

                    transfer[
                        "value_raw"
                    ],

                    amount_exact,

                    decimal_38_18_or_none(
                        amount_exact
                    ),

                    metadata_entry[
                        "ingested_at"
                    ],

                    metadata_entry[
                        "source_file"
                    ],

                    receipt_entry[
                        "source_file"
                    ],
                )
            )


        missing_in_receipt = (
            source_signatures_by_tx[
                tx_hash
            ]
            - receipt_signatures
        )


        if missing_in_receipt:
            preview = sorted(
                missing_in_receipt
            )[:3]


            raise RuntimeError(
                "ERC20 Bronze signatures "
                "were not found in "
                "receipt logs for "
                f"{wallet['wallet_id']} / "
                f"{tx_hash}. "
                f"Examples: {preview}"
            )


    return rows


def build_internal_rows(
    wallet,
):
    entries = (
        load_dataset_entries(
            "internal_transactions",
            wallet["address"],
        )
    )


    canonical = (
        choose_latest_by_key(
            entries,
            internal_key,
        )
    )


    rows = []


    for signature, entry in sorted(
        canonical.items(),
        key=lambda item:
            str(item[0]),
    ):
        record = entry[
            "record"
        ]


        tx_hash = normalize_hex(
            record.get(
                "hash"
            )
        )


        from_address = (
            normalize_address(
                record.get(
                    "from"
                )
            )
        )


        to_address = (
            normalize_address(
                record.get(
                    "to"
                )
            )
        )


        contract_address = (
            normalize_address(
                record.get(
                    "contractAddress"
                )
            )
        )


        call_type = str(
            record.get(
                "type",
                "",
            )
        ).strip().lower()


        direction = (
            classify_internal_direction(
                wallet[
                    "address"
                ],
                from_address,
                to_address,
                contract_address,
                call_type,
            )
        )


        if direction == "OTHER":
            raise RuntimeError(
                "Internal row does "
                "not involve "
                f"{wallet['wallet_id']}: "
                f"{tx_hash}"
            )


        value_raw = str(
            record.get(
                "value",
                "0",
            )
        )


        value_exact = (
            exact_amount_string(
                value_raw,
                18,
            )
        )


        rows.append(
            (
                stable_id(
                    "internal",
                    CHAIN_ID,

                    wallet[
                        "wallet_id"
                    ],

                    *signature,
                ),

                CHAIN_ID,

                wallet[
                    "organization_id"
                ],

                wallet[
                    "wallet_id"
                ],

                wallet[
                    "address"
                ],

                tx_hash,

                str(
                    record.get(
                        "traceId",
                        "",
                    )
                ),

                parse_int(
                    record.get(
                        "blockNumber"
                    )
                ),

                parse_unix_timestamp(
                    record.get(
                        "timeStamp"
                    )
                ),

                from_address,

                to_address,

                contract_address,

                call_type,

                normalize_hex(
                    record.get(
                        "input"
                    )
                ),

                direction,

                value_raw,

                value_exact,

                decimal_38_18_or_none(
                    value_exact
                ),

                parse_int(
                    record.get(
                        "gas"
                    )
                ),

                parse_int(
                    record.get(
                        "gasUsed"
                    )
                ),

                parse_bool_flag(
                    record.get(
                        "isError"
                    )
                ),

                record.get(
                    "errCode"
                ),

                entry[
                    "ingested_at"
                ],

                entry[
                    "source_file"
                ],
            )
        )


    return rows


def create_tables(
    connection,
):
    connection.execute(
        """
        CREATE SCHEMA
        IF NOT EXISTS silver
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
        DROP TABLE IF EXISTS
        silver.erc20_transfers
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
        DROP TABLE IF EXISTS
        silver.wallets
        """
    )


    connection.execute(
        """
        CREATE TABLE silver.wallets (
            organization_id VARCHAR
                NOT NULL,

            organization_name VARCHAR
                NOT NULL,

            wallet_id VARCHAR
                PRIMARY KEY,

            wallet_name VARCHAR
                NOT NULL,

            wallet_role VARCHAR
                NOT NULL,

            address VARCHAR
                NOT NULL
                UNIQUE,

            chain_id INTEGER
                NOT NULL,

            monitoring_enabled BOOLEAN
                NOT NULL,

            source_reference VARCHAR
        )
        """
    )


    connection.execute(
        """
        CREATE TABLE silver.transactions (
            activity_id VARCHAR
                PRIMARY KEY,

            chain_id INTEGER
                NOT NULL,

            organization_id VARCHAR
                NOT NULL,

            wallet_id VARCHAR
                NOT NULL,

            treasury_address VARCHAR
                NOT NULL,

            transaction_hash VARCHAR
                NOT NULL,

            block_number BIGINT,

            block_hash VARCHAR,

            transaction_index BIGINT,

            block_timestamp TIMESTAMPTZ,

            from_address VARCHAR,

            to_address VARCHAR,

            contract_address VARCHAR,

            direction VARCHAR
                NOT NULL,

            value_wei_raw VARCHAR,

            value_eth_exact VARCHAR,

            value_eth_decimal
                DECIMAL(38,18),

            nonce BIGINT,

            gas BIGINT,

            gas_price_wei BIGINT,

            gas_used BIGINT,

            gas_cost_wei_raw VARCHAR,

            gas_cost_eth_exact VARCHAR,

            gas_cost_eth_decimal
                DECIMAL(38,18),

            is_error BOOLEAN,

            receipt_status INTEGER,

            method_id VARCHAR,

            function_name VARCHAR,

            ingested_at TIMESTAMPTZ
                NOT NULL,

            source_file VARCHAR
                NOT NULL
        )
        """
    )


    connection.execute(
        """
        CREATE TABLE silver.erc20_transfers (
            activity_id VARCHAR
                PRIMARY KEY,

            blockchain_event_id VARCHAR
                NOT NULL,

            chain_id INTEGER
                NOT NULL,

            organization_id VARCHAR
                NOT NULL,

            wallet_id VARCHAR
                NOT NULL,

            treasury_address VARCHAR
                NOT NULL,

            transaction_hash VARCHAR
                NOT NULL,

            log_index BIGINT
                NOT NULL,

            block_number BIGINT,

            block_hash VARCHAR,

            transaction_index BIGINT,

            block_timestamp TIMESTAMPTZ,

            token_contract VARCHAR
                NOT NULL,

            token_name VARCHAR,

            token_symbol VARCHAR,

            token_decimals INTEGER
                NOT NULL,

            from_address VARCHAR
                NOT NULL,

            to_address VARCHAR
                NOT NULL,

            direction VARCHAR
                NOT NULL,

            value_raw VARCHAR
                NOT NULL,

            amount_exact VARCHAR
                NOT NULL,

            amount_decimal
                DECIMAL(38,18),

            tokentx_ingested_at
                TIMESTAMPTZ
                NOT NULL,

            tokentx_source_file VARCHAR
                NOT NULL,

            receipt_source_file VARCHAR
                NOT NULL,

            UNIQUE (
                wallet_id,
                transaction_hash,
                log_index
            )
        )
        """
    )


    connection.execute(
        """
        CREATE TABLE
        silver.internal_transactions (
            activity_id VARCHAR
                PRIMARY KEY,

            chain_id INTEGER
                NOT NULL,

            organization_id VARCHAR
                NOT NULL,

            wallet_id VARCHAR
                NOT NULL,

            treasury_address VARCHAR
                NOT NULL,

            transaction_hash VARCHAR
                NOT NULL,

            trace_id VARCHAR,

            block_number BIGINT,

            block_timestamp TIMESTAMPTZ,

            from_address VARCHAR,

            to_address VARCHAR,

            contract_address VARCHAR,

            call_type VARCHAR,

            input VARCHAR,

            direction VARCHAR
                NOT NULL,

            value_wei_raw VARCHAR,

            value_eth_exact VARCHAR,

            value_eth_decimal
                DECIMAL(38,18),

            gas BIGINT,

            gas_used BIGINT,

            is_error BOOLEAN,

            error_code VARCHAR,

            ingested_at TIMESTAMPTZ
                NOT NULL,

            source_file VARCHAR
                NOT NULL
        )
        """
    )


def insert_rows(
    connection,
    table_name,
    rows,
    column_count,
):
    if not rows:
        return


    placeholders = ", ".join(
        ["?"]
        * column_count
    )


    connection.executemany(
        f"""
        INSERT INTO {table_name}
        VALUES ({placeholders})
        """,
        rows,
    )


def print_summary(
    connection,
):
    print()

    print(
        "=" * 100
    )

    print(
        "SILVER BUILD COMPLETE"
    )

    print(
        "=" * 100
    )


    wallet_count = (
        connection.execute(
            """
            SELECT COUNT(*)
            FROM silver.wallets
            """
        ).fetchone()[0]
    )


    print(
        "Wallets:",
        wallet_count,
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
                w.wallet_name,

                COUNT(*) AS row_count,

                MIN(
                    t.block_timestamp
                ) AS first_timestamp,

                MAX(
                    t.block_timestamp
                ) AS last_timestamp

            FROM
                silver.{table_name}
                AS t

            JOIN silver.wallets
                AS w
                USING (wallet_id)

            GROUP BY
                w.wallet_name

            ORDER BY
                w.wallet_name
            """
        ).fetchall()


        for row in rows:
            print(
                "  ",
                row[0],
                "| rows:",
                row[1],
                "| first:",
                row[2],
                "| last:",
                row[3],
            )


    duplicate_groups = (
        connection.execute(
            """
            SELECT COUNT(*)

            FROM (
                SELECT
                    wallet_id,
                    transaction_hash,
                    log_index

                FROM
                    silver.erc20_transfers

                GROUP BY
                    wallet_id,
                    transaction_hash,
                    log_index

                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )


    print()

    print(
        "ERC20 duplicate "
        "(wallet_id, "
        "transaction_hash, "
        "log_index) groups:",
        duplicate_groups,
    )


def main():
    wallets = load_wallets()


    receipt_index = (
        build_receipt_index()
    )


    receipt_cache = {}


    wallet_rows = (
        build_wallet_rows(
            wallets
        )
    )


    transaction_rows = []

    erc20_rows = []

    internal_rows = []


    print(
        "=" * 100
    )

    print(
        "BUILDING MULTI-WALLET "
        "SILVER"
    )

    print(
        "=" * 100
    )


    for wallet in wallets:
        print()

        print(
            "Wallet:",
            wallet[
                "wallet_name"
            ],
        )

        print(
            "Address:",
            wallet[
                "address"
            ],
        )


        current_transactions = (
            build_transaction_rows(
                wallet
            )
        )


        current_erc20 = (
            build_erc20_rows(
                wallet,
                receipt_index,
                receipt_cache,
            )
        )


        current_internal = (
            build_internal_rows(
                wallet
            )
        )


        transaction_rows.extend(
            current_transactions
        )


        erc20_rows.extend(
            current_erc20
        )


        internal_rows.extend(
            current_internal
        )


        print(
            "  Transactions:",
            len(
                current_transactions
            ),
        )

        print(
            "  ERC20 transfers:",
            len(
                current_erc20
            ),
        )

        print(
            "  Internal transactions:",
            len(
                current_internal
            ),
        )


    SILVER_DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    connection = duckdb.connect(
        str(
            SILVER_DB_PATH
        )
    )


    try:
        connection.execute(
            "BEGIN TRANSACTION"
        )


        create_tables(
            connection
        )


        insert_rows(
            connection,
            "silver.wallets",
            wallet_rows,
            9,
        )


        insert_rows(
            connection,
            "silver.transactions",
            transaction_rows,
            30,
        )


        insert_rows(
            connection,
            "silver.erc20_transfers",
            erc20_rows,
            25,
        )


        insert_rows(
            connection,
            "silver.internal_transactions",
            internal_rows,
            24,
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