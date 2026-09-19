import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


# Wallet test hiện tại.
# Chưa phải wallet chính thức của project.
address = "0x2449ecef5012f0a0e153b278ef4fcc9625bc4c78"

url = "https://api.etherscan.io/v2/api"

params = {
    "chainid": "1",
    "module": "account",
    "action": "txlist",
    "address": address,
    "startblock": 0,
    "endblock": 99999999,
    "page": 1,
    "offset": 5,
    "sort": "desc",
    "apikey": api_key,
}


response = requests.get(
    url,
    params=params,
    timeout=20,
)

response.raise_for_status()


# Thời điểm dữ liệu được ingestion.
ingested_at = datetime.now(timezone.utc)

date_folder = ingested_at.strftime("%Y-%m-%d")
timestamp = ingested_at.strftime("%Y%m%dT%H%M%SZ")


output_dir = Path(
    "data",
    "raw",
    "ethereum",
    "transactions",
    f"ingestion_date={date_folder}",
)

output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


output_file = output_dir / f"txlist_{address}_{timestamp}.json"


output_file.write_text(
    response.text,
    encoding="utf-8",
)


print("Raw data saved successfully.")
print("File:", output_file)
print("HTTP status:", response.status_code)