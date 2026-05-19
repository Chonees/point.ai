# Aggressive Auto Openings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore high-recall automatic door/window placement by reusing the legacy annotation-first openings path, auto-filling swing/side semantics in the backend, and removing the current need for human interaction.

**Architecture:** Keep MitUNet as the wall source and move doors/windows back to a CubiCasa → reanchor → auto-annotation pipeline. Do not force openings through the current structural postprocess path for production DXF output; instead, enrich them with automatic swing/side fallbacks and expose review/debug signals. Fix the preview renderer so artifact screenshots match the actual annotation coordinates.

**Tech Stack:** Python 3.14, FastAPI backend, CubiCasa + MitUNet inference, OpenCV preview rendering, pytest.

---

## File Map

- Modify: `backend/ensemble_inference.py` — restore the legacy high-recall reanchor path, add automatic swing/side enrichment, and emit richer debug metrics.
- Modify: `backend/services/parse_service.py` — patch post-parse quality metrics for the annotation-first ensemble path so the API does not report false “no openings detected” when auto-annotations exist.
- Modify: `backend/artifacts.py` — fix preview Y-coordinate handling for structured openings and optionally persist richer inference debug payloads alongside the image artifacts.
- Modify: `tests/test_ensemble_inference.py` — capture desired behavior for legacy reanchor recall plus automatic semantic enrichment.
- Modify/Create: `tests/test_v2_api.py` and `tests/test_artifacts.py` — lock the API/preview regressions.

### Task 1: Lock the target behavior with failing tests

**Files:**
- Modify: `tests/test_ensemble_inference.py`
- Modify: `tests/test_v2_api.py`
- Create: `tests/test_artifacts.py`

- [ ] **Step 1: Add a failing regression test for automatic door swing fallback**

```python
def test_infer_ensemble_auto_fills_missing_door_swing(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": "door-no-swing",
                "kind": "door",
                "position": {"x": 110.0, "y": 74.0},
                "span": 28.0,
                "orientation": "vertical",
                "confidence": 0.55,
                "door_type": "normal",
                "swing": None,
            }
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    doors = [ann for ann in result["_auto_annotations"] if ann["type"] == "door"]
    assert len(doors) == 1
    assert doors[0]["swing"] in {"left", "right"}
```

- [ ] **Step 2: Add a failing regression test for automatic window side fallback**

```python
def test_infer_ensemble_auto_fills_window_side_when_missing(monkeypatch):
    _patch_models(
        monkeypatch,
        cubicasa_openings=[
            {
                "id": "window-no-side",
                "kind": "window",
                "position": {"x": 151.0, "y": 20.0},
                "span": 30.0,
                "orientation": "horizontal",
                "confidence": 0.55,
            }
        ],
    )

    result = infer_ensemble("data:image/png;base64,AAAA")

    windows = [ann for ann in result["_auto_annotations"] if ann["type"] == "window"]
    assert len(windows) == 1
    assert windows[0]["swing"] in {"up", "down"}
```

- [ ] **Step 3: Add a failing regression test for annotation-first quality metrics**

```python
def test_generate_dxf_endpoint_uses_auto_annotations_as_opening_signal(monkeypatch):
    def fake_infer(image: str, *, backend=None, options=None):
        result = build_mitunet_infer_result()
        result["source"] = "ensemble_local"
        result["openings"] = []
        result["_auto_annotations"] = [
            {"type": "window", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 20.0, "swing": "down"}
        ]
        result["inference_debug"] = {"backend": "ensemble_local", "model_variant": "ensemble"}
        return result

    monkeypatch.setattr("backend.services.parse_service.infer_structure", fake_infer)

    response = client.post(
        "/api/v2/generate-dxf",
        json={"image": build_synthetic_structure_image(), "model_variant": "ensemble"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["quality_metrics"]["opening_count"] == 1
    assert "no_openings_detected" not in payload["quality_metrics"]["quality_gate_reasons"]
```

- [ ] **Step 4: Add a failing regression test for preview Y-flip correctness**

```python
def test_build_preview_image_draws_structured_openings_in_image_coordinates():
    image = np.full((100, 100, 3), 255, dtype=np.uint8)
    image_b64 = encode_png_data(image)
    structure = {
        "walls": [],
        "openings": [
            {
                "kind": "window",
                "position": {"x": 40.0, "y": 20.0},
                "span": 16.0,
                "orientation": "horizontal",
            }
        ],
        "structure_meta": {
            "image_size": {"width": 100, "height": 100},
        },
    }

    preview = build_preview_image(structure, image_b64=image_b64)

    assert tuple(preview[80, 40]) != (255, 255, 255)
    assert tuple(preview[20, 40]) == (255, 255, 255)
```

- [ ] **Step 5: Run only the new tests and verify RED**

Run:

```bash
.\.venv\Scripts\python -m pytest tests/test_ensemble_inference.py -q
.\.venv\Scripts\python -m pytest tests/test_v2_api.py -q
.\.venv\Scripts\python -m pytest tests/test_artifacts.py -q
```

