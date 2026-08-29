"""Contract validator supporting type validation, freshness, severity levels, and actions.

Covers:
- Not-null, uniqueness, accepted values, and numeric range constraints.
- Declared data type validation (integer, number, string, datetime, boolean).
- Contract-level dataset freshness checks.
- Severity classification: critical, warning, info.
- Action determination: block, quarantine, warn, pass.
- Row-level quarantine filtering.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


SEVERITY_ORDER: dict[str, int] = {
    "info": 0,
    "warning": 1,
    "critical": 2,
}

DEFAULT_ACTION_POLICY: dict[str, str] = {
    "critical": "block",
    "warning": "quarantine",
    "info": "warn",
}


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity.lower(),
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_type(series: pd.Series, expected_type: str) -> tuple[bool, int, str]:
    """Validate that non-null values conform to the expected data type."""
    non_null = series.dropna()
    if non_null.empty:
        return True, 0, "No non-null values to validate"

    expected = expected_type.lower()
    invalid_mask = pd.Series(False, index=non_null.index)

    if expected in ("integer", "int", "int64", "bigint"):
        def is_valid_int(v: Any) -> bool:
            if isinstance(v, (bool, np.bool_)):
                return False
            if isinstance(v, (int, np.integer)):
                return True
            if isinstance(v, (float, np.floating)):
                return not np.isnan(v) and float(v).is_integer()
            if isinstance(v, str):
                s = v.strip()
                if s.startswith(("-", "+")):
                    return s[1:].isdigit()
                return s.isdigit()
            return False

        invalid_mask = ~non_null.map(is_valid_int)

    elif expected in ("number", "float", "numeric", "double", "float64"):
        def is_valid_num(v: Any) -> bool:
            if isinstance(v, (bool, np.bool_)):
                return False
            if isinstance(v, (int, float, np.number)):
                return not np.isnan(v)
            try:
                float(str(v).strip())
                return True
            except (ValueError, TypeError):
                return False

        invalid_mask = ~non_null.map(is_valid_num)

    elif expected in ("string", "str", "text", "varchar"):
        def is_valid_str(v: Any) -> bool:
            return isinstance(v, str)

        invalid_mask = ~non_null.map(is_valid_str)

    elif expected in ("datetime", "timestamp", "date"):
        parsed = pd.to_datetime(non_null, errors="coerce", utc=True, format="mixed")
        invalid_mask = parsed.isna()

    elif expected in ("boolean", "bool"):
        def is_valid_bool(v: Any) -> bool:
            if isinstance(v, (bool, np.bool_)):
                return True
            if isinstance(v, str) and v.lower() in ("true", "false", "1", "0"):
                return True
            if isinstance(v, (int, float)) and v in (0, 1):
                return True
            return False

        invalid_mask = ~non_null.map(is_valid_bool)

    else:
        return True, 0, f"unsupported_type_check: {expected_type}"

    invalid_count = int(invalid_mask.sum())
    return (invalid_count == 0), invalid_count, f"invalid_type_count={invalid_count}; expected={expected_type}"


def validate_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
    *,
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    columns = contract.get("columns", {})

    for column, rules in columns.items():
        severity = rules.get("severity", "warning").lower()
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        # 1. Not-null validation
        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        # 2. Type validation
        if "type" in rules:
            expected_type = rules["type"]
            passed_type, invalid_count, details = _check_type(series, expected_type)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=passed_type,
                    details=details,
                )
            )

        # 3. Uniqueness validation
        if rules.get("unique"):
            duplicate_count = int(series.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        # 4. Accepted values validation
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        # 5. Numeric range validation
        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

    # 6. Freshness validation
    freshness = contract.get("freshness")
    if freshness and isinstance(freshness, dict):
        col = freshness.get("column")
        max_delay = freshness.get("max_delay_minutes", 60)
        freshness_severity = freshness.get("severity", "warning").lower()

        if col is None or col not in df.columns:
            issues.append(
                _issue(
                    "freshness",
                    column=col,
                    severity=freshness_severity,
                    passed=False,
                    details=f"Freshness column '{col}' not found in dataframe",
                )
            )
        else:
            ts_series = pd.to_datetime(df[col], utc=True, errors="coerce")
            valid_ts = ts_series.dropna()
            if valid_ts.empty:
                issues.append(
                    _issue(
                        "freshness",
                        column=col,
                        severity=freshness_severity,
                        passed=False,
                        details=f"No valid timestamps in freshness column '{col}'",
                    )
                )
            else:
                latest_ts = valid_ts.max()
                ref_time = reference_time if reference_time is not None else datetime.now(timezone.utc)
                if not isinstance(ref_time, pd.Timestamp):
                    ref_time = pd.Timestamp(ref_time)
                if ref_time.tzinfo is None:
                    ref_time = ref_time.tz_localize("UTC")

                delay_minutes = (ref_time - latest_ts).total_seconds() / 60.0
                passed = (delay_minutes <= max_delay)
                issues.append(
                    _issue(
                        "freshness",
                        column=col,
                        severity=freshness_severity,
                        passed=passed,
                        details=f"delay_minutes={delay_minutes:.2f}; max_delay_minutes={max_delay}",
                    )
                )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    """Filter failed issues optionally bounded by a minimum severity threshold."""
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    threshold = SEVERITY_ORDER.get(min_severity.lower(), 1)
    return [i for i in failed if SEVERITY_ORDER.get(i.get("severity", "warning").lower(), 1) >= threshold]


def determine_action(issues: list[dict[str, Any]], contract: dict[str, Any] | None = None) -> str:
    """Determine operational action (block, quarantine, warn, pass) based on validation results."""
    failed = [i for i in issues if not i.get("passed", False)]
    if not failed:
        return "pass"

    action_policy = dict(DEFAULT_ACTION_POLICY)
    if contract and "actions" in contract and isinstance(contract["actions"], dict):
        action_policy.update(contract["actions"])

    severities = {i.get("severity", "warning").lower() for i in failed}
    if "critical" in severities:
        return action_policy.get("critical", "block")
    if "warning" in severities:
        return action_policy.get("warning", "quarantine")
    if "info" in severities:
        return action_policy.get("info", "warn")
    return "warn"


def categorize_issues(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group issues into passed, critical_fails, warning_fails, and info_fails."""
    result: dict[str, list[dict[str, Any]]] = {
        "passed": [],
        "critical_fails": [],
        "warning_fails": [],
        "info_fails": [],
    }
    for issue in issues:
        if issue.get("passed", False):
            result["passed"].append(issue)
        else:
            sev = issue.get("severity", "warning").lower()
            if sev == "critical":
                result["critical_fails"].append(issue)
            elif sev == "warning":
                result["warning_fails"].append(issue)
            else:
                result["info_fails"].append(issue)
    return result


