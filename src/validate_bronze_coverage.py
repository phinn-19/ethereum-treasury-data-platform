import json
import sys
from pathlib import Path


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


DATASETS = {
    "transactions": {
        "prefix": "txlist",
    },
    "erc20_transfers": {
        "prefix": "tokentx",
    },
    "internal_transactions": {
        "prefix": "txlistinternal",
    },
}


def load_wallets():
    if not WALLET_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Wallet config not found: "
            f"{WALLET_CONFIG_PATH}"
        )
    # 
    wallets = json.loads(
        WALLET_CONFIG_PATH.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(wallets, list):
        raise ValueError(
            "wallets.json must contain "
            "a JSON list"
        )
    # chỉ check wallet có monitoring_enabled true
    active_wallets = [
        wallet
        for wallet in wallets
        if wallet.get(
            "monitoring_enabled",
            False,
        )
    ]

    if not active_wallets:
        raise ValueError(
            "No monitoring-enabled "
            "wallets found"
        )

    return active_wallets


def load_dataset_records(
    dataset_name,
    address,
):
    prefix = DATASETS[
        dataset_name
    ]["prefix"]

    dataset_dir = (
        RAW_ROOT
        / dataset_name
    )

    pattern = (
        f"**/"
        f"{prefix}_{address}_*.json"
    )

    raw_files = sorted(
        dataset_dir.glob(pattern)
    )

    records = []

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

        records.extend(result)

    return raw_files, records


def load_existing_receipt_hashes():
    receipt_hashes = set()

    if not RECEIPT_ROOT.exists():
        return receipt_hashes

    for receipt_file in (
        RECEIPT_ROOT.glob(
            "**/receipt_*.json"
        )
    ):
        filename = receipt_file.stem

        tx_hash = filename[
            len("receipt_"):
        ].lower()

        receipt_hashes.add(
            tx_hash
        )

    return receipt_hashes


def unique_erc20_hashes(records):
    return {
        record["hash"].lower()
        for record in records
        if record.get("hash")
    }


def highest_block(records):
    blocks = [
        int(record["blockNumber"])
        for record in records
        if record.get("blockNumber")
    ]

    if not blocks:
        return None

    return max(blocks)


def main():
    wallets = load_wallets()

    existing_receipts = (
        load_existing_receipt_hashes()
    )

    has_errors = False

    print(
        "=" * 100
    )
    print(
        "BRONZE MULTI-WALLET VALIDATION"
    )
    print(
        "=" * 100
    )

    print(
        "Monitoring-enabled wallets:",
        len(wallets),
    )

    print(
        "Stored transaction receipts:",
        len(existing_receipts),
    )


    for wallet in wallets:
        address = (
            wallet["address"]
            .lower()
        )

        print()
        print(
            "-" * 100
        )

        print(
            wallet["wallet_name"]
        )

        print(
            "Wallet ID:",
            wallet["wallet_id"],
        )

        print(
            "Address:",
            address,
        )

        print(
            "Role:",
            wallet["wallet_role"],
        )


        wallet_records = {}


        for dataset_name in DATASETS:
            raw_files, records = (
                load_dataset_records(
                    dataset_name,
                    address,
                )
            )

            wallet_records[
                dataset_name
            ] = records


            print()
            print(
                dataset_name
            )

            print(
                "  Raw files:",
                len(raw_files),
            )

            print(
                "  Raw records:",
                len(records),
            )

            print(
                "  Highest block:",
                highest_block(
                    records
                ),
            )


            if not raw_files:
                print(
                    "  STATUS: MISSING"
                )

                has_errors = True

            else:
                print(
                    "  STATUS: OK"
                )


        erc20_records = (
            wallet_records[
                "erc20_transfers"
            ]
        )

        erc20_hashes = (
            unique_erc20_hashes(
                erc20_records
            )
        )

        missing_receipts = (
            erc20_hashes
            - existing_receipts
        )


        print()
        print(
            "transaction_receipts"
        )

        print(
            "  Unique ERC20 "
            "transaction hashes:",
            len(erc20_hashes),
        )

        print(
            "  Receipts available:",
            (
                len(erc20_hashes)
                - len(
                    missing_receipts
                )
            ),
        )

        print(
            "  Missing receipts:",
            len(
                missing_receipts
            ),
        )


        if missing_receipts:
            print(
                "  STATUS: INCOMPLETE"
            )

            print(
                "  First missing hashes:"
            )

            for tx_hash in sorted(
                missing_receipts
            )[:5]:
                print(
                    f"    {tx_hash}"
                )

            has_errors = True

        else:
            print(
                "  STATUS: OK"
            )


    print()
    print(
        "=" * 100
    )

    if has_errors:
        print(
            "VALIDATION FAILED"
        )

        print(
            "Bronze is not complete "
            "for all monitored wallets."
        )

        sys.exit(1)


    print(
        "VALIDATION PASSED"
    )

    print(
        "Bronze is complete for all "
        "monitored wallets."
    )


if __name__ == "__main__":
    main()