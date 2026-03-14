from backend.inference_client import infer_structure

from tests.helpers import build_synthetic_structure_image


def test_infer_structure_detects_raw_fragments_and_openings_from_image():
    inferred = infer_structure(build_synthetic_structure_image())

    assert inferred["source"] == "heuristic_local"
    assert inferred["structure_meta"]["image_size"] == {"width": 220, "height": 160}
    assert len(inferred["walls"]) >= 7
    assert len(inferred["openings"]) == 2
    assert {opening["kind"] for opening in inferred["openings"]} == {"door", "window"}
