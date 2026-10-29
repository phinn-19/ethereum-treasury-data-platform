"""Safety test: failed validation must preserve the last good dashboard DB."""

import duckdb
import pytest

from src import publish_dashboard_snapshot


def make_database(path, silver_rows: int, gold_rows: int):
    """Create a tiny DuckDB file with only the tables publication checks."""
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE SCHEMA silver")
        con.execute("CREATE SCHEMA gold")
        con.execute("CREATE TABLE silver.erc20_transfers (id INTEGER)")
        con.execute(
            "CREATE TABLE gold.wallet_erc20_transfer_valuations (id INTEGER)"
        )
        con.execute(
            "CREATE TABLE gold.organization_native_eth_valuations (id INTEGER)"
        )
        for index in range(silver_rows):
            con.execute(
                "INSERT INTO silver.erc20_transfers VALUES (?)", [index]
            )
        for index in range(gold_rows):
            con.execute(
                "INSERT INTO gold.wallet_erc20_transfer_valuations VALUES (?)",
                [index],
            )
    finally:
        con.close()


def test_invalid_source_does_not_replace_dashboard_snapshot(tmp_path, monkeypatch):
    # Arrange: source has 2 Silver rows but only 1 Gold valuation row.
    source = tmp_path / "source.duckdb"
    serving = tmp_path / "serving.duckdb"
    make_database(source, silver_rows=2, gold_rows=1)
    make_database(serving, silver_rows=1, gold_rows=1)

    # Redirect the REAL publishing function to temporary test files.
    monkeypatch.setattr(publish_dashboard_snapshot, "SOURCE", source)
    monkeypatch.setattr(publish_dashboard_snapshot, "TARGET", serving)

    # Act: publication must reject inconsistent source data.
    with pytest.raises(RuntimeError, match="Silver and Gold ERC20 counts differ"):
        publish_dashboard_snapshot.publish()

    # Assert: last good dashboard snapshot still exists and is unchanged.
    with duckdb.connect(str(serving), read_only=True) as con:
        silver_count = con.execute(
            "SELECT COUNT(*) FROM silver.erc20_transfers"
        ).fetchone()[0]
        gold_count = con.execute(
            "SELECT COUNT(*) FROM gold.wallet_erc20_transfer_valuations"
        ).fetchone()[0]
    assert (silver_count, gold_count) == (1, 1)
    assert not list(tmp_path.glob(".treasury_snapshot_*.duckdb"))
