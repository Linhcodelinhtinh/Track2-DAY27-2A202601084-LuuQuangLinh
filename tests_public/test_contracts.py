from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

from src.contract_validator import (
    determine_action,
    failed_issues,
    load_contract,
    quarantine_records,
    validate_dataframe,
)
from student_api import validate_orders

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "orders_contract.yaml"


def healthy_df() -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    return pd.DataFrame([
        {
            "order_id": 1,
            "customer_id": "C1",
            "amount": 10.0,
            "currency": "USD",
            "status": "completed",
            "created_at": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        {
            "order_id": 2,
            "customer_id": "C2",
            "amount": 20.0,
            "currency": "USD",
            "status": "pending",
            "created_at": (now - timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": (now - timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    ])


def failed(issues):
    return [i for i in issues if not i["passed"]]


def test_healthy_contract_passes_all_checks():
    issues = validate_orders(healthy_df(), CONTRACT)
    assert not failed(issues)
    assert determine_action(issues) == "pass"


def test_duplicate_order_id_is_detected():
    df = healthy_df()
    df.loc[1, "order_id"] = 1
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "unique" and i["column"] == "order_id" for i in issues)
    assert determine_action(issues) == "block"


def test_invalid_currency_is_detected():
    df = healthy_df()
    df.loc[0, "currency"] = "BTC"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "accepted_values" and i["column"] == "currency" for i in issues)
    assert determine_action(issues) == "block"


def test_type_validation_invalid_integer():
    df = healthy_df()
    df.loc[0, "order_id"] = "not_an_int"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "type" and i["column"] == "order_id" for i in issues)
    assert determine_action(issues) == "block"


def test_type_validation_invalid_datetime():
    df = healthy_df()
    df.loc[0, "created_at"] = "invalid_timestamp_value"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "type" and i["column"] == "created_at" for i in issues)


def test_freshness_delay_breach_detected():
    df = healthy_df()
    # Set updated_at to 2 hours ago (> 30 min max_delay)
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    df["updated_at"] = old_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = failed(validate_orders(df, CONTRACT))
    freshness_issues = [i for i in issues if i["check"] == "freshness"]
    assert len(freshness_issues) == 1
    assert freshness_issues[0]["passed"] is False
    assert freshness_issues[0]["severity"] == "warning"


def test_severity_levels_and_action_determination():
    contract_data = load_contract(CONTRACT)
    df = healthy_df()

    # Warning failure: invalid status (severity: warning)
    df_warn = df.copy()
    df_warn.loc[0, "status"] = "unknown_status"
    issues_warn = validate_dataframe(df_warn, contract_data)
    assert determine_action(issues_warn, contract_data) == "quarantine"
    assert len(failed_issues(issues_warn, min_severity="critical")) == 0
    assert len(failed_issues(issues_warn, min_severity="warning")) >= 1

    # Critical failure: negative amount (severity: critical)
    df_crit = df.copy()
    df_crit.loc[0, "amount"] = -100.0
    issues_crit = validate_dataframe(df_crit, contract_data)
    assert determine_action(issues_crit, contract_data) == "block"
    assert len(failed_issues(issues_crit, min_severity="critical")) >= 1


def test_quarantine_records_partitions_correctly():
    contract_data = load_contract(CONTRACT)
    df = healthy_df()
    # Append an invalid row (status = 'corrupted')
    bad_row = df.iloc[[0]].copy()
    bad_row["order_id"] = 999
    bad_row["status"] = "corrupted"
    df_mixed = pd.concat([df, bad_row], ignore_index=True)

    valid_df, quarantined_df = quarantine_records(df_mixed, contract_data)
    assert len(valid_df) == 2
    assert len(quarantined_df) == 1
    assert quarantined_df.iloc[0]["order_id"] == 999