Expected: FAIL on the newly added assertions for missing auto-filled semantics, false `no_openings_detected`, and mirrored preview pixels.

- [ ] **Step 6: Commit the red tests**

```bash
git add tests/test_ensemble_inference.py tests/test_v2_api.py tests/test_artifacts.py
git commit -m "test(openings): capture aggressive auto-openings regressions"
```

### Task 2: Restore the high-recall annotation-first ensemble path

**Files:**
- Modify: `backend/ensemble_inference.py`
- Test: `tests/test_ensemble_inference.py`

- [ ] **Step 1: Reintroduce a legacy-style nearest-wall reanchor helper**

```python
def _reanchor_openings(
    cubicasa_openings: list[dict[str, Any]],
    mitunet_walls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not mitunet_walls or not cubicasa_openings:
        return []

    reanchored: list[dict[str, Any]] = []
    for opening in cubicasa_openings:
        pos = opening.get("position") or {}
        cx = float(pos.get("x", 0))
        cy = float(pos.get("y", 0))
        best_wall = None
        best_dist = float("inf")

        for wall in mitunet_walls:
            poly = wall.get("polyline", [])
            if len(poly) < 2:
                continue
            p0, p1 = poly[0], poly[1]
            wx0, wy0 = float(p0[0]), float(p0[1])
            wx1, wy1 = float(p1[0]), float(p1[1])
            wall_cx = (wx0 + wx1) / 2
            wall_cy = (wy0 + wy1) / 2
            dist = abs(cx - wall_cx) + abs(cy - wall_cy)
            if dist < best_dist:
                best_dist = dist
                best_wall = wall

        if best_wall is not None and best_dist <= _MAX_OPENING_WALL_DISTANCE:
            anchored = dict(opening)
            anchored["wall_id"] = best_wall["id"]
            anchored["_anchor_distance"] = round(best_dist, 1)
            reanchored.append(anchored)
    return reanchored
```

- [ ] **Step 2: Add automatic semantic enrichment helpers**

```python
def _auto_fill_opening_semantics(opening: dict[str, Any], wall: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    enriched = dict(opening)
    flags: list[str] = []

    if enriched.get("kind") == "door" and not enriched.get("swing"):
        enriched["swing"] = _fallback_door_swing(enriched, wall)
        enriched["_auto_swing"] = True
        flags.append(f"auto-filled door swing for {enriched['id']}")

    if enriched.get("kind") == "window" and not enriched.get("side"):
        enriched["side"] = _fallback_window_side(enriched, wall)
        enriched["_auto_side"] = True
        flags.append(f"auto-filled window side for {enriched['id']}")

    return enriched, flags
```

- [ ] **Step 3: Switch `infer_ensemble()` to annotation-first output**

```python
reanchored = _reanchor_openings(cubicasa_openings, mitunet_walls)
wall_lookup = {wall["id"]: wall for wall in normalized_mitunet_walls}
enriched: list[dict[str, Any]] = []
review_flags: list[str] = []

for opening in reanchored:
    wall = wall_lookup.get(opening.get("wall_id"))
    next_opening, flags = _auto_fill_opening_semantics(opening, wall)
    enriched.append(next_opening)
    review_flags.extend(flags)

auto_annotations = _openings_to_annotations(enriched, image_height=h)

return {
    "walls": mitunet_walls,
    "openings": [],
    "rooms": [],
    "source": ENSEMBLE_BACKEND,
    "_wall_mask": mitunet_result["_wall_mask"],
    "_image_shape": mitunet_result["_image_shape"],
    "_auto_annotations": auto_annotations,
    "inference_debug": {
        "backend": ENSEMBLE_BACKEND,
        "model_variant": "ensemble",
        "cubicasa": cubicasa_debug,
        "ensemble": {
            "reanchored_opening_count": len(reanchored),
            "auto_annotation_count": len(auto_annotations),
            "review_flags": review_flags,
        },
    },
}
```

- [ ] **Step 4: Run the ensemble tests and verify GREEN**

Run:

```bash
.\.venv\Scripts\python -m pytest tests/test_ensemble_inference.py -q
```

Expected: PASS with the new swing/side fallback assertions green.

- [ ] **Step 5: Commit the ensemble implementation**

```bash
git add backend/ensemble_inference.py tests/test_ensemble_inference.py
git commit -m "feat(openings): restore aggressive auto-annotation ensemble flow"
```

### Task 3: Make quality metrics compatible with annotation-first openings

**Files:**
- Modify: `backend/services/parse_service.py`
- Test: `tests/test_v2_api.py`

- [ ] **Step 1: Add a post-parse helper that promotes auto-annotations into opening metrics for ensemble**

