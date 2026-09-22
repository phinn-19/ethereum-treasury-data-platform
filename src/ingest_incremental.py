import argparse
import os

from dotenv import load_dotenv

from etherscan_ingestion import ingest_account_history
from ingestion_state import (
    find_highest_block_in_raw,
    load_checkpoint,
    save_checkpoint,
)


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError(
        "Không tìm thấy ETHERSCAN_API_KEY trong file .env"
    )


parser = argparse.ArgumentParser(
    description=(
        "Incrementally ingest Ethereum treasury "
        "activity from Etherscan."
    )
)

parser.add_argument(
    "address",
    help="Ethereum address to ingest.",
)

parser.add_argument(
    "--offset",
    type=int,
    default=100,
    help="Number of records per API page. Default: 100",
)

args = parser.parse_args()

if args.offset <= 0:
    raise ValueError(
        "--offset phải lớn hơn 0"
    )


DATASETS = [
    {
        "action": "txlist",
        "dataset_name": "transactions",
        "file_prefix": "txlist",
    },
    {
        "action": "tokentx",
        "dataset_name": "erc20_transfers",
        "file_prefix": "tokentx",
    },
    {
        "action": "txlistinternal",
        "dataset_name": "internal_transactions",
        "file_prefix": "txlistinternal",
    },
]


for dataset in DATASETS:
    dataset_name = dataset["dataset_name"]
    file_prefix = dataset["file_prefix"]

    print()
    print("=" * 60)
    print("Dataset:", dataset_name)
    print("=" * 60)


    checkpoint = load_checkpoint(
        dataset_name=dataset_name,
        address=args.address,
    )


    # Nếu chưa có checkpoint:
    # đọc Bronze lịch sử để tự tìm block cao nhất.
    if checkpoint is None:
        checkpoint = find_highest_block_in_raw(
            dataset_name=dataset_name,
            file_prefix=file_prefix,
            address=args.address,
        )

        if checkpoint is None:
            raise RuntimeError(
                f"Không tìm thấy historical Bronze data "
                f"cho dataset {dataset_name}. "
                f"Hãy chạy historical ingestion trước."
            )

        save_checkpoint(
            dataset_name=dataset_name,
            address=args.address,
            block_number=checkpoint,
        )

        print(
            "Initialized checkpoint from Bronze:",
            checkpoint,
        )


    # Chỉ lấy dữ liệu sau block đã xử lý.
    start_block = checkpoint + 1

    print(
        "Last processed block:",
        checkpoint,
    )

    print(
        "Incremental start block:",
        start_block,
    )


    summary = ingest_account_history(
        api_key=api_key,
        address=args.address,
        action=dataset["action"],
        dataset_name=dataset_name,
        file_prefix=file_prefix,
        offset=args.offset,
        start_block=start_block,
    )


    highest_block = summary["highest_block"]


    # Không có record mới.
    if highest_block is None:
        print(
            "No new records. "
            "Checkpoint unchanged."
        )

        continue


    # Chỉ update checkpoint sau khi ingestion
    # đã hoàn thành thành công.
    save_checkpoint(
        dataset_name=dataset_name,
        address=args.address,
        block_number=highest_block,
    )

    print(
        "Checkpoint updated:",
        highest_block,
    )