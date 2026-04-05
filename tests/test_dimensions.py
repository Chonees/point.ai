import ezdxf
import numpy as np

import backend.components.dimensions as dimensions_module
import backend.scale_calibrator as scale_calibrator_module
from backend.components.dimensions import generate_all_dimensions
from backend.scale_calibrator import calibrate_scale


def _simple_annotations() -> list[dict]:
    return [
        {"type": "wall", "x1": 20, "y1": 20, "x2": 120, "y2": 20},
        {"type": "wall", "x1": 20, "y1": 100, "x2": 120, "y2": 100},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 20, "y2": 100},
        {"type": "wall", "x1": 120, "y1": 20, "x2": 120, "y2": 100},
        {"type": "window", "x1": 50, "y1": 20, "x2": 70, "y2": 20},
        {"type": "label", "x1": 60, "y1": 60, "x2": 60, "y2": 60, "roomName": "Bedroom 1", "sqft": 50},
    ]


def _simple_wall_mask() -> np.ndarray:
    mask = np.zeros((140, 140), dtype=np.uint8)
    mask[20:101, 20] = 255
    mask[20:101, 120] = 255
    mask[20, 20:121] = 255
    mask[100, 20:121] = 255
    return mask


def _fragmented_annotations() -> list[dict]:
    return [
        {"type": "wall", "x1": 40, "y1": 40, "x2": 120, "y2": 40},
        {"type": "wall", "x1": 160, "y1": 40, "x2": 240, "y2": 40},
        {"type": "wall", "x1": 40, "y1": 160, "x2": 100, "y2": 160},
        {"type": "wall", "x1": 140, "y1": 160, "x2": 240, "y2": 160},
        {"type": "wall", "x1": 40, "y1": 40, "x2": 40, "y2": 160},
        {"type": "wall", "x1": 240, "y1": 40, "x2": 240, "y2": 160},
        {"type": "wall", "x1": 46, "y1": 46, "x2": 118, "y2": 46},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 40, "y2": 20},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 20, "y2": 40},
        {"type": "window", "x1": 120, "y1": 40, "x2": 160, "y2": 40},
        {"type": "label", "x1": 90, "y1": 90, "x2": 90, "y2": 90, "roomName": "Living", "sqft": 100},
    ]


def _fragmented_wall_mask() -> np.ndarray:
    mask = np.zeros((220, 320), dtype=np.uint8)
    mask[40:161, 40:48] = 255
    mask[40:161, 232:240] = 255
    mask[40:48, 40:240] = 255
    mask[152:160, 40:240] = 255
    mask[40:161, 138:146] = 255
    mask[20:40, 20:28] = 255
    mask[20:28, 20:40] = 255
    return mask


def _notched_room_annotations() -> list[dict]:
    return [
        {"type": "wall", "x1": 20, "y1": 20, "x2": 120, "y2": 20},
        {"type": "wall", "x1": 20, "y1": 100, "x2": 150, "y2": 100},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 20, "y2": 100},
        {"type": "wall", "x1": 120, "y1": 20, "x2": 120, "y2": 60},
        {"type": "wall", "x1": 150, "y1": 60, "x2": 150, "y2": 100},
        {"type": "wall", "x1": 120, "y1": 60, "x2": 150, "y2": 60},
        {"type": "label", "x1": 60, "y1": 40, "x2": 60, "y2": 40, "roomName": "Great Room", "sqft": 60},
    ]


def _notched_room_wall_mask() -> np.ndarray:
    mask = np.zeros((140, 180), dtype=np.uint8)
    mask[20:101, 20] = 255
    mask[20, 20:121] = 255
    mask[100, 20:151] = 255
    mask[20:61, 120] = 255
    mask[60, 120:151] = 255
    mask[60:101, 150] = 255
    return mask


