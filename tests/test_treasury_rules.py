"""Regression tests for critical ENS DAO treasury rules.

All examples use synthetic addresses and an in-memory database.
No Etherscan API, Airflow, or production DuckDB file is accessed.
"""

from decimal import Decimal

import duckdb
import pytest

from src import build_gold, build_silver, ingestion_state


WALLET_A = "0x" + "a" * 40
WALLET_B = "0x" + "b" * 40
EXTERNAL = "0x" + "c" * 40
USDC_CONTRACT = "0x" + "d" * 40


def test_wallet_direction_is_not_organization_direction():
    # The same monitored-to-monitored event has two wallet-level perspectives.
    assert build_silver.classify_direction(WALLET_A, WALLET_A, WALLET_B) == "OUT"
    assert build_silver.classify_direction(WALLET_B, WALLET_A, WALLET_B) == "IN"
    assert build_silver.classify_direction(WALLET_A, WALLET_A, WALLET_A) == "SELF"


def test_transfer_log_decode_and_log_index_identity():
    def transfer_log(log_index):
        return {
            "address": USDC_CONTRACT.upper(),
            "topics": [
                build_silver.TRANSFER_TOPIC,
                "0x" + ("0" * 24) + WALLET_A[2:],
                "0x" + ("0" * 24) + WALLET_B[2:],
            ],
            "data": "0x" + format(100_000_000, "064x"),
            "logIndex": hex(log_index),
            "transactionIndex": "0x1",
            "blockNumber": "0x64",
        }

    decoded_13 = build_silver.decode_erc20_transfer_log(transfer_log(13))
    decoded_14 = build_silver.decode_erc20_transfer_log(transfer_log(14))

    assert decoded_13["value_raw"] == "100000000"
    assert decoded_13["token_contract"] == USDC_CONTRACT
    assert decoded_13["from_address"] == WALLET_A
    assert decoded_13["to_address"] == WALLET_B
    assert decoded_13["log_index"] == 13
    assert decoded_14["log_index"] == 14

    tx_hash = "0x" + "f" * 64
    event_13 = build_silver.stable_id("erc20_event", 1, tx_hash, 13)
    event_14 = build_silver.stable_id("erc20_event", 1, tx_hash, 14)
    assert event_13 != event_14  # The tx hash alone is insufficient.
    assert build_silver.stable_id("erc20_event", 1, tx_hash, 13) == event_13


def test_usdc_raw_amount_uses_six_decimals_exactly():
    assert build_silver.exact_amount_string("100000000", 6) == "100.000000"
    assert build_silver.decimal_38_18_or_none("100.000000") == Decimal("100.000000")


@pytest.fixture
def warehouse():
    # Test data lives exclusively in memory, not in data/silver/ or data/serving/.
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA silver")
    con.execute("CREATE SCHEMA gold")
    con.execute("""
        CREATE TABLE silver.wallets (
            organization_id VARCHAR, organization_name VARCHAR,
            wallet_id VARCHAR, address VARCHAR, monitoring_enabled BOOLEAN
        )
    """)
    con.executemany(
        "INSERT INTO silver.wallets VALUES (?, ?, ?, ?, ?)",
        [
            ("ens_dao", "ENS DAO", "wallet_a", WALLET_A, True),
            ("ens_dao", "ENS DAO", "wallet_b", WALLET_B, True),
        ],
    )
    con.execute("""
        CREATE TABLE gold.wallet_erc20_transfer_valuations (
            wallet_id VARCHAR,
            blockchain_event_id VARCHAR,
            chain_id INTEGER,
            organization_id VARCHAR,
            valuation_date DATE,
            token_contract VARCHAR,
            token_name VARCHAR,
            token_symbol VARCHAR,
            token_decimals INTEGER,
            from_address VARCHAR,
            to_address VARCHAR,
            amount_decimal DECIMAL(38,18),
            valuation_status VARCHAR,
            daily_price_usd DECIMAL(38,8),
            value_usd DECIMAL(38,8)
        )
    """)
    try:
        yield con
    finally:
        con.close()


def insert_gold_event(con, wallet_id, event_id, sender, recipient, amount, status, price, usd):
    con.execute("""
        INSERT INTO gold.wallet_erc20_transfer_valuations
        VALUES (?, ?, 1, 'ens_dao', DATE '2026-10-01', ?, 'USD Coin', 'USDC',
                6, ?, ?, ?, ?, ?, ?)
    """, [wallet_id, event_id, USDC_CONTRACT, sender, recipient, amount, status, price, usd])


def test_internal_transfer_is_counted_once_not_as_external(warehouse):
    # Two wallet-grain observations refer to ONE blockchain transfer event.
    for wallet_id in ("wallet_a", "wallet_b"):
        insert_gold_event(
            warehouse, wallet_id, "event-1", WALLET_A, WALLET_B,
            Decimal("100"), "VALUED", Decimal("1"), Decimal("100"),
        )

    build_gold.build_organization_daily_erc20_flows(warehouse)
    row = warehouse.execute("""
        SELECT total_event_count, internal_transfer_event_count,
               external_inflow_event_count, external_outflow_event_count,
               internal_transfer_amount, external_inflow_amount, external_outflow_amount
        FROM gold.organization_daily_erc20_flows
    """).fetchone()

    assert row == (1, 1, 0, 0, Decimal("100"), Decimal("0"), Decimal("0"))


def test_unpriced_external_outflow_remains_null_usd(warehouse):
    insert_gold_event(
        warehouse, "wallet_a", "event-2", WALLET_A, EXTERNAL,
        Decimal("50"), "PRICE_UNAVAILABLE", None, None,
    )

    build_gold.build_organization_daily_erc20_flows(warehouse)
    amount, value, missing_count = warehouse.execute("""
        SELECT external_outflow_amount, external_outflow_usd,
               price_unavailable_event_count
        FROM gold.organization_daily_erc20_flows
    """).fetchone()

    assert amount == Decimal("50")
    assert value is None  # Unknown USD value must NOT be counted as zero.
    assert missing_count == 1


def test_checkpoint_roundtrip_does_not_touch_real_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion_state, "STATE_ROOT", tmp_path / "state")
    dataset = "erc20_transfers"
    ingestion_state.save_checkpoint(dataset, WALLET_A.upper(), 26248943)

    assert ingestion_state.load_checkpoint(dataset, WALLET_A) == 26248943
    checkpoint_path = ingestion_state.get_checkpoint_path(dataset, WALLET_A)
    assert checkpoint_path.exists()
    assert not checkpoint_path.with_suffix(".tmp").exists()
