import json
from datetime import datetime, timezone
from pathlib import Path


STATE_ROOT = Path(
    "data",
    "state",
    "ethereum",
)

RAW_ROOT = Path(
    "data",
    "raw",
    "ethereum",
)


def get_checkpoint_path(
    dataset_name,
    address,
):
    return (
        STATE_ROOT
        / dataset_name
        / f"{address.lower()}.json"
    )


def load_checkpoint(
    dataset_name,
    address,
):
    checkpoint_path = get_checkpoint_path(
        dataset_name,
        address,
    )

    if not checkpoint_path.exists():
        return None

    payload = json.loads(
        checkpoint_path.read_text(
            encoding="utf-8"
        )
    )

    return int(
        payload["last_processed_block"]
    )


def save_checkpoint(
    dataset_name,
    address,
    block_number,
):
    checkpoint_path = get_checkpoint_path(
        dataset_name,
        address,
    )

    checkpoint_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "dataset": dataset_name,
        "address": address.lower(),
        "last_processed_block": block_number,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    temporary_path = checkpoint_path.with_suffix(
        ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        checkpoint_path
    )


def find_highest_block_in_raw(
    dataset_name,
    file_prefix,
    address,
):
    dataset_dir = (
        RAW_ROOT
        / dataset_name
    )

    if not dataset_dir.exists():
        return None

    pattern = (
        f"**/{file_prefix}_"
        f"{address.lower()}_*.json"
    )

    highest_block = None

    for raw_file in dataset_dir.glob(pattern):
        payload = json.loads(
            raw_file.read_text(
                encoding="utf-8"
            )
        )

        result = payload.get("result")

        if not isinstance(result, list):
            continue

        for record in result:
            block_number = record.get(
                "blockNumber"
            )

            if block_number is None:
                continue

            block_number = int(block_number)

            if (
                highest_block is None
                or block_number > highest_block
            ):
                highest_block = block_number

    return highest_block