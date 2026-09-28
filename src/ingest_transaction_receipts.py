import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://api.etherscan.io/v2/api"

CHAIN_ID = 1

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)

ERC20_ROOT = (
    RAW_ROOT
    / "erc20_transfers"
)

RECEIPT_ROOT = (
    RAW_ROOT
    / "transaction_receipts"
)


MAX_RETRIES = 3

BASE_RETRY_DELAY = 2

RETRYABLE_HTTP_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


def normalize_address(address):
    address = address.strip().lower()

    if re.fullmatch(
        r"0x[a-f0-9]{40}",
        address,
    ) is None:
        raise ValueError(
            "Invalid Ethereum address: "
            f"{address}"
        )

    return address


def load_api_key():
    load_dotenv(
        dotenv_path=".env"
    )

    api_key = os.getenv(
        "ETHERSCAN_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "ETHERSCAN_API_KEY "
            "was not found in .env"
        )

    return api_key

#lấy theo transaction_hash, kh theo wallet

def collect_transaction_hashes(
    address,
):
    pattern = (
        f"**/"
        f"tokentx_{address}_*.json"
    )

    raw_files = sorted(
        ERC20_ROOT.glob(pattern)
    )

    if not raw_files:
        raise FileNotFoundError(
            "No ERC20 Bronze files "
            f"found for address {address}"
        )

    transaction_hashes = set()

    raw_record_count = 0


    for raw_file in raw_files:
        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            raise ValueError(
                "Expected result to be "
                f"a list in {raw_file}"
            )

        raw_record_count += len(result)


        for record in result:
            tx_hash = (
                record.get("hash")
            )

            if not tx_hash:
                continue

            transaction_hashes.add(
                tx_hash.lower()
            )


    return {
        "raw_files": len(raw_files),
        "raw_records": raw_record_count,
        "transaction_hashes": sorted(
            transaction_hashes
        ),
    }


def find_existing_receipts():
    existing_hashes = set()

    if not RECEIPT_ROOT.exists():
        return existing_hashes


    for receipt_file in (
        RECEIPT_ROOT.glob(
            "**/receipt_*.json"
        )
    ):
        filename = (
            receipt_file.stem
        )

        if not filename.startswith(
            "receipt_"
        ):
            continue

        tx_hash = filename[
            len("receipt_"):
        ].lower()

        existing_hashes.add(
            tx_hash
        )


    return existing_hashes


def should_retry_payload(
    payload,
):
    text = json.dumps(
        payload
    ).lower()

    retryable_patterns = (
        "rate limit",
        "max rate limit",
        "timeout",
        "temporarily unavailable",
        "server busy",
    )

    return any(
        pattern in text
        for pattern
        in retryable_patterns
    )


def fetch_receipt(
    session,
    api_key,
    tx_hash,
):
    params = {
        "chainid": str(CHAIN_ID),
        "module": "proxy",
        "action":
            "eth_getTransactionReceipt",
        "txhash": tx_hash,
        "apikey": api_key,
    }


    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = session.get(
                BASE_URL,
                params=params,
                timeout=20,
            )


            if (
                response.status_code
                in RETRYABLE_HTTP_STATUS_CODES
            ):
                raise requests.HTTPError(
                    "Retryable HTTP status: "
                    f"{response.status_code}"
                )


            response.raise_for_status()

            payload = response.json()


            if should_retry_payload(
                payload
            ):
                raise RuntimeError(
                    "Retryable Etherscan "
                    f"response: {payload}"
                )


            receipt = payload.get(
                "result"
            )


            if not isinstance(
                receipt,
                dict,
            ):
                raise RuntimeError(
                    "Expected receipt object "
                    f"for transaction {tx_hash}, "
                    f"got: {payload}"
                )


            returned_hash = (
                receipt.get(
                    "transactionHash",
                    "",
                )
                .lower()
            )


            if returned_hash != tx_hash:
                raise RuntimeError(
                    "Receipt transaction hash "
                    "does not match requested "
                    f"hash: {tx_hash}"
                )


            return payload


        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
            RuntimeError,
        ) as error:
            if attempt == MAX_RETRIES:
                raise


            delay = (
                BASE_RETRY_DELAY
                * (
                    2
                    ** (
                        attempt - 1
                    )
                )
            )

            print(
                "Request failed:"
            )

            print(
                f"  {error}"
            )

            print(
                "Retrying in "
                f"{delay} seconds..."
            )

            time.sleep(delay)


    raise RuntimeError(
        "Receipt fetch failed "
        f"for {tx_hash}"
    )


