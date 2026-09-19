import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# Đọc các biến trong file .env
load_dotenv()
api_key = os.getenv("ETHERSCAN_API_KEY")
if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")

# Address dùng để TEST kết nối API.
# Đây chưa phải wallet chính thức của project.
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
    "offset": 5, # 5 record trên page này
    "sort": "desc",
    "apikey": api_key,
}
# biến res thành các endpoint bằng các param

response = requests.get(url, params = params, timeout = 20)
response.raise_for_status()

data = response.json()
print("HTTP status:", response.status_code)
print("Etherscan status:", data.get("status"))
print("Message:", data.get("message"))
print()

transactions = data.get("result", [])
if not isinstance(transactions, list):
    print("API trả về lỗi:")
    print(transactions)
    raise SystemExit(1)

for tx in transactions:
    timestamp = datetime.fromtimestamp(
        int(tx["timeStamp"]),
        tz=timezone.utc,
    )

    eth_value = int(tx["value"]) / 10**18

    print("=" * 60)
    print("Transaction hash:", tx["hash"])
    print("Block:", tx["blockNumber"])
    print("Time:", timestamp)
    print("From:", tx["from"])
    print("To:", tx["to"])
    print("Value:", eth_value, "ETH")
    print("Function:", tx.get("functionName"))
    print("Nonce:", tx["nonce"])
    print("Gas used:", tx["gasUsed"])
    print("Gas price:", tx["gasPrice"])
    print("Status:", tx["txreceipt_status"])