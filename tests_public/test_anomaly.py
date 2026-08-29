from student_api import detect_metric


def test_large_volume_drop_is_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(300, history, method="zscore")
    assert result["is_anomaly"] is True


def test_stable_value_is_not_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(1002, history, method="zscore")
    assert result["is_anomaly"] is False


def test_mad_detector_handles_outliers():
    # History has extreme outlier, but median and MAD stay robust
    history = [100, 102, 98, 101, 100, 5000, 99]
    result = detect_metric(101, history, method="mad")
    assert result["is_anomaly"] is False


def test_mad_detector_handles_zero_mad():
    history = [100, 100, 100, 100, 100]
    # Matching history
    assert detect_metric(100, history, method="mad")["is_anomaly"] is False
    # Deviating from constant history
    assert detect_metric(150, history, method="mad")["is_anomaly"] is True


def test_auto_method_with_context_segmentation():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    context = {"day_of_week": 6, "same_segment_history": [300, 310, 295, 305, 300]}
    # Current value 302 matches Sunday segment
    result = detect_metric(302, history, method="auto", context=context)
    assert result["is_anomaly"] is False