def save_receipt(
    tx_hash,
    payload,
):
    fetched_at = datetime.now(
        timezone.utc
    )

    ingestion_date = (
        fetched_at.date()
        .isoformat()
    )

    output_dir = (
        RECEIPT_ROOT
        / (
            "ingestion_date="
            f"{ingestion_date}"
        )
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )


    output_file = (
        output_dir
        / f"receipt_{tx_hash}.json"
    )

    temporary_file = (
        output_file.with_suffix(
            ".tmp"
        )
    )


    temporary_file.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )


    temporary_file.replace(
        output_file
    )


    return output_file


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Ethereum transaction "
            "receipts for ERC20 Bronze "
            "transactions."
        )
    )


    parser.add_argument(
        "address",
        help=(
            "Ethereum treasury wallet "
            "address whose ERC20 "
            "transactions should be "
            "backfilled with receipts."
        ),
    )


    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of new "
            "receipts to fetch during "
            "this run."
        ),
    )


    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help=(
            "Seconds to wait between "
            "successful API requests. "
            "Default: 0.25"
        ),
    )


    args = parser.parse_args()


    if (
        args.limit is not None
        and args.limit <= 0
    ):
        parser.error(
            "--limit must be greater "
            "than zero"
        )


    if args.delay < 0:
        parser.error(
            "--delay cannot be negative"
        )


    address = normalize_address(
        args.address
    )

    api_key = load_api_key()


    source_summary = (
        collect_transaction_hashes(
            address
        )
    )


    transaction_hashes = (
        source_summary[
            "transaction_hashes"
        ]
    )


    existing_hashes = (
        find_existing_receipts()
    )


    pending_hashes = [
        tx_hash
        for tx_hash
        in transaction_hashes
        if tx_hash
        not in existing_hashes
    ]


    already_saved_count = (
        len(transaction_hashes)
        - len(pending_hashes)
    )


    if args.limit is not None:
        pending_hashes = (
            pending_hashes[
                :args.limit
            ]
        )


    print(
        "Wallet:",
        address,
    )

    print(
        "ERC20 Bronze files:",
        source_summary[
            "raw_files"
        ],
    )

    print(
        "ERC20 Bronze records:",
        source_summary[
            "raw_records"
        ],
    )

    print(
        "Unique transaction hashes:",
        len(transaction_hashes),
    )

    print(
        "Receipts already saved:",
        already_saved_count,
    )

    print(
        "Receipts to fetch "
        "this run:",
        len(pending_hashes),
    )


    if not pending_hashes:
        print()
        print(
            "No new receipts "
            "need to be fetched."
        )

        return


    fetched_count = 0

    last_output_file = None


    with requests.Session() as session:
        for index, tx_hash in enumerate(
            pending_hashes,
            start=1,
        ):
            print()
            print(
                f"[{index}/"
                f"{len(pending_hashes)}] "
                "Fetching receipt:"
            )

            print(
                f"  {tx_hash}"
            )


            payload = fetch_receipt(
                session,
                api_key,
                tx_hash,
            )


            last_output_file = (
                save_receipt(
                    tx_hash,
                    payload,
                )
            )


            fetched_count += 1


            print(
                "Saved:"
            )

            print(
                f"  {last_output_file}"
            )


            if args.delay > 0:
                time.sleep(
                    args.delay
                )


    print()
    print(
        "=" * 80
    )

    print(
        "RECEIPT INGESTION COMPLETE"
    )

    print(
        "=" * 80
    )

    print(
        "Wallet:",
        address,
    )

    print(
        "Unique ERC20 "
        "transaction hashes:",
        len(transaction_hashes),
    )

    print(
        "Already available:",
        already_saved_count,
    )

    print(
        "Fetched this run:",
        fetched_count,
    )

    print(
        "Receipt root:",
        RECEIPT_ROOT,
    )
    

if __name__ == "__main__":
    main()