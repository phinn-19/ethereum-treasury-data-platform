import json
from collections import Counter
from pathlib import Path


RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)


DATASETS = {
    "erc20_transfers": {
        "stable_fields": (
            "hash",
            "transactionIndex",
            "contractAddress",
            "from",
            "to",
            "value",
        ),
    },

    "internal_transactions": {
        "stable_fields": (
            "hash",
            "traceId",
            "from",
            "to",
            "value",
            "type",
            "contractAddress",
            "input",
        ),
    },
}

#ghép các giá trị thành một tuple
def make_signature(record, fields):
    return tuple(
        record.get(field)
        for field in fields
    )


for dataset_name, config in DATASETS.items():
    dataset_dir = RAW_ROOT / dataset_name

    raw_files = sorted(
        dataset_dir.glob("**/*.json")
    )

    files_with_repeats = 0
    repeated_groups = 0
    extra_rows = 0
    max_copies = 1

    examples = []


    for raw_file in raw_files:
        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            continue

            #counter = bộ đếm mỗi signature xuất hiện bao nhiêu lần
        signature_counts = Counter(
            make_signature(
                record,
                config["stable_fields"],
            )
            for record in result
        )


        repeated_in_file = {
            signature: count
            for signature, count
            in signature_counts.items()
            if count > 1
        }


        if not repeated_in_file:
            continue


        files_with_repeats += 1

        repeated_groups += len(
            repeated_in_file
        )

        extra_rows += sum(
            count - 1
            for count
            in repeated_in_file.values()
        )

        max_copies = max(
            max_copies,
            max(
                repeated_in_file.values()
            ),
        )


        for signature, count in repeated_in_file.items():
            if len(examples) >= 5:
                break

            examples.append(
                {
                    "source_file": str(raw_file),
                    "count": count,
                    "signature": signature,
                }
            )


    print()
    print("=" * 80)
    print("Dataset:", dataset_name)
    print("=" * 80)

    print(
        "Stable fields:",
        " + ".join(
            config["stable_fields"]
        ),
    )

    print(
        "Raw files scanned:",
        len(raw_files),
    )

    print(
        "Files containing repeated signatures:",
        files_with_repeats,
    )

    print(
        "Repeated signature groups:",
        repeated_groups,
    )

    print(
        "Extra rows inside same file:",
        extra_rows,
    )

    print(
        "Maximum copies of one signature in one file:",
        max_copies,
    )


    if examples:
        print()
        print("Examples:")

        for example in examples:
            print()
            print(
                "Source:",
                example["source_file"],
            )

            print(
                "Copies:",
                example["count"],
            )

            for field, value in zip(
                config["stable_fields"],
                example["signature"],
            ):
                print(
                    f"  {field}: {value}"
                )