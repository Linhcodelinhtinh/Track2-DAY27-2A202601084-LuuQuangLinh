from student_api import rag_embedding_shift, rag_length_shift


def test_rag_length_collapse_is_detected():
    baseline_batch_means = [40, 42, 39, 41, 43, 40, 42]
    current_texts = ["x y", "a b c", "one two"]
    assert rag_length_shift(current_texts, baseline_batch_means)["is_anomaly"] is True


def test_rag_embedding_norm_shift_detected():
    baseline_norms = [1.0, 1.02, 0.98, 1.01, 0.99]
    # Norm collapse
    current_norms = [0.01, 0.02, 0.01]
    assert rag_embedding_shift(current_norms, baseline_norms)["is_anomaly"] is True

