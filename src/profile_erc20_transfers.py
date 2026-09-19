import argparse
import os
from collections import defaultdict #nếu một key chưa tồn tại -> tạo gt mặc định
from decimal import Decimal

import requests
from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("ETHERSCAN_API_KEY")

if not api_key:
    raise RuntimeError("Không tìm thấy ETHERSCAN_API_KEY trong file .env")


parser = argparse.ArgumentParser(
    description="Profile ERC-20 transfers for an Ethereum wallet address."
)

parser.add_argument(
    "address",
    help="Ethereum wallet address, for example 0xabc...",
)

parser.add_argument(
    "--offset",
    type=int,
    default=100,
    help="Number of ERC-20 transfer records to profile. Default: 100",
)

args = parser.parse_args()

address = args.address.lower()
offset = args.offset


url = "https://api.etherscan.io/v2/api"

params = {
    "chainid": "1",
    "module": "account",
    "action": "tokentx",
    "address": address,
    "startblock": 0,
    "endblock": 99999999,
    "page": 1,
    "offset": offset,
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

transfers = data.get("result", [])

if not isinstance(transfers, list):
    print("API trả về lỗi:")
    print(transfers)
    raise SystemExit(1)


token_stats = defaultdict(
    lambda: {
        "symbol": "",
        "name": "",
        "transfer_count": 0,
        "in_count": 0,
        "out_count": 0,
        "in_amount": Decimal("0"),
        "out_amount": Decimal("0"),
    }
)


for transfer in transfers:
    contract_address = transfer["contractAddress"].lower()
    from_address = transfer["from"].lower()
    to_address = transfer["to"].lower()

    decimals = int(transfer["tokenDecimal"])

    amount = (
        Decimal(transfer["value"])
        / (Decimal(10) ** decimals)
    )

    stats = token_stats[contract_address]

    stats["symbol"] = transfer["tokenSymbol"]
    stats["name"] = transfer["tokenName"]
    stats["transfer_count"] += 1

    if to_address == address:
        stats["in_count"] += 1
        stats["in_amount"] += amount

    if from_address == address:
        stats["out_count"] += 1
        stats["out_amount"] += amount


sorted_tokens = sorted(
    token_stats.items(),
    key=lambda item: item[1]["transfer_count"],
    reverse=True,
)


print("Wallet:", address)
print("Total transfers:", len(transfers))
print("Unique token contracts:", len(token_stats))
print()

print(
    f"{'Token':<35}"
    f"{'Transfers':>10}"
    f"{'In':>8}"
    f"{'Out':>8}"
    f"{'In amount':>30}"
    f"{'Out amount':>30}"
)

print("-" * 90)


for contract_address, stats in sorted_tokens:
    print(
        f"{stats['symbol']:<35}"
        f"{stats['transfer_count']:>10}"
        f"{stats['in_count']:>8}"
        f"{stats['out_count']:>8}"
        f"{str(stats['in_amount']):>30}"
        f"{str(stats['out_amount']):>30}"
)

    print(
        f"  Contract: {contract_address}"
    )