def _two_room_annotations_without_sqft() -> list[dict]:
    return [
        {"type": "wall", "x1": 20, "y1": 20, "x2": 120, "y2": 20},
        {"type": "wall", "x1": 20, "y1": 100, "x2": 120, "y2": 100},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 20, "y2": 100},
        {"type": "wall", "x1": 120, "y1": 20, "x2": 120, "y2": 100},
        {"type": "wall", "x1": 70, "y1": 20, "x2": 70, "y2": 100},
        {"type": "label", "x1": 45, "y1": 60, "x2": 45, "y2": 60, "roomName": "Bedroom 1"},
        {"type": "label", "x1": 95, "y1": 60, "x2": 95, "y2": 60, "roomName": "Bedroom 2"},
    ]


def _two_room_wall_mask() -> np.ndarray:
    mask = np.zeros((140, 140), dtype=np.uint8)
    mask[20:101, 20] = 255
    mask[20:101, 120] = 255
    mask[20, 20:121] = 255
    mask[100, 20:121] = 255
    mask[20:101, 70] = 255
    return mask


def _open_plan_duplicate_label_annotations() -> list[dict]:
    return [
        {"type": "wall", "x1": 20, "y1": 20, "x2": 120, "y2": 20},
        {"type": "wall", "x1": 20, "y1": 100, "x2": 120, "y2": 100},
        {"type": "wall", "x1": 20, "y1": 20, "x2": 20, "y2": 100},
        {"type": "wall", "x1": 120, "y1": 20, "x2": 120, "y2": 100},
        {"type": "label", "x1": 45, "y1": 60, "x2": 45, "y2": 60, "roomName": "Dining"},
        {"type": "label", "x1": 95, "y1": 60, "x2": 95, "y2": 60, "roomName": "Living"},
    ]


def _open_plan_duplicate_label_wall_mask() -> np.ndarray:
    return _simple_wall_mask()


def test_generate_all_dimensions_keeps_only_exterior_wall_and_window_center_dims():
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()

    counts = generate_all_dimensions(
        doc,
        msp,
        _simple_annotations(),
        scale_ipp=1.0,
        image_shape=(140, 140),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_mask=_simple_wall_mask(),
        render_dimensions=True,
    )

    assert counts["exterior_wall_dims"] == 4
    assert counts["window_center_dims"] == 2
    assert counts["room_labels"] == 1
    assert counts["room_size_labels"] == 1
    assert counts["sqft_labels"] == 1

    dims = list(msp.query('DIMENSION[layer=="DIMS"]'))
    assert len(dims) == 6
    assert all("'" in entity.dxf.text and '"' in entity.dxf.text for entity in dims)

    texts = [entity.dxf.text for entity in msp.query('TEXT[layer=="ROOM LBLS"]')]
    assert "BEDROOM 1" in texts
    assert '8\'-2" x 6\'-6"' in texts
    assert "50 SQ FT" in texts


def test_generate_all_dimensions_skips_dim_entities_without_scale():
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()

    counts = generate_all_dimensions(
        doc,
        msp,
        _simple_annotations(),
        scale_ipp=1.0,
        image_shape=(140, 140),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_mask=_simple_wall_mask(),
        render_dimensions=False,
    )

    assert counts["exterior_wall_dims"] == 0
    assert counts["window_center_dims"] == 0
    assert counts["room_labels"] == 1
    assert counts["room_size_labels"] == 0
    assert counts["sqft_labels"] == 1

    dims = list(msp.query('DIMENSION[layer=="DIMS"]'))
    assert not dims

    texts = [entity.dxf.text for entity in msp.query('TEXT[layer=="ROOM LBLS"]')]
    assert "BEDROOM 1" in texts
    assert "50 SQ FT" in texts
    assert all(" x " not in text for text in texts)


def test_generate_all_dimensions_uses_wall_mask_footprint_for_fragmented_exterior_walls():
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()

    counts = generate_all_dimensions(
        doc,
        msp,
        _fragmented_annotations(),
        scale_ipp=1.0,
        image_shape=(220, 320),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_mask=_fragmented_wall_mask(),
        render_dimensions=True,
    )

    assert counts["exterior_wall_dims"] == 4
    assert counts["window_center_dims"] == 2
    assert counts["room_labels"] == 1
    assert counts["room_size_labels"] == 1
    assert counts["sqft_labels"] == 1

    dims = list(msp.query('DIMENSION[layer=="DIMS"]'))
    assert len(dims) == 6
    assert all("'" in entity.dxf.text and '"' in entity.dxf.text for entity in dims)

    texts = [entity.dxf.text for entity in msp.query('TEXT[layer=="ROOM LBLS"]')]
    assert "LIVING" in texts
    assert "100 SQ FT" in texts


