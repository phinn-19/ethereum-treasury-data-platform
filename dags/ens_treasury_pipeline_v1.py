"""ENS DAO treasury V1 batch pipeline.

Initial deployment: manual trigger only. Do not schedule until baseline
Bronze data, checkpoint behavior, and production retry policy are verified.

This DAG orchestrates existing scripts; business transformations remain in src/.
"""
from airflow.timetables.trigger import CronTriggerTimetable
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task


PROJECT_ROOT = Path("/opt/airflow/project")
DB_RELATIVE_PATH = "data/silver/ethereum_treasury.duckdb"


@dag(
    dag_id="ens_treasury_pipeline_v1",
    
    schedule=CronTriggerTimetable(
        "0 3 * * *",
        timezone="Asia/Ho_Chi_Minh",
        run_immediately=False,
    ),

    start_date=pendulum.datetime(2026, 10, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    default_args={"retries": 0, "retry_delay": timedelta(minutes=3)},
    tags=["ens-treasury", "v1", "batch"],
)
def ens_treasury_pipeline_v1():
    @task
    def preflight_historical_bronze():
        """Incremental loader requires historical Bronze for every wallet."""
        import json

        wallet_config = PROJECT_ROOT / "config" / "wallets.json"
        if not wallet_config.is_file():
            raise FileNotFoundError(f"Missing wallet config: {wallet_config}")

        wallets = json.loads(wallet_config.read_text(encoding="utf-8"))
        active = [w for w in wallets if w.get("monitoring_enabled")]
        if not active:
            raise RuntimeError("No monitored wallets configured")

        expected = {
            "transactions": "txlist",
            "erc20_transfers": "tokentx",
            "internal_transactions": "txlistinternal",
        }
        for wallet in active:
            address = wallet["address"].lower()
            for dataset, prefix in expected.items():
                folder = PROJECT_ROOT / "data" / "raw" / "ethereum" / dataset
                pattern = f"**/{prefix}_{address}_*.json"
                if not any(folder.glob(pattern)):
                    raise FileNotFoundError(
                        f"Historical Bronze missing for wallet {wallet['wallet_id']} "
                        f"and dataset {dataset}. Run historical backfill separately."
                    )
        print(f"Historical Bronze files found for {len(active)} monitored wallets")

    @task
    def ingest_incremental_all_wallets():
        """Fetch incremental txlist/tokentx/txlistinternal for each wallet."""
        import json
        import subprocess
        import sys

        wallets = json.loads(
            (PROJECT_ROOT / "config" / "wallets.json").read_text(encoding="utf-8")
        )
        for wallet in wallets:
            if not wallet.get("monitoring_enabled"):
                continue
            print(f"Incremental ingestion: {wallet['wallet_id']}", flush=True)
            subprocess.run(
                [sys.executable, "src/ingest_incremental.py", wallet["address"]],
                cwd=PROJECT_ROOT,
                check=True,
            )

    @task
    def ingest_receipts_all_wallets():
        """Fetch missing receipts after ERC20 Bronze has been updated."""
        import json
        import subprocess
        import sys

        wallets = json.loads(
            (PROJECT_ROOT / "config" / "wallets.json").read_text(encoding="utf-8")
        )
        for wallet in wallets:
            if not wallet.get("monitoring_enabled"):
                continue
            print(f"Receipt ingestion: {wallet['wallet_id']}", flush=True)
            subprocess.run(
                [sys.executable, "src/ingest_transaction_receipts.py", wallet["address"]],
                cwd=PROJECT_ROOT,
                check=True,
            )

    @task
    def run_existing_script(script_filename: str):
        """Keep orchestration separate from business code in src/."""
        import subprocess
        import sys

        allowed_scripts = {
            "validate_bronze_coverage.py",
            "build_silver.py",
            "ingest_token_prices.py",
            "build_silver_token_prices.py",
            "validate_silver.py",
            "build_gold.py",
            "validate_gold.py",
            "build_gold_counterparties.py",
            "validate_gold_counterparties.py",
            "build_gold_large_transfers.py",
            "validate_gold_large_transfers.py",
            "build_gold_native_eth.py",
            "validate_gold_native_eth.py",
            "ingest_native_eth_prices.py",
            "build_silver_native_eth_prices.py",
            "build_gold_native_eth_usd.py",
            "validate_gold_native_eth_usd.py",
            "publish_dashboard_snapshot.py",
        }
        if script_filename not in allowed_scripts:
            raise ValueError(f"Unexpected script filename: {script_filename}")
        print(f"Running {script_filename}", flush=True)
        subprocess.run(
            [sys.executable, "src/" + script_filename],
            cwd=PROJECT_ROOT,
            check=True,
        )

    # Single-file DuckDB writes are deliberately serialized in V1.
    head = preflight_historical_bronze()
    incremental = ingest_incremental_all_wallets()
    receipts = ingest_receipts_all_wallets()
    head >> incremental >> receipts
    upstream = receipts

    script_steps = [
        ("validate_bronze", "validate_bronze_coverage.py"),
        ("build_silver", "build_silver.py"),
        ("ingest_token_prices", "ingest_token_prices.py"),
        ("build_silver_token_prices", "build_silver_token_prices.py"),
        ("validate_silver", "validate_silver.py"),
        ("build_gold_erc20", "build_gold.py"),
        ("validate_gold_erc20", "validate_gold.py"),
        ("build_gold_counterparties", "build_gold_counterparties.py"),
        ("validate_gold_counterparties", "validate_gold_counterparties.py"),
        ("build_gold_large_erc20", "build_gold_large_transfers.py"),
        ("validate_gold_large_erc20", "validate_gold_large_transfers.py"),
        ("build_gold_native_eth", "build_gold_native_eth.py"),
        ("validate_gold_native_eth", "validate_gold_native_eth.py"),
        ("ingest_native_eth_prices", "ingest_native_eth_prices.py"),
        ("build_silver_native_eth_prices", "build_silver_native_eth_prices.py"),
        ("build_gold_native_eth_usd", "build_gold_native_eth_usd.py"),
        ("validate_gold_native_eth_usd", "validate_gold_native_eth_usd.py"),
    ]
    for task_id, script_filename in script_steps:
        downstream = run_existing_script.override(task_id=task_id)(script_filename)
        upstream >> downstream
        upstream = downstream

        
    publish = run_existing_script.override(
        task_id="publish_dashboard_snapshot"
    )("publish_dashboard_snapshot.py")

    upstream >> publish



ens_treasury_pipeline_v1()
