import json
from collections import Counter
from pathlib import Path


RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)


DATASETS = {
    "transactions": {
        "candidate_keys": [
            ("hash",),
        ],
    },

    "erc20_transfers": {
        "candidate_keys": [
            ("hash",),
            ("hash", "logIndex"),
            (
                "hash",
                "transactionIndex",
                "contractAddress",
                "from",
                "to",
                "value",
            ),
        ],
    },

    "internal_transactions": {
        "candidate_keys": [
            ("hash",),
            ("hash", "traceId"),
        ],
    },
}


def load_records(dataset_name):
    dataset_dir = RAW_ROOT / dataset_name

    records = []

    raw_files = list(
        dataset_dir.glob("**/*.json")
    )

    for raw_file in raw_files:
        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            continue

        records.extend(result)

    return raw_files, records


def analyze_fields(records):
    field_counts = Counter()

    for record in records:
        field_counts.update(
            record.keys()
        )

    return field_counts


def analyze_candidate_key(
    records,
    fields,
):
    missing_records = 0
    values = []

    for record in records:
        key_parts = []

        missing = False

        for field in fields:
            value = record.get(field)

            if value is None:
                missing = True
                break

            key_parts.append(value)

        if missing:
            missing_records += 1
            continue

        values.append(
            tuple(key_parts)
        )

    unique_count = len(set(values))

    duplicate_count = (
        len(values) - unique_count
    )

    return {
        "records_with_key": len(values),
        "missing_records": missing_records,
        "unique_count": unique_count,
        "duplicate_count": duplicate_count,
    }


for dataset_name, config in DATASETS.items():
    raw_files, records = load_records(
        dataset_name
    )

    field_counts = analyze_fields(
        records
    )

    print()
    print("=" * 80)
    print("Dataset:", dataset_name)
    print("=" * 80)

    print("Raw files:", len(raw_files))
    print("Records scanned:", len(records))

    print()
    print("Observed fields:")

    for field in sorted(field_counts):
        print(
            f"  {field:<25}"
            f"{field_counts[field]}/{len(records)}"
        )

    print()
    print("Candidate unique keys:")

    for fields in config["candidate_keys"]:
        result = analyze_candidate_key(
            records,
            fields,
        )

        field_name = " + ".join(fields)

        print()
        print(" ", field_name)

        print(
            "    Records with key:",
            result["records_with_key"],
        )

        print(
            "    Missing key fields:",
            result["missing_records"],
        )

        print(
            "    Unique keys:",
            result["unique_count"],
        )

        print(
            "    Duplicate rows by this key:",
            result["duplicate_count"],
        )