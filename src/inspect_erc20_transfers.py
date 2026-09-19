import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

import argparse #cho phép đọc tham số dòng lệnh (command-line arguments)

load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


parser = argparse.ArgumentParser(
    description="Inspect Ethereum data for a wallet address."
)

parser.add_argument(
    "address",
    help="Ethereum wallet address, for example 0xabc...",
)

args = parser.parse_args()

address = args.address

url = "https://api.etherscan.io/v2/api"

params = {
    "chainid": "1",
    "module": "account",
    "action": "tokentx",
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


transfers = data.get("result", [])

if not isinstance(transfers, list):
    print("API trả về lỗi:")
    print(transfers)
    raise SystemExit(1)


for transfer in transfers:
    timestamp = datetime.fromtimestamp(
        int(transfer["timeStamp"]),
        tz=timezone.utc,
    )
    #tokenDecimal = đặt dấu thập phân ở đâu
    #tokenDecimal = 6, value = 100000000 -> 100 USDC
    decimals = int(transfer["tokenDecimal"])
    raw_value = int(transfer["value"])
    token_amount = raw_value / (10 ** decimals)

    print("=" * 60)
    print("Transaction hash:", transfer["hash"])
    print("Block:", transfer["blockNumber"])
    print("Time:", timestamp)
    print("From:", transfer["from"])
    print("To:", transfer["to"])
    print("Token:", transfer["tokenSymbol"])
    print("Token name:", transfer["tokenName"])
    print("Token contract:", transfer["contractAddress"])
    print("Amount:", token_amount, transfer["tokenSymbol"])