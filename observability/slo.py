from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = round(1.0 - target, 10)
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = round(actual_bad_rate / allowed_bad_rate, 6)
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, round(1.0 - consumed_fraction, 6)),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "multiwindow",
) -> dict[str, Any]:
    """Evaluate multi-window burn rate according to Google SRE alerting principles.

    - Sustained fast burn (both short and long windows exceed critical threshold): PAGE (critical).
    - Transient spike (short window high, long window low/normal): NO PAGE (warning/info).
    - Slow burn (moderate consumption across both windows): NO PAGE (warning ticket).
    """
    short_burn = float(short_window_burn)
    long_burn = float(long_window_burn)

    # 1. Critical fast burn: 1h burn > 14 and 6h burn > 14 (or 2% error budget consumed rapidly)
    if short_burn >= 14.0 and long_burn >= 14.0:
        return {
            "page": True,
            "severity": "critical",
            "reason": f"sustained_fast_burn: short={short_burn:.2f}, long={long_burn:.2f}",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
        }

    # 2. Elevated fast burn: 6h burn >= 6.0 and 24h burn >= 6.0 (5% budget in 6h)
    if short_burn >= 6.0 and long_burn >= 6.0:
        return {
            "page": True,
            "severity": "critical",
            "reason": f"sustained_high_burn: short={short_burn:.2f}, long={long_burn:.2f}",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
        }

    # 3. Transient spike: Short window high, but long window has not accumulated burn
    if short_burn >= 6.0 and long_burn < 6.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"transient_spike_suppressed: short={short_burn:.2f}, long={long_burn:.2f}",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
        }

    # 4. Slow burn: Continuous burn rate above normal (1.0x to 6.0x)
    if short_burn >= 1.0 and long_burn >= 1.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"slow_burn_warning: short={short_burn:.2f}, long={long_burn:.2f}",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
        }

    # 5. Normal / Healthy
    return {
        "page": False,
        "severity": "info",
        "reason": f"normal: short={short_burn:.2f}, long={long_burn:.2f}",
        "short_window_burn": short_burn,
        "long_window_burn": long_burn,
    }

