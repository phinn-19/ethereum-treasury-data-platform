import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


# Nhận tham số từ command line
parser = argparse.ArgumentParser(
    description="Ingest ERC-20 transfers for an Ethereum address."
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

address = args.address
offset = args.offset

if offset <= 0:
    raise ValueError("--offset phải lớn hơn 0")


url = "https://api.etherscan.io/v2/api"


# Thời điểm bắt đầu một lần ingestion
run_time = datetime.now(timezone.utc)

date_folder = run_time.strftime("%Y-%m-%d")
timestamp = run_time.strftime("%Y%m%dT%H%M%SZ")


# Folder dùng chung cho tất cả page trong lần chạy này
output_dir = Path(
    "data",
    "raw",
    "ethereum",
    "erc20_transfers",
    f"ingestion_date={date_folder}",
)

output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# Bắt đầu từ page 1
page = 1


while True:
    params = {
        "chainid": "1",
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": offset,
        "sort": "asc",
        "apikey": api_key,
    }

    print(f"Fetching page {page}...")

    response = requests.get(
        url,
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()
    result = payload.get("result")


    # Trường hợp đã hết dữ liệu
    if (
        payload.get("status") == "0"
        and "No transactions found" in str(result)
    ):
        print("No more records. Stopping.")
        break


    # Trường hợp API trả về thứ gì đó bất thường
    if not isinstance(result, list):
        raise RuntimeError(
            f"Etherscan API error on page {page}: {payload}"
        )


    # Nếu list rỗng thì cũng dừng
    if len(result) == 0:
        print("No more records. Stopping.")
        break


    # Mỗi page lưu thành một raw file riêng
    output_file = (
        output_dir
        / (
            f"tokentx_{address.lower()}_"
            f"page_{page:04d}_"
            f"{timestamp}.json"
        )
    )

    output_file.write_text(
        response.text,
        encoding="utf-8",
    )

    print(
        f"Saved page {page}: "
        f"{len(result)} records"
    )


    # Nếu page hiện tại ít hơn offset
    # thì đây là page cuối
    if len(result) < offset:
        print("Reached the last page.")
        break


    # Sang page tiếp theo
    page += 1