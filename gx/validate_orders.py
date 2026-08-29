#!/usr/bin/env python3
"""Great Expectations Core 1.x validation workflow for Orders dataset.

Builds:
- Ephemeral Data Source & Dataframe Asset / Batch Definition
- Expectation Suite with column type, not-null, unique, set, and range rules
- Validation Definition binding batch definition to expectation suite
- Checkpoint running validations
- Severity classification (critical, warning, info) and action determination (BLOCK, QUARANTINE, WARN, PASS)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:  # friendlier classroom failure
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_orders_suite() -> gx.ExpectationSuite:
    """Construct expectation suite based on contracts/orders_contract.yaml."""
    suite = gx.ExpectationSuite(name="orders_expectation_suite")

    expectations = [
        # order_id: integer, required, unique, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_id",
            notes="severity:critical",
        ),
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="order_id",
            notes="severity:critical",
        ),
        gx.expectations.ExpectColumnValuesToBeOfType(
            column="order_id",
            type_="int64",
            notes="severity:critical",
        ),
        # customer_id: string, required, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="customer_id",
            notes="severity:critical",
        ),
        # amount: number, min 0, required, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="amount",
            notes="severity:critical",
        ),
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="amount",
            min_value=0,
            notes="severity:critical",
        ),
        # currency: accepted_values [USD, VND], required, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="currency",
            notes="severity:critical",
        ),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="currency",
            value_set=["USD", "VND"],
            notes="severity:critical",
        ),
        # status: accepted_values [pending, completed, refunded, cancelled], required, warning
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="status",
            notes="severity:warning",
        ),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
            notes="severity:warning",
        ),
        # created_at: datetime, required, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="created_at",
            notes="severity:critical",
        ),
        # updated_at: datetime, required, critical
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="updated_at",
            notes="severity:critical",
        ),
    ]

    for exp in expectations:
        suite.add_expectation(exp)

    return suite


def run_orders_checkpoint(df: pd.DataFrame) -> dict[str, Any]:
    """Execute GX ValidationDefinition and Checkpoint on the orders dataframe."""
    context = gx.get_context(mode="ephemeral")

    # 1. Ephemeral Data Source & Dataframe Asset
    data_source = context.data_sources.add_pandas("orders_datasource")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("orders_batch_def")

    # 2. Expectation Suite
    suite = build_orders_suite()
    suite = context.suites.add(suite)

    # 3. Validation Definition
    val_def = gx.ValidationDefinition(
        name="orders_validation_definition",
        data=batch_definition,
        suite=suite,
    )
    val_def = context.validation_definitions.add(val_def)

    # 4. Checkpoint
    checkpoint = gx.Checkpoint(
        name="orders_checkpoint",
        validation_definitions=[val_def],
    )
    checkpoint = context.checkpoints.add(checkpoint)

    # 5. Run Checkpoint
    checkpoint_result = checkpoint.run(batch_parameters={"dataframe": df})

    # 6. Parse and classify expectation results
    detailed_results = []
    has_critical_failure = False
    has_warning_failure = False
    has_info_failure = False

    for _, val_res in checkpoint_result.run_results.items():
        for exp_res in val_res.results:
            exp_type = exp_res.expectation_config.type
            kwargs = exp_res.expectation_config.kwargs
            notes = exp_res.expectation_config.notes or ""
            col = kwargs.get("column", "table")
            success = bool(exp_res.success)

            severity = "warning"
            if "severity:critical" in notes:
                severity = "critical"
            elif "severity:info" in notes:
                severity = "info"
            elif "severity:warning" in notes:
                severity = "warning"

            if not success:
                if severity == "critical":
                    has_critical_failure = True
                elif severity == "warning":
                    has_warning_failure = True
                else:
                    has_info_failure = True

            detailed_results.append({
                "expectation": exp_type,
                "column": col,
                "severity": severity,
                "success": success,
                "result": exp_res.result,
            })

    # 7. Action determination
    if has_critical_failure:
        action = "BLOCK"
    elif has_warning_failure:
        action = "QUARANTINE"
    elif has_info_failure:
        action = "WARN"
    else:
        action = "PASS"

    return {
        "success": bool(checkpoint_result.success),
        "action": action,
        "results": detailed_results,
        "checkpoint_result": checkpoint_result,
    }


def main() -> None:
    orders_csv = ROOT / "data" / "incoming" / "orders.csv"
    if not orders_csv.exists():
        print(f"File not found: {orders_csv}. Running reset_lab...")
        from scripts.reset_lab import main as reset_main
        reset_main()

    df = pd.read_csv(orders_csv)
    print(f"Validating orders dataframe ({len(df)} rows) with Great Expectations Checkpoint...")

    summary = run_orders_checkpoint(df)

    print("\n" + "=" * 80)
    print(f"{'EXPECTATION':<35} {'COLUMN':<15} {'SEVERITY':<10} {'STATUS':<10}")
    print("=" * 80)
    for res in summary["results"]:
        status = "PASSED" if res["success"] else "FAILED"
        print(f"{res['expectation']:<35} {str(res['column']):<15} {res['severity']:<10} {status:<10}")

    print("=" * 80)
    print(f"Overall Checkpoint Status : {'SUCCESS' if summary['success'] else 'FAILED'}")
    print(f"Determined Pipeline Action: {summary['action']}")
    print("=" * 80)


if __name__ == "__main__":
    main()

