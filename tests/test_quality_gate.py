from backend.quality_gate import apply_quality_gate
from tests.helpers import build_low_quality_structure, build_manual_structure


def test_quality_gate_passes_for_reasonable_structure():
    structure = build_manual_structure()
    metrics, flags = apply_quality_gate(
        structure,
        {
            "wall_count": 5,
            "opening_count": 2,
            "exterior_wall_count": 4,
        },
        [],
    )

    assert metrics["quality_gate_passed"] is True
    assert metrics["quality_gate_reasons"] == []
    assert flags == []


def test_quality_gate_flags_missing_openings_and_exterior_shell():
    structure = build_low_quality_structure()
    metrics, flags = apply_quality_gate(
        structure,
        {
            "wall_count": 5,
            "opening_count": 0,
            "exterior_wall_count": 0,
        },
        [],
    )

    assert metrics["quality_gate_passed"] is False
    assert "no_openings_detected" in metrics["quality_gate_reasons"]
    assert "anomalous_exterior_wall_count" in metrics["quality_gate_reasons"]
    assert flags
