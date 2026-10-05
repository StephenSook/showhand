from showhand.residual import ResidualRow, paired_agreement_residual


def test_residual_harness_on_synthetic_labels_only() -> None:
    synthetic = [
        ResidualRow("synthetic-1", True, True, False),
        ResidualRow("synthetic-2", False, False, True),
        ResidualRow("synthetic-3", True, True, True),
        ResidualRow("synthetic-4", False, True, False),
    ]
    first = paired_agreement_residual(synthetic, replicates=200, seed=7)
    second = paired_agreement_residual(synthetic, replicates=200, seed=7)
    assert first == second
    assert first["n"] == 4
    assert first["label_source"] == "human"
    assert "fused_kappa" in first
    assert "paired_kappa_difference" in first
