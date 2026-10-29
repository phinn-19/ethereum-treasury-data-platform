"""Check that a failure during pagination cannot advance the ERC20 checkpoint."""

import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import etherscan_ingestion, ingestion_state


def test_second_page_error_keeps_checkpoint(tmp_path, monkeypatch):
    # Arrange: simulated data files and checkpoints, not the real project data.
    monkeypatch.chdir(tmp_path)
    address = "0x" + "a" * 40
    for dataset in ("transactions", "erc20_transfers", "internal_transactions"):
        ingestion_state.save_checkpoint(dataset, address, 1000)

    first_page = [
        {"blockNumber": "1001", "hash": "0xaaa"},
        {"blockNumber": "1002", "hash": "0xbbb"},
    ]
    requested = []

    def fake_fetch_page(*, api_key, address, action, page, offset, start_block):
        requested.append((action, page, start_block))
        if action == "txlist":
            return SimpleNamespace(text="{}"), []
        if action == "tokentx" and page == 1:
            return SimpleNamespace(text=json.dumps({"result": first_page})), first_page
        if action == "tokentx" and page == 2:
            raise RuntimeError("Simulated API failure on page 2")
        raise AssertionError(f"Unexpected API call: {action}, page={page}")

    monkeypatch.setattr(etherscan_ingestion, "fetch_page", fake_fetch_page)
    # The CLI imports these modules without the 'src.' prefix.
    monkeypatch.setitem(sys.modules, "etherscan_ingestion", etherscan_ingestion)
    monkeypatch.setitem(sys.modules, "ingestion_state", ingestion_state)
    monkeypatch.setenv("ETHERSCAN_API_KEY", "fake-test-key")
    monkeypatch.setattr(
        sys, "argv", ["ingest_incremental.py", address, "--offset", "2"]
    )

    script = Path(etherscan_ingestion.__file__).with_name("ingest_incremental.py")

    # Act: run the actual incremental CLI with a fake error on page 2.
    with pytest.raises(RuntimeError, match="Simulated API failure on page 2"):
        runpy.run_path(str(script), run_name="__main__")

    # Assert: page 1 was saved, but the checkpoint must NOT move forward.
    assert requested == [
        ("txlist", 1, 1001),
        ("tokentx", 1, 1001),
        ("tokentx", 2, 1001),
    ]
    assert ingestion_state.load_checkpoint("erc20_transfers", address) == 1000

    files = list((tmp_path / "data/raw/ethereum/erc20_transfers").rglob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["result"] == first_page
