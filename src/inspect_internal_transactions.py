import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


# Address test hiện tại.
# Chưa phải treasury wallet chính thức của project.
address = "0x2449ecef5012f0a0e153b278ef4fcc9625bc4c78"

url = "https://api.etherscan.io/v2/api"

params = {
    "chainid": "1",
    "module": "account",
    "action": "txlistinternal",
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

data = response.json()

print("HTTP status:", response.status_code)
print("Etherscan status:", data.get("status"))
print("Message:", data.get("message"))
print()


internal_transactions = data.get("result", [])

if not isinstance(internal_transactions, list):
    print("API trả về lỗi:")
    print(internal_transactions)
    raise SystemExit(1)


for tx in internal_transactions:
    timestamp = datetime.fromtimestamp(
        int(tx["timeStamp"]),
        tz=timezone.utc,
    )

    eth_value = int(tx["value"]) / 10**18

    print("=" * 60)
    print("Parent transaction hash:", tx["hash"])
    print("Block:", tx["blockNumber"])
    print("Time:", timestamp)
    print("From:", tx["from"])
    print("To:", tx["to"])
    print("Value:", eth_value, "ETH")
    print("Type:", tx["type"])
    print("Trace ID:", tx["traceId"])
    print("Is error:", tx["isError"])