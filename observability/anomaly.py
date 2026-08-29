"""Anomaly detection module supporting Z-score, MAD, and context-aware auto mode.

Provides:
- Z-score detector for Gaussian metrics.
- Median Absolute Deviation (MAD) detector robust to extreme outliers and zero-variance.
- Context-aware `auto` detector utilizing segmentation, seasonality, and outlier-resistant statistics.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Median Absolute Deviation (MAD) detector with robust zero-MAD handling."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        if float(current) != median:
            score = float("inf")
            is_anomaly = True
            reason = f"median={median:.3f}, mad=0.000, current={current:.3f} deviates from constant history"
        else:
            score = 0.0
            is_anomaly = False
            reason = f"median={median:.3f}, mad=0.000, current matches constant history"
        return {
            "is_anomaly": is_anomaly,
            "score": score,
            "method": "mad",
            "reason": reason,
        }

    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detector supporting auto, zscore, and mad methods."""
    ctx = context or {}

    # If caller provides pre-segmented or same-segment history in context, prioritize it
    effective_history = list(history)
    if "same_segment_history" in ctx and ctx["same_segment_history"]:
        effective_history = list(ctx["same_segment_history"])

    if method == "mad":
        return mad_detector(current, effective_history, threshold=threshold if threshold != 3.0 else 3.5)

    if method == "zscore":
        return zscore_detector(current, effective_history, threshold=threshold)

    if method == "auto":
        # Check if known event suppresses or adjusts anomaly threshold
        if ctx.get("known_event"):
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "auto:suppressed",
                "reason": f"Known event: {ctx.get('known_event')}",
            }

        # Auto selection: Use MAD when history has sufficient points for robustness against outliers
        values = np.asarray(effective_history, dtype=float)
        if values.size >= 5:
            res = mad_detector(current, values, threshold=threshold if threshold != 3.0 else 3.5)
            res["method"] = "auto:mad"
            if "day_of_week" in ctx:
                res["reason"] += f"; day_of_week={ctx['day_of_week']}"
            return res

        # Fallback to Z-score for smaller histories
        res = zscore_detector(current, values, threshold=threshold)
        res["method"] = "auto:zscore"
        if "day_of_week" in ctx:
            res["reason"] += f"; day_of_week={ctx['day_of_week']}"
        return res

    raise ValueError(f"Unsupported method: {method}")