def quarantine_records(df: pd.DataFrame, contract: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partition a dataframe into (valid_records, quarantined_records) based on row-level rule violations."""
    invalid_mask = pd.Series(False, index=df.index)
    columns = contract.get("columns", {})

    for column, rules in columns.items():
        if column not in df.columns:
            if rules.get("required", False):
                return df.iloc[0:0], df.copy()
            continue

        series = df[column]

        if rules.get("required", False):
            invalid_mask |= series.isna()

        if "type" in rules:
            exp = rules["type"].lower()
            if exp in ("integer", "int"):
                def _is_int(v: Any) -> bool:
                    if isinstance(v, (bool, np.bool_)) or pd.isna(v):
                        return True
                    if isinstance(v, (int, np.integer)):
                        return True
                    if isinstance(v, (float, np.floating)):
                        return float(v).is_integer()
                    if isinstance(v, str):
                        s = v.strip()
                        return (s[1:].isdigit() if s.startswith(("-", "+")) else s.isdigit())
                    return False
                invalid_mask |= ~series.map(_is_int)

        if rules.get("unique"):
            invalid_mask |= series.duplicated(keep=False)

        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask |= (series.notna() & ~series.isin(accepted))

        if "min" in rules or "max" in rules:
            num = pd.to_numeric(series, errors="coerce")
            if "min" in rules:
                invalid_mask |= (num < rules["min"])
            if "max" in rules:
                invalid_mask |= (num > rules["max"])

    valid_df = df[~invalid_mask].copy()
    quarantined_df = df[invalid_mask].copy()
    return valid_df, quarantined_df