def test_generate_all_dimensions_emits_passing_window_chain_audit(monkeypatch):
    events: list[dict] = []

    def _capture(event: str, **fields):
        events.append({"event": event, **fields})

    monkeypatch.setattr(dimensions_module, "log_event", _capture)

    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()

    counts = generate_all_dimensions(
        doc,
        msp,
        _simple_annotations(),
        scale_ipp=1.0,
        image_shape=(140, 140),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_mask=_simple_wall_mask(),
        render_dimensions=True,
    )

    assert counts["exterior_wall_dims"] == 4
    audits = [event for event in events if event["event"] == "window_chain_audit"]
    assert len(audits) == 1
    assert audits[0]["status"] == "pass"
    assert audits[0]["wall_length_arch"] == '8\'-4"'
    assert audits[0]["generated_chain_sum_arch"] == '8\'-4"'
    assert audits[0]["generated_gap_px"] == 0.0

    summaries = [event for event in events if event["event"] == "dims_audit_summary"]
    assert len(summaries) == 1
    assert summaries[0]["audited_window_chains"] == 1
    assert summaries[0]["window_chain_pass"] == 1
    assert summaries[0]["window_chain_fail"] == 0


def test_room_metrics_use_face_to_face_seedline_instead_of_bbox():
    dims_text = dimensions_module._label_room_metrics(
        _notched_room_annotations(),
        _notched_room_wall_mask(),
        (140, 180),
        _notched_room_annotations()[-1],
        scale_ipp=1.0,
    )

    assert dims_text == '8\'-2" x 6\'-6"'
    assert dims_text != '10\'-8" x 6\'-6"'


def test_generate_all_dimensions_uses_total_area_to_compute_room_sqft_labels():
    annotations = _two_room_annotations_without_sqft()
    wall_mask = _two_room_wall_mask()
    measurement_context = calibrate_scale(
        annotations,
        wall_mask,
        (140, 140),
        total_area_sqft=100,
    )

    assert measurement_context is not None
    assert measurement_context["calibration_mode"] == "total_area"

    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    counts = generate_all_dimensions(
        doc,
        msp,
        annotations,
        scale_ipp=float(measurement_context["scale_ipp"]),
        image_shape=(140, 140),
        transform={"scale": 1.0, "offset_x": 0.0, "offset_y": 0.0},
        wall_mask=wall_mask,
        render_dimensions=True,
        measurement_context=measurement_context,
    )

    assert counts["room_labels"] == 2
    assert counts["room_size_labels"] == 2
    assert counts["sqft_labels"] == 2

    texts = [entity.dxf.text for entity in msp.query('TEXT[layer=="ROOM LBLS"]')]
    assert texts.count("50 SQ FT") == 2


def test_calibrate_scale_flags_duplicate_regions_for_open_plan_labels(monkeypatch):
    events: list[dict] = []

    def _capture(event: str, **fields):
        events.append({"event": event, **fields})

    monkeypatch.setattr(scale_calibrator_module, "log_event", _capture)

    measurement_context = scale_calibrator_module.calibrate_scale(
        _open_plan_duplicate_label_annotations(),
        _open_plan_duplicate_label_wall_mask(),
        (140, 140),
        total_area_sqft=100,
    )

    assert measurement_context is not None
    room_analysis = measurement_context["room_analysis"]
    assert room_analysis["duplicated_region_count"] == 1
    assert room_analysis["overlapping_label_count"] == 1

    summaries = [event for event in events if event["event"] == "room_area_audit_summary"]
    assert len(summaries) == 1
    assert summaries[0]["duplicated_region_count"] == 1
    assert summaries[0]["overlapping_label_count"] == 1
    assert summaries[0]["raw_sum_sqft"] > summaries[0]["total_area_sqft"]
