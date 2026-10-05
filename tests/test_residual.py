from showhand.residual import ResidualRow, paired_agreement_residual


def test_residual_harness_on_synthetic_labels_only() -> None:
    pattern = [
        (True, True, False),
        (False, False, True),
        (True, True, True),
        (False, True, False),
    ]
    synthetic = [
        ResidualRow(f"synthetic-{index:02d}", *pattern[index % len(pattern)]) for index in range(20)
    ]
    first = paired_agreement_residual(synthetic, replicates=200, seed=7, label_source="synthetic")
    second = paired_agreement_residual(synthetic, replicates=200, seed=7, label_source="synthetic")
    assert first == second
    assert first["n"] == 20
    assert first["label_source"] == "synthetic"
    assert "fused_kappa" in first
    assert "paired_kappa_difference" in first
