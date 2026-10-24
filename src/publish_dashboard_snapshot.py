
"""Publish a verified DuckDB snapshot for the Streamlit dashboard."""

import os
import shutil
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

SOURCE = ROOT / "data/silver/ethereum_treasury.duckdb"
TARGET = ROOT / "data/serving/ethereum_treasury.duckdb"

TABLES = (
    "silver.erc20_transfers",
    "gold.wallet_erc20_transfer_valuations",
    "gold.organization_native_eth_valuations",
)


def counts(connection):
    return {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in TABLES
    }


def publish():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Missing database: {SOURCE}")

    # Do not copy a database with pending WAL changes.
    if Path(str(SOURCE) + ".wal").exists():
        raise RuntimeError(
            "Source database has a WAL file. Check for active writers."
        )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".treasury_snapshot_",
            suffix=".duckdb",
            dir=TARGET.parent,
            delete=False,
        ) as temp:
            temp_path = Path(temp.name)

            source_conn = duckdb.connect(
                str(SOURCE), read_only=True
            )
            try:
                original_counts = counts(source_conn)

                if (
                    original_counts["silver.erc20_transfers"]
                    != original_counts[
                        "gold.wallet_erc20_transfer_valuations"
                    ]
                ):
                    raise RuntimeError(
                        "Silver and Gold ERC20 counts differ"
                    )

                with SOURCE.open("rb") as original:
                    shutil.copyfileobj(
                        original, temp, length=1024 * 1024
                    )

                temp.flush()
                os.fsync(temp.fileno())
            finally:
                source_conn.close()

        snapshot_conn = duckdb.connect(
            str(temp_path), read_only=True
        )
        try:
            snapshot_counts = counts(snapshot_conn)
        finally:
            snapshot_conn.close()

        if original_counts != snapshot_counts:
            raise RuntimeError("Snapshot validation failed")

        os.replace(temp_path, TARGET)

        print(f"Dashboard snapshot published: {TARGET}")
        print(f"Verified counts: {snapshot_counts}")

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    publish()