```python
def _apply_auto_annotation_opening_metrics(parsed: dict, inferred: dict) -> None:
    auto_anns = [ann for ann in (inferred.get("_auto_annotations") or []) if ann.get("type") in {"door", "window"}]
    if not auto_anns:
        return

    metrics = parsed["quality_metrics"]
    metrics["opening_count"] = len(auto_anns)
    metrics["door_count"] = sum(1 for ann in auto_anns if ann["type"] == "door")
    metrics["window_count"] = sum(1 for ann in auto_anns if ann["type"] == "window")
    metrics["auto_annotation_opening_count"] = len(auto_anns)

    reasons = [reason for reason in metrics.get("quality_gate_reasons", []) if reason != "no_openings_detected"]
    metrics["quality_gate_reasons"] = reasons
    metrics["quality_gate_reason_count"] = len(reasons)
    metrics["quality_gate_passed"] = len(reasons) == 0

    parsed["review_flags"] = [
        flag for flag in parsed["review_flags"]
        if flag != "Quality gate: no openings detected."
    ]
    parsed["needs_review"] = bool(parsed["review_flags"])
```

- [ ] **Step 2: Call the helper only for ensemble/image inference results**

```python
parsed = parse_structure_payload(structure=inferred, scale_hint=scale_hint)
parsed["quality_metrics"]["inference_backend"] = (
    inferred.get("inference_debug", {}).get("backend") or inferred.get("source")
)
if (inferred.get("source") or inferred.get("inference_debug", {}).get("backend")) == ENSEMBLE_BACKEND:
    _apply_auto_annotation_opening_metrics(parsed, inferred)
parsed["_infer_result"] = inferred
```

- [ ] **Step 3: Run the API regression test and verify GREEN**

Run:

```bash
.\.venv\Scripts\python -m pytest tests/test_v2_api.py -q
```

Expected: PASS with `opening_count == 1` and no `no_openings_detected` reason for the mocked ensemble response.

- [ ] **Step 4: Commit the parse/quality patch**

```bash
git add backend/services/parse_service.py tests/test_v2_api.py
git commit -m "fix(api): count auto-annotated ensemble openings"
```

### Task 4: Fix preview coordinates and persist actionable debug artifacts

**Files:**
- Modify: `backend/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Add a helper to convert structured opening points into image Y-down coordinates when rendering over a real image**

```python
def _opening_center_for_preview(structure: dict[str, Any], opening: dict[str, Any]) -> tuple[int, int]:
    position = opening["position"]
    x = float(position["x"])
    y = float(position["y"])
    image_size = structure.get("structure_meta", {}).get("image_size") or {}
    image_h = image_size.get("height")
    if image_h is not None:
        y = float(image_h) - y
    return round(x), round(y)
```

- [ ] **Step 2: Use the helper inside `build_preview_image()` and save an explicit debug payload when available**

```python
for opening in structure.get("openings") or []:
    radius = max(4, round(opening["span"] / 4))
    color = (0, 200, 0) if opening["kind"] == "door" else (255, 0, 0)
    cx, cy = _opening_center_for_preview(structure, opening)
    cv2.circle(canvas, (round(cx + offset_x), round(cy + offset_y)), radius, color, 2)
```

```python
debug_payload = {
    "auto_annotations": auto_annotations or [],
    "inference_debug": structure.get("inference_debug") or {},
}
(run_dir / "openings_debug.json").write_text(json.dumps(debug_payload, indent=2), encoding="utf-8")
artifact_urls["openings_debug_url"] = f"/artifacts/{request_id}/openings_debug.json"
```

- [ ] **Step 3: Run the preview tests and verify GREEN**

Run:

```bash
.\.venv\Scripts\python -m pytest tests/test_artifacts.py -q
```

Expected: PASS with the drawn pixel appearing only at the image-space location, not the mirrored one.

- [ ] **Step 4: Commit the artifact fixes**

```bash
git add backend/artifacts.py tests/test_artifacts.py
git commit -m "fix(debug): align opening preview coordinates"
```

### Task 5: End-to-end verification without building

**Files:**
- Modify: `backend/ensemble_inference.py`
- Modify: `backend/services/parse_service.py`
- Modify: `backend/artifacts.py`
- Modify: `tests/test_ensemble_inference.py`
- Modify: `tests/test_v2_api.py`
- Create/Modify: `tests/test_artifacts.py`

- [ ] **Step 1: Run the targeted backend suite**

Run:

```bash
.\.venv\Scripts\python -m pytest tests/test_ensemble_inference.py tests/test_v2_api.py tests/test_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 2: Reproduce the real sample image through the live API**

Run:

```bash
$img = [Convert]::ToBase64String([IO.File]::ReadAllBytes('backend\data\whitestone-v2.png'))
$body = @{ image = $img; model_variant = 'ensemble' } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v2/generate-dxf' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 600
```

Expected: a 200 response with `quality_metrics.opening_count > 0` and an artifact directory containing `structure_preview.png` and `openings_debug.json`.

- [ ] **Step 3: Inspect the latest artifact screenshots before claiming success**

Run:

```bash
Get-ChildItem "$env:TEMP\pointai_artifacts" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 Name,LastWriteTime
```

Expected: a fresh artifact folder from the verification run.

- [ ] **Step 4: Commit the final verified changes**

```bash
git add backend/ensemble_inference.py backend/services/parse_service.py backend/artifacts.py tests/test_ensemble_inference.py tests/test_v2_api.py tests/test_artifacts.py
git commit -m "feat(openings): auto-place doors and windows without manual input"
```
