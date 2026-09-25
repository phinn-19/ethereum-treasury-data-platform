import json
from collections import defaultdict
from pathlib import Path


RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)


DATASETS = {
    "erc20_transfers": {
        "key_fields": (
            "hash",
            "transactionIndex",
            "contractAddress",
            "from",
            "to",
            "value",
        ),
    },

    "internal_transactions": {
        "key_fields": (
            "hash",
            "traceId",
        ),
    },
}


def load_records(dataset_name):
    dataset_dir = RAW_ROOT / dataset_name

    records = []

    for raw_file in dataset_dir.glob("**/*.json"):
        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            continue

        for record in result:
            records.append(
                {
                    "source_file": str(raw_file),
                    "record": record,
                }
            )

    return records


def make_key(record, key_fields):
    return tuple(
        record.get(field)
        for field in key_fields
    )


def record_signature(record):
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
    )


for dataset_name, config in DATASETS.items():
    records = load_records(dataset_name)

    groups = defaultdict(list)

    for item in records:
        key = make_key(
            item["record"],
            config["key_fields"],
        )

        groups[key].append(item)


    duplicate_groups = {
        key: items
        for key, items in groups.items()
        if len(items) > 1
    }


    exact_duplicate_groups = 0
    collision_groups = []


    for key, items in duplicate_groups.items():
        signatures = {
            record_signature(
                item["record"]
            )
            for item in items
        }

        if len(signatures) == 1:
            exact_duplicate_groups += 1
        else:
            collision_groups.append(
                (key, items)
            )


    print()
    print("=" * 80)
    print("Dataset:", dataset_name)
    print("=" * 80)

    print(
        "Key fields:",
        " + ".join(
            config["key_fields"]
        ),
    )

    print(
        "Total raw records:",
        len(records),
    )

    print(
        "Unique candidate keys:",
        len(groups),
    )

    print(
        "Keys appearing more than once:",
        len(duplicate_groups),
    )

    print(
        "Exact duplicate groups:",
        exact_duplicate_groups,
    )

    print(
        "Collision groups:",
        len(collision_groups),
    )


    if collision_groups:
        print()
        print("First collision examples:")

        for key, items in collision_groups[:3]:
            print()
            print("Key:", key)

            print(
                "Number of records:",
                len(items),
            )

            for item in items[:3]:
                print(
                    "Source:",
                    item["source_file"],
                )

                print(
                    json.dumps(
                        item["record"],
                        indent=2,
                    )
                )