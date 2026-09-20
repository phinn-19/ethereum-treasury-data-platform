import argparse
import os

from dotenv import load_dotenv

from etherscan_ingestion import ingest_account_history


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError(
        "Không tìm thấy ETHERSCAN_API_KEY trong file .env"
    )


parser = argparse.ArgumentParser(
    description="Ingest internal transactions for an Ethereum address."
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
    raise ValueError("--offset phải lớn hơn 0")


ingest_account_history(
    api_key=api_key,
    address=args.address,
    action="txlistinternal",
    dataset_name="internal_transactions",
    file_prefix="txlistinternal",
    offset=args.offset,
